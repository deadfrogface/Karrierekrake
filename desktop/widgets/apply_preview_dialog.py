"""Pre-submit application preview dialog with READY/WARNING/BLOCKED gate."""

from __future__ import annotations

import webbrowser

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from apply.preview import ApplicationPreview
from desktop.i18n import tr


class ApplyPreviewDialog(QDialog):
    """Show intended form values / documents before any real submit."""

    def __init__(self, preview: ApplicationPreview, parent=None, *, config=None, job=None) -> None:
        super().__init__(parent)
        self.preview = preview
        self._config = config
        self._job = job
        self.setWindowTitle(tr("apps.preview_title"))
        self.resize(720, 560)

        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.gate = QLabel()
        self.gate.setWordWrap(True)
        self.body = QPlainTextEdit()
        self.body.setReadOnly(True)
        self.body.setPlainText(preview.text_report())

        self.open_url_btn = QPushButton(tr("btn.open_manual"))
        self.open_url_btn.clicked.connect(self._open_url)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        close_btn = buttons.button(QDialogButtonBox.StandardButton.Close)
        if close_btn:
            close_btn.setText(tr("btn.close") if tr("btn.close") != "btn.close" else "Schließen")
        self.approve_btn = QPushButton(tr("approval.approve"))
        self.approve_btn.setObjectName("PrimaryButton")
        can_approve = (
            config is not None
            and job is not None
            and bool((preview.cover_letter_preview or "").strip())
            and not preview.cover_refusal_code
        )
        self.approve_btn.setEnabled(can_approve)
        self.approve_btn.setVisible(can_approve)
        self.approve_btn.clicked.connect(self._approve)
        buttons.addButton(self.approve_btn, QDialogButtonBox.ButtonRole.ActionRole)

        top = QHBoxLayout()
        top.addWidget(self.summary, 1)
        top.addWidget(self.open_url_btn)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.gate)
        layout.addWidget(self.body, 1)
        layout.addWidget(buttons)

        submit_note = (
            tr("apps.preview_will_submit")
            if preview.will_submit
            else tr("apps.preview_no_submit")
        )
        if submit_note.startswith("apps."):
            submit_note = (
                "Finales Absenden wäre erlaubt."
                if preview.will_submit
                else "Finales Absenden ist blockiert (Dry-Run / Review)."
            )
        title = tr("apps.preview_title")
        if title.startswith("apps."):
            title = "Bewerbungsvorschau (vor Absenden)"
        self.setWindowTitle(title)
        company = preview.company or "—"
        doc = ""
        if preview.document_filename or preview.document_role:
            doc = (
                f"<br/>Dokument: <b>{preview.document_role or 'cv'}</b> — "
                f"{preview.document_filename or '—'}"
            )
        self.summary.setText(
            f"<b>{company}</b> — {preview.title}<br/>"
            f"ATS: {preview.ats} ({preview.ats_support})<br/>{submit_note}{doc}"
        )
        gate = getattr(preview, "quality_gate", "WARNING") or "WARNING"
        gate_key = {
            "READY": tr("apps.gate_ready"),
            "WARNING": tr("apps.gate_warning"),
            "BLOCKED": tr("apps.gate_blocked"),
        }.get(gate, gate)
        if str(gate_key).startswith("apps."):
            gate_key = {
                "READY": "Qualität: READY — bereit zur Vorbereitung",
                "WARNING": "Qualität: WARNING — bitte prüfen",
                "BLOCKED": "Qualität: BLOCKED — CV/Profil blockiert",
            }.get(gate, gate)
        color = {"READY": "#1b7f3a", "WARNING": "#9a6b00", "BLOCKED": "#a11"}.get(gate, "#333")
        refusal = ""
        if preview.cover_refusal_code:
            refusal_text = tr(preview.cover_refusal_key) if preview.cover_refusal_key else ""
            if refusal_text == preview.cover_refusal_key:
                refusal_text = preview.cover_refusal_code
            refusal = (
                f"<br/><span style='color:#a11; font-weight:600'>"
                f"{preview.cover_refusal_code}: {refusal_text}</span>"
            )
        self.gate.setText(
            f"<span style='color:{color}; font-weight:600'>{gate_key}</span>{refusal}"
        )

    def _approve(self) -> None:
        from core.cover_letter import CoverLetterRefused, approve_cover_letter

        if self._config is None or self._job is None:
            return
        try:
            path = approve_cover_letter(self._job, self._config, self.preview.cover_letter_preview)
        except CoverLetterRefused as exc:
            lang = getattr(self._config.settings, "language", "de")
            QMessageBox.warning(self, tr("apps.preview_title"), exc.refusal.text(lang))
            return
        QMessageBox.information(self, tr("apps.preview_title"), tr("cover.saved") + f"\n{path}")
        self.accept()

    def _open_url(self) -> None:
        url = self.preview.application_url
        if url:
            webbrowser.open(url)
