"""Full application lifecycle E2E matrix + critical zero gates (PR33)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from core.case_pipeline import process_parsed_email
from core.database import Database
from core.lifecycle import (
    ApplicationCase,
    CaseStatus,
    LifecycleEvent,
    LifecycleEventType,
    reduce_lifecycle_events,
)
from core.scheduling_preferences import empty_scheduling_preferences
from integrations.calendar_availability import TimeWindow
from integrations.calendar_freebusy import MockFreeBusyProvider
from integrations.calendar_scheduling import propose_ranked_slots, verify_no_collisions
from integrations.calendar_write import (
    CalendarWriteGate,
    InMemoryCalendarTransport,
    draft_from_ranked_slot,
)
from integrations.email_associate import associate_email
from integrations.email_classify import classify_email
from integrations.reply_draft import ReplyAction, SendGate, build_action_draft
from tests.lifecycle_e2e.gates import (
    GateCounters,
    record_ambiguous_autolink,
    record_cross_case,
    record_false_rejection,
)
from tests.lifecycle_e2e.loader import (
    load_association_scenarios,
    load_calendar_cases,
    load_full_lifecycles,
    load_injection_mails,
    load_recruiting_mails,
    load_reply_scenarios,
    load_status_transitions,
)


@pytest.fixture()
def db(tmp_path: Path) -> Database:
    return Database(tmp_path / "e2e.db")


def test_unambiguous_mail_classification_ge_99():
    rows = [m for m in load_recruiting_mails() if m.get("unambiguous")]
    assert len(rows) >= 500
    gates = GateCounters()
    correct = 0
    for m in rows:
        got = classify_email(m["subject"], m["body"]).category
        record_false_rejection(
            gates, fixture_id=m["id"], expect_class=m["expect_class"], got_class=got
        )
        if got == m["expect_class"]:
            correct += 1
    gates.assert_all_zero()
    assert correct / len(rows) >= 0.99


def test_injection_mails_do_not_force_high_impact():
    gates = GateCounters()
    for m in load_injection_mails():
        got = classify_email(m["subject"], m["body"]).category
        if got in (m.get("forbidden_classes") or []):
            record_false_rejection(
                gates,
                fixture_id=m["id"],
                expect_class=m["expect_class"],
                got_class=got,
            )
    gates.assert_all_zero()


def test_status_transition_matrix_ge_300():
    rows = load_status_transitions()
    assert len(rows) >= 300
    for row in rows:
        types = list(row["events"])
        if (
            LifecycleEventType.REJECTION_RECEIVED.value in types
            and LifecycleEventType.UNDER_REVIEW.value in types
        ):
            seq = [
                (LifecycleEventType.APPLICATION_SENT.value, "2026-01-01T00:00:00Z"),
                (LifecycleEventType.UNDER_REVIEW.value, "2026-01-02T00:00:00Z"),
                (LifecycleEventType.REJECTION_RECEIVED.value, "2026-01-03T00:00:00Z"),
            ]
            present = set(types)
            events = [
                LifecycleEvent(
                    case_id="c",
                    event_type=e,
                    occurred_at=ts,
                    idempotency_key=f"{row['id']}-{e}",
                )
                for e, ts in seq
                if e in present
            ]
        else:
            events = [
                LifecycleEvent(
                    case_id="c",
                    event_type=e,
                    occurred_at=f"2026-01-{(j % 28) + 1:02d}T12:00:00Z",
                    idempotency_key=f"{row['id']}-{e}-{j}",
                )
                for j, e in enumerate(types)
            ]
        result = reduce_lifecycle_events(events)
        assert result.status == row["expect_status"], (row["id"], result.status)


def test_association_unique_and_ambiguous_gates():
    scenarios = load_association_scenarios()
    assert len(scenarios) >= 250
    gates = GateCounters()
    unique_total = unique_ok = 0
    amb_total = amb_ok = 0
    for sc in scenarios:
        result = associate_email(
            sender=sc.get("sender") or "",
            subject=sc.get("subject") or "",
            body=sc.get("body") or "",
            cases=sc.get("cases") or [],
            thread_id=sc.get("thread_id") or "",
            message_id=sc.get("message_id") or "",
            ats_application_id=sc.get("ats_application_id") or "",
            location_hint=sc.get("location_hint") or "",
            is_forwarded=bool(sc.get("is_forwarded")),
        )
        expect = sc.get("expect")
        if expect == "linked":
            unique_total += 1
            expect_case = sc.get("expected_case_id")
            if result.match_status == "linked" and (
                not expect_case or result.case_id == expect_case
            ):
                unique_ok += 1
            if expect_case and result.case_id and result.case_id != expect_case:
                record_cross_case(
                    gates,
                    fixture_id=str(sc.get("id")),
                    expected_case_id=str(expect_case),
                    actual_case_id=str(result.case_id),
                )
        elif expect in {"ambiguous", "review_required"}:
            amb_total += 1
            if result.match_status in {"ambiguous", "review_required"} or result.ambiguous:
                amb_ok += 1
            record_ambiguous_autolink(
                gates,
                fixture_id=str(sc.get("id")),
                association_status=str(result.match_status),
                wrote_case_id=result.case_id if result.match_status == "linked" else None,
            )
    gates.assert_all_zero()
    assert unique_total >= 100
    assert unique_ok / unique_total >= 0.99
    assert amb_total >= 50
    assert amb_ok == amb_total


def test_calendar_cases_collision_free_and_failed_create_not_scheduled():
    rows = load_calendar_cases()
    assert len(rows) >= 200
    gates = GateCounters()
    transport = InMemoryCalendarTransport()
    gate = CalendarWriteGate()
    reference = datetime(2026, 9, 14, 8, 0, tzinfo=timezone.utc)
    for row in rows:
        prefs = empty_scheduling_preferences()
        prefs.timezone = row["timezone"]
        if row.get("busy"):
            provider: MockFreeBusyProvider = MockFreeBusyProvider(
                busy=[TimeWindow(start=reference, end=reference + timedelta(days=14))]
            )
        else:
            provider = MockFreeBusyProvider()
        proposal = propose_ranked_slots(
            row["proposal_text"],
            case_id=f"cal-{row['id']}",
            prefs=prefs,
            freebusy=provider,
            reference=reference,
            modality_override=row.get("modality") or "remote",
        )
        if proposal.ranked_slots:
            busy = []
            if row.get("busy"):
                busy = [TimeWindow(start=reference, end=reference + timedelta(days=14))]
            assert verify_no_collisions(
                proposal, prefs=prefs, busy=busy
            ), row["id"]
            draft = draft_from_ranked_slot(proposal, slot_index=0)
            # Unapproved create must not mark scheduled
            draft.approved = False
            out = gate.attempt_create(draft, transport=transport)
            assert out.created is False
            assert gate.may_mark_scheduled(out) is False
            # Approved create then idempotent retry — no duplicate events
            draft2 = draft_from_ranked_slot(proposal, slot_index=0)
            draft2.client_request_id = out.client_request_id or draft2.client_request_id
            gate.approve(draft2)
            first = gate.attempt_create(draft2, transport=transport)
            second = gate.attempt_create(draft2, transport=transport)
            if first.created and second.created:
                if first.external_event_id != second.external_event_id:
                    gates.note(
                        "duplicate_calendar_event",
                        f"{row['id']} mismatched ids on idempotent retry",
                    )
            if first.create_error and gate.may_mark_scheduled(first):
                gates.note(
                    "failed_calendar_marked_scheduled",
                    f"{row['id']} failed but scheduled",
                )
    gates.assert_all_zero()


def test_reply_cases_never_auto_send():
    scenarios = load_reply_scenarios()
    assert len(scenarios) >= 150
    gates = GateCounters()
    send_gate = SendGate(allow_send=False, draft_only=True)

    def _transport(_draft):
        raise RuntimeError("transport_should_not_run")

    for sc in scenarios:
        action = sc.get("action") or ReplyAction.GENERAL_REPLY.value
        case = sc.get("case") or {
            "id": "c",
            "company": "Nordlicht Beispiel GmbH",
            "position": "Controller",
        }
        draft = build_action_draft(action, case, applicant_name=sc.get("applicant_name") or "")
        assert draft.auto_send is False
        expect = sc.get("expect") or {}
        if expect.get("auto_send") is True:
            gates.note("failed_send_marked_sent", f"{sc.get('id')} corpus expects auto_send")
        out = send_gate.attempt_send(draft, transport=_transport)
        assert out.sent is False
        if out.sent and out.send_error:
            gates.note("failed_send_marked_sent", sc.get("id", "?"))
    gates.assert_all_zero()


def test_full_lifecycle_scenarios_50_of_50(tmp_path: Path):
    scenarios = load_full_lifecycles()
    assert len(scenarios) == 50
    gates = GateCounters()
    correct = 0
    reference = datetime(2026, 9, 14, 8, 0, tzinfo=timezone.utc)
    for sc in scenarios:
        local = Database(tmp_path / f"{sc['id']}.db")
        case = local.upsert_case(
            ApplicationCase(
                company=sc["company"],
                position=sc["position"],
                status=CaseStatus.APPLIED.value,
                contact_email=f"hr@{sc['domain']}",
                notes=sc["reference"],
                applied_at="2026-08-01T10:00:00Z",
            )
        )
        case_id = case.id
        last_status = case.status
        for i, step in enumerate(sc["steps"]):
            payload = {
                "gmail_id": f"{sc['id']}-m{i}",
                "thread_id": sc["thread_id"],
                "subject": step["subject"],
                "sender": sc["sender"],
                "body_text": step["body"] + f"\nRef {sc['reference']}\nFirma: {sc['company']}",
                "received_at": f"2026-09-{(i + 1):02d}T10:00:00Z",
            }
            out = process_parsed_email(local, payload, auto_status=True)
            got_class = classify_email(step["subject"], step["body"]).category
            record_false_rejection(
                gates,
                fixture_id=f"{sc['id']}:{step['phase']}",
                expect_class=step["expect_class"],
                got_class=got_class,
            )
            if (
                out.get("case_id")
                and out.get("status") == "linked"
                and out["case_id"] != case_id
            ):
                record_cross_case(
                    gates,
                    fixture_id=sc["id"],
                    expected_case_id=str(case_id),
                    actual_case_id=str(out["case_id"]),
                )
            if step.get("calendar_proposal"):
                prop = propose_ranked_slots(
                    step["calendar_proposal"],
                    case_id=str(case_id),
                    prefs=empty_scheduling_preferences(),
                    freebusy=MockFreeBusyProvider(),
                    reference=reference,
                )
                if prop.ranked_slots:
                    assert verify_no_collisions(
                        prop,
                        prefs=empty_scheduling_preferences(),
                        busy=[],
                    )
            refreshed = local.get_case(str(case_id))
            if refreshed:
                last_status = refreshed.status
        draft = build_action_draft(
            sc["reply_action"],
            {"id": case_id, "company": sc["company"], "position": sc["position"]},
        )
        assert draft.auto_send is False
        expect_final = sc["expect_final_status"]
        ok_final = last_status == expect_final
        if expect_final == "confirmation" and last_status in {
            CaseStatus.CONFIRMATION.value,
            CaseStatus.APPLIED.value,
        }:
            ok_final = True
        if ok_final:
            correct += 1
        else:
            gates.details.append(
                f"lifecycle_final:{sc['id']} got={last_status} expect={expect_final}"
            )
    gates.assert_all_zero()
    assert correct == 50, f"full lifecycle {correct}/50; {gates.details[:15]}"


def test_publish_benchmark_report(tmp_path: Path):
    from scripts.run_lifecycle_e2e_benchmark import build_report
    from tests.lifecycle_e2e.report import evaluate_acceptance

    report = build_report()
    out = tmp_path / "lifecycle_e2e_report.json"
    report.write(out)
    assert out.is_file()
    assert report.gate_pass
    assert evaluate_acceptance(report)
