"""Dashboard page — next action first, then clear CTAs and key stats."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.database import Database
from desktop.i18n import tr
from desktop.services import ConfigService


class StatCard(QFrame):
    def __init__(self, title_key: str, parent=None) -> None:
        super().__init__(parent)
        self._title_key = title_key
        self.setObjectName("Card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        self.value = QLabel("0")
        self.value.setObjectName("CardValue")
        self.caption = QLabel()
        self.caption.setObjectName("CardTitle")
        layout.addWidget(self.value)
        layout.addWidget(self.caption)
        self.retranslate()

    def retranslate(self) -> None:
        self.caption.setText(tr(self._title_key))

    def set_value(self, text: str | int) -> None:
        self.value.setText(str(text))


class DashboardPage(QWidget):
    search_requested = Signal()
    apply_requested = Signal()
    test_requested = Signal()
    pause_requested = Signal()
    review_requested = Signal()
    cancel_requested = Signal()
    clear_jobs_requested = Signal()

    def __init__(self, config_service: ConfigService, parent=None) -> None:
        super().__init__(parent)
        self.config_service = config_service
        self._next_action = "search"

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(14)

        self.page_title = QLabel()
        self.page_title.setObjectName("PageTitle")
        self.page_subtitle = QLabel()
        self.page_subtitle.setObjectName("PageSubtitle")
        self.page_subtitle.setWordWrap(True)
        root.addWidget(self.page_title)
        root.addWidget(self.page_subtitle)

        self.hero = QFrame()
        self.hero.setObjectName("HeroCard")
        hero_layout = QVBoxLayout(self.hero)
        hero_layout.setContentsMargins(18, 16, 18, 16)
        hero_layout.setSpacing(10)
        self.next_title = QLabel()
        self.next_title.setObjectName("NextActionTitle")
        self.next_body = QLabel()
        self.next_body.setWordWrap(True)
        self.next_body.setObjectName("PageSubtitle")
        self.btn_primary = QPushButton()
        self.btn_primary.setObjectName("PrimaryButton")
        self.btn_primary.clicked.connect(self._on_primary)
        hero_btns = QHBoxLayout()
        hero_btns.addWidget(self.btn_primary)
        hero_btns.addStretch()
        hero_layout.addWidget(self.next_title)
        hero_layout.addWidget(self.next_body)
        hero_layout.addLayout(hero_btns)
        root.addWidget(self.hero)

        self.cards = {
            "matches_ge_75": StatCard("dash.matches"),
            "needs_review": StatCard("dash.needs_review"),
            "jobs_found_today": StatCard("dash.found_today"),
            "applications_today": StatCard("dash.applied"),
            "new_today": StatCard("dash.new"),
            "this_run": StatCard("dash.this_run"),
            "captcha": StatCard("dash.captcha"),
            "errors": StatCard("dash.errors"),
        }
        grid = QGridLayout()
        grid.setSpacing(10)
        for i, card in enumerate(self.cards.values()):
            grid.addWidget(card, i // 4, i % 4)
        root.addLayout(grid)

        self.mode_label = QLabel()
        self.last_run_label = QLabel()
        self.next_run_label = QLabel()
        self.status_label = QLabel()
        self.home_warning_label = QLabel()
        self.home_warning_label.setWordWrap(True)
        self.home_warning_label.setObjectName("WarningLabel")
        self.run_detail_label = QLabel()
        self.run_detail_label.setWordWrap(True)
        self.run_detail_label.setObjectName("PageSubtitle")

        info = QVBoxLayout()
        info.setSpacing(4)
        info.addWidget(self.mode_label)
        info.addWidget(self.last_run_label)
        info.addWidget(self.next_run_label)
        info.addWidget(self.status_label)
        info.addWidget(self.home_warning_label)
        info.addWidget(self.run_detail_label)
        root.addLayout(info)

        self.btn_search = QPushButton()
        self.btn_search.setObjectName("PrimaryButton")
        self.btn_cancel = QPushButton()
        self.btn_cancel.setObjectName("SecondaryButton")
        self.btn_cancel.setEnabled(False)
        self.btn_apply = QPushButton()
        self.btn_apply.setObjectName("SecondaryButton")
        self.btn_test = QPushButton()
        self.btn_test.setObjectName("SecondaryButton")
        self.btn_pause = QPushButton()
        self.btn_pause.setObjectName("SecondaryButton")
        self.btn_review = QPushButton()
        self.btn_review.setObjectName("SecondaryButton")
        self.btn_clear_jobs = QPushButton()
        self.btn_clear_jobs.setObjectName("SecondaryButton")
        self.btn_search.clicked.connect(self.search_requested.emit)
        self.btn_cancel.clicked.connect(self.cancel_requested.emit)
        self.btn_apply.clicked.connect(self.apply_requested.emit)
        self.btn_test.clicked.connect(self.test_requested.emit)
        self.btn_pause.clicked.connect(self.pause_requested.emit)
        self.btn_review.clicked.connect(self.review_requested.emit)
        self.btn_clear_jobs.clicked.connect(self.clear_jobs_requested.emit)

        row1 = QHBoxLayout()
        row1.setSpacing(8)
        for btn in (self.btn_search, self.btn_cancel, self.btn_apply, self.btn_test):
            row1.addWidget(btn)
        row1.addStretch()
        row2 = QHBoxLayout()
        row2.setSpacing(8)
        for btn in (self.btn_pause, self.btn_review, self.btn_clear_jobs):
            row2.addWidget(btn)
        row2.addStretch()
        root.addLayout(row1)
        root.addLayout(row2)
        root.addStretch()

        self.retranslate_ui()

    def _on_primary(self) -> None:
        if self._next_action == "review":
            self.review_requested.emit()
        elif self._next_action == "profile":
            parent = self.window()
            if parent is not None and hasattr(parent, "navigate_to"):
                parent.navigate_to("nav.profile")  # type: ignore[attr-defined]
                return
            self.search_requested.emit()
        else:
            self.search_requested.emit()

    def retranslate_ui(self) -> None:
        self.page_title.setText(tr("dash.page_title"))
        self.page_subtitle.setText(tr("dash.page_subtitle"))
        for card in self.cards.values():
            card.retranslate()
        self.btn_search.setText(tr("btn.search_now"))
        self.btn_cancel.setText(tr("btn.cancel_search"))
        self.btn_apply.setText(tr("btn.start_apply"))
        self.btn_test.setText(tr("btn.apply_test"))
        self.btn_review.setText(tr("btn.review_queue"))
        self.btn_clear_jobs.setText(tr("btn.clear_jobs"))
        self.status_label.setText(tr("status.ready"))
        self.refresh()

    def set_pipeline_running(self, running: bool) -> None:
        self.btn_search.setEnabled(not running)
        self.btn_cancel.setEnabled(running)
        self.btn_apply.setEnabled(not running)
        self.btn_test.setEnabled(not running)
        self.btn_clear_jobs.setEnabled(not running)
        self.btn_primary.setEnabled(not running or self._next_action == "review")

    def _compute_next_action(self, cfg, stats: dict) -> None:
        titles = [t for t in (cfg.profile.jobs.desired_titles or []) if str(t).strip()]
        if not titles:
            self._next_action = "profile"
            self.next_title.setText(tr("dash.next_profile_title"))
            self.next_body.setText(tr("dash.next_profile_body"))
            self.btn_primary.setText(tr("dash.next_profile_cta"))
            return
        if int(stats.get("needs_review") or 0) > 0:
            self._next_action = "review"
            self.next_title.setText(tr("dash.next_review_title"))
            self.next_body.setText(tr("dash.next_review_body"))
            self.btn_primary.setText(tr("btn.review_queue"))
            return
        self._next_action = "search"
        self.next_title.setText(tr("dash.next_search_title"))
        self.next_body.setText(tr("dash.next_search_body"))
        self.btn_primary.setText(tr("btn.find_jobs"))

    def refresh(self) -> None:
        cfg = self.config_service.load()
        db = Database(cfg.db_path)
        stats = db.dashboard_stats()
        for key, card in self.cards.items():
            card.set_value(stats.get(key, 0))
        self._compute_next_action(cfg, stats)
        mode = cfg.settings.mode
        dry = tr("dash.on") if cfg.settings.dry_run else tr("dash.off")
        paused = bool(cfg.settings.automation_paused)
        paused_label = tr("dash.paused") if paused else tr("dash.active")
        auto = tr("dash.on") if cfg.settings.run_automatically else tr("dash.off")
        self.mode_label.setText(
            f"{tr('dash.mode')}: {mode}  |  {tr('dash.dry_run')}: {dry}  |  "
            f"{tr('dash.automation')}: {auto} ({paused_label})"
        )
        self.btn_pause.setText(
            tr("btn.resume_automation") if paused else tr("btn.pause_automation")
        )
        meta = self.config_service.load_meta()
        self.last_run_label.setText(
            f"{tr('dash.last_search')}: {meta.get('last_search_run') or '—'}"
        )
        self.next_run_label.setText(
            f"{tr('dash.next_run')}: {meta.get('next_scheduled_run') or '—'}"
        )

        loc = cfg.profile.location
        if not (loc.home_address or "").strip() and loc.home_latitude is None:
            self.home_warning_label.setText(tr("dash.home_missing"))
            self.home_warning_label.setVisible(True)
        else:
            self.home_warning_label.clear()
            self.home_warning_label.setVisible(False)

        run_id = db.latest_run_id()
        detail = ""
        if run_id:
            with db.connection() as conn:
                row = conn.execute(
                    "SELECT status, stats_json, started_at, finished_at FROM search_runs WHERE id = ?",
                    (run_id,),
                ).fetchone()
            if row:
                import json

                try:
                    st = json.loads(row["stats_json"] or "{}")
                except Exception:
                    st = {}
                if st.get("home_warning"):
                    self.home_warning_label.setText(str(st["home_warning"]))
                    self.home_warning_label.setVisible(True)
                detail = (
                    f"{tr('dash.run_stats')}: raw={st.get('raw_results', st.get('total', '—'))} | "
                    f"dup={st.get('duplicates', '—')} | dist={st.get('distance_removed', st.get('outside', '—'))} | "
                    f"neu={st.get('new_jobs', st.get('new', '—'))} | match={st.get('matches', '—')} | "
                    f"ATS unknown={st.get('ats_unknown', '—')} / supported={st.get('ats_supported', '—')}"
                )
        self.run_detail_label.setText(detail)

    def set_status(self, text: str) -> None:
        self.status_label.setText(text)
