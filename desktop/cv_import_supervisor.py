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
# QA only. Unset or 0 in production: the child starts immediately.
_ENV_OBSERVE = "KARRIEREKRAKE_CV_IMPORT_OBSERVE_S"
_OBSERVE_CAP_S = 120.0

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


def qa_observe_seconds() -> float:
    """Seconds to hold before spawning the import child.

    ``KARRIEREKRAKE_CV_IMPORT_OBSERVE_S`` is off unless a test explicitly sets
    a positive number. Empty, invalid, and negative values stay at 0.
    """
    raw = os.environ.get(_ENV_OBSERVE)
    if raw is None or raw.strip() == "":
        return 0.0
    try:
        value = float(raw.strip())
    except ValueError:
        return 0.0
    if value <= 0:
        return 0.0
    return min(value, _OBSERVE_CAP_S)


def cv_import_child_argv(cv_path: Path, out_path: Path) -> list[str]:
    """Build argv for the contained CV-import worker.

    Dev (unfrozen): ``python -m desktop.cv_import_child …``.
    Packaged Windows EXE: ``Karrierekrake.exe --cv-import-child …`` — the EXE
    entrypoint must recognize that flag before the GUI / instance lock.
    """
    cv = str(cv_path)
    out = str(out_path)
    if getattr(sys, "frozen", False):
        return [
            str(Path(sys.executable).resolve()),
            "--cv-import-child",
            "--cv",
            cv,
            "--out",
            out,
        ]
    return [
        sys.executable,
        "-m",
        "desktop.cv_import_child",
        "--cv",
        cv,
        "--out",
        out,
    ]


def default_spawn(cv_path: Path, out_path: Path) -> ContainedProcess:
    return launch_contained(cv_import_child_argv(cv_path, out_path), console=False)


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
        if self._wait_qa_observe(progress):
            return ImportAttemptResult(False, "cancelled", "cancelled", None, attempts=1)
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

    def _wait_qa_observe(self, progress: Callable[[str], None] | None) -> bool:
        """Hold on the worker thread so the progress bar can paint. True if cancelled."""
        seconds = qa_observe_seconds()
        if seconds <= 0:
            return self._cancel.is_set()
        deadline = time.monotonic() + seconds
        next_pulse = 0.0
        while time.monotonic() < deadline:
            if self._cancel.is_set():
                return True
            now = time.monotonic()
            if progress is not None and now >= next_pulse:
                progress("parsing")
                next_pulse = now + 0.2
            time.sleep(0.05)
        return self._cancel.is_set()

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
