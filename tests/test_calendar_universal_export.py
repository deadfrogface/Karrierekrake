from pathlib import Path

import pytest

from integrations.calendar_write import CalendarEventDraft, export_approved_ics


def draft():
    return CalendarEventDraft(
        case_id="case1", title="Vorstellungsgespräch", start="2026-11-02T10:00:00+01:00",
        end="2026-11-02T11:00:00+01:00", uid="kk-abc@example.invalid",
        client_request_id="req1", location="Düsseldorf, Büro", description="Gespräch",
    )


def test_export_requires_explicit_approval(tmp_path):
    item = draft()
    with pytest.raises(PermissionError):
        export_approved_ics(item, tmp_path / "interview.ics")
    assert not (tmp_path / "interview.ics").exists()


def test_export_contains_location_and_does_not_mark_created(tmp_path):
    item = draft()
    item.approved = True
    path = export_approved_ics(item, tmp_path / "interview.ics")
    content = path.read_text(encoding="utf-8")
    assert "BEGIN:VEVENT" in content
    assert "LOCATION:Düsseldorf\\, Büro" in content
    assert "DTSTART:20261102T090000Z" in content
    assert "DTEND:20261102T100000Z" in content
    assert item.created is False


def test_export_rejects_invalid_dates(tmp_path):
    item = draft()
    item.approved = True
    item.end = item.start
    with pytest.raises(ValueError):
        export_approved_ics(item, tmp_path / "interview.ics")
