"""V2 Zuordnung + Interview dialog smoke tests."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication, QDialog

from desktop.i18n import TRANSLATIONS, i18n, tr
from desktop.widgets.association_review_dialog import AssociationReviewDialog
from desktop.widgets.interview_prep_dialog import InterviewPrepDialog
from integrations.interview_prep import InterviewPrep, PrepItem


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


ASSOC_KEYS = (
    "assoc.title",
    "assoc.alert_title",
    "assoc.alert_body",
    "assoc.from",
    "assoc.subject",
    "assoc.which_application",
    "assoc.none",
    "assoc.no_guess",
    "assoc.confirm",
    "assoc.left_unlinked",
)

INTERVIEW_KEYS = (
    "interview.title",
    "interview.status_received",
    "interview.scheduling",
    "interview.no_excerpt",
    "interview.calendar_hint",
    "interview.prep",
    "interview.no_points",
    "interview.gaps",
    "interview.notes_placeholder",
    "interview.close",
    "interview.draft_reply",
)


def test_assoc_interview_i18n_keys_parity():
    for key in (*ASSOC_KEYS, *INTERVIEW_KEYS):
        assert key in TRANSLATIONS["de"]
        assert key in TRANSLATIONS["en"]
    assert set(TRANSLATIONS["de"]) == set(TRANSLATIONS["en"])


def test_association_review_dialog_none_choice(qapp):
    i18n.set_language("de")
    dlg = AssociationReviewDialog(
        subject="Einladung",
        sender="hr@example.invalid",
        excerpt="Bitte Termin wählen",
        candidates=[
            {"id": "c1", "company": "Acme", "position": "Backend", "updated_at": "2026-01-01"},
            {"id": "c2", "company": "Acme", "position": "Frontend", "updated_at": "2026-01-02"},
        ],
    )
    assert dlg.windowTitle() == tr("assoc.title")
    # Select "none" radio (last button)
    buttons = dlg._group.buttons()
    assert len(buttons) == 3
    buttons[-1].setChecked(True)
    dlg._accept_choice()
    assert dlg.result() == QDialog.DialogCode.Accepted
    assert dlg.selected_case_id == ""


def test_association_review_dialog_picks_case(qapp):
    dlg = AssociationReviewDialog(
        subject="S",
        sender="a@b.example",
        excerpt="",
        candidates=[{"id": "case-9", "company": "X", "position": "Y"}],
    )
    dlg._group.buttons()[0].setChecked(True)
    dlg._accept_choice()
    assert dlg.selected_case_id == "case-9"


def test_interview_prep_dialog_draft_flag(qapp):
    i18n.set_language("de")
    prep = InterviewPrep(
        case_id="c1",
        company="Muster GmbH",
        position="Engineer",
        talking_points=["Punkt A", "Punkt B"],
        gaps=[PrepItem(claim="Cloud", support="NOT_SUPPORTED")],
    )
    dlg = InterviewPrepDialog(prep, email_excerpt="Wir laden Sie ein.")
    assert dlg.windowTitle() == tr("interview.title")
    assert dlg.want_draft is False
    dlg._accept_draft()
    assert dlg.want_draft is True
    assert dlg.result() == QDialog.DialogCode.Accepted
