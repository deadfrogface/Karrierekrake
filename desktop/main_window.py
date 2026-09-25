"""Main application window."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

from PySide6.QtCore import QObject, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QGuiApplication, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from desktop.branding import icon_path

from desktop.i18n import i18n, install_qt_translator, tr
from desktop.pages.applications import ApplicationsPage
from desktop.pages.dashboard import DashboardPage
from desktop.pages.inbox import InboxPage
from desktop.pages.jobs import JobsPage
from desktop.pages.logs import LogsPage
from desktop.pages.profile import ProfilePage
from desktop.pages.search import SearchPage
from desktop.pages.settings import SettingsPage
from desktop.services import ConfigService
from desktop.services.schedule_service import ScheduleService
from desktop.services.shutdown import get_shutdown_manager
from desktop.theme import apply_theme
from desktop.tray import AppTray, app_icon
from desktop.workers import PipelineWorker, connect_queued, start_worker, thread_is_running
from desktop.wizard import FirstRunWizard
from desktop.design_system.a11y import annotate_nav_button, set_accessible_name, set_accessible_description, set_automation_id
from desktop.widgets.about_dialog import AboutDialog
from desktop.widgets.confirm_dialog import confirm_action


class _GeoIndexBridge(QObject):
    """Hop from the geo-loader thread back onto the UI thread."""

    ready = Signal()


class MainWindow(QMainWindow):
    def __init__(self, config_service: ConfigService) -> None:
        super().__init__()
        self.config_service = config_service
        self._force_quit = False
        self._geo_bridge = _GeoIndexBridge(self)
        self._geo_bridge.ready.connect(self._refresh_home_notices_after_geo)
        from core.geo_resolve import (
            bind_ui_thread,
            preload_geo_index_async,
            when_geo_index_ready,
        )

        bind_ui_thread()

        def _emit_geo_ready() -> None:
            self._geo_bridge.ready.emit()

        when_geo_index_ready(_emit_geo_ready)
        preload_geo_index_async()
        self._shutting_down = False
        self._worker = None
        self._thread = None
        self.setMinimumSize(900, 650)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setWindowTitle(tr("app.name"))
        self.setWindowIcon(app_icon())
        set_automation_id(self, "kk.main_window")

        central = QWidget()
        self.setCentralWidget(central)
        shell = QHBoxLayout(central)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)

        self.sidebar = QFrame()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setMinimumWidth(160)
        self.sidebar.setMaximumWidth(220)
        side_layout = QVBoxLayout(self.sidebar)
        side_layout.setContentsMargins(10, 14, 10, 14)
        side_layout.setSpacing(6)
        brand_row = QHBoxLayout()
        brand_row.setSpacing(8)
        self.brand_icon = QLabel()
        self.brand_icon.setFixedSize(36, 36)
        ip = icon_path(64) or icon_path(48) or icon_path(32)
        if ip is not None:
            pix = QPixmap(str(ip))
            if not pix.isNull():
                self.brand_icon.setPixmap(
                    pix.scaled(
                        36,
                        36,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
        brand_text = QVBoxLayout()
        brand_text.setSpacing(2)
        self.brand = QLabel(tr("app.name"))
        self.brand.setObjectName("Brand")
        self.brand_tagline = QLabel(tr("brand.tagline"))
        self.brand_tagline.setObjectName("BrandTagline")
        self.brand_tagline.setWordWrap(True)
        brand_text.addWidget(self.brand)
        brand_text.addWidget(self.brand_tagline)
        brand_row.addWidget(self.brand_icon, 0, Qt.AlignmentFlag.AlignTop)
        brand_row.addLayout(brand_text, 1)
        side_layout.addLayout(brand_row)
        side_layout.addSpacing(8)

        self.stack = QStackedWidget()
        self.stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.dashboard = DashboardPage(config_service)
        self.profile = ProfilePage(config_service)
        self.search = SearchPage(config_service)
        self.jobs = JobsPage(config_service)
        self.applications = ApplicationsPage(config_service)
        self.inbox = InboxPage(config_service)
        # Lifecycle remains reachable via Postfach (embedded) — keep direct ref for refresh.
        self.lifecycle = self.inbox.lifecycle
        self.settings = SettingsPage(config_service)
        self.logs = LogsPage(config_service)

        # V2 primary nav: Übersicht · Jobs · Bewerbungen · Postfach · Profil
        # Bottom: Einstellungen · Hilfe
        # Hidden stack pages (preserved): Suche, Protokolle
        self._primary_nav: list[tuple[str, QWidget]] = [
            ("nav.overview", self.dashboard),
            ("nav.jobs", self.jobs),
            ("nav.applications", self.applications),
            ("nav.inbox", self.inbox),
            ("nav.profile", self.profile),
        ]
        self._utility_nav: list[tuple[str, QWidget]] = [
            ("nav.settings", self.settings),
        ]
        # Full stack order (nav buttons only for primary + utility; search/logs via helpers)
        self._nav_defs = [
            *self._primary_nav,
            *self._utility_nav,
            ("nav.search", self.search),
            ("nav.logs", self.logs),
        ]
        self._page_index = {key: i for i, (key, _) in enumerate(self._nav_defs)}
        # Alias legacy keys so older navigate_to calls keep working
        self._page_index["nav.dashboard"] = self._page_index["nav.overview"]
        self._page_index["nav.guenther"] = self._page_index["nav.inbox"]
        self._page_index["nav.lifecycle"] = self._page_index["nav.inbox"]

        for _key, page in self._nav_defs:
            self.stack.addWidget(page)

        self.nav_buttons: list[QPushButton] = []
        primary_total = len(self._primary_nav) + len(self._utility_nav) + 1  # +Hilfe
        for i, (key, _page) in enumerate(self._primary_nav):
            btn = QPushButton(tr(key))
            slug = key.replace("nav.", "")
            set_automation_id(btn, f"kk.nav.{slug}")
            btn.setCheckable(True)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn.clicked.connect(lambda checked=False, idx=i: self._navigate(idx))
            annotate_nav_button(btn, name=tr(key), position=i + 1, total=primary_total)
            self.nav_buttons.append(btn)
            side_layout.addWidget(btn)

        side_layout.addStretch(1)

        for j, (key, _page) in enumerate(self._utility_nav):
            idx = len(self._primary_nav) + j
            btn = QPushButton(tr(key))
            slug = key.replace("nav.", "")
            set_automation_id(btn, f"kk.nav.{slug}")
            btn.setCheckable(True)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn.clicked.connect(lambda checked=False, i=idx: self._navigate(i))
            annotate_nav_button(
                btn, name=tr(key), position=len(self._primary_nav) + j + 1, total=primary_total
            )
            self.nav_buttons.append(btn)
            side_layout.addWidget(btn)

        self.help_btn = QPushButton(tr("nav.help"))
        set_automation_id(self.help_btn, "kk.nav.help")
        self.help_btn.setCheckable(False)
        self.help_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.help_btn.clicked.connect(self.open_help)
        annotate_nav_button(
            self.help_btn,
            name=tr("nav.help"),
            position=primary_total,
            total=primary_total,
        )
        side_layout.addWidget(self.help_btn)

        shell.addWidget(self.sidebar, 0)
        content = QWidget()
        content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(12, 12, 12, 12)
        content_layout.addWidget(self.stack, 1)
        shell.addWidget(content, 1)

        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.progress_label = QLabel(tr("status.ready"))
        set_accessible_name(self.progress_label, tr("status.ready"))
        set_accessible_description(self.progress_label, tr("a11y.status_bar"))
        self.status.addPermanentWidget(self.progress_label)

        self.dashboard.search_requested.connect(self.start_search)
        self.dashboard.apply_requested.connect(self.start_apply_run)
        self.dashboard.test_requested.connect(self.run_application_test)
        self.dashboard.pause_requested.connect(self.toggle_automation_paused)
        self.dashboard.review_requested.connect(self.open_review_queue)
        self.dashboard.cancel_requested.connect(self.cancel_pipeline)
        self.dashboard.clear_jobs_requested.connect(self.clear_job_data)
        self.settings.appearance_changed.connect(self.apply_appearance_from_settings)
        self.settings.settings_saved.connect(self._sync_worker_pause_from_settings)

        self.tray = AppTray(self)
        self.tray.show()
        get_shutdown_manager().set_tray(self.tray)

        i18n.register(self.retranslate_ui)
        self._restore_geometry()
        self._navigate(0)
        self.refresh_all()

    def _restore_geometry(self) -> None:
        state = self.config_service.get_window_state()
        width = int(state.get("width") or 1180)
        height = int(state.get("height") or 760)
        width = max(900, width)
        height = max(650, height)
        self.resize(width, height)
        x = state.get("x")
        y = state.get("y")
        if isinstance(x, int) and isinstance(y, int):
            screen = QGuiApplication.primaryScreen()
            if screen is not None:
                geo: QRect = screen.availableGeometry()
                if geo.contains(x + 40, y + 40):
                    self.move(x, y)
        if state.get("maximized"):
            self.showMaximized()

    def _save_geometry(self) -> None:
        maximized = self.isMaximized()
        # Use normal geometry when maximized so restore works
        geo = self.normalGeometry() if maximized else self.geometry()
        self.config_service.save_window_state(
            width=geo.width(),
            height=geo.height(),
            x=geo.x(),
            y=geo.y(),
            maximized=maximized,
        )

    def retranslate_ui(self) -> None:
        self.setWindowTitle(tr("app.name"))
        self.brand.setText(tr("app.name"))
        if hasattr(self, "brand_tagline"):
            self.brand_tagline.setText(tr("brand.tagline"))
        primary_total = len(self._primary_nav) + len(self._utility_nav) + 1
        labeled = list(self._primary_nav) + list(self._utility_nav)
        for i, (btn, (key, _)) in enumerate(zip(self.nav_buttons, labeled)):
            btn.setText(tr(key))
            annotate_nav_button(btn, name=tr(key), position=i + 1, total=primary_total)
        if hasattr(self, "help_btn"):
            self.help_btn.setText(tr("nav.help"))
            annotate_nav_button(
                self.help_btn, name=tr("nav.help"), position=primary_total, total=primary_total
            )
        self.progress_label.setText(tr("status.ready"))
        set_accessible_name(self.progress_label, tr("status.ready"))
        for page in (
            self.dashboard,
            self.profile,
            self.search,
            self.jobs,
            self.applications,
            self.inbox,
            self.settings,
            self.logs,
        ):
            if hasattr(page, "retranslate"):
                page.retranslate()
            if hasattr(page, "retranslate_ui"):
                page.retranslate_ui()
        if hasattr(self.tray, "retranslate_ui"):
            self.tray.retranslate_ui()

    def open_help(self) -> None:
        AboutDialog(self, data_dir=self.config_service.dirs["root"]).exec()

    def open_search_intent(self) -> None:
        """Suche remains a first-class page, not primary nav (V2 IA)."""
        self.navigate_to("nav.search")

    def open_diagnose_logs(self) -> None:
        self.navigate_to("nav.logs")

    def _navigate(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        for i, btn in enumerate(self.nav_buttons):
            btn.setChecked(i == index)
        page = self.stack.widget(index)
        if hasattr(page, "refresh"):
            page.refresh()
        if hasattr(page, "load_from_config"):
            page.load_from_config()

    def apply_appearance_from_settings(self) -> None:
        cfg = self.config_service.load()
        app = QApplication.instance()
        lang = cfg.settings.language or "de"
        if app is not None:
            apply_theme(
                app,
                cfg.settings.theme or "system",
                high_contrast=bool(getattr(cfg.settings, "high_contrast", False)),
            )
            install_qt_translator(app, lang)
        i18n.set_language(lang)

    def _refresh_home_notices_after_geo(self) -> None:
        """Notice labels only. Does not rebuild profile cards."""
        if self._shutting_down:
            return
        if not hasattr(self, "dashboard"):
            QTimer.singleShot(0, self._refresh_home_notices_after_geo)
            return
        try:
            self.dashboard.refresh()
            self.profile.refresh_home_status()
            self.profile.location_work.refresh_home_notice(
                self.config_service.load().profile.location
            )
            self.settings._refresh_home_notice()
            self.jobs.refresh()
        except Exception:
            return

    def refresh_all(self) -> None:
        self.dashboard.refresh()
        self.jobs.refresh()
        self.applications.refresh()
        self.inbox.refresh()
        self.profile.load_from_config()
        self.search.load_from_config()
        self.settings.load_from_config()
        self.logs.refresh()

    def navigate_to(self, nav_key: str) -> None:
        idx = self._page_index.get(nav_key)
        if idx is not None:
            self._navigate(idx)

    def start_apply_run(self) -> None:
        cfg = self.config_service.load()
        mode = cfg.settings.mode
        if mode == "search_only":
            mode = "review_before_submit"
        self._start_pipeline(mode=mode, action_label=tr("status.apply_starting"))

    def run_application_test(self) -> None:
        # Deepcopy so dry_run / mode overrides never mutate the cached GUI config.
        cfg = deepcopy(self.config_service.load())
        cfg.settings.dry_run = True
        self._start_pipeline(
            mode="review_before_submit",
            config_override=cfg,
            action_label=tr("status.apply_test_starting"),
        )

    def start_search(self) -> None:
        self._start_pipeline(mode="search_only", action_label=tr("status.search_starting"))

    def _start_pipeline(self, mode: str, config_override=None, action_label: str | None = None) -> None:
        if thread_is_running(self._thread):
            QMessageBox.information(self, tr("app.name"), tr("msg.pipeline_running"))
            return
        # Always snapshot: GUI load()/save() and ConfigService.config must not
        # mutate a live worker's safety settings mid-search / mid-apply.
        cfg = deepcopy(config_override or self.config_service.load())
        if bool(getattr(cfg.settings, "automation_paused", False)):
            QMessageBox.information(self, tr("app.name"), tr("msg.automation_paused"))
            return
        titles = list(cfg.profile.jobs.desired_titles or [])
        from app.main import resolve_search_titles

        searchable = resolve_search_titles(cfg)
        if not searchable:
            QMessageBox.warning(self, tr("app.name"), tr("msg.no_job_titles"))
            return
        _ = titles  # desired titles optional in discovery mode
        loc = cfg.profile.location
        if not (loc.home_address or "").strip() and not loc.allow_remote_germany:
            QMessageBox.warning(self, tr("app.name"), tr("msg.no_search_location"))
            return
        status = action_label or tr("status.running")
        self.progress_label.setText(status)
        self.dashboard.set_status(status)
        self.dashboard.set_pipeline_running(True)
        worker = PipelineWorker(cfg, mode=mode)
        thread = start_worker(worker)

        def on_progress(msg: str) -> None:
            if self._shutting_down:
                return
            self.progress_label.setText(msg)
            self.dashboard.set_status(msg)

        def on_finished(stats: dict) -> None:
            if self._shutting_down:
                return
            self._worker = None
            self._thread = None
            self.dashboard.set_pipeline_running(False)
            self.progress_label.setText(tr("status.done"))
            self.dashboard.set_status(tr("status.done"))
            # Persist only home coords (never dry_run/mode overrides from apply-test).
            if stats.get("home_updated") and getattr(worker, "config", None) is not None:
                try:
                    self.config_service.save_home_coords_from(worker.config)
                except Exception:
                    pass
            self.config_service.set_last_search(
                datetime.now(timezone.utc).replace(microsecond=0).isoformat()
            )
            self.refresh_all()
            extra = ""
            if stats.get("config_error") == "empty_queries":
                extra = "\n" + tr("msg.empty_queries")
            if stats.get("source_errors"):
                extra = (extra + "\n" if extra else "\n") + "\n".join(stats.get("source_errors") or [])
            from core.location import home_location_notice

            notice = home_location_notice(self.config_service.load().profile.location)
            if notice.ask_postal and notice.notice_key:
                extra += "\n\n" + tr(notice.notice_key)
            if stats.get("ats_unknown") is not None:
                extra += (
                    f"\nATS: supported={stats.get('ats_supported', 0)} "
                    f"unknown={stats.get('ats_unknown', 0)} "
                    f"unsupported={stats.get('ats_detected_unsupported', 0)}"
                )
            if stats.get("cancelled"):
                self.progress_label.setText(tr("status.cancelled"))
                self.dashboard.set_status(tr("status.cancelled"))
                QMessageBox.information(
                    self,
                    tr("msg.run_cancelled"),
                    f"{tr('msg.run_cancelled_body')}\n"
                    f"{tr('msg.new')}: {stats.get('new', 0)} | {tr('msg.matches')}: {stats.get('matches', 0)} | "
                    f"{tr('msg.applied')}: {stats.get('applied', 0)} | {tr('msg.review')}: {stats.get('needs_review', 0)}"
                    f"{extra}",
                )
                self._schedule_status_reset(tr("status.cancelled"))
            else:
                QMessageBox.information(
                    self,
                    tr("msg.run_done"),
                    f"{tr('msg.new')}: {stats.get('new', 0)} | {tr('msg.matches')}: {stats.get('matches', 0)} | "
                    f"{tr('msg.applied')}: {stats.get('applied', 0)} | {tr('msg.review')}: {stats.get('needs_review', 0)}"
                    f"{extra}",
                )

        def on_failed(err: str) -> None:
            if self._shutting_down:
                return
            self._worker = None
            self._thread = None
            self.dashboard.set_pipeline_running(False)
            self.progress_label.setText(tr("status.error"))
            self.dashboard.set_status(tr("status.error"))
            QMessageBox.warning(
                self,
                tr("msg.error"),
                tr("msg.error_body", err=err[:300]),
            )
            self.logs.refresh()

        connect_queued(worker.progress, on_progress)
        connect_queued(worker.finished, on_finished)
        connect_queued(worker.failed, on_failed)
        self._worker = worker
        self._thread = thread

    STATUS_RESET_MS = 5000

    def _schedule_status_reset(self, shown: str, delay_ms: int | None = None) -> None:
        """Return a finished-run status (e.g. "Abgebrochen") to "Bereit" after a moment."""

        def _reset() -> None:
            try:
                if self._shutting_down or self._pipeline_running():
                    return
                if self.progress_label.text() != shown:
                    return
                ready = tr("status.ready")
                self.progress_label.setText(ready)
                set_accessible_name(self.progress_label, ready)
                self.dashboard.set_status(ready)
            except RuntimeError:
                pass

        QTimer.singleShot(self.STATUS_RESET_MS if delay_ms is None else delay_ms, _reset)

    def cancel_pipeline(self) -> None:
        worker = getattr(self, "_worker", None)
        if worker is not None and hasattr(worker, "request_cancel"):
            worker.request_cancel()
            self.progress_label.setText(tr("btn.cancel_search") + "…")
            self.dashboard.set_status(tr("btn.cancel_search") + "…")

    def clear_job_data(self) -> None:
        if not confirm_action(
            self,
            tr("msg.clear_jobs_title"),
            tr("msg.clear_jobs_body"),
            confirm_text=tr("btn.clear_jobs"),
            destructive=True,
        ):
            return
        cfg = self.config_service.load()
        from core.database import Database

        Database(cfg.db_path).clear_job_data(
            clear_applications=True,
            clear_source_status=True,
            clear_search_runs=True,
            clear_geocode_cache=False,
        )
        self.refresh_all()
        QMessageBox.information(self, tr("msg.clear_jobs_title"), tr("msg.clear_jobs_done"))

    def open_review_queue(self) -> None:
        self.navigate_to("nav.applications")
        self.applications.show_review_only()

    def toggle_automation_paused(self) -> None:
        cfg = self.config_service.load()
        self.set_automation_paused(not bool(cfg.settings.automation_paused))

    def set_automation_paused(self, paused: bool) -> None:
        cfg = self.config_service.load()
        cfg.settings.automation_paused = paused
        self.config_service.save(cfg)
        ScheduleService(cfg).sync_from_config()
        # Fail-closed: pause must stop an in-flight pipeline (config is snapshotted).
        self._sync_worker_pause(paused)
        self.dashboard.refresh()
        self.settings.load_from_config()
        self.progress_label.setText(
            tr("status.paused") if paused else tr("status.resumed")
        )

    def _sync_worker_pause_from_settings(self) -> None:
        cfg = self.config_service.load()
        self._sync_worker_pause(bool(cfg.settings.automation_paused))

    def _sync_worker_pause(self, paused: bool) -> None:
        worker = getattr(self, "_worker", None)
        if worker is not None and hasattr(worker, "set_paused"):
            worker.set_paused(paused)

    def force_quit(self) -> None:
        """Explicit exit (tray menu). Always terminates the process."""
        self._force_quit = True
        self.close()

    def _pipeline_running(self) -> bool:
        return thread_is_running(self._thread)

    def _confirm_exit_while_busy(self) -> bool:
        box = QMessageBox(self)
        box.setWindowTitle(tr("app.name"))
        box.setIcon(QMessageBox.Icon.Warning)
        box.setText(tr("shutdown.busy_title"))
        box.setInformativeText(tr("shutdown.busy_body"))
        cancel_btn = box.addButton(tr("shutdown.cancel"), QMessageBox.ButtonRole.RejectRole)
        quit_btn = box.addButton(tr("shutdown.quit_anyway"), QMessageBox.ButtonRole.AcceptRole)
        box.setDefaultButton(cancel_btn)
        box.exec()
        return box.clickedButton() is quit_btn

    def closeEvent(self, event: QCloseEvent) -> None:
        self._save_geometry()
        cfg = self.config_service.load()
        minimize = bool(getattr(cfg.settings, "minimize_to_tray", False))

        # Optional: hide to tray only when explicitly enabled and not forcing exit.
        if (
            not self._force_quit
            and not self._shutting_down
            and minimize
            and self.tray.isVisible()
        ):
            self.hide()
            self.tray.showMessage(
                tr("app.name"),
                tr("tray.running"),
                self.tray.MessageIcon.Information,
                2500,
            )
            event.ignore()
            return

        if self._pipeline_running() and not self._shutting_down:
            if not self._confirm_exit_while_busy():
                event.ignore()
                self._force_quit = False
                return

        self._shutting_down = True
        event.accept()
        get_shutdown_manager().shutdown(reason="window_close")

    def maybe_run_wizard(self) -> None:
        if not self.config_service.is_first_run():
            return
        wizard = FirstRunWizard(self.config_service, self)
        if wizard.exec():
            self.refresh_all()
