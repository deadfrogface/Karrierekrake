"""Classification + contracts that always run (Linux CI safe)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tests.blackbox import (
    SYNTHETIC_LABEL,
    SYNTHETIC_SUITE_PATH,
)
from tests.blackbox.flows import HUMAN_FLOW_STEPS, PROVIDER_MATRIX
from tests.blackbox.flows.human_journey import describe_visible_contracts, run_human_journey
from tests.blackbox.flows.provider_matrix import run_provider_matrix
from tests.blackbox.gates import BlackboxZeroGates
from tests.blackbox.harness import assess_environment
from tests.blackbox.visible import (
    CONFIRMATION_INTERVIEW_ABSENT,
    INTERVIEW_INVITE_PREP_PRESENT,
    SEARCH_IDLE_CANCEL_ABSENT,
    SEARCH_RUNNING_CANCEL_PRESENT,
    assert_visible,
)


ROOT = Path(__file__).resolve().parents[2]


def test_synthetic_suite_is_reclassified_not_real_acceptance():
    e2e_init = (ROOT / SYNTHETIC_SUITE_PATH / "__init__.py").read_text(encoding="utf-8")
    assert "SYNTHETIC" in e2e_init.upper() or "synthetic" in e2e_init.lower()
    assert "NOT" in e2e_init and "acceptance" in e2e_init.lower()
    report = (ROOT / "docs" / "e2e" / "full-product-e2e-report.md").read_text(encoding="utf-8")
    assert "SYNTHETIC" in report
    assert "REAL PRODUCT ACCEPTANCE READY" in report
    assert "**NO**" in report
    # Affirmative overall product pass must stay struck out / absent
    assert "OVERALL PRODUCT E2E: PASS" not in report.replace("~~OVERALL PRODUCT E2E: PASS~~", "")
    assert "SYNTHETIC" in SYNTHETIC_LABEL


def test_blackbox_package_does_not_import_app_modules():
    """Final acceptance code must not import core/desktop/integrations."""
    bb = ROOT / "tests" / "blackbox"
    forbidden_prefixes = ("core.", "desktop.", "integrations.", "guenther.", "search.")
    # Allowlisted: none — harness is pure stdlib + pywinauto + tests.blackbox
    for path in bb.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                mod = node.module
                for bad in forbidden_prefixes:
                    assert not mod.startswith(bad), f"{path} imports {mod}"
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for bad in forbidden_prefixes:
                        assert not alias.name.startswith(bad), f"{path} imports {alias.name}"


def test_human_flow_steps_cover_required_journey():
    required = {
        "onboarding",
        "profile",
        "real_local_cv_file_picker",
        "cv_preview",
        "verify_berufserfahrung_ausbildung",
        "save",
        "restart",
        "search_intent",
        "google_road_distance_job_search",
        "job_detail",
        "application_preview",
        "fake_safe_application",
        "bewerbungen",
        "inbox",
        "association",
        "lifecycle",
        "interview",
        "calendar",
        "reply_draft",
        "rejection",
        "separate_offer_case",
        "export",
        "delete_reset",
    }
    assert required.issubset(set(HUMAN_FLOW_STEPS))


def test_provider_matrix_includes_mixed_gmail_ms_calendar():
    names = {p.name for p in PROVIDER_MATRIX}
    assert "google_google" in names
    assert "microsoft_microsoft" in names
    assert "imap_caldav" in names
    assert "mixed_gmail_ms_cal" in names
    mixed = next(p for p in PROVIDER_MATRIX if p.name == "mixed_gmail_ms_cal")
    assert mixed.mail == "google_gmail"
    assert mixed.calendar == "microsoft_graph"


def test_visible_contracts_examples():
    idle = "Jobs suchen\nProfil\n"
    assert_visible(idle, SEARCH_IDLE_CANCEL_ABSENT)
    running = "Suche abbrechen\nTreffer"
    assert_visible(running, SEARCH_RUNNING_CANCEL_PRESENT)
    confirm = "Eingangsbestätigung\nZuordnung prüfen"
    assert_visible(confirm, CONFIRMATION_INTERVIEW_ABSENT)
    invite = "Interview-Einladung\nInterview vorbereiten"
    assert_visible(invite, INTERVIEW_INVITE_PREP_PRESENT)
    with pytest.raises(AssertionError):
        assert_visible(idle, SEARCH_RUNNING_CANCEL_PRESENT)


def test_zero_gates_start_at_zero():
    g = BlackboxZeroGates()
    g.assert_all_zero()
    g.bump("false_rejection", "demo")
    with pytest.raises(AssertionError):
        g.assert_all_zero()


def test_linux_honest_blocked_without_windows_exe():
    env = assess_environment()
    # On this Linux agent we must not claim PASS
    journey = run_human_journey()
    assert journey["status"] in {"NOT_RUN", "BLOCKED"}
    assert journey["evidence_class"] == "real_windows_blackbox_human_e2e"
    matrix = run_provider_matrix()
    assert matrix["status"] in {"NOT_RUN", "BLOCKED", "PASS"}
    if not env.can_run:
        assert matrix["status"] == "BLOCKED"
        assert all(
            row["AUTH"] == "BLOCKED" for row in matrix["pairs"] if row["integration_relevant"]
        )


def test_visible_contract_catalog_nonempty():
    cats = describe_visible_contracts()
    assert len(cats) >= 4
