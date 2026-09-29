"""Parent-side deadline for one CV import.

The formula in ``import_timeout_seconds`` is the initial deadline. The parent
may raise it twice and never lower it: once after the first prompt block,
from the measured prompt rate, and once after 64 generated tokens or 15 s of
generation, from the measured generation rate. Each step is

    min(ceiling, max(current deadline, recalculated))

``timeout_s_final`` is emitted only by the generation step, which is the last
recalculation. If the import ends before that step, nothing is emitted.
``KARRIEREKRAKE_CV_IMPORT_TIMEOUT_S`` locks the initial deadline.

Stall starts at the first prompt block. During the prompt the gap is
``max(60 s, 3 × first block duration)``. After the first generated token it
is 60 s. The clock is the last real progress time, not the time the event
was flushed.
"""

from __future__ import annotations

import math

REFINE_MIN_TOKENS = 64
REFINE_MIN_GEN_S = 15.0
REFINE_RATE_PAD = 1.5
STALL_S = 60.0
PROMPT_STALL_FACTOR = 3.0


class ImportDeadlineWatch:
    """Clock for one child. ``now`` is the parent's monotonic time."""

    def __init__(
        self,
        *,
        initial_s: float,
        started_at: float,
        env_locked: bool,
        buffer_s: float,
        ceiling_s: float,
        stall_s: float = STALL_S,
        r_gen_tps: float | None = None,
    ) -> None:
        if r_gen_tps is None:
            from core.cv_docpick_import import CV_IMPORT_R_GEN_TPS

            r_gen_tps = CV_IMPORT_R_GEN_TPS
        self.initial_s = float(initial_s)
        self.limit_s = float(initial_s)
        self.started_at = float(started_at)
        self.env_locked = bool(env_locked)
        self.buffer_s = float(buffer_s)
        self.ceiling_s = float(ceiling_s)
        self.stall_s = float(stall_s)
        self.r_gen_tps = float(r_gen_tps)
        self.max_tokens: int | None = None
        self.n_prompt: int | None = None
        self.tokens_done = 0
        self.prompt_tokens_done = 0
        self.generation_started_at: float | None = None
        self.last_progress_at: float | None = None
        self.first_block_s: float | None = None
        self.timeout_s_final: int | None = None
        self.revisions = 0
        self._adopted = False
        self._prompt_refined = False
        self._gen_refined = False
        self._clock_offset: float | None = None
        self._rate_tokens: int | None = None

    def adopt_initial(self, timeout_s: float) -> None:
        """Take the child's one formula timeout as the initial deadline.

        An env override already is that deadline. A recalculation is not
        undone here.
        """
        if self.env_locked or self._prompt_refined or self._gen_refined or self._adopted:
            return
        self._adopted = True
        value = float(timeout_s)
        self.initial_s = value
        self.limit_s = value

    def note_max_tokens(self, value: int) -> None:
        if self.max_tokens is None and int(value) > 0:
            self.max_tokens = int(value)

    def note_n_prompt(self, value: int) -> None:
        if self.n_prompt is None and int(value) > 0:
            self.n_prompt = int(value)

    def note_prompt(
        self,
        prompt_tokens_done: int,
        now: float,
        t_mono: float | None = None,
        block_s: float | None = None,
    ) -> None:
        """Record one prompt block. Does not emit ``timeout_s_final``."""
        count = int(prompt_tokens_done)
        if count <= 0 or count <= self.prompt_tokens_done:
            return
        progress = self._progress_at(float(now), t_mono)
        if self._rate_tokens is None:
            self._rate_tokens = count
            if block_s is not None and float(block_s) > 0:
                self.first_block_s = float(block_s)
        self.prompt_tokens_done = count
        self.last_progress_at = progress
        self._maybe_refine_prompt(float(now))

    def note_tokens(
        self,
        tokens_done: int,
        now: float,
        t_mono: float | None = None,
    ) -> int | None:
        """Record generated tokens. Return ``timeout_s_final`` once.

        The return is the deadline after the generation recalculation, which
        is the last one. A later call returns None. A repeated count does
        not move the progress clock. ``t_mono`` is the child's monotonic
        delta at the real token, including a count flushed late.
        """
        count = int(tokens_done)
        if count <= 0:
            return None
        progress = self._progress_at(float(now), t_mono)
        if self.generation_started_at is None:
            self.generation_started_at = progress
        if count <= self.tokens_done:
            return None
        self.tokens_done = count
        self.last_progress_at = progress
        return self._maybe_refine_gen(float(now), progress)

    def _progress_at(self, now: float, t_mono: float | None) -> float:
        if t_mono is None:
            return now
        if self._clock_offset is None:
            self._clock_offset = now - float(t_mono)
        return self._clock_offset + float(t_mono)

    def _maybe_refine_prompt(self, now: float) -> None:
        if self.env_locked or self._prompt_refined:
            return
        if (
            self.n_prompt is None
            or self.max_tokens is None
            or not self._rate_tokens
            or not self.first_block_s
        ):
            return
        rate = self._rate_tokens / self.first_block_s
        if rate <= 0 or self.r_gen_tps <= 0:
            return
        self._prompt_refined = True
        self.revisions += 1
        remaining = max(0, self.n_prompt - self.prompt_tokens_done)
        elapsed = now - self.started_at
        recalculated = (
            elapsed
            + (remaining / rate) * REFINE_RATE_PAD
            + (self.max_tokens / self.r_gen_tps)
            + self.buffer_s
        )
        self.limit_s = min(self.ceiling_s, max(self.limit_s, recalculated))

    def _maybe_refine_gen(self, now: float, progress: float) -> int | None:
        if self.env_locked or self._gen_refined:
            return None
        if self.generation_started_at is None or self.max_tokens is None:
            return None
        gen_elapsed = progress - self.generation_started_at
        if self.tokens_done < REFINE_MIN_TOKENS and gen_elapsed < REFINE_MIN_GEN_S:
            return None
        if gen_elapsed <= 0 or self.tokens_done <= 0:
            return None
        self._gen_refined = True
        self.revisions += 1
        rate = self.tokens_done / gen_elapsed
        remaining = max(0, self.max_tokens - self.tokens_done)
        elapsed = now - self.started_at
        recalculated = elapsed + (remaining / rate) * REFINE_RATE_PAD + self.buffer_s
        self.limit_s = min(self.ceiling_s, max(self.limit_s, recalculated))
        shown = int(min(self.ceiling_s, math.ceil(self.limit_s - 1e-9)))
        self.timeout_s_final = shown
        return shown

    def _stall_limit(self) -> float | None:
        if self.tokens_done > 0:
            return self.stall_s
        if self.prompt_tokens_done > 0:
            block = self.first_block_s or 0.0
            return max(self.stall_s, PROMPT_STALL_FACTOR * block)
        return None

    def failure(self, now: float) -> str | None:
        """``stall`` from the last real progress, else ``deadline``.

        Before the first prompt block and the first token there is no stall.
        The deadline uses the same strict ``>`` as the stage check.
        """
        stall_after = self._stall_limit()
        if (
            stall_after is not None
            and self.last_progress_at is not None
            and (float(now) - self.last_progress_at) >= stall_after
        ):
            return "stall"
        if (float(now) - self.started_at) > self.limit_s:
            return "deadline"
        return None
