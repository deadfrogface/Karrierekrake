"""Orchestrate email → classify → associate → case events."""

from __future__ import annotations

import json
import logging
from typing import Any, Iterable

from core.database import Database
from core.lifecycle import (
    CaseEvent,
    CaseEventType,
    CaseStatus,
    email_category_to_status,
)
from integrations.email_associate import (
    ASSOCIATION_POLICY_VERSION,
    associate_email,
    decide_association_write,
)
from integrations.email_classify import classify_email
from integrations.followup import suggest_follow_ups
from integrations.gmail_sync import ParsedEmail, sender_is_excluded

logger = logging.getLogger("karrierekrake.lifecycle")


def process_parsed_email(
    db: Database,
    email: ParsedEmail | dict[str, Any],
    *,
    exclude_senders: list[str] | None = None,
    auto_status: bool = True,
    min_confidence: float = 0.65,
) -> dict[str, Any]:
    """Classify + associate one email. Ambiguous → review queue."""
    if isinstance(email, ParsedEmail):
        payload = {
            "gmail_id": email.id,
            "thread_id": email.thread_id,
            "subject": email.subject,
            "sender": email.sender,
            "body_text": email.body_text,
            "received_at": email.internal_date,
        }
    else:
        payload = dict(email)

    # Fail-safe dedupe: never emit duplicate lifecycle events for same gmail_id.
    existing_gid = str(payload.get("gmail_id") or "").strip()
    if existing_gid and db.has_gmail_message(existing_gid):
        existing = db.get_email_by_gmail_id(existing_gid) or {}
        return {
            "email_id": existing.get("id") or existing_gid,
            "status": "duplicate",
            "skipped": True,
        }

    sender = payload.get("sender") or ""
    if sender_is_excluded(sender, exclude_senders or []):
        payload.update(
            {
                "category": "noise",
                "confidence": 1.0,
                "association_status": "excluded",
            }
        )
        eid = db.save_email_message(payload)
        return {"email_id": eid, "status": "excluded"}

    classification = classify_email(
        payload.get("subject") or "", payload.get("body_text") or ""
    )
    payload["category"] = classification.category
    payload["confidence"] = classification.confidence

    # Optional Günther second opinion — never overrides false-rejection guard
    # or forces status; stored as advisory metadata only.
    guenther_meta: dict[str, Any] = {}
    try:
        from core.config import load_config
        from guenther.service import get_guenther_service

        cfg = load_config()
        if getattr(cfg.settings, "guenther_enabled", False):
            g = get_guenther_service(
                enabled=True,
                model=getattr(cfg.settings, "guenther_model", "auto") or "auto",
            )
            env = g.suggest_email_class(
                payload.get("subject") or "",
                payload.get("body_text") or "",
                deterministic_category=classification.category,
                deterministic_false_rejection_blocked=classification.false_rejection_blocked,
            )
            if env.ok and env.validated:
                guenther_meta = {
                    "category": env.suggestion.get("category"),
                    "confidence": env.suggestion.get("confidence"),
                    "safety_notes": env.safety_notes,
                    "model_id": env.model_id,
                }
                # Advisory only: never raise confidence to force rejection
                if (
                    classification.false_rejection_blocked
                    or env.suggestion.get("false_rejection_risk")
                ):
                    guenther_meta["status_write_blocked"] = True
    except Exception:
        logger.debug("guenther email assist skipped", exc_info=False)

    cases = [c.to_dict() for c in db.list_cases(limit=2000)]
    proposed = associate_email(
        sender=sender,
        subject=payload.get("subject") or "",
        body=payload.get("body_text") or "",
        cases=cases,
        thread_id=payload.get("thread_id") or "",
        message_id=payload.get("message_id") or payload.get("gmail_id") or "",
    )

    # Protect confirmed associations on re-ingest (no silent overwrite / cross-case mutation).
    existing = None
    gmail_key = payload.get("gmail_id") or ""
    if gmail_key:
        existing = db.get_email_message(gmail_key)
    if existing and (
        int(existing.get("association_confirmed") or 0)
        or (
            (existing.get("association_status") or "") == "linked"
            and existing.get("case_id")
            and int(existing.get("association_confirmed") or 0)
        )
    ):
        assoc = decide_association_write(
            existing_status=str(existing.get("association_status") or ""),
            existing_case_id=str(existing.get("case_id") or ""),
            existing_confirmed=bool(int(existing.get("association_confirmed") or 0)),
            existing_policy_version=str(existing.get("association_policy_version") or ""),
            proposed=proposed,
        )
    else:
        assoc = proposed

    if guenther_meta:
        payload["guenther"] = guenther_meta

    payload["association_policy_version"] = assoc.policy_version or ASSOCIATION_POLICY_VERSION
    payload["association_explanation"] = assoc.explanation or assoc.reason
    payload["association_evidence_json"] = list(assoc.evidence)

    if assoc.match_status == "protected" and existing:
        # Keep confirmed link; do not mutate case status from this pass.
        payload["case_id"] = existing.get("case_id") or ""
        payload["association_status"] = "linked"
        payload["association_confirmed"] = 1
        eid = db.save_email_message(payload)
        return {
            "email_id": eid,
            "status": "protected",
            "case_id": payload["case_id"],
            "category": classification.category,
            "confidence": classification.confidence,
            "false_rejection_blocked": classification.false_rejection_blocked,
            "association_reason": assoc.reason,
            "policy_version": assoc.policy_version,
        }

    if assoc.ambiguous or not assoc.case_id:
        status = assoc.match_status if assoc.match_status in {"ambiguous", "review_required"} else (
            "ambiguous" if assoc.candidates or assoc.ambiguous else "unlinked"
        )
        payload["association_status"] = status
        payload["case_id"] = ""
        eid = db.save_email_message(payload)
        if assoc.candidates:
            for cid in assoc.candidates[:3]:
                db.add_case_event(
                    CaseEvent(
                        case_id=cid,
                        event_type=CaseEventType.EMAIL_AMBIGUOUS.value,
                        payload_json=json.dumps(
                            {
                                "email_id": eid,
                                "reason": assoc.reason,
                                "candidates": list(assoc.candidates),
                                "explanation": assoc.explanation,
                                "policy_version": assoc.policy_version,
                                "evidence": list(assoc.evidence),
                            },
                            ensure_ascii=False,
                        ),
                        confidence=assoc.confidence,
                    )
                )
        return {
            "email_id": eid,
            "status": payload["association_status"],
            "category": classification.category,
            "confidence": classification.confidence,
            "false_rejection_blocked": classification.false_rejection_blocked,
            "candidates": list(assoc.candidates),
            "association_reason": assoc.reason,
            "policy_version": assoc.policy_version,
        }

    payload["case_id"] = assoc.case_id
    payload["association_status"] = "linked"
    eid = db.save_email_message(payload)
    db.add_case_event(
        CaseEvent(
            case_id=assoc.case_id,
            event_type=CaseEventType.EMAIL_LINKED.value,
            payload_json=json.dumps(
                {
                    "email_id": eid,
                    "category": classification.category,
                    "confidence": classification.confidence,
                    "association_confidence": assoc.confidence,
                    "explanation": assoc.explanation,
                    "evidence": list(assoc.evidence),
                    "policy_version": assoc.policy_version,
                },
                ensure_ascii=False,
            ),
            confidence=classification.confidence,
        )
    )

    if (
        auto_status
        and classification.confidence >= min_confidence
        and not classification.false_rejection_blocked
    ):
        new_status = email_category_to_status(classification.category)
        if new_status:
            db.set_case_status(
                assoc.case_id,
                new_status,
                confidence=classification.confidence,
                payload={"source": "email", "email_id": eid},
            )

    return {
        "email_id": eid,
        "status": "linked",
        "case_id": assoc.case_id,
        "category": classification.category,
        "confidence": classification.confidence,
        "false_rejection_blocked": classification.false_rejection_blocked,
        "association_reason": assoc.reason,
        "policy_version": assoc.policy_version,
    }


def process_email_batch(
    db: Database,
    emails: Iterable[ParsedEmail | dict[str, Any]],
    *,
    exclude_senders: list[str] | None = None,
) -> list[dict[str, Any]]:
    return [
        process_parsed_email(db, e, exclude_senders=exclude_senders) for e in emails
    ]


def refresh_follow_up_tasks(db: Database, *, follow_up_days: int = 14, ghosted_days: int = 21) -> int:
    cases = [c.to_dict() for c in db.list_cases(limit=2000)]
    suggestions = suggest_follow_ups(
        cases, follow_up_days=follow_up_days, ghosted_days=ghosted_days
    )
    created = 0
    for s in suggestions:
        assert s.auto_send is False
        db.save_lifecycle_task(
            {
                "case_id": s.case_id,
                "kind": s.kind,
                "title": "Ghosting-Hinweis" if s.kind == "ghosted" else "Nachfassen",
                "body": s.text,
                "status": "open",
                "auto_send": False,
            }
        )
        db.add_case_event(
            CaseEvent(
                case_id=s.case_id,
                event_type=CaseEventType.FOLLOW_UP_SUGGESTED.value,
                payload_json=json.dumps({"kind": s.kind, "text": s.text}, ensure_ascii=False),
            )
        )
        if s.kind == "ghosted":
            case = db.get_case(s.case_id)
            if case and case.status in {
                CaseStatus.APPLIED.value,
                CaseStatus.CONFIRMATION.value,
            }:
                db.set_case_status(s.case_id, CaseStatus.GHOSTED.value, force=False)
        created += 1
    return created
