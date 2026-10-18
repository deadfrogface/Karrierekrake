"""Setup recommendations, atomic activation and responsive one-click UI."""
import hashlib
import io
import json
import threading

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QWizard

from guenther import setup_models as setup
from guenther import model_manager as models
from desktop.widgets import model_setup_panel as panels
from desktop.wizard import FirstRunWizard
from tests.test_ui_manual_qa_fixes import config_service


@pytest.mark.parametrize('ram,free,cores,expected,alternatives,warnings', [
    (16,12,2,'qwen3.5-4b-gsq', ('qwen3-8b-gsq',), ('slow_cpu',)),
    # PR144 setup thresholds, behaviour change: old expected 'qwen3-8b-gsq',
    # new 'qwen3.5-4b-gsq'. 8B is never the recommendation while its peak is
    # unverified; it must be listed as an alternative (fits, peak_unverified).
    (24,18,6,'qwen3.5-4b-gsq', ('qwen3-8b-gsq',), ()),
    (24,8,6,'qwen3.5-4b-gsq', ('qwen3-8b-gsq',), ()),
    # PR144 Teamlead decision 1, behaviour change: old expected
    # 'qwen3.8-27b-gsq-rco' (alternatives 8B, 4B), new 'qwen3.5-4b-gsq'.
    # Attestation duty applies to every class above 4B, including 27B; 27B
    # and 8B are unattested and stay selectable alternatives.
    (64,40,16,'qwen3.5-4b-gsq', ('qwen3.8-27b-gsq-rco', 'qwen3-8b-gsq'), ()),
    # PR144 setup thresholds, behaviour change: old expected None (dead end),
    # new 'qwen3.5-4b-gsq' with NO warning. Total RAM classifies the device;
    # 5 GiB free is above the reachable 4B low_free_ram threshold (~3.57 GiB).
    (24,5,6,'qwen3.5-4b-gsq', ('qwen3-8b-gsq',), ()),
    # PR144 setup thresholds, new pure-logic case: 8 GB laptop, 3 GiB free
    # is below ~3.57 GiB -> 4B with low_free_ram.
    (7.7,3.0,2,'qwen3.5-4b-gsq', (), ('low_free_ram',)),
])
def test_recommendation_balances_device_and_current_resources(ram, free, cores, expected,
                                                              alternatives, warnings):
    result = setup.recommend_setup_model(total_gib=ram, available_gib=free,
                                        physical_cores=cores, free_disk_bytes=100_000_000_000)
    assert result.model_id == expected
    assert result.reason is None
    assert result.fits[expected] is True
    assert result.warnings == warnings
    for mid in alternatives:
        assert mid in result.alternatives
        assert result.fits[mid] is True
        assert result.peak_unverified[mid] is True


def test_not_enough_disk_does_not_offer_an_uninstallable_model():
    result = setup.recommend_setup_model(total_gib=64, available_gib=60,
                                        physical_cores=16, free_disk_bytes=1_000_000_000)
    assert result.model_id is None


@pytest.fixture
def downloaded_model(tmp_path, monkeypatch):
    mid = 'qwen3.5-4b-gsq'
    payload = b'verified fake test weights' * 50_000
    entry = dict(setup.SETUP_MODEL_CATALOG[mid], approx_bytes=len(payload),
                 sha256=hashlib.sha256(payload).hexdigest())
    monkeypatch.setattr(setup, 'SETUP_MODEL_CATALOG', {mid: entry})
    monkeypatch.setenv('KARRIEREKRAKE_MODELS_DIR', str(tmp_path))
    class Response(io.BytesIO):
        status = 200
        headers = {'Content-Length': str(len(payload))}
    monkeypatch.setattr(models.urllib.request, 'urlopen', lambda *a, **k: Response(payload))
    return mid, payload, tmp_path


def test_download_then_probe_then_activation_selects_both_runtime_paths(downloaded_model, monkeypatch):
    from core import model_probe, cv_llm_runtime
    from guenther.hardware import resolve_production_model
    mid, payload, root = downloaded_model
    stages = []
    def probe(model_id, **_):
        assert setup.selected_model_id() is None
        assert models.ModelManager(root).model_path(model_id).read_bytes() == payload
        stages.append('probe')
    monkeypatch.setattr(model_probe, 'probe_in_subprocess', probe)
    path = setup.install_recommended_model(mid, cancelled=lambda: False,
                                          progress=lambda p: stages.append(p.status))
    assert stages[-1] == 'probe'
    assert setup.selected_model_id() == mid
    assert cv_llm_runtime.resolve_cv_model_path() == path
    assert resolve_production_model('qwen3.5-4b') == mid


@pytest.mark.parametrize('failure', ['probe', 'cancel'])
def test_failed_or_cancelled_load_never_activates_model(downloaded_model, monkeypatch, failure):
    from core import model_probe
    mid, _, root = downloaded_model
    cancelled = threading.Event()
    def probe(*a, **k):
        if failure == 'cancel':
            cancelled.set()
        else:
            raise RuntimeError('model_probe_failed')
    monkeypatch.setattr(model_probe, 'probe_in_subprocess', probe)
    with pytest.raises(RuntimeError):
        setup.install_recommended_model(mid, cancelled=cancelled.is_set, progress=lambda _: None)
    assert not (root / 'active-model.json').exists()


def test_bad_checksum_never_probes_or_activates(downloaded_model, monkeypatch):
    from core import model_probe
    mid, _, root = downloaded_model
    setup.SETUP_MODEL_CATALOG[mid]['sha256'] = '0' * 64
    monkeypatch.setattr(model_probe, 'probe_in_subprocess', lambda *a, **k: pytest.fail('corrupt load'))
    with pytest.raises(RuntimeError, match='checksum_mismatch'):
        setup.install_recommended_model(mid, cancelled=lambda: False, progress=lambda _: None)
    assert not (root / 'active-model.json').exists()


def test_selected_model_survives_restart_and_missing_file_does_not_load_bundled_model(tmp_path, monkeypatch):
    from core import cv_llm_runtime
    monkeypatch.setenv('KARRIEREKRAKE_MODELS_DIR', str(tmp_path))
    mid = 'qwen3-8b-gsq'
    setup.activate_model(mid, tmp_path)
    fallback = tmp_path / 'bundled.gguf'
    fallback.write_bytes(b'legacy weights')
    monkeypatch.setattr(cv_llm_runtime, 'bundled_cv_model_candidates', lambda: [fallback])
    assert setup.selected_model_id() == mid
    assert cv_llm_runtime.resolve_cv_model_path() is None
    path = tmp_path / mid / setup.SETUP_MODEL_CATALOG[mid]['filename']
    path.parent.mkdir()
    path.write_bytes(b'selected weights')
    assert cv_llm_runtime.resolve_cv_model_path() == path


def test_setup_click_keeps_gui_responsive_and_allows_next_after_success(qtbot, config_service, monkeypatch, tmp_path):
    recommendation = setup.recommend_setup_model(total_gib=24, available_gib=18,
                                                 physical_cores=6, free_disk_bytes=100_000_000_000)
    monkeypatch.setattr(panels, 'inspect_setup_device', lambda: recommendation)
    activated = {'path': None}
    monkeypatch.setattr(panels, 'selected_model_path', lambda: activated['path'])
    monkeypatch.setattr(panels, 'selected_model_id', lambda: 'qwen3-8b-gsq' if activated['path'] else None)
    blocked, started = threading.Event(), threading.Event()
    def install(mid, **kwargs):
        assert mid == 'qwen3-8b-gsq'
        started.set()
        blocked.wait(3)
        activated['path'] = tmp_path / 'verified.gguf'
        return activated['path']
    monkeypatch.setattr(panels, 'install_recommended_model', install)
    wizard = FirstRunWizard(config_service)
    qtbot.addWidget(wizard)
    wizard.show()
    panel = wizard.model.updates
    # PR144 setup thresholds: 8B is an alternative now; pick it explicitly.
    panel.model_choice.setCurrentIndex(panel.model_choice.findData('qwen3-8b-gsq'))
    ticks = []
    timer = QTimer(wizard)
    timer.timeout.connect(lambda: ticks.append(True))
    timer.start(5)
    panel.install_button.click()
    try:
        qtbot.waitUntil(started.is_set)
        qtbot.waitUntil(lambda: len(ticks) >= 3)
        assert not wizard.button(QWizard.WizardButton.NextButton).isEnabled()
    finally:
        blocked.set()
    qtbot.waitUntil(lambda: not panel.busy)
    assert panel.install_button.isVisible()  # user may install a different model later
    assert panel.install_button.isEnabled()
    assert wizard.button(QWizard.WizardButton.NextButton).isEnabled()
    assert config_service.load().settings.guenther_model == 'qwen3-8b-gsq'
    assert config_service.is_first_run()
    wizard.reject()


def test_setup_cancel_keeps_current_model_and_can_retry(qtbot, monkeypatch):
    monkeypatch.setattr(panels, 'selected_model_path', lambda: None)
    started = threading.Event()
    def install(mid, *, cancelled, progress):
        started.set()
        assert started.wait(1)
        while not cancelled():
            threading.Event().wait(.01)
        raise RuntimeError('cancelled')
    recommendation = setup.recommend_setup_model(total_gib=16, available_gib=12,
                                                 physical_cores=2, free_disk_bytes=100_000_000_000)
    monkeypatch.setattr(panels, 'inspect_setup_device', lambda: recommendation)
    monkeypatch.setattr(panels, 'install_recommended_model', install)
    panel = panels.ModelSetupPanel()
    qtbot.addWidget(panel)
    activated = []
    panel.model_ready.connect(activated.append)
    panel.install_button.click()
    qtbot.waitUntil(started.is_set)
    panel.cancel_button.click()
    qtbot.waitUntil(lambda: not panel.busy)
    assert not activated
    assert panel.install_button.isEnabled()
    assert panel.cancel_button.isHidden()


def test_app_updates_retain_selected_setup_model(tmp_path, monkeypatch):
    from core import app_updates as updates
    from tests.test_app_updates import installed, manifest, Response
    root = tmp_path / 'app'
    root.mkdir()
    installed(root)
    models_root = tmp_path / 'models'
    models_root.mkdir()
    mid = 'qwen3-8b-gsq'
    monkeypatch.setenv('KARRIEREKRAKE_MODELS_DIR', str(models_root))
    path = models_root / mid / setup.SETUP_MODEL_CATALOG[mid]['filename']
    path.parent.mkdir()
    path.write_bytes(b'independently installed model')
    setup.activate_model(mid, models_root)
    calls = []
    def get(url, **kwargs):
        calls.append(url)
        return Response(b'new app')
    monkeypatch.setattr(updates, '_get', get)
    new = manifest(model=b'new default weights')
    stage = updates.stage_update(new, root)
    assert len(calls) == 1 and calls[0].endswith('app-001.bin')
    assert not (stage / updates.MODEL_PATH).exists()
    assert path.read_bytes() == b'independently installed model'
    assert setup.selected_model_id() == mid


def test_load_probe_timeout_terminates_child_and_removes_result_file(monkeypatch):
    from core import model_probe
    import subprocess
    import sys
    from pathlib import Path
    original = subprocess.Popen
    spawned, result_files = [], []
    def spawn(command, **kwargs):
        result_files.append(Path(command[-1]))
        proc = original([sys.executable, '-c', 'import time; time.sleep(30)'], **kwargs)
        spawned.append(proc)
        return proc
    monkeypatch.setattr(model_probe.subprocess, 'Popen', spawn)
    with pytest.raises(RuntimeError, match='model_probe_timeout'):
        model_probe.probe_in_subprocess('qwen3.5-4b-gsq', cancelled=lambda: False, timeout_seconds=.15)
    assert spawned[0].poll() is not None
    assert not result_files[0].exists()


def test_device_scan_does_not_start_network_or_load_llama(qtbot, monkeypatch):
    import urllib.request
    from core import model_probe
    monkeypatch.setattr(urllib.request, 'urlopen', lambda *a, **k: pytest.fail('network during scan'))
    monkeypatch.setattr(model_probe, 'probe_model', lambda *a: pytest.fail('inference during scan'))
    panel = panels.ModelSetupPanel()
    qtbot.addWidget(panel)
    assert panel.recommendation is not None
    assert not panel.busy


def test_previous_setup_users_get_device_aware_popup_once(qapp, config_service, monkeypatch):
    from desktop.main_window import MainWindow
    from PySide6.QtWidgets import QWidget, QDialog
    config_service.save_meta({'first_run_completed': True, 'setup_flow_version': 2})
    shown = []
    def finish(wizard):
        shown.append(wizard.model.updates.recommendation)
        wizard.accept()
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(FirstRunWizard, 'exec', finish)
    window = QWidget()
    window.config_service = config_service
    window.refresh_all = lambda: None
    MainWindow.maybe_run_wizard(window)
    MainWindow.maybe_run_wizard(window)
    assert len(shown) == 1
    assert config_service.load_meta()['setup_flow_version'] == 3


def test_setup_offers_compatible_alternatives_without_automatic_download(qtbot, monkeypatch):
    recommendation = setup.recommend_setup_model(
        total_gib=64, available_gib=40, physical_cores=16,
        free_disk_bytes=100_000_000_000)
    monkeypatch.setattr(panels, "inspect_setup_device", lambda: recommendation)
    monkeypatch.setattr(panels, "selected_model_path", lambda: None)
    panel = panels.ModelSetupPanel()
    qtbot.addWidget(panel)
    # PR144 Teamlead decision 1: old expected "qwen3.8-27b-gsq-rco"; without a
    # 27B attestation the recommendation (preselection) is 4B, 27B and 8B stay
    # selectable alternatives (asserted by the item set below).
    assert panel.model_choice.currentData() == "qwen3.5-4b-gsq"
    assert {panel.model_choice.itemData(i) for i in range(panel.model_choice.count())} == set(setup.SETUP_MODEL_CATALOG)
    assert panel.install_button.isEnabled()
    assert not panel.busy


def test_setup_can_change_previously_selected_model(qtbot, monkeypatch, tmp_path):
    recommendation = setup.recommend_setup_model(
        total_gib=24, available_gib=18, physical_cores=6,
        free_disk_bytes=100_000_000_000)
    monkeypatch.setattr(panels, "inspect_setup_device", lambda: recommendation)
    monkeypatch.setattr(panels, "selected_model_path", lambda: tmp_path / "old.gguf")
    monkeypatch.setattr(panels, "selected_model_id", lambda: "qwen3.5-4b-gsq")
    panel = panels.ModelSetupPanel()
    qtbot.addWidget(panel)
    assert not panel.install_button.isHidden()
    assert panel.model_choice.count() >= 2
    panel.model_choice.setCurrentIndex(panel.model_choice.findData("qwen3-8b-gsq"))
    assert panel.model_choice.currentData() == "qwen3-8b-gsq"


def test_explicit_model_choice_survives_hardware_refresh(qtbot, monkeypatch):
    recommendation = setup.recommend_setup_model(
        total_gib=64, available_gib=40, physical_cores=16,
        free_disk_bytes=100_000_000_000)
    monkeypatch.setattr(panels, "inspect_setup_device", lambda: recommendation)
    monkeypatch.setattr(panels, "selected_model_path", lambda: None)
    panel = panels.ModelSetupPanel()
    qtbot.addWidget(panel)
    panel.model_choice.setCurrentIndex(panel.model_choice.findData("qwen3-8b-gsq"))
    panel.refresh_recommendation()
    assert panel.model_choice.currentData() == "qwen3-8b-gsq"


def test_active_model_persists_and_cv_runtime_resolves_it(tmp_path, monkeypatch):
    from core import cv_llm_runtime as runtime
    from guenther import setup_models as setup_models_module
    from guenther import model_manager

    monkeypatch.setattr(model_manager, "default_models_dir", lambda: tmp_path)
    monkeypatch.delenv("KARRIEREKRAKE_CV_LLM_MODEL", raising=False)
    for model_id in setup_models_module.SETUP_MODEL_CATALOG:
        spec = setup_models_module.SETUP_MODEL_CATALOG[model_id]
        path = tmp_path / model_id / spec["filename"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"test-gguf")
        setup_models_module.activate_model(model_id, tmp_path)
        assert setup_models_module.selected_model_id() == model_id
        assert setup_models_module.selected_model_path() == path
        assert runtime.resolve_cv_model_path() == path


def test_hardware_inspection_before_model_directory_exists(tmp_path, monkeypatch):
    from guenther import model_manager
    from guenther import setup_models as models

    fresh_dir = tmp_path / "not-yet-created" / "models"
    monkeypatch.setattr(model_manager, "default_models_dir", lambda: fresh_dir)
    result = models.inspect_setup_device()
    assert result.free_disk_bytes > 0
    assert result.total_gib > 0
    assert not fresh_dir.exists()


def test_selected_model_rejects_symlink_outside_managed_store(tmp_path):
    mid = "qwen3-8b-gsq"
    external = tmp_path / "external.gguf"
    external.write_bytes(b"not a managed model")
    setup.activate_model(mid, tmp_path)
    model_dir = tmp_path / mid
    model_dir.mkdir()
    link = model_dir / setup.SETUP_MODEL_CATALOG[mid]["filename"]
    try:
        link.symlink_to(external)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation unavailable on this runner")
    assert setup.selected_model_path(tmp_path) is None


def test_setup_offers_installed_model_even_when_disk_is_full(qtbot, monkeypatch, tmp_path):
    mid = "qwen3.5-4b-gsq"
    path = tmp_path / "existing.gguf"
    path.write_bytes(b"existing")
    recommendation = setup.recommend_setup_model(
        total_gib=16, available_gib=12, physical_cores=4, free_disk_bytes=1)
    assert recommendation.model_id is None
    monkeypatch.setattr(panels, "inspect_setup_device", lambda: recommendation)
    monkeypatch.setattr(panels, "selected_model_id", lambda: mid)
    monkeypatch.setattr(panels, "selected_model_path", lambda: path)
    panel = panels.ModelSetupPanel()
    qtbot.addWidget(panel)
    assert panel.model_choice.currentData() == mid
    assert panel.install_button.isEnabled()


def test_selected_model_rejects_symlinked_model_directory(tmp_path):
    mid = "qwen3-8b-gsq"
    setup.activate_model(mid, tmp_path)
    external = tmp_path / "external"
    external.mkdir()
    (external / setup.SETUP_MODEL_CATALOG[mid]["filename"]).write_bytes(b"outside")
    try:
        (tmp_path / mid).symlink_to(external, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Directory symlinks unavailable on this runner")
    assert setup.selected_model_path(tmp_path) is None
