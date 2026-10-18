"""Model setup panel on top of the setup-threshold patch (02be8fc6).

Uses the REAL recommend_setup_model through guenther.setup_models.inspect_setup_device
with faked device detection (psutil / disk), no hand-built recommendation.
Lives apart from test_model_setup_ux.py so the designer patch stays valid on
adc297cf without the threshold patch.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from PySide6.QtCore import Qt

from desktop.i18n import tr
from desktop.widgets import model_setup_panel as panels
from guenther import setup_models as setup

SMALL, MID, LARGE = "qwen3.5-4b-gsq", "qwen3-8b-gsq", "qwen3.8-27b-gsq-rco"
GIB = 1024 ** 3


def _fake_device(monkeypatch, total_gib, free_gib, cores, tmp_path):
    import psutil

    from guenther import model_manager
    monkeypatch.setattr(psutil, "virtual_memory",
                        lambda: SimpleNamespace(total=int(total_gib * GIB), available=int(free_gib * GIB)))
    monkeypatch.setattr(psutil, "cpu_count", lambda logical=True: cores)
    monkeypatch.setattr(setup.shutil, "disk_usage",
                        lambda path: SimpleNamespace(total=10**12, used=0, free=500_000_000_000))
    monkeypatch.setattr(model_manager, "default_models_dir", lambda: tmp_path)
    monkeypatch.setattr(panels, "selected_model_path", lambda: None)
    monkeypatch.setattr(panels, "selected_model_id", lambda: None)


@pytest.mark.parametrize("total,free,cores,selectable,locked,warnings", [
    (7.7, 3.0, 2, [SMALL], [MID, LARGE], ["low_free_ram"]),
    (15.6, 12.0, 4, [SMALL, MID], [LARGE], []),  # low_free_ram not asserted either way
    (31.6, 28.0, 2, [SMALL, MID, LARGE], [], ["slow_cpu"]),
], ids=["7.7GiB-3free-2cores", "15.6GiB-12free-4cores", "31.6GiB-28free-2cores"])
def test_real_recommendation_panel_states(qtbot, monkeypatch, tmp_path,
                                          total, free, cores, selectable, locked, warnings):
    _fake_device(monkeypatch, total, free, cores, tmp_path)
    started = []
    monkeypatch.setattr(panels, "install_recommended_model", lambda mid, **k: started.append(mid))
    real = setup.inspect_setup_device()  # real recommend_setup_model on the faked device
    assert real.model_id == SMALL and real.fits[SMALL] is True
    assert all(real.peak_unverified[mid] is True for mid in setup.SETUP_MODEL_CATALOG)
    panel = panels.ModelSetupPanel()
    qtbot.addWidget(panel)
    panel.show()
    assert panel.state == "ready"
    # All unverified: nothing preselected, nothing "Empfohlen", button off until chosen.
    assert panel.model_choice.currentIndex() == -1
    assert not panel.install_button.isEnabled()
    assert panel.recommended.text() == "Wähle das Modell aus, um es herunterzuladen."
    assert panel.recommended.isVisible()
    for i in range(panel.model_choice.count()):
        assert "empfohlen" not in panel.model_choice.itemText(i).lower()
    # Only warnings the optimizer named are asserted; low_free_ram is neither
    # required nor excluded for 15.6 / 31.6 GiB (Kritiker Fund 2 zu 02be8fc6).
    for code in warnings:
        assert code in real.warnings
        assert panel.warnings.isVisible()
        assert tr("setup.model.warning." + code) in panel.warnings.text()
    for mid in locked:
        index = panel.model_choice.findData(mid)
        assert real.fits[mid] is False
        reason = tr("setup.model.block.ram_too_small")
        assert reason in panel.model_choice.itemText(index)
        spoken = panel.model_choice.itemData(index, Qt.ItemDataRole.AccessibleTextRole)
        assert spoken.endswith(tr("setup.model.blocked_a11y", reason=reason))
        panel.model_choice.setCurrentIndex(index)
        assert not panel.install_button.isEnabled()
        assert reason in panel.install_button.accessibleName()
    for mid in selectable:
        assert real.fits[mid] is True
        index = panel.model_choice.findData(mid)
        assert "noch nicht gemessen" in panel.model_choice.itemText(index)
        panel.model_choice.setCurrentIndex(index)  # explicit choice
        assert panel.install_button.isEnabled()
        assert panel.unverified_note.isVisible()
        assert tr("setup.model.unverified_note") in panel.install_button.accessibleName()
    assert started == []


def _panel_for_device(qtbot, monkeypatch, tmp_path, total, free, cores):
    _fake_device(monkeypatch, total, free, cores, tmp_path)
    monkeypatch.setattr(panels, "install_recommended_model", lambda *a, **k: pytest.fail("download"))
    panel = panels.ModelSetupPanel()
    qtbot.addWidget(panel)
    panel.show()
    return panel


def test_8gb_little_free_memory_shows_grey_low_free_ram_hint(qtbot, monkeypatch, tmp_path):
    panel = _panel_for_device(qtbot, monkeypatch, tmp_path, 7.7, 3.0, 2)
    assert "low_free_ram" in panel.fit.warnings
    assert panel.warnings.isVisible() and panel.warnings.objectName() == "ModelSetupHint"
    assert tr("setup.model.warning.low_free_ram") in panel.warnings.text()


# low_free_ram fix of the optimizer (Kritiker Fund 2 zu 02be8fc6) is in 58e27efe.
def test_8gb_enough_free_memory_shows_no_low_free_ram_hint(qtbot, monkeypatch, tmp_path):
    panel = _panel_for_device(qtbot, monkeypatch, tmp_path, 7.7, 6.5, 2)
    assert "low_free_ram" not in panel.fit.warnings
    assert tr("setup.model.warning.low_free_ram") not in panel.warnings.text()


def test_adapter_uses_budgets_from_guenther_model_budgets(monkeypatch):
    """One source: the adapter has no local copy and reads guenther.model_budgets per call."""
    from desktop.widgets import model_fit
    from guenther import model_budgets
    assert model_fit.model_budgets is model_budgets
    assert not hasattr(model_fit, "_LocalBudgets") and not hasattr(model_fit, "_budgets")
    shape = SimpleNamespace(total_gib=15.6, available_gib=12.0, physical_cores=4,
                            free_disk_bytes=100 * GIB, model_id=None)  # no fits -> fallback path
    assert model_fit.adapt_setup_recommendation(shape).model(MID).fits
    # Raise the optimizer's 8B class gate: the adapter must follow it.
    monkeypatch.setitem(model_budgets.CLASS_TOTAL_GATE_GIB, model_budgets.CLASS_8B, 16.0)
    fit = model_fit.adapt_setup_recommendation(shape)
    assert not fit.model(MID).fits and fit.model(MID).block_reason == "ram_too_small"
    assert fit.model(SMALL).fits
    # The disk reserve also comes from model_budgets.
    entry = setup.SETUP_MODEL_CATALOG[SMALL]
    monkeypatch.setattr(model_budgets, "DISK_RESERVE_BYTES", 10**15)
    assert model_fit.derive_fallback_fits(entry, 15.6, 12.0, 100 * GIB, False, SMALL)[:2] == (
        False, "disk_too_small")
