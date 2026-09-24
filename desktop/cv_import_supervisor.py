"""One-shot CV import outside the UI thread.

``run_once`` never loops. OOM and timeout return a resource failure and leave
a manual retry to the caller. Cancel terminates the contained process group
so Docling / llama.cpp children do not keep running.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from core.hardware_peak_gate import is_oom_exit
from devops.peak_rss_harness import ContainedProcess, launch_contained

DEFAULT_CV_IMPORT_TIMEOUT_S = 180.0
_ENV_TIMEOUT = "KARRIEREKRAKE_CV_IMPORT_TIMEOUT_S"

Spawn = Callable[[Path, Path], object]


@dataclass(frozen=True)
class ImportAttemptResult:
    ok: bool
    kind: str
    message: str
    parsed: dict | None = None
    attempts: int = 1


def default_import_timeout_s() -> float:
    raw = os.environ.get(_ENV_TIMEOUT)
    if raw is None or raw.strip() == "":
        return DEFAULT_CV_IMPORT_TIMEOUT_S
    return float(raw)


def default_spawn(cv_path: Path, out_path: Path) -> ContainedProcess:
    argv = [
        sys.executable,
        "-m",
        "desktop.cv_import_child",
        "--cv",
        str(cv_path),
        "--out",
        str(out_path),
    ]
    return launch_contained(argv, console=False)


class CvImportSupervisor:
    """Runs a single contained import. Call again only after an explicit retry."""

    def __init__(
        self,
        cv_path: Path,
        *,
        spawn: Spawn | None = None,
        timeout_s: float | None = None,
    ) -> None:
        self.cv_path = Path(cv_path)
        self._spawn = spawn or default_spawn
        self.timeout_s = default_import_timeout_s() if timeout_s is None else float(timeout_s)
        self._cancel = threading.Event()
        self._proc: object | None = None
        self.ran_on_thread: int | None = None

    def request_cancel(self) -> None:
        self._cancel.set()
        proc = self._proc
        if proc is not None:
            terminate = getattr(proc, "terminate", None)
            if callable(terminate):
                try:
                    terminate()
                except OSError:
                    pass

    def run_once(self, progress: Callable[[str], None] | None = None) -> ImportAttemptResult:
        """Parse once. Does not retry OOM, timeout, or model failures."""
        self.ran_on_thread = threading.get_ident()
        if self._cancel.is_set():
            return ImportAttemptResult(False, "cancelled", "cancelled", None, attempts=1)
        if progress:
            progress("parsing")
        fd, name = tempfile.mkstemp(prefix="kk-cv-import-", suffix=".json")
        os.close(fd)
        out_path = Path(name)
        proc = None
        try:
            proc = self._spawn(self.cv_path, out_path)
            self._proc = proc
            if self._cancel.is_set():
                self._stop(proc)
                return ImportAttemptResult(False, "cancelled", "cancelled", None, attempts=1)
            deadline = time.monotonic() + self.timeout_s
            while True:
                if self._cancel.is_set():
                    self._stop(proc)
                    return ImportAttemptResult(False, "cancelled", "cancelled", None, attempts=1)
                code = proc.poll()
                if code is not None:
                    return self._classify(int(code), out_path)
                if time.monotonic() >= deadline:
                    self._stop(proc)
                    return ImportAttemptResult(
                        False,
                        "timeout",
                        "timeout",
                        None,
                        attempts=1,
                    )
                time.sleep(0.02)
        finally:
            closer = getattr(proc, "close", None) if proc is not None else None
            if callable(closer):
                try:
                    closer()
                except OSError:
                    pass
            self._proc = None
            try:
                out_path.unlink(missing_ok=True)
            except OSError:
                pass

    def _stop(self, proc: object) -> None:
        terminate = getattr(proc, "terminate", None)
        if callable(terminate):
            try:
                terminate()
            except OSError:
                pass
        wait = getattr(proc, "wait", None)
        if callable(wait):
            try:
                wait(timeout=2)
            except Exception:
                pass

    def _classify(self, code: int, out_path: Path) -> ImportAttemptResult:
        payload = _read_payload(out_path)
        if code == 0 and payload.get("ok") and isinstance(payload.get("parsed"), dict):
            return ImportAttemptResult(True, "ok", "", payload["parsed"], attempts=1)
        kind = str(payload.get("kind") or "")
        message = str(payload.get("message") or "")
        if kind == "oom" or code == 3 or is_oom_exit(code):
            return ImportAttemptResult(False, "oom", message or "oom", None, attempts=1)
        if kind == "timeout":
            return ImportAttemptResult(False, "timeout", message or "timeout", None, attempts=1)
        if kind == "cancelled":
            return ImportAttemptResult(False, "cancelled", message or "cancelled", None, attempts=1)
        return ImportAttemptResult(
            False,
            kind or "error",
            message or f"exit {code}",
            None,
            attempts=1,
        )


def _read_payload(path: Path) -> dict:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}
