"""Bewerbungen — demo list + interactive detail (timeline/actions on detail)."""

from __future__ import annotations

import webbrowser

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.database import Database
from core.models import JobStatus
from desktop.design_system.a11y import set_accessible_name
from desktop.design_system.v2_chrome import ContentCard, StatusChip
from desktop.i18n import tr
from desktop.services import ConfigService
from desktop.status_labels import status_label
from desktop.viewmodels.case_timeline import build_case_timeline_viewmodel
from desktop.widgets.product_panels import CaseTimelinePanel


STATUS_FILTERS = [
    "",
    JobStatus.QUEUED.value,
    JobStatus.APPLYING.value,
    JobStatus.APPLIED.value,
    JobStatus.NEEDS_REVIEW.value,
    JobStatus.CAPTCHA.value,
    JobStatus.FAILED.value,
    JobStatus.CLOSED.value,
]


class ApplicationsPage(QWidget):
    def __init__(self, config_service: ConfigService, parent=None) -> None:
        super().__init__(parent)
        self.config_service = config_service
        self._records = []
        self._selected_row = -1

        self.stack = QStackedWidget()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self.stack)

        # --- List surface (demo) ---
        list_page = QWidget()
        list_l = QVBoxLayout(list_page)
        list_l.setContentsMargins(16, 12, 16, 16)
        list_l.setSpacing(12)

        self.page_title = QLabel()
        self.page_title.setObjectName("PageTitle")
        self.page_subtitle = QLabel()
        self.page_subtitle.setObjectName("PageSubtitle")
        self.page_subtitle.setWordWrap(True)
        list_l.addWidget(self.page_title)
        list_l.addWidget(self.page_subtitle)

        toolbar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("apps.search_placeholder"))
        self.search.textChanged.connect(self.refresh)
        self.status = QComboBox()
        self.status.addItem("", "")
        for s in STATUS_FILTERS:
            if s:
                self.status.addItem(s, s)
        self.status.currentIndexChanged.connect(self.refresh)
        self.lbl_status = QLabel()
        self.sort = QComboBox()
        self.sort.addItem("", "updated")
        self.sort.addItem("", "company")
        self.sort.addItem("", "status")
        self.sort.currentIndexChanged.connect(self.refresh)
        self.lbl_sort = QLabel()
        toolbar.addWidget(self.search, stretch=1)
        toolbar.addWidget(self.lbl_status)
        toolbar.addWidget(self.status)
        toolbar.addWidget(self.lbl_sort)
        toolbar.addWidget(self.sort)
        list_l.addLayout(toolbar)

        self.alert = QFrame()
        self.alert.setObjectName("Card")
        alert_l = QHBoxLayout(self.alert)
        self.alert_text = QLabel()
        self.alert_text.setWordWrap(True)
        self.alert_btn = QPushButton()
        self.alert_btn.setObjectName("SecondaryButton")
        self.alert_btn.clicked.connect(self.show_review_only)
        alert_l.addWidget(self.alert_text, stretch=1)
        alert_l.addWidget(self.alert_btn)
        self.alert.hide()
        list_l.addWidget(self.alert)

        self.refresh_btn = QPushButton()
        self.refresh_btn.setObjectName("SecondaryButton")
        self.refresh_btn.clicked.connect(self.refresh)
        self.review_btn = QPushButton()
        self.review_btn.setObjectName("SecondaryButton")
        self.review_btn.clicked.connect(self.show_review_only)
        # Compatibility aliases (preview/open live on detail)
        self.open_btn = QPushButton()
        self.open_btn.hide()
        self.open_btn.clicked.connect(self.open_selected)
        self.preview_btn = QPushButton()
        self.preview_btn.hide()
        self.preview_btn.clicked.connect(self.preview_selected)
        secondary = QHBoxLayout()
        secondary.addWidget(self.refresh_btn)
        secondary.addWidget(self.review_btn)
        secondary.addStretch()
        list_l.addLayout(secondary)

        self.table = QTableWidget(0, 5)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(False)
        self.table.itemSelectionChanged.connect(self._on_selection)
        self.table.doubleClicked.connect(self._open_detail)
        self.table.cellClicked.connect(lambda *_: self._open_detail())
        header = self.table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)

        self.empty = QLabel()
        self.empty.setObjectName("EmptyState")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setVisible(False)
        list_l.addWidget(self.table, 1)
        list_l.addWidget(self.empty)
        self.stack.addWidget(list_page)

        # --- Detail surface ---
        detail_page = QWidget()
        detail_l = QVBoxLayout(detail_page)
        detail_l.setContentsMargins(16, 12, 16, 16)
        detail_l.setSpacing(12)
        top = QHBoxLayout()
        self.back_btn = QPushButton()
        self.back_btn.setObjectName("SecondaryButton")
        self.back_btn.clicked.connect(self._back_to_list)
        top.addWidget(self.back_btn)
        top.addStretch()
        detail_l.addLayout(top)

        head = ContentCard()
        hb = head.body()
        self.detail_title = QLabel()
        self.detail_title.setObjectName("PageTitle")
        self.detail_title.setWordWrap(True)
        self.detail_company = QLabel()
        self.detail_company.setObjectName("PageSubtitle")
        self.detail_status = StatusChip("", kind="info")
        title_row = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.addWidget(self.detail_title)
        title_col.addWidget(self.detail_company)
        title_row.addLayout(title_col, stretch=1)
        title_row.addWidget(self.detail_status)
        hb.addLayout(title_row)
        detail_l.addWidget(head)

        actions = QHBoxLayout()
        self.detail_open = QPushButton()
        self.detail_open.setObjectName("SecondaryButton")
        self.detail_open.clicked.connect(self.open_selected)
        self.detail_preview = QPushButton()
        self.detail_preview.setObjectName("PrimaryButton")
        self.detail_preview.clicked.connect(self.preview_selected)
        actions.addWidget(self.detail_preview)
        actions.addWidget(self.detail_open)
        actions.addStretch()
        detail_l.addLayout(actions)

        self.timeline = CaseTimelinePanel()
        detail_l.addWidget(self.timeline, 1)
        self.stack.addWidget(detail_page)

        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        self.page_title.setText(tr("apps.page_title"))
        self.page_subtitle.setText(tr("apps.page_subtitle"))
        self.lbl_status.setText(tr("jobs.status"))
        self.lbl_sort.setText(tr("apps.sort_label"))
        self.search.setPlaceholderText(tr("apps.search_placeholder"))
        self.status.setItemText(0, tr("jobs.all"))
        for i in range(1, self.status.count()):
            raw = self.status.itemData(i)
            self.status.setItemText(i, status_label(str(raw)))
        sort_labels = {
            "updated": tr("apps.sort_updated"),
            "company": tr("apps.sort_company"),
            "status": tr("apps.sort_status"),
        }
        for i in range(self.sort.count()):
            key = str(self.sort.itemData(i))
            self.sort.setItemText(i, sort_labels.get(key, key))
        self.refresh_btn.setText(tr("btn.refresh"))
        self.review_btn.setText(tr("btn.review_only"))
        self.open_btn.setText(tr("btn.open_manual"))
        self.preview_btn.setText(tr("btn.preview_apply"))
        self.detail_open.setText(tr("btn.open_manual"))
        self.detail_preview.setText(tr("btn.preview_apply"))
        self.back_btn.setText(tr("apps.back"))
        set_accessible_name(self.back_btn, tr("apps.back"))
        self.empty.setText(tr("apps.empty"))
        self.alert_btn.setText(tr("apps.alert_cta"))
        self.table.setHorizontalHeaderLabels(
            [
                tr("apps.col_company_role"),
                tr("jobs.status"),
                tr("apps.date"),
                tr("apps.col_next"),
                tr("col.fit"),
            ]
        )

    def show_review_only(self) -> None:
        idx = self.status.findData(JobStatus.NEEDS_REVIEW.value)
        if idx >= 0:
            self.status.setCurrentIndex(idx)
        self.stack.setCurrentIndex(0)
        self.refresh()

    def _on_selection(self) -> None:
        self._selected_row = self.table.currentRow()
        row = self._selected_row
        if row < 0 or row >= len(self._records):
            self.timeline.clear()
            return
        # Keep timeline bound on selection for compatibility; detail page shows it.
        rec = self._records[row]
        cfg = self.config_service.load()
        db = Database(cfg.db_path)
        case = None
        if rec.job_id:
            cases = db.list_cases(limit=500)
            case = next((c for c in cases if c.job_id == rec.job_id), None)
        if case is None:
            self.timeline.clear()
            return
        events = db.list_lifecycle_events(case.id)
        vm = build_case_timeline_viewmodel(case.id, events, current_status=case.status)
        self.timeline.bind(vm)

    def _open_detail(self) -> None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self._records):
            return
        self._selected_row = row
        rec = self._records[row]
        self.detail_title.setText(rec.position or "—")
        self.detail_company.setText(rec.company or "—")
        self.detail_status.set_status(status_label(rec.status), kind="info")
        cfg = self.config_service.load()
        db = Database(cfg.db_path)
        case = None
        if rec.job_id:
            cases = db.list_cases(limit=500)
            case = next((c for c in cases if c.job_id == rec.job_id), None)
        if case is None:
            self.timeline.clear()
        else:
            events = db.list_lifecycle_events(case.id)
            vm = build_case_timeline_viewmodel(case.id, events, current_status=case.status)
            self.timeline.bind(vm)
        self.stack.setCurrentIndex(1)

    def _back_to_list(self) -> None:
        self.stack.setCurrentIndex(0)

    def refresh(self) -> None:
        cfg = self.config_service.load()
        db = Database(cfg.db_path)
        status_val = self.status.currentData()
        records = db.list_applications(
            statuses=[status_val] if status_val else None,
            limit=500,
        )
        q = self.search.text().strip().lower()
        if q:
            records = [
                r
                for r in records
                if q in (r.company or "").lower() or q in (r.position or "").lower()
            ]
        key = str(self.sort.currentData() or "updated")
        if key == "company":
            records = sorted(records, key=lambda r: (r.company or "").lower())
        elif key == "status":
            records = sorted(records, key=lambda r: (r.status or "").lower())
        else:
            records = sorted(records, key=lambda r: r.application_date or "", reverse=True)
        self._records = records

        needs = sum(1 for r in db.list_applications(limit=500) if r.status == JobStatus.NEEDS_REVIEW.value)
        if needs:
            self.alert_text.setText(tr("apps.alert_needs_help", n=needs))
            self.alert.show()
        else:
            self.alert.hide()

        self.table.setRowCount(0)
        from desktop.viewmodels.job_fit import build_job_fit_viewmodel

        _fit_i18n = {
            "sehr_passend": tr("fit.sehr_passend"),
            "passend": tr("fit.passend"),
            "teilweise_passend": tr("fit.teilweise_passend"),
            "nicht_passend": tr("fit.nicht_passend"),
            "unbekannt": tr("fit.unbekannt"),
        }
        for rec in records:
            job = db.get_job(rec.job_id) if rec.job_id else None
            fit_label = ""
            if job is not None:
                fit = build_job_fit_viewmodel(job, cfg)
                fit_label = _fit_i18n.get(fit.headline_key, tr("fit.unbekannt"))
            row = self.table.rowCount()
            self.table.insertRow(row)
            company_role = f"{rec.company}\n{rec.position}"
            next_step = rec.error_message or rec.result or "—"
            values = [
                company_role,
                status_label(rec.status),
                (rec.application_date or "")[:19],
                next_step[:80],
                fit_label,
            ]
            for col, value in enumerate(values):
                self.table.setItem(row, col, QTableWidgetItem(value))
        empty = len(records) == 0
        self.table.setVisible(not empty)
        self.empty.setVisible(empty)
        if empty:
            self.timeline.clear()

    def open_selected(self) -> None:
        row = self._selected_row if self._selected_row >= 0 else self.table.currentRow()
        if row < 0 or row >= len(self._records):
            return
        rec = self._records[row]
        cfg = self.config_service.load()
        db = Database(cfg.db_path)
        job = db.get_job(rec.job_id) if rec.job_id else None
        url = ""
        if job:
            url = job.application_url or job.url
        if url:
            webbrowser.open(url)
        else:
            QMessageBox.information(self, tr("nav.applications"), tr("jobs.no_url"))

    def preview_selected(self) -> None:
        row = self._selected_row if self._selected_row >= 0 else self.table.currentRow()
        if row < 0 or row >= len(self._records):
            return
        rec = self._records[row]
        cfg = self.config_service.load()
        db = Database(cfg.db_path)
        job = db.get_job(rec.job_id) if rec.job_id else None
        if job is None:
            from apply.preview import ApplicationPreview
            from desktop.widgets.apply_preview_dialog import ApplyPreviewDialog

            preview = ApplicationPreview(
                job_id=rec.job_id,
                company=rec.company,
                title=rec.position,
                application_url="",
                ats=rec.platform or "unknown",
                ats_support="unknown",
                ats_note=rec.error_message or "",
                dry_run=bool(cfg.settings.dry_run),
                mode=cfg.settings.mode,
                will_submit=False,
                form_values={},
                documents={"CV": rec.cv_used, "Anschreiben": rec.cover_letter_used},
                cover_letter_preview=rec.error_message or "",
                warnings=["Job-Datensatz nicht gefunden — gespeicherte Notiz wird angezeigt."],
            )
            ApplyPreviewDialog(preview, self).exec()
            return
        from apply.preview import build_application_preview
        from desktop.widgets.apply_preview_dialog import ApplyPreviewDialog

        preview = build_application_preview(job, cfg)
        ApplyPreviewDialog(preview, self).exec()
