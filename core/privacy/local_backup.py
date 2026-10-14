"""Offline, user-initiated backups with integrity checks and safe test restores.

The caller chooses both the source data directory and destination archive.
No network access, no credentials collection, no automatic overwrite.
"""
from __future__ import annotations

from contextlib import ExitStack
import hashlib
import json
import os
import re
import shutil
import sqlite3
from pathlib import Path, PurePosixPath
import tempfile
import time
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
        if path.name.endswith(("-wal", "-shm", "-journal")):
            database = path.with_name(path.name.rsplit("-", 1)[0])
            if database.is_file():
                with database.open("rb") as header:
                    if header.read(16) == b"SQLite format 3\x00":
                        continue
        total += path.stat().st_size
        files.append((path, rel))
        if len(files) > MAX_FILES or total > MAX_TOTAL_BYTES:
            raise ValueError("backup_size_limit")
    fd, temporary = tempfile.mkstemp(prefix=".kk-backup-", suffix=".zip", dir=destination.parent)
    os.close(fd)
    try:
        manifest = {"schema": SCHEMA, "files": {}}
        with ExitStack() as cleanup, zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            actual_total = 0
            for path, rel in files:
                digest = hashlib.sha256()
                actual_size = 0
                # SQLite backup API includes committed WAL records and avoids
                # inconsistent copies when the desktop has an open connection.
                snapshot = None
                with path.open("rb") as header:
                    is_sqlite = header.read(16) == b"SQLite format 3\x00"
                if is_sqlite:
                    snapshot = tempfile.TemporaryDirectory(prefix="kk-db-snapshot-")
                    cleanup.callback(snapshot.cleanup)
                    snapshot_path = Path(snapshot.name) / "database.sqlite3"
                    try:
                        original = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=10)
                        copied = sqlite3.connect(snapshot_path)
                        try:
                            deadline = time.monotonic() + 60
                            def check_snapshot(status, remaining, total):
                                if time.monotonic() > deadline:
                                    raise TimeoutError("backup_database_busy")
                            original.backup(copied, pages=256, progress=check_snapshot)
                        finally:
                            copied.close()
                            original.close()
                    except Exception:
                        snapshot.cleanup()
                        raise
                try:
                    src = (snapshot_path if is_sqlite else path).open("rb")
                except Exception:
                    if snapshot:
                        snapshot.cleanup()
                    raise
                with src, archive.open("data/" + rel, "w") as dst:
                    while block := src.read(1024 * 1024):
                        actual_size += len(block)
                        actual_total += len(block)
                        if actual_total > MAX_TOTAL_BYTES:
                            raise ValueError("backup_size_limit")
                        digest.update(block)
                        dst.write(block)
                if snapshot:
                    snapshot.cleanup()
                manifest["files"][rel] = {"size": actual_size, "sha256": digest.hexdigest()}
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
    manifest_info = archive.getinfo("manifest.json")
    if manifest_info.file_size > 4 * 1024 * 1024:
        raise ValueError("backup_manifest_too_large")
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
        if not isinstance(entry.get("sha256"), str) or not re.fullmatch(r"[0-9a-fA-F]{64}", entry["sha256"]):
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
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Extract and hash the same open archive into a private sibling directory.
    # Interrupted/invalid restores never leave partly restored user data.
    stage = Path(tempfile.mkdtemp(prefix=".kk-restore-", dir=destination.parent))
    try:
        with zipfile.ZipFile(backup) as archive:
            files = _validated_members(archive)
            for name, entry in files.items():
                target = stage.joinpath(*PurePosixPath(name).parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                digest = hashlib.sha256()
                size = 0
                with archive.open("data/" + name) as src, target.open("xb") as out:
                    while block := src.read(1024 * 1024):
                        size += len(block)
                        if size > entry["size"]:
                            raise ValueError("backup_size_mismatch")
                        digest.update(block)
                        out.write(block)
                if size != entry["size"] or digest.hexdigest() != entry["sha256"]:
                    raise ValueError("backup_integrity_failed")
        if destination.is_symlink():
            raise ValueError("restore_symlink_destination")
        if destination.exists():
            destination.rmdir()  # Fails if another process added files.
        stage.rename(destination)
        return {"files": len(files), "bytes": sum(x["size"] for x in files.values())}
    finally:
        if stage.exists():
            shutil.rmtree(stage)
