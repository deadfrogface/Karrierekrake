"""Phase events from the CV-import child to the UI.

``timeout_s`` is the supervisor's already chosen wall-clock limit, in whole
seconds. Nothing in this module derives a new limit from the token count.
Generation progress is at most one event per second.
"""

from __future__ import annotations

import json
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


def generation_timeout_event() -> dict[str, int | str] | None:
    """One event with the published supervisor timeout, or None if already sent.

    Reads ``KARRIEREKRAKE_CV_IMPORT_TIMEOUT_S`` as the supervisor set it.
    Does not recompute the limit.
    """
    global _timeout_sent
    if _timeout_sent:
        return None
    _timeout_sent = True
    raw = os.environ.get("KARRIEREKRAKE_CV_IMPORT_TIMEOUT_S", "").strip()
    if raw:
        timeout_s = int(float(raw))
    else:
        from core.cv_docpick_import import CV_IMPORT_TIMEOUT_S

        timeout_s = int(CV_IMPORT_TIMEOUT_S)
    return {"phase": "generation", "timeout_s": timeout_s}


def absorb_phase_message(
    message: str,
    *,
    timeout_s: int | None,
    tokens_done: int | None,
    max_tokens: int | None,
) -> tuple[int | None, int | None, int | None]:
    """Keep the first ``timeout_s`` and the latest throttled token counts.

    Plain stage names are ignored. The visible status text stays the
    existing progress sentence.
    """
    if not message.startswith("{"):
        return timeout_s, tokens_done, max_tokens
    try:
        event = json.loads(message)
    except json.JSONDecodeError:
        return timeout_s, tokens_done, max_tokens
    if not isinstance(event, dict):
        return timeout_s, tokens_done, max_tokens
    if "timeout_s" in event and timeout_s is None:
        try:
            timeout_s = int(event["timeout_s"])
        except (TypeError, ValueError):
            pass
    if "tokens_done" in event and "max_tokens" in event:
        try:
            tokens_done = int(event["tokens_done"])
            max_tokens = int(event["max_tokens"])
        except (TypeError, ValueError):
            pass
    return timeout_s, tokens_done, max_tokens


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


def emit_generation_timeout() -> dict[str, int | str] | None:
    event = generation_timeout_event()
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
        max_tokens: int,
        now: float,
    ) -> dict[str, int | str] | None:
        if self._last is not None and (now - self._last) < self.interval_s:
            return None
        self._last = now
        return {
            "phase": "generation",
            "tokens_done": int(tokens_done),
            "max_tokens": int(max_tokens),
        }


def emit_token_progress(
    throttle: TokenProgressThrottle,
    *,
    tokens_done: int,
    max_tokens: int,
    now: float,
) -> dict[str, int | str] | None:
    event = throttle.consider(tokens_done=tokens_done, max_tokens=max_tokens, now=now)
    if event is not None:
        append_phase_event(event)
    return event
