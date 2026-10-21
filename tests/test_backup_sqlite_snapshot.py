import sqlite3
from core.privacy.local_backup import create_backup, restore_to_empty_directory


def test_live_wal_commits_are_present_after_restore(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    db = sqlite3.connect(source / 'jobs.db')
    try:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('CREATE TABLE demo (value TEXT)')
        db.execute("INSERT INTO demo VALUES ('committed')")
        db.commit()
        archive = create_backup(source, tmp_path / 'backup.zip')
        destination = tmp_path / 'restored'
        restore_to_empty_directory(archive, destination)
        restored = sqlite3.connect(destination / 'jobs.db')
        try:
            assert restored.execute('SELECT value FROM demo').fetchone() == ('committed',)
        finally:
            restored.close()
        assert not (destination / 'jobs.db-wal').exists()
    finally:
        db.close()
