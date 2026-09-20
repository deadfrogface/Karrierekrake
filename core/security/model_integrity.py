"""Atomic, hash-verified model / artifact file helpers."""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path


class ModelIntegrityError(ValueError):
    """Missing or mismatched model checksum."""


def require_sha256(expected: str | None) -> str:
    digest = (expected or "").strip().lower()
    if not digest or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ModelIntegrityError("sha256_required")
    return digest


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def verify_file_sha256(path: Path, expected: str) -> str:
    want = require_sha256(expected)
    got = sha256_file(path)
    if got != want:
        raise ModelIntegrityError(f"checksum_mismatch:{got[:12]}")
    return got


def atomic_write_bytes(
    dest: Path,
    data: bytes,
    *,
    expected_sha256: str,
) -> str:
    """Write bytes via temp file, verify hash, then atomic replace."""
    want = require_sha256(expected_sha256)
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".model_", suffix=".tmp", dir=str(dest.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        got = sha256_file(tmp_path)
        if got != want:
            raise ModelIntegrityError(f"checksum_mismatch:{got[:12]}")
        os.replace(tmp_path, dest)
        return got
    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
