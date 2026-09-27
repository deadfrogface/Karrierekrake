"""Cross-process lock so only one role holds the sole Qwen GGUF in RAM.

CV import runs in a child process; Günther writing runs in the UI process.
They must not both keep a full weight resident at once on 8 GB machines.
"""

from __future__ import annotations

import atexit
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

_LOCK_NAME = "qwen35_4b_gguf.lock"
_holder: tuple[object, str] | None = None  # (fd/file, role)


def _lock_path() -> Path:
    try:
        from guenther.model_manager import default_models_dir

        root = default_models_dir()
    except Exception:  # noqa: BLE001
        root = Path.home() / ".cache" / "karrierekrake-models"
    root.mkdir(parents=True, exist_ok=True)
    return root / _LOCK_NAME


def _release() -> None:
    global _holder
    if _holder is None:
        return
    fh, _role = _holder
    try:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        fh.close()
    except Exception:  # noqa: BLE001
        pass
    _holder = None


atexit.register(_release)


@contextmanager
def hold_production_model(*, role: str, timeout_s: float = 30.0) -> Iterator[None]:
    """Exclusive lock while ``role`` (``cv_import`` | ``writing``) loads the GGUF."""
    global _holder
    path = _lock_path()
    fh = open(path, "a+", encoding="utf-8")  # noqa: SIM115
    deadline = time.monotonic() + max(0.5, timeout_s)
    locked = False
    while time.monotonic() < deadline:
        try:
            if os.name == "nt":
                import msvcrt

                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
            break
        except OSError:
            time.sleep(0.2)
    if not locked:
        fh.close()
        raise TimeoutError(f"model_lock_busy:{role}")
    fh.seek(0)
    fh.truncate()
    fh.write(f"{role} pid={os.getpid()}\n")
    fh.flush()
    _holder = (fh, role)
    try:
        yield
    finally:
        _release()
