"""Phase events from the CV-import child to the UI.

``timeout_s`` is the integer already chosen for this generation: the formula
result, or ``KARRIEREKRAKE_CV_IMPORT_TIMEOUT_S`` when that variable is set.
This module does not tokenize and does not compute a remaining time.
Generation progress is at most one event per second.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time

PHASE_EVENTS_ENV = "KARRIEREKRAKE_CV_PHASE_EVENTS"
TOKEN_EVENT_INTERVAL_S = 1.0

_timeout_sent = False


def phase_clock() -> float:
    return time.monotonic()


def reset_generation_phase_events() -> None:
    """Allow one timeout event for the next generation in this process."""
    global _timeout_sent
    _timeout_sent = False


def generation_timeout_event(timeout_s: int | None = None) -> dict[str, int | str] | None:
    """One event with the already chosen timeout, or None if already sent.

    Pass the integer from ``choose_import_timeout_s``. Without that argument
    the env override wins, then the value chosen earlier in this process.
    This does not run the formula again.
    """
    global _timeout_sent
    if _timeout_sent:
        return None
    _timeout_sent = True
    if timeout_s is None:
        raw = os.environ.get("KARRIEREKRAKE_CV_IMPORT_TIMEOUT_S", "").strip()
        if raw:
            timeout_s = int(float(raw))
        else:
            from core.cv_docpick_import import current_import_timeout_s

            timeout_s = int(current_import_timeout_s())
    return {"phase": "generation", "timeout_s": int(timeout_s)}


def absorb_phase_message(
    message: str,
    *,
    timeout_s: int | None,
    tokens_done: int | None,
    timeout_s_final: int | None = None,
) -> tuple[int | None, int | None, int | None]:
    """Keep the first ``timeout_s`` and the latest ``tokens_done`` count.

    ``timeout_s_final`` is kept the first time it appears. It does not
    replace ``timeout_s``. Plain stage names are ignored. ``max_tokens``
    is not a UI field. The visible status text stays the existing
    progress sentence. There is no remaining-time calculation.
    """
    if not message.startswith("{"):
        return timeout_s, tokens_done, timeout_s_final
    try:
        event = json.loads(message)
    except json.JSONDecodeError:
        return timeout_s, tokens_done, timeout_s_final
    if not isinstance(event, dict):
        return timeout_s, tokens_done, timeout_s_final
    if "timeout_s" in event and timeout_s is None:
        try:
            timeout_s = int(event["timeout_s"])
        except (TypeError, ValueError):
            pass
    if "timeout_s_final" in event and timeout_s_final is None:
        try:
            timeout_s_final = int(event["timeout_s_final"])
        except (TypeError, ValueError):
            pass
    if "tokens_done" in event:
        try:
            tokens_done = int(event["tokens_done"])
        except (TypeError, ValueError):
            pass
    return timeout_s, tokens_done, timeout_s_final


def emit_diag(message: str, *, level: str = "info") -> None:
    """One diagnostic line for the parent. The child process has no app log."""
    append_phase_event({"diag": message, "level": level})


_SAFE_DIAG = re.compile(
    r"^(cv_llm_rates|cv_llm_config|cv_llm_inprocess|cv_llm_load|cv_llm_think|cv_llm_prompt_prefix|"
    r"cv_llm_prompt_prefill|cv_import memory_shares|cv_import smaps_rollup|"
    r"llm_timeout|llm_prompt_too_long|llm_output_truncated|job_memory_limit_hit|"
    r"memory_budget_app_share|peak_rss_exceeded|peak_rss_unmeasured)"
    r"( [a-z0-9_]+=-?[A-Za-z0-9_.:]+)*$"
)


def diag_line_is_safe(message: str) -> bool:
    """True when a child diagnostic is a fixed line with whitelist values."""
    return _SAFE_DIAG.match(message) is not None


def relay_diag_event(event: dict) -> bool:
    """Write a child diagnostic into the app log. True when ``event`` is one.

    The parent is the only writer of ``karrierekrake.log``. A diag event is
    not a UI progress line. Free text, paths, and model output are dropped.
    """
    if "diag" not in event:
        return False
    message = str(event.get("diag") or "").strip()
    if not message or not diag_line_is_safe(message):
        return True
    level = str(event.get("level") or "info").lower()
    if level not in {"info", "warning", "error"}:
        level = "info"
    log = logging.getLogger("karrierekrake")
    if level == "error":
        log.error("%s", message)
    elif level == "warning":
        log.warning("%s", message)
    else:
        log.info("%s", message)
    return True


def append_phase_event(event: dict) -> None:
    """Append one JSON line. A missing path or a write error does not fail the import."""
    path = os.environ.get(PHASE_EVENTS_ENV, "").strip()
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, separators=(",", ":")) + "\n")
    except OSError:
        return


def emit_generation_timeout(timeout_s: int | None = None) -> dict[str, int | str] | None:
    event = generation_timeout_event(timeout_s)
    if event is not None:
        append_phase_event(event)
    return event


class TokenProgressThrottle:
    """At most one generation-progress event per ``interval_s``.

    A count that arrives inside the window is held and sent when the window
    ends. The sent ``t_mono`` is the child's monotonic delta of the last real
    token in that window, not the flush time.
    """

    def __init__(self, interval_s: float = TOKEN_EVENT_INTERVAL_S) -> None:
        self.interval_s = float(interval_s)
        self._window_at: float | None = None
        self._pending_count: int | None = None
        self._pending_at: float | None = None

    def consider(
        self,
        *,
        tokens_done: int,
        now: float,
        t_mono: float | None = None,
    ) -> dict[str, int | float | str] | None:
        """Emit the first token immediately. Later tokens stay within 1/s."""
        count = int(tokens_done)
        if count <= 0:
            return None
        stamp = float(now if t_mono is None else t_mono)
        if self._window_at is None:
            self._window_at = float(now)
            return self._event(count, stamp)
        due = (float(now) - self._window_at) >= self.interval_s
        if due and self._pending_count is not None:
            event = self._emit_pending(float(now))
            if count > int(event["tokens_done"]):
                self._pending_count = count
                self._pending_at = stamp
            return event
        if self._pending_count is None or count > self._pending_count:
            self._pending_count = count
            self._pending_at = stamp
        return None

    def flush(self, now: float) -> dict[str, int | float | str] | None:
        """Send a held count once the window has elapsed."""
        if self._pending_count is None or self._window_at is None:
            return None
        if (float(now) - self._window_at) < self.interval_s:
            return None
        return self._emit_pending(float(now))

    def _emit_pending(self, now: float) -> dict[str, int | float | str]:
        count = int(self._pending_count or 0)
        stamp = float(self._pending_at if self._pending_at is not None else now)
        self._pending_count = None
        self._pending_at = None
        self._window_at = now
        return self._event(count, stamp)

    @staticmethod
    def _event(count: int, stamp: float) -> dict[str, int | float | str]:
        return {"phase": "generation", "tokens_done": int(count), "t_mono": stamp}


def emit_token_progress(
    throttle: TokenProgressThrottle,
    *,
    tokens_done: int,
    now: float,
    t_mono: float | None = None,
) -> dict[str, int | float | str] | None:
    event = throttle.consider(tokens_done=tokens_done, now=now, t_mono=t_mono)
    if event is not None:
        append_phase_event(event)
    return event
