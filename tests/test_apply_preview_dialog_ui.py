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
