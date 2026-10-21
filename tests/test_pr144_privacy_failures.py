"""Unreadable data is not evidence of successful deletion."""
from core.privacy.lifecycle import PrivacyLifecycleService


def test_corrupt_database_does_not_report_deleted(tmp_path):
    database = tmp_path / 'jobs.db'
    database.write_bytes(b'not a SQLite database')
    service = PrivacyLifecycleService(dirs={'data': tmp_path}, database_path=database)
    assert not service.delete_mail_cache().ok
    assert not service.delete_hr_contacts().ok
    assert not service.delete_application_case('case').ok
    assert 'jobs' in service.verify_no_unexpected_data()


def test_unreadable_profile_does_not_report_deleted(tmp_path):
    def unavailable():
        raise OSError('unavailable')
    service = PrivacyLifecycleService(dirs={'data': tmp_path}, load_profile=unavailable)
    assert not service.delete_profile().verified


def test_delete_all_credentials_covers_every_provider(tmp_path):
    from integrations.secure_tokens import MANAGED_TOKEN_ACCOUNTS, store_token, token_absent_verified
    for account in MANAGED_TOKEN_ACCOUNTS:
        store_token(account, {'refresh_token': 'synthetic'}, fallback_dir=tmp_path)
    service = PrivacyLifecycleService(dirs={'data': tmp_path}, token_dir=tmp_path)
    assert service.delete_oauth_tokens().verified
    assert all(token_absent_verified(account, fallback_dir=tmp_path) for account in MANAGED_TOKEN_ACCOUNTS)


def test_inaccessible_keyring_cannot_confirm_deletion(tmp_path, monkeypatch):
    from integrations import secure_tokens
    monkeypatch.setattr(secure_tokens, '_keyring', lambda: None)
    service = PrivacyLifecycleService(dirs={'data': tmp_path}, token_dir=tmp_path)
    assert not service.delete_oauth_tokens().verified
