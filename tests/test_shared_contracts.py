"""PR37 — shared mobile contract fixtures + Python round-trips."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema")

from core.config import ApplicationProfile
from core.lifecycle import ApplicationCase, CaseStatus, LifecycleEvent, LifecycleEventType
from core.models import Job
from core.search_intent import SearchIntent, Strictness
from core.shared_contracts import (
    BUNDLE_VERSION,
    FIXTURES_V1,
    SCHEMA_IDS,
    application_case_from_contract,
    application_case_to_contract,
    calendar_proposal_from_contract,
    calendar_proposal_to_contract,
    guenther_result_from_contract,
    guenther_result_to_contract,
    job_from_contract,
    job_to_contract,
    lifecycle_event_from_contract,
    lifecycle_event_to_contract,
    profile_from_contract,
    profile_to_contract,
    reply_draft_from_contract,
    reply_draft_to_contract,
    roundtrip,
    search_intent_from_contract,
    search_intent_to_contract,
    validate_against_schema,
)
from guenther.contracts import GuentherEnvelope
from integrations.calendar_scheduling import SchedulingProposal
from integrations.reply_draft import ReplyDraft

FIXTURE_SCHEMA = {
    "profile": "profile",
    "search_intent": "search_intent",
    "job": "job",
    "application_case": "application_case",
    "lifecycle_event": "lifecycle_event",
    "calendar_proposal": "calendar_proposal",
    "reply_draft": "reply_draft",
    "guenther_result": "guenther_result",
}


def _all_fixtures() -> list[Path]:
    return sorted(FIXTURES_V1.glob("*.json"))


@pytest.mark.parametrize("path", _all_fixtures(), ids=lambda p: p.name)
def test_all_fixtures_validate(path: Path):
    schema_key = FIXTURE_SCHEMA[path.name.split(".")[0]]
    doc = json.loads(path.read_text(encoding="utf-8"))
    validate_against_schema(schema_key, doc)
    assert doc["schema_id"] == SCHEMA_IDS[schema_key]
    assert doc["contract_version"].startswith("1.")


def test_fixture_count_covers_all_contracts():
    prefixes = {p.name.split(".")[0] for p in _all_fixtures()}
    assert set(SCHEMA_IDS) <= prefixes


def test_unknown_fields_forward_compatible():
    doc = json.loads((FIXTURES_V1 / "profile.unknown_field.json").read_text(encoding="utf-8"))
    validate_against_schema("profile", doc)
    assert "mobile_client_tag" in doc
    profile = profile_from_contract(doc)
    # Unknown field stripped on domain load — no crash, no invention.
    assert not hasattr(profile, "mobile_client_tag")
    assert profile.first_name == "Jürgen"


def test_old_and_new_minor_versions_validate():
    old = json.loads((FIXTURES_V1 / "lifecycle_event.v1_baseline.json").read_text(encoding="utf-8"))
    new = json.loads((FIXTURES_V1 / "guenther_result.forward_minor.json").read_text(encoding="utf-8"))
    assert old["contract_version"] == "1.0.0"
    assert new["contract_version"] == "1.1.0"
    validate_against_schema("lifecycle_event", old)
    validate_against_schema("guenther_result", new)


def test_unicode_search_intent_roundtrip():
    doc = json.loads((FIXTURES_V1 / "search_intent.unicode.json").read_text(encoding="utf-8"))
    validate_against_schema("search_intent", doc)
    intent = search_intent_from_contract(doc)
    assert "Buchhalterin" in intent.target_roles[0]
    back = search_intent_to_contract(intent)
    assert "Buchhalterin" in back["target_roles"][0]


def test_timestamps_and_timezones_preserved_on_wire():
    doc = json.loads((FIXTURES_V1 / "job.valid.json").read_text(encoding="utf-8"))
    assert "+02:00" in doc["published_at"] or doc["published_at"].endswith("Z") or "+" in doc["published_at"]
    job = job_from_contract(doc)
    assert job.published_at == doc["published_at"]
    cal = json.loads((FIXTURES_V1 / "calendar_proposal.valid.json").read_text(encoding="utf-8"))
    assert cal["timezone"] == "Europe/Berlin"
    assert cal["ranked_slots"][0]["start"]
    validate_against_schema("calendar_proposal", cal)


def test_profile_roundtrip_no_semantic_loss():
    profile = ApplicationProfile(
        first_name="Jürgen",
        last_name="Müller",
        city="München",
        email="juergen.mueller@example.com",
        country="DE",
        answers={"notice": "3 Monate"},
        field_origins={"email": "manual"},
    )
    again = roundtrip("profile", profile)
    assert again.first_name == profile.first_name
    assert again.last_name == profile.last_name
    assert again.city == profile.city
    assert again.email == profile.email
    assert again.answers == profile.answers
    assert again.field_origins == profile.field_origins


def test_search_intent_roundtrip_preserves_null_strictness():
    intent = SearchIntent(
        target_roles=["Controller"],
        mandatory_skills=["Excel"],
        strictness=None,
        remote_mode=None,
        salary_min=None,
    )
    again = roundtrip("search_intent", intent)
    assert again.strictness is None
    assert again.remote_mode is None
    assert again.target_roles == ["Controller"]
    assert again.mandatory_skills == ["Excel"]


def test_search_intent_roundtrip_strict():
    intent = SearchIntent(
        target_roles=["Lohnbuchhalter"],
        mandatory_skills=["SAP"],
        strictness=Strictness.STRICT,
        countries=["DE", "CH"],
        radius_km=30.0,
    )
    again = roundtrip("search_intent", intent)
    assert again.strictness == Strictness.STRICT
    assert again.countries == ["DE", "CH"]
    assert again.radius_km == 30.0


def test_job_roundtrip():
    job = Job(
        id="j1",
        title="Sachbearbeiter",
        company="Firma ÄÖÜ",
        country_code="AT",
        match_reasons=["✓ Zielberuf"],
        rejection_reasons=["⚠ wenig SAP"],
        match_score=70,
        distance_km=8.5,
    )
    again = roundtrip("job", job)
    assert again.id == "j1"
    assert again.company == job.company
    assert again.match_reasons == job.match_reasons
    assert again.rejection_reasons == job.rejection_reasons
    assert again.country_code == "AT"


def test_application_case_roundtrip_canonical_status():
    case = ApplicationCase(
        id="c1",
        job_id="j1",
        company="Acme",
        position="Payroll",
        status=CaseStatus.OFFER.value,
        contact_email="HR@Example.COM",
    )
    again = roundtrip("application_case", case)
    assert again.status == "offer"
    assert again.contact_email == "hr@example.com"  # normalized


def test_lifecycle_event_roundtrip():
    ev = LifecycleEvent(
        event_type=LifecycleEventType.MANUAL_OVERRIDE.value,
        case_id="c1",
        occurred_at="2026-09-20T10:00:00Z",
        recorded_at="2026-09-20T10:00:01Z",
        source="user",
        payload={"to": "interview", "note": "Korrektur"},
        confidence=1.0,
        idempotency_key="manual:c1:1",
        id="e1",
    )
    again = roundtrip("lifecycle_event", ev)
    assert again.event_type == LifecycleEventType.MANUAL_OVERRIDE.value
    assert again.payload["to"] == "interview"
    assert again.idempotency_key == "manual:c1:1"


def test_calendar_proposal_roundtrip():
    doc = json.loads((FIXTURES_V1 / "calendar_proposal.valid.json").read_text(encoding="utf-8"))
    prop = calendar_proposal_from_contract(doc)
    assert isinstance(prop, SchedulingProposal)
    assert prop.timezone == "Europe/Berlin"
    assert prop.ranked_slots
    back = calendar_proposal_to_contract(prop)
    validate_against_schema("calendar_proposal", back)
    assert back["case_id"] == doc["case_id"]
    assert back["ranked_slots"][0]["rank"] == doc["ranked_slots"][0]["rank"]


def test_reply_draft_auto_send_always_false():
    draft = ReplyDraft(
        case_id="c1",
        action="WITHDRAW",
        to_address="hr@example.com",
        subject="Rücknahme",
        body="…",
        auto_send=True,  # attacker/wire attempt
        draft_only=True,
    )
    wire = reply_draft_to_contract(draft)
    assert wire["auto_send"] is False
    validate_against_schema("reply_draft", wire)
    again = reply_draft_from_contract({**wire, "auto_send": True})
    assert again.auto_send is False


def test_guenther_result_roundtrip():
    env = GuentherEnvelope(
        ok=False,
        capability="writing",
        suggestion={},
        validated=False,
        fallback_reason="model_unavailable",
        safety_notes=["fail_closed"],
    )
    again = roundtrip("guenther_result", env)
    assert again.ok is False
    assert again.validated is False
    assert again.fallback_reason == "model_unavailable"


def test_invalid_status_rejected_by_schema():
    doc = json.loads((FIXTURES_V1 / "application_case.valid.json").read_text(encoding="utf-8"))
    bad = deepcopy(doc)
    bad["status"] = "totally_fake_status"
    with pytest.raises(jsonschema.ValidationError):
        validate_against_schema("application_case", bad)


def test_permissions_matrix_covers_all_schema_ids():
    path = Path("contracts/permissions.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    ids = {v["schema_id"] for v in data["objects"].values()}
    assert ids == set(SCHEMA_IDS.values())
    assert data["objects"]["reply_draft"]["mobile_write"] == "draft_only"
    assert data["objects"]["job"]["mobile_write"] is False


def test_bundle_version_matches_envelope():
    assert BUNDLE_VERSION == "1.0.0"
    doc = profile_to_contract(ApplicationProfile(first_name="A"))
    assert doc["contract_version"] == BUNDLE_VERSION


def test_e2e_python_json_schema_roundtrip_chain():
    """Acceptance: Python object → JSON → schema → roundtrip."""
    samples = {
        "profile": ApplicationProfile(first_name="Anna", city="Köln", country="DE"),
        "search_intent": SearchIntent(target_roles=["Analyst"], strictness=Strictness.BALANCED),
        "job": Job(id="x", title="Analyst", company="Co"),
        "application_case": ApplicationCase(
            id="c", company="Co", position="Analyst", status="applied"
        ),
        "lifecycle_event": LifecycleEvent(
            event_type="APPLICATION_RECEIVED", case_id="c", source="email"
        ),
        "reply_draft": ReplyDraft(
            case_id="c",
            action="THANK_YOU",
            to_address="a@example.com",
            subject="Danke",
            body="Danke",
        ),
        "guenther_result": GuentherEnvelope(ok=True, capability="job_analysis", validated=True),
    }
    for key, obj in samples.items():
        wire = {
            "profile": profile_to_contract,
            "search_intent": search_intent_to_contract,
            "job": job_to_contract,
            "application_case": application_case_to_contract,
            "lifecycle_event": lifecycle_event_to_contract,
            "reply_draft": reply_draft_to_contract,
            "guenther_result": guenther_result_to_contract,
        }[key](obj)
        raw = json.dumps(wire, ensure_ascii=False)
        loaded = json.loads(raw)
        validate_against_schema(key, loaded)
        again = {
            "profile": profile_from_contract,
            "search_intent": search_intent_from_contract,
            "job": job_from_contract,
            "application_case": application_case_from_contract,
            "lifecycle_event": lifecycle_event_from_contract,
            "reply_draft": reply_draft_from_contract,
            "guenther_result": guenther_result_from_contract,
        }[key](loaded)
        assert again is not None


def test_docs_exist_and_sync_unspecified():
    root = Path("docs/mobile")
    for name in (
        "companion_architecture.md",
        "capability_matrix.md",
        "privacy_security_data_flow.md",
        "sync_decision.md",
    ):
        text = (root / name).read_text(encoding="utf-8")
        assert text.strip()
    sync = (root / "sync_decision.md").read_text(encoding="utf-8").lower()
    assert "unspecified" in sync
    assert "invent" in sync or "nicht" in sync or "forbidden" in sync
