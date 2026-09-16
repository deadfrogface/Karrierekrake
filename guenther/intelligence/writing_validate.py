"""Writing validators — grounding + hard-req + style rules."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from guenther.contracts import WritingSuggestion
from guenther.intelligence.claims import extract_claims_from_writing
from guenther.intelligence.errors import (
    CAREER_CHANGER_ROLE_CLAIM,
    ROLE_REVERSAL,
    WRONG_COMPANY,
    ValidatorError,
    make_error,
)
from guenther.intelligence.evidence import EvidenceStore, build_evidence_store
from guenther.intelligence.grounding import (
    GroundingStatus,
    ground_claims,
    grounding_errors,
    results_to_dicts,
)
from guenther.intelligence.hard_requirements import (
    evaluate_hard_requirements,
    writing_should_block,
)
from guenther.intelligence.grounding import _fold


@dataclass
class WritingValidationReport:
    ok: bool
    errors: list[ValidatorError] = field(default_factory=list)
    grounding: list[dict[str, Any]] = field(default_factory=list)
    hard_requirements: dict[str, Any] = field(default_factory=dict)
    writing_blocked: bool = False
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "errors": [e.to_dict() for e in self.errors],
            "grounding": self.grounding,
            "hard_requirements": self.hard_requirements,
            "writing_blocked": self.writing_blocked,
            "notes": list(self.notes),
        }


def validate_writing_grounded(
    model: WritingSuggestion,
    *,
    profile_text: str,
    job_text: str,
    existing_evidence: list[dict[str, Any]] | None = None,
    target_company: str | None = None,
    forbid_role_reversal: bool = False,
    forbid_wrong_role: list[str] | None = None,
) -> tuple[WritingSuggestion, WritingValidationReport]:
    store = build_evidence_store(profile_text=profile_text, existing_evidence=existing_evidence)
    claims = extract_claims_from_writing(model.model_dump(mode="json"))
    g_results = ground_claims(
        claims, store=store, profile_text=profile_text, job_text=job_text
    )
    errors = grounding_errors(g_results)

    hard = evaluate_hard_requirements(
        job_text=job_text,
        profile_text=profile_text,
        evidence_corpus=store.corpus(),
    )
    blocked, block_errs = writing_should_block(
        hard, body=model.body or "", subject=model.subject or ""
    )
    errors.extend(block_errs)
    # Hard-req NOT_MET is informational unless the draft claims the credential
    # (otherwise every honest gap letter would infinite-repair).
    if blocked:
        errors.extend(hard.blocking_errors)
    else:
        for e in hard.blocking_errors:
            # Keep as warning note only when not claimed
            e.severity = "warning"
            errors.append(e)

    blob = f"{model.subject or ''}\n{model.body or ''}"
    fold = _fold(blob)
    notes: list[str] = []

    if forbid_role_reversal or True:
        if any(
            p in fold
            for p in (
                "ihre bewerbung",
                "bewerbungsdatei",
                "ihre unterlagen zu pruefen",
                "freue mich ihre bewerbung",
            )
        ):
            errors.append(make_error(ROLE_REVERSAL, claim_text="role_reversal", severity="error"))

    if target_company:
        if _fold(target_company) not in fold and len(model.body or "") > 40:
            errors.append(
                make_error(
                    WRONG_COMPANY,
                    claim_text=target_company,
                    severity="warning",
                )
            )

    for bad in forbid_wrong_role or []:
        if _fold(bad) in fold:
            errors.append(
                make_error(
                    CAREER_CHANGER_ROLE_CLAIM,
                    claim_text=bad,
                    severity="warning",
                )
            )

    # Mark invented if any unsupported credential
    if any(
        e.code in {"UNSUPPORTED_CREDENTIAL", "WRITING_BLOCKED_HARD_REQUIREMENT", "CONTRADICTED_CLAIM"}
        for e in errors
    ):
        model.invented_flag = True
        notes.append("ungrounded_credential_detected")

    # If blocked after detection: sanitize body (fail closed)
    if blocked:
        model.invented_flag = True
        model.body = ""
        model.subject = model.subject or ""
        model.confidence = model.confidence  # keep
        notes.append("writing_blocked_hard_requirement_body_cleared")

    # Drop anchors that aren't in profile
    from guenther.validation import filter_anchors

    model.anchors_used = filter_anchors(
        model.anchors_used, profile_text=profile_text, job_text=job_text
    )

    # Deduplicate errors by code+claim
    uniq: list[ValidatorError] = []
    seen: set[str] = set()
    for e in errors:
        key = f"{e.code}:{e.claim_text}"
        if key in seen:
            continue
        seen.add(key)
        uniq.append(e)

    blocking = blocked or any(e.severity == "block" for e in uniq)
    # ok means no error-severity credential/grounding failures remaining in output
    ok = not blocking and not any(
        e.code
        in {
            "UNSUPPORTED_CREDENTIAL",
            "CONTRADICTED_CLAIM",
            "JOB_REQUIREMENT_USED_AS_EVIDENCE",
            "ROLE_REVERSAL",
        }
        for e in uniq
    )

    report = WritingValidationReport(
        ok=ok,
        errors=uniq,
        grounding=results_to_dicts(g_results),
        hard_requirements=hard.to_dict(),
        writing_blocked=blocking,
        notes=notes,
    )
    return model, report
