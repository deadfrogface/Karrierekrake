"""Deterministic validation of WritingPlan against EvidenceStore + job targeting."""

from __future__ import annotations

import re
from typing import Any

from guenther.intelligence.errors import (
    UNSUPPORTED_CREDENTIAL,
    WRONG_COMPANY,
    ValidatorError,
    make_error,
)
from guenther.intelligence.evidence import EvidenceKind, EvidenceStore
from guenther.intelligence.quality_loop.schemas import (
    RequirementStatus,
    WritingPlan,
)


def _known_ids(store: EvidenceStore) -> set[str]:
    return {i.id for i in store.items}


def _credential_ids(store: EvidenceStore) -> set[str]:
    return {i.id for i in store.items if i.kind == EvidenceKind.CREDENTIAL}


def validate_writing_plan(
    plan: WritingPlan,
    *,
    store: EvidenceStore,
    target_company: str | None = None,
    target_role: str | None = None,
    known_missing_hard: list[str] | None = None,
) -> tuple[WritingPlan, list[ValidatorError]]:
    """Validate plan deterministically. Does not invent or weaken safety."""
    errors: list[ValidatorError] = []
    known = _known_ids(store)
    creds = _credential_ids(store)

    # Drop do_not_claim entries that are actually supported by profile evidence
    # (false blocks that starve the writer of legitimate material).
    corpus = store.corpus().lower()
    cleaned_dnc: list[str] = []
    for claim in plan.do_not_claim:
        c = str(claim).strip()
        if not c:
            continue
        tokens = [t for t in re.findall(r"[a-zäöüß]{4,}", c.lower()) if t not in {"keine", "kein", "ohne", "nicht", "erfahrung", "bereich"}]
        if tokens and sum(1 for t in tokens if t in corpus) >= max(1, len(tokens) - 1):
            # Supported by profile — do not forbid
            continue
        cleaned_dnc.append(c)
    if cleaned_dnc != list(plan.do_not_claim):
        plan = plan.model_copy(update={"do_not_claim": cleaned_dnc})

    for ref in plan.strongest_direct_evidence:
        if ref.evidence_id not in known:
            errors.append(
                make_error(
                    "PLAN_UNKNOWN_EVIDENCE",
                    severity="error",
                    message_de=f"Plan verweist auf unbekannte DIRECT-Evidenz {ref.evidence_id}.",
                    repair_instruction=(
                        f"Entferne evidence_id {ref.evidence_id} oder ersetze durch eine "
                        "existierende EvidenceStore-ID."
                    ),
                    claim_text=ref.evidence_id,
                )
            )
        elif ref.evidence_id in creds:
            # credentials in direct list are OK (DIRECT)
            pass

    for ref in plan.strongest_related_evidence:
        if ref.evidence_id not in known:
            errors.append(
                make_error(
                    "PLAN_UNKNOWN_EVIDENCE",
                    severity="error",
                    message_de=f"Plan verweist auf unbekannte RELATED-Evidenz {ref.evidence_id}.",
                    repair_instruction=(
                        f"Entferne evidence_id {ref.evidence_id} oder ersetze durch eine "
                        "existierende EvidenceStore-ID."
                    ),
                    claim_text=ref.evidence_id,
                )
            )
        if ref.evidence_id in creds:
            errors.append(
                make_error(
                    UNSUPPORTED_CREDENTIAL,
                    severity="error",
                    message_de="Credential darf nicht als RELATED geführt werden.",
                    repair_instruction=(
                        f"Verschiebe {ref.evidence_id} nach strongest_direct_evidence "
                        "oder entferne den Credential-Bezug."
                    ),
                    claim_text=ref.evidence_id,
                )
            )

    if target_company and str(target_company).strip():
        co = str(target_company).strip()
        planned = (plan.target_company or "").strip()
        if planned and co.lower() not in planned.lower() and planned.lower() not in co.lower():
            if planned.upper() not in {"UNKNOWN", "UNBEKANNT", ""}:
                errors.append(
                    make_error(
                        WRONG_COMPANY,
                        severity="error",
                        message_de=f"Plan-Firma '{planned}' weicht von TARGET_COMPANY '{co}' ab.",
                        repair_instruction=f"Setze target_company exakt auf '{co}'.",
                        claim_text=planned,
                    )
                )
        ref_txt = (plan.company_reference or "").strip()
        if ref_txt and co.lower() not in ref_txt.lower():
            # soft: company_reference should mention company when known — repairable
            if "[" in ref_txt or "]" in ref_txt:
                errors.append(
                    make_error(
                        "UNRESOLVED_PLACEHOLDER",
                        severity="error",
                        message_de="company_reference enthält Platzhalter.",
                        repair_instruction=f"Ersetze Platzhalter durch '{co}' oder generische Formulierung.",
                        claim_text=ref_txt[:120],
                    )
                )

    if target_role and str(target_role).strip():
        role = str(target_role).strip()
        planned_role = (plan.target_role or "").strip()
        if planned_role and role.lower() not in planned_role.lower() and planned_role.lower() not in role.lower():
            # allow slight wording differences; only block clear opposite placeholders
            if "[" in planned_role or "]" in planned_role:
                errors.append(
                    make_error(
                        "UNRESOLVED_PLACEHOLDER",
                        severity="error",
                        message_de="target_role enthält Platzhalter.",
                        repair_instruction=f"Setze target_role auf '{role}'.",
                        claim_text=planned_role,
                    )
                )

    for claim in plan.do_not_claim:
        if not str(claim).strip():
            continue
        # do_not_claim must not assert the candidate HAS the thing
        low = claim.lower()
        if any(x in low for x in ("ich habe", "ich besitze", "abgeschlossen")):
            errors.append(
                make_error(
                    "PLAN_DO_NOT_CLAIM_MALFORMED",
                    severity="error",
                    message_de="do_not_claim darf keine positive Faktenbehauptung sein.",
                    repair_instruction="Formuliere als verbotene Behauptung, z.B. 'keine Pflegeausbildung'.",
                    claim_text=claim[:120],
                )
            )

    missing = [m for m in (known_missing_hard or []) if str(m).strip()]
    if missing:
        dnc_blob = " ".join(plan.do_not_claim).lower()
        hard_not_met = [
            h.requirement
            for h in plan.hard_requirements
            if h.status in {RequirementStatus.NOT_MET, RequirementStatus.UNKNOWN}
        ]
        covered = dnc_blob + " " + " ".join(hard_not_met).lower()
        for m in missing:
            token = str(m).strip().lower()
            if token and token not in covered and len(token) >= 4:
                errors.append(
                    make_error(
                        "PLAN_MISSING_DO_NOT_CLAIM",
                        severity="error",
                        message_de=f"Fehlende Hard-Requirement '{m}' fehlt in do_not_claim/hard_requirements.",
                        repair_instruction=(
                            f"Füge '{m}' zu do_not_claim hinzu und setze hard_requirements.status=NOT_MET."
                        ),
                        claim_text=m[:120],
                    )
                )

    # invented unsupported material in arguments
    blob = " ".join(
        [
            plan.candidate_positioning,
            plan.argument_1,
            plan.argument_2,
            plan.argument_3,
            plan.opening_strategy,
            plan.closing_strategy,
        ]
    ).lower()
    for phrase in ("pflegeausbildung", "staatl", "bachelor", "master", "ihk-abschluss"):
        if phrase in blob:
            corpus = store.corpus().lower()
            if phrase not in corpus:
                errors.append(
                    make_error(
                        UNSUPPORTED_CREDENTIAL,
                        severity="error",
                        message_de=f"Plan erwähnt '{phrase}' ohne Evidenz.",
                        repair_instruction=f"Entferne '{phrase}' aus dem Plan oder belege mit Evidence-ID.",
                        claim_text=phrase,
                    )
                )

    ok_plan = plan
    return ok_plan, errors


def plan_blocking(errors: list[ValidatorError]) -> bool:
    return any(e.severity == "error" for e in errors)


def summarize_plan_for_draft(
    plan: WritingPlan,
    store: EvidenceStore,
    *,
    contact_claims: Any | None = None,
) -> dict[str, Any]:
    """Compact verified plan payload for the drafting prompt (no unrelated profile dump)."""
    by_id = {i.id: i for i in store.items}
    direct = []
    for ref in plan.strongest_direct_evidence:
        item = by_id.get(ref.evidence_id)
        if item:
            direct.append(
                {
                    "evidence_id": ref.evidence_id,
                    "text": item.text,
                    "kind": item.kind.value,
                    "reason": ref.reason,
                }
            )
    related = []
    for ref in plan.strongest_related_evidence:
        item = by_id.get(ref.evidence_id)
        if item:
            related.append(
                {
                    "evidence_id": ref.evidence_id,
                    "text": item.text,
                    "kind": item.kind.value,
                    "reason": ref.reason,
                    "allowed_transfer_framing": ref.allowed_transfer_framing,
                }
            )
    out = {
        "target_role": plan.target_role,
        "target_company": plan.target_company,
        "candidate_positioning": plan.candidate_positioning,
        "allowed_direct_evidence": direct,
        "allowed_related_evidence": related,
        "do_not_claim": list(plan.do_not_claim),
        "argument_1": plan.argument_1,
        "argument_2": plan.argument_2,
        "argument_3": plan.argument_3,
        "company_reference": plan.company_reference,
        "opening_strategy": plan.opening_strategy,
        "closing_strategy": plan.closing_strategy,
        "hard_requirements": [h.model_dump(mode="json") for h in plan.hard_requirements],
        "desirable_requirements": [d.model_dump(mode="json") for d in plan.desirable_requirements],
    }
    if contact_claims is not None and hasattr(contact_claims, "to_dict"):
        out["contact_claims"] = contact_claims.to_dict()
    return out
