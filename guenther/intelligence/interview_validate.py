"""Interview prep validators — empty TPS on supported cases must repair."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from guenther.contracts import InterviewPrepSuggestion
from guenther.intelligence.claims import extract_claims_from_interview
from guenther.intelligence.errors import (
    EMPTY_INTERVIEW_QUESTIONS,
    EMPTY_TALKING_POINTS,
    UNSUPPORTED_CREDENTIAL,
    ValidatorError,
    make_error,
)
from guenther.intelligence.evidence import build_evidence_store
from guenther.intelligence.grounding import (
    GroundingStatus,
    ground_claims,
    grounding_errors,
    results_to_dicts,
)
from guenther.validation import claim_supported_by_corpus, filter_anchors


@dataclass
class InterviewValidationReport:
    ok: bool
    errors: list[ValidatorError] = field(default_factory=list)
    grounding: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    has_direct_evidence: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "errors": [e.to_dict() for e in self.errors],
            "grounding": self.grounding,
            "notes": list(self.notes),
            "has_direct_evidence": self.has_direct_evidence,
        }


def _has_direct_support(evidence: list[dict[str, Any]] | None) -> bool:
    for e in evidence or []:
        if str(e.get("support") or "").upper() == "DIRECT":
            return True
    return False


def validate_interview_grounded(
    model: InterviewPrepSuggestion,
    *,
    profile_text: str,
    job_text: str,
    evidence: list[dict[str, Any]] | None = None,
) -> tuple[InterviewPrepSuggestion, InterviewValidationReport]:
    store = build_evidence_store(profile_text=profile_text, existing_evidence=evidence)
    claims = extract_claims_from_interview(model.model_dump(mode="json"))
    g_results = ground_claims(claims, store=store, profile_text=profile_text, job_text=job_text)
    errors = grounding_errors(g_results)
    notes: list[str] = []

    # Drop ungrounded talking points
    corpus = f"{profile_text}\n{store.corpus()}\n{job_text}"
    grounded_tps = [
        tp for tp in model.talking_points if claim_supported_by_corpus(tp, corpus)
    ]
    if len(grounded_tps) < len(model.talking_points):
        notes.append("ungrounded_talking_points_dropped")
        model.invented_flag = True
    model.talking_points = grounded_tps

    # Remove talking points that assert unsupported credentials
    cleaned_tps = []
    for tp in model.talking_points:
        sub = extract_claims_from_interview({"talking_points": [tp]})
        bad = False
        for c in sub:
            gr = ground_claims([c], store=store, profile_text=profile_text, job_text=job_text)
            if gr and gr[0].status in {
                GroundingStatus.UNSUPPORTED,
                GroundingStatus.CONTRADICTED,
            }:
                bad = True
                errors.append(
                    make_error(
                        UNSUPPORTED_CREDENTIAL if c.requires_direct or c.kind.value == "credential" else "UNSUPPORTED_CLAIM",
                        claim_text=c.text,
                        severity="error",
                    )
                )
        if not bad:
            cleaned_tps.append(tp)
    model.talking_points = cleaned_tps

    has_direct = _has_direct_support(evidence) or bool(store.items)
    if has_direct and not model.talking_points and not model.questions:
        # Empty productive output despite evidence → repair
        if model.gap_notes:
            errors.append(make_error(EMPTY_TALKING_POINTS, severity="error"))
            notes.append("empty_tps_with_gaps_only")
        else:
            errors.append(make_error(EMPTY_TALKING_POINTS, severity="error"))
            errors.append(make_error(EMPTY_INTERVIEW_QUESTIONS, severity="error"))
    elif has_direct and not model.talking_points:
        errors.append(make_error(EMPTY_TALKING_POINTS, severity="error"))
    elif has_direct and not model.questions:
        errors.append(make_error(EMPTY_INTERVIEW_QUESTIONS, severity="warning"))

    model.anchors_used = filter_anchors(
        model.anchors_used,
        profile_text=profile_text,
        job_text=job_text,
        evidence_text=store.corpus(),
    )

    uniq: list[ValidatorError] = []
    seen: set[str] = set()
    for e in errors:
        key = f"{e.code}:{e.claim_text}"
        if key in seen:
            continue
        seen.add(key)
        uniq.append(e)

    ok = not any(e.severity == "error" for e in uniq)
    if not ok:
        model.confidence = model.confidence

    return model, InterviewValidationReport(
        ok=ok,
        errors=uniq,
        grounding=results_to_dicts(g_results),
        notes=notes,
        has_direct_evidence=has_direct,
    )
