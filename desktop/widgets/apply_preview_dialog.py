"""Calm pre-submit application review dialog (Karrierekrake design system).

Shows job + draft status, then separate CV / cover / form sections.
Technical fields (ATS, dry-run flags, URL, …) stay behind „Technische Details“.
Does not change submit or safety logic — only presentation and labels.
"""

from __future__ import annotations

import webbrowser
from typing import Iterable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from apply.preview import ApplicationPreview
from desktop.design_system.a11y import set_accessible_name
from desktop.design_system.polish import apply_button_icon, polish_interactive
from desktop.design_system.v2_chrome import DataItem, ProfileSectionCard, StatusChip
from desktop.i18n import tr
from desktop.widgets.dialog_geometry import fit_dialog_to_screen, wrap_dialog_body


def _looks_missing(value: str | None) -> bool:
    text = (value or "").strip()
    return not text or text in {"—", "-", "(generiert, siehe unten)", "(generiert)"}


def _warning_bucket(warning: str) -> str:
    """Map a warning string to cv | cover | form | general (ui placement only)."""
    low = (warning or "").lower()
    if any(
        token in low
        for token in (
            "cv",
            "lebenslauf",
            "dokument",
            "datei fehlt",
            "nicht lesbar",
        )
    ):
        return "cv"
    if any(
        token in low
        for token in (
            "anschreiben",
            "cover",
            "firmenplatzhalter",
            "bei nan",
        )
    ):
        return "cover"
    if any(
        token in low
        for token in (
            "profil",
            "kontakt",
            "formular",
            "vorname",
            "e-mail",
            "email",
            "firmenname",
        )
    ):
        return "form"
    return "general"


def _is_technical_warning(warning: str) -> bool:
    """Warnings that belong in Technische Details, not the calm review surface."""
    low = (warning or "").lower()
    # Keep automation availability visible (humanized) on the main surface.
    if "automatisierung" in low:
        return False
    return any(
        token in low
        for token in (
            "dry-run",
            "dry run",
            "submit_allowed",
            "review_before_submit",
            "submit-klick",
            "vollautomatik",
            "automatische abgabe",
        )
    )


def _humanize_warning(warning: str) -> str:
    """Softer copy for the main view; technical wording stays in details."""
    low = (warning or "").lower()
    if "dry-run" in low or "submit-klick" in low:
        return tr("apps.preview_hint_no_send")
    if "vollautomatik" in low or "automatische abgabe" in low:
        return tr("apps.preview_hint_no_auto_send")
    if "automatisierung" in low and "nicht verfügbar" in low:
        return tr("apps.preview_hint_manual_finish")
    if "teilweise automatisierung" in low:
        return tr("apps.preview_hint_partial_fill")
    return warning


class ApplyPreviewDialog(QDialog):
    """Review intended form values / documents before any real submit."""

    def __init__(self, preview: ApplicationPreview, parent=None, *, config=None, job=None) -> None:
        super().__init__(parent)
        self.preview = preview
        self._config = config
        self._job = job
        self.setObjectName("ApplyPreviewDialog")
        self.setModal(True)
        self.setMinimumWidth(520)
        self.setMinimumHeight(420)

        title = tr("apps.preview_prepare_title")
        if title.startswith("apps."):
            title = "Bewerbung vorbereiten"
        self.setWindowTitle(title)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 16)
        root.setSpacing(12)

        # --- Header: Stelle + Unternehmen + Status ---
        header = QVBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(6)

        self.job_title = QLabel(preview.title or "—")
        self.job_title.setObjectName("PageTitle")
        self.job_title.setWordWrap(True)
        set_accessible_name(self.job_title, preview.title or "")

        company = preview.company or "—"
        self.company_label = QLabel(company)
        self.company_label.setObjectName("PageSubtitle")
        self.company_label.setWordWrap(True)

        status_row = QHBoxLayout()
        status_row.setContentsMargins(0, 0, 0, 0)
        status_row.setSpacing(8)
        self.status_chip = StatusChip("", kind="info")
        self._apply_status_chip()
        status_row.addWidget(self.status_chip, 0, Qt.AlignmentFlag.AlignLeft)
        status_row.addStretch(1)

        header.addWidget(self.job_title)
        header.addWidget(self.company_label)
        header.addLayout(status_row)
        root.addLayout(header)

        # Back-compat aliases used by older tests / callers
        self.summary = self.company_label
        self.gate = self.status_chip

        # --- Scrollable body ---
        body_host = QWidget()
        body_layout = QVBoxLayout(body_host)
        body_layout.setContentsMargins(0, 0, 4, 0)
        body_layout.setSpacing(12)

        buckets = self._bucket_warnings(preview.warnings)

        # General (non-technical) hints near the top
        self.general_hints = QLabel()
        self.general_hints.setObjectName("PageSubtitle")
        self.general_hints.setWordWrap(True)
        general_lines = [_humanize_warning(w) for w in buckets["general"]]
        if general_lines:
            self.general_hints.setText("\n".join(f"• {line}" for line in general_lines))
        else:
            self.general_hints.hide()
        body_layout.addWidget(self.general_hints)

        # CV section
        self.cv_card = ProfileSectionCard(tr("apps.preview_section_cv"))
        cv_body = self.cv_card.body()
        raw_doc = ((preview.documents or {}).get("CV") or "").strip()
        cv_name = (preview.document_filename or "").strip() or raw_doc or "—"
        self.cv_name = QLabel(cv_name)
        self.cv_name.setObjectName("PageSubtitle")
        self.cv_name.setWordWrap(True)
        cv_body.addWidget(self.cv_name)
        if preview.document_role and preview.document_role != "cv":
            role_note = QLabel(tr("apps.preview_cv_role_note", role=preview.document_role))
            role_note.setObjectName("KkHint")
            role_note.setWordWrap(True)
            cv_body.addWidget(role_note)
        self.cv_hints = self._hint_label(buckets["cv"])
        if self.cv_hints is not None:
            cv_body.addWidget(self.cv_hints)
        if _looks_missing(cv_name) and self.cv_hints is None:
            missing = QLabel(tr("apps.preview_cv_missing"))
            missing.setObjectName("KkErrorText")
            missing.setWordWrap(True)
            cv_body.addWidget(missing)
        body_layout.addWidget(self.cv_card)

        # Cover letter — fully visible + scrollable
        self.cover_card = ProfileSectionCard(tr("apps.preview_section_cover"))
        cover_body = self.cover_card.body()
        self.cover_edit = QPlainTextEdit()
        self.cover_edit.setObjectName("PreviewCoverEdit")
        self.cover_edit.setReadOnly(True)
        self.cover_edit.setPlainText(preview.cover_letter_preview or "")
        self.cover_edit.setMinimumHeight(160)
        self.cover_edit.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        set_accessible_name(self.cover_edit, tr("apps.preview_section_cover"))
        cover_body.addWidget(self.cover_edit, 1)
        self.body = self.cover_edit  # back-compat for tests expecting .body
        if preview.cover_refusal_code:
            refusal_text = tr(preview.cover_refusal_key) if preview.cover_refusal_key else ""
            if refusal_text == preview.cover_refusal_key:
                refusal_text = preview.cover_refusal_code
            refusal = QLabel(f"{preview.cover_refusal_code}: {refusal_text}")
            refusal.setObjectName("KkErrorText")
            refusal.setWordWrap(True)
            cover_body.addWidget(refusal)
        elif not (preview.cover_letter_preview or "").strip():
            empty = QLabel(tr("apps.preview_cover_missing"))
            empty.setObjectName("KkHint")
            empty.setWordWrap(True)
            cover_body.addWidget(empty)
        self.cover_hints = self._hint_label(buckets["cover"])
        if self.cover_hints is not None:
            cover_body.addWidget(self.cover_hints)
        body_layout.addWidget(self.cover_card, 1)

        # Form values
        self.form_card = ProfileSectionCard(tr("apps.preview_section_form"))
        form_body = self.form_card.body()
        form_grid = QGridLayout()
        form_grid.setContentsMargins(0, 0, 0, 0)
        form_grid.setHorizontalSpacing(16)
        form_grid.setVerticalSpacing(10)
        items = list((preview.form_values or {}).items())
        if not items:
            empty_form = QLabel(tr("apps.preview_form_empty"))
            empty_form.setObjectName("KkHint")
            empty_form.setWordWrap(True)
            form_body.addWidget(empty_form)
        else:
            for idx, (key, value) in enumerate(items):
                item = DataItem(key, value or "—")
                if _looks_missing(value):
                    item.value.setObjectName("KkErrorText")
                row, col = divmod(idx, 2)
                form_grid.addWidget(item, row, col)
            form_body.addLayout(form_grid)
        # Screening / answers (if any)
        answers = dict(preview.intended_answers or {})
        for k, v in (preview.screening_questions or {}).items():
            answers.setdefault(k, v)
        if answers:
            answers_title = QLabel(tr("apps.preview_section_answers"))
            answers_title.setObjectName("NextActionTitle")
            form_body.addWidget(answers_title)
            for key, value in answers.items():
                form_body.addWidget(DataItem(key, value or "—"))
        if preview.unknown_fields:
            unk = QLabel(
                tr("apps.preview_unknown_fields")
                + ": "
                + ", ".join(preview.unknown_fields)
            )
            unk.setObjectName("KkHint")
            unk.setWordWrap(True)
            form_body.addWidget(unk)
        self.form_hints = self._hint_label(buckets["form"])
        if self.form_hints is not None:
            form_body.addWidget(self.form_hints)
        body_layout.addWidget(self.form_card)

        # Technical details (collapsed)
        tech_body = QFrame()
        tech_body.setObjectName("DetailPanel")
        tech_lay = QVBoxLayout(tech_body)
        tech_lay.setContentsMargins(12, 10, 12, 10)
        tech_lay.setSpacing(4)
        for label, value in self._tech_rows(preview):
            row = QLabel(f"{label}: {value}")
            row.setObjectName("KkHint")
            row.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            row.setWordWrap(True)
            tech_lay.addWidget(row)
        tech_warnings = [w for w in (preview.warnings or []) if _is_technical_warning(w)]
        if tech_warnings:
            tech_lay.addWidget(QLabel(tr("apps.preview_tech_warnings")))
            for w in tech_warnings:
                wl = QLabel(f"• {w}")
                wl.setObjectName("KkHint")
                wl.setWordWrap(True)
                tech_lay.addWidget(wl)

        self.tech_toggle = QToolButton()
        self.tech_toggle.setText(tr("apps.preview_tech_details"))
        self.tech_toggle.setCheckable(True)
        self.tech_toggle.setChecked(False)
        self.tech_toggle.setObjectName("SecondaryButton")
        self.tech_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        set_accessible_name(self.tech_toggle, tr("apps.preview_tech_details"))
        tech_body.setVisible(False)
        self.tech_toggle.toggled.connect(tech_body.setVisible)
        self.tech_body = tech_body
        body_layout.addWidget(self.tech_toggle)
        body_layout.addWidget(tech_body)
        body_layout.addStretch(0)

        self._scroll = wrap_dialog_body(body_host)
        root.addWidget(self._scroll, 1)

        # --- Footer actions ---
        self.open_url_btn = QPushButton(tr("btn.open_manual"))
        self.open_url_btn.setObjectName("SecondaryButton")
        self.open_url_btn.clicked.connect(self._open_url)
        if not (preview.application_url or "").strip():
            self.open_url_btn.setEnabled(False)

        self.close_btn = QPushButton(tr("btn.close"))
        self.close_btn.setObjectName("SecondaryButton")
        self.close_btn.clicked.connect(self.reject)

        self.approve_btn = QPushButton(tr("apps.preview_confirm_draft"))
        self.approve_btn.setObjectName("PrimaryButton")
        apply_button_icon(self.approve_btn, "check", color="#ffffff")
        polish_interactive(self.approve_btn)
        can_approve = (
            config is not None
            and job is not None
            and bool((preview.cover_letter_preview or "").strip())
            and not preview.cover_refusal_code
        )
        # Never show a misleading submit / Absenden CTA — approve only confirms draft.
        self.approve_btn.setEnabled(can_approve)
        self.approve_btn.setVisible(can_approve)
        self.approve_btn.clicked.connect(self._approve)
        set_accessible_name(self.approve_btn, tr("apps.preview_confirm_draft"))

        # Order: Manuell öffnen (secondary, left of stretch) … Schließen … primary
        footer = QHBoxLayout()
        footer.setContentsMargins(0, 4, 0, 0)
        footer.setSpacing(10)
        footer.addWidget(self.open_url_btn)
        footer.addStretch(1)
        footer.addWidget(self.close_btn)
        footer.addWidget(self.approve_btn)
        root.addLayout(footer)

        fit_dialog_to_screen(self, preferred_width=720, preferred_height=640)

    def _apply_status_chip(self) -> None:
        preview = self.preview
        gate = getattr(preview, "quality_gate", "WARNING") or "WARNING"
        if not preview.will_submit:
            text = tr("apps.preview_status_draft")
            kind = "info"
            if gate == "BLOCKED":
                kind = "danger"
            elif gate == "WARNING":
                kind = "warn"
            self.status_chip.set_status(text, kind=kind)
            return
        # will_submit True still only confirms draft in this dialog — stay honest.
        text = tr("apps.preview_status_ready")
        kind = {"READY": "ok", "WARNING": "warn", "BLOCKED": "danger"}.get(gate, "info")
        self.status_chip.set_status(text, kind=kind)

    def _hint_label(self, warnings: Iterable[str]) -> QLabel | None:
        lines = [_humanize_warning(w) for w in warnings if w]
        if not lines:
            return None
        label = QLabel("\n".join(f"• {line}" for line in lines))
        label.setObjectName("KkErrorText")
        label.setWordWrap(True)
        return label

    def _bucket_warnings(self, warnings: list[str] | None) -> dict[str, list[str]]:
        buckets: dict[str, list[str]] = {
            "cv": [],
            "cover": [],
            "form": [],
            "general": [],
        }
        for warning in warnings or []:
            if _is_technical_warning(warning):
                continue
            buckets[_warning_bucket(warning)].append(warning)
        return buckets

    def _tech_rows(self, preview: ApplicationPreview) -> list[tuple[str, str]]:
        rows = [
            (tr("apps.preview_tech_url"), preview.application_url or "—"),
            (tr("apps.preview_tech_ats"), f"{preview.ats} ({preview.ats_support})"),
            (tr("apps.preview_tech_mode"), preview.mode or "—"),
            (tr("apps.preview_tech_dry_run"), tr("dash.on") if preview.dry_run else tr("dash.off")),
            (
                tr("apps.preview_tech_submit_allowed"),
                tr("dash.on") if preview.submit_allowed else tr("dash.off"),
            ),
            (
                tr("apps.preview_tech_will_submit"),
                tr("dash.on") if preview.will_submit else tr("dash.off"),
            ),
            (tr("apps.preview_tech_gate"), preview.quality_gate or "—"),
            (tr("apps.preview_tech_match"), f"{int(preview.match_score or 0)}%"),
        ]
        if preview.ats_note:
            rows.append((tr("apps.preview_tech_ats_note"), preview.ats_note))
        if preview.document_role or preview.document_filename:
            rows.append(
                (
                    tr("apps.preview_tech_document"),
                    f"{preview.document_role or 'cv'} / {preview.document_filename or '—'}",
                )
            )
        return rows

    def _approve(self) -> None:
        from core.cover_letter import CoverLetterRefused, approve_cover_letter

        if self._config is None or self._job is None:
            return
        try:
            path = approve_cover_letter(self._job, self._config, self.preview.cover_letter_preview)
        except CoverLetterRefused as exc:
            lang = getattr(self._config.settings, "language", "de")
            QMessageBox.warning(self, self.windowTitle(), exc.refusal.text(lang))
            return
        QMessageBox.information(self, self.windowTitle(), tr("cover.saved") + f"\n{path}")
        self.accept()

    def _open_url(self) -> None:
        url = self.preview.application_url
        if url:
            webbrowser.open(url)
