"""Übersicht — demo-faithful hierarchy: stateful search CTA, calm KPIs, no diagnostics."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.database import Database
from desktop.design_system.a11y import set_accessible_name
from desktop.design_system.polish import (
    apply_button_icon,
    footer_actions_layout,
    polish_card,
    polish_interactive,
)
from desktop.design_system.v2_chrome import ContentCard, KpiCard, PageHeader
from desktop.i18n import i18n, tr, tr_n
from desktop.services import ConfigService
from desktop.util.human_time import format_human_datetime
from desktop.widgets.scroll_page import wrap_scrollable


class DashboardPage(QWidget):
    search_requested = Signal()
    apply_requested = Signal()
    test_requested = Signal()
    pause_requested = Signal()
    review_requested = Signal()
    cancel_requested = Signal()
    clear_jobs_requested = Signal()

    # idle | starting | running | cancelling
    _SEARCH_IDLE = "idle"
    _SEARCH_STARTING = "starting"
    _SEARCH_RUNNING = "running"
    _SEARCH_CANCELLING = "cancelling"

    def __init__(self, config_service: ConfigService, parent=None) -> None:
        super().__init__(parent)
        self.config_service = config_service
        self._next_action = "search"
        self._search_state = self._SEARCH_IDLE
        self._had_search = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # White sticky-style header strip — title only (primary CTAs live bottom-right)
        header_wrap = QWidget()
        header_wrap.setObjectName("Card")
        header_row = QHBoxLayout(header_wrap)
        header_row.setContentsMargins(24, 16, 24, 16)
        header_row.setSpacing(12)
        self.header = PageHeader()
        header_row.addWidget(self.header, stretch=1)
        outer.addWidget(header_wrap)

        self.btn_search = QPushButton()
        self.btn_search.setObjectName("PrimaryButton")
        self.btn_search.setAccessibleDescription("kk.search.toggle")
        self.btn_search.setMinimumHeight(40)
        self.btn_search.setMinimumWidth(180)
        self.btn_search.clicked.connect(self._on_search_cta)
        polish_interactive(self.btn_search)
        # Compat: cancel button aliases the same CTA when running
        self.btn_cancel = self.btn_search

        # Constrained content column (demo max-w-6xl feel). Scrolls on short
        # screens instead of squeezing cards; the search CTA footer stays pinned.
        content = QWidget()
        content.setMaximumWidth(1100)
        content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        root = QVBoxLayout(content)
        root.setContentsMargins(24, 20, 24, 8)
        root.setSpacing(20)

        scroll_body = QWidget()
        content_host = QHBoxLayout(scroll_body)
        content_host.setContentsMargins(0, 0, 0, 0)
        content_host.addStretch(1)
        content_host.addWidget(content, stretch=6)
        content_host.addStretch(1)
        self.body_scroll = wrap_scrollable(scroll_body, min_content_width=560)
        outer.addWidget(self.body_scroll, stretch=1)

        self.queue_section = QLabel()
        self.queue_section.setObjectName("KkHint")
        root.addWidget(self.queue_section)

        self.hero = ContentCard()
        self.hero.setObjectName("HeroCard")
        # Never squeeze the queue card below its content (clipped CTA on short windows).
        self.hero.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        hero_body = self.hero.body()
        self.next_title = QLabel()
        self.next_title.setObjectName("NextActionTitle")
        self.next_body = QLabel()
        self.next_body.setWordWrap(True)
        self.next_body.setObjectName("PageSubtitle")
        self.btn_primary = QPushButton()
        self.btn_primary.setObjectName("AccentButton")
        self.btn_primary.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_primary.clicked.connect(self._on_primary)
        hero_btns = QHBoxLayout()
        hero_btns.addStretch()
        hero_btns.addWidget(self.btn_primary)
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
        for i, (key, card) in enumerate(self.kpi_cards.items()):
            kpi_grid.addWidget(card, 0, i)
            card.activated.connect(lambda k=key: self._on_kpi_activated(k))
        root.addLayout(kpi_grid)

        meta_row = QHBoxLayout()
        meta_row.setSpacing(12)
        self.last_run_card = ContentCard()
        last_body = self.last_run_card.body()
        self.last_run_caption = QLabel()
        self.last_run_caption.setObjectName("KkHint")
        self.last_run_label = QLabel("—")
        self.last_run_label.setObjectName("NextActionTitle")
        last_body.addWidget(self.last_run_caption)
        last_body.addWidget(self.last_run_label)
        self.next_run_card = ContentCard()
        next_body = self.next_run_card.body()
        self.next_run_caption = QLabel()
        self.next_run_caption.setObjectName("KkHint")
        self.next_run_label = QLabel("—")
        self.next_run_label.setObjectName("NextActionTitle")
        self.mode_chip = QLabel()
        self.mode_chip.setObjectName("BadgeMuted")
        next_body.addWidget(self.next_run_caption)
        next_body.addWidget(self.next_run_label)
        next_body.addWidget(self.mode_chip, alignment=Qt.AlignmentFlag.AlignLeft)
        meta_row.addWidget(self.last_run_card)
        meta_row.addWidget(self.next_run_card)
        root.addLayout(meta_row)

        self.home_warning_label = QLabel()
        self.home_warning_label.setWordWrap(True)
        self.home_warning_label.setObjectName("KkNotice")
        root.addWidget(self.home_warning_label)

        # Hidden compat widgets (signals / older tests) — never shown in production UI
        self.mode_label = QLabel()
        self.mode_label.hide()
        self.status_label = QLabel()
        self.status_label.hide()
        self.advanced_section = QLabel()
        self.advanced_section.hide()
        self.advanced_stats = QLabel()
        self.advanced_stats.hide()
        self.run_detail_label = QLabel()
        self.run_detail_label.hide()
        self.more_actions = QPushButton()
        self.more_actions.hide()
        self.btn_apply = QPushButton()
        self.btn_apply.hide()
        self.btn_apply.clicked.connect(self.apply_requested.emit)
        self.btn_test = QPushButton()
        self.btn_test.hide()
        self.btn_test.clicked.connect(self.test_requested.emit)
        self.btn_pause = QPushButton()
        self.btn_pause.hide()
        self.btn_pause.clicked.connect(self.pause_requested.emit)
        self.btn_review = QPushButton()
        self.btn_review.hide()
        self.btn_review.clicked.connect(self.review_requested.emit)
        self.btn_clear_jobs = QPushButton()
        self.btn_clear_jobs.hide()
        self.btn_clear_jobs.clicked.connect(self.clear_jobs_requested.emit)

        root.addStretch(1)

        # Primary search CTA — bottom-right of the content column (not header)
        self._cta_footer = footer_actions_layout(self.btn_search)
        footer_column = QWidget()
        footer_column.setMaximumWidth(1100)
        footer_column.setLayout(self._cta_footer)
        self._cta_footer.setContentsMargins(24, 8, 24, 20)
        footer_host = QHBoxLayout()
        footer_host.setContentsMargins(0, 0, 0, 0)
        footer_host.addStretch(1)
        footer_host.addWidget(footer_column, stretch=6)
        footer_host.addStretch(1)
        outer.addLayout(footer_host)

        polish_card(self.hero)
        for card in self.kpi_cards.values():
            polish_card(card)
        polish_card(self.last_run_card)
        polish_card(self.next_run_card)

        self.page_title = self.header.title
        self.page_subtitle = self.header.subtitle
        self.cards = self.kpi_cards
        self.search_banner = self.hero  # compat alias

        self.retranslate_ui()

    def _on_search_cta(self) -> None:
        if self._search_state in {self._SEARCH_RUNNING, self._SEARCH_STARTING}:
            self._search_state = self._SEARCH_CANCELLING
            self._sync_search_cta()
            self.cancel_requested.emit()
            return
        if self._search_state == self._SEARCH_CANCELLING:
            return
        self._search_state = self._SEARCH_STARTING
        self._sync_search_cta()
        self.search_requested.emit()

    def _sync_search_cta(self) -> None:
        lang = i18n.language if hasattr(i18n, "language") else "de"
        _ = lang
        if self._search_state == self._SEARCH_STARTING:
            text = tr("dash.search_starting")
            self.btn_search.setObjectName("SecondaryButton")
            self.btn_search.setEnabled(False)
        elif self._search_state == self._SEARCH_RUNNING:
            text = tr("btn.cancel_search")
            self.btn_search.setObjectName("SecondaryButton")
            self.btn_search.setEnabled(True)
        elif self._search_state == self._SEARCH_CANCELLING:
            text = tr("dash.search_cancelling")
            self.btn_search.setObjectName("SecondaryButton")
            self.btn_search.setEnabled(False)
        else:
            text = tr("btn.search_again") if self._had_search else tr("btn.find_jobs")
            self.btn_search.setObjectName("PrimaryButton")
            self.btn_search.setEnabled(True)
        self.btn_search.setText(text)
        set_accessible_name(self.btn_search, text)
        self.btn_search.setAccessibleDescription("kk.search.toggle")
        icon_kind = "search"
        icon_color = "#ffffff"
        if self._search_state == self._SEARCH_IDLE:
            icon_kind = "rocket" if not self._had_search else "search"
        elif self._search_state in {self._SEARCH_RUNNING, self._SEARCH_CANCELLING}:
            icon_kind = "close"
            icon_color = "#1c2430"
        apply_button_icon(self.btn_search, icon_kind, color=icon_color)
        style = self.btn_search.style()
        if style is not None:
            style.unpolish(self.btn_search)
            style.polish(self.btn_search)

    def _navigate(self, nav_key: str) -> bool:
        parent = self.window()
        if parent is not None and parent is not self and hasattr(parent, "navigate_to"):
            parent.navigate_to(nav_key)  # type: ignore[attr-defined]
            return True
        return False

    def _on_kpi_activated(self, key: str) -> None:
        if key == "needs_review":
            self.review_requested.emit()
            return
        nav_key = {
            "matches": "nav.jobs",
            "applications": "nav.applications",
            "replies": "nav.inbox",
        }.get(key)
        if nav_key:
            self._navigate(nav_key)

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
            # Avoid duplicating search CTA — navigate to Jobs instead
            parent = self.window()
            if parent is not None and hasattr(parent, "navigate_to"):
                parent.navigate_to("nav.jobs")  # type: ignore[attr-defined]
                return
            self.search_requested.emit()

    def retranslate_ui(self) -> None:
        self.header.set_texts(tr("dash.greeting"), tr("dash.greeting_sub"))
        self.queue_section.setText(tr("dash.section_queue"))
        self.kpi_section.setText(tr("dash.section_kpis"))
        self.advanced_section.setText(tr("dash.section_advanced"))
        self.last_run_caption.setText(tr("dash.last_search"))
        self.next_run_caption.setText(tr("dash.next_run"))
        self.btn_apply.setText(tr("btn.start_apply"))
        self.btn_test.setText(tr("btn.apply_test"))
        self.btn_review.setText(tr("btn.review_queue"))
        self.btn_clear_jobs.setText(tr("btn.clear_jobs"))
        for card in self.kpi_cards.values():
            card.set_clickable(True, tooltip=tr("dash.kpi_open_hint"))
        self._sync_search_cta()
        self.status_label.setText(tr("status.ready"))
        self.refresh()

    def set_pipeline_running(self, running: bool) -> None:
        if running:
            self._search_state = self._SEARCH_RUNNING
            self._had_search = True
        else:
            if self._search_state == self._SEARCH_CANCELLING:
                self._search_state = self._SEARCH_IDLE
            else:
                self._search_state = self._SEARCH_IDLE
        self._sync_search_cta()
        self.btn_primary.setEnabled(
            self._search_state == self._SEARCH_IDLE or self._next_action in {"review", "inbox"}
        )

    def _mode_label(self, mode: str) -> str:
        return {
            "search_only": tr("settings.mode.search"),
            "review_before_submit": tr("settings.mode.review"),
            "fully_automatic": tr("settings.mode.auto"),
        }.get(mode, tr("settings.mode.search"))

    def _compute_next_action(self, cfg, stats: dict) -> None:
        titles = [t for t in (cfg.profile.jobs.desired_titles or []) if str(t).strip()]
        if not titles:
            self._next_action = "profile"
            self.next_title.setText(tr("dash.next_profile_title"))
            self.next_body.setText(tr("dash.next_profile_body"))
            self.btn_primary.setText(tr("dash.next_profile_cta"))
            self.hero.setVisible(True)
            return
        replies = int(stats.get("replies_attention") or 0)
        if replies > 0:
            self._next_action = "inbox"
            self.next_title.setText(tr_n("dash.next_inbox_title", replies))
            self.next_body.setText(tr("dash.next_inbox_body"))
            self.btn_primary.setText(tr("dash.next_inbox_cta"))
            self.hero.setVisible(True)
            return
        if int(stats.get("needs_review") or 0) > 0:
            self._next_action = "review"
            self.next_title.setText(tr("dash.next_review_title"))
            self.next_body.setText(tr("dash.next_review_body"))
            self.btn_primary.setText(tr("btn.review_queue"))
            self.hero.setVisible(True)
            return
        # No queue item — hide redundant search card (primary CTA is bottom footer)
        self._next_action = "search"
        self.hero.setVisible(False)
        self.next_title.setText(tr("dash.next_search_title"))
        self.next_body.setText(tr("dash.next_search_body"))
        self.btn_primary.setText(tr("btn.find_jobs"))

    def refresh(self) -> None:
        cfg = self.config_service.load()
        db = Database(cfg.db_path)
        stats = db.dashboard_stats()
        self._compute_next_action(cfg, stats)
        lang = (cfg.settings.language or "de").lower()

        self.kpi_cards["matches"].set_value(
            stats.get("matches_ge_75", 0),
            tr("dash.kpi_matches"),
            hint=tr("dash.kpi_matches_hint").format(n=stats.get("new_today", 0)),
        )
        review_n = int(stats.get("needs_review") or 0)
        self.kpi_cards["needs_review"].set_value(
            review_n,
            tr("dash.needs_review"),
            hint=tr("dash.kpi_review_hint"),
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
        self.mode_chip.setText(self._mode_label(mode))
        self.mode_label.setText(self._mode_label(mode))
        paused = bool(cfg.settings.automation_paused)
        self.btn_pause.setText(
            tr("btn.resume_automation") if paused else tr("btn.pause_automation")
        )
        meta = self.config_service.load_meta()
        self.last_run_label.setText(
            format_human_datetime(meta.get("last_search_run"), lang=lang)
        )
        self.next_run_label.setText(
            format_human_datetime(meta.get("next_scheduled_run"), lang=lang)
        )

        loc = cfg.profile.location
        home_text = (loc.home_address or "").strip()
        home_known = loc.home_latitude is not None and loc.home_longitude is not None
        if not home_text and not home_known:
            self.home_warning_label.setText(tr("dash.home_missing"))
            self.home_warning_label.setVisible(True)
        else:
            self.home_warning_label.clear()
            self.home_warning_label.setVisible(False)

        # Keep diagnostics populated for tests / developer tooling — never shown.
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
                # A warning from an older run is stale once the home resolved since.
                if st.get("home_warning") and home_text and not home_known:
                    self.home_warning_label.setText(
                        tr("dash.home_unresolved", place=home_text)
                    )
                    self.home_warning_label.setVisible(True)
                detail = (
                    f"raw={st.get('raw_results', st.get('total', '—'))} | "
                    f"dup={st.get('duplicates', '—')} | dist={st.get('distance_removed', st.get('outside', '—'))}"
                )
        self.run_detail_label.setText(detail)

    def set_status(self, text: str) -> None:
        self.status_label.setText(text)
        # Map pipeline status strings into CTA states. "Cancelled"/"Abgebrochen"
        # arrive after the run ended — they must not lock an idle CTA.
        low = (text or "").lower()
        active = self._search_state in {self._SEARCH_RUNNING, self._SEARCH_STARTING}
        if active and any(k in low for k in ("cancel", "abbruch", "abbrechen", "beendet")):
            self._search_state = self._SEARCH_CANCELLING
        elif self._search_state == self._SEARCH_IDLE and any(
            k in low for k in ("running", "läuft", "start", "suche")
        ) and not any(k in low for k in ("cancel", "abbruch", "abbrechen", "abgebrochen")):
            self._search_state = self._SEARCH_STARTING
        self._sync_search_cta()
