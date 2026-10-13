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



def test_backup_rejects_windows_drive_like_member(tmp_path):
    import json
    import zipfile
    archive = tmp_path / "unsafe.zip"
    name = "C:private.txt"
    manifest = {"schema": "karrierekrake.local-backup.v1",
                "files": {name: {"size": 1, "sha256": "0" * 64}}}
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        zf.writestr("data/" + name, b"x")
    with pytest.raises(ValueError, match="backup_unsafe_path"):
        restore_to_empty_directory(archive, tmp_path / "restore")



def test_restore_rejects_symlink_destination(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "file.txt").write_text("data")
    archive = create_backup(source, tmp_path / "backup.zip")
    real_target = tmp_path / "real"
    real_target.mkdir()
    symlink = tmp_path / "linked"
    try:
        symlink.symlink_to(real_target, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    with pytest.raises(ValueError, match="restore_symlink_destination"):
        restore_to_empty_directory(archive, symlink)
    assert list(real_target.iterdir()) == []


@pytest.mark.parametrize("name", ["CON", "docs/NUL.txt", "LPT1", "folder/trailing.", "folder/trailing ", "file\\x01.txt"])
def test_backup_rejects_platform_unsafe_names(tmp_path, name):
    import json
    import zipfile
    archive = tmp_path / "unsafe.zip"
    manifest = {"schema": "karrierekrake.local-backup.v1",
                "files": {name: {"size": 1, "sha256": "0" * 64}}}
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        zf.writestr("data/" + name, b"x")
    with pytest.raises(ValueError, match="backup_unsafe_path"):
        verify_backup(archive)
