"""Lifecycle / Günther page — timeline, approvals, contextual assist."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.case_pipeline import refresh_follow_up_tasks
from core.database import Database
from core.lifecycle import CaseStatus
from desktop.i18n import tr
from desktop.services import ConfigService
from desktop.viewmodels.approvals import (
    GuentherActionKind,
    ambiguous_mail_approval,
    calendar_proposal_approval,
    contextual_guenther_actions,
    reply_draft_approval,
)
from desktop.viewmodels.case_timeline import build_case_timeline_viewmodel, case_status_i18n_key
from desktop.widgets.product_panels import (
    ApprovalPanel,
    CaseTimelinePanel,
    GuentherActionsBar,
)
from integrations.followup import FollowUpPolicy
from integrations.interview_prep import build_interview_prep
from integrations.reply_draft import SendGate, build_follow_up_draft


class LifecyclePage(QWidget):
    def __init__(self, config_service: ConfigService, parent=None) -> None:
        super().__init__(parent)
        self.config_service = config_service
        self._pending_draft = None
        self._pending_calendar = None
        self._pending_mail: dict | None = None

        self.page_title = QLabel()
        self.page_title.setObjectName("PageTitle")
        self.page_subtitle = QLabel()
        self.page_subtitle.setObjectName("PageSubtitle")
        self.page_subtitle.setWordWrap(True)

        self.refresh_btn = QPushButton()
        self.refresh_btn.setObjectName("PrimaryButton")
        self.refresh_btn.clicked.connect(self.refresh)
        self.followup_btn = QPushButton()
        self.followup_btn.setObjectName("SecondaryButton")
        self.followup_btn.clicked.connect(self.generate_followups)
        self.link_btn = QPushButton()
        self.link_btn.setObjectName("SecondaryButton")
        self.link_btn.clicked.connect(self.prepare_link_email)
        self.draft_btn = QPushButton()
        self.draft_btn.setObjectName("SecondaryButton")
        self.draft_btn.clicked.connect(self.prepare_followup_draft)
        self.prep_btn = QPushButton()
        self.prep_btn.setObjectName("SecondaryButton")
        self.prep_btn.clicked.connect(self.show_prep)
        self.calendar_btn = QPushButton()
        self.calendar_btn.setObjectName("SecondaryButton")
        self.calendar_btn.clicked.connect(self.prepare_calendar_proposal)

        btn_row = QHBoxLayout()
        for b in (
            self.refresh_btn,
            self.followup_btn,
            self.link_btn,
            self.draft_btn,
            self.calendar_btn,
            self.prep_btn,
        ):
            btn_row.addWidget(b)
        btn_row.addStretch()

        self.guenther_bar = GuentherActionsBar()
        self.guenther_bar.action_triggered.connect(self._on_guenther_action)

        self.cases = QTableWidget(0, 5)
        self.cases.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.cases.setAlternatingRowColors(True)
        self.cases.itemSelectionChanged.connect(self._on_case_selected)
        self.cases.horizontalHeader().setStretchLastSection(True)
        for col in (0, 3, 4):
            self.cases.horizontalHeader().setSectionResizeMode(
                col, QHeaderView.ResizeMode.ResizeToContents
            )

        self.emails = QTableWidget(0, 4)
        self.emails.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.emails.setAlternatingRowColors(True)
        self.emails.horizontalHeader().setStretchLastSection(True)

        self.case_picker = QComboBox()
        self.tasks_label = QLabel()
        self.tasks_label.setWordWrap(True)
        self.stats_label = QLabel()
        self.stats_label.setWordWrap(True)
        self.ambiguous_label = QLabel()

        self.timeline = CaseTimelinePanel()
        self.approval = ApprovalPanel()
        self.approval.approved.connect(self._on_approval_confirmed)
        self.approval.cancelled.connect(self._clear_approval)

        left = QVBoxLayout()
        left_host = QWidget()
        left_host.setLayout(left)
        left.addWidget(self.stats_label)
        left.addWidget(self.cases, 3)
        left.addWidget(self.ambiguous_label)
        link_row = QHBoxLayout()
        link_row.addWidget(self.case_picker, 1)
        left.addLayout(link_row)
        left.addWidget(self.emails, 2)
        left.addWidget(self.tasks_label)

        right = QVBoxLayout()
        right_host = QWidget()
        right_host.setLayout(right)
        right.addWidget(self.timeline, 2)
        right.addWidget(self.approval)
        right.addWidget(self.guenther_bar)

        splitter = QSplitter()
        splitter.addWidget(left_host)
        splitter.addWidget(right_host)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        layout = QVBoxLayout(self)
        layout.addWidget(self.page_title)
        layout.addWidget(self.page_subtitle)
        layout.addLayout(btn_row)
        layout.addWidget(splitter, 1)
        self._chrome_widgets = [
            self.page_title,
            self.page_subtitle,
            self.refresh_btn,
            self.followup_btn,
            self.link_btn,
            self.draft_btn,
            self.calendar_btn,
            self.prep_btn,
            self.stats_label,
            self.cases,
            self.ambiguous_label,
            self.emails,
            self.tasks_label,
            self.case_picker,
        ]
        self._btn_row_host = btn_row
        self.retranslate()

    def set_embedded_inbox_mode(self, enabled: bool) -> None:
        """When embedded in Postfach shell: hide permanent control wall."""
        for w in self._chrome_widgets:
            w.setVisible(not enabled)
        # Keep approval + timeline + guenther for contextual use.
        self.page_title.setVisible(False if enabled else True)
        self.page_subtitle.setVisible(False if enabled else True)

    def retranslate(self) -> None:
        self.page_title.setText(tr("nav.guenther"))
        self.page_subtitle.setText(tr("lifecycle.subtitle"))
        self.refresh_btn.setText(tr("btn.refresh"))
        self.followup_btn.setText(tr("lifecycle.followups"))
        self.link_btn.setText(tr("lifecycle.link_email"))
        self.draft_btn.setText(tr("lifecycle.draft_reply"))
        self.prep_btn.setText(tr("lifecycle.interview_prep"))
        self.calendar_btn.setText(tr("lifecycle.calendar_proposal"))
        self.ambiguous_label.setText(tr("lifecycle.ambiguous"))
        self.approval.retranslate()
        self.cases.setHorizontalHeaderLabels(
            [
                tr("lifecycle.col.status"),
                tr("lifecycle.col.company"),
                tr("lifecycle.col.position"),
                tr("lifecycle.col.updated"),
                "ID",
            ]
        )
        self.emails.setHorizontalHeaderLabels(
            [
                tr("lifecycle.col.subject"),
                tr("lifecycle.col.sender"),
                tr("lifecycle.col.category"),
                "ID",
            ]
        )

    def _db(self) -> Database:
        return Database(self.config_service.load().db_path)

    def _selected_case_id(self) -> str | None:
        row = self.cases.currentRow()
        if row < 0:
            return None
        item = self.cases.item(row, 4)
        return item.text() if item else None

    def _on_case_selected(self) -> None:
        case_id = self._selected_case_id()
        if not case_id:
            self.timeline.clear()
            self._bind_guenther()
            return
        db = self._db()
        case = db.get_case(case_id)
        if not case:
            return
        events = db.list_lifecycle_events(case_id)
        vm = build_case_timeline_viewmodel(case_id, events, current_status=case.status)
        self.timeline.bind(vm)
        self._bind_guenther(case_id=case_id, job_id=case.job_id or "")

    def _bind_guenther(self, *, case_id: str = "", job_id: str = "") -> None:
        cfg = self.config_service.load()
        enabled = bool(getattr(cfg.settings, "guenther_enabled", False))
        status = ""
        if case_id:
            case = self._db().get_case(case_id)
            status = case.status if case else ""
        actions = contextual_guenther_actions(
            guenther_enabled=enabled,
            case_id=case_id,
            job_id=job_id,
            has_cover_context=bool(job_id),
            has_job_context=bool(job_id),
            has_interview_context=status
            in {
                CaseStatus.INTERVIEW.value,
                CaseStatus.ASSESSMENT.value,
                CaseStatus.CONFIRMATION.value,
                CaseStatus.APPLIED.value,
            },
        )
        self.guenther_bar.bind(actions)

    def refresh(self) -> None:
        db = self._db()
        counts = db.lifecycle_dashboard_counts()
        self.stats_label.setText(
            tr("lifecycle.stats").format(
                cases=counts.get("cases_total", 0),
                ambiguous=counts.get("ambiguous_emails", 0),
                tasks=counts.get("open_tasks", 0),
            )
        )
        cases = db.list_cases(limit=300)
        self.cases.setRowCount(0)
        self.case_picker.clear()
        for c in cases:
            r = self.cases.rowCount()
            self.cases.insertRow(r)
            label = tr(case_status_i18n_key(c.status))
            self.cases.setItem(r, 0, QTableWidgetItem(f"{label} ({c.status})"))
            self.cases.setItem(r, 1, QTableWidgetItem(c.company))
            self.cases.setItem(r, 2, QTableWidgetItem(c.position))
            self.cases.setItem(r, 3, QTableWidgetItem((c.updated_at or "")[:19]))
            self.cases.setItem(r, 4, QTableWidgetItem(c.id))
            self.case_picker.addItem(f"{c.company} — {c.position}", c.id)

        emails = db.list_ambiguous_emails(limit=100)
        self.emails.setRowCount(0)
        for e in emails:
            r = self.emails.rowCount()
            self.emails.insertRow(r)
            self.emails.setItem(r, 0, QTableWidgetItem(e.get("subject") or ""))
            self.emails.setItem(r, 1, QTableWidgetItem(e.get("sender") or ""))
            self.emails.setItem(r, 2, QTableWidgetItem(e.get("category") or ""))
            self.emails.setItem(r, 3, QTableWidgetItem(e.get("id") or ""))

        tasks = db.list_lifecycle_tasks(status="open", limit=20)
        if not tasks:
            self.tasks_label.setText(tr("lifecycle.no_tasks"))
        else:
            lines = [f"• {t.get('title')}: {t.get('body')}" for t in tasks[:8]]
            self.tasks_label.setText("\n".join(lines))
        self._on_case_selected()

    def generate_followups(self) -> None:
        cfg = self.config_service.load()
        db = self._db()
        policy = FollowUpPolicy.from_settings(cfg.settings)
        n = refresh_follow_up_tasks(db, policy=policy)
        QMessageBox.information(
            self, tr("nav.guenther"), tr("lifecycle.followups_done").format(n=n)
        )
        self.refresh()

    def prepare_link_email(self) -> None:
        row = self.emails.currentRow()
        if row < 0:
            QMessageBox.information(self, tr("nav.guenther"), tr("lifecycle.select_email"))
            return
        email_id = self.emails.item(row, 3).text()
        case_id = self.case_picker.currentData()
        if not case_id:
            QMessageBox.information(self, tr("nav.guenther"), tr("lifecycle.select_case"))
            return
        subject = self.emails.item(row, 0).text()
        sender = self.emails.item(row, 1).text()
        self.prepare_link_email_ids(
            email_id=email_id,
            case_id=str(case_id),
            subject=subject,
            sender=sender,
        )

    def prepare_link_email_ids(
        self,
        *,
        email_id: str,
        case_id: str,
        subject: str = "",
        sender: str = "",
    ) -> None:
        self._pending_mail = {"email_id": email_id, "case_id": str(case_id)}
        self._pending_draft = None
        self._pending_calendar = None
        self.approval.bind(
            ambiguous_mail_approval(
                email_id=email_id,
                case_id=str(case_id),
                subject=subject,
                sender=sender,
            )
        )
        self.approval.setVisible(True)

    def prepare_followup_draft(self) -> None:
        case_id = self._selected_case_id()
        if not case_id:
            QMessageBox.information(self, tr("nav.guenther"), tr("lifecycle.select_case"))
            return
        db = self._db()
        case = db.get_case(case_id)
        if not case:
            return
        cfg = self.config_service.load()
        draft = build_follow_up_draft(
            case.to_dict(),
            applicant_name=cfg.application.full_name,
        )
        gate = SendGate(allow_send=bool(cfg.settings.allow_employer_email_send))
        draft.draft_only = bool(cfg.settings.email_draft_only) or not gate.allow_send
        self._pending_draft = draft
        self._pending_calendar = None
        self._pending_mail = None
        self.approval.bind(
            reply_draft_approval(
                case_id=case_id,
                subject=draft.subject,
                body=draft.body,
                approved=False,
                draft_only=draft.draft_only,
                requires_binding_review=bool(draft.requires_explicit_review),
            )
        )

    def prepare_calendar_proposal(self) -> None:
        case_id = self._selected_case_id()
        if not case_id:
            QMessageBox.information(self, tr("nav.guenther"), tr("lifecycle.select_case"))
            return
        db = self._db()
        case = db.get_case(case_id)
        if not case:
            return
        summary = (
            f"{case.company} — {case.position}\n"
            f"{tr('approval.calendar_body')}\n"
            f"Status: {case.status}"
        )
        self._pending_calendar = {"case_id": case_id, "summary": summary}
        self._pending_draft = None
        self._pending_mail = None
        self.approval.bind(
            calendar_proposal_approval(case_id=case_id, summary=summary, approved=False)
        )

    def _clear_approval(self) -> None:
        self._pending_draft = None
        self._pending_calendar = None
        self._pending_mail = None
        self.approval.bind(None)

    def _on_approval_confirmed(self) -> None:
        """Execute only after explicit ApprovalPanel approve — never auto."""
        if self._pending_mail:
            email_id = self._pending_mail["email_id"]
            case_id = self._pending_mail["case_id"]
            self._db().resolve_email_association(email_id, case_id)
            QMessageBox.information(self, tr("nav.guenther"), tr("approval.mail_done"))
            self._clear_approval()
            self.refresh()
            return
        if self._pending_draft is not None:
            cfg = self.config_service.load()
            gate = SendGate(allow_send=bool(cfg.settings.allow_employer_email_send))
            draft = gate.approve(self._pending_draft)
            # Still draft-only unless send is enabled — no auto-send.
            result = gate.attempt_send(
                draft,
                transport=lambda d: (_ for _ in ()).throw(RuntimeError("blocked")),
            )
            QMessageBox.information(
                self,
                tr("lifecycle.draft_reply"),
                f"To: {draft.to_address}\nSubject: {draft.subject}\n\n{draft.body}\n\n"
                f"[{'DRAFT ONLY' if draft.draft_only else 'send gated'}] "
                f"{result.send_error or tr('approval.draft_ready')}",
            )
            self._clear_approval()
            return
        if self._pending_calendar is not None:
            # Proposal acknowledgement only — calendar write stays behind CalendarWriteGate.
            QMessageBox.information(
                self,
                tr("lifecycle.calendar_proposal"),
                tr("approval.calendar_ack")
                + "\n\n"
                + self._pending_calendar.get("summary", ""),
            )
            self._clear_approval()
            return

    def show_prep(self) -> None:
        case_id = self._selected_case_id()
        if not case_id:
            QMessageBox.information(self, tr("nav.guenther"), tr("lifecycle.select_case"))
            return
        db = self._db()
        case = db.get_case(case_id)
        if not case:
            return
        evidence = []
        match_reasons = []
        if case.job_id:
            job = db.get_job(case.job_id)
            if job:
                match_reasons = list(job.match_reasons or [])
        prep = build_interview_prep(
            case_id=case.id,
            company=case.company,
            position=case.position,
            evidence=evidence,
            match_reasons=match_reasons,
        )
        points = "\n".join(f"• {p}" for p in prep.talking_points[:12]) or "—"
        QMessageBox.information(
            self,
            tr("lifecycle.interview_prep"),
            f"{prep.company} — {prep.position}\n\n{points}",
        )

    def _on_guenther_action(self, kind: str) -> None:
        case_id = self._selected_case_id() or ""
        if kind == GuentherActionKind.DRAFT_REPLY.value:
            self.prepare_followup_draft()
            return
        if kind == GuentherActionKind.PREP_INTERVIEW.value:
            self.show_prep()
            return
        if kind == GuentherActionKind.EXPLAIN_JOB.value:
            self._explain_job(case_id)
            return
        if kind == GuentherActionKind.IMPROVE_COVER.value:
            QMessageBox.information(
                self,
                tr("guenther.action.improve_cover"),
                tr("guenther.hint.improve_cover"),
            )

    def _explain_job(self, case_id: str) -> None:
        if not case_id:
            QMessageBox.information(self, tr("nav.guenther"), tr("lifecycle.select_case"))
            return
        db = self._db()
        case = db.get_case(case_id)
        if not case or not case.job_id:
            return
        job = db.get_job(case.job_id)
        if not job:
            return
        from desktop.viewmodels.job_fit import build_job_fit_viewmodel

        fit = build_job_fit_viewmodel(job, self.config_service.load())
        lines = "\n".join(fit.primary_lines(limit=12))
        QMessageBox.information(
            self,
            tr("guenther.action.explain_job"),
            f"{job.title}\n\n{tr('fit.' + fit.headline_key)}\n{lines}",
        )
