"""Shared mobile contract adapters — Python domain ↔ versioned JSON.

Does not invent a sync backend. Round-trips must preserve semantics for known
fields; unknown JSON keys are preserved on the wire but stripped when loading
into strict domain objects (forward/backward compatible).
"""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from core.config import ApplicationProfile
from core.lifecycle import ApplicationCase, LifecycleEvent
from core.models import Job
from core.search_intent import SearchIntent, parse_search_intent
from guenther.contracts import GuentherEnvelope
from integrations.calendar_scheduling import SchedulingProposal
from integrations.reply_draft import ReplyDraft

CONTRACTS_ROOT = Path(__file__).resolve().parents[1] / "contracts"
SCHEMAS_V1 = CONTRACTS_ROOT / "schemas" / "v1"
FIXTURES_V1 = CONTRACTS_ROOT / "fixtures" / "v1"
BUNDLE_VERSION = (CONTRACTS_ROOT / "VERSION").read_text(encoding="utf-8").strip()

SCHEMA_IDS = {
    "profile": "karrierekrake.profile",
    "search_intent": "karrierekrake.search_intent",
    "job": "karrierekrake.job",
    "application_case": "karrierekrake.application_case",
    "lifecycle_event": "karrierekrake.lifecycle_event",
    "calendar_proposal": "karrierekrake.calendar_proposal",
    "reply_draft": "karrierekrake.reply_draft",
    "guenther_result": "karrierekrake.guenther_result",
}


def _envelope(schema_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    out = dict(payload)
    out.setdefault("contract_version", BUNDLE_VERSION)
    out["schema_id"] = SCHEMA_IDS[schema_key]
    return out


def _strip_none_for_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _strip_none_for_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_strip_none_for_json(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value


# --- serializers -----------------------------------------------------------------


def profile_to_contract(profile: ApplicationProfile) -> dict[str, Any]:
    data = asdict(profile)
    return _envelope("profile", data)


def profile_from_contract(data: dict[str, Any]) -> ApplicationProfile:
    known = {f.name for f in ApplicationProfile.__dataclass_fields__.values()}  # type: ignore[attr-defined]
    filtered = {k: v for k, v in data.items() if k in known}
    return ApplicationProfile(**filtered)


def search_intent_to_contract(intent: SearchIntent) -> dict[str, Any]:
    data = intent.model_dump(mode="json")
    return _envelope("search_intent", data)


def search_intent_from_contract(data: dict[str, Any]) -> SearchIntent:
    raw = {k: v for k, v in data.items() if k not in {"contract_version", "schema_id"}}
    return parse_search_intent(raw)


def job_to_contract(job: Job) -> dict[str, Any]:
    return _envelope("job", job.to_dict())


def job_from_contract(data: dict[str, Any]) -> Job:
    raw = {k: v for k, v in data.items() if k not in {"contract_version", "schema_id"}}
    return Job.from_dict(raw)


def application_case_to_contract(case: ApplicationCase) -> dict[str, Any]:
    return _envelope("application_case", case.to_dict())


def application_case_from_contract(data: dict[str, Any]) -> ApplicationCase:
    raw = {k: v for k, v in data.items() if k not in {"contract_version", "schema_id"}}
    return ApplicationCase.from_dict(raw)


def lifecycle_event_to_contract(event: LifecycleEvent) -> dict[str, Any]:
    data = {
        "id": event.id,
        "case_id": event.case_id,
        "event_type": event.event_type,
        "occurred_at": event.occurred_at,
        "recorded_at": event.recorded_at,
        "idempotency_key": event.idempotency_key,
        "payload": dict(event.payload or {}),
        "source": event.source,
        "confidence": float(event.confidence),
    }
    return _envelope("lifecycle_event", data)


def lifecycle_event_from_contract(data: dict[str, Any]) -> LifecycleEvent:
    return LifecycleEvent(
        event_type=str(data.get("event_type") or ""),
        occurred_at=str(data.get("occurred_at") or ""),
        idempotency_key=str(data.get("idempotency_key") or ""),
        payload=dict(data.get("payload") or {}),
        id=str(data.get("id") or ""),
        case_id=str(data.get("case_id") or ""),
        recorded_at=str(data.get("recorded_at") or ""),
        source=str(data.get("source") or ""),
        confidence=float(data.get("confidence") or 0),
    )


def calendar_proposal_to_contract(proposal: SchedulingProposal) -> dict[str, Any]:
    return _envelope("calendar_proposal", proposal.to_dict())


def calendar_proposal_from_contract(data: dict[str, Any]) -> SchedulingProposal:
    raw = {k: v for k, v in data.items() if k not in {"contract_version", "schema_id"}}
    # lifecycle_event_hint is wire-only; SchedulingProposal.from_dict ignores extras
    raw.pop("lifecycle_event_hint", None)
    return SchedulingProposal.from_dict(raw)


def reply_draft_to_contract(draft: ReplyDraft) -> dict[str, Any]:
    data = {
        "case_id": draft.case_id,
        "action": draft.action,
        "to_address": draft.to_address,
        "subject": draft.subject,
        "body": draft.body,
        "created_at": draft.created_at,
        "approved": bool(draft.approved),
        "binding_review_approved": bool(draft.binding_review_approved),
        "sent": bool(draft.sent),
        "send_error": draft.send_error,
        "draft_only": bool(draft.draft_only),
        "auto_send": False,  # product invariant
        "requires_explicit_review": bool(draft.requires_explicit_review),
        "blocking_reasons": list(draft.blocking_reasons or []),
        "used_facts": list(draft.used_facts or []),
    }
    return _envelope("reply_draft", data)


def reply_draft_from_contract(data: dict[str, Any]) -> ReplyDraft:
    draft = ReplyDraft(
        case_id=str(data.get("case_id") or ""),
        action=str(data.get("action") or "GENERAL_REPLY"),
        to_address=str(data.get("to_address") or ""),
        subject=str(data.get("subject") or ""),
        body=str(data.get("body") or ""),
        created_at=str(data.get("created_at") or ""),
        approved=bool(data.get("approved")),
        binding_review_approved=bool(data.get("binding_review_approved")),
        sent=bool(data.get("sent")),
        send_error=str(data.get("send_error") or ""),
        draft_only=bool(data.get("draft_only", True)),
        auto_send=False,
        requires_explicit_review=bool(data.get("requires_explicit_review")),
        blocking_reasons=list(data.get("blocking_reasons") or []),
        used_facts=list(data.get("used_facts") or []),
    )
    draft.auto_send = False
    return draft


def guenther_result_to_contract(envelope: GuentherEnvelope) -> dict[str, Any]:
    data = envelope.model_dump(mode="json")
    return _envelope("guenther_result", data)


def guenther_result_from_contract(data: dict[str, Any]) -> GuentherEnvelope:
    raw = {k: v for k, v in data.items() if k not in {"contract_version", "schema_id"}}
    return GuentherEnvelope.model_validate(raw)


SERIALIZERS: dict[str, Callable[[Any], dict[str, Any]]] = {
    "profile": profile_to_contract,
    "search_intent": search_intent_to_contract,
    "job": job_to_contract,
    "application_case": application_case_to_contract,
    "lifecycle_event": lifecycle_event_to_contract,
    "calendar_proposal": calendar_proposal_to_contract,
    "reply_draft": reply_draft_to_contract,
    "guenther_result": guenther_result_to_contract,
}

DESERIALIZERS: dict[str, Callable[[dict[str, Any]], Any]] = {
    "profile": profile_from_contract,
    "search_intent": search_intent_from_contract,
    "job": job_from_contract,
    "application_case": application_case_from_contract,
    "lifecycle_event": lifecycle_event_from_contract,
    "calendar_proposal": calendar_proposal_from_contract,
    "reply_draft": reply_draft_from_contract,
    "guenther_result": guenther_result_from_contract,
}


def roundtrip(schema_key: str, obj: Any) -> Any:
    """Python → JSON dict → domain object; asserts serializer exists."""
    wire = SERIALIZERS[schema_key](obj)
    wire = json.loads(json.dumps(_strip_none_for_json(wire), ensure_ascii=False))
    return DESERIALIZERS[schema_key](wire)


def load_schema(name: str) -> dict[str, Any]:
    path = SCHEMAS_V1 / f"{name}.schema.json"
    return json.loads(path.read_text(encoding="utf-8"))


def validate_against_schema(schema_key: str, document: dict[str, Any]) -> None:
    """Raise jsonschema.ValidationError if invalid."""
    import jsonschema
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource
    from referencing.jsonschema import DRAFT202012

    schemas = {
        f"{p.name}": json.loads(p.read_text(encoding="utf-8"))
        for p in SCHEMAS_V1.glob("*.schema.json")
    }
    resources = []
    for fname, schema in schemas.items():
        uri = schema.get("$id") or f"https://karrierekrake.local/contracts/v1/{fname}"
        resources.append((uri, Resource.from_contents(schema, default_specification=DRAFT202012)))
        # Also register relative filename for $ref resolution used in schemas.
        resources.append(
            (
                fname,
                Resource.from_contents(schema, default_specification=DRAFT202012),
            )
        )
    registry = Registry().with_resources(resources)
    schema = schemas[f"{schema_key}.schema.json"]
    Draft202012Validator(schema, registry=registry).validate(document)


def semantic_fingerprint(schema_key: str, obj: Any) -> Any:
    """Comparable payload without wire metadata."""
    if schema_key == "search_intent":
        return obj.model_dump(mode="json")
    if schema_key == "guenther_result":
        return obj.model_dump(mode="json")
    if schema_key == "calendar_proposal":
        data = obj.to_dict()
        data.pop("lifecycle_event_hint", None)
        return data
    if schema_key == "reply_draft":
        return reply_draft_to_contract(obj)
    if schema_key == "lifecycle_event":
        return lifecycle_event_to_contract(obj)
    if is_dataclass(obj):
        return asdict(obj)
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    raise TypeError(schema_key)
