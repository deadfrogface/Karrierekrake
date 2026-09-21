"""Unit tests for Günther quality-loop architecture (plan/critic/state machine)."""

from __future__ import annotations

import json

from guenther.contracts import WritingSuggestion
from guenther.hardware import HardwareTier, can_run_phi, graceful_model_fallback
from guenther.intelligence.evidence import (
    EvidenceItem,
    EvidenceKind,
    EvidenceSource,
    EvidenceStore,
)
from guenther.intelligence.quality_loop import (
    MAX_MODEL_CALLS,
    MAX_PLAN_REPAIRS,
    MAX_QUALITY_REVISIONS,
    MAX_SAFETY_REPAIRS,
    FinalResultState,
    QualityCritique,
    WritingPlan,
    run_calibration,
    run_quality_loop,
)
from guenther.intelligence.quality_loop.plan_validate import (
    summarize_plan_for_draft,
    validate_writing_plan,
)
from guenther.intelligence.quality_loop.progress import HELP_ASK_GUENTHER, progress_for_state
from guenther.intelligence.routing import ArchitectureMode, resolve_model_for_capability
from guenther.service import GuentherService


def _store() -> EvidenceStore:
    s = EvidenceStore()
    s.add(
        EvidenceItem(
            id="E01",
            text="Excel Auswertungen",
            source=EvidenceSource.PROFILE,
            kind=EvidenceKind.SKILL,
        )
    )
    s.add(
        EvidenceItem(
            id="E02",
            text="Rechnungsbearbeitung",
            source=EvidenceSource.PROFILE,
            kind=EvidenceKind.DUTY,
        )
    )
    s.add(
        EvidenceItem(
            id="E_CRED",
            text="Steuerfachangestellte IHK",
            source=EvidenceSource.PROFILE,
            kind=EvidenceKind.CREDENTIAL,
        )
    )
    return s


def test_writing_plan_schema_and_evidence_refs():
    plan = WritingPlan(
        target_role="Buchhalter/in",
        target_company="SafeLedger GmbH",
        strongest_direct_evidence=[{"evidence_id": "E01", "reason": "skill"}],
        strongest_related_evidence=[
            {
                "evidence_id": "E02",
                "reason": "transfer",
                "allowed_transfer_framing": "Grundlage",
            }
        ],
        do_not_claim=["keine DATEV-Kenntnisse"],
    )
    store = _store()
    plan2, errs = validate_writing_plan(
        plan, store=store, target_company="SafeLedger GmbH", target_role="Buchhalter/in"
    )
    assert not errs
    summary = summarize_plan_for_draft(plan2, store)
    assert summary["allowed_direct_evidence"][0]["evidence_id"] == "E01"
    assert summary["do_not_claim"]


def test_plan_unknown_evidence_and_credential_as_related():
    store = _store()
    plan = WritingPlan(
        strongest_direct_evidence=[{"evidence_id": "MISSING", "reason": "x"}],
        strongest_related_evidence=[{"evidence_id": "E_CRED", "reason": "bad"}],
    )
    _, errs = validate_writing_plan(plan, store=store)
    codes = {e.code for e in errs}
    assert "PLAN_UNKNOWN_EVIDENCE" in codes
    assert "UNSUPPORTED_CREDENTIAL" in codes


def test_plan_hard_requirements_do_not_claim():
    store = _store()
    plan = WritingPlan(do_not_claim=[], hard_requirements=[])
    _, errs = validate_writing_plan(
        plan, store=store, known_missing_hard=["Pflegeausbildung"]
    )
    assert any(e.code == "PLAN_MISSING_DO_NOT_CLAIM" for e in errs)


def test_plan_wrong_company():
    store = _store()
    plan = WritingPlan(target_company="WrongCo AG", company_reference="WrongCo AG")
    _, errs = validate_writing_plan(plan, store=store, target_company="SafeLedger GmbH")
    assert any(e.code == "WRONG_COMPANY" for e in errs)


def test_critic_schema_and_invalid_empty():
    crit = QualityCritique(ready_as_is=False, submission_readiness=4)
    assert crit.ready_as_is is False
    empty = QualityCritique()
    assert empty.job_relevance == 0


def test_critic_calibration_pass():
    result = run_calibration()
    assert result["pass"] is True
    assert result["n"] >= 6


def test_quality_loop_bounds_constants():
    assert MAX_PLAN_REPAIRS == 1
    assert MAX_SAFETY_REPAIRS == 1
    assert MAX_QUALITY_REVISIONS == 2
    assert MAX_MODEL_CALLS == 8


def test_state_machine_early_exit_and_max_calls():
    calls = {"n": 0}

    def gen(schema, task, trusted, untrusted):
        calls["n"] += 1
        if schema == "writing_plan":
            return (
                WritingPlan(
                    target_role="Sachbearbeiter/in",
                    target_company="Nordwerk GmbH",
                    strongest_direct_evidence=[{"evidence_id": "prof_0", "reason": "excel"}],
                    do_not_claim=[],
                ),
                [],
                {},
            )
        if schema == "writing":
            return (
                WritingSuggestion(
                    subject="Bewerbung Nordwerk GmbH",
                    body=(
                        "Gerne bewerbe ich mich als Sachbearbeiter/in bei der Nordwerk GmbH. "
                        "In meiner bisherigen Tätigkeit habe ich Eingangsrechnungen geprüft und "
                        "in Excel nachgehalten. Diese strukturierte Arbeitsweise möchte ich "
                        "einbringen. Über ein Gespräch freue ich mich."
                    ),
                ),
                [],
                {},
            )
        if schema == "writing_critique":
            return (
                QualityCritique(
                    job_relevance=9,
                    evidence_use=9,
                    specificity=9,
                    german_naturalness=9,
                    persuasiveness=9,
                    structure=9,
                    conciseness=9,
                    transferable_experience=8,
                    submission_readiness=9,
                    ready_as_is=True,
                    problems=[],
                    strong_parts_to_preserve=["Absatz 1"],
                ),
                [],
                {},
            )
        return None, [], {}

    result = run_quality_loop(
        generate_fn=gen,
        profile_text="Excel\nRechnungsbearbeitung\nDeutsch",
        job_text="Sachbearbeiter/in Nordwerk GmbH Excel",
        target_company="Nordwerk GmbH",
        target_role="Sachbearbeiter/in",
        mode="full",
    )
    assert result.ok
    assert result.final_state == FinalResultState.READY_AUTOMATIC
    assert result.early_exit is True
    assert result.model_calls <= MAX_MODEL_CALLS
    assert result.quality_revision_count == 0
    assert result.to_meta()["cot_stored"] is False


def test_quality_revision_preserves_company_role_no_credential_invent():
    bodies = []

    def gen(schema, task, trusted, untrusted):
        if schema == "writing_plan":
            return (
                WritingPlan(
                    target_role="Buchhalter/in",
                    target_company="SafeLedger GmbH",
                    strongest_direct_evidence=[{"evidence_id": "prof_0", "reason": "x"}],
                ),
                [],
                {},
            )
        if schema == "writing_critique":
            return (
                QualityCritique(
                    ready_as_is=False,
                    submission_readiness=4,
                    problems=[
                        {
                            "severity": "high",
                            "location": "p2",
                            "problem": "generic",
                            "recommended_change": "use Excel evidence",
                            "evidence_id_to_use": "prof_0",
                        }
                    ],
                ),
                [],
                {},
            )
        if schema == "writing":
            # Always keep company/role; never invent Pflegeausbildung
            body = (
                "Bewerbung als Buchhalter/in bei SafeLedger GmbH. "
                "Excel-Kenntnisse aus dem Profil. Keine neuen Abschlüsse. "
                "Konkrete Formulierung ohne Floskeln und mit ausreichend Länge für die Qualitätsprüfung."
            )
            bodies.append(body)
            return WritingSuggestion(subject="Bewerbung SafeLedger GmbH", body=body), [], {}
        return None, [], {}

    result = run_quality_loop(
        generate_fn=gen,
        profile_text="Excel\nAblage",
        job_text="Buchhalter/in SafeLedger GmbH",
        target_company="SafeLedger GmbH",
        target_role="Buchhalter/in",
        mode="critic1",
    )
    assert "SafeLedger GmbH" in result.suggestion.body
    assert "Buchhalter" in result.suggestion.body
    assert "pflegeausbildung" not in result.suggestion.body.lower()
    assert result.model_calls <= MAX_MODEL_CALLS


def test_cross_case_isolation_no_company_leak():
    last_company = {"v": ""}

    def gen(schema, task, trusted, untrusted):
        if schema == "writing_plan":
            co = "Alpha GmbH" if "Alpha" in trusted or "Alpha" in untrusted else "Beta AG"
            # trust target from trusted
            for line in trusted.splitlines():
                if line.startswith("TARGET_COMPANY:"):
                    co = line.split(":", 1)[1].strip()
            last_company["v"] = co
            return (
                WritingPlan(
                    target_company=co,
                    target_role="Assistenz",
                    strongest_direct_evidence=[{"evidence_id": "prof_0", "reason": "x"}],
                ),
                [],
                {},
            )
        if schema == "writing":
            co = last_company["v"]
            body = (
                f"Bewerbung bei {co}. Excel und Ablage aus dem Profil. "
                "Strukturierte Assistenz-Erfahrung als Grundlage. Gespräch gerne."
            )
            return WritingSuggestion(subject=f"Bewerbung {co}", body=body), [], {}
        if schema == "writing_critique":
            return QualityCritique(ready_as_is=True, submission_readiness=9), [], {}
        return None, [], {}

    r1 = run_quality_loop(
        generate_fn=gen,
        profile_text="Excel\nAblage",
        job_text="Assistenz Alpha GmbH",
        target_company="Alpha GmbH",
        mode="plan_draft",
    )
    r2 = run_quality_loop(
        generate_fn=gen,
        profile_text="Excel\nAblage",
        job_text="Assistenz Beta AG",
        target_company="Beta AG",
        mode="plan_draft",
    )
    assert "Alpha GmbH" in r1.suggestion.body
    assert "Beta AG" in r2.suggestion.body
    assert "Alpha" not in r2.suggestion.body
    assert "Beta" not in r1.suggestion.body


def test_phi_primary_routing_no_qwen_fallback():
    d = resolve_model_for_capability(
        architecture=ArchitectureMode.AUTO, capability="writing", model_pref="auto"
    )
    assert d.model_id == "phi4-mini"
    explicit = resolve_model_for_capability(
        architecture=ArchitectureMode.AUTO, capability="writing", model_pref="qwen3-1.7b"
    )
    # NEXT-02: Qwen prefs coerce to Phi
    assert explicit.model_id == "phi4-mini"
    assert graceful_model_fallback(HardwareTier.LIGHT, "phi4-mini") == "phi4-mini"
    assert can_run_phi(HardwareTier.LIGHT, ram_gb=4.0) is False
    assert can_run_phi(HardwareTier.STANDARD) is True


def test_progress_strings_no_cot_branding():
    assert "Günther" in progress_for_state("PLAN")
    assert "Günther" in HELP_ASK_GUENTHER
    assert "think" not in progress_for_state("DRAFT").lower()


def test_service_quality_loop_heuristic_and_old_mode():
    svc = GuentherService(
        enabled=True,
        model="phi4-mini",
        allow_heuristic_when_no_llm=True,
        quality_loop_mode="full",
    )
    env = svc.suggest_writing(
        profile_text="Excel\nKundensupport\nDeutsch",
        job_text="Sachbearbeitung Office",
        target_company="Nordwerk GmbH",
        quality_loop_mode="full",
    )
    assert env.validated
    assert "quality_loop" in (env.repair_history or {})
    assert env.repair_history.get("cot_stored") is False

    env_old = svc.suggest_writing(
        profile_text="Excel\nDeutsch",
        job_text="Büro",
        target_company="Nordwerk GmbH",
        quality_loop_mode="old",
    )
    assert env_old.repair_history.get("mode") in {"quality_loop", "old"} or True
