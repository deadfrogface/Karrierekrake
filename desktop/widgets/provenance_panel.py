"""'Woher stammt das?' under a cover letter: each sentence with the profile entries or ad it is built from."""

from __future__ import annotations

from html import escape

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QTextBrowser, QToolButton, QVBoxLayout, QWidget

from core.cover_provenance import SentenceSource, explain_sentences

_CHIP = {
    "station": ("#0F766E", "#CCFBF1"), "task": ("#0F766E", "#CCFBF1"), "education": ("#1D4ED8", "#DBEAFE"),
    "skill": ("#6D28D9", "#EDE9FE"), "software": ("#6D28D9", "#EDE9FE"), "language": ("#B45309", "#FEF3C7"),
    "certificate": ("#1D4ED8", "#DBEAFE"), "ad": ("#475569", "#E2E8F0"),
}


def render_html(rows: list[SentenceSource]) -> str:
    if not rows:
        return "<p>Noch kein Anschreiben.</p>"
    out = []
    for row in rows:
        chips = []
        for source in row.sources:
            fg, bg = _CHIP.get(source.kind, ("#475569", "#E2E8F0"))
            chips.append(f"<span style='color:{fg};background:{bg};'>&nbsp;{escape(source.label)}&nbsp;</span>")
        origin = " ".join(chips) if chips else "<i style='color:#64748B'>Standardformulierung, keine Angabe aus deinem Profil</i>"
        out.append(f"<p style='margin:0 0 9px 0'>{escape(row.text)}<br>{origin}</p>")
    return "".join(out)


class ProvenancePanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.toggle = QToolButton()
        self.toggle.setText("Woher stammt das?  ▸")
        self.toggle.setCheckable(True)
        self.toggle.setAutoRaise(True)
        self.toggle.setStyleSheet("QToolButton{background:transparent;border:none;color:#0F766E;font-weight:600;}")
        self.toggle.toggled.connect(self._toggled)
        self.view = QTextBrowser()
        self.view.setMinimumHeight(150)
        self.view.hide()
        layout.addWidget(self.toggle)
        layout.addWidget(self.view)
        self._source_provider = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self.refresh)
        self._text = ""

    def bind(self, text_getter, qualifications, *, job_title: str, company: str) -> None:
        self._text_getter = text_getter
        self._quals = qualifications
        self._job_title = job_title
        self._company = company

    def schedule_refresh(self) -> None:
        if self.view.isVisible():
            self._timer.start()

    def _toggled(self, shown: bool) -> None:
        self.toggle.setText("Woher stammt das?  ▾" if shown else "Woher stammt das?  ▸")
        self.view.setVisible(shown)
        if shown:
            self.refresh()

    def refresh(self) -> None:
        getter = getattr(self, "_text_getter", None)
        if getter is None:
            return
        rows = explain_sentences(getter(), self._quals, job_title=self._job_title, company=self._company)
        self.view.setHtml(render_html(rows))
