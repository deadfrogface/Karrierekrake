"""UI contract: Bewerbungsvorschau status + honest draft CTA labels."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication

from apply.preview import ApplicationPreview
from desktop.i18n import tr
from desktop.theme import stylesheet_for
from desktop.widgets.apply_preview_dialog import ApplyPreviewDialog


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _restore_stylesheet(qapp):
    previous = qapp.styleSheet()
    qapp.setStyleSheet(stylesheet_for("light"))
    yield
    if qapp.styleSheet() != previous:
        qapp.setStyleSheet(previous)
        qapp.processEvents()


def _preview(**overrides) -> ApplicationPreview:
    base = dict(
        job_id="j1",
        company="Nordlicht Consulting GmbH",
        title="Office Manager (m/w/d)",
        application_url="https://boards.greenhouse.io/example/jobs/1",
        ats="greenhouse",
        ats_support="supported",
        ats_note="",
        dry_run=True,
        mode="review_before_submit",
        will_submit=False,
        form_values={"Vorname": "Max", "E-Mail": "max@example.com"},
        documents={"CV": "cv.pdf"},
        cover_letter_preview="Sehr geehrte Damen und Herren,\n\n…",
        warnings=["Dry-Run aktiv: finaler Submit-Klick ist blockiert."],
        quality_gate="WARNING",
        document_role="cv",
        document_filename="cv.pdf",
        submit_allowed=False,
    )
    base.update(overrides)
    return ApplicationPreview(**base)


def test_preview_dialog_shows_draft_status_not_technical_jargon(qapp):
    dlg = ApplyPreviewDialog(_preview())
    dlg.show()
    qapp.processEvents()
    status = dlg.status_chip.text()
    assert "Entwurf" in status
    assert "wird nicht versendet" in status
    # Main surface must not dump technical tokens
    surface = " ".join(
        [
            dlg.job_title.text(),
            dlg.company_label.text(),
            dlg.status_chip.text(),
            dlg.cv_name.text(),
            dlg.cover_edit.toPlainText(),
            dlg.general_hints.text() if dlg.general_hints.isVisible() else "",
        ]
    )
    for banned in (
        "ATS",
        "submit_allowed",
        "review_before_submit",
        "Dry-Run",
        "===",
        "Absenden",
    ):
        assert banned not in surface
    # Technical details stay collapsed and hold the jargon
    assert dlg.tech_toggle.isCheckable()
    assert not dlg.tech_toggle.isChecked()
    assert not dlg.tech_body.isVisible()
    dlg.tech_toggle.setChecked(True)
    qapp.processEvents()
    assert dlg.tech_body.isVisible()
    from PySide6.QtWidgets import QLabel

    tech_text = " ".join(w.text() for w in dlg.tech_body.findChildren(QLabel))
    assert "ATS" in tech_text or "greenhouse" in tech_text
    assert "submit_allowed" in tech_text or "Dry-Run" in tech_text or "dry" in tech_text.lower()
    assert "https://boards.greenhouse.io" in tech_text
    dlg.close()


def test_preview_dialog_primary_is_confirm_draft_never_submit(qapp):
    dlg = ApplyPreviewDialog(_preview())
    # Without config/job the approve action is hidden (cannot confirm)
    assert dlg.approve_btn.text() == tr("apps.preview_confirm_draft")
    assert "Absenden" not in dlg.approve_btn.text()
    assert "Freigeben" not in dlg.approve_btn.text()
    assert not dlg.approve_btn.isVisible()
    assert dlg.open_url_btn.text() == tr("btn.open_manual")
    assert dlg.open_url_btn.objectName() == "SecondaryButton"
    assert dlg.close_btn.objectName() == "SecondaryButton"
    dlg.close()


def test_preview_dialog_confirm_visible_when_draft_ready(qapp, tmp_path):
    from core.config import AppConfig, ApplicationProfile, SettingsConfig
    from core.models import Job

    cfg = AppConfig(
        application=ApplicationProfile(
            first_name="Max",
            last_name="Mustermann",
            email="max@example.com",
        ),
        settings=SettingsConfig(dry_run=True, mode="review_before_submit"),
        root=tmp_path,
    )
    job = Job(
        id="j1",
        source="indeed",
        title="Office Manager",
        company="Nordlicht",
        application_url="https://example.com/job",
    )
    dlg = ApplyPreviewDialog(
        _preview(will_submit=False, cover_refusal_code=""),
        config=cfg,
        job=job,
    )
    dlg.show()
    qapp.processEvents()
    assert not dlg.approve_btn.isHidden()
    assert dlg.approve_btn.isEnabled()
    assert dlg.approve_btn.text() == "Entwurf bestätigen"
    assert dlg.approve_btn.objectName() == "PrimaryButton"
    assert "Absenden" not in dlg.approve_btn.text()
    dlg.close()


def test_preview_dialog_sections_separate_and_cover_scrollable(qapp):
    long_cover = "Absatz\n\n" * 80 + "Schlusszeile"
    dlg = ApplyPreviewDialog(
        _preview(
            cover_letter_preview=long_cover,
            warnings=[
                "CV-Datei fehlt oder ist nicht lesbar.",
                "Anschreiben enthält ungültigen Firmenplatzhalter.",
                "Profil-Kontaktdaten unvollständig.",
                "Dry-Run aktiv: finaler Submit-Klick ist blockiert.",
            ],
            form_values={"Vorname": "", "E-Mail": "max@example.com"},
            document_filename="",
        )
    )
    dlg.show()
    qapp.processEvents()
    assert dlg.cv_card.isVisible()
    assert dlg.cover_card.isVisible()
    assert dlg.form_card.isVisible()
    assert dlg.cover_edit.toPlainText() == long_cover
    assert not dlg.cover_edit.isReadOnly()
    assert dlg.cover_edit.minimumHeight() >= 160
    # Section-local hints (technical dry-run filtered out of main buckets)
    assert dlg.cv_hints is not None
    assert "CV" in dlg.cv_hints.text() or "Lebenslauf" in dlg.cv_hints.text() or "fehlt" in dlg.cv_hints.text().lower()
    assert dlg.cover_hints is not None
    assert dlg.form_hints is not None
    # No === dump body
    assert not hasattr(dlg, "body") or "=== Geplante" not in dlg.body.toPlainText()
    dlg.resize(900, 650)
    qapp.processEvents()
    assert dlg.width() <= 920
    dlg.close()


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_preview_dialog_renders_in_light_and_dark(qapp, theme):
    qapp.setStyleSheet(stylesheet_for(theme))
    dlg = ApplyPreviewDialog(_preview())
    dlg.show()
    qapp.processEvents()
    assert dlg.status_chip.isVisible()
    assert "Entwurf" in dlg.status_chip.text()
    assert dlg.cv_card.objectName() == "Card"
    assert dlg.approve_btn.objectName() == "PrimaryButton"
    pix = dlg.grab()
    assert not pix.isNull()
    assert pix.width() > 100
    dlg.close()


def _dialog_copy(dlg) -> str:
    from PySide6.QtWidgets import QLabel, QPushButton

    parts = [dlg.windowTitle(), dlg.cover_edit.toPlainText(), dlg.status_chip.text()]
    parts.extend(label.text() for label in dlg.findChildren(QLabel))
    parts.extend(button.text() for button in dlg.findChildren(QPushButton))
    return "\n".join(parts)


def _profile_with_licence(tmp_path, code: str):
    from core.config import AppConfig, ExtractReview, SourcedText

    cfg = AppConfig(root=tmp_path)
    cfg.application.first_name = "Ada"
    cfg.application.last_name = "Beispiel"
    cfg.profile.extract_review = ExtractReview(source="cv", confirmed=True)
    cfg.profile.qualifications.driving_license = [SourcedText(value=code, source="manual")]
    cfg.profile.qualifications.skills = [SourcedText(value="Excel", source="manual")]
    return cfg


def _preview_job():
    from core.models import Job

    return Job(
        id="vorschau-klasse",
        title="Disponent",
        company="Nordlicht GmbH",
        description="Führerschein Klasse C ist erforderlich.",
    )


_CLEAN_LETTER = """Sehr geehrte Damen und Herren,

hiermit bewerbe ich mich um die Position als Disponent bei Nordlicht GmbH.

Zu meinen relevanten Kenntnissen zählen insbesondere: Excel.

Über die Möglichkeit eines persönlichen Gesprächs freue ich mich.

Mit freundlichen Grüßen
Ada Beispiel
"""

_INVENTED_C_LETTER = """Sehr geehrte Damen und Herren,

hiermit bewerbe ich mich um die Position als Disponent bei Nordlicht GmbH.

Zu meinen relevanten Kenntnissen zählen insbesondere: Führerschein Klasse C.

Über die Möglichkeit eines persönlichen Gesprächs freue ich mich.

Mit freundlichen Grüßen
Ada Beispiel
"""


def test_preview_refusal_is_a_sentence_without_the_reason_code(qapp):
    dlg = ApplyPreviewDialog(
        _preview(
            cover_letter_preview="",
            cover_refusal_code="job_incomplete",
            cover_refusal_key="cover.job_incomplete",
            warnings=[],
        )
    )
    dlg.show()
    qapp.processEvents()
    from PySide6.QtWidgets import QLabel

    labels = [label.text() for label in dlg.findChildren(QLabel)]
    assert any("Die Anzeige hat keinen Beschreibungstext." in text for text in labels)
    assert all("job_incomplete" not in text for text in labels)
    assert "unsubstantiated_claims" not in _dialog_copy(dlg)
    dlg.close()


_CLASS_C_SENTENCE = (
    "Zu meinen relevanten Kenntnissen zählen insbesondere: Führerschein Klasse C."
)


def _insert_unconfirmed_class_c(dlg) -> None:
    plain = dlg.cover_edit.toPlainText()
    at = plain.index("insbesondere:") + len("insbesondere:")
    cursor = dlg.cover_edit.textCursor()
    cursor.setPosition(at)
    dlg.cover_edit.setTextCursor(cursor)
    dlg.cover_edit.insertPlainText(" Führerschein Klasse C.")


def _assert_class_c_sentence_is_quoted_from_the_letter(dlg) -> None:
    notice = dlg._guard_notice.text()
    assert f"‚{_CLASS_C_SENTENCE}‘" in notice
    assert _CLASS_C_SENTENCE in dlg.cover_edit.toPlainText()
    assert "Klasse C" in notice
    assert "Fahrerlaubnis" not in notice
    assert "Prüfen nötig" in dlg.status_chip.text()


def test_preview_blocks_confirm_when_the_letter_invents_class_c(qapp, tmp_path):
    """Opening on an unconfirmed class locks confirm and quotes the sentence."""
    cfg = _profile_with_licence(tmp_path, "B")
    job = _preview_job()
    dlg = ApplyPreviewDialog(
        _preview(cover_letter_preview=_INVENTED_C_LETTER, warnings=[]),
        config=cfg,
        job=job,
    )
    dlg.show()
    qapp.processEvents()
    assert dlg.approve_btn.isVisible()
    assert not dlg.approve_btn.isEnabled()
    _assert_class_c_sentence_is_quoted_from_the_letter(dlg)
    assert "unsubstantiated_claims" not in _dialog_copy(dlg)
    saved = tmp_path / "cover_letters" / f"{job.id}.txt"
    assert not saved.exists()
    dlg.close()


def test_preview_confirm_screens_the_edited_letter_again(qapp, tmp_path):
    """A clean draft stays editable. Inserting class C and confirming saves nothing."""
    cfg = _profile_with_licence(tmp_path, "B")
    job = _preview_job()
    dlg = ApplyPreviewDialog(
        _preview(cover_letter_preview=_CLEAN_LETTER, warnings=[]),
        config=cfg,
        job=job,
    )
    dlg.show()
    qapp.processEvents()
    assert dlg.approve_btn.isEnabled()
    assert "Prüfen nötig" not in dlg.status_chip.text()
    _insert_unconfirmed_class_c(dlg)
    dlg.approve_btn.click()
    qapp.processEvents()
    saved = tmp_path / "cover_letters" / f"{job.id}.txt"
    assert not saved.exists()
    assert not dlg.approve_btn.isEnabled()
    _assert_class_c_sentence_is_quoted_from_the_letter(dlg)
    assert "unsubstantiated_claims" not in _dialog_copy(dlg)
    dlg.close()


def test_confirm_during_debounce_checks_that_text(qapp, tmp_path, monkeypatch):
    """Confirm under 400 ms runs a full check and quotes that exact sentence."""
    import core.cover_guard as guard

    scans = {"n": 0}
    original = guard.screen_prepared_letter

    def counting(letter, prepared):
        scans["n"] += 1
        return original(letter, prepared)

    monkeypatch.setattr(guard, "screen_prepared_letter", counting)
    cfg = _profile_with_licence(tmp_path, "B")
    job = _preview_job()
    dlg = ApplyPreviewDialog(
        _preview(cover_letter_preview=_CLEAN_LETTER, warnings=[]),
        config=cfg,
        job=job,
    )
    dlg.show()
    qapp.processEvents()
    assert scans["n"] == 1
    assert dlg.approve_btn.isEnabled()
    _insert_unconfirmed_class_c(dlg)
    assert scans["n"] == 1
    assert dlg._guard_timer.isActive()
    dlg.approve_btn.click()
    qapp.processEvents()
    assert scans["n"] == 2
    assert not dlg._guard_timer.isActive()
    saved = tmp_path / "cover_letters" / f"{job.id}.txt"
    assert not saved.exists()
    assert not dlg.approve_btn.isEnabled()
    _assert_class_c_sentence_is_quoted_from_the_letter(dlg)
    from PySide6.QtTest import QTest

    QTest.qWait(dlg._guard_timer.interval() + 50)
    assert scans["n"] == 2
    dlg.close()


def test_stale_guard_result_keeps_confirm_locked(qapp, tmp_path, monkeypatch):
    """A run of the clean letter must not unlock confirm after the text changed."""
    import core.cover_guard as guard

    cfg = _profile_with_licence(tmp_path, "B")
    dlg = ApplyPreviewDialog(
        _preview(cover_letter_preview=_CLEAN_LETTER, warnings=[]),
        config=cfg,
        job=_preview_job(),
    )
    dlg.show()
    qapp.processEvents()
    assert dlg.approve_btn.isEnabled()
    original = guard.screen_prepared_letter

    def delayed(letter, prepared):
        assert "Führerschein Klasse C." not in letter
        _insert_unconfirmed_class_c(dlg)
        return original(letter, prepared)

    monkeypatch.setattr(guard, "screen_prepared_letter", delayed)
    # The clean letter was already scanned. Hold a second run of that text.
    dlg._last_scanned_hash = ""
    dlg._on_guard_debounce()
    assert "Führerschein Klasse C." in dlg.cover_edit.toPlainText()
    assert not dlg.approve_btn.isEnabled()
    assert "Prüfen nötig" in dlg.status_chip.text()
    dlg.close()


def test_fifty_keystrokes_run_one_guard_after_the_pause_and_one_on_confirm(
    qapp, tmp_path, monkeypatch
):
    """50 characters at 50 ms: one scan after the pause, one more on confirm."""
    import core.cover_guard as guard
    from PySide6.QtCore import QTimer
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QMessageBox

    scans = {"n": 0}
    prepares = {"n": 0}
    profile_reads = {"n": 0}
    original_scan = guard.screen_prepared_letter
    original_prepare = guard.prepare_cover_check
    original_profile = guard.confirmed_profile_text

    def counting_scan(letter, prepared):
        scans["n"] += 1
        return original_scan(letter, prepared)

    def counting_prepare(*args, **kwargs):
        prepares["n"] += 1
        return original_prepare(*args, **kwargs)

    def counting_profile(config):
        profile_reads["n"] += 1
        return original_profile(config)

    monkeypatch.setattr(guard, "screen_prepared_letter", counting_scan)
    monkeypatch.setattr(guard, "prepare_cover_check", counting_prepare)
    monkeypatch.setattr(guard, "confirmed_profile_text", counting_profile)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)
    cfg = _profile_with_licence(tmp_path, "B")
    dlg = ApplyPreviewDialog(
        _preview(cover_letter_preview=_CLEAN_LETTER, warnings=[]),
        config=cfg,
        job=_preview_job(),
    )
    dlg.show()
    qapp.processEvents()
    assert prepares["n"] == 1
    assert profile_reads["n"] == 1
    assert scans["n"] == 1
    assert dlg._guard_timer.interval() >= 400
    assert len(dlg.findChildren(QTimer)) == 1
    scans["n"] = 0
    for _ in range(50):
        dlg.cover_edit.insertPlainText("x")
        QTest.qWait(50)
    assert scans["n"] == 0
    assert prepares["n"] == 1
    assert profile_reads["n"] == 1
    QTest.qWait(dlg._guard_timer.interval() + 80)
    assert scans["n"] == 1
    assert dlg.approve_btn.isEnabled()
    dlg.approve_btn.click()
    qapp.processEvents()
    assert scans["n"] == 2
    assert prepares["n"] == 1
    assert profile_reads["n"] == 1
    dlg.close()
