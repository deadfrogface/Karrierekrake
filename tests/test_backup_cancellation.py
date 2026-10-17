from pathlib import Path
import pytest
from core.privacy.local_backup import create_backup, restore_to_empty_directory


def test_cancelled_backup_leaves_no_archive(tmp_path):
    source = tmp_path / 'source'; source.mkdir()
    (source / 'sample.txt').write_text('synthetic')
    destination = tmp_path / 'backup.zip'
    with pytest.raises(InterruptedError):
        create_backup(source, destination, cancelled=lambda: True)
    assert not destination.exists()
    assert not list(tmp_path.glob('.kk-backup-*'))


def test_cancelled_restore_preserves_empty_target(tmp_path):
    source = tmp_path / 'source'; source.mkdir()
    (source / 'sample.txt').write_text('synthetic')
    archive = create_backup(source, tmp_path / 'backup.zip')
    target = tmp_path / 'target'; target.mkdir()
    with pytest.raises(InterruptedError):
        restore_to_empty_directory(archive, target, cancelled=lambda: True)
    assert target.is_dir() and not list(target.iterdir())
    assert not list(tmp_path.glob('.kk-restore-*'))
