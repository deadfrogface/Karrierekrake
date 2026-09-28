"""Parent-side generation deadline for one CV import.

The formula in ``import_timeout_seconds`` is the initial deadline. Once
during generation, after 64 tokens or 15 s of generation, whichever comes
first, the parent may raise that deadline from the measured token rate.
The new deadline is never shorter than the initial one, never above the
900 s ceiling, and it changes at most once. ``KARRIEREKRAKE_CV_IMPORT_TIMEOUT_S``
locks the initial deadline: there is no recalculation.

A 60 s gap after the first token is a stall. Before the first token only
the deadline applies. The parent checks both, because a child blocked
inside llama.cpp does not return to Python.
"""

from __future__ import annotations

import math

REFINE_MIN_TOKENS = 64
REFINE_MIN_GEN_S = 15.0
REFINE_RATE_PAD = 1.5
STALL_S = 60.0


class ImportDeadlineWatch:
    """Wall clock for one child. Times are monotonic seconds."""

    def __init__(
        self,
        *,
        initial_s: float,
        started_at: float,
        env_locked: bool,
        buffer_s: float,
        ceiling_s: float,
        stall_s: float = STALL_S,
    ) -> None:
        self.initial_s = float(initial_s)
        self.limit_s = float(initial_s)
        self.started_at = float(started_at)
        self.env_locked = bool(env_locked)
        self.buffer_s = float(buffer_s)
        self.ceiling_s = float(ceiling_s)
        self.stall_s = float(stall_s)
        self.max_tokens: int | None = None
        self.tokens_done = 0
        self.generation_started_at: float | None = None
        self.last_token_at: float | None = None
        self.timeout_s_final: int | None = None
        self.revisions = 0
        self._adopted = False
        self._refined = False

    def adopt_initial(self, timeout_s: float) -> None:
        """Take the child's one formula timeout as the initial deadline.

        An env override already is that deadline, so the child event does
        not replace it. A later refinement is not undone here.
        """
        if self.env_locked or self._refined or self._adopted:
            return
        self._adopted = True
        value = float(timeout_s)
        self.initial_s = value
        self.limit_s = value

    def note_max_tokens(self, value: int) -> None:
        if self.max_tokens is None and int(value) > 0:
            self.max_tokens = int(value)

    def note_tokens(self, tokens_done: int, now: float) -> int | None:
        """Record a ``tokens_done`` event. Return ``timeout_s_final`` once.

        A repeated count does not move the stall clock. The first event
        starts generation time.
        """
        count = int(tokens_done)
        if count <= 0:
            return None
        if self.generation_started_at is None:
            self.generation_started_at = float(now)
        if count <= self.tokens_done:
            return None
        self.tokens_done = count
        self.last_token_at = float(now)
        return self._maybe_refine(float(now))

    def _maybe_refine(self, now: float) -> int | None:
        if self.env_locked or self._refined:
            return None
        if self.generation_started_at is None or self.max_tokens is None:
            return None
        gen_elapsed = now - self.generation_started_at
        if self.tokens_done < REFINE_MIN_TOKENS and gen_elapsed < REFINE_MIN_GEN_S:
            return None
        if gen_elapsed <= 0 or self.tokens_done <= 0:
            return None
        self._refined = True
        rate = self.tokens_done / gen_elapsed
        remaining = max(0, self.max_tokens - self.tokens_done)
        elapsed = now - self.started_at
        recalculated = elapsed + (remaining / rate) * REFINE_RATE_PAD + self.buffer_s
        new_limit = min(self.ceiling_s, max(self.initial_s, recalculated))
        if new_limit <= self.limit_s:
            return None
        self.limit_s = new_limit
        self.revisions += 1
        shown = int(min(self.ceiling_s, math.ceil(new_limit - 1e-9)))
        if shown < math.ceil(self.initial_s - 1e-9):
            shown = int(math.ceil(self.initial_s - 1e-9))
        self.timeout_s_final = shown
        return shown

    def failure(self, now: float) -> str | None:
        """``stall`` after the first token, else ``deadline`` past the limit.

        Before the first token there is no stall. The deadline uses the
        same strict ``>`` as the stage check in the child.
        """
        if (
            self.last_token_at is not None
            and (float(now) - self.last_token_at) >= self.stall_s
        ):
            return "stall"
        if (float(now) - self.started_at) > self.limit_s:
            return "deadline"
        return None
