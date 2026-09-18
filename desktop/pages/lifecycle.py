"""Lifecycle page — cases, ambiguous email review, follow-up tasks."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
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
from integrations.interview_prep import build_interview_prep
from integrations.reply_draft import ReplyAction, SendGate, build_action_draft


class LifecyclePage(QWidget):
    def __init__(self, config_service: ConfigService, parent=None) -> None:
        super().__init__(parent)
        self.config_service = config_service

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
        self.link_btn.clicked.connect(self.link_selected_email)
        self.draft_btn = QPushButton()
        self.draft_btn.setObjectName("SecondaryButton")
        self.draft_btn.clicked.connect(self.draft_followup)
        self.prep_btn = QPushButton()
        self.prep_btn.setObjectName("SecondaryButton")
        self.prep_btn.clicked.connect(self.show_prep)

        btn_row = QHBoxLayout()
        for b in (
            self.refresh_btn,
            self.followup_btn,
            self.link_btn,
            self.draft_btn,
            self.prep_btn,
        ):
            btn_row.addWidget(b)
        btn_row.addStretch()

        self.cases = QTableWidget(0, 5)
        self.cases.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.cases.setAlternatingRowColors(True)
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

        layout = QVBoxLayout(self)
        layout.addWidget(self.page_title)
        layout.addWidget(self.page_subtitle)
        layout.addLayout(btn_row)
        layout.addWidget(self.stats_label)
        layout.addWidget(self.cases, 3)
        layout.addWidget(QLabel("Ambiguous / review"))
        link_row = QHBoxLayout()
        link_row.addWidget(self.case_picker, 1)
        layout.addLayout(link_row)
        layout.addWidget(self.emails, 2)
        layout.addWidget(self.tasks_label)
        self.retranslate()

    def retranslate(self) -> None:
        self.page_title.setText(tr("nav.lifecycle"))
        self.page_subtitle.setText(tr("lifecycle.subtitle"))
        self.refresh_btn.setText(tr("btn.refresh"))
        self.followup_btn.setText(tr("lifecycle.followups"))
        self.link_btn.setText(tr("lifecycle.link_email"))
        self.draft_btn.setText(tr("lifecycle.draft_reply"))
        self.prep_btn.setText(tr("lifecycle.interview_prep"))
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
            self.cases.setItem(r, 0, QTableWidgetItem(c.status))
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

    def generate_followups(self) -> None:
        cfg = self.config_service.load()
        db = self._db()
        n = refresh_follow_up_tasks(
            db,
            follow_up_days=int(cfg.settings.follow_up_days),
            ghosted_days=int(cfg.settings.ghosted_days),
        )
        QMessageBox.information(
            self, tr("nav.lifecycle"), tr("lifecycle.followups_done").format(n=n)
        )
        self.refresh()

    def link_selected_email(self) -> None:
        row = self.emails.currentRow()
        if row < 0:
            QMessageBox.information(self, tr("nav.lifecycle"), tr("lifecycle.select_email"))
            return
        email_id = self.emails.item(row, 3).text()
        case_id = self.case_picker.currentData()
        if not case_id:
            QMessageBox.information(self, tr("nav.lifecycle"), tr("lifecycle.select_case"))
            return
        self._db().resolve_email_association(email_id, str(case_id))
        self.refresh()

    def draft_followup(self) -> None:
        row = self.cases.currentRow()
        if row < 0:
            QMessageBox.information(self, tr("nav.lifecycle"), tr("lifecycle.select_case"))
            return
        case_id = self.cases.item(row, 4).text()
        db = self._db()
        case = db.get_case(case_id)
        if not case:
            return
        cfg = self.config_service.load()
        # Typed FOLLOWUP action — never free-form generation; never auto-send.
        draft = build_action_draft(
            ReplyAction.FOLLOWUP,
            case.to_dict(),
            applicant_name=cfg.application.full_name,
        )
        gate = SendGate(
            allow_send=bool(cfg.settings.allow_employer_email_send),
            draft_only=bool(cfg.settings.email_draft_only),
        )
        draft.draft_only = True
        draft.auto_send = False
        result = gate.attempt_send(
            draft, transport=lambda d: (_ for _ in ()).throw(RuntimeError("blocked"))
        )
        review = "BINDING REVIEW" if draft.requires_explicit_review else "DRAFT ONLY"
        QMessageBox.information(
            self,
            tr("lifecycle.draft_reply"),
            f"Action: {draft.action}\nTo: {draft.to_address}\nSubject: {draft.subject}\n\n"
            f"{draft.body}\n\n"
            f"[{review}] "
            f"{result.send_error or 'ready for approval'}",
        )

    def show_prep(self) -> None:
        row = self.cases.currentRow()
        if row < 0:
            QMessageBox.information(self, tr("nav.lifecycle"), tr("lifecycle.select_case"))
            return
        case_id = self.cases.item(row, 4).text()
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
