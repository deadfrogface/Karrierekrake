"""Interview Vorbereitung — structured prep surface (not a message box dump)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from desktop.design_system.a11y import set_accessible_name
from desktop.design_system.v2_chrome import ContentCard, StatusChip
from desktop.i18n import tr
from integrations.interview_prep import InterviewPrep


class InterviewPrepDialog(QDialog):
    """Demo-aligned interview prep: context + talking points, no model internals."""

    def __init__(
        self,
        prep: InterviewPrep,
        *,
        email_excerpt: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setModal(True)
        self.setMinimumSize(720, 520)
        self.setWindowTitle(tr("interview.title"))

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        header = QHBoxLayout()
        title_col = QVBoxLayout()
        title = QLabel(tr("interview.title"))
        title.setObjectName("PageTitle")
        subtitle = QLabel(f"{prep.company} — {prep.position}")
        subtitle.setObjectName("PageSubtitle")
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header.addLayout(title_col, stretch=1)
        chip = StatusChip(tr("interview.status_received"), kind="ok")
        header.addWidget(chip)
        root.addLayout(header)

        cols = QHBoxLayout()
        cols.setSpacing(14)

        left = ContentCard()
        lb = left.body()
        lb.addWidget(self._h(tr("interview.scheduling")))
        if email_excerpt:
            excerpt = QLabel(f"„{email_excerpt[:280]}“")
            excerpt.setObjectName("PageSubtitle")
            excerpt.setWordWrap(True)
            lb.addWidget(excerpt)
        else:
            empty = QLabel(tr("interview.no_excerpt"))
            empty.setObjectName("KkHint")
            empty.setWordWrap(True)
            lb.addWidget(empty)
        cal_hint = QLabel(tr("interview.calendar_hint"))
        cal_hint.setObjectName("KkHint")
        cal_hint.setWordWrap(True)
        lb.addWidget(cal_hint)
        cols.addWidget(left, stretch=5)

        right = ContentCard()
        rb = right.body()
        rb.addWidget(self._h(tr("interview.prep")))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        points_host = QWidget()
        pl = QVBoxLayout(points_host)
        if prep.talking_points:
            for point in prep.talking_points[:16]:
                row = QLabel(f"• {point}")
                row.setWordWrap(True)
                row.setObjectName("PageSubtitle")
                pl.addWidget(row)
        else:
            pl.addWidget(QLabel(tr("interview.no_points")))
        if prep.gaps:
            pl.addWidget(self._h(tr("interview.gaps")))
            for gap in prep.gaps[:6]:
                g = QLabel(f"— {gap.claim}")
                g.setWordWrap(True)
                g.setObjectName("KkHint")
                pl.addWidget(g)
        pl.addStretch()
        scroll.setWidget(points_host)
        rb.addWidget(scroll, stretch=1)
        notes = QTextEdit()
        notes.setPlaceholderText(tr("interview.notes_placeholder"))
        notes.setMaximumHeight(100)
        rb.addWidget(notes)
        cols.addWidget(right, stretch=7)
        root.addLayout(cols, stretch=1)

        buttons = QHBoxLayout()
        buttons.addStretch()
        close_btn = QPushButton(tr("interview.close"))
        close_btn.setObjectName("SecondaryButton")
        close_btn.clicked.connect(self.accept)
        set_accessible_name(close_btn, tr("interview.close"))
        draft_btn = QPushButton(tr("interview.draft_reply"))
        draft_btn.setObjectName("PrimaryButton")
        set_accessible_name(draft_btn, tr("interview.draft_reply"))
        self.want_draft = False
        draft_btn.clicked.connect(self._accept_draft)
        buttons.addWidget(close_btn)
        buttons.addWidget(draft_btn)
        root.addLayout(buttons)

    def _accept_draft(self) -> None:
        self.want_draft = True
        self.accept()

    @staticmethod
    def _h(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("NextActionTitle")
        return lbl
