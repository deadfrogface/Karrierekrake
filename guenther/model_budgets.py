"""Single source of the RAM planning budgets for local model classes.

Both ``guenther.device_check`` (offline device report) and
``guenther.setup_models`` (first-run recommendation) read these values, so the
two views cannot drift apart again.

Semantics (binding):

* ``CLASS_RAM_MIN_GIB[cls]`` is the MINIMUM RAM in GiB a model of that class
  needs while running (weights + context + runtime buffers). A HIGHER value
  is STRICTER. The 27B class uses 14.0, the stricter of the two previously
  diverging values (device_check 12.0 vs. setup_models 14.0).
* ``OS_RESERVE_GIB`` is kept free for the OS and the app on top of that.
* ``CLASS_TOTAL_GATE_GIB[cls]`` is the minimum TOTAL installed RAM for which a
  class is considered at all. Below it a model of that class never "fits",
  however much RAM happens to be free.

These are conservative planning values, not measured peaks. A measured peak
only exists once ``scripts/run_i3_peak_job_benchmark.py`` produced ship
evidence on the physical i3 / 8 GB laptop (see ``guenther.setup_models``
``PEAK_ATTESTATION``).
"""
from __future__ import annotations

from core.hardware_peak_gate import HARD_PEAK_RSS_BYTES

CLASS_4B = "4b"
CLASS_8B = "8b"
CLASS_27B = "27b"

# Minimum required RAM (GiB) per class; higher = stricter.
CLASS_RAM_MIN_GIB = {CLASS_4B: 6.0, CLASS_8B: 9.0, CLASS_27B: 14.0}

# Free RAM kept for the OS/UI on top of the class budget.
OS_RESERVE_GIB = 2.0

# Minimum TOTAL RAM before a class is considered (classification by total RAM).
# An "8 GB" laptop reports ~7.7 GiB total, hence 7.0 for the 4B class.
# UNSICHER: 8B on 15 GiB total is a planning threshold, not a measurement.
CLASS_TOTAL_GATE_GIB = {CLASS_4B: 7.0, CLASS_8B: 15.0, CLASS_27B: 15.0}

# Recommendation-only thresholds (fitting is decided by the values above).
# 8B recommendation gate is unchanged from before (23 GiB total, 4 cores);
# 8B additionally needs a peak attestation. fits/alternative start at 15.0.
RECOMMEND_8B_MIN_TOTAL_GIB = 23.0
RECOMMEND_8B_MIN_CORES = 4
RECOMMEND_27B_MIN_TOTAL_GIB = 47.0
RECOMMEND_27B_MIN_CORES = 12

# Free-RAM warning threshold per class (GiB): low_free_ram is set when the
# currently free RAM is below this value for the recommended model.
# 4B: the i3 / 8 GB process-group peak gate (3_300_000_000 bytes, see
# docs/devops/i3-8gb-peak-rss-gate.md) in GiB plus a 0.5 GiB buffer, ~3.57 GiB.
# 8B/27B: their class budget (free RAM must cover the class minimum).
# UNSICHER: the 4B value is derived from the gate, not measured; replace it
# with the T05.06 low_free_ram measurement on the physical i3.
I3_PEAK_GATE_BYTES = HARD_PEAK_RSS_BYTES  # 3_300_000_000, single source
LOW_FREE_RAM_BUFFER_GIB = 0.5
LOW_FREE_RAM_WARN_GIB = {
    CLASS_4B: I3_PEAK_GATE_BYTES / 1024 ** 3 + LOW_FREE_RAM_BUFFER_GIB,
    CLASS_8B: CLASS_RAM_MIN_GIB[CLASS_8B],
    CLASS_27B: CLASS_RAM_MIN_GIB[CLASS_27B],
}

# Free disk kept on top of the artifact size.
DISK_RESERVE_BYTES = 500_000_000


def low_free_ram(model_class: str, available_gib: float) -> bool:
    """Reachable free-RAM warning: free RAM below the class warn threshold."""
    return available_gib < LOW_FREE_RAM_WARN_GIB[model_class]


def class_ram_min_gib(model_class: str, own_gib: float | None = None) -> float:
    """Required RAM for one artifact: never below its class minimum."""
    floor = CLASS_RAM_MIN_GIB[model_class]
    return floor if own_gib is None else max(float(own_gib), floor)


def ram_budget_gib(total_gib: float, available_gib: float) -> float:
    """RAM usable by a model right now: the smaller of total/free minus reserve."""
    return max(0.0, min(total_gib, available_gib) - OS_RESERVE_GIB)


def class_gate_passes(model_class: str, total_gib: float) -> bool:
    return total_gib >= CLASS_TOTAL_GATE_GIB[model_class]


def total_headroom_ok(model_class: str, total_gib: float, own_gib: float | None = None) -> bool:
    """Installed RAM can hold the class budget plus the OS reserve.

    The 4B class is exempt on purpose: it is sized by its 7.0 GiB total-RAM
    class gate. Its 6.0 + 2.0 GiB exceed the ~7.7 GiB of an 8 GB laptop, so
    applying this rule to 4B would recreate the 8 GB dead end. For 8B this is
    implied by the 15.0 GiB gate (9.0 + 2.0); for 27B it needs 16.0 GiB, so a
    16 GB device (~15.6-15.7 GiB total) never fits the 27B class.
    """
    if model_class == CLASS_4B:
        return True
    return class_ram_min_gib(model_class, own_gib) + OS_RESERVE_GIB <= total_gib


def installed_ram_fits(model_class: str, total_gib: float, own_gib: float | None = None) -> bool:
    """Device check on INSTALLED RAM: class gate and total headroom."""
    return (class_gate_passes(model_class, total_gib)
            and total_headroom_ok(model_class, total_gib, own_gib))


def ram_fits(model_class: str, *, total_gib: float, available_gib: float,
             own_gib: float | None = None) -> bool:
    """Device-only RAM check on CURRENT free RAM, shared by device_check and setup_models.

    Implies ``installed_ram_fits`` (min(total, free) - 2 GiB <= total - 2 GiB).
    """
    return (installed_ram_fits(model_class, total_gib, own_gib)
            and class_ram_min_gib(model_class, own_gib) <= ram_budget_gib(total_gib, available_gib))
