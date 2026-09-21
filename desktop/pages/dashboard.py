"""Übersicht — ruhiges Bewerbungs-Cockpit (V2): Action Queue, 4 KPIs, leise Tech-Stats."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.database import Database
from desktop.design_system.a11y import set_accessible_name
from desktop.design_system.v2_chrome import ContentCard, KpiCard, PageHeader
from desktop.i18n import tr
from desktop.services import ConfigService


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
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(16)

        header_row = QHBoxLayout()
        header_row.setSpacing(12)
        self.header = PageHeader()
        header_row.addWidget(self.header, stretch=1)
        self.btn_search = QPushButton()
        self.btn_search.setObjectName("PrimaryButton")
        self.btn_search.clicked.connect(self.search_requested.emit)
        header_row.addWidget(self.btn_search, stretch=0)
        root.addLayout(header_row)

        self.queue_section = QLabel()
        self.queue_section.setObjectName("KkHint")
        root.addWidget(self.queue_section)

        self.hero = ContentCard()
        self.hero.setObjectName("HeroCard")
        hero_body = self.hero.body()
        self.next_title = QLabel()
        self.next_title.setObjectName("NextActionTitle")
        self.next_body = QLabel()
        self.next_body.setWordWrap(True)
        self.next_body.setObjectName("PageSubtitle")
        self.btn_primary = QPushButton()
        self.btn_primary.setObjectName("SecondaryButton")
        self.btn_primary.clicked.connect(self._on_primary)
        hero_btns = QHBoxLayout()
        hero_btns.addWidget(self.btn_primary)
        hero_btns.addStretch()
        hero_body.addWidget(self.next_title)
        hero_body.addWidget(self.next_body)
        hero_body.addLayout(hero_btns)
        root.addWidget(self.hero)

        self.kpi_section = QLabel()
        self.kpi_section.setObjectName("KkHint")
        root.addWidget(self.kpi_section)

        self.kpi_cards = {
            "matches": KpiCard(),
            "needs_review": KpiCard(),
            "applications": KpiCard(),
            "replies": KpiCard(),
        }
        kpi_grid = QGridLayout()
        kpi_grid.setSpacing(12)
        for i, card in enumerate(self.kpi_cards.values()):
            kpi_grid.addWidget(card, 0, i)
        root.addLayout(kpi_grid)

        meta_row = QHBoxLayout()
        meta_row.setSpacing(12)
        self.last_run_card = ContentCard()
        last_body = self.last_run_card.body()
        self.last_run_caption = QLabel()
        self.last_run_caption.setObjectName("KkHint")
        self.last_run_label = QLabel("—")
        self.last_run_label.setObjectName("PageSubtitle")
        last_body.addWidget(self.last_run_caption)
        last_body.addWidget(self.last_run_label)
        self.next_run_card = ContentCard()
        next_body = self.next_run_card.body()
        self.next_run_caption = QLabel()
        self.next_run_caption.setObjectName("KkHint")
        self.next_run_label = QLabel("—")
        self.next_run_label.setObjectName("PageSubtitle")
        self.mode_chip = QLabel()
        self.mode_chip.setObjectName("BadgeMuted")
        next_body.addWidget(self.next_run_caption)
        next_body.addWidget(self.next_run_label)
        next_body.addWidget(self.mode_chip)
        meta_row.addWidget(self.last_run_card)
        meta_row.addWidget(self.next_run_card)
        root.addLayout(meta_row)

        self.mode_label = QLabel()
        self.mode_label.setObjectName("KkHint")
        self.status_label = QLabel()
        self.home_warning_label = QLabel()
        self.home_warning_label.setWordWrap(True)
        self.home_warning_label.setObjectName("WarningLabel")
        root.addWidget(self.mode_label)
        root.addWidget(self.status_label)
        root.addWidget(self.home_warning_label)

        self.advanced_section = QLabel()
        self.advanced_section.setObjectName("KkHint")
        root.addWidget(self.advanced_section)

        self.advanced_stats = QLabel()
        self.advanced_stats.setObjectName("KkHint")
        self.advanced_stats.setWordWrap(True)
        self.run_detail_label = QLabel()
        self.run_detail_label.setWordWrap(True)
        self.run_detail_label.setObjectName("KkHint")
        root.addWidget(self.advanced_stats)
        root.addWidget(self.run_detail_label)

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
        self.btn_cancel.clicked.connect(self.cancel_requested.emit)
        self.btn_apply.clicked.connect(self.apply_requested.emit)
        self.btn_test.clicked.connect(self.test_requested.emit)
        self.btn_pause.clicked.connect(self.pause_requested.emit)
        self.btn_review.clicked.connect(self.review_requested.emit)
        self.btn_clear_jobs.clicked.connect(self.clear_jobs_requested.emit)
        # Capability preserved; permanent button wall removed (overflow).
        for btn in (
            self.btn_cancel,
            self.btn_apply,
            self.btn_test,
            self.btn_pause,
            self.btn_review,
            self.btn_clear_jobs,
        ):
            btn.hide()

        overflow_row = QHBoxLayout()
        self.more_actions = QToolButton()
        self.more_actions.setObjectName("SecondaryButton")
        self.more_actions.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._actions_menu = QMenu(self)
        self.more_actions.setMenu(self._actions_menu)
        overflow_row.addWidget(self.more_actions)
        overflow_row.addStretch()
        root.addLayout(overflow_row)
        root.addStretch()

        # Compatibility aliases used by older tests / callers
        self.page_title = self.header.title
        self.page_subtitle = self.header.subtitle
        self.cards = self.kpi_cards

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
        elif self._next_action == "inbox":
            parent = self.window()
            if parent is not None and hasattr(parent, "navigate_to"):
                parent.navigate_to("nav.inbox")  # type: ignore[attr-defined]
                return
            self.review_requested.emit()
        else:
            self.search_requested.emit()

    def retranslate_ui(self) -> None:
        self.header.set_texts(tr("dash.page_title"), tr("dash.page_subtitle"))
        self.queue_section.setText(tr("dash.section_queue"))
        self.kpi_section.setText(tr("dash.section_kpis"))
        self.advanced_section.setText(tr("dash.section_advanced"))
        self.last_run_caption.setText(tr("dash.last_search"))
        self.next_run_caption.setText(tr("dash.next_run"))
        self.btn_search.setText(tr("btn.find_jobs"))
        set_accessible_name(self.btn_search, tr("btn.find_jobs"))
        self.btn_cancel.setText(tr("btn.cancel_search"))
        self.btn_apply.setText(tr("btn.start_apply"))
        self.btn_test.setText(tr("btn.apply_test"))
        self.btn_review.setText(tr("btn.review_queue"))
        self.btn_clear_jobs.setText(tr("btn.clear_jobs"))
        self.more_actions.setText(tr("dash.more_actions"))
        set_accessible_name(self.more_actions, tr("dash.more_actions"))
        self._rebuild_actions_menu()
        self.status_label.setText(tr("status.ready"))
        self.refresh()

    def _rebuild_actions_menu(self) -> None:
        self._actions_menu.clear()
        for btn in (
            self.btn_cancel,
            self.btn_apply,
            self.btn_test,
            self.btn_pause,
            self.btn_review,
            self.btn_clear_jobs,
        ):
            act = self._actions_menu.addAction(btn.text())
            act.setEnabled(btn.isEnabled())
            act.triggered.connect(btn.click)

    def set_pipeline_running(self, running: bool) -> None:
        self.btn_search.setEnabled(not running)
        self.btn_cancel.setEnabled(running)
        self.btn_apply.setEnabled(not running)
        self.btn_test.setEnabled(not running)
        self.btn_clear_jobs.setEnabled(not running)
        self.btn_primary.setEnabled(not running or self._next_action in {"review", "inbox"})
        self._rebuild_actions_menu()

    def _compute_next_action(self, cfg, stats: dict) -> None:
        titles = [t for t in (cfg.profile.jobs.desired_titles or []) if str(t).strip()]
        if not titles:
            self._next_action = "profile"
            self.next_title.setText(tr("dash.next_profile_title"))
            self.next_body.setText(tr("dash.next_profile_body"))
            self.btn_primary.setText(tr("dash.next_profile_cta"))
            return
        replies = int(stats.get("replies_attention") or 0)
        if replies > 0:
            self._next_action = "inbox"
            self.next_title.setText(tr("dash.next_inbox_title").format(n=replies))
            self.next_body.setText(tr("dash.next_inbox_body"))
            self.btn_primary.setText(tr("dash.next_inbox_cta"))
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
        self._compute_next_action(cfg, stats)

        self.kpi_cards["matches"].set_value(
            stats.get("matches_ge_75", 0),
            tr("dash.kpi_matches"),
            hint=tr("dash.kpi_matches_hint").format(n=stats.get("new_today", 0)),
        )
        review_n = int(stats.get("needs_review") or 0)
        captcha_n = int(stats.get("captcha") or 0)
        review_hint = tr("dash.kpi_review_hint")
        if captcha_n > 0:
            review_hint = tr("dash.kpi_review_hint_captcha").format(n=captcha_n)
        self.kpi_cards["needs_review"].set_value(
            review_n,
            tr("dash.needs_review"),
            hint=review_hint,
        )
        self.kpi_cards["applications"].set_value(
            stats.get("applications_active", stats.get("applications_today", 0)),
            tr("dash.kpi_applications"),
            hint=tr("dash.kpi_applications_hint"),
        )
        self.kpi_cards["replies"].set_value(
            stats.get("replies_attention", 0),
            tr("dash.kpi_replies"),
            hint=tr("dash.kpi_replies_hint"),
        )

        mode = cfg.settings.mode
        dry = tr("dash.on") if cfg.settings.dry_run else tr("dash.off")
        paused = bool(cfg.settings.automation_paused)
        paused_label = tr("dash.paused") if paused else tr("dash.active")
        auto = tr("dash.on") if cfg.settings.run_automatically else tr("dash.off")
        self.mode_label.setText(
            f"{tr('dash.mode')}: {mode}  |  {tr('dash.dry_run')}: {dry}  |  "
            f"{tr('dash.automation')}: {auto} ({paused_label})"
        )
        self.mode_chip.setText(f"{tr('dash.mode')}: {mode}")
        self.btn_pause.setText(
            tr("btn.resume_automation") if paused else tr("btn.pause_automation")
        )
        self._rebuild_actions_menu()
        meta = self.config_service.load_meta()
        self.last_run_label.setText(str(meta.get("last_search_run") or "—"))
        self.next_run_label.setText(str(meta.get("next_scheduled_run") or "—"))

        loc = cfg.profile.location
        if not (loc.home_address or "").strip() and loc.home_latitude is None:
            self.home_warning_label.setText(tr("dash.home_missing"))
            self.home_warning_label.setVisible(True)
        else:
            self.home_warning_label.clear()
            self.home_warning_label.setVisible(False)

        self.advanced_stats.setText(
            " · ".join(
                [
                    f"{tr('dash.found_today')}: {stats.get('jobs_found_today', 0)}",
                    f"{tr('dash.new')}: {stats.get('new_today', 0)}",
                    f"{tr('dash.applied')}: {stats.get('applications_today', 0)}",
                    f"{tr('dash.this_run')}: {stats.get('this_run', 0)}",
                    f"{tr('dash.captcha')}: {stats.get('captcha', 0)}",
                    f"{tr('dash.errors')}: {stats.get('errors', 0)}",
                ]
            )
        )

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
