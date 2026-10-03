"""Regression tests for account setup, previews, prep binding and reply copy."""
from datetime import datetime, timezone
from types import SimpleNamespace as NS
import json
import pytest
from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import QFileDialog, QMessageBox, QLabel
from tests.test_profile_refresh_cards import qapp, config_service
from desktop.pages.settings import SettingsPage, _SETTINGS_NAV_KEYS
from desktop.widgets.calendar_preview_dialog import CalendarPreviewDialog
from integrations.reply_draft import human_slot, build_action_draft, ReplyAction
from integrations.interview_prep import build_interview_prep


@pytest.fixture(autouse=True)
def no_background_account_probes(monkeypatch):
    monkeypatch.setattr(SettingsPage, "_refresh_provider_status", lambda *args: None)


def test_preview_marks_proposal_days_and_selection_never_writes(qapp):
    slots = [NS(start=datetime(2026, 10, d, 14, tzinfo=timezone.utc),
                end=datetime(2026, 10, d, 15, tzinfo=timezone.utc)) for d in (7, 8)]
    dialog = CalendarPreviewDialog(slots, title="Employer — Position")
    assert dialog.selected_index == 0
    assert dialog.agenda.rowCount() == 1
    assert "14:00 Uhr" in dialog.agenda.item(0, 0).text()
    assert dialog.calendar.dateTextFormat(QDate(2026, 10, 8)).background().color().name() == "#b8e8df"
    dialog.calendar.setSelectedDate(QDate(2026, 10, 8))
    assert dialog.selected_index == 1
    dialog.calendar.setSelectedDate(QDate(2026, 10, 9))
    assert dialog.selected_index is None
    dialog.reject()


@pytest.mark.parametrize("client_kind, valid", [("installed", True), ("web", False)])
def test_google_client_import_stays_in_user_profile(qapp, config_service, tmp_path, monkeypatch, client_kind, valid):
    source = tmp_path / "oauth.json"
    source.write_text(json.dumps({client_kind: {"client_id": "test.apps.googleusercontent.com", "client_secret": "test-secret", "auth_uri": "https://accounts.google.com/o/oauth2/auth", "token_uri": "https://oauth2.googleapis.com/token"}}))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a: (str(source), "JSON"))
    monkeypatch.setattr(QMessageBox, "warning", lambda *a: None)
    page = SettingsPage(config_service)
    assert page._import_google_client() is valid
    if valid:
        target = config_service.dirs["config"] / "google_desktop_client.json"
        assert target.is_file()
        assert config_service.load().settings.gmail_credentials_path == str(target)
        assert page._google_client_path() == target
    page.close()


def test_search_configuration_has_own_settings_section(qapp, config_service):
    page = SettingsPage(config_service)
    index = _SETTINGS_NAV_KEYS.index("nav.search")
    page.nav.setCurrentRow(index)
    assert page.search_mode.window() is page
    assert page.stack.currentWidget().isAncestorOf(page.search_mode)
    assert not page.stack.widget(_SETTINGS_NAV_KEYS.index("settings.nav.advanced")).isAncestorOf(page.search_mode)
    page.close()


def test_reply_contains_human_time_without_internal_jargon():
    case = dict(id="a", company="Employer", position="Clerk", company_verified=True, position_verified=True)
    draft = build_action_draft(ReplyAction.PROPOSE_SLOTS, case, applicant_name="Mara König", proposed_slots=["2026-10-07T14:00:00+02:00"])
    assert "Mittwoch, 07.10.2026 um 14:00 Uhr (UTC+02:00)" in draft.body
    assert "2026-10-07T" not in draft.body
    assert "verifizierte" not in draft.body
    assert "kurze Rückmeldung" in draft.body
    assert not draft.sent


def test_prep_uses_evidence_and_has_honest_fallback():
    prep = build_interview_prep(case_id="a", company="Employer", position="Clerk", evidence=[dict(claim="Customer service", support="DIRECT", note="CV experience")])
    assert prep.strengths[0].claim == "Customer service"
    assert "CV experience" in prep.talking_points[0]
    empty = build_interview_prep(case_id="a", company="Employer", position="Clerk", evidence=[])
    assert empty.talking_points and not empty.strengths



def test_interview_prep_receives_selected_email_and_job_evidence(qapp, config_service, monkeypatch):
    from core.database import Database
    from core.models import Job
    from core.lifecycle import ApplicationCase
    from desktop.pages.lifecycle import LifecyclePage
    from PySide6.QtWidgets import QDialog
    cfg = config_service.load()
    db = Database(cfg.db_path)
    db.upsert_job(Job(id="prep-job", company="Employer", title="Clerk"))
    db.upsert_case(ApplicationCase(id="prep-case", job_id="prep-job", company="Employer", position="Clerk", status="interview"))
    monkeypatch.setattr("core.matcher.score_job", lambda *a, **k: NS(evidence=[dict(token="Service", evidence_class="DIRECT", note="CV fact")]))
    captured = {}
    class Dialog:
        DialogCode = QDialog.DialogCode
        want_draft = False
        def __init__(self, prep, *, email_excerpt, parent):
            captured.update(prep=prep, excerpt=email_excerpt)
        def exec(self):
            return self.DialogCode.Rejected
    monkeypatch.setattr("desktop.widgets.interview_prep_dialog.InterviewPrepDialog", Dialog)
    page = LifecyclePage(config_service)
    page.refresh()
    page.cases.selectRow(0)
    page.show_prep(source_email=dict(case_id="prep-case", body_text="Invitation for 7 October"))
    assert captured["excerpt"] == "Invitation for 7 October"
    assert captured["prep"].strengths[0].claim == "Service"
    page.close()
