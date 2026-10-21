import json
import sqlite3
import zipfile
from core.privacy.lifecycle import PrivacyLifecycleService
from core.privacy.export_bundle import build_export_bundle


def test_export_does_not_silently_limit_cases(tmp_path):
    db = tmp_path / 'jobs.db'
    with sqlite3.connect(db) as conn:
        conn.execute('CREATE TABLE application_cases (id TEXT PRIMARY KEY)')
        conn.executemany('INSERT INTO application_cases VALUES (?)', [(str(i),) for i in range(5001)])
        conn.execute('CREATE TABLE lifecycle_tasks (id TEXT)')
        conn.execute("INSERT INTO lifecycle_tasks VALUES ('synthetic-task')")
    service = PrivacyLifecycleService(dirs={'root': tmp_path}, database_path=db)
    result = service.export_my_data(tmp_path / 'exports', user_confirmed_pii=True)
    assert result.ok
    with zipfile.ZipFile(result.path) as archive:
        assert len(json.loads(archive.read('cases.json'))) == 5001
        assert json.loads(archive.read('lifecycle_tasks.json')) == [{'id': 'synthetic-task'}]


def test_failed_export_leaves_no_partial_archive(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError('synthetic full disk')
    monkeypatch.setattr(zipfile.ZipFile, 'writestr', fail)
    import pytest
    with pytest.raises(OSError):
        build_export_bundle(dest_dir=tmp_path, profile={}, user_confirmed_pii=True)
    assert not list(tmp_path.iterdir())
