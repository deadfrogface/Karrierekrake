from desktop.pages.settings import SettingsPage


def test_backup_settings_actions_available():
    assert callable(SettingsPage._create_local_backup)
    assert callable(SettingsPage._verify_local_backup)


def test_backup_error_dialog_does_not_expose_private_path(monkeypatch):
    from desktop.pages import settings
    from core.privacy import local_backup
    messages = []
    monkeypatch.setattr(settings.QFileDialog, "getExistingDirectory", lambda *a: "/private/home/CV")
    monkeypatch.setattr(settings.QFileDialog, "getSaveFileName", lambda *a: ("/private/home/CV/archive.zip", ""))
    monkeypatch.setattr(local_backup, "create_backup", lambda *a: (_ for _ in ()).throw(OSError("/private/home/CV/secret.pdf")))
    monkeypatch.setattr(settings.QMessageBox, "warning", lambda *a: messages.append(a[-1]))
    SettingsPage._create_local_backup(None)
    assert len(messages) == 1
    assert "/private/" not in messages[0]
    assert "secret.pdf" not in messages[0]


def test_backup_verify_error_dialog_does_not_expose_private_path(monkeypatch):
    from desktop.pages import settings
    from core.privacy import local_backup
    messages = []
    monkeypatch.setattr(settings.QFileDialog, "getOpenFileName", lambda *a: ("/private/home/archive.zip", ""))
    monkeypatch.setattr(local_backup, "verify_backup", lambda *a, **kw: (_ for _ in ()).throw(ValueError("/private/home/secret.pdf")))
    monkeypatch.setattr(settings.QMessageBox, "warning", lambda *a: messages.append(a[-1]))
    class _BrokenBackupPage:
        def _run_backup_operation(self, operation, message):
            try:
                operation(lambda: False)
            except ValueError:
                settings.QMessageBox.warning(None, 'Backup fehlgeschlagen', 'Backup konnte nicht geprüft werden.')
    SettingsPage._verify_local_backup(_BrokenBackupPage())
    assert len(messages) == 1
    assert "/private/" not in messages[0]
    assert "secret.pdf" not in messages[0]
