"""One-shot CV import outside the UI thread.

``run_once`` never loops. OOM and timeout return a resource failure and leave
a manual retry to the caller. Cancel terminates the contained process group
so Docling / llama.cpp children do not keep running.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

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


# Linux parent reads the child's anonymous RSS this often. One smaps_rollup
# read with the GGUF mmap'd was 35 µs on this VM (0.0017% of one core at 2 s).
# Windows PeakPagefileUsage is already a lifetime peak, so the interval is
# Linux-only. A spike that rises and falls between samples is invisible:
# the kernel does not expose an Rss_Anon high-water, and VmHWM counts mmap.
_PARENT_ANON_SAMPLE_S = 2.0


def _job_limit_from_environ() -> int | None:
    """Job limit from the budget the supervisor just published, or None.

    None leaves ``JOB_OBJECT_LIMIT_JOB_MEMORY`` unset. A published budget
    sets the limit one margin above the child budget.
    """
    raw_budget = os.environ.get("KARRIEREKRAKE_CV_CHILD_BUDGET_BYTES", "").strip()
    raw_app = os.environ.get("KARRIEREKRAKE_CV_APP_PRIVATE_BYTES", "").strip()
    if not raw_budget or not raw_app:
        return None
    try:
        child_budget = int(raw_budget)
        app_private = int(raw_app)
    except ValueError:
        return None
    if child_budget <= 0:
        return None
    from core.cv_docpick_import import job_enforce_memory_bytes

    limit = job_enforce_memory_bytes(child_budget=child_budget, app_private=app_private)
    if limit <= 0:
        return None
    return limit


def default_spawn(cv_path: Path, out_path: Path) -> ContainedProcess:
    """Start the extract child inside a job (Windows) or a process group.

    When the supervisor has published the child budget, the Windows job
    limit is that budget plus ``JOB_LIMIT_MARGIN_BYTES``. The in-process
    gate compares against the child budget, which is lower, and trips
    first. Without a published budget the job does not set
    ``JOB_OBJECT_LIMIT_JOB_MEMORY``. Cancel still uses
    ``TerminateJobObject`` / ``killpg``.
    """
    return launch_contained(
        cv_import_child_argv(cv_path, out_path),
        console=False,
        enforce_memory_bytes=_job_limit_from_environ(),
    )


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
        """Parse once. Does not retry OOM, timeout, or model failures.

        ``llm_timeout`` depends on the machine and is not deterministic.
        It is still not retried automatically. A manual retry is the UI PR.
        ``llm_prompt_too_long`` and ``llm_output_truncated`` are input-conditioned.
        ``peak_rss_exceeded`` is input-conditioned (the child does not fit the
        fresh-app budget). ``memory_budget_app_share`` is the app's share of
        the group cap. Neither is retried automatically.
        """
        self.ran_on_thread = threading.get_ident()
        # Release Günther's in-process weight before the import child loads the
        # same sole GGUF (parser and writing stay separate processes/roles).
        try:
            from guenther.service import get_guenther_service

            g = get_guenther_service(enabled=True)
            if g is not None and hasattr(g, "provider"):
                g.provider.unload_model()
        except Exception:  # noqa: BLE001
            pass
        if self._cancel.is_set():
            return ImportAttemptResult(False, "cancelled", "cancelled", None, attempts=1)
        if progress:
            progress("parsing")
        if self._wait_qa_observe(progress):
            return ImportAttemptResult(False, "cancelled", "cancelled", None, attempts=1)
        # One app read. The child budget is the group cap minus this value.
        # The app is not polled again while the child runs.
        app_private = _read_app_private_bytes()
        if app_private <= 0:
            logger.error(
                "cv_import app private unmeasured value=%s; not a pass",
                app_private,
            )
            return ImportAttemptResult(
                False, "peak_rss_unmeasured", "peak_rss_unmeasured", None, attempts=1
            )
        from core.cv_docpick_import import (
            CV_IMPORT_CHILD_MIN_AFTER_LOAD_BYTES,
            child_start_allowed,
            fresh_app_child_budget_bytes,
        )

        allowed, child_budget = child_start_allowed(app_private)
        fresh_budget = fresh_app_child_budget_bytes()
        logger.info(
            "cv_import memory_shares app_private=%s child_budget=%s "
            "fresh_child_budget=%s child_min_after_load=%s",
            app_private,
            child_budget,
            fresh_budget,
            CV_IMPORT_CHILD_MIN_AFTER_LOAD_BYTES,
        )
        if not allowed:
            logger.error(
                "memory_budget_app_share app_private=%s child_budget=%s "
                "child_min_after_load=%s",
                app_private,
                child_budget,
                CV_IMPORT_CHILD_MIN_AFTER_LOAD_BYTES,
            )
            return ImportAttemptResult(
                False,
                "memory_budget_app_share",
                "memory_budget_app_share",
                None,
                attempts=1,
            )
        fd, name = tempfile.mkstemp(prefix="kk-cv-import-", suffix=".json")
        os.close(fd)
        out_path = Path(name)
        phase_fd, phase_name = tempfile.mkstemp(prefix="kk-cv-phase-", suffix=".jsonl")
        os.close(phase_fd)
        phase_path = Path(phase_name)
        proc = None
        try:
            proc = _spawn_with_child_budget(
                self._spawn,
                self.cv_path,
                out_path,
                app_private=app_private,
                child_budget=child_budget,
                timeout_s=self.timeout_s,
                phase_events=phase_path,
            )
            self._proc = proc
            self._app_private = app_private
            self._child_budget = child_budget
            if self._cancel.is_set():
                self._stop(proc)
                return ImportAttemptResult(False, "cancelled", "cancelled", None, attempts=1)
            deadline = time.monotonic() + self.timeout_s
            next_anon = time.monotonic()
            phase_offset = 0
            last_sample: int | None = None
            while True:
                if self._cancel.is_set():
                    self._stop(proc)
                    return ImportAttemptResult(False, "cancelled", "cancelled", None, attempts=1)
                phase_offset = _drain_phase_events(phase_path, phase_offset, progress)
                if _job_memory_limit_signaled(proc):
                    self._stop(proc)
                    _drain_phase_events(phase_path, phase_offset, progress)
                    code = proc.poll()
                    return self._classify(
                        int(code if code is not None else 1),
                        out_path,
                        last_sample=last_sample,
                        job_memory_limit=True,
                    )
                code = proc.poll()
                if code is not None:
                    if last_sample is None:
                        from core.cv_docpick_import import is_job_limit_crash_exit

                        if is_job_limit_crash_exit(int(code)):
                            sampled = _parent_anon_sample(proc)
                            if sampled is not None:
                                last_sample = sampled
                    _drain_phase_events(phase_path, phase_offset, progress)
                    return self._classify(
                        int(code),
                        out_path,
                        last_sample=last_sample,
                        job_memory_limit=_job_memory_limit_signaled(proc),
                    )
                now = time.monotonic()
                if now >= next_anon:
                    next_anon = now + _PARENT_ANON_SAMPLE_S
                    sampled = _parent_anon_sample(proc)
                    if sampled is not None:
                        last_sample = sampled
                    memory_code = _parent_memory_code(proc, child_budget=child_budget)
                    if memory_code:
                        self._stop(proc)
                        return ImportAttemptResult(
                            False,
                            memory_code,
                            memory_code,
                            None,
                            attempts=1,
                        )
                if now >= deadline:
                    self._stop(proc)
                    # Machine-dependent. Not deterministic. No automatic retry.
                    logger.error(
                        "llm_timeout wall_clock limit_s=%s",
                        self.timeout_s,
                    )
                    return ImportAttemptResult(
                        False,
                        "llm_timeout",
                        "llm_timeout",
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
            try:
                phase_path.unlink(missing_ok=True)
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

    def _classify(
        self,
        code: int,
        out_path: Path,
        *,
        last_sample: int | None = None,
        job_memory_limit: bool = False,
    ) -> ImportAttemptResult:
        payload = _read_payload(out_path)
        if code == 0 and payload.get("ok") and isinstance(payload.get("parsed"), dict):
            return ImportAttemptResult(True, "ok", "", payload["parsed"], attempts=1)
        kind = str(payload.get("kind") or "")
        message = str(payload.get("message") or "")
        if kind == "memory_budget_app_share":
            return ImportAttemptResult(
                False, "memory_budget_app_share", message or kind, None, attempts=1
            )
        if kind == "peak_rss_exceeded":
            return ImportAttemptResult(
                False, "peak_rss_exceeded", message or kind, None, attempts=1
            )
        from core.cv_docpick_import import memory_kind_for_limit_death

        limit_kind = memory_kind_for_limit_death(
            exit_code=code,
            last_sample=last_sample,
            child_budget=getattr(self, "_child_budget", 0),
            app_private=getattr(self, "_app_private", 0),
            job_memory_limit=job_memory_limit,
        )
        if limit_kind:
            logger.error(
                "%s job_memory_limit=%s exit=%s last_sample=%s child_budget=%s",
                limit_kind,
                job_memory_limit,
                code,
                last_sample,
                getattr(self, "_child_budget", 0),
            )
            return ImportAttemptResult(False, limit_kind, limit_kind, None, attempts=1)
        if kind == "oom" or code == 3 or is_oom_exit(code):
            return ImportAttemptResult(False, "oom" if kind != "peak_rss_exceeded" else "peak_rss_exceeded", message or "oom", None, attempts=1)
        if kind in {"timeout", "llm_timeout"}:
            logger.error("llm_timeout child_kind=%s", kind or "timeout")
            return ImportAttemptResult(False, "llm_timeout", "llm_timeout", None, attempts=1)
        if kind == "cancelled":
            return ImportAttemptResult(False, "cancelled", message or "cancelled", None, attempts=1)
        return ImportAttemptResult(
            False,
            kind or "error",
            message or f"exit {code}",
            None,
            attempts=1,
        )


def _job_memory_limit_signaled(proc: object) -> bool:
    probe = getattr(proc, "job_memory_limit_signaled", None)
    if not callable(probe):
        return False
    try:
        return bool(probe())
    except OSError:
        return False


def _drain_phase_events(path: Path, offset: int, progress: Callable[[str], None] | None) -> int:
    """Forward complete JSON lines from the child to the UI progress callback."""
    try:
        data = path.read_bytes()
    except OSError:
        return offset
    if len(data) <= offset:
        return offset
    chunk = data[offset:]
    newline = chunk.rfind(b"\n")
    if newline < 0:
        return offset
    complete = chunk[: newline + 1]
    if progress is not None:
        for line in complete.decode("utf-8").splitlines():
            if line.strip():
                progress(line)
    return offset + newline + 1


def _spawn_with_child_budget(
    spawn: Callable[..., object],
    cv_path: Path,
    out_path: Path,
    *,
    app_private: int,
    child_budget: int,
    timeout_s: float,
    phase_events: Path,
) -> object:
    """Publish the one-shot budget in the environment the child inherits.

    The values are removed from this process after ``Popen`` copies them.
    The app is not sampled again. ``timeout_s`` is the supervisor's already
    chosen limit, not a second calculation.
    """
    keys = {
        "KARRIEREKRAKE_CV_APP_PRIVATE_BYTES": str(app_private),
        "KARRIEREKRAKE_CV_CHILD_BUDGET_BYTES": str(child_budget),
        "KARRIEREKRAKE_CV_IMPORT_TIMEOUT_S": str(timeout_s),
        "KARRIEREKRAKE_CV_PHASE_EVENTS": str(phase_events),
    }
    previous = {key: os.environ.get(key) for key in keys}
    os.environ.update(keys)
    try:
        return spawn(cv_path, out_path)
    finally:
        for key, old in previous.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old


def _read_app_private_bytes() -> int:
    """One private-commit read of this process (the app). Not a poll loop."""
    from core.cv_docpick_import import _self_rss_bytes

    return int(_self_rss_bytes())


def _parent_memory_code(proc: object, *, child_budget: int) -> str | None:
    """Error code when a measurable child sample is over its budget.

    An unmeasured sample (0/None) is logged inside ``_parent_anon_sample``
    and does not by itself kill the child: the in-process gate fails closed
    on its own 0/None read. The app's private commit is not read here.
    """
    sample = _parent_anon_sample(proc)
    if sample is None:
        return None
    from core.cv_docpick_import import (
        classify_child_private_commit,
        fresh_app_child_budget_bytes,
    )

    fresh_budget = fresh_app_child_budget_bytes()
    logger.info(
        "cv_import memory_shares parent child_bytes=%s child_budget=%s fresh_child_budget=%s",
        sample,
        child_budget,
        fresh_budget,
    )
    code = classify_child_private_commit(sample, child_budget)
    if code is not None:
        logger.error(
            "%s parent child_bytes=%s child_budget=%s fresh_child_budget=%s",
            code,
            sample,
            child_budget,
            fresh_budget,
        )
    return code


def _parent_anon_sample(proc: object) -> int | None:
    """Anonymous RSS of the extract child, or None when it is not measurable.

    Linux only. ``0`` / missing ``/proc`` is unmeasured and is not a pass.
    """
    if sys.platform == "win32":
        return None
    pid = getattr(proc, "pid", None)
    if not isinstance(pid, int) or pid <= 0:
        return None
    from core.cv_docpick_import import _linux_rss_anon_bytes

    value = _linux_rss_anon_bytes(pid)
    if value <= 0:
        logger.error(
            "cv_import parent anon sample unmeasured pid=%s value=%s; not a pass",
            pid,
            value,
        )
        return None
    return value


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
