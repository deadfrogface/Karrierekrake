"""Hard 3_300_000_000 process-group peak gate. CI numbers are not ship evidence."""

from __future__ import annotations

import ctypes
import sys
from pathlib import Path

import pytest

from core.hardware_peak_gate import (
    HARD_PEAK_RSS_BYTES,
    RETIRED_SOFT_12GB_DECIMAL_BYTES,
    RETIRED_SOFT_12GIB_BYTES,
    evaluate_peak,
    verdict_for_run,
)
from devops.peak_rss_harness import run_contained_until_exit, run_self_test
from devops.win_job_object import (
    CREATE_BREAKAWAY_FROM_JOB,
    CREATE_SUSPENDED,
    JOB_OBJECT_LIMIT_BREAKAWAY_OK,
    JOB_OBJECT_LIMIT_JOB_MEMORY,
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
    JOB_OBJECT_LIMIT_SILENT_BREAKAWAY_OK,
    JOBOBJECT_EXTENDED_LIMIT_INFORMATION,
    assign_then_resume,
    containment_limit_flags,
    create_process_flags,
    extended_limit_info,
)

ROOT = Path(__file__).resolve().parents[1]
SCAN_ROOTS = ("core", "desktop", "devops", "guenther", "scripts", "tests", ".github", "app")
SOFT_PATTERNS = (
    "12_000_000_000",
    "12884901888",
    "<= 12 GB",
    "<= 12GB",
    "≤ 12 GB",
    "≤12 GB",
    "SOFT_PEAK",
)


def test_hard_limit_is_exactly_3_300_000_000():
    assert HARD_PEAK_RSS_BYTES == 3_300_000_000
    assert evaluate_peak(3_300_000_000).ok
    assert evaluate_peak(3_300_000_000).hard_fail is False
    assert evaluate_peak(3_300_000_001).hard_fail
    assert evaluate_peak(0).ok


def test_retired_12gb_soft_ceiling_is_a_hard_fail():
    # RETIRED_NOT_A_PASS — 12 GB decimal and 12 GiB must not pass.
    assert evaluate_peak(RETIRED_SOFT_12GB_DECIMAL_BYTES).hard_fail
    assert evaluate_peak(RETIRED_SOFT_12GIB_BYTES).hard_fail
    assert RETIRED_SOFT_12GIB_BYTES > HARD_PEAK_RSS_BYTES


def test_enforced_oom_fails_even_when_sampled_peak_is_under_the_cap():
    assert verdict_for_run(
        100,
        process_exit=3,
        enforce_limit=True,
        killed_by_harness=False,
    ).hard_fail
    assert verdict_for_run(
        100,
        process_exit=3,
        enforce_limit=True,
        killed_by_harness=True,
    ).ok
    assert verdict_for_run(
        HARD_PEAK_RSS_BYTES + 1,
        process_exit=0,
        enforce_limit=False,
        killed_by_harness=False,
    ).hard_fail


def test_job_object_flags_block_breakaway_and_assign_before_resume():
    flags = containment_limit_flags()
    assert flags & JOB_OBJECT_LIMIT_BREAKAWAY_OK == 0
    assert flags & JOB_OBJECT_LIMIT_SILENT_BREAKAWAY_OK == 0
    assert flags & JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    created = create_process_flags(console=False)
    assert created & CREATE_BREAKAWAY_FROM_JOB == 0
    assert created & CREATE_SUSPENDED
    enforced = containment_limit_flags(enforce_memory_bytes=HARD_PEAK_RSS_BYTES)
    assert enforced & JOB_OBJECT_LIMIT_JOB_MEMORY
    info = extended_limit_info(enforce_memory_bytes=HARD_PEAK_RSS_BYTES)
    assert int(info.JobMemoryLimit) == HARD_PEAK_RSS_BYTES
    assert int(info.BasicLimitInformation.LimitFlags) & JOB_OBJECT_LIMIT_BREAKAWAY_OK == 0

    class _Kernel:
        def __init__(self) -> None:
            self.events: list[str] = []

        def AssignProcessToJobObject(self, job, process) -> int:
            self.events.append("assign")
            return 1

        def ResumeThread(self, thread) -> int:
            self.events.append("resume")
            return 1

    kernel = _Kernel()
    assign_then_resume(kernel, 1, 2, 3)
    assert kernel.events == ["assign", "resume"]


def test_extended_limit_struct_matches_64bit_windows_layout():
    if ctypes.sizeof(ctypes.c_void_p) != 8:
        pytest.skip("layout assertion is for 64-bit")
    assert ctypes.sizeof(JOBOBJECT_EXTENDED_LIMIT_INFORMATION) == 144


def test_no_soft_12gb_success_criterion_in_runtime_or_ci():
    hits: list[str] = []
    for rel in SCAN_ROOTS:
        root = ROOT / rel
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.suffix.lower() not in {".py", ".yml", ".yaml"}:
                continue
            if path.name == "test_i3_peak_gate.py":
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for lineno, line in enumerate(text.splitlines(), start=1):
                if "RETIRED_NOT_A_PASS" in line:
                    continue
                lowered = line.lower()
                if any(token.lower() in lowered for token in SOFT_PATTERNS):
                    hits.append(f"{path.relative_to(ROOT)}:{lineno}:{line.strip()}")
                if "12" in line and "1024" in line and "*" in line and "pass" in lowered:
                    hits.append(f"{path.relative_to(ROOT)}:{lineno}:{line.strip()}")
    assert hits == []


def test_self_test_contains_grandchild_and_stays_under_the_gate():
    report = run_self_test(timeout_s=20)
    assert report["contained"] is True
    assert report["breakaway_flags_set"] is False
    assert report["ship_evidence"] is False
    assert report["hard_fail"] is False
    assert report["peak_bytes"] <= HARD_PEAK_RSS_BYTES
    assert report["limit_bytes"] == HARD_PEAK_RSS_BYTES
    assert report["grandchild_pid"] != report["child_pid"]


def test_short_process_is_not_ship_evidence_even_if_attest_is_requested():
    report = run_contained_until_exit(
        [sys.executable, "-c", "print('peak-scaffold')"],
        timeout_s=30,
        attest_physical_i3=True,
        console=False,
    )
    assert report.hard_fail is False
    assert report.ship_evidence is False
    assert report.breakaway_flags_set is False
    assert "attest_refused_not_physical_windows_job" in report.notes
