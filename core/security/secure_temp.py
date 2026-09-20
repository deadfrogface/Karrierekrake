"""Secure temporary files — 0600, best-effort wipe, no secrets in path names."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


def _chmod_private(path: Path) -> None:
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _best_effort_wipe(path: Path) -> None:
    try:
        if path.is_file():
            size = path.stat().st_size
            with path.open("wb") as fh:
                fh.write(b"\x00" * min(size, 1024 * 1024))
                fh.flush()
                os.fsync(fh.fileno())
            path.unlink(missing_ok=True)
    except OSError:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


@contextmanager
def secure_temp_file(
    *,
    suffix: str = ".tmp",
    prefix: str = "kk_",
    text: bool = False,
) -> Iterator[Path]:
    """Create a private temp file; wipe+delete on exit."""
    fd, name = tempfile.mkstemp(prefix=prefix, suffix=suffix)
    path = Path(name)
    try:
        os.close(fd)
        _chmod_private(path)
        yield path
    finally:
        _best_effort_wipe(path)


@contextmanager
def secure_temp_dir(*, prefix: str = "kk_") -> Iterator[Path]:
    """Private temporary directory; recursive wipe of files on exit."""
    path = Path(tempfile.mkdtemp(prefix=prefix))
    try:
        try:
            os.chmod(path, 0o700)
        except OSError:
            pass
        yield path
    finally:
        for child in sorted(path.rglob("*"), reverse=True):
            if child.is_file():
                _best_effort_wipe(child)
            else:
                try:
                    child.rmdir()
                except OSError:
                    pass
        try:
            path.rmdir()
        except OSError:
            pass
