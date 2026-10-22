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
