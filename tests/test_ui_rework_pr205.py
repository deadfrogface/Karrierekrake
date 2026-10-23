"""Jobs page, fit wording, work-model detection and the connection guides (user feedback after the first test)."""
from core.matcher import percent_to_min_score
from desktop.viewmodels.job_fit import FIT_PARTIAL, FIT_STRONG, FitBullet, _headline, humanize_reason
from search.remote_text import classify_remote


def test_matcher_reasons_are_shown_in_german():
    assert humanize_reason("✓ working time matched") == "Arbeitszeit passt"
    assert humanize_reason("salary unknown (not hard-failed)") == "Gehalt nicht angegeben"
    assert humanize_reason("within radius 20.0 km") == "Innerhalb von 20 km"
    assert humanize_reason("Few listed skills found in the job text") == "Wenige deiner Kenntnisse im Stellentext gefunden"
    assert humanize_reason("unbekannter Text") == "unbekannter Text"


def test_generic_passes_alone_do_not_make_a_job_passend():
    generic = tuple(FitBullet("pass", text) for text in
                    ("working time matched", "salary unknown (not hard-failed)", "country matched", "Vollzeit"))
    assert _headline(generic, excluded=False, sort_score=None) != FIT_STRONG
    real = generic + (FitBullet("pass", "Direkt: Erfahrung Sachbearbeiter"),)
    assert _headline(real, excluded=False, sort_score=None) == FIT_PARTIAL


def test_min_match_percent_is_measured_against_the_realistic_top_score():
    assert percent_to_min_score(75) == 52
    assert percent_to_min_score(0) == 0
    assert percent_to_min_score(100) == 70


def test_homeoffice_as_a_benefit_is_hybrid_not_remote():
    assert classify_remote("Homeoffice ist möglich. Vollzeit") == "hybrid"
    assert classify_remote("Möglichkeit zur mobilen Arbeit (bis zu zwei Tage/Woche)") == "hybrid"
    assert classify_remote("100% remote Position") == "remote"
    assert classify_remote("Customer Hero (Remote; 80-100%)") == "remote"
    assert classify_remote("kein Homeoffice möglich") == "onsite"


def test_mail_dialog_shows_steps_for_every_provider(qtbot):
    from desktop.widgets.free_mail_credentials import FreeMailCredentialsDialog

    dialog = FreeMailCredentialsDialog()
    qtbot.addWidget(dialog)
    for index in range(len(dialog.PRESETS)):
        dialog.provider.setCurrentIndex(index)
        assert "<ol" in dialog.guide.toHtml() or dialog.guide.toPlainText().strip()
    dialog.provider.setCurrentIndex(0)
    assert "App-Passwort" in dialog.guide.toPlainText() and "16 Buchstaben" in dialog.guide.toPlainText()


def test_calendar_dialog_offers_link_only_where_a_link_exists(qtbot):
    from desktop.widgets.connection_guide import CalendarConnectDialog

    dialog = CalendarConnectDialog()
    qtbot.addWidget(dialog)
    dialog.app.setCurrentText("Google Kalender")
    assert dialog.link_btn.isEnabled()
    dialog.app.setCurrentText("Apple Kalender / iCloud")
    assert not dialog.link_btn.isEnabled() and dialog.file_btn.isEnabled()
    dialog.file_btn.click()
    assert dialog.choice == "file"


def test_dashboard_counts_jobs_at_75_percent_of_the_realistic_top_score(tmp_path):
    from core.database import Database
    from core.models import Job

    db = Database(tmp_path / "jobs.db")
    db.upsert_job(Job(id="a", title="Sachbearbeiter", match_score=62))
    db.upsert_job(Job(id="b", title="Servicekraft", match_score=37))
    assert db.dashboard_stats()["matches_ge_75"] == 1


def test_search_card_title_shows_a_single_ampersand(qtbot):
    from desktop.pages.search import SearchCard

    card = SearchCard()
    qtbot.addWidget(card)
    card.setTitle("Ort, Modell && Konditionen")
    assert card.heading.text() == "Ort, Modell & Konditionen"


def test_old_remote_jobs_with_homeoffice_benefit_become_hybrid_once(tmp_path):
    from core.database import Database
    from core.job_repair import reclassify_remote_jobs
    from core.models import Job

    db = Database(tmp_path / "jobs.db")
    db.upsert_job(Job(id="a", title="Sachbearbeiter", description="Homeoffice ist möglich. Vollzeit.", remote_type="remote"))
    db.upsert_job(Job(id="b", title="Remote Support", description="100% remote Position", remote_type="remote"))
    assert reclassify_remote_jobs(db) == 1
    assert {j.id: j.remote_type for j in db.list_jobs(min_match=0, limit=10)} == {"a": "hybrid", "b": "remote"}
    assert reclassify_remote_jobs(db) == 0  # already done for this database


def test_help_dialog_has_first_steps_faq_and_both_connection_guides(qtbot):
    from desktop.widgets.help_dialog import HelpDialog

    dialog = HelpDialog()
    qtbot.addWidget(dialog)
    titles = [dialog.tabs.tabText(i) for i in range(dialog.tabs.count())]
    assert titles == ["Erste Schritte", "Häufige Fragen", "Postfach verbinden", "Kalender verbinden"]
    assert "App-Passwort" in dialog.tabs.widget(2).toPlainText()
    assert "Geheime Adresse" in dialog.tabs.widget(3).toPlainText()


def test_getting_started_card_counts_done_steps_and_offers_actions_only_for_open_ones(qtbot):
    from desktop.widgets.getting_started import GettingStartedCard
    from PySide6.QtWidgets import QPushButton

    clicked = []
    card = GettingStartedCard()
    qtbot.addWidget(card)
    card.set_steps([("A", "hint a", True, lambda: clicked.append("a"), "Los"),
                    ("B", "hint b", False, lambda: clicked.append("b"), "Starten")])
    assert card.count.text() == "1 von 2 erledigt"
    buttons = [b for b in card.findChildren(QPushButton) if b.text() == "Starten"]
    assert len(buttons) == 1 and not [b for b in card.findChildren(QPushButton) if b.text() == "Los"]
    buttons[0].click()
    assert clicked == ["b"]
    card.set_steps([("A", "", True, None, "")])  # a second refresh replaces the rows
    assert card.count.text() == "1 von 1 erledigt"



def test_job_card_chips_show_work_model_working_time_and_source_in_german():
    from core.models import Job
    from desktop.widgets.job_card_delegate import job_chips

    job = Job(id="1", title="t", remote_type="hybrid", employment_type="fulltime", source="indeed")
    assert job_chips(job) == ["Hybrid", "Vollzeit", "Indeed"]
    assert job_chips(Job(id="2", title="t", remote_type="unknown", employment_type="nan")) == []


def _ev(kind, source="", day="2026-10-20"):
    from types import SimpleNamespace as NS
    return NS(event_type=kind, source=source, occurred_at=day + "T10:00:00+00:00", recorded_at=day)


def test_rail_never_reports_a_sent_application_without_proof():
    from desktop.viewmodels.evidence_rail import DONE, OPEN, UNCERTAIN, build_evidence_rail

    only_program = build_evidence_rail([_ev("APPLICATION_CREATED", "apply"), _ev("APPLICATION_SENT", "apply")])
    assert [s.state for s in only_program][:3] == [DONE, UNCERTAIN, OPEN]
    assert "Kein Beleg" in only_program[1].evidence
    # status "applied" saved without any event is just as unproven
    assert build_evidence_rail([], application_status="applied")[1].state == UNCERTAIN


def test_rail_marks_sent_done_by_your_confirmation_or_the_employers_receipt():
    from desktop.viewmodels.evidence_rail import DONE, FAILED, build_evidence_rail

    by_you = build_evidence_rail([_ev("APPLICATION_CREATED", "manual"), _ev("APPLICATION_SENT", "manual")])
    assert by_you[1].state == DONE and "von dir bestätigt" in by_you[1].evidence
    receipt = build_evidence_rail([_ev("APPLICATION_SENT", "apply"), _ev("APPLICATION_RECEIVED", "imap", "2026-10-21"),
                                   _ev("REJECTION_RECEIVED", "imap", "2026-10-25")])
    assert receipt[1].state == DONE and receipt[2].state == DONE and "21.10.2026" in receipt[2].evidence
    assert receipt[4].label == "Absage" and receipt[4].state == FAILED


def test_rail_widget_renders_one_column_per_step(qtbot):
    from desktop.viewmodels.evidence_rail import build_evidence_rail
    from desktop.widgets.evidence_rail import EvidenceRail

    rail = EvidenceRail()
    qtbot.addWidget(rail)
    rail.bind(build_evidence_rail([_ev("APPLICATION_CREATED", "manual")]))
    rail.bind(build_evidence_rail([_ev("APPLICATION_CREATED", "manual"), _ev("APPLICATION_SENT", "apply")]))
    assert "Gesendet: uncertain" in rail.accessibleDescription()


def test_your_own_confirmation_is_stored_with_its_source_and_turns_the_step_done(tmp_path):
    from core.database import Database
    from core.lifecycle import LifecycleEvent, LifecycleEventType
    from core.lifecycle import ApplicationCase
    from desktop.viewmodels.evidence_rail import DONE, UNCERTAIN, build_evidence_rail

    db = Database(tmp_path / "jobs.db")
    db.upsert_case(ApplicationCase(id="c1", job_id="j1", company="Firma", position="Sachbearbeiter", status="applied"))
    assert build_evidence_rail(db.list_lifecycle_events("c1"), application_status="applied")[1].state == UNCERTAIN
    db.append_lifecycle_event(LifecycleEvent(event_type=LifecycleEventType.APPLICATION_SENT.value, case_id="c1",
                                             source="manual", idempotency_key="manual-sent:c1"))
    events = db.list_lifecycle_events("c1")
    assert build_evidence_rail(events, application_status="applied")[1].state == DONE


def test_each_cover_letter_sentence_points_to_the_profile_entry_it_comes_from():
    from core.config import ExperienceEntry, QualificationsConfig, SourcedText
    from core.cover_provenance import explain_sentences

    quals = QualificationsConfig(
        work_experience=[ExperienceEntry(title="Buchhalter im Forderungswesen", company="Beispiel GmbH",
                                         responsibilities=["Prüfung und Buchung von Eingangsrechnungen"])],
        software=[SourcedText(value="SAP")])
    letter = ("Sehr geehrte Damen und Herren, in meiner Zeit als Buchhalter im Forderungswesen bei der Beispiel GmbH habe ich "
              "Eingangsrechnungen geprüft und gebucht. Mit SAP arbeite ich täglich. Ich freue mich auf Ihre Antwort.")
    rows = explain_sentences(letter, quals, job_title="Sachbearbeiter Rechnungswesen", company="Muster GmbH")
    by_text = {r.text: r for r in rows}
    station = next(r for r in rows if "Forderungswesen" in r.text)
    assert any(s.kind == "station" for s in station.sources)
    assert any(s.kind == "software" and "SAP" in s.label for s in next(r for r in rows if "SAP" in r.text).sources)
    assert next(r for r in rows if "Antwort" in r.text).is_standard and by_text


def test_provenance_panel_renders_standard_wording_honestly(qtbot):
    from core.cover_provenance import SentenceSource
    from desktop.widgets.provenance_panel import render_html

    html = render_html([SentenceSource("Ich freue mich auf Ihre Antwort.")])
    assert "Standardformulierung" in html and "keine Angabe aus deinem Profil" in html
