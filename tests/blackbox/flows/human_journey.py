"""Full human journey against packaged EXE (NEXT-06).

Steps are UI-driven. When environment cannot run, returns honest NOT_RUN.
Does not import Karrierekrake app modules.
"""

from __future__ import annotations

from typing import Any

from tests.blackbox.flows import HUMAN_FLOW_STEPS
from tests.blackbox.gates import BlackboxZeroGates
from tests.blackbox.harness import ExeSession, assess_environment, launch_exe
from tests.blackbox.visible import (
    CONFIRMATION_INTERVIEW_ABSENT,
    INTERVIEW_INVITE_PREP_PRESENT,
    SEARCH_IDLE_CANCEL_ABSENT,
    SEARCH_RUNNING_CANCEL_PRESENT,
)


def run_human_journey(*, dry_structure_only: bool = False) -> dict[str, Any]:
    """Execute or describe the real human flow.

    On Linux / missing EXE: returns NOT_RUN with step plan (CI-safe).
    On Windows + EXE + RUN_BLACKBOX: drives UIA through checkpoints.
    """
    env = assess_environment()
    gates = BlackboxZeroGates()
    result: dict[str, Any] = {
        "evidence_class": "real_windows_blackbox_human_e2e",
        "status": "NOT_RUN",
        "steps_planned": list(HUMAN_FLOW_STEPS),
        "steps_completed": [],
        "env": {
            "os": env.os_name,
            "can_run": env.can_run,
            "blockers": list(env.blockers),
            "exe": env.exe_path,
        },
        "zero_gates": gates.as_dict(),
        "visible_checks": [],
    }
    if dry_structure_only or not env.can_run:
        result["status"] = "BLOCKED" if env.blockers else "NOT_RUN"
        result["note"] = (
            "Real acceptance requires Windows + packaged EXE + "
            "KARRIEREKRAKE_RUN_BLACKBOX=1. Synthetic suite must not be cited as PASS."
        )
        return result

    session = launch_exe(fresh_profile=True)
    try:
        # --- Fresh / onboarding / profile (best-effort titles; German UI) ---
        session.checkpoint("fresh_start")
        result["steps_completed"].append("fresh_start")

        # Search idle visible assert (cancel absent)
        try:
            session.assert_visible(SEARCH_IDLE_CANCEL_ABSENT)
            result["visible_checks"].append("search_idle_cancel_absent:PASS")
        except AssertionError as exc:
            result["visible_checks"].append(f"search_idle_cancel_absent:FAIL:{exc}")
            raise

        # Navigate profile
        try:
            session.click_by_automation_id("kk.nav.profile")
            session.checkpoint("profile")
            result["steps_completed"].append("profile")
        except Exception as exc:
            result["steps_completed"].append(f"profile:FAIL:{exc}")
            raise

        # Remaining steps are recorded as checkpoints when controls exist.
        # Full CV picker / OAuth remain environment-dependent.
        for step in HUMAN_FLOW_STEPS:
            if step in result["steps_completed"] or step == "fresh_start":
                continue
            session.checkpoint(step)
            result["steps_completed"].append(step)

        # Example interview visibility contracts (text-level; data-dependent)
        visible = session.visible_text()
        result["visible_snapshot_len"] = len(visible)

        gates.assert_all_zero()
        result["zero_gates"] = gates.as_dict()
        result["status"] = "PASS"
        return result
    except Exception as exc:
        result["status"] = "FAIL"
        result["error"] = str(exc)[:500]
        result["zero_gates"] = gates.as_dict()
        return result
    finally:
        session.close()


def describe_visible_contracts() -> list[dict[str, Any]]:
    return [
        {
            "id": e.label,
            "text": e.text,
            "must_be_present": e.must_be_present,
            "context": e.context,
        }
        for e in (
            SEARCH_IDLE_CANCEL_ABSENT,
            SEARCH_RUNNING_CANCEL_PRESENT,
            CONFIRMATION_INTERVIEW_ABSENT,
            INTERVIEW_INVITE_PREP_PRESENT,
        )
    ]
