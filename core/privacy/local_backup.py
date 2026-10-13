"""Offline, user-initiated backups with integrity checks and safe test restores.

The caller chooses both the source data directory and destination archive.
No network access, no credentials collection, no automatic overwrite.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path, PurePosixPath
import tempfile
import zipfile

SCHEMA = "karrierekrake.local-backup.v1"
MAX_FILES = 20000
MAX_TOTAL_BYTES = 8 * 1024**3


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def create_backup(source: Path, destination: Path) -> Path:
    """Create a verified ZIP from a closed application's local data folder."""
    source = Path(source).resolve(strict=True)
    destination = Path(destination).resolve()
    if not source.is_dir():
        raise ValueError("backup_source_not_directory")
    if destination.is_relative_to(source):
        raise ValueError("backup_destination_inside_source")
    if destination.exists():
        raise FileExistsError("backup_destination_exists")
    destination.parent.mkdir(parents=True, exist_ok=True)
    files = []
    total = 0
    for path in sorted(source.rglob("*")):
        if path.is_symlink():
            raise ValueError("backup_symlink_not_allowed")
        if not path.is_file():
            continue
        rel = path.relative_to(source).as_posix()
        total += path.stat().st_size
        files.append((path, rel))
        if len(files) > MAX_FILES or total > MAX_TOTAL_BYTES:
            raise ValueError("backup_size_limit")
    fd, temporary = tempfile.mkstemp(prefix=".kk-backup-", suffix=".zip", dir=destination.parent)
    os.close(fd)
    try:
        manifest = {"schema": SCHEMA, "files": {}}
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path, rel in files:
                data = path.read_bytes()
                manifest["files"][rel] = {"size": len(data), "sha256": _sha256(data)}
                archive.writestr("data/" + rel, data)
            archive.writestr("manifest.json", json.dumps(manifest, sort_keys=True))
        verify_backup(Path(temporary))
        os.replace(temporary, destination)
        return destination
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _validated_members(archive: zipfile.ZipFile) -> dict[str, dict]:
    names = archive.namelist()
    if len(names) != len(set(names)) or names.count("manifest.json") != 1:
        raise ValueError("backup_duplicate_entries")
    manifest = json.loads(archive.read("manifest.json"))
    if not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA:
        raise ValueError("backup_invalid_manifest")
    files = manifest.get("files")
    if not isinstance(files, dict) or len(files) > MAX_FILES:
        raise ValueError("backup_invalid_file_list")
    for name in files:
        if not isinstance(name, str) or not name:
            raise ValueError("backup_unsafe_path")
        posix = PurePosixPath(name)
        if posix.is_absolute() or ".." in posix.parts or "\\" in name or ":" in name or name.startswith("."):
            raise ValueError("backup_unsafe_path")
        for part in posix.parts:
            stem = part.split(".", 1)[0].upper()
            if (part in {"", "."} or part.endswith((" ", "."))
                    or re.fullmatch(r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])", stem)
                    or any(ord(char) < 32 for char in part)):
                raise ValueError("backup_unsafe_path")
    if set(names) != {"manifest.json"} | {"data/" + key for key in files}:
        raise ValueError("backup_unexpected_entries")
    total = 0
    for name, entry in files.items():
        if not isinstance(entry, dict) or type(entry.get("size")) is not int or entry["size"] < 0:
            raise ValueError("backup_invalid_size")
        if not isinstance(entry.get("sha256"), str) or len(entry["sha256"]) != 64:
            raise ValueError("backup_invalid_hash")
        info = archive.getinfo("data/" + name)
        if info.file_size != entry["size"] or info.is_dir():
            raise ValueError("backup_size_mismatch")
        if (info.external_attr >> 16) & 0o170000 == 0o120000:
            raise ValueError("backup_symlink_not_allowed")
        total += info.file_size
        if total > MAX_TOTAL_BYTES:
            raise ValueError("backup_size_limit")
    return files


def verify_backup(backup: Path) -> dict:
    """Verify every file before any restore is allowed."""
    with zipfile.ZipFile(backup) as archive:
        files = _validated_members(archive)
        for name, entry in files.items():
            digest = hashlib.sha256()
            size = 0
            with archive.open("data/" + name) as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    size += len(block)
                    digest.update(block)
            if size != entry["size"] or digest.hexdigest() != entry["sha256"]:
                raise ValueError("backup_integrity_failed")
        return {"files": len(files), "bytes": sum(x["size"] for x in files.values())}


def restore_to_empty_directory(backup: Path, destination: Path) -> dict:
    """Never overwrite user data. Restore only into a new, empty test directory."""
    destination = Path(destination)
    if destination.is_symlink():
        raise ValueError("restore_symlink_destination")
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise FileExistsError("restore_target_not_empty")
    summary = verify_backup(backup)
    with zipfile.ZipFile(backup) as archive:
        files = _validated_members(archive)
        destination.mkdir(parents=True, exist_ok=True)
        for name in files:
            target = destination.joinpath(*PurePosixPath(name).parts)
            if not target.resolve().is_relative_to(destination.resolve()):
                raise ValueError("backup_unsafe_path")
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open("data/" + name) as source, target.open("xb") as out:
                while block := source.read(1024 * 1024):
                    out.write(block)
    return summary
