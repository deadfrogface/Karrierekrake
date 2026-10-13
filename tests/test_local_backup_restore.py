import pytest
from core.privacy.local_backup import create_backup, verify_backup, restore_to_empty_directory


def test_local_backup_roundtrip(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "profile.json").write_text('{"demo":true}')
    archive = create_backup(source, tmp_path / "backup.zip")
    assert verify_backup(archive)["files"] == 1
    target = tmp_path / "restore"
    assert restore_to_empty_directory(archive, target)["files"] == 1
    assert (target / "profile.json").read_text() == '{"demo":true}'


def test_backup_does_not_overwrite_existing_files(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "profile.txt").write_text("data")
    archive = create_backup(source, tmp_path / "backup.zip")
    with pytest.raises(FileExistsError):
        create_backup(source, archive)
    target = tmp_path / "target"
    target.mkdir()
    (target / "existing").write_text("keep")
    with pytest.raises(FileExistsError):
        restore_to_empty_directory(archive, target)
    assert (target / "existing").read_text() == "keep"
