import json
from core import app_updates as u
from desktop.widgets.update_panel import UpdatePanel


def test_source_checkout_does_not_start_network(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(u, 'install_root', lambda: tmp_path)
    monkeypatch.setattr(u, 'check_for_update', lambda: (_ for _ in ()).throw(AssertionError('network')))
    panel = UpdatePanel()
    qtbot.addWidget(panel)
    panel.check(quiet=True)
    assert not panel.check_button.isEnabled()
    assert 'manuell' in panel.status.text()


def test_managed_startup_offers_update_without_blocking(qtbot, tmp_path, monkeypatch):
    import sys
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(u, 'install_root', lambda: tmp_path)
    (tmp_path / u.CURRENT).write_text(json.dumps({'tag': 'old'}))
    (tmp_path / u.MODEL_PATH).parent.mkdir(parents=True)
    (tmp_path / u.MODEL_PATH).write_bytes(b'model')
    m = {'components': {'app': {'size': 1024**2}}}
    monkeypatch.setattr(u, 'check_for_update', lambda: m)
    monkeypatch.setattr(u, 'changed_components', lambda *a: ['app'])
    panel = UpdatePanel()
    qtbot.addWidget(panel)
    panel.check(quiet=True)
    qtbot.waitUntil(lambda: not panel.busy, timeout=3000)
    assert panel.manifest == m
    assert not panel.install_button.isHidden()
    assert '1 MB' in panel.status.text()


def test_first_install_offers_missing_model(qtbot, tmp_path, monkeypatch):
    import sys
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(u, 'install_root', lambda: tmp_path)
    (tmp_path / u.CURRENT).write_text(json.dumps({'tag': 'initial'}))
    panel = UpdatePanel()
    qtbot.addWidget(panel)
    assert not panel.install_button.isHidden()
    assert 'KI-Modell' in panel.install_button.text()
