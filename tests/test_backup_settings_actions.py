from desktop.pages.settings import SettingsPage


def test_backup_settings_actions_available():
    assert callable(SettingsPage._create_local_backup)
    assert callable(SettingsPage._verify_local_backup)
