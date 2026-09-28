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
) -> tuple[int | None, int | None]:
    """Keep the first ``timeout_s`` and the latest ``tokens_done`` count.

    Plain stage names are ignored. ``max_tokens`` is not a UI field.
    The visible status text stays the existing progress sentence.
    There is no remaining-time calculation.
    """
    if not message.startswith("{"):
        return timeout_s, tokens_done
    try:
        event = json.loads(message)
    except json.JSONDecodeError:
        return timeout_s, tokens_done
    if not isinstance(event, dict):
        return timeout_s, tokens_done
    if "timeout_s" in event and timeout_s is None:
        try:
            timeout_s = int(event["timeout_s"])
        except (TypeError, ValueError):
            pass
    if "tokens_done" in event:
        try:
            tokens_done = int(event["tokens_done"])
        except (TypeError, ValueError):
            pass
    return timeout_s, tokens_done


def emit_diag(message: str, *, level: str = "info") -> None:
    """One diagnostic line for the parent. The child process has no app log."""
    append_phase_event({"diag": message, "level": level})


def relay_diag_event(event: dict) -> bool:
    """Write a child diagnostic into the app log. True when ``event`` is one.

    The parent is the only writer of ``karrierekrake.log``. A diag event is
    not a UI progress line.
    """
    if "diag" not in event:
        return False
    message = str(event.get("diag") or "").strip()
    if not message:
        return True
    level = str(event.get("level") or "info").lower()
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
    """At most one generation-progress event per ``interval_s``."""

    def __init__(self, interval_s: float = TOKEN_EVENT_INTERVAL_S) -> None:
        self.interval_s = float(interval_s)
        self._last: float | None = None

    def consider(
        self,
        *,
        tokens_done: int,
        now: float,
    ) -> dict[str, int | str] | None:
        """Emit immediately on the first token, then at most once per interval."""
        if self._last is not None and (now - self._last) < self.interval_s:
            return None
        self._last = now
        return {"phase": "generation", "tokens_done": int(tokens_done)}


def emit_token_progress(
    throttle: TokenProgressThrottle,
    *,
    tokens_done: int,
    now: float,
) -> dict[str, int | str] | None:
    event = throttle.consider(tokens_done=tokens_done, now=now)
    if event is not None:
        append_phase_event(event)
    return event
