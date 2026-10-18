"""Calm pre-submit application review dialog (Karrierekrake design system).

Shows job + draft status, then separate CV / cover / form sections.
Technical fields (ATS, dry-run flags, URL, …) stay behind „Technische Details“.
Does not change submit or safety logic — only presentation and labels.
"""

from __future__ import annotations

import webbrowser
from typing import Iterable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from apply.preview import ApplicationPreview
from desktop.design_system.a11y import set_accessible_description, set_accessible_name
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


def _cover_refusal_text(preview: ApplicationPreview) -> str:
    """German (or active-language) refusal. The reason code stays out of the UI."""
    keys = {
        "job_incomplete": "cover.job_incomplete",
        "no_evidence": "cover.no_evidence",
        "company_missing": "cover.company_missing",
        "blocked_demo": "cover.demo_excluded",
    }
    key = (preview.cover_refusal_key or "").strip() or keys.get(preview.cover_refusal_code, "")
    text = tr(key) if key else ""
    if not text or text == key or text.startswith("cover."):
        fallback = keys.get(preview.cover_refusal_code, "cover.no_evidence")
        text = tr(fallback)
    if not text or text.startswith("cover."):
        return "Das Anschreiben kann so nicht erstellt werden."
    return text


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
        self._prepared = None
        # Teamlead #190: confirmations are keys bound to the letter text
        # (sha256 of letter, sentence, kind); a new text means new keys.
        self._confirmed_keys: set[str] = set()
        self._shown_finding_keys: tuple[str, ...] = ()
        self.finding_checks: list[QCheckBox] = []
        self.finding_labels: list[QLabel] = []
        self._rewrite_active = False
        self._rewrite_closed = False
        self.finished.connect(self._stop_rewrite_updates)
        if config is not None:
            self._prepared = self._build_prepared_check()
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
            refusal = QLabel(_cover_refusal_text(preview))
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
        self._guard_notice = QLabel()
        self._guard_notice.setObjectName("KkErrorText")
        self._guard_notice.setWordWrap(True)
        self._guard_notice.hide()
        cover_body.addWidget(self._guard_notice)
        # One row per confirmable finding: sentence + reason as text and a
        # checkbox „Trotzdem freigeben“. Built by _show_findings.
        self.findings_box = QWidget()
        self.findings_box.setObjectName("PreviewGuardFindings")
        self._findings_layout = QVBoxLayout(self.findings_box)
        self._findings_layout.setContentsMargins(0, 4, 0, 0)
        self._findings_layout.setSpacing(6)
        self.findings_notice = QLabel()
        self.findings_notice.setObjectName("KkHint")
        self.findings_notice.setWordWrap(True)
        self._findings_layout.addWidget(self.findings_notice)
        self.findings_box.hide()
        cover_body.addWidget(self.findings_box)
        # Rewrite draft with findings (Teamlead #190): shown next to the old
        # text, which stays the default until the user adopts the draft.
        self._draft_text = ""
        self.draft_checks: list[QCheckBox] = []
        self.draft_labels: list[QLabel] = []
        self.draft_box = QWidget()
        self.draft_box.setObjectName("PreviewRewriteDraft")
        self._draft_layout = QVBoxLayout(self.draft_box)
        self._draft_layout.setContentsMargins(0, 4, 0, 0)
        self._draft_layout.setSpacing(6)
        self.draft_notice = QLabel(tr("apps.preview_draft_intro"))
        self.draft_notice.setObjectName("KkHint")
        self.draft_notice.setWordWrap(True)
        set_accessible_name(self.draft_notice, tr("apps.preview_draft_intro"))
        self._draft_layout.addWidget(self.draft_notice)
        self.draft_view = QTextEdit()
        self.draft_view.setObjectName("PreviewRewriteDraftView")
        self.draft_view.setReadOnly(True)
        self.draft_view.setMinimumHeight(120)
        set_accessible_name(self.draft_view, tr("apps.preview_draft_view"))
        self._draft_layout.addWidget(self.draft_view)
        self._draft_rows = QVBoxLayout()
        self._draft_rows.setSpacing(6)
        self._draft_layout.addLayout(self._draft_rows)
        draft_buttons = QHBoxLayout()
        self.keep_text_btn = QPushButton(tr("apps.preview_draft_keep"))
        self.keep_text_btn.setObjectName("SecondaryButton")
        set_accessible_name(self.keep_text_btn, tr("apps.preview_draft_keep"))
        self.keep_text_btn.clicked.connect(self._discard_draft)
        self.adopt_draft_btn = QPushButton(tr("apps.preview_draft_adopt"))
        self.adopt_draft_btn.setObjectName("SecondaryButton")
        set_accessible_name(self.adopt_draft_btn, tr("apps.preview_draft_adopt"))
        self.adopt_draft_btn.setEnabled(False)
        self.adopt_draft_btn.clicked.connect(self._adopt_draft)
        draft_buttons.addWidget(self.keep_text_btn)
        draft_buttons.addStretch(1)
        draft_buttons.addWidget(self.adopt_draft_btn)
        self._draft_layout.addLayout(draft_buttons)
        self.draft_box.hide()
        cover_body.addWidget(self.draft_box)
        # #190 fix 2: a draft the dialog rejects (hard claim) is never dropped
        # silently. The old text stays; this says so in words, not colour only.
        self.draft_rejected_notice = QLabel()
        self.draft_rejected_notice.setObjectName("KkErrorText")
        self.draft_rejected_notice.setWordWrap(True)
        self.draft_rejected_notice.setTextFormat(Qt.TextFormat.PlainText)
        self.draft_rejected_notice.hide()
        cover_body.addWidget(self.draft_rejected_notice)
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
        self.rewrite_btn = QPushButton("Anschreiben ausformulieren" if getattr(getattr(config, "settings", None), "language", "de") == "de" else "Refine cover letter")
        self.rewrite_btn.setObjectName("SecondaryButton")
        self.rewrite_btn.setVisible(can_approve)
        self.rewrite_btn.clicked.connect(self._start_cover_rewrite)
        footer.addWidget(self.rewrite_btn)
        footer.addWidget(self.open_url_btn)
        footer.addStretch(1)
        footer.addWidget(self.close_btn)
        footer.addWidget(self.approve_btn)
        root.addLayout(footer)

        fit_dialog_to_screen(self, preferred_width=720, preferred_height=640)
        self._run_cover_guard()
        if can_approve:
            from core.cover_quality import local_writer_available
            if local_writer_available():
                QTimer.singleShot(0, self._start_cover_rewrite)

    def _stop_rewrite_updates(self, *_args):
        self._rewrite_closed = True

    def _start_cover_rewrite(self):
        if self._rewrite_active or self._rewrite_closed or self._config is None or self._job is None:
            return
        from core.cover_quality import rewrite_cover_letter
        from desktop.workers import FunctionWorker, connect_queued, start_worker
        self._rewrite_active = True
        self._rewrite_previous_text = self.cover_edit.toPlainText()
        # A chronological template is an internal seed, not the finished
        # application. Do not invite copying it while the writer is running.
        self.cover_edit.clear()
        self.cover_edit.setPlaceholderText("Dein individuelles Anschreiben wird erstellt …" if self._config.settings.language == "de" else "Creating your tailored cover letter …")
        self._rewrite_seed = ""
        self._discard_draft()
        self._guard_notice.hide()
        self.rewrite_btn.setEnabled(False)
        self.approve_btn.setEnabled(False)
        self.status_chip.set_status("Anschreiben wird formuliert …" if self._config.settings.language == "de" else "Drafting cover letter …", kind="info")
        from copy import deepcopy
        config = deepcopy(self._config)
        job = deepcopy(self._job)
        worker = FunctionWorker(lambda: rewrite_cover_letter(job, config))
        connect_queued(worker.finished, self._finish_cover_rewrite)
        connect_queued(worker.failed, self._cover_rewrite_failed)
        self._rewrite_worker = worker
        self._rewrite_thread = start_worker(worker)

    def _cover_rewrite_failed(self, _error):
        from core.cover_quality import CoverRewrite
        self._finish_cover_rewrite(CoverRewrite(False, reason="runtime_error"))

    def _finish_cover_rewrite(self, result):
        self._rewrite_active = False
        if self._rewrite_closed:
            return
        self.draft_rejected_notice.hide()
        self.draft_rejected_notice.clear()
        self.rewrite_btn.setEnabled(True)
        self.cover_edit.setPlaceholderText("")
        # A late model response must never overwrite the user's own edits.
        if result.ok and self.cover_edit.toPlainText() == self._rewrite_seed:
            import hashlib
            self.preview.cover_letter_preview = result.text
            self.preview.cover_letter_sha256 = hashlib.sha256(result.text.encode("utf-8")).hexdigest()
            self.cover_edit.setPlainText(result.text)
            self._run_cover_guard()
        elif not result.ok and result.reason == "needs_confirmation" and result.text:
            # The old text stays the default; the draft waits for a choice.
            if self.cover_edit.toPlainText() == self._rewrite_seed:
                self.cover_edit.setPlainText(self._rewrite_previous_text)
            self._run_cover_guard()
            self._show_draft(result.text)
        elif not result.ok:
            if self.cover_edit.toPlainText() == self._rewrite_seed:
                self.cover_edit.setPlainText(self._rewrite_previous_text)
            self._run_cover_guard()
            german = self._config.settings.language == "de"
            self._guard_notice.setText(
                "Der Entwurf konnte lokal nicht ausreichend ausformuliert und geprüft werden. Bitte die lokale Installation prüfen oder konkrete Tätigkeiten im Profil ergänzen."
                if german else "The local draft could not be refined and verified. Check the local installation or add concrete responsibilities to your profile."
            )
            self._guard_notice.show()
            self._mark_check_needed()
        else:
            self._run_cover_guard()

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

    def _build_prepared_check(self):
        """Classes, employers, degrees and normalized evidence, once per dialog."""
        from core.cover_guard import prepare_cover_check

        job = self._job
        job_text = f"{getattr(job, 'title', '')} {getattr(job, 'description', '')}".strip()
        allowed = f"{getattr(job, 'title', '')} {getattr(job, 'company', '')}".strip()
        return prepare_cover_check(self._config, job_text, allowed)

    def _scan_letter(self, text: str) -> tuple[list[str], bool, str]:
        """Letter-only scan. The profile side stays the object built at open.

        Only findings the user cannot confirm (licence, employer, degree …)
        count here; native / gender / salutation go through _show_findings.
        """
        hard = [f for f in self._findings(text) if not f.confirmable]
        if not hard:
            return [], True, ""
        from core.cover_guard import unconfirmed_licence_codes

        sentence = hard[0].sentence
        codes = unconfirmed_licence_codes(
            sentence,
            confirmed_licences=set(self._prepared.licence_codes),
        )
        return codes, False, sentence

    def _findings(self, text: str) -> list:
        if self._prepared is None or not (text or "").strip():
            return []
        from core.cover_guard import screen_findings

        return screen_findings(text, self._prepared)

    def _guard_message(self, sentence: str, codes: list[str]) -> str:
        if sentence and codes:
            return tr(
                "apps.preview_claim_blocked",
                sentence=sentence,
                classes=", ".join(codes),
            )
        return tr("apps.preview_claim_blocked_generic")

    def _finding_reason(self, finding) -> str:
        if finding.kind == "native":
            if finding.profile_level:
                return tr("apps.preview_reason_native_level", profile=finding.profile_level)
            if finding.language:
                return tr("apps.preview_reason_native_missing", language=finding.language.capitalize())
            return tr("apps.preview_reason_native_unnamed")
        if finding.kind == "gender":
            return tr("apps.preview_reason_gender")
        if finding.kind == "salutation":
            if finding.expected:
                return tr("apps.preview_reason_salutation", expected=finding.expected)
            return tr("apps.preview_reason_salutation_generic")
        return tr("apps.preview_claim_blocked_generic")

    def _clear_findings(self) -> None:
        for widget in self.finding_checks + self.finding_labels:
            self._findings_layout.removeWidget(widget)
            widget.deleteLater()
        self.finding_checks = []
        self.finding_labels = []
        self._shown_finding_keys = ()
        self.findings_box.hide()

    def _finding_rows(self, findings, layout, on_toggle) -> tuple[list[QLabel], list[QCheckBox]]:
        """Sentence + reason (wrapped text) and one checkbox per finding."""
        labels: list[QLabel] = []
        checks: list[QCheckBox] = []
        for finding in findings:
            reason = self._finding_reason(finding)
            label = QLabel(tr("apps.preview_finding_line", sentence=finding.sentence, reason=reason))
            label.setObjectName("KkErrorText")
            label.setWordWrap(True)
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            check = QCheckBox(tr("apps.preview_finding_confirm"))
            check.setObjectName("PreviewFindingConfirm")
            check.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            set_accessible_name(
                check, tr("apps.preview_finding_a11y", sentence=finding.sentence, reason=reason)
            )
            check.setChecked(finding.key in self._confirmed_keys)
            check.toggled.connect(lambda on, f=finding: on_toggle(f, on))
            label.setBuddy(check)
            layout.addWidget(label)
            layout.addWidget(check)
            labels.append(label)
            checks.append(check)
        return labels, checks

    def _show_findings(self, findings) -> None:
        keys = tuple(f.key for f in findings)
        if keys == self._shown_finding_keys and self.finding_checks:
            return
        self._clear_findings()
        if not findings:
            return
        intro = tr("apps.preview_findings_intro")
        self.findings_notice.setText(intro)
        set_accessible_name(self.findings_notice, intro)
        set_accessible_description(
            self.findings_notice,
            " ".join(f"„{f.sentence}“ {self._finding_reason(f)}" for f in findings),
        )
        self.finding_labels, self.finding_checks = self._finding_rows(
            findings, self._findings_layout, self._on_finding_toggled
        )
        self._shown_finding_keys = keys
        self.findings_box.show()
        # Designer: after the check the focus is on the first finding.
        first = self.finding_checks[0]
        first.setFocus(Qt.FocusReason.OtherFocusReason)
        QTimer.singleShot(0, lambda: first.setFocus(Qt.FocusReason.OtherFocusReason))

    def _show_draft(self, draft: str) -> None:
        """Draft with the affected sentences marked »…« (text, not colour only)."""
        import html

        self._discard_draft()
        all_findings = self._findings(draft)
        hard = [f for f in all_findings if not f.confirmable]
        if hard:
            text = tr("apps.preview_draft_rejected", sentence=hard[0].sentence)
            self.draft_rejected_notice.setText(text)
            set_accessible_name(self.draft_rejected_notice, text)
            self.draft_rejected_notice.show()
            return
        findings = [f for f in all_findings if f.confirmable]
        if not findings:
            return
        self._draft_text = draft
        marked = html.escape(draft)
        for sentence in dict.fromkeys(f.sentence for f in findings):
            safe = html.escape(sentence)
            marked = marked.replace(safe, f"<b><u>»{safe}«</u></b>", 1)
        self.draft_view.setHtml(marked.replace("\n", "<br>"))
        self.draft_labels, self.draft_checks = self._finding_rows(
            findings, self._draft_rows, lambda f, on: self._on_draft_toggled(f, on)
        )
        self.adopt_draft_btn.setEnabled(False)
        self.draft_box.show()
        first = self.draft_checks[0]
        first.setFocus(Qt.FocusReason.OtherFocusReason)

    def _on_draft_toggled(self, finding, on: bool) -> None:
        self._on_finding_toggled(finding, on)
        self.adopt_draft_btn.setEnabled(
            bool(self.draft_checks) and all(c.isChecked() for c in self.draft_checks)
        )

    def _discard_draft(self) -> None:
        for widget in self.draft_checks + self.draft_labels:
            self._draft_rows.removeWidget(widget)
            widget.deleteLater()
        self.draft_checks = []
        self.draft_labels = []
        self._draft_text = ""
        self.draft_view.clear()
        self.adopt_draft_btn.setEnabled(False)
        self.draft_box.hide()

    def _adopt_draft(self) -> None:
        """Only after every draft finding is confirmed one by one."""
        draft = self._draft_text
        if not draft or not self.draft_checks or not all(c.isChecked() for c in self.draft_checks):
            return
        import hashlib

        self._discard_draft()
        self.preview.cover_letter_preview = draft
        self.preview.cover_letter_sha256 = hashlib.sha256(draft.encode("utf-8")).hexdigest()
        self.cover_edit.setPlainText(draft)
        self._run_cover_guard()

    def _on_finding_toggled(self, finding, on: bool) -> None:
        if on:
            if finding.key not in self._confirmed_keys:
                self._confirmed_keys.add(finding.key)
                self._log_confirmation(finding)
        else:
            self._confirmed_keys.discard(finding.key)
        self._sync_after_findings()

    def _log_confirmation(self, finding) -> None:
        """Local JSONL only: key, kind, job id, time. No sentence text, no network."""
        root = getattr(self._config, "root", None)
        if not root:
            return
        import json
        from datetime import UTC, datetime
        from pathlib import Path

        row = {
            "key": finding.key,
            "kind": finding.kind,
            "job_id": str(getattr(self._job, "id", "") or ""),
            "ts": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        try:
            path = Path(root) / "logs" / "cover_guard_confirmations.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def _open_findings(self) -> bool:
        return any(not check.isChecked() for check in self.finding_checks)

    def _sync_after_findings(self) -> None:
        text = self.preview.cover_letter_preview or ""
        _codes, hard_ok, _sentence = self._scan_letter(text)
        if not hard_ok:
            self._mark_check_needed()
            return
        if self._open_findings():
            self._mark_check_needed()
            return
        self._apply_status_chip()
        self._sync_approve_button(blocked=False)

    def _sync_approve_button(self, *, blocked: bool) -> None:
        can = (
            self._config is not None
            and self._job is not None
            and bool(self.cover_edit.toPlainText().strip())
            and not self.preview.cover_refusal_code
        )
        self.approve_btn.setVisible(can)
        self.approve_btn.setEnabled(can and not blocked and not self._rewrite_active)

    def _mark_check_needed(self) -> None:
        self.status_chip.set_status(tr("apps.preview_status_check"), kind="warn")
        self._sync_approve_button(blocked=True)

    def _run_cover_guard(self) -> bool:
        """Scan the letter on screen. Opening and confirming each run it in full.

        True only when there is no hard finding and every confirmable finding
        of exactly this letter text is confirmed (Teamlead #190).
        """
        text = self.preview.cover_letter_preview or ""
        findings = self._findings(text)
        self._show_findings([f for f in findings if f.confirmable])
        codes, ok, sentence = self._scan_letter(text)
        if not ok:
            self._guard_notice.setText(self._guard_message(sentence, codes))
            self._guard_notice.show()
            self._mark_check_needed()
            return False
        self._guard_notice.hide()
        self._guard_notice.clear()
        if self._open_findings():
            self._mark_check_needed()
            return False
        self._apply_status_chip()
        self._sync_approve_button(blocked=False)
        return True

    def _config_for_approval(self):
        """Profile at approval time. A saved edit after the preview must count."""
        parent = self.parent()
        service = getattr(parent, "config_service", None) if parent is not None else None
        loader = getattr(service, "load", None)
        if callable(loader):
            return loader()
        return self._config

    def _approve(self) -> None:
        from core.cover_letter import CoverLetterRefused, approve_cover_letter

        if self._config is None or self._job is None:
            return
        if not self._run_cover_guard():
            return
        try:
            path = approve_cover_letter(
                self._job,
                self._config_for_approval(),
                self.cover_edit.toPlainText(),
                generated_sha256=self.preview.cover_letter_sha256,
                profile_fingerprint=self.preview.cover_profile_fingerprint,
            )
        except CoverLetterRefused as exc:
            lang = getattr(self._config.settings, "language", "de")
            if exc.refusal.message_key == "cover.preview_stale":
                self._guard_notice.setText(exc.refusal.text(lang))
                self._guard_notice.show()
                self._sync_approve_button(blocked=True)
                return
            QMessageBox.warning(self, self.windowTitle(), exc.refusal.text(lang))
            return
        except ValueError:
            QMessageBox.warning(self, self.windowTitle(), tr("cover.preview_required"))
            return
        QMessageBox.information(self, self.windowTitle(), tr("cover.saved") + f"\n{path}")
        self.accept()

    def _open_url(self) -> None:
        url = self.preview.application_url
        if url:
            webbrowser.open(url)
