"""Zuordnung prüfen — calm ambiguity review (no silent best-match)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from desktop.design_system.a11y import set_accessible_name
from desktop.design_system.v2_chrome import ContentCard
from desktop.i18n import tr


class AssociationReviewDialog(QDialog):
    """Demo-aligned association review: pick a case or leave unlinked.

    Does not invent match percentages. Evidence is company/position/date text only.
    """

    def __init__(
        self,
        *,
        subject: str,
        sender: str,
        excerpt: str,
        candidates: list[dict],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setModal(True)
        self.setMinimumWidth(560)
        self.setMinimumHeight(420)
        self._choice: str | None = None  # case_id or "" for none
        self.setWindowTitle(tr("assoc.title"))

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 16)
        root.setSpacing(14)

        alert = ContentCard()
        alert_body = alert.body()
        alert_title = QLabel(tr("assoc.alert_title"))
        alert_title.setObjectName("NextActionTitle")
        alert_title.setWordWrap(True)
        alert_body_lbl = QLabel(tr("assoc.alert_body"))
        alert_body_lbl.setObjectName("PageSubtitle")
        alert_body_lbl.setWordWrap(True)
        alert_body.addWidget(alert_title)
        alert_body.addWidget(alert_body_lbl)
        root.addWidget(alert)

        mail = ContentCard()
        mb = mail.body()
        mb.addWidget(QLabel(f"{tr('assoc.from')}: {sender or '—'}"))
        mb.addWidget(QLabel(f"{tr('assoc.subject')}: {subject or '—'}"))
        excerpt_lbl = QLabel((excerpt or "")[:400] or "—")
        excerpt_lbl.setObjectName("PageSubtitle")
        excerpt_lbl.setWordWrap(True)
        mb.addWidget(excerpt_lbl)
        root.addWidget(mail)

        pick_card = ContentCard()
        pb = pick_card.body()
        heading = QLabel(tr("assoc.which_application"))
        heading.setObjectName("NextActionTitle")
        pb.addWidget(heading)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        host = QWidget()
        host_l = QVBoxLayout(host)
        host_l.setSpacing(8)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        for i, cand in enumerate(candidates):
            radio = QRadioButton()
            case_id = str(cand.get("id") or "")
            title = str(cand.get("position") or "—")
            company = str(cand.get("company") or "—")
            updated = str(cand.get("updated_at") or cand.get("created_at") or "")[:10]
            radio.setText(f"{title}\n{company}" + (f" · {updated}" if updated else ""))
            radio.setProperty("case_id", case_id)
            self._group.addButton(radio, i)
            host_l.addWidget(radio)
            if i == 0:
                radio.setChecked(True)
        none = QRadioButton(tr("assoc.none"))
        none.setProperty("case_id", "")
        self._group.addButton(none, max(len(candidates), 1))
        if not candidates:
            none.setChecked(True)
        host_l.addWidget(none)
        host_l.addStretch()
        scroll.setWidget(host)
        pb.addWidget(scroll)
        root.addWidget(pick_card, stretch=1)

        hint = QLabel(tr("assoc.no_guess"))
        hint.setObjectName("KkHint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton(tr("btn.cancel"))
        cancel.setObjectName("SecondaryButton")
        cancel.clicked.connect(self.reject)
        confirm = QPushButton(tr("assoc.confirm"))
        confirm.setObjectName("PrimaryButton")
        confirm.clicked.connect(self._accept_choice)
        set_accessible_name(confirm, tr("assoc.confirm"))
        buttons.addWidget(cancel)
        buttons.addWidget(confirm)
        root.addLayout(buttons)

    def _accept_choice(self) -> None:
        btn = self._group.checkedButton()
        if btn is None:
            self._choice = None
            self.reject()
            return
        self._choice = str(btn.property("case_id") or "")
        self.accept()

    @property
    def selected_case_id(self) -> str | None:
        """Chosen case id, empty string for 'none', or None if cancelled."""
        return self._choice
