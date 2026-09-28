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
    assert dlg.cover_edit.isReadOnly()
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


_PATH_FOR_CLASS_C = (
    "Bestätige Klasse C im Führerschein-Feld oder nimm den Eintrag aus deinen Skills."
)


def _assert_class_c_sentence_is_quoted_from_the_letter(dlg) -> None:
    notice = dlg._guard_notice.text()
    assert notice.startswith(f"‚{_CLASS_C_SENTENCE}‘")
    assert _PATH_FOR_CLASS_C in notice
    assert _CLASS_C_SENTENCE in dlg.cover_edit.toPlainText()
    assert "Nimm ihn aus dem Brief" not in notice
    assert "Fahrerlaubnis" not in notice
    assert "Prüfen nötig" in dlg.status_chip.text()


def test_preview_hint_equals_the_utf8_literal(qapp, tmp_path):
    """The hint under Prüfen nötig is this UTF-8 text, including the Skills label."""
    cfg = _profile_with_licence(tmp_path, "B")
    dlg = ApplyPreviewDialog(
        _preview(cover_letter_preview=_INVENTED_C_LETTER, warnings=[]),
        config=cfg,
        job=_preview_job(),
    )
    dlg.show()
    qapp.processEvents()
    assert dlg._guard_notice.text() == (
        "‚Zu meinen relevanten Kenntnissen zählen insbesondere: Führerschein Klasse C.‘\n"
        "Bestätige Klasse C im Führerschein-Feld oder nimm den Eintrag aus deinen Skills."
    )
    dlg.close()


def test_open_and_one_confirm_run_exactly_two_guard_scans(qapp, tmp_path, monkeypatch):
    """Opening the dialog and confirming once runs the guard twice, and no more."""
    import core.cover_guard as guard
    from PySide6.QtWidgets import QMessageBox

    scans = {"n": 0}
    original = guard.screen_prepared_letter

    def counting(letter, prepared):
        scans["n"] += 1
        return original(letter, prepared)

    monkeypatch.setattr(guard, "screen_prepared_letter", counting)
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
    assert scans["n"] == 1
    assert dlg.approve_btn.isEnabled()
    qapp.processEvents()
    assert scans["n"] == 1
    dlg.approve_btn.click()
    qapp.processEvents()
    assert scans["n"] == 2
    dlg.close()
    qapp.processEvents()
    assert scans["n"] == 2


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


def test_preview_cover_is_read_only(qapp):
    """Typing and paste leave the generated letter unchanged."""
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtTest import QTest

    dlg = ApplyPreviewDialog(_preview(cover_letter_preview=_CLEAN_LETTER, warnings=[]))
    dlg.show()
    qapp.processEvents()
    assert dlg.cover_edit.isReadOnly()
    before = dlg.cover_edit.toPlainText()
    dlg.cover_edit.setFocus()
    QTest.keyClicks(dlg.cover_edit, "Klasse C")
    assert dlg.cover_edit.toPlainText() == before
    QGuiApplication.clipboard().setText("Eingefügt")
    dlg.cover_edit.paste()
    qapp.processEvents()
    assert dlg.cover_edit.toPlainText() == before
    dlg.close()


def test_approve_saves_the_generated_preview_bytes(qapp, tmp_path, monkeypatch):
    """Confirm stores preview.cover_letter_preview, not a typed editor value."""
    from PySide6.QtWidgets import QMessageBox

    from apply.preview import build_application_preview
    from core.config import ExtractReview, SourcedText
    from core.cover_letter import approve_cover_letter
    from core.models import Job

    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)
    cfg = _profile_with_licence(tmp_path, "B")
    cfg.profile.extract_review = ExtractReview(source="cv", confirmed=True)
    cfg.profile.qualifications.skills = [SourcedText(value="Excel", source="manual")]
    job = Job(
        id="vorschau-speichern",
        title="Disponent",
        company="Nordlicht GmbH",
        remote_type="remote",
        description="Excel und Tourenplanung.",
    )
    preview = build_application_preview(job, cfg)
    assert preview.cover_letter_preview.strip()
    seen: dict[str, str] = {}
    original = approve_cover_letter

    def wrapped(job, config, text=None):
        seen["text"] = text
        return original(job, config, text)

    monkeypatch.setattr("core.cover_letter.approve_cover_letter", wrapped)
    dlg = ApplyPreviewDialog(preview, config=cfg, job=job)
    dlg.show()
    qapp.processEvents()
    assert dlg.approve_btn.isEnabled()
    dlg.approve_btn.click()
    qapp.processEvents()
    assert seen["text"] == preview.cover_letter_preview
    saved = tmp_path / "cover_letters" / f"{job.id}.txt"
    assert saved.read_bytes() == preview.cover_letter_preview.encode("utf-8")
    dlg.close()


def _shipped_class_c_profile(tmp_path, codes: list[str], skills: list[str]):
    from core.config import ExtractReview, SourcedText
    from core.models import Job

    cfg = _profile_with_licence(tmp_path, codes[0] if codes else "B")
    cfg.profile.extract_review = ExtractReview(source="cv", confirmed=True)
    cfg.profile.qualifications.driving_license = [
        SourcedText(value=code, source="manual") for code in codes
    ]
    cfg.profile.qualifications.skills = [
        SourcedText(value=skill, source="manual") for skill in skills
    ]
    job = Job(
        id="vorschau-neu",
        title="Disponent",
        company="Nordlicht GmbH",
        remote_type="remote",
        description="Excel und Führerschein Klasse C sind erforderlich.",
    )
    return cfg, job


def test_reopen_after_confirming_class_c_enables_and_saves(qapp, tmp_path, monkeypatch):
    """Closing, confirming C, and opening again rebuilds the letter and saves it."""
    import core.cover_guard as guard
    from PySide6.QtWidgets import QMessageBox

    from apply.preview import build_application_preview
    from core.config import SourcedText

    prepares = {"n": 0}
    original_prepare = guard.prepare_cover_check

    def counting_prepare(*args, **kwargs):
        prepares["n"] += 1
        return original_prepare(*args, **kwargs)

    monkeypatch.setattr(guard, "prepare_cover_check", counting_prepare)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)
    cfg, job = _shipped_class_c_profile(tmp_path, ["B"], ["Führerschein Klasse C"])
    first = build_application_preview(job, cfg)
    dlg = ApplyPreviewDialog(first, config=cfg, job=job)
    dlg.show()
    qapp.processEvents()
    assert prepares["n"] == 1
    assert not dlg.approve_btn.isEnabled()
    _assert_class_c_sentence_is_quoted_from_the_letter(dlg)
    dlg.close()
    qapp.processEvents()
    saved = tmp_path / "cover_letters" / f"{job.id}.txt"
    assert not saved.exists()
    cfg.profile.qualifications.driving_license = [SourcedText(value="C", source="manual")]
    second = build_application_preview(job, cfg)
    assert "Führerschein Klasse C" in second.cover_letter_preview
    again = ApplyPreviewDialog(second, config=cfg, job=job)
    again.show()
    qapp.processEvents()
    assert prepares["n"] == 2
    assert again._prepared is not dlg._prepared
    assert "C" in again._prepared.licence_codes
    assert again.approve_btn.isEnabled()
    assert "Prüfen nötig" not in again.status_chip.text()
    again.approve_btn.click()
    qapp.processEvents()
    assert saved.read_bytes() == second.cover_letter_preview.encode("utf-8")
    again.close()


def test_reopen_after_removing_the_skill_enables_and_saves(qapp, tmp_path, monkeypatch):
    """Closing, removing the skill, and opening again rebuilds a letter that saves."""
    import core.cover_guard as guard
    from PySide6.QtWidgets import QMessageBox

    from apply.preview import build_application_preview
    from core.config import SourcedText

    prepares = {"n": 0}
    original_prepare = guard.prepare_cover_check

    def counting_prepare(*args, **kwargs):
        prepares["n"] += 1
        return original_prepare(*args, **kwargs)

    monkeypatch.setattr(guard, "prepare_cover_check", counting_prepare)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)
    cfg, job = _shipped_class_c_profile(
        tmp_path, ["B"], ["Excel", "Führerschein Klasse C"]
    )
    first = build_application_preview(job, cfg)
    dlg = ApplyPreviewDialog(first, config=cfg, job=job)
    dlg.show()
    qapp.processEvents()
    assert not dlg.approve_btn.isEnabled()
    assert _PATH_FOR_CLASS_C in dlg._guard_notice.text()
    assert "Führerschein Klasse C" in dlg._guard_notice.text()
    dlg.close()
    qapp.processEvents()
    saved = tmp_path / "cover_letters" / f"{job.id}.txt"
    assert not saved.exists()
    cfg.profile.qualifications.skills = [SourcedText(value="Excel", source="manual")]
    second = build_application_preview(job, cfg)
    assert "Führerschein Klasse C" not in second.cover_letter_preview
    assert second.cover_letter_preview != first.cover_letter_preview
    again = ApplyPreviewDialog(second, config=cfg, job=job)
    again.show()
    qapp.processEvents()
    assert prepares["n"] == 2
    assert again._prepared is not dlg._prepared
    assert again.cover_edit.toPlainText() == second.cover_letter_preview
    assert again.approve_btn.isEnabled()
    again.approve_btn.click()
    qapp.processEvents()
    assert saved.read_bytes() == second.cover_letter_preview.encode("utf-8")
    again.close()
