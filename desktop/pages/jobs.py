"""Jobs listing page — focused columns + match explanation; never shows nan."""

from __future__ import annotations

import webbrowser

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.database import Database
from core.models import JobStatus
from core.text_normalize import clean_text, display_or_dash
from desktop.i18n import tr
from desktop.services import ConfigService
from desktop.status_labels import status_label
from desktop.viewmodels.job_fit import build_job_fit_viewmodel
from desktop.widgets.product_panels import JobFitPanel
from desktop.widgets.wheel_guard import IntentionalWheelSpinBox


class JobsPage(QWidget):
    COLS = (
        "title",
        "company",
        "location",
        "distance",
        "remote",
        "score",
        "explanation",
        "source",
        "status",
    )

    def __init__(self, config_service: ConfigService, parent=None) -> None:
        super().__init__(parent)
        self.config_service = config_service
        self._jobs = []
        self._selected = None

        self.page_title = QLabel()
        self.page_title.setObjectName("PageTitle")
        self.page_subtitle = QLabel()
        self.page_subtitle.setObjectName("PageSubtitle")
        self.page_subtitle.setWordWrap(True)
        self.count_label = QLabel()
        self.count_label.setObjectName("PageSubtitle")

        self.min_match = IntentionalWheelSpinBox()
        self.min_match.setRange(0, 100)
        self.max_dist = IntentionalWheelSpinBox()
        self.max_dist.setRange(1, 500)
        self.city = QLineEdit()
        self.title = QLineEdit()
        self.company = QLineEdit()
        self.source = QLineEdit()
        self.status = QComboBox()
        self.status.addItem("", "")
        for s in JobStatus:
            self.status.addItem(s.value, s.value)
        self.chk_remote = QCheckBox()
        self.chk_hybrid = QCheckBox()
        self.chk_onsite = QCheckBox()
        self.age_days = IntentionalWheelSpinBox()
        self.age_days.setRange(0, 90)

        self.lbl_min_match = QLabel()
        self.lbl_max_dist = QLabel()
        self.lbl_city = QLabel()
        self.lbl_title = QLabel()
        self.lbl_company = QLabel()
        self.lbl_source = QLabel()
        self.lbl_status = QLabel()

        filter_form = QFormLayout()
        filter_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        filter_form.addRow(self.lbl_min_match, self.min_match)
        filter_form.addRow(self.lbl_max_dist, self.max_dist)
        filter_form.addRow(self.lbl_city, self.city)
        filter_form.addRow(self.lbl_title, self.title)
        filter_form.addRow(self.lbl_company, self.company)
        filter_form.addRow(self.lbl_source, self.source)
        filter_form.addRow(self.lbl_status, self.status)

        model_row = QHBoxLayout()
        model_row.addWidget(self.chk_remote)
        model_row.addWidget(self.chk_hybrid)
        model_row.addWidget(self.chk_onsite)
        model_row.addStretch()
        filter_form.addRow(model_row)

        self.apply_btn = QPushButton()
        self.apply_btn.setObjectName("PrimaryButton")
        self.apply_btn.clicked.connect(self.refresh)
        self.open_btn = QPushButton()
        self.open_btn.setObjectName("SecondaryButton")
        self.open_btn.clicked.connect(self.open_selected)
        self.prepare_btn = QPushButton()
        self.prepare_btn.setObjectName("PrimaryButton")
        self.prepare_btn.clicked.connect(self.prepare_application)
        btn_row = QHBoxLayout()
        btn_row.addWidget(self.apply_btn)
        btn_row.addWidget(self.open_btn)
        btn_row.addWidget(self.prepare_btn)
        btn_row.addStretch()
        filter_form.addRow(btn_row)

        self.table = QTableWidget(0, len(self.COLS))
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        self.table.itemSelectionChanged.connect(self._on_selection)
        self.table.doubleClicked.connect(self.open_selected)
        header = self.table.horizontalHeader()
        header.setStretchLastSection(True)
        for col in (3, 4, 5, 7, 8):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)

        self.empty = QLabel()
        self.empty.setObjectName("EmptyState")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setVisible(False)

        list_wrap = QVBoxLayout()
        list_wrap.setContentsMargins(0, 0, 0, 0)
        list_host = QWidget()
        list_host.setLayout(list_wrap)
        list_wrap.addWidget(self.table)
        list_wrap.addWidget(self.empty)

        self.detail = QFrame()
        self.detail.setObjectName("DetailPanel")
        detail_layout = QVBoxLayout(self.detail)
        detail_layout.setContentsMargins(14, 12, 14, 12)
        self.detail_title = QLabel()
        self.detail_title.setObjectName("NextActionTitle")
        self.detail_title.setWordWrap(True)
        self.detail_meta = QLabel()
        self.detail_meta.setObjectName("PageSubtitle")
        self.detail_meta.setWordWrap(True)
        self.detail_status = QLabel()
        self.fit_panel = JobFitPanel()
        self.detail_body = QTextEdit()
        self.detail_body.setReadOnly(True)
        self.detail_body.setMinimumHeight(140)
        self.detail_prepare = QPushButton()
        self.detail_prepare.setObjectName("PrimaryButton")
        self.detail_prepare.clicked.connect(self.prepare_application)
        self.detail_open = QPushButton()
        self.detail_open.setObjectName("SecondaryButton")
        self.detail_open.clicked.connect(self.open_selected)
        dbtns = QHBoxLayout()
        dbtns.addWidget(self.detail_prepare)
        dbtns.addWidget(self.detail_open)
        dbtns.addStretch()
        detail_layout.addWidget(self.detail_title)
        detail_layout.addWidget(self.detail_meta)
        detail_layout.addWidget(self.detail_status)
        detail_layout.addWidget(self.fit_panel)
        detail_layout.addWidget(self.detail_body, 1)
        detail_layout.addLayout(dbtns)

        splitter = QSplitter()
        splitter.setOrientation(Qt.Orientation.Horizontal)
        splitter.addWidget(list_host)
        splitter.addWidget(self.detail)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        layout = QVBoxLayout(self)
        layout.addWidget(self.page_title)
        layout.addWidget(self.page_subtitle)
        layout.addWidget(self.count_label)
        layout.addLayout(filter_form)
        layout.addWidget(splitter, 1)

        self._clear_detail()
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        self.page_title.setText(tr("jobs.page_title"))
        self.page_subtitle.setText(tr("jobs.page_subtitle"))
        self.lbl_min_match.setText(tr("jobs.min_match"))
        self.lbl_max_dist.setText(tr("jobs.max_km"))
        self.lbl_city.setText(tr("jobs.city"))
        self.lbl_title.setText(tr("jobs.title"))
        self.lbl_company.setText(tr("jobs.company"))
        self.lbl_source.setText(tr("jobs.source"))
        self.lbl_status.setText(tr("jobs.status"))
        self.chk_remote.setText(tr("remote"))
        self.chk_hybrid.setText(tr("hybrid"))
        self.chk_onsite.setText(tr("onsite"))
        self.apply_btn.setText(tr("btn.filter"))
        self.open_btn.setText(tr("btn.open_job"))
        self.prepare_btn.setText(tr("btn.prepare_application"))
        self.detail_prepare.setText(tr("btn.prepare_application"))
        self.detail_open.setText(tr("btn.open_job"))
        self.empty.setText(tr("jobs.empty"))
        self.status.setItemText(0, tr("jobs.all"))
        for i in range(1, self.status.count()):
            raw = self.status.itemData(i)
            self.status.setItemText(i, status_label(str(raw)))
        self.table.setHorizontalHeaderLabels(
            [
                tr("col.title"),
                tr("col.company"),
                tr("col.city"),
                tr("col.distance"),
                tr("col.remote"),
                tr("col.fit"),
                tr("col.explanation"),
                tr("col.source"),
                tr("col.status"),
            ]
        )
        if self._selected is None:
            self._clear_detail()

    def _clear_detail(self) -> None:
        self.detail_title.setText(tr("jobs.detail_empty_title"))
        self.detail_meta.setText(tr("jobs.detail_empty_body"))
        self.detail_status.clear()
        self.fit_panel.clear()
        self.detail_body.setPlainText("")
        self.detail_prepare.setEnabled(False)
        self.detail_open.setEnabled(False)

    def _job_for_row(self, row: int):
        if row < 0:
            return None
        item = self.table.item(row, 0)
        if not item:
            return None
        job_id = item.data(Qt.ItemDataRole.UserRole)
        if job_id:
            return next((j for j in self._jobs if j.id == job_id), None)
        title = clean_text(item.text())
        company_item = self.table.item(row, 1)
        company = clean_text(company_item.text() if company_item else "")
        return next(
            (j for j in self._jobs if clean_text(j.title) == title and clean_text(j.company) == company),
            None,
        )

    def _on_selection(self) -> None:
        row = self.table.currentRow()
        job = self._job_for_row(row)
        self._selected = job
        if job is None:
            self._clear_detail()
            return
        self.detail_title.setText(display_or_dash(job.title))
        dist = "" if job.distance_km is None else f"{job.distance_km:.1f} km"
        self.detail_meta.setText(
            f"{display_or_dash(job.company)} · {display_or_dash(job.city)} · "
            f"{display_or_dash(job.remote_type)} · {dist or '—'} · "
            f"{display_or_dash(job.salary_text)} · {display_or_dash(job.source)}"
        )
        self.detail_status.setText(f"{tr('jobs.status')}: {status_label(job.status)}")
        cfg = self.config_service.load()
        fit = build_job_fit_viewmodel(job, cfg)
        self.fit_panel.bind(fit)
        body = clean_text(job.description)
        chunks: list[str] = []
        lines = fit.primary_lines(limit=12)
        if lines:
            chunks.append(f"{tr('jobs.fit_detail')}:\n" + "\n".join(lines))
        if body:
            chunks.append(body[:4000])
        self.detail_body.setPlainText("\n\n".join(chunks) if chunks else tr("jobs.no_description"))
        self.detail_prepare.setEnabled(True)
        self.detail_open.setEnabled(True)

    def refresh(self) -> None:
        cfg = self.config_service.load()
        self.min_match.setValue(self.min_match.value() or int(cfg.settings.minimum_match_for_dashboard))
        if self.max_dist.value() == 1 and not hasattr(self, "_dist_init"):
            self.max_dist.setValue(int(cfg.profile.location.max_distance_km))
            self._dist_init = True
        db = Database(cfg.db_path)
        remote_types = []
        if self.chk_remote.isChecked():
            remote_types.append("remote")
        if self.chk_hybrid.isChecked():
            remote_types.append("hybrid")
        if self.chk_onsite.isChecked():
            remote_types.append("onsite")
        status_val = self.status.currentData()
        jobs = db.list_jobs(
            min_match=self.min_match.value(),
            max_distance=float(self.max_dist.value()),
            statuses=[status_val] if status_val else None,
            hide_applied=cfg.settings.hide_already_applied,
            hide_duplicates=cfg.settings.hide_duplicates,
            remote_types=remote_types or None,
            company_query=self.company.text().strip() or None,
            title_query=self.title.text().strip() or None,
            city_query=self.city.text().strip() or None,
            source=self.source.text().strip() or None,
            limit=500,
        )
        self._jobs = jobs
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        cfg = self.config_service.load()
        _fit_i18n = {
            "sehr_passend": tr("fit.sehr_passend"),
            "passend": tr("fit.passend"),
            "teilweise_passend": tr("fit.teilweise_passend"),
            "nicht_passend": tr("fit.nicht_passend"),
            "unbekannt": tr("fit.unbekannt"),
        }
        for job in jobs:
            row = self.table.rowCount()
            self.table.insertRow(row)
            dist = "" if job.distance_km is None else f"{job.distance_km:.1f}"
            fit = build_job_fit_viewmodel(job, cfg)
            fit_label = _fit_i18n.get(fit.headline_key, tr("fit.unbekannt"))
            values = [
                display_or_dash(job.title),
                display_or_dash(job.company),
                display_or_dash(job.city),
                dist or "—",
                display_or_dash(job.remote_type),
                fit_label,
                " · ".join(fit.primary_lines(limit=2)) or display_or_dash(job.match_explanation()),
                display_or_dash(job.source),
                status_label(job.status),
            ]
            for col, value in enumerate(values):
                # Never paint raw nan into the table.
                if str(value).strip().lower() in {"nan", "none", "null"}:
                    value = "—"
                item = QTableWidgetItem(value)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, job.id)
                if col == 5:
                    # Keep numeric sort hint without displaying fake precision.
                    item.setData(Qt.ItemDataRole.UserRole + 1, int(job.match_score or 0))
                self.table.setItem(row, col, item)
        self.table.setSortingEnabled(True)
        empty = len(jobs) == 0
        self.table.setVisible(not empty)
        self.empty.setVisible(empty)
        self.count_label.setText(tr("jobs.count", n=len(jobs)))
        if empty:
            self._clear_detail()

    def open_selected(self) -> None:
        job = self._selected or self._job_for_row(self.table.currentRow())
        if not job:
            QMessageBox.information(self, tr("nav.jobs"), tr("jobs.select_first"))
            return
        url = job.application_url or job.url
        if url:
            webbrowser.open(url)
        else:
            QMessageBox.information(self, tr("nav.jobs"), tr("jobs.no_url"))

    def prepare_application(self) -> None:
        job = self._selected or self._job_for_row(self.table.currentRow())
        if not job:
            QMessageBox.information(self, tr("nav.jobs"), tr("jobs.select_first"))
            return
        cfg = self.config_service.load()
        from apply.preview import build_application_preview
        from desktop.widgets.apply_preview_dialog import ApplyPreviewDialog

        meta = self.config_service.load_meta()
        preview = build_application_preview(job, cfg, meta=meta)
        ApplyPreviewDialog(preview, self).exec()
