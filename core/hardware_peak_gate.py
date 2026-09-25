"""Hard process-group peak memory gate for the i3-11 / 8 GB Windows laptop.

The ship limit is ``HARD_PEAK_RSS_BYTES`` (3_300_000_000). A measurement at or
below that value passes. Anything above fails hard.

A historical twelve-gigabyte ceiling is not a success criterion. Agent-VM and
CI numbers are not ship evidence; only a Windows Job Object run on the physical
laptop is.
See ``docs/devops/i3-8gb-peak-rss-gate.md``.
"""

from __future__ import annotations

from dataclasses import dataclass

# Intel Core i3 (11th gen) / 8 GB RAM — process-group peak, inclusive.
HARD_PEAK_RSS_BYTES = 3_300_000_000

# 12 GiB and 12*10^9 both sit above the hard gate. Kept only so call sites and
# tests can show that the retired soft ceiling is a failure, not a pass.
# RETIRED_NOT_A_PASS
RETIRED_SOFT_12GB_DECIMAL_BYTES = 12_000_000_000  # RETIRED_NOT_A_PASS
RETIRED_SOFT_12GIB_BYTES = 12 * 1024 * 1024 * 1024  # RETIRED_NOT_A_PASS


@dataclass(frozen=True)
class PeakVerdict:
    peak_bytes: int
    limit_bytes: int
    hard_fail: bool

    @property
    def ok(self) -> bool:
        return not self.hard_fail


def evaluate_peak(
    peak_bytes: int,
    *,
    limit_bytes: int = HARD_PEAK_RSS_BYTES,
) -> PeakVerdict:
    """Hard fail when the process-group peak is above the limit.

    ``peak_bytes == limit_bytes`` passes (the gate is ≤, not <).
    """
    if peak_bytes < 0:
        raise ValueError(f"peak_bytes must be >= 0, got {peak_bytes}")
    if limit_bytes <= 0:
        raise ValueError(f"limit_bytes must be > 0, got {limit_bytes}")
    return PeakVerdict(
        peak_bytes=int(peak_bytes),
        limit_bytes=int(limit_bytes),
        hard_fail=int(peak_bytes) > int(limit_bytes),
    )


def verdict_for_run(
    peak_bytes: int,
    *,
    process_exit: int | None,
    enforce_limit: bool,
    killed_by_harness: bool,
    limit_bytes: int = HARD_PEAK_RSS_BYTES,
) -> PeakVerdict:
    """Combine the measured peak with an optional Job Object memory cap.

    ``--enforce-limit`` asks Windows to deny commit above the gate. An OOM exit
    in that mode is a hard fail even if the recorded peak never crossed the
    number (the cap stops the counter). Harness-initiated cancel/timeout kills
    are not treated as OOM.
    """
    verdict = evaluate_peak(peak_bytes, limit_bytes=limit_bytes)
    if verdict.hard_fail:
        return verdict
    if enforce_limit and not killed_by_harness and is_oom_exit(process_exit):
        return PeakVerdict(
            peak_bytes=verdict.peak_bytes,
            limit_bytes=verdict.limit_bytes,
            hard_fail=True,
        )
    return verdict


# Child protocol + Windows NTSTATUS values that mean the process group ran out
# of memory. SIGKILL (137 / -9) counts only when the harness did not kill it.
_OOM_EXIT_CODES = {
    3,
    137,
    -9,
    0xC0000017,  # STATUS_NO_MEMORY
    0xC000012D,  # STATUS_COMMITMENT_LIMIT
}


def is_oom_exit(process_exit: int | None) -> bool:
    if process_exit is None:
        return False
    code = int(process_exit)
    if code < 0:
        # Python subprocess: negative signal number, or unsigned NTSTATUS
        # truncated into a signed 32-bit wait status.
        if code in _OOM_EXIT_CODES:
            return True
        unsigned = code & 0xFFFFFFFF
        return unsigned in _OOM_EXIT_CODES
    return code in _OOM_EXIT_CODES or (code & 0xFFFFFFFF) in _OOM_EXIT_CODES
