"""A missing tray must neither block startup nor hide an unreachable window."""
from types import SimpleNamespace

import pytest
from PySide6.QtGui import QCloseEvent


def test_native_health_ack_precedes_onboarding(monkeypatch):
    from desktop import app
    from core import native_update_install
    order = []
    monkeypatch.setattr(app.sys, 'platform', 'linux')
    monkeypatch.setattr(app.sys, 'frozen', True, raising=False)
    monkeypatch.setattr(native_update_install, 'acknowledge_startup', lambda: order.append('healthy'))
    def onboarding():
        assert order == ['healthy']
        order.append('onboarding')
    app._complete_startup(SimpleNamespace(maybe_run_wizard=onboarding))
    assert order == ['healthy', 'onboarding']


@pytest.mark.parametrize('available', [False, True])
def test_close_only_hides_when_a_tray_is_actually_available(monkeypatch, available):
    import desktop.main_window as module
    calls = []
    tray = SimpleNamespace(isSystemTrayAvailable=lambda: available, isVisible=lambda: True,
                           showMessage=lambda *a: calls.append('message'),
                           MessageIcon=SimpleNamespace(Information=1))
    window = SimpleNamespace(_save_geometry=lambda: None,
        config_service=SimpleNamespace(load=lambda: SimpleNamespace(settings=SimpleNamespace(minimize_to_tray=True))),
        _force_quit=False, _shutting_down=False, tray=tray,
        hide=lambda: calls.append('hide'), _pipeline_running=lambda: False,
        _drop_geo_listener=lambda: calls.append('drop'))
    monkeypatch.setattr(module, 'get_shutdown_manager', lambda: SimpleNamespace(shutdown=lambda **k: calls.append('shutdown')))
    event = QCloseEvent()
    module.MainWindow.closeEvent(window, event)
    if available:
        assert calls == ['hide', 'message']
        assert not event.isAccepted()
    else:
        assert calls == ['drop', 'shutdown']
        assert event.isAccepted()


def test_startup_without_tray_never_opens_a_modal_warning(tmp_path):
    import os
    from pathlib import Path
    import subprocess
    import sys
    code = '''from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMainWindow
from desktop import app
notices = []
class Signal:
    def connect(self, callback): pass
class Server:
    def __init__(self, *args): self.newConnection = Signal()
    @staticmethod
    def removeServer(*args): pass
    def listen(self, *args): return True
class Window(QMainWindow):
    def __init__(self, config):
        super().__init__()
        QTimer.singleShot(0, app.QApplication.instance().quit)
    def maybe_run_wizard(self): pass
    def statusBar(self):
        class Status:
            def showMessage(self, message, timeout): notices.append((message, timeout))
        return Status()
def forbidden(*args): raise AssertionError("modal startup warning blocked readiness")
app.MainWindow = Window
app.QLocalServer = Server
app.acquire_single_instance_lock = lambda: object()
app.QSystemTrayIcon.isSystemTrayAvailable = lambda: False
app.QMessageBox.warning = forbidden
assert app.run() == 0
assert notices == [(app.tr("tray.unavailable"), 15000)]
'''
    child = subprocess.run([sys.executable, '-c', code], cwd=Path(__file__).resolve().parents[1],
                           env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen',
                                'KARRIEREKRAKE_DATA_DIR': str(tmp_path / 'profile')},
                           capture_output=True, text=True, timeout=30)
    assert child.returncode == 0, child.stderr
