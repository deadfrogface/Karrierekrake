"""Jobs — V2: compact result filters, explicit sort, ~60/40 list+detail."""

from __future__ import annotations

import webbrowser
from datetime import datetime

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
    QListWidget,
    QListWidgetItem,
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
from desktop.design_system.a11y import set_accessible_name
from desktop.design_system.v2_chrome import ContentCard, PageHeader, SectionEditDrawer
from desktop.i18n import tr
from desktop.services import ConfigService
from desktop.status_labels import status_label
from desktop.viewmodels.job_fit import build_job_fit_viewmodel
from desktop.widgets.product_panels import JobFitPanel
from desktop.widgets.wheel_guard import IntentionalWheelSpinBox


def _parse_discovered(value: str | None) -> datetime:
    raw = (value or "").strip()
    if not raw:
        return datetime.min
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw.replace("Z", "+0000")[:26], fmt)
        except ValueError:
            continue
    return datetime.min


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

        self.header = PageHeader()
        self.page_title = self.header.title
        self.page_subtitle = self.header.subtitle
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
        # Dead control kept for compatibility — never surface in V2 (matrix HIDE).
        self.age_days = IntentionalWheelSpinBox()
        self.age_days.setRange(0, 90)
        self.age_days.hide()

        self.lbl_min_match = QLabel()
        self.lbl_max_dist = QLabel()
        self.lbl_city = QLabel()
        self.lbl_title = QLabel()
        self.lbl_company = QLabel()
        self.lbl_source = QLabel()
        self.lbl_status = QLabel()
        self.lbl_sort = QLabel()
        self.lbl_filters = QLabel()
        self.lbl_filters.setObjectName("KkHint")

        self.sort = QComboBox()
        self.sort.addItem("", "match_desc")
        self.sort.addItem("", "match_asc")
        self.sort.addItem("", "distance_near")
        self.sort.addItem("", "distance_far")
        self.sort.addItem("", "newest")
        self.sort.currentIndexChanged.connect(self._on_sort_changed)

        # Compact primary filter row (result filters — not search parameters)
        primary = QHBoxLayout()
        primary.setSpacing(8)
        for w in (
            self.lbl_min_match,
            self.min_match,
            self.lbl_max_dist,
            self.max_dist,
            self.lbl_city,
            self.city,
            self.chk_remote,
            self.chk_hybrid,
            self.chk_onsite,
        ):
            primary.addWidget(w)
        self.apply_btn = QPushButton()
        self.apply_btn.setObjectName("PrimaryButton")
        self.apply_btn.clicked.connect(self.refresh)
        self.more_filters_btn = QPushButton()
        self.more_filters_btn.setObjectName("SecondaryButton")
        self.more_filters_btn.clicked.connect(self._open_more_filters)
        self.search_intent_btn = QPushButton()
        self.search_intent_btn.setObjectName("SecondaryButton")
        self.search_intent_btn.clicked.connect(self.open_search_intent)
        primary.addWidget(self.apply_btn)
        primary.addWidget(self.more_filters_btn)
        primary.addWidget(self.search_intent_btn)
        primary.addStretch()

        self.more_filters = QWidget()
        more_form = QFormLayout(self.more_filters)
        more_form.setContentsMargins(0, 4, 0, 0)
        more_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        more_form.addRow(self.lbl_title, self.title)
        more_form.addRow(self.lbl_company, self.company)
        more_form.addRow(self.lbl_source, self.source)
        more_form.addRow(self.lbl_status, self.status)
        self._filter_drawer = SectionEditDrawer(parent=self)
        # Host for drawer content when closed
        self._filter_host = QWidget(self)
        self._filter_host.hide()
        QVBoxLayout(self._filter_host).addWidget(self.more_filters)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(12)
        toolbar.addWidget(self.count_label)
        toolbar.addStretch()
        toolbar.addWidget(self.lbl_sort)
        toolbar.addWidget(self.sort)

        self.open_btn = QPushButton()
        self.open_btn.setObjectName("SecondaryButton")
        self.open_btn.clicked.connect(self.open_selected)
        self.prepare_btn = QPushButton()
        self.prepare_btn.setObjectName("PrimaryButton")
        self.prepare_btn.clicked.connect(self.prepare_application)
        action_row = QHBoxLayout()
        action_row.addWidget(self.prepare_btn)
        action_row.addWidget(self.open_btn)
        action_row.addStretch()

        self.table = QTableWidget(0, len(self.COLS))
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setSortingEnabled(False)
        self.table.setAlternatingRowColors(True)
        self.table.itemSelectionChanged.connect(self._on_selection)
        self.table.doubleClicked.connect(self.open_selected)
        self.table.hide()  # Demo uses cards; table kept for tests/compat
        header = self.table.horizontalHeader()
        header.setStretchLastSection(True)
        for col in (3, 4, 5, 7, 8):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)

        self.job_list = QListWidget()
        self.job_list.setSpacing(6)
        self.job_list.currentRowChanged.connect(self._on_card_row)

        self.empty = QLabel()
        self.empty.setObjectName("EmptyState")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setVisible(False)

        list_wrap = QVBoxLayout()
        list_wrap.setContentsMargins(0, 0, 0, 0)
        list_host = QWidget()
        list_host.setLayout(list_wrap)
        list_wrap.addWidget(self.job_list)
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
        # ~60/40
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([600, 400])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)
        layout.addWidget(self.header)
        layout.addWidget(self.lbl_filters)
        layout.addLayout(primary)
        layout.addLayout(toolbar)
        layout.addLayout(action_row)
        layout.addWidget(splitter, 1)

        self._clear_detail()
        self.retranslate_ui()

    def _open_more_filters(self) -> None:
        self.more_filters.setParent(None)
        self._filter_drawer.set_texts(
            title=tr("jobs.more_filters"),
            save=tr("btn.filter"),
            cancel=tr("btn.cancel"),
        )
        result = self._filter_drawer.present(self.more_filters)
        self._filter_drawer.take_content()
        self._filter_host.layout().addWidget(self.more_filters)
        if result == SectionEditDrawer.DialogCode.Accepted:
            self.refresh()

    def _toggle_more_filters(self, checked: bool) -> None:
        # Compat for older callers — open drawer instead of inline expand.
        if checked:
            self._open_more_filters()
        self.more_filters_btn.setChecked(False)

    def _on_card_row(self, row: int) -> None:
        if row < 0:
            return
        self.table.blockSignals(True)
        self.table.selectRow(row)
        self.table.blockSignals(False)
        self._on_selection()

    def _on_sort_changed(self, _index: int = 0) -> None:
        if not self._jobs:
            return
        self._jobs = self._sorted_jobs(self._jobs)
        self._populate_table(self._jobs)

    def _sort_key(self) -> str:
        return str(self.sort.currentData() or "match_desc")

    def _sorted_jobs(self, jobs: list) -> list:
        key = self._sort_key()
        if key == "match_asc":
            return sorted(jobs, key=lambda j: int(j.match_score or 0))
        if key == "distance_near":
            return sorted(
                jobs,
                key=lambda j: (
                    j.distance_km is None,
                    float(j.distance_km) if j.distance_km is not None else 0.0,
                ),
            )
        if key == "distance_far":
            return sorted(
                jobs,
                key=lambda j: (
                    j.distance_km is None,
                    -(float(j.distance_km) if j.distance_km is not None else 0.0),
                ),
            )
        if key == "newest":
            return sorted(
                jobs,
                key=lambda j: _parse_discovered(getattr(j, "discovered_at", None)),
                reverse=True,
            )
        # match_desc (default)
        return sorted(jobs, key=lambda j: int(j.match_score or 0), reverse=True)

    def retranslate_ui(self) -> None:
        self.header.set_texts(tr("jobs.page_title"), tr("jobs.page_subtitle"))
        self.lbl_filters.setText(tr("jobs.section_result_filters"))
        self.lbl_min_match.setText(tr("jobs.min_match"))
        self.lbl_max_dist.setText(tr("jobs.max_km"))
        self.lbl_city.setText(tr("jobs.city"))
        self.lbl_title.setText(tr("jobs.title"))
        self.lbl_company.setText(tr("jobs.company"))
        self.lbl_source.setText(tr("jobs.source"))
        self.lbl_status.setText(tr("jobs.status"))
        self.lbl_sort.setText(tr("jobs.sort_label"))
        self.chk_remote.setText(tr("remote"))
        self.chk_hybrid.setText(tr("hybrid"))
        self.chk_onsite.setText(tr("onsite"))
        self.apply_btn.setText(tr("btn.filter"))
        self.more_filters_btn.setText(tr("jobs.more_filters"))
        self.open_btn.setText(tr("btn.open_job"))
        self.prepare_btn.setText(tr("btn.prepare_application"))
        self.search_intent_btn.setText(tr("jobs.open_search_intent"))
        set_accessible_name(self.search_intent_btn, tr("jobs.open_search_intent"))
        self.detail_prepare.setText(tr("btn.prepare_application"))
        self.detail_open.setText(tr("btn.open_job"))
        self.empty.setText(tr("jobs.empty"))
        self.status.setItemText(0, tr("jobs.all"))
        for i in range(1, self.status.count()):
            raw = self.status.itemData(i)
            self.status.setItemText(i, status_label(str(raw)))
        sort_labels = {
            "match_desc": tr("jobs.sort_match_desc"),
            "match_asc": tr("jobs.sort_match_asc"),
            "distance_near": tr("jobs.sort_distance_near"),
            "distance_far": tr("jobs.sort_distance_far"),
            "newest": tr("jobs.sort_newest"),
        }
        for i in range(self.sort.count()):
            key = str(self.sort.itemData(i))
            self.sort.setItemText(i, sort_labels.get(key, key))
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

    def _populate_table(self, jobs: list) -> None:
        self.table.setRowCount(0)
        self.job_list.clear()
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
            reason = " · ".join(fit.primary_lines(limit=2)) or display_or_dash(job.match_explanation())
            values = [
                display_or_dash(job.title),
                display_or_dash(job.company),
                display_or_dash(job.city),
                dist or "—",
                display_or_dash(job.remote_type),
                fit_label,
                reason,
                display_or_dash(job.source),
                status_label(job.status),
            ]
            for col, value in enumerate(values):
                if str(value).strip().lower() in {"nan", "none", "null"}:
                    value = "—"
                item = QTableWidgetItem(value)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, job.id)
                if col == 5:
                    item.setData(Qt.ItemDataRole.UserRole + 1, int(job.match_score or 0))
                self.table.setItem(row, col, item)
            # Demo card row (compact)
            dist_txt = f"{dist} km" if dist else "—"
            card = (
                f"{display_or_dash(job.title)}\n"
                f"{display_or_dash(job.company)} · {display_or_dash(job.city)} ({dist_txt}) · "
                f"{display_or_dash(job.remote_type)}\n"
                f"{fit_label} — {reason}"
            )
            list_item = QListWidgetItem(card)
            list_item.setData(Qt.ItemDataRole.UserRole, job.id)
            self.job_list.addItem(list_item)
        empty = len(jobs) == 0
        self.table.hide()
        self.job_list.setVisible(not empty)
        self.empty.setVisible(empty)
        self.count_label.setText(tr("jobs.count", n=len(jobs)))
        if empty:
            self._clear_detail()
        elif self.job_list.count():
            self.job_list.setCurrentRow(0)

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
        self._jobs = self._sorted_jobs(jobs)
        self._populate_table(self._jobs)

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

    def open_search_intent(self) -> None:
        parent = self.window()
        if parent is not None and hasattr(parent, "open_search_intent"):
            parent.open_search_intent()  # type: ignore[attr-defined]
