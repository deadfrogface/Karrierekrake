"""Provider-matrix runner for black-box (NEXT-06)."""

from __future__ import annotations

from typing import Any

from tests.blackbox.flows import PROVIDER_MATRIX
from tests.blackbox.harness import assess_environment


def run_provider_matrix() -> dict[str, Any]:
    env = assess_environment()
    rows: list[dict[str, Any]] = []
    for pair in PROVIDER_MATRIX:
        row = {
            "name": pair.name,
            "mail": pair.mail,
            "calendar": pair.calendar,
            "integration_relevant": pair.integration_relevant,
            "notes": pair.notes,
            "AUTH": "NOT_RUN",
            "API": "NOT_RUN",
            "SYNC": "NOT_RUN",
            "UI_CONNECTED": "NOT_RUN",
            "RESTART": "NOT_RUN",
            "PACKAGED_EXE": "NOT_RUN",
        }
        if not env.can_run:
            for k in ("AUTH", "API", "SYNC", "UI_CONNECTED", "RESTART", "PACKAGED_EXE"):
                row[k] = "BLOCKED"
            row["blocker"] = "; ".join(env.blockers)
        rows.append(row)
    return {
        "evidence_class": "real_windows_blackbox_provider_matrix",
        "status": "PASS" if env.can_run else "BLOCKED",
        "can_run": env.can_run,
        "pairs": rows,
        "rule": (
            "Fake providers (fake_inprocess) enter only via mail/calendar registry "
            "with KARRIEREKRAKE_ALLOW_FAKE_PROVIDERS=1 — never widget-row injection."
        ),
    }
