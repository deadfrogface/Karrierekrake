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
    manifest = {
        'tag': 'update-1-aaaaaaaaaaaa', 'protocol': 1, 'sequence': 1,
        'components': {
            'app': {'path': u.TARGETS['app'], 'size': 1, 'sha256': 'a' * 64,
                    'parts': [{'size': 1, 'sha256': 'a' * 64,
                               'url': 'https://github.com/deadfrogface/Karrierekrake/releases/download/update-1-aaaaaaaaaaaa/app-001.bin'}]},
            'model': {'path': u.TARGETS['model'], 'size': 1, 'sha256': 'b' * 64,
                      'parts': [{'size': 1, 'sha256': 'b' * 64,
                                 'url': 'https://github.com/deadfrogface/Karrierekrake/releases/download/update-1-aaaaaaaaaaaa/model-001.bin'}]},
        },
    }
    (tmp_path / u.CURRENT).write_text(json.dumps(manifest))
    panel = UpdatePanel()
    qtbot.addWidget(panel)
    assert not panel.install_button.isHidden()
    assert 'KI-Modell' in panel.install_button.text()


def test_missing_model_install_stages_only_model(qtbot, tmp_path, monkeypatch):
    import sys
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(u, 'install_root', lambda: tmp_path)
    manifest = {
        'tag': 'update-1-aaaaaaaaaaaa',
        'protocol': 1,
        'sequence': 1,
        'components': {
            'app': {'path': u.TARGETS['app'], 'size': 1, 'sha256': 'a' * 64,
                    'parts': [{'size': 1, 'sha256': 'a' * 64,
                               'url': 'https://github.com/deadfrogface/Karrierekrake/releases/download/update-1-aaaaaaaaaaaa/app-001.bin'}]},
            'model': {'path': u.TARGETS['model'], 'size': 1, 'sha256': 'b' * 64,
                      'parts': [{'size': 1, 'sha256': 'b' * 64,
                                 'url': 'https://github.com/deadfrogface/Karrierekrake/releases/download/update-1-aaaaaaaaaaaa/model-001.bin'}]},
        },
    }
    (tmp_path / u.CURRENT).write_text(json.dumps(manifest))
    calls = []
    monkeypatch.setattr(u, 'stage_update', lambda manifest, **kw: calls.append(kw.get('only_components')) or tmp_path)
    monkeypatch.setattr(u, 'launch_installer', lambda stage: None)
    monkeypatch.setattr('desktop.widgets.update_panel.confirm_action', lambda *a, **kw: True)
    panel = UpdatePanel()
    qtbot.addWidget(panel)
    panel.install()
    qtbot.waitUntil(lambda: not panel.busy, timeout=3000)
    assert calls == [{'model'}]


def test_download_failure_shows_cause_and_allows_retry(qtbot, tmp_path, monkeypatch):
    import sys
    from desktop.i18n import tr
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(u, 'install_root', lambda: tmp_path)
    (tmp_path / u.CURRENT).write_text(json.dumps({'tag': 'old'}))
    (tmp_path / u.MODEL_PATH).parent.mkdir(parents=True)
    (tmp_path / u.MODEL_PATH).write_bytes(b'model')
    panel = UpdatePanel()
    qtbot.addWidget(panel)
    def failed():
        raise PermissionError('private user path should not appear')
    panel._run(failed, lambda value: None)
    qtbot.waitUntil(lambda: not panel.busy)
    from PySide6.QtCore import Qt
    assert panel.status.textInteractionFlags() & Qt.TextInteractionFlag.TextSelectableByMouse
    assert 'write_permission_denied' in panel.status.text()
    assert 'private user path' not in panel.status.text()
    assert panel.check_button.isEnabled() and panel.install_button.isEnabled()
