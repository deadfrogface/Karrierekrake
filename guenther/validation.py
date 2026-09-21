"""Validate untrusted LLM output — fail closed, claim guards, manual wins."""

from __future__ import annotations

import json
import re
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from guenther.contracts import (
    SCHEMA_BY_NAME,
    AssociationSuggestion,
    ClaimAnchor,
    ConfidenceLevel,
    CVExtractSuggestion,
    EmailClassSuggestion,
    EvidenceAssistSuggestion,
    EvidenceSupport,
    GuentherEnvelope,
    InterviewPrepSuggestion,
    JobAnalysisSuggestion,
    WritingSuggestion,
)

T = TypeVar("T", bound=BaseModel)

_JSON_FENCE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)
_THINK_BLOCK = re.compile(r"<think>[\s\S]*?</think>", re.IGNORECASE)


def extract_json_object(text: str) -> dict[str, Any] | None:
    """Best-effort JSON object extraction from model text (still untrusted)."""
    raw = (text or "").strip()
    if not raw:
        return None
    # Qwen3 and similar models may emit chain-of-thought before JSON.
    raw = _THINK_BLOCK.sub("", raw).strip()
    m = _JSON_FENCE.search(raw)
    if m:
        raw = m.group(1).strip()
    # Find outermost object
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        return None
    chunk = raw[start : end + 1]
    try:
        data = json.loads(chunk)
    except json.JSONDecodeError:
        # Trailing commas / minor repair for live small models
        repaired = re.sub(r",\s*}", "}", chunk)
        repaired = re.sub(r",\s*]", "]", repaired)
        try:
            data = json.loads(repaired)
        except json.JSONDecodeError:
            return None
    return data if isinstance(data, dict) else None


def parse_contract(schema_name: str, payload: dict[str, Any] | str | None) -> BaseModel | None:
    cls = SCHEMA_BY_NAME.get(schema_name)
    if cls is None or payload is None:
        return None
    if isinstance(payload, str):
        obj = extract_json_object(payload)
        if obj is None:
            return None
        payload = obj
    if not isinstance(payload, dict):
        return None
    # Soft-normalize common model quirks before strict validation.
    data = dict(payload)
    conf = data.get("confidence")
    if isinstance(conf, str):
        data["confidence"] = conf.strip().lower()
    if isinstance(data.get("support"), str):
        data["support"] = data["support"].strip().upper()
    # Association coercions
    if schema_name == "association":
        if data.get("case_id") == "":
            data["case_id"] = None
        if isinstance(data.get("reason"), str) and len(data["reason"]) > 400:
            data["reason"] = data["reason"][:400]
        cands = data.get("candidate_case_ids")
        if isinstance(cands, list):
            data["candidate_case_ids"] = [str(c) for c in cands if c][:8]
        if data.get("ambiguous") is True or not data.get("case_id"):
            data.setdefault("match_status", "ambiguous" if data.get("ambiguous") else "no_safe_match")
        # Drop unknown keys for association to avoid extra=forbid failures
        allowed = {
            "case_id",
            "confidence",
            "ambiguous",
            "candidate_case_ids",
            "reason",
            "match_status",
        }
        data = {k: v for k, v in data.items() if k in allowed}
    if schema_name == "email_class":
        allowed_email = {
            "category",
            "confidence",
            "reasons",
            "false_rejection_risk",
            "evidence",
        }
        if isinstance(data.get("category"), str):
            data["category"] = data["category"].strip().lower().replace(" ", "_")
            # Map unknown labels into review
            known = {
                "confirmation",
                "interview",
                "interview_cancelled",
                "offer",
                "rejection",
                "assessment",
                "document_request",
                "employer_question",
                "recruiter_outreach",
                "noise",
                "other",
                "ghosted",
                "review",
            }
            if data["category"] not in known:
                data["category"] = "review"
        data = {k: v for k, v in data.items() if k in allowed_email}
    # Coerce bare string anchors → ClaimAnchor dicts
    if isinstance(data.get("anchors_used"), list):
        data["anchors_used"] = [
            {"text": a, "source": "profile"} if isinstance(a, str) else a
            for a in data["anchors_used"]
        ]
    if "items" in data and isinstance(data["items"], list):
        fixed_items = []
        for item in data["items"]:
            if isinstance(item, dict):
                it = dict(item)
                if isinstance(it.get("support"), str):
                    it["support"] = it["support"].strip().upper()
                if isinstance(it.get("confidence"), str):
                    it["confidence"] = it["confidence"].strip().lower()
                if isinstance(it.get("anchors"), list):
                    it["anchors"] = [
                        {"text": a, "source": "evidence"} if isinstance(a, str) else a
                        for a in it["anchors"]
                    ]
                fixed_items.append(it)
            else:
                fixed_items.append(item)
        data["items"] = fixed_items
    try:
        return cls.model_validate(data)
    except ValidationError:
        return None


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


def _token_set(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-zA-ZäöüÄÖÜß0-9]{3,}", _norm(text))}


def claim_supported_by_corpus(claim: str, corpus: str, *, min_overlap: int = 1) -> bool:
    """True if claim tokens appear in trusted corpus (profile/job/email/evidence)."""
    c = _token_set(claim)
    if not c:
        return False
    body = _token_set(corpus)
    return len(c & body) >= min_overlap


def filter_anchors(
    anchors: list[ClaimAnchor],
    *,
    profile_text: str = "",
    job_text: str = "",
    email_text: str = "",
    evidence_text: str = "",
    manual_text: str = "",
) -> list[ClaimAnchor]:
    allowed: list[ClaimAnchor] = []
    corpora = {
        "profile": profile_text,
        "cv": profile_text,
        "job": job_text,
        "email": email_text,
        "evidence": evidence_text,
        "manual": manual_text or profile_text,
    }
    for a in anchors:
        corpus = corpora.get(a.source, "")
        quote = a.quote or a.text
        if claim_supported_by_corpus(quote, corpus) or (
            a.quote and _norm(a.quote) and _norm(a.quote) in _norm(corpus)
        ):
            allowed.append(a)
    return allowed


def demote_high_confidence(level: ConfidenceLevel, *, ok: bool) -> ConfidenceLevel:
    if not ok:
        return ConfidenceLevel.LOW
    return level


def validate_cv_extract(
    model: CVExtractSuggestion,
    *,
    cv_text: str,
    manual_profile: dict[str, Any] | None = None,
) -> tuple[CVExtractSuggestion, list[str]]:
    """Ground every claim in CV text. Ungrounded → DROP. Manual profile wins."""
    notes: list[str] = []
    manual = manual_profile or {}
    # Manual data wins — overwrite non-empty manual fields
    if manual.get("full_name"):
        model.full_name = str(manual["full_name"])
        notes.append("manual_name_wins")

    def _ground_list(values: list[str], *, kind: str) -> list[str]:
        kept: list[str] = []
        dropped = 0
        for v in values:
            if claim_supported_by_corpus(v, cv_text):
                kept.append(v)
            else:
                dropped += 1
        if dropped:
            notes.append(f"ungrounded_{kind}_dropped")
            model.invented_flag = True
        return kept

    model.skills = _ground_list(list(model.skills), kind="skills")
    model.experience_titles = _ground_list(
        list(model.experience_titles), kind="experience_titles"
    )
    model.education = _ground_list(list(model.education), kind="education")
    model.certificates = _ground_list(list(model.certificates), kind="certificates")
    model.languages = _ground_list(list(model.languages), kind="languages")
    # emails / phones must also appear in CV (or manual)
    grounded_emails = []
    for e in model.emails:
        if manual.get("email") and e == manual.get("email"):
            grounded_emails.append(e)
        elif claim_supported_by_corpus(e, cv_text):
            grounded_emails.append(e)
        else:
            notes.append("ungrounded_email_dropped")
            model.invented_flag = True
    model.emails = grounded_emails
    grounded_phones = []
    for p in model.phones:
        if claim_supported_by_corpus(p, cv_text) or _norm(p) in _norm(cv_text):
            grounded_phones.append(p)
        else:
            notes.append("ungrounded_phone_dropped")
            model.invented_flag = True
    model.phones = grounded_phones
    if model.full_name and not manual.get("full_name"):
        if not claim_supported_by_corpus(model.full_name, cv_text):
            notes.append("ungrounded_name_dropped")
            model.full_name = ""
            model.invented_flag = True
    if model.invented_flag:
        model.confidence = ConfidenceLevel.LOW
    return model, notes


def validate_job_analysis(
    model: JobAnalysisSuggestion, *, job_text: str
) -> tuple[JobAnalysisSuggestion, list[str]]:
    notes: list[str] = []
    kept = []
    for item in model.requirements:
        if claim_supported_by_corpus(item.requirement, job_text):
            kept.append(item)
        else:
            notes.append("ungrounded_requirement_dropped")
    model.requirements = kept
    if notes:
        model.confidence = ConfidenceLevel.LOW
    return model, notes


def validate_evidence_assist(
    model: EvidenceAssistSuggestion,
    *,
    profile_text: str,
    job_text: str,
    existing_evidence: list[dict[str, Any]] | None = None,
) -> tuple[EvidenceAssistSuggestion, list[str]]:
    """Never upgrade NOT_SUPPORTED → DIRECT without profile tokens.

    JOB REQUIREMENT ≠ CANDIDATE EVIDENCE. Aliases supported via token fold.
    """
    notes: list[str] = []
    existing = {
        _norm(str(e.get("claim") or e.get("requirement") or "")): str(
            e.get("support") or e.get("level") or ""
        ).upper()
        for e in (existing_evidence or [])
    }
    job_tokens = _token_set(job_text)
    profile_tokens = _token_set(profile_text)
    cleaned: list = []
    for item in model.items:
        key = _norm(item.claim)
        prior = existing.get(key)
        if prior == "NOT_SUPPORTED" and item.support == EvidenceSupport.DIRECT:
            item.support = EvidenceSupport.NOT_SUPPORTED
            notes.append("blocked_unsupported_to_direct")
        claim_tokens = _token_set(item.claim)
        # Demote DIRECT when claim is only present in JOB, not PROFILE
        if (
            item.support == EvidenceSupport.DIRECT
            and claim_tokens
            and claim_tokens <= job_tokens
            and not (claim_tokens & profile_tokens)
        ):
            item.support = EvidenceSupport.NOT_SUPPORTED
            notes.append("job_requirement_not_candidate_evidence")
        if item.support == EvidenceSupport.DIRECT and not claim_supported_by_corpus(
            item.claim, profile_text
        ):
            overlap = claim_tokens & profile_tokens
            if overlap:
                item.support = EvidenceSupport.RELATED
                notes.append("direct_partial_demoted_related")
            else:
                item.support = EvidenceSupport.NOT_SUPPORTED
                notes.append("direct_without_profile_demoted")
        # Credential-like claims need profile tokens; related admin ≠ Pflegeausbildung
        low = key
        if any(x in low for x in ("pflegeausbildung", "bachelor", "master", "examen")):
            if not claim_supported_by_corpus(item.claim, profile_text, min_overlap=1):
                item.support = EvidenceSupport.NOT_SUPPORTED
                notes.append("credential_direct_without_profile")
            elif "pflege" in low and "pflegeausbildung" not in _norm(
                profile_text
            ) and "pflegefach" not in _norm(profile_text):
                item.support = EvidenceSupport.NOT_SUPPORTED
                notes.append("pflege_credential_not_supported")
        item.anchors = filter_anchors(
            item.anchors, profile_text=profile_text, job_text=job_text, evidence_text=profile_text
        )
        cleaned.append(item)
    model.items = cleaned
    if notes:
        model.confidence = ConfidenceLevel.LOW
    return model, notes


def validate_email_class(
    model: EmailClassSuggestion,
    *,
    deterministic_category: str | None = None,
    deterministic_false_rejection_blocked: bool = False,
    deterministic_confidence: float = 0.0,
    deterministic_evidence: tuple[str, ...] | list[str] | None = None,
    email_text: str = "",
) -> tuple[EmailClassSuggestion, list[str]]:
    """Merge LLM suggestion with deterministic classify — fail closed on high impact.

    Asymmetric rules:
    - LLM must not demote a solid deterministic confirmation/interview to noise/other.
    - LLM must not invent rejection/offer/interview_cancelled without deterministic agreement.
    - Instruction-frame / review from deterministic blocks all high-impact LLM labels.
    - Uncertain → review (or other) with low confidence.
    """
    notes: list[str] = []
    det = (deterministic_category or "").strip() or None
    det_ev = tuple(deterministic_evidence or ())
    high_impact = {"rejection", "offer", "interview_cancelled"}
    solid_det = {
        "confirmation",
        "interview",
        "offer",
        "rejection",
        "assessment",
        "interview_cancelled",
        "document_request",
        "employer_question",
        "recruiter_outreach",
    }
    instr_blocked = any(
        str(x).startswith("instruction_frame") or str(x) == "instruction_frame_blocked"
        for x in det_ev
    ) or (det == "review" and any("instruction" in str(x) for x in det_ev))

    if deterministic_false_rejection_blocked and model.category == "rejection":
        model.category = det if det and det != "rejection" else "review"
        model.false_rejection_risk = True
        model.confidence = ConfidenceLevel.LOW
        notes.append("false_rejection_guard")

    # Prefer solid deterministic hiring signals over LLM soft demotion / wrong soft labels.
    if (
        det in solid_det
        and deterministic_confidence >= 0.55
        and det not in high_impact
        and model.category != det
        and model.category not in high_impact
    ):
        # Do not let LLM replace confirmation/interview/etc. with unrelated categories
        model.category = det  # type: ignore[assignment]
        model.confidence = (
            ConfidenceLevel.MEDIUM if deterministic_confidence >= 0.7 else ConfidenceLevel.LOW
        )
        if det_ev:
            model.evidence = [e for e in det_ev if "instruction" not in str(e)][:8] or list(det_ev)[
                :8
            ]
            model.reasons = list(model.evidence)[:8]
        notes.append("deterministic_signal_preferred")

    # High-impact: require deterministic agreement (asymmetric — false positives worse)
    if model.category in high_impact:
        if instr_blocked or det == "review":
            was_rejection = model.category == "rejection"
            notes.append("instruction_or_review_blocks_high_impact")
            model.category = "review"  # type: ignore[assignment]
            model.confidence = ConfidenceLevel.LOW
            if was_rejection:
                model.false_rejection_risk = True
        elif det != model.category:
            # LLM invented high-impact that deterministic did not support
            notes.append("high_impact_without_deterministic_agreement")
            was_rejection = model.category == "rejection"
            model.category = "review"  # type: ignore[assignment]
            model.confidence = ConfidenceLevel.LOW
            if was_rejection:
                model.false_rejection_risk = True
        else:
            # det agrees — attach deterministic evidence
            if det_ev:
                model.evidence = list(det_ev)[:8]
                notes.append("high_impact_from_deterministic_evidence")
            elif not (model.evidence or model.reasons):
                notes.append("high_impact_without_grounded_evidence")
                was_rejection = model.category == "rejection"
                model.category = "review"  # type: ignore[assignment]
                model.confidence = ConfidenceLevel.LOW
                if was_rejection:
                    model.false_rejection_risk = True

    # Deterministic review wins over any remaining LLM high-impact
    if det == "review" and model.category in high_impact:
        was_rejection = model.category == "rejection"
        model.category = "review"  # type: ignore[assignment]
        model.confidence = ConfidenceLevel.LOW
        if was_rejection:
            model.false_rejection_risk = True
        notes.append("deterministic_review_blocks_high_impact")

    # After blocking a bogus high-impact, restore solid non-high-impact deterministic label
    if (
        det in solid_det
        and det not in high_impact
        and deterministic_confidence >= 0.55
        and model.category == "review"
        and "high_impact_without_deterministic_agreement" in notes
    ):
        model.category = det  # type: ignore[assignment]
        model.confidence = (
            ConfidenceLevel.MEDIUM if deterministic_confidence >= 0.7 else ConfidenceLevel.LOW
        )
        if det_ev:
            model.evidence = list(det_ev)[:8]
            model.reasons = list(det_ev)[:8]
        notes.append("restored_det_after_blocked_high_impact")

    if model.confidence == ConfidenceLevel.HIGH and model.category in {
        "other",
        "noise",
        "review",
    }:
        model.confidence = ConfidenceLevel.LOW
        notes.append("high_confidence_demoted_for_weak_category")

    return model, notes


def validate_association(
    model: AssociationSuggestion,
    *,
    known_case_ids: set[str] | None = None,
    deterministic_ambiguous: bool = False,
    deterministic_case_id: str | None = None,
    deterministic_candidates: tuple[str, ...] | list[str] | None = None,
    deterministic_reason: str = "",
) -> tuple[AssociationSuggestion, list[str]]:
    """Fail closed: ambiguous or unknown case_id → no HIGH confidence silent link."""
    notes: list[str] = []
    known = known_case_ids or set()

    if model.case_id == "":
        model.case_id = None
    if model.case_id and model.case_id not in known:
        notes.append("unknown_case_id")
        model.case_id = None
        model.ambiguous = True
        model.confidence = ConfidenceLevel.LOW
        model.match_status = "no_safe_match"

    if deterministic_ambiguous:
        model.ambiguous = True
        model.confidence = ConfidenceLevel.LOW
        model.case_id = None
        model.match_status = "ambiguous"
        if deterministic_candidates:
            model.candidate_case_ids = [c for c in deterministic_candidates if c][:8]
        if deterministic_reason and not model.reason:
            model.reason = deterministic_reason[:400]
        notes.append("deterministic_ambiguous_wins")

    if model.ambiguous or not model.case_id:
        if model.confidence == ConfidenceLevel.HIGH:
            notes.append("blocked_high_confidence_ambiguous")
        model.confidence = ConfidenceLevel.LOW
        if model.ambiguous:
            model.case_id = None
            if model.match_status == "linked":
                model.match_status = "ambiguous"
        elif not model.case_id:
            model.match_status = model.match_status if model.match_status != "linked" else "no_safe_match"
    else:
        # Linked only when not ambiguous and case known
        model.match_status = "linked"
        model.ambiguous = False

    # Deterministic unambiguous link preferred when LLM disagrees weakly
    if deterministic_case_id and not deterministic_ambiguous:
        if not model.case_id or model.ambiguous:
            model.case_id = deterministic_case_id
            model.ambiguous = False
            model.match_status = "linked"
            model.confidence = ConfidenceLevel.MEDIUM
            notes.append("deterministic_link_applied")

    return model, notes


def validate_writing(
    model: WritingSuggestion,
    *,
    profile_text: str,
    job_text: str,
    allowed_facts: list[str] | None = None,
) -> tuple[WritingSuggestion, list[str]]:
    notes: list[str] = []
    corpus = f"{profile_text}\n{job_text}\n" + "\n".join(allowed_facts or [])
    model.anchors_used = filter_anchors(
        model.anchors_used, profile_text=profile_text, job_text=job_text, manual_text=corpus
    )
    # Heuristic: employer/degree-like invented phrases — if body mentions
    # tokens that look like companies not in corpus, flag (lightweight).
    body_tokens = _token_set(model.body)
    corpus_tokens = _token_set(corpus)
    suspicious = {
        t
        for t in body_tokens
        if len(t) >= 6 and t not in corpus_tokens and t[0].isalpha()
    }
    # Only flag if many novel long tokens (avoid false positives on glue)
    if len(suspicious) >= 8:
        model.invented_flag = True
        model.confidence = ConfidenceLevel.LOW
        notes.append("possible_invented_facts")
    return model, notes


def validate_interview_prep(
    model: InterviewPrepSuggestion,
    *,
    profile_text: str,
    job_text: str,
    evidence_text: str,
) -> tuple[InterviewPrepSuggestion, list[str]]:
    notes: list[str] = []
    model.anchors_used = filter_anchors(
        model.anchors_used,
        profile_text=profile_text,
        job_text=job_text,
        evidence_text=evidence_text,
    )
    # Talking points must be grounded
    grounded = [
        tp
        for tp in model.talking_points
        if claim_supported_by_corpus(tp, f"{profile_text}\n{evidence_text}\n{job_text}")
    ]
    if len(grounded) < len(model.talking_points):
        notes.append("ungrounded_talking_points_dropped")
        model.invented_flag = True
        model.confidence = ConfidenceLevel.LOW
    model.talking_points = grounded
    return model, notes


def envelope_from_model(
    *,
    capability: str,
    model: BaseModel | None,
    ok: bool,
    fallback_reason: str = "",
    provider_status: str = "",
    model_id: str = "",
    safety_notes: list[str] | None = None,
    validated: bool = False,
    architecture: str = "",
    validator_errors: list[dict[str, Any]] | None = None,
    repair_history: dict[str, Any] | None = None,
    grounding_report: dict[str, Any] | None = None,
) -> GuentherEnvelope:
    return GuentherEnvelope(
        ok=ok and model is not None,
        capability=capability,
        suggestion=model.model_dump(mode="json") if model is not None else {},
        fallback_reason=fallback_reason,
        provider_status=provider_status,
        model_id=model_id,
        validated=validated,
        safety_notes=list(safety_notes or []),
        architecture=architecture or "",
        validator_errors=list(validator_errors or [])[:40],
        repair_history=dict(repair_history or {}),
        grounding_report=dict(grounding_report or {}),
    )
