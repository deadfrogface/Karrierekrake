"""One-shot CV import outside the UI thread.

``run_once`` never loops. OOM and timeout return a resource failure and leave
a manual retry to the caller. Cancel terminates the contained process group
so Docling / llama.cpp children do not keep running.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

from core.hardware_peak_gate import is_oom_exit
from devops.peak_rss_harness import ContainedProcess, launch_contained

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
    reason: str | None = None


def default_import_timeout_s() -> float:
    """Outer process deadline before the child reports its formula timeout.

    Uses the same env helper as the child's resolver. Otherwise the ceiling
    (900 s) is the backstop until the child's one ``timeout_s`` event.
    """
    from core.cv_docpick_import import (
        CV_IMPORT_TIMEOUT_CEILING_S,
        env_import_timeout_override,
    )

    override = env_import_timeout_override()
    if override is None:
        return float(CV_IMPORT_TIMEOUT_CEILING_S)
    return float(override)


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


# Linux parent reads the child's anonymous RSS this often. Each read walks
# the child's page tables (smaps_rollup). Parent reads of a headless DE_01
# child on this VM (not the i3), 15 times: median 0.0144 s, max 0.0267 s.
# That is 0.72% of one core at 2 s, so the interval stays 2 s. It becomes
# 5 s when the median of at least three reads, or the sum of the reads over
# the wall clock, exceeds 1% of one core. The median and the max are logged
# once per import. Windows reads PeakJobMemoryUsed inside the child, so
# this read does not run there. A spike that rises and falls between samples
# is invisible: the kernel does not expose an Rss_Anon high-water, and
# VmHWM counts mmap.
_PARENT_ANON_SAMPLE_S = 2.0
_PARENT_ANON_SAMPLE_SLOW_S = 5.0
# Deadline and stall are rechecked after each wake, so the wait stays
# at most this long. Cancel wakes the same wait immediately.
_POLL_SLICE_S = 0.25
_MAX_TOKENS_IN_DIAG = re.compile(r"\bmax_tokens=(\d+)\b")
_N_PROMPT_IN_DIAG = re.compile(r"\bn_prompt=(\d+)\b")
_THREAD_FIELD_IN_DIAG = re.compile(
    r"\b(n_threads|n_threads_batch|physical|logical|reserve)=(\d+)\b"
)
_SOURCE_IN_DIAG = re.compile(r"\bsource=(rule|env)\b")
_THINK_IN_DIAG = re.compile(r"\bthink_tokens=(\d+)\b")


def _monotonic() -> float:
    return time.monotonic()


def _job_limit_from_environ() -> int | None:
    """Job limit from the child budget the supervisor just published, or None.

    The limit equals that budget (the same byte count as the in-process gate).
    None leaves ``JOB_OBJECT_LIMIT_JOB_MEMORY`` unset.
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
    limit is that budget: ``3_300_000_000`` minus the one app-private read.
    The in-process gate uses the same number and, in the normal case,
    raises the clean code first. Without a published budget the job does
    not set ``JOB_OBJECT_LIMIT_JOB_MEMORY``. Cancel still uses
    ``TerminateJobObject`` / ``killpg``.
    """
    return launch_contained(
        cv_import_child_argv(cv_path, out_path),
        console=False,
        enforce_memory_bytes=_job_limit_from_environ(),
        discard_stderr=True,
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
        from core.cv_docpick_import import env_import_timeout_override

        self._publish_timeout = timeout_s is not None or env_import_timeout_override() is not None
        self.timeout_s = default_import_timeout_s() if timeout_s is None else float(timeout_s)
        self._cancel = threading.Event()
        self._proc: object | None = None
        self.ran_on_thread: int | None = None

    def _pause(self, timeout: float) -> None:
        """Wait until cancel or ``timeout`` seconds.

        ``self._cancel.wait`` wakes as soon as ``request_cancel`` sets the
        event. ``timeout`` is at most 0.25 s, so the deadline and the stall
        check run on that grid. The QA observe hold calls the same wait and
        stays off unless ``KARRIEREKRAKE_CV_IMPORT_OBSERVE_S`` is set.
        """
        self._cancel.wait(timeout)

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
        It is still not retried automatically. The dialog shows the existing
        timeout sentence and the retry button.
        ``llm_prompt_too_long`` and ``llm_output_truncated`` are input-conditioned.
        ``peak_rss_exceeded`` is input-conditioned (the child does not fit the
        fresh-app budget). ``memory_budget_app_share`` is the app's share of
        the group cap. Neither is retried automatically.
        """
        self.ran_on_thread = threading.get_ident()
        # Release Günther's in-process weight before the import child loads the
        # same sole GGUF (parser and writing stay separate processes/roles).
        # Never construct Guenther just to unload — llama_cpp import can AV on
        # Windows when probed from a QThread (see CI shard-1 peak gate).
        try:
            from guenther.service import unload_guenther_if_loaded

            unload_guenther_if_loaded()
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
        rates = CvLlmRates()
        anon_interval = _PARENT_ANON_SAMPLE_S
        anon_durations: list[float] = []
        anon_logged = False
        try:
            proc = _spawn_with_child_budget(
                self._spawn,
                self.cv_path,
                out_path,
                app_private=app_private,
                child_budget=child_budget,
                timeout_s=self.timeout_s,
                phase_events=phase_path,
                publish_timeout=self._publish_timeout,
            )
            self._proc = proc
            self._child_budget = child_budget
            self._child_started_mono = time.monotonic()
            if self._cancel.is_set():
                self._stop(proc, reason="cancelled")
                return ImportAttemptResult(False, "cancelled", "cancelled", None, attempts=1)
            from core.cv_docpick_import import (
                CV_IMPORT_TIMEOUT_BUFFER_S,
                CV_IMPORT_TIMEOUT_CEILING_S,
            )
            from core.cv_import_deadline import ImportDeadlineWatch

            started = _monotonic()
            # The env var, and an explicit timeout published as that var,
            # stay put. Otherwise the ceiling holds until the child reports
            # the formula. The prompt block and generation may each raise it
            # once. ``timeout_s_final`` follows only the generation step.
            watch = ImportDeadlineWatch(
                initial_s=self.timeout_s,
                started_at=started,
                env_locked=self._publish_timeout,
                buffer_s=CV_IMPORT_TIMEOUT_BUFFER_S,
                ceiling_s=CV_IMPORT_TIMEOUT_CEILING_S,
            )
            next_anon = started
            phase_offset = 0
            while True:
                if self._cancel.is_set():
                    # Events already in the file still count toward cv_llm_rates.
                    _drain_phase_events(
                        phase_path, phase_offset, progress, watch, rates
                    )
                    self._stop(proc, reason="cancelled")
                    return ImportAttemptResult(False, "cancelled", "cancelled", None, attempts=1)
                # Every complete line in this pass, not one event per wait.
                # A single-event read would let the child's event pipe fill.
                phase_offset = _drain_phase_events(
                    phase_path, phase_offset, progress, watch, rates
                )
                self.timeout_s = watch.limit_s
                if _job_memory_limit_signaled(proc):
                    self._stop(proc)
                    _drain_phase_events(
                        phase_path, phase_offset, progress, watch, rates
                    )
                    code = proc.poll()
                    return self._classify(
                        int(code if code is not None else 1),
                        out_path,
                        job_memory_limit=True,
                    )
                code = proc.poll()
                if code is not None:
                    _drain_phase_events(
                        phase_path, phase_offset, progress, watch, rates
                    )
                    return self._classify(
                        int(code),
                        out_path,
                        job_memory_limit=_job_memory_limit_signaled(proc),
                    )
                now = _monotonic()
                if now >= next_anon:
                    memory_code = _parent_memory_code(
                        proc,
                        child_budget=child_budget,
                        durations=anon_durations,
                    )
                    elapsed = max(0.0, now - started)
                    anon_interval = _anon_interval_s(
                        anon_durations, elapsed_s=elapsed, current_s=anon_interval
                    )
                    next_anon = now + anon_interval
                    if not anon_logged and len(anon_durations) >= 3:
                        _log_smaps_rollup_once(anon_durations, anon_interval)
                        anon_logged = True
                    if memory_code:
                        self._stop(proc)
                        return ImportAttemptResult(
                            False,
                            memory_code,
                            memory_code,
                            None,
                            attempts=1,
                        )
                # Events written during poll or the smaps read belong to this
                # pass. Stall uses the last of them, not the first.
                phase_offset = _drain_phase_events(
                    phase_path, phase_offset, progress, watch, rates
                )
                reason = watch.failure(_monotonic())
                if reason is not None:
                    self._stop(proc)
                    # Machine-dependent. Not deterministic. No automatic retry.
                    # The UI message stays ``llm_timeout`` so no new sentence appears.
                    self.timeout_s = watch.limit_s
                    timeout_line = "llm_timeout reason=%s limit_s=%.3f" % (
                        reason,
                        watch.limit_s,
                    )
                    logger.error("%s", timeout_line)
                    logging.getLogger("karrierekrake").error("%s", timeout_line)
                    return ImportAttemptResult(
                        False,
                        "llm_timeout",
                        "llm_timeout",
                        None,
                        attempts=1,
                        reason=reason,
                    )
                rest_anon = max(0.0, next_anon - _monotonic())
                self._pause(min(_POLL_SLICE_S, rest_anon))
        finally:
            if proc is not None:
                _emit_cv_llm_rates(rates)
            if not anon_logged and anon_durations:
                _log_smaps_rollup_once(anon_durations, anon_interval)
                anon_logged = True
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
                # UI pulses stay at half a second. No timer under 250 ms.
                next_pulse = now + 0.5
            rest = max(0.0, deadline - time.monotonic())
            until_pulse = max(0.0, next_pulse - time.monotonic()) if progress is not None else rest
            # QA only (KARRIEREKRAKE_CV_IMPORT_OBSERVE_S). Off in production.
            # Same wake as the import loop: cancel returns immediately.
            self._cancel.wait(min(_POLL_SLICE_S, rest, until_pulse))
        return self._cancel.is_set()

    def _stop(self, proc: object, *, reason: str = "") -> None:
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
        if reason == "cancelled":
            started = getattr(self, "_child_started_mono", None)
            elapsed_ms = 0
            if isinstance(started, float):
                elapsed_ms = int(round((time.monotonic() - started) * 1000))
            stamp = datetime.now().astimezone().isoformat(timespec="seconds")
            logging.getLogger("karrierekrake").info(
                "cv_import cancelled at=%s child_ended_ms=%s",
                stamp,
                elapsed_ms,
            )

    def _classify(
        self,
        code: int,
        out_path: Path,
        *,
        job_memory_limit: bool = False,
    ) -> ImportAttemptResult:
        payload = _read_payload(out_path)
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
        if code == 0 and payload.get("ok") and isinstance(payload.get("parsed"), dict):
            return ImportAttemptResult(True, "ok", "", payload["parsed"], attempts=1)
        from core.cv_docpick_import import (
            is_job_limit_crash_exit,
            memory_kind_for_job_limit,
        )

        child_budget = int(getattr(self, "_child_budget", 0))
        if job_memory_limit or is_job_limit_crash_exit(code):
            if not job_memory_limit:
                logger.error(
                    "job_memory_limit_hit exit=%s child_budget=%s",
                    code,
                    child_budget,
                )
            limit_kind = memory_kind_for_job_limit(child_budget=child_budget)
            logger.error(
                "%s job_memory_limit=%s exit=%s child_budget=%s",
                limit_kind,
                job_memory_limit,
                code,
                child_budget,
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
    """Non-blocking drain of the job completion port. No extra wait loop."""
    probe = getattr(proc, "job_memory_limit_signaled", None)
    if not callable(probe):
        return False
    try:
        return bool(probe())
    except OSError:
        return False


class CvLlmRates:
    """What the parent has seen, for one ``cv_llm_rates`` line at the end.

    Prompt tokens prefer the blocks already reported. The diagnostic
    ``n_prompt`` fills in only when no block has arrived. Prompt duration is
    the sum of ``block_s``. Generation duration is the span from the first
    generated token's ``t_mono`` to the last. Rates are counts divided by
    those durations. A cancel or a timeout keeps the partial figures.
    """

    def __init__(self) -> None:
        self.n_threads: int | None = None
        self.n_threads_batch: int | None = None
        self.physical: int | None = None
        self.logical: int | None = None
        self.reserve: int | None = None
        self.source: str | None = None
        self._event_prompt = 0
        self._diag_prompt: int | None = None
        self.prompt_s = 0.0
        self._saw_block = False
        self.n_gen = 0
        self.think_tokens: int | None = None
        self.gen_first: float | None = None
        self.gen_last: float | None = None

    def note_diag(self, diag: str) -> None:
        for match in _THREAD_FIELD_IN_DIAG.finditer(diag):
            name, raw = match.group(1), int(match.group(2))
            if name == "n_threads":
                self.n_threads = raw
            elif name == "n_threads_batch":
                self.n_threads_batch = raw
            elif name == "physical":
                self.physical = raw
            elif name == "logical":
                self.logical = raw
            elif name == "reserve":
                self.reserve = raw
        source = _SOURCE_IN_DIAG.search(diag)
        if source is not None:
            self.source = source.group(1)
        prompt = _N_PROMPT_IN_DIAG.search(diag)
        if prompt is not None and self._diag_prompt is None:
            self._diag_prompt = int(prompt.group(1))
        think = _THINK_IN_DIAG.search(diag)
        if think is not None:
            self.think_tokens = int(think.group(1))

    def note_phase(self, event: dict) -> None:
        if "prompt_tokens_done" in event:
            try:
                count = int(event["prompt_tokens_done"])
            except (TypeError, ValueError):
                count = 0
            if count > self._event_prompt:
                self._event_prompt = count
                block = event.get("block_s")
                try:
                    block_s = float(block) if block is not None else 0.0
                except (TypeError, ValueError):
                    block_s = 0.0
                if block_s > 0:
                    self.prompt_s += block_s
                    self._saw_block = True
        if "tokens_done" not in event:
            return
        try:
            count = int(event["tokens_done"])
        except (TypeError, ValueError):
            return
        if count <= self.n_gen:
            return
        self.n_gen = count
        raw = event.get("t_mono")
        if raw is None:
            return
        try:
            stamp = float(raw)
        except (TypeError, ValueError):
            return
        if self.gen_first is None:
            self.gen_first = stamp
        self.gen_last = stamp

    @property
    def n_prompt(self) -> int | None:
        if self._event_prompt > 0:
            return self._event_prompt
        return self._diag_prompt

    @property
    def prompt_duration_s(self) -> float | None:
        if not self._saw_block:
            return None
        return self.prompt_s

    @property
    def gen_duration_s(self) -> float | None:
        if (
            self.gen_first is None
            or self.gen_last is None
            or self.gen_last <= self.gen_first
        ):
            return None
        return self.gen_last - self.gen_first

    def line(self) -> str:
        source = self.source
        if source not in {"rule", "env"}:
            from core.cv_llm_runtime import cv_llm_thread_source

            source = cv_llm_thread_source()
        prompt_s = self.prompt_duration_s
        gen_s = self.gen_duration_s
        n_prompt = self.n_prompt
        prompt_tps = None
        if n_prompt and prompt_s and prompt_s > 0:
            prompt_tps = n_prompt / prompt_s
        gen_tps = None
        if self.n_gen > 0 and gen_s and gen_s > 0:
            gen_tps = self.n_gen / gen_s
        return (
            "cv_llm_rates n_threads=%s n_threads_batch=%s physical=%s "
            "logical=%s reserve=%s source=%s n_prompt=%s prompt_s=%s "
            "n_gen=%s gen_s=%s prompt_tps=%s gen_tps=%s think_tokens=%s"
            % (
                _fmt_int(self.n_threads),
                _fmt_int(self.n_threads_batch),
                _fmt_int(self.physical),
                _fmt_int(self.logical),
                _fmt_int(self.reserve),
                source,
                _fmt_int(n_prompt),
                _fmt_seconds(prompt_s),
                str(self.n_gen),
                _fmt_seconds(gen_s),
                _fmt_rate(prompt_tps),
                _fmt_rate(gen_tps),
                _fmt_int(self.think_tokens),
            )
        )


def _fmt_int(value: int | None) -> str:
    if value is None:
        return "na"
    return str(int(value))


def _fmt_seconds(value: float | None) -> str:
    if value is None:
        return "na"
    return "%.3f" % float(value)


def _fmt_rate(value: float | None) -> str:
    if value is None:
        return "na"
    return "%.3f" % float(value)


def _emit_cv_llm_rates(rates: CvLlmRates) -> None:
    """One app-log line. Also after cancel and timeout, with partial figures."""
    line = rates.line()
    logger.info("%s", line)
    logging.getLogger("karrierekrake").info("%s", line)


def _drain_phase_events(
    path: Path,
    offset: int,
    progress: Callable[[str], None] | None,
    watch: object | None = None,
    rates: CvLlmRates | None = None,
) -> int:
    """Forward every complete JSON line currently in the file.

    One call consumes the whole pending tail, not a single event. Diagnostic
    lines stay in the app log. ``max_tokens`` and ``n_prompt`` are read from
    the child diagnostic and are not UI fields. The first ``timeout_s`` is
    the initial deadline. ``timeout_s_final`` is one event after the
    generation recalculation, with no new sentence.
    """
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
    from core.cv_phase_events import relay_diag_event

    for line in complete.decode("utf-8").splitlines():
        if not line.strip():
            continue
        event = None
        if line.startswith("{"):
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                event = None
        if isinstance(event, dict) and relay_diag_event(event):
            diag = str(event.get("diag") or "")
            _note_diag_budget(watch, diag)
            if rates is not None:
                rates.note_diag(diag)
            continue
        if isinstance(event, dict):
            _note_phase_budget(watch, event, progress)
            if rates is not None:
                rates.note_phase(event)
        if progress is not None:
            progress(line)
    return offset + newline + 1


def _event_float(event: dict, key: str) -> float | None:
    if key not in event:
        return None
    try:
        return float(event[key])
    except (TypeError, ValueError):
        return None


def _note_diag_budget(watch: object | None, diag: str) -> None:
    if watch is None:
        return
    match = _MAX_TOKENS_IN_DIAG.search(diag)
    if match is not None:
        note = getattr(watch, "note_max_tokens", None)
        if callable(note):
            note(int(match.group(1)))
    prompt = _N_PROMPT_IN_DIAG.search(diag)
    if prompt is not None:
        note_prompt = getattr(watch, "note_n_prompt", None)
        if callable(note_prompt):
            note_prompt(int(prompt.group(1)))


def _note_phase_budget(
    watch: object | None,
    event: dict,
    progress: Callable[[str], None] | None,
) -> None:
    if watch is None:
        return
    if "timeout_s" in event:
        adopt = getattr(watch, "adopt_initial", None)
        if callable(adopt):
            try:
                adopt(float(event["timeout_s"]))
            except (TypeError, ValueError):
                pass
    if "prompt_tokens_done" in event:
        note_prompt = getattr(watch, "note_prompt", None)
        if callable(note_prompt):
            try:
                count = int(event["prompt_tokens_done"])
            except (TypeError, ValueError):
                count = 0
            if count > 0:
                note_prompt(
                    count,
                    _monotonic(),
                    _event_float(event, "t_mono"),
                    _event_float(event, "block_s"),
                )
    if "tokens_done" not in event:
        return
    note = getattr(watch, "note_tokens", None)
    if not callable(note):
        return
    try:
        count = int(event["tokens_done"])
    except (TypeError, ValueError):
        return
    final = note(count, _monotonic(), _event_float(event, "t_mono"))
    if final is None or progress is None:
        return
    progress(json.dumps({"timeout_s_final": int(final)}, separators=(",", ":")))


def _spawn_with_child_budget(
    spawn: Callable[..., object],
    cv_path: Path,
    out_path: Path,
    *,
    app_private: int,
    child_budget: int,
    timeout_s: float,
    phase_events: Path,
    publish_timeout: bool,
) -> object:
    """Publish the one-shot budget in the environment the child inherits.

    The values are removed from this process after ``Popen`` copies them.
    The app is not sampled again. ``timeout_s`` is published only when the
    caller or the env var already chose it. Otherwise the child runs the
    formula once after tokenization.
    """
    keys = {
        "KARRIEREKRAKE_CV_APP_PRIVATE_BYTES": str(app_private),
        "KARRIEREKRAKE_CV_CHILD_BUDGET_BYTES": str(child_budget),
        "KARRIEREKRAKE_CV_PHASE_EVENTS": str(phase_events),
    }
    if publish_timeout:
        keys["KARRIEREKRAKE_CV_IMPORT_TIMEOUT_S"] = str(timeout_s)
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
    from core.cv_docpick_import import app_private_commit_bytes

    return int(app_private_commit_bytes())


def _anon_interval_s(
    durations: list[float], *, elapsed_s: float, current_s: float
) -> float:
    """2 s until the reads exceed 1% of one core, then 5 s.

    The decision uses the median once three reads exist, so one slow read
    does not move the interval. It also uses the sum of the read times over
    the wall clock once that window covers at least three intervals.
    Windows does not call this.
    """
    if len(durations) < 3 or current_s <= 0:
        return current_s
    import statistics

    if statistics.median(durations) / current_s > 0.01:
        return _PARENT_ANON_SAMPLE_SLOW_S
    if elapsed_s >= 3 * current_s and sum(durations) / elapsed_s > 0.01:
        return _PARENT_ANON_SAMPLE_SLOW_S
    return current_s


def _log_smaps_rollup_once(durations: list[float], interval_s: float) -> None:
    """One line: median and max of the Linux ``smaps_rollup`` reads."""
    import statistics

    line = (
        "cv_import smaps_rollup reads=%s median_s=%.6f max_s=%.6f interval_s=%.1f"
        % (len(durations), statistics.median(durations), max(durations), interval_s)
    )
    logger.info("%s", line)
    logging.getLogger("karrierekrake").info("%s", line)


def _parent_memory_code(
    proc: object,
    *,
    child_budget: int,
    durations: list[float] | None = None,
) -> str | None:
    """Error code when a measurable child sample is over its budget.

    An unmeasured sample (0/None) is logged inside ``_parent_anon_sample``
    and does not by itself kill the child: the in-process gate fails closed
    on its own 0/None read. The app's private commit is not read here.
    """
    sample = _parent_anon_sample(proc, durations=durations)
    if sample is None:
        return None
    from core.cv_docpick_import import (
        classify_child_private_commit,
        fresh_app_child_budget_bytes,
    )

    fresh_budget = fresh_app_child_budget_bytes()
    logger.info(
        "cv_import memory_shares role=parent child_bytes=%s child_budget=%s fresh_child_budget=%s",
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


def _parent_anon_sample(
    proc: object, *, durations: list[float] | None = None
) -> int | None:
    """Anonymous RSS of the extract child, or None when it is not measurable.

    Linux only. ``0`` / missing ``/proc`` is unmeasured and is not a pass.
    When ``durations`` is set, the ``smaps_rollup`` read time is appended.
    Windows returns before any read: the child gate uses ``PeakJobMemoryUsed``.
    """
    if sys.platform == "win32":
        return None
    pid = getattr(proc, "pid", None)
    if not isinstance(pid, int) or pid <= 0:
        return None
    from core.cv_docpick_import import _linux_rss_anon_bytes

    started = time.perf_counter()
    value = _linux_rss_anon_bytes(pid)
    if durations is not None:
        durations.append(time.perf_counter() - started)
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
