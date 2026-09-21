"""Settings page — V2 side-nav IA (demo Einstellungen) with scrolling sections."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.database import Database
from desktop.design_system.a11y import set_accessible_name
from desktop.design_system.v2_chrome import PageHeader
from desktop.i18n import tr
from desktop.services import ConfigService
from desktop.services.browser_install import playwright_available
from desktop.services.schedule_service import ScheduleService
from desktop.widgets.about_dialog import AboutDialog
from desktop.widgets.scroll_page import wrap_scrollable
from desktop.widgets.wheel_guard import IntentionalWheelSpinBox, apply_wheel_guard_to_spinboxes
from desktop.workers import (
    BrowserCheckWorker,
    BrowserRepairWorker,
    connect_queued,
    start_worker,
)


SOURCES = [
    ("bundesagentur", "Bundesagentur"),
    ("indeed", "Indeed"),
    ("linkedin", "LinkedIn"),
    ("stepstone", "StepStone"),
    ("xing", "XING"),
    ("company_sites", "company_sites"),
]

# Demo-aligned inner nav keys (order = stack index).
_SETTINGS_NAV_KEYS = (
    "settings.nav.general",
    "settings.nav.automation",
    "settings.nav.communication",
    "settings.nav.integrations",
    "settings.nav.privacy",
    "settings.nav.advanced",
)


def _scroll_form() -> tuple[QWidget, QVBoxLayout]:
    inner = QWidget()
    layout = QVBoxLayout(inner)
    layout.setContentsMargins(16, 8, 24, 16)
    layout.setSpacing(14)
    page = QWidget()
    outer = QVBoxLayout(page)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.addWidget(wrap_scrollable(inner, min_content_width=520))
    return page, layout


def _collapsible_host(title_btn: QToolButton, body: QWidget) -> QWidget:
    """Progressive-disclosure shell: checkable header toggles body visibility."""
    host = QWidget()
    lay = QVBoxLayout(host)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(4)
    title_btn.setCheckable(True)
    title_btn.setChecked(False)
    title_btn.setObjectName("SecondaryButton")
    body.setVisible(False)
    title_btn.toggled.connect(body.setVisible)
    lay.addWidget(title_btn)
    lay.addWidget(body)
    return host


class SettingsPage(QWidget):
    appearance_changed = Signal()
    settings_saved = Signal()

    def __init__(self, config_service: ConfigService, parent=None) -> None:
        super().__init__(parent)
        self.config_service = config_service
        self._install_thread = None
        self._install_worker = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.header = PageHeader(tr("nav.settings"))
        root.addWidget(self.header)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        self.nav = QListWidget()
        self.nav.setObjectName("SettingsNav")
        self.nav.setFixedWidth(240)
        self.nav.setSpacing(2)
        set_accessible_name(self.nav, tr("nav.settings"))
        self.stack = QStackedWidget()
        # Back-compat: older tests/helpers may still look for `.tabs`
        self.tabs = self.stack

        for key in _SETTINGS_NAV_KEYS:
            item = QListWidgetItem(tr(key))
            item.setData(Qt.ItemDataRole.UserRole, key)
            self.nav.addItem(item)

        body.addWidget(self.nav)
        body.addWidget(self.stack, stretch=1)
        root.addLayout(body, stretch=1)

        # --- 0 Allgemein ---
        general_page, general_layout = _scroll_form()
        self.section_general = QLabel()
        self.section_general.setObjectName("PageTitle")
        general_layout.addWidget(self.section_general)
        self.lang_combo = QComboBox()
        self.lang_combo.addItem("", "de")
        self.lang_combo.addItem("", "en")
        self.theme_combo = QComboBox()
        self.theme_combo.addItem("", "system")
        self.theme_combo.addItem("", "light")
        self.theme_combo.addItem("", "dark")
        self.start_windows = QCheckBox()
        self.minimize_tray = QCheckBox()
        self.general_form = QFormLayout()
        self.lang_label = QLabel()
        self.theme_label = QLabel()
        self.general_form.addRow(self.lang_label, self.lang_combo)
        self.general_form.addRow(self.theme_label, self.theme_combo)
        self.high_contrast = QCheckBox()
        self.general_form.addRow(self.high_contrast)
        self.general_form.addRow(self.start_windows)
        self.general_form.addRow(self.minimize_tray)
        self.about_btn = QPushButton()
        self.about_btn.setObjectName("SecondaryButton")
        self.about_btn.clicked.connect(self.open_about)
        self.general_form.addRow(self.about_btn)
        general_box = QGroupBox()
        self.general_box = general_box
        self.appear_box = general_box  # back-compat attribute
        general_box.setLayout(self.general_form)
        general_layout.addWidget(general_box)
        general_layout.addStretch(1)
        self.stack.addWidget(general_page)

        # --- 1 Automation (mode + schedule + safety limits) ---
        auto_page, auto_layout = _scroll_form()
        self.section_automation = QLabel()
        self.section_automation.setObjectName("PageTitle")
        auto_layout.addWidget(self.section_automation)

        mode_box = QGroupBox()
        self.mode_box = mode_box
        mode_layout = QVBoxLayout(mode_box)
        self.mode_group = QButtonGroup(self)
        self.mode_search = QRadioButton()
        self.mode_review = QRadioButton()
        self.mode_auto = QRadioButton()
        for i, btn in enumerate((self.mode_search, self.mode_review, self.mode_auto)):
            self.mode_group.addButton(btn, i)
            mode_layout.addWidget(btn)
        self.dry_run = QCheckBox()
        mode_layout.addWidget(self.dry_run)
        auto_layout.addWidget(mode_box)

        bg_box = QGroupBox()
        self.bg_box = bg_box
        bform = QFormLayout(bg_box)
        self.run_auto = QCheckBox()
        self.schedule_mode = QComboBox()
        self.interval_hours = IntentionalWheelSpinBox()
        self.interval_hours.setRange(1, 24)
        self.custom_times = QLineEdit()
        self.paused = QCheckBox()
        self.lbl_schedule = QLabel()
        self.lbl_interval = QLabel()
        self.lbl_times = QLabel()
        bform.addRow(self.run_auto)
        bform.addRow(self.lbl_schedule, self.schedule_mode)
        bform.addRow(self.lbl_interval, self.interval_hours)
        bform.addRow(self.lbl_times, self.custom_times)
        bform.addRow(self.paused)
        auto_layout.addWidget(bg_box)

        apply_box = QGroupBox()
        self.apply_box = apply_box
        aform = QFormLayout(apply_box)
        self.min_match_apply = IntentionalWheelSpinBox()
        self.min_match_apply.setRange(0, 100)
        self.max_per_run = IntentionalWheelSpinBox()
        self.max_per_run.setRange(1, 100)
        self.max_per_day = IntentionalWheelSpinBox()
        self.max_per_day.setRange(1, 200)
        self.max_fail = IntentionalWheelSpinBox()
        self.max_fail.setRange(1, 50)
        self.delay = IntentionalWheelSpinBox()
        self.delay.setRange(0, 600)
        self.auto_cover = QCheckBox()
        self.auto_submit = QCheckBox()
        self.lbl_min_match_apply = QLabel()
        self.lbl_max_per_run = QLabel()
        self.lbl_max_per_day = QLabel()
        self.lbl_max_fail = QLabel()
        self.lbl_delay = QLabel()
        aform.addRow(self.lbl_min_match_apply, self.min_match_apply)
        aform.addRow(self.lbl_max_per_run, self.max_per_run)
        aform.addRow(self.lbl_max_per_day, self.max_per_day)
        aform.addRow(self.lbl_max_fail, self.max_fail)
        aform.addRow(self.lbl_delay, self.delay)
        aform.addRow(self.auto_cover)
        aform.addRow(self.auto_submit)
        self.safety_toggle = QToolButton()
        self.safety_toggle.setCheckable(True)
        auto_layout.addWidget(_collapsible_host(self.safety_toggle, apply_box))
        auto_layout.addStretch(1)
        self.stack.addWidget(auto_page)

        # --- 2 Kommunikation & Termine ---
        comm_page, comm_layout = _scroll_form()
        self.section_communication = QLabel()
        self.section_communication.setObjectName("PageTitle")
        comm_layout.addWidget(self.section_communication)
        life_box = QGroupBox()
        self.life_box = life_box
        lform = QFormLayout(life_box)
        self.preferred_contact = QComboBox()
        self.preferred_contact.addItem("E-Mail", "email")
        self.preferred_contact.addItem("Telefon", "phone")
        self.preferred_contact.addItem("Beides", "either")
        self.phone_available = QCheckBox()
        self.telephone_availability = QLineEdit()
        self.working_hours = QLineEdit()
        self.follow_up_days = IntentionalWheelSpinBox()
        self.follow_up_days.setRange(1, 90)
        self.ghosted_days = IntentionalWheelSpinBox()
        self.ghosted_days.setRange(1, 180)
        self.email_draft_only = QCheckBox()
        self.followup_enabled = QCheckBox()
        self.followup_reminders_enabled = QCheckBox()
        self.allow_employer_email_send = QCheckBox()
        self.lbl_preferred_contact = QLabel()
        self.lbl_tel_avail = QLabel()
        self.lbl_working_hours = QLabel()
        self.lbl_follow_up_days = QLabel()
        self.lbl_ghosted_days = QLabel()
        lform.addRow(self.lbl_preferred_contact, self.preferred_contact)
        lform.addRow(self.phone_available)
        lform.addRow(self.lbl_tel_avail, self.telephone_availability)
        lform.addRow(self.lbl_working_hours, self.working_hours)
        lform.addRow(self.lbl_follow_up_days, self.follow_up_days)
        lform.addRow(self.lbl_ghosted_days, self.ghosted_days)
        lform.addRow(self.followup_enabled)
        lform.addRow(self.followup_reminders_enabled)
        lform.addRow(self.email_draft_only)
        lform.addRow(self.allow_employer_email_send)
        comm_layout.addWidget(life_box)
        comm_layout.addStretch(1)
        self.stack.addWidget(comm_page)

        # --- 3 Integrationen (Mail / Kalender Providers + Günther) ---
        integ_page, integ_layout = _scroll_form()
        self.section_integrations = QLabel()
        self.section_integrations.setObjectName("PageTitle")
        integ_layout.addWidget(self.section_integrations)

        oauth_box = QGroupBox()
        self.oauth_box = oauth_box
        oform = QVBoxLayout(oauth_box)

        self.lbl_mail_provider = QLabel()
        self.mail_provider = QComboBox()
        for label, data in (
            ("integrations.mail.none", "none"),
            ("integrations.mail.google", "google_gmail"),
            ("integrations.mail.microsoft", "microsoft_graph"),
            ("integrations.mail.other", "generic_imap"),
        ):
            self.mail_provider.addItem(label, data)
        self.mail_status = QLabel()
        self.mail_status.setWordWrap(True)
        oform.addWidget(self.lbl_mail_provider)
        oform.addWidget(self.mail_provider)
        oform.addWidget(self.mail_status)

        self.lbl_calendar_provider = QLabel()
        self.calendar_provider = QComboBox()
        for label, data in (
            ("integrations.calendar.google", "google_calendar"),
            ("integrations.calendar.microsoft", "microsoft_graph"),
            ("integrations.calendar.other", "generic_caldav"),
            ("integrations.calendar.none_explicit", "none"),
        ):
            self.calendar_provider.addItem(label, data)
        self.calendar_status = QLabel()
        self.calendar_status.setWordWrap(True)
        oform.addWidget(self.lbl_calendar_provider)
        oform.addWidget(self.calendar_provider)
        oform.addWidget(self.calendar_status)

        self.provider_hint = QLabel()
        self.provider_hint.setWordWrap(True)
        oform.addWidget(self.provider_hint)

        self.privacy_connect_gmail_btn = QPushButton()
        self.privacy_connect_gmail_btn.setObjectName("SecondaryButton")
        self.privacy_connect_gmail_btn.clicked.connect(self._privacy_connect_gmail)
        self.privacy_connect_cal_btn = QPushButton()
        self.privacy_connect_cal_btn.setObjectName("SecondaryButton")
        self.privacy_connect_cal_btn.clicked.connect(self._privacy_connect_calendar)
        self.privacy_connect_ms_mail_btn = QPushButton()
        self.privacy_connect_ms_mail_btn.setObjectName("SecondaryButton")
        self.privacy_connect_ms_mail_btn.clicked.connect(self._connect_microsoft_mail)
        self.privacy_connect_ms_cal_btn = QPushButton()
        self.privacy_connect_ms_cal_btn.setObjectName("SecondaryButton")
        self.privacy_connect_ms_cal_btn.clicked.connect(self._connect_microsoft_calendar)
        self.privacy_disconnect_btn = QPushButton()
        self.privacy_disconnect_btn.setObjectName("SecondaryButton")
        self.privacy_disconnect_btn.clicked.connect(self._privacy_disconnect_selected)
        for btn in (
            self.privacy_connect_gmail_btn,
            self.privacy_connect_cal_btn,
            self.privacy_connect_ms_mail_btn,
            self.privacy_connect_ms_cal_btn,
            self.privacy_disconnect_btn,
        ):
            oform.addWidget(btn)
        integ_layout.addWidget(oauth_box)

        guenther_box = QGroupBox()
        self.guenther_box = guenther_box
        gform = QFormLayout(guenther_box)
        self.guenther_enabled = QCheckBox()
        self.guenther_model_fixed = QLabel("Phi-4-mini (einziges Produktionsmodell)")
        self.guenther_hint = QLabel()
        self.guenther_hint.setWordWrap(True)
        self.lbl_guenther_model = QLabel()
        gform.addRow(self.guenther_enabled)
        gform.addRow(self.lbl_guenther_model, self.guenther_model_fixed)
        gform.addRow(self.guenther_hint)
        integ_layout.addWidget(guenther_box)
        integ_layout.addStretch(1)
        self.stack.addWidget(integ_page)

        # --- 4 Daten & Datenschutz ---
        privacy_page, privacy_layout = _scroll_form()
        self.section_privacy = QLabel()
        self.section_privacy.setObjectName("PageTitle")
        privacy_layout.addWidget(self.section_privacy)
        privacy_box = QGroupBox()
        self.privacy_box = privacy_box
        pform = QVBoxLayout(privacy_box)
        self.privacy_intro = QLabel()
        self.privacy_intro.setWordWrap(True)
        self.privacy_intro.setObjectName("PageSubtitle")
        pform.addWidget(self.privacy_intro)
        self.privacy_export_btn = QPushButton()
        self.privacy_export_btn.setObjectName("SecondaryButton")
        self.privacy_export_btn.clicked.connect(self._privacy_export)
        pform.addWidget(self.privacy_export_btn)
        privacy_layout.addWidget(privacy_box)

        danger_box = QGroupBox()
        self.danger_box = danger_box
        dform = QVBoxLayout(danger_box)
        self.privacy_mail_btn = QPushButton()
        self.privacy_mail_btn.setObjectName("SecondaryButton")
        self.privacy_mail_btn.clicked.connect(self._privacy_delete_mail)
        self.privacy_cal_btn = QPushButton()
        self.privacy_cal_btn.setObjectName("SecondaryButton")
        self.privacy_cal_btn.clicked.connect(self._privacy_delete_calendar)
        self.privacy_logs_btn = QPushButton()
        self.privacy_logs_btn.setObjectName("SecondaryButton")
        self.privacy_logs_btn.clicked.connect(self._privacy_delete_logs)
        self.privacy_all_btn = QPushButton()
        self.privacy_all_btn.setObjectName("PrimaryButton")
        self.privacy_all_btn.clicked.connect(self._privacy_delete_all)
        for btn in (
            self.privacy_mail_btn,
            self.privacy_cal_btn,
            self.privacy_logs_btn,
            self.privacy_all_btn,
        ):
            dform.addWidget(btn)
        self.danger_toggle = QToolButton()
        self.danger_toggle.setCheckable(True)
        privacy_layout.addWidget(_collapsible_host(self.danger_toggle, danger_box))
        privacy_layout.addStretch(1)
        self.stack.addWidget(privacy_page)

        # --- 5 Erweitert (sources, search knobs, browser, diagnose) ---
        adv_page, adv_layout = _scroll_form()
        self.section_advanced = QLabel()
        self.section_advanced.setObjectName("PageTitle")
        adv_layout.addWidget(self.section_advanced)

        self.source_checks: dict[str, QCheckBox] = {}
        self.source_status = QLabel()
        self.source_status.setWordWrap(True)
        src_box = QGroupBox()
        self.src_box = src_box
        src_layout = QVBoxLayout(src_box)
        for key, _label in SOURCES:
            cb = QCheckBox()
            self.source_checks[key] = cb
            src_layout.addWidget(cb)
        src_layout.addWidget(self.source_status)
        adv_layout.addWidget(src_box)

        search_box = QGroupBox()
        self.search_box = search_box
        sform = QFormLayout(search_box)
        self.published_days = IntentionalWheelSpinBox()
        self.published_days.setRange(1, 90)
        self.min_match_dash = IntentionalWheelSpinBox()
        self.min_match_dash.setRange(0, 100)
        self.max_distance = IntentionalWheelSpinBox()
        self.max_distance.setRange(1, 300)
        self.search_mode = QComboBox()
        self.search_mode.addItem("", "profile_discovery")
        self.search_mode.addItem("", "explicit_titles")
        self.jobs_per_search = QComboBox()
        from core.config import JOBS_PER_SEARCH_CHOICES

        for n in JOBS_PER_SEARCH_CHOICES:
            label = "Max" if n == 0 else str(n)
            self.jobs_per_search.addItem(label, n)
        self.lbl_published = QLabel()
        self.lbl_min_match_dash = QLabel()
        self.lbl_max_distance = QLabel()
        self.lbl_search_mode = QLabel()
        self.lbl_jobs_per_search = QLabel()
        sform.addRow(self.lbl_search_mode, self.search_mode)
        sform.addRow(self.lbl_jobs_per_search, self.jobs_per_search)
        sform.addRow(self.lbl_published, self.published_days)
        sform.addRow(self.lbl_min_match_dash, self.min_match_dash)
        sform.addRow(self.lbl_max_distance, self.max_distance)
        adv_layout.addWidget(search_box)

        br_box = QGroupBox()
        self.br_box = br_box
        br_layout = QVBoxLayout(br_box)
        self.browser_status = QLabel()
        self.browser_status.setWordWrap(True)
        btn_row = QHBoxLayout()
        self.check_browser_btn = QPushButton()
        self.check_browser_btn.setObjectName("SecondaryButton")
        self.check_browser_btn.clicked.connect(self.check_browser_component)
        self.repair_browser_btn = QPushButton()
        self.repair_browser_btn.setObjectName("SecondaryButton")
        self.repair_browser_btn.clicked.connect(self.repair_browser_component)
        btn_row.addWidget(self.check_browser_btn)
        btn_row.addWidget(self.repair_browser_btn)
        btn_row.addStretch(1)
        br_layout.addWidget(self.browser_status)
        br_layout.addLayout(btn_row)
        adv_layout.addWidget(br_box)

        diag_box = QGroupBox()
        self.diag_box = diag_box
        dform = QVBoxLayout(diag_box)
        self.diag_intro = QLabel()
        self.diag_intro.setWordWrap(True)
        self.diag_intro.setObjectName("PageSubtitle")
        self.open_logs_btn = QPushButton()
        self.open_logs_btn.setObjectName("SecondaryButton")
        self.open_logs_btn.clicked.connect(self._open_diagnose_logs)
        dform.addWidget(self.diag_intro)
        dform.addWidget(self.open_logs_btn)
        self.apply_test_btn = QPushButton()
        self.apply_test_btn.setObjectName("SecondaryButton")
        self.apply_test_btn.clicked.connect(self._request_apply_test)
        self.clear_jobs_btn = QPushButton()
        self.clear_jobs_btn.setObjectName("SecondaryButton")
        self.clear_jobs_btn.clicked.connect(self._request_clear_jobs)
        dform.addWidget(self.apply_test_btn)
        dform.addWidget(self.clear_jobs_btn)
        adv_layout.addWidget(diag_box)
        adv_layout.addStretch(1)
        self.stack.addWidget(adv_page)
        self._browser_busy = False

        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(1)  # Automation as in demo default

        self.save_btn = QPushButton()
        self.save_btn.setObjectName("PrimaryButton")
        self.save_btn.clicked.connect(self.save)
        root.addWidget(self.save_btn)

        apply_wheel_guard_to_spinboxes(self)
        self._annotate_a11y_controls()
        self.retranslate_ui()

    def _annotate_a11y_controls(self) -> None:
        from desktop.design_system.a11y import annotate_button, wire_form_row

        wire_form_row(self.lang_label, self.lang_combo)
        wire_form_row(self.theme_label, self.theme_combo)
        annotate_button(self.high_contrast)
        annotate_button(self.save_btn)
        for btn in (
            self.privacy_connect_gmail_btn,
            self.privacy_connect_cal_btn,
            self.privacy_export_btn,
            self.privacy_disconnect_btn,
            self.privacy_mail_btn,
            self.privacy_cal_btn,
            self.privacy_logs_btn,
            self.privacy_all_btn,
            self.check_browser_btn,
            self.repair_browser_btn,
            self.about_btn,
            self.open_logs_btn,
        ):
            annotate_button(btn)

    def retranslate_ui(self) -> None:
        self.header.set_texts(tr("nav.settings"))
        for i, key in enumerate(_SETTINGS_NAV_KEYS):
            item = self.nav.item(i)
            if item is not None:
                item.setText(tr(key))
        self.section_general.setText(tr("settings.nav.general"))
        self.section_automation.setText(tr("settings.nav.automation"))
        self.section_communication.setText(tr("settings.nav.communication"))
        self.section_integrations.setText(tr("settings.nav.integrations"))
        self.section_privacy.setText(tr("settings.nav.privacy"))
        self.section_advanced.setText(tr("settings.nav.advanced"))
        self.safety_toggle.setText(tr("settings.safety_limits"))
        self.danger_toggle.setText(tr("settings.danger_zone"))
        self.oauth_box.setTitle(tr("settings.nav.integrations"))
        self.danger_box.setTitle(tr("settings.danger_zone"))
        self.privacy_box.setTitle(tr("privacy.title"))
        self.privacy_intro.setText(tr("privacy.intro"))
        if hasattr(self, "lbl_mail_provider"):
            self.lbl_mail_provider.setText(tr("integrations.mail.label"))
            self.lbl_calendar_provider.setText(tr("integrations.calendar.label"))
            self.provider_hint.setText(tr("integrations.no_fallback_hint"))
            # refresh combo labels
            for combo, keys in (
                (
                    self.mail_provider,
                    [
                        ("integrations.mail.none", "none"),
                        ("integrations.mail.google", "google_gmail"),
                        ("integrations.mail.microsoft", "microsoft_graph"),
                        ("integrations.mail.other", "generic_imap"),
                    ],
                ),
                (
                    self.calendar_provider,
                    [
                        ("integrations.calendar.google", "google_calendar"),
                        ("integrations.calendar.microsoft", "microsoft_graph"),
                        ("integrations.calendar.other", "generic_caldav"),
                        ("integrations.calendar.none_explicit", "none"),
                    ],
                ),
            ):
                cur = combo.currentData()
                combo.clear()
                for key, data in keys:
                    combo.addItem(tr(key), data)
                idx = combo.findData(cur)
                combo.setCurrentIndex(idx if idx >= 0 else 0)
            self.mail_status.setText(tr("integrations.status.unknown"))
            self.calendar_status.setText(tr("integrations.status.unknown"))
        self.privacy_connect_gmail_btn.setText(tr("privacy.connect_gmail"))
        self.privacy_connect_cal_btn.setText(tr("privacy.connect_calendar"))
        if hasattr(self, "privacy_connect_ms_mail_btn"):
            self.privacy_connect_ms_mail_btn.setText(tr("integrations.connect_microsoft_mail"))
            self.privacy_connect_ms_cal_btn.setText(tr("integrations.connect_microsoft_calendar"))
        self.privacy_export_btn.setText(tr("privacy.export"))
        self.privacy_disconnect_btn.setText(tr("integrations.disconnect_selected"))
        self.privacy_mail_btn.setText(tr("privacy.delete_mail"))
        self.privacy_cal_btn.setText(tr("privacy.delete_calendar"))
        self.privacy_logs_btn.setText(tr("privacy.delete_logs"))
        self.privacy_all_btn.setText(tr("privacy.delete_all"))
        self.general_box.setTitle(tr("settings.general"))
        self.appear_box.setTitle(tr("settings.general"))
        self.src_box.setTitle(tr("settings.sources"))
        self.search_box.setTitle(tr("settings.search"))
        self.mode_box.setTitle(tr("settings.mode"))
        self.apply_box.setTitle(tr("settings.auto_apply"))
        self.bg_box.setTitle(tr("settings.automation"))
        self.br_box.setTitle(tr("settings.browser"))
        self.diag_box.setTitle(tr("settings.advanced"))
        self.diag_intro.setText(tr("settings.open_diagnose_logs"))
        self.open_logs_btn.setText(tr("settings.open_diagnose_logs"))
        self.apply_test_btn.setText(tr("btn.apply_test"))
        self.clear_jobs_btn.setText(tr("btn.clear_jobs"))
        self.lang_label.setText(tr("settings.language"))
        self.theme_label.setText(tr("settings.theme"))
        self.high_contrast.setText(tr("a11y.high_contrast"))
        self.high_contrast.setToolTip(tr("a11y.high_contrast_hint"))
        self.start_windows.setText(tr("settings.start_windows"))
        self.minimize_tray.setText(tr("settings.minimize_tray"))
        self.lang_combo.setItemText(0, tr("lang.de"))
        self.lang_combo.setItemText(1, tr("lang.en"))
        self.theme_combo.setItemText(0, tr("settings.theme.system"))
        self.theme_combo.setItemText(1, tr("settings.theme.light"))
        self.theme_combo.setItemText(2, tr("settings.theme.dark"))
        for key, label in SOURCES:
            text = tr("settings.company_sites") if key == "company_sites" else label
            self.source_checks[key].setText(text)
        self.mode_search.setText(tr("settings.mode.search"))
        self.mode_review.setText(tr("settings.mode.review"))
        self.mode_auto.setText(tr("settings.mode.auto"))
        self.dry_run.setText(tr("settings.dry_run"))
        self.lbl_published.setText(tr("settings.published_days"))
        self.lbl_min_match_dash.setText(tr("settings.min_match_dash"))
        self.lbl_max_distance.setText(tr("settings.max_distance"))
        self.lbl_search_mode.setText(tr("settings.search_mode"))
        self.lbl_jobs_per_search.setText(tr("settings.jobs_per_search"))
        cur_mode = self.search_mode.currentData()
        self.search_mode.setItemText(0, tr("settings.search_mode.discovery"))
        self.search_mode.setItemText(1, tr("settings.search_mode.explicit"))
        idx = self.search_mode.findData(cur_mode)
        if idx >= 0:
            self.search_mode.setCurrentIndex(idx)
        # Refresh Max label translation-agnostic (numeric data preserved)
        for i in range(self.jobs_per_search.count()):
            data = self.jobs_per_search.itemData(i)
            if data == 0:
                self.jobs_per_search.setItemText(i, tr("settings.jobs_per_search.max"))
        self.lbl_min_match_apply.setText(tr("settings.min_match_apply"))
        self.lbl_max_per_run.setText(tr("settings.max_per_run"))
        self.lbl_max_per_day.setText(tr("settings.max_per_day"))
        self.lbl_max_fail.setText(tr("settings.max_fail"))
        self.lbl_delay.setText(tr("settings.delay"))
        self.auto_cover.setText(tr("settings.auto_cover"))
        self.auto_submit.setText(tr("settings.auto_submit"))
        if hasattr(self, "life_box"):
            self.life_box.setTitle(tr("settings.lifecycle"))
            self.lbl_preferred_contact.setText(tr("settings.preferred_contact"))
            self.phone_available.setText(tr("settings.phone_available"))
            self.lbl_tel_avail.setText(tr("settings.telephone_availability"))
            self.lbl_working_hours.setText(tr("settings.working_hours"))
            self.lbl_follow_up_days.setText(tr("settings.follow_up_days"))
            self.lbl_ghosted_days.setText(tr("settings.ghosted_days"))
            self.followup_enabled.setText(tr("settings.followup_enabled"))
            self.followup_reminders_enabled.setText(tr("settings.followup_reminders_enabled"))
            self.email_draft_only.setText(tr("settings.email_draft_only"))
            self.allow_employer_email_send.setText(tr("settings.allow_employer_email_send"))
        if hasattr(self, "guenther_box"):
            self.guenther_box.setTitle(tr("settings.guenther"))
            self.guenther_enabled.setText(tr("settings.guenther_enabled"))
            self.lbl_guenther_model.setText(tr("settings.guenther_model"))
            self.guenther_hint.setText(tr("settings.guenther_hint"))
            if hasattr(self, "guenther_model_fixed"):
                self.guenther_model_fixed.setText(tr("settings.guenther_model.phi_only"))
        self.run_auto.setText(tr("settings.run_auto"))
        self.lbl_schedule.setText(tr("settings.schedule"))
        self.lbl_interval.setText(tr("settings.interval"))
        self.lbl_times.setText(tr("settings.times"))
        self.paused.setText(tr("settings.paused"))
        # rebuild schedule items preserving data
        current = self.schedule_mode.currentData()
        self.schedule_mode.clear()
        for key in (
            "settings.schedule.on_login",
            "settings.schedule.every",
            "settings.schedule.once",
            "settings.schedule.twice",
            "settings.schedule.custom",
        ):
            data = {
                "settings.schedule.on_login": "on_login",
                "settings.schedule.every": "every_x_hours",
                "settings.schedule.once": "once_daily",
                "settings.schedule.twice": "twice_daily",
                "settings.schedule.custom": "custom",
            }[key]
            self.schedule_mode.addItem(tr(key), data)
        idx = self.schedule_mode.findData(current)
        self.schedule_mode.setCurrentIndex(idx if idx >= 0 else 1)
        self.custom_times.setPlaceholderText("08:00, 17:00")
        self.check_browser_btn.setText(tr("btn.check_browser"))
        self.repair_browser_btn.setText(tr("btn.repair_browser"))
        self.open_logs_btn.setText(tr("settings.open_diagnose_logs"))
        self.about_btn.setText(tr("about.open"))
        self.save_btn.setText(tr("btn.save_settings"))
        self._annotate_a11y_controls()

    def _open_diagnose_logs(self) -> None:
        parent = self.window()
        if parent is not None and hasattr(parent, "open_diagnose_logs"):
            parent.open_diagnose_logs()  # type: ignore[attr-defined]

    def _request_apply_test(self) -> None:
        parent = self.window()
        if parent is not None and hasattr(parent, "run_application_test"):
            parent.run_application_test()  # type: ignore[attr-defined]

    def _request_clear_jobs(self) -> None:
        parent = self.window()
        if parent is not None and hasattr(parent, "clear_job_data"):
            parent.clear_job_data()  # type: ignore[attr-defined]

    def open_about(self) -> None:
        AboutDialog(self).exec()

    def load_from_config(self) -> None:
        cfg = self.config_service.load()
        s = cfg.settings
        lang_idx = self.lang_combo.findData((s.language or "de").lower())
        self.lang_combo.setCurrentIndex(lang_idx if lang_idx >= 0 else 0)
        theme_idx = self.theme_combo.findData((s.theme or "system").lower())
        self.theme_combo.setCurrentIndex(theme_idx if theme_idx >= 0 else 0)
        self.high_contrast.setChecked(bool(getattr(s, "high_contrast", False)))
        self.start_windows.setChecked(bool(getattr(s, "start_with_windows", False)))
        self.minimize_tray.setChecked(bool(getattr(s, "minimize_to_tray", False)))
        {
            "search_only": self.mode_search,
            "review_before_submit": self.mode_review,
            "fully_automatic": self.mode_auto,
        }.get(s.mode, self.mode_search).setChecked(True)
        self.dry_run.setChecked(bool(s.dry_run))
        enabled = set(s.enabled_sources or [])
        for key, cb in self.source_checks.items():
            cb.setChecked(key in enabled)
        self.published_days.setValue(int(s.published_within_days))
        self.min_match_dash.setValue(int(s.minimum_match_for_dashboard))
        mode_idx = self.search_mode.findData(
            str(getattr(s, "search_mode", "profile_discovery") or "profile_discovery")
        )
        self.search_mode.setCurrentIndex(mode_idx if mode_idx >= 0 else 0)
        jps = int(getattr(s, "jobs_per_search", 40) or 0)
        jps_idx = self.jobs_per_search.findData(jps)
        if jps_idx < 0:
            from core.config import normalize_jobs_per_search

            jps_idx = self.jobs_per_search.findData(normalize_jobs_per_search(jps))
        self.jobs_per_search.setCurrentIndex(jps_idx if jps_idx >= 0 else 3)
        self.max_distance.setValue(int(cfg.profile.location.max_distance_km))
        self.min_match_apply.setValue(int(s.minimum_match_for_auto_apply))
        self.max_per_run.setValue(int(s.max_applications_per_run))
        self.max_per_day.setValue(int(s.max_applications_per_day))
        self.max_fail.setValue(int(s.max_failed_applications_per_run))
        self.delay.setValue(int(s.delay_between_applications_seconds))
        self.auto_cover.setChecked(bool(getattr(s, "automatic_cover_letters", True)))
        self.auto_submit.setChecked(bool(getattr(s, "automatic_submission", False)))
        if hasattr(self, "preferred_contact"):
            pc = self.preferred_contact.findData(getattr(s, "preferred_contact", "email") or "email")
            self.preferred_contact.setCurrentIndex(pc if pc >= 0 else 0)
            self.phone_available.setChecked(bool(getattr(s, "phone_available", True)))
            self.telephone_availability.setText(str(getattr(s, "telephone_availability", "") or ""))
            self.working_hours.setText(str(getattr(s, "working_hours", "") or "09:00-17:00"))
            self.follow_up_days.setValue(int(getattr(s, "follow_up_days", 14) or 14))
            self.ghosted_days.setValue(int(getattr(s, "ghosted_days", 21) or 21))
            self.followup_enabled.setChecked(bool(getattr(s, "followup_enabled", True)))
            self.followup_reminders_enabled.setChecked(bool(getattr(s, "followup_reminders_enabled", False)))
            self.email_draft_only.setChecked(bool(getattr(s, "email_draft_only", True)))
            self.allow_employer_email_send.setChecked(
                bool(getattr(s, "allow_employer_email_send", False))
            )
        if hasattr(self, "guenther_enabled"):
            self.guenther_enabled.setChecked(bool(getattr(s, "guenther_enabled", False)))
        if hasattr(self, "mail_provider"):
            mp = self.mail_provider.findData(getattr(s, "mail_provider", "none") or "none")
            self.mail_provider.setCurrentIndex(mp if mp >= 0 else 0)
            cp = self.calendar_provider.findData(
                getattr(s, "calendar_provider", "none") or "none"
            )
            self.calendar_provider.setCurrentIndex(cp if cp >= 0 else max(0, self.calendar_provider.count() - 1))
            self._refresh_provider_status(s)
        self.run_auto.setChecked(bool(s.run_automatically))
        idx = self.schedule_mode.findData(s.schedule_mode)
        self.schedule_mode.setCurrentIndex(idx if idx >= 0 else 1)
        self.interval_hours.setValue(int(s.schedule_interval_hours or 6))
        self.custom_times.setText(", ".join(s.schedule_times or []))
        self.paused.setChecked(bool(s.automation_paused))

        db = Database(cfg.db_path)
        lines = []
        for row in db.list_source_status():
            st = row.get("status") or "unknown"
            label = {
                "ok": tr("settings.source_active"),
                "OK_WITH_RESULTS": tr("settings.source_ok_results"),
                "OK_EMPTY": tr("settings.source_ok_empty"),
                "TIMEOUT": tr("settings.source_timeout"),
                "BLOCKED": tr("settings.source_blocked"),
                "PARSER_ERROR": tr("settings.source_parser"),
                "NETWORK_ERROR": tr("settings.source_network"),
                "AUTH_REQUIRED": tr("settings.source_login"),
                "RATE_LIMITED": tr("settings.source_rate"),
                "DISABLED": tr("settings.source_unavailable"),
                "PLACEHOLDER": tr("settings.source_placeholder"),
                "CANCELLED": tr("settings.source_cancelled"),
                "ERROR": tr("settings.source_error"),
                "error": tr("settings.source_error"),
                "login_required": tr("settings.source_login"),
                "unavailable": tr("settings.source_unavailable"),
            }.get(st, st)
            msg = (row.get("message") or "").strip()
            jobs_n = row.get("jobs_found")
            suffix = f" ({jobs_n} Jobs)" if jobs_n is not None else ""
            if st in {"error", "ERROR", "TIMEOUT", "NETWORK_ERROR", "PARSER_ERROR", "BLOCKED"} and msg:
                lines.append(f"{row.get('source')}: {label}{suffix}")
                lines.append(f"  {msg[:240]}")
            else:
                lines.append(
                    f"{row.get('source')}: {label}{suffix}"
                    + (f" – {msg[:80]}" if msg else "")
                )
        self.source_status.setText("\n".join(lines) if lines else tr("settings.no_source_status"))
        self.browser_status.setText(
            tr("settings.browser_ok") if playwright_available() else tr("settings.browser_missing")
        )

    def save(self) -> None:
        cfg = self.config_service.load()
        old_lang = (cfg.settings.language or "de").lower()
        cfg.settings.language = self.lang_combo.currentData() or "de"
        cfg.settings.theme = self.theme_combo.currentData() or "system"
        cfg.settings.high_contrast = self.high_contrast.isChecked()
        cfg.settings.start_with_windows = self.start_windows.isChecked()
        cfg.settings.minimize_to_tray = self.minimize_tray.isChecked()
        if self.mode_search.isChecked():
            cfg.settings.mode = "search_only"
        elif self.mode_review.isChecked():
            cfg.settings.mode = "review_before_submit"
        else:
            cfg.settings.mode = "fully_automatic"
        cfg.settings.dry_run = self.dry_run.isChecked()
        cfg.settings.enabled_sources = [
            key for key, cb in self.source_checks.items() if cb.isChecked()
        ]
        cfg.settings.published_within_days = self.published_days.value()
        cfg.settings.minimum_match_for_dashboard = self.min_match_dash.value()
        cfg.settings.search_mode = str(
            self.search_mode.currentData() or "profile_discovery"
        )
        cfg.settings.jobs_per_search = int(self.jobs_per_search.currentData() or 40)
        cfg.profile.location.max_distance_km = float(self.max_distance.value())
        cfg.settings.minimum_match_for_auto_apply = self.min_match_apply.value()
        cfg.settings.max_applications_per_run = self.max_per_run.value()
        cfg.settings.max_applications_per_day = self.max_per_day.value()
        cfg.settings.max_failed_applications_per_run = self.max_fail.value()
        cfg.settings.delay_between_applications_seconds = self.delay.value()
        cfg.settings.automatic_cover_letters = self.auto_cover.isChecked()
        cfg.settings.automatic_submission = self.auto_submit.isChecked()
        if hasattr(self, "preferred_contact"):
            cfg.settings.preferred_contact = str(
                self.preferred_contact.currentData() or "email"
            )
            cfg.settings.phone_available = self.phone_available.isChecked()
            cfg.settings.telephone_availability = self.telephone_availability.text().strip()
            cfg.settings.working_hours = self.working_hours.text().strip() or "09:00-17:00"
            cfg.settings.follow_up_days = int(self.follow_up_days.value())
            cfg.settings.ghosted_days = int(self.ghosted_days.value())
            cfg.settings.followup_enabled = self.followup_enabled.isChecked()
            cfg.settings.followup_reminders_enabled = self.followup_reminders_enabled.isChecked()
            cfg.settings.email_draft_only = self.email_draft_only.isChecked()
            cfg.settings.allow_employer_email_send = self.allow_employer_email_send.isChecked()
        if hasattr(self, "guenther_enabled"):
            cfg.settings.guenther_enabled = self.guenther_enabled.isChecked()
            cfg.settings.guenther_model = "phi4-mini"
            cfg.settings.guenther_heuristic_fallback = False
        if hasattr(self, "mail_provider"):
            cfg.settings.mail_provider = str(self.mail_provider.currentData() or "none")
            cfg.settings.calendar_provider = str(
                self.calendar_provider.currentData() or "none"
            )
        cfg.settings.run_automatically = self.run_auto.isChecked()
        cfg.settings.schedule_mode = self.schedule_mode.currentData()
        cfg.settings.schedule_interval_hours = self.interval_hours.value()
        times = [t.strip() for t in self.custom_times.text().split(",") if t.strip()]
        cfg.settings.schedule_times = times or ["08:00"]
        cfg.settings.automation_paused = self.paused.isChecked()

        errors = self.config_service.validate(cfg)
        if errors:
            QMessageBox.warning(self, tr("nav.settings"), "\n".join(errors))
            return
        self.config_service.save(cfg)
        ok, msg = ScheduleService(cfg).sync_from_config()
        self.appearance_changed.emit()
        self.settings_saved.emit()
        note = tr("settings.saved")
        if (cfg.settings.language or "de").lower() != old_lang:
            note = f"{note}\n{tr('settings.lang_restart')}"
        QMessageBox.information(
            self,
            tr("nav.settings"),
            f"{note}\n{msg}" if ok else f"{note}\n{msg}",
        )
        self.load_from_config()

    def _set_browser_busy(self, busy: bool) -> None:
        self._browser_busy = busy
        self.check_browser_btn.setEnabled(not busy)
        self.repair_browser_btn.setEnabled(not busy)

    def check_browser_component(self) -> None:
        if self._browser_busy:
            return
        self._set_browser_busy(True)
        self.browser_status.setText(tr("settings.browser_checking"))
        worker = BrowserCheckWorker()
        thread = start_worker(worker)

        def done(ok: bool, msg: str) -> None:
            self._browser_worker = None
            self._browser_thread = None
            self._set_browser_busy(False)
            self.browser_status.setText(
                tr("settings.browser_ok") if ok else tr("settings.browser_missing")
            )
            if ok:
                QMessageBox.information(self, tr("settings.browser"), msg)
            else:
                QMessageBox.warning(self, tr("settings.browser"), msg)

        connect_queued(worker.finished, done)
        self._browser_worker = worker
        self._browser_thread = thread

    def repair_browser_component(self) -> None:
        if self._browser_busy:
            return
        self._set_browser_busy(True)
        self.browser_status.setText(tr("settings.browser_repairing"))
        worker = BrowserRepairWorker()
        thread = start_worker(worker)

        def done(ok: bool, msg: str) -> None:
            self._browser_worker = None
            self._browser_thread = None
            self._set_browser_busy(False)
            self.browser_status.setText(
                tr("settings.browser_ok") if ok else tr("settings.browser_missing")
            )
            if ok:
                QMessageBox.information(self, tr("settings.browser"), msg)
            else:
                QMessageBox.warning(self, tr("settings.browser"), msg)

        connect_queued(worker.finished, done)
        self._browser_worker = worker
        self._browser_thread = thread

    def _privacy_life(self):
        return self.config_service.privacy_lifecycle()

    def _privacy_report(self, result) -> None:
        if getattr(result, "ok", False) and getattr(result, "verified", False):
            QMessageBox.information(self, tr("privacy.tab"), tr("privacy.action_ok"))
        else:
            QMessageBox.warning(self, tr("privacy.tab"), tr("privacy.action_failed"))

    def _privacy_export(self) -> None:
        confirm = QMessageBox.question(self, tr("privacy.tab"), tr("privacy.export_confirm"))
        if confirm != QMessageBox.StandardButton.Yes:
            return
        from PySide6.QtWidgets import QFileDialog

        dest = QFileDialog.getExistingDirectory(self, tr("privacy.export"))
        if not dest:
            return
        result = self._privacy_life().export_my_data(
            Path(dest), user_confirmed_pii=True, include_document_bytes=False
        )
        if result.ok:
            QMessageBox.information(
                self,
                tr("privacy.tab"),
                f"{tr('privacy.export_done')}\n{result.path}",
            )
        else:
            QMessageBox.warning(self, tr("privacy.tab"), tr("privacy.export_failed"))

    def _privacy_connect_gmail(self) -> None:
        if str(self.mail_provider.currentData() or "") != "google_gmail":
            QMessageBox.warning(
                self, tr("privacy.tab"), tr("integrations.wrong_mail_provider")
            )
            return
        confirm = QMessageBox.question(
            self, tr("privacy.tab"), tr("privacy.connect_gmail_confirm")
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        from integrations.gmail_auth import authorize_gmail

        app_cfg = self.config_service.load()
        settings = app_cfg.settings
        creds = Path(settings.gmail_credentials_path)
        if not creds.is_file():
            creds = self.config_service.dirs["root"] / settings.gmail_credentials_path
        outcome = authorize_gmail(
            credentials_path=creds,
            token_dir=self.config_service.dirs["config"],
            interactive=True,
            open_browser=True,
            privacy_policy_url=getattr(settings, "oauth_privacy_policy_url", "") or "",
            homepage_url=getattr(settings, "oauth_homepage_url", "") or "",
            oauth_env=getattr(settings, "oauth_environment", None),
        )
        if outcome.service is not None and not outcome.denied_features:
            app_cfg.settings.mail_provider = "google_gmail"
            self.config_service.save(app_cfg)
            QMessageBox.information(self, tr("privacy.tab"), tr("privacy.connect_ok"))
        elif outcome.credentials is not None and outcome.denied_features:
            QMessageBox.warning(self, tr("privacy.tab"), tr("privacy.connect_partial"))
        else:
            QMessageBox.warning(self, tr("privacy.tab"), tr("privacy.connect_failed"))

    def _privacy_connect_calendar(self) -> None:
        if str(self.calendar_provider.currentData() or "") != "google_calendar":
            QMessageBox.warning(
                self, tr("privacy.tab"), tr("integrations.wrong_calendar_provider")
            )
            return
        confirm = QMessageBox.question(
            self, tr("privacy.tab"), tr("privacy.connect_calendar_confirm")
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        from integrations.gmail_auth import authorize_calendar_freebusy

        app_cfg = self.config_service.load()
        settings = app_cfg.settings
        creds = Path(settings.gmail_credentials_path)
        if not creds.is_file():
            creds = self.config_service.dirs["root"] / settings.gmail_credentials_path
        outcome = authorize_calendar_freebusy(
            credentials_path=creds,
            token_dir=self.config_service.dirs["config"],
            interactive=True,
            open_browser=True,
            privacy_policy_url=getattr(settings, "oauth_privacy_policy_url", "") or "",
            homepage_url=getattr(settings, "oauth_homepage_url", "") or "",
            oauth_env=getattr(settings, "oauth_environment", None),
        )
        if outcome.service is not None and not outcome.denied_features:
            app_cfg.settings.calendar_provider = "google_calendar"
            self.config_service.save(app_cfg)
            QMessageBox.information(self, tr("privacy.tab"), tr("privacy.connect_ok"))
        elif outcome.credentials is not None and outcome.denied_features:
            QMessageBox.warning(self, tr("privacy.tab"), tr("privacy.connect_partial"))
        else:
            QMessageBox.warning(self, tr("privacy.tab"), tr("privacy.connect_failed"))

    def _connect_microsoft_mail(self) -> None:
        if str(self.mail_provider.currentData() or "") != "microsoft_graph":
            QMessageBox.warning(
                self, tr("privacy.tab"), tr("integrations.wrong_mail_provider")
            )
            return
        app_cfg = self.config_service.load()
        client_id = str(getattr(app_cfg.settings, "microsoft_client_id", "") or "")
        if not client_id:
            QMessageBox.warning(
                self, tr("privacy.tab"), tr("integrations.microsoft_client_missing")
            )
            return
        from integrations.mail.microsoft.oauth_pkce import (
            TOKEN_ACCOUNT_MAIL,
            mail_scopes,
            run_local_pkce_login,
            store_ms_token,
        )
        from integrations.providers.connection_probe import clear_probe_cache, probe_microsoft_graph
        from integrations.providers.diagnostics import DiagStage, log_stage
        from urllib.parse import urlparse

        redirect = str(getattr(app_cfg.settings, "microsoft_redirect_uri", "") or "")
        parsed = urlparse(redirect)
        port = parsed.port or 8765
        path = parsed.path or "/oauth/callback"
        log_stage(DiagStage.AUTH_START, provider="microsoft_graph_mail", ok=True)
        try:
            tokens = run_local_pkce_login(
                client_id=client_id,
                scopes=mail_scopes(),
                redirect_port=port,
                redirect_path=path,
                open_browser=True,
            )
            store_ms_token(TOKEN_ACCOUNT_MAIL, tokens, token_dir=self.config_service.dirs["config"])
            clear_probe_cache("microsoft_graph_mail")
            probe = probe_microsoft_graph(
                provider="microsoft_graph_mail",
                token_dir=self.config_service.dirs["config"],
                force=True,
            )
            if not probe.connected:
                QMessageBox.warning(
                    self, tr("privacy.tab"), tr("integrations.probe_failed")
                )
                return
            app_cfg.settings.mail_provider = "microsoft_graph"
            self.config_service.save(app_cfg)
            QMessageBox.information(self, tr("privacy.tab"), tr("privacy.connect_ok"))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(
                self,
                tr("privacy.tab"),
                f"{tr('privacy.connect_failed')}\n{type(exc).__name__}",
            )

    def _connect_microsoft_calendar(self) -> None:
        if str(self.calendar_provider.currentData() or "") != "microsoft_graph":
            QMessageBox.warning(
                self, tr("privacy.tab"), tr("integrations.wrong_calendar_provider")
            )
            return
        app_cfg = self.config_service.load()
        client_id = str(getattr(app_cfg.settings, "microsoft_client_id", "") or "")
        if not client_id:
            QMessageBox.warning(
                self, tr("privacy.tab"), tr("integrations.microsoft_client_missing")
            )
            return
        from integrations.mail.microsoft.oauth_pkce import (
            TOKEN_ACCOUNT_CALENDAR,
            calendar_scopes,
            run_local_pkce_login,
            store_ms_token,
        )
        from integrations.providers.connection_probe import clear_probe_cache, probe_microsoft_graph
        from integrations.providers.diagnostics import DiagStage, log_stage
        from urllib.parse import urlparse

        redirect = str(getattr(app_cfg.settings, "microsoft_redirect_uri", "") or "")
        parsed = urlparse(redirect)
        port = parsed.port or 8765
        path = parsed.path or "/oauth/callback"
        write = bool(getattr(app_cfg.settings, "allow_calendar_write", False))
        log_stage(DiagStage.AUTH_START, provider="microsoft_graph_calendar", ok=True)
        try:
            tokens = run_local_pkce_login(
                client_id=client_id,
                scopes=calendar_scopes(write=write),
                redirect_port=port,
                redirect_path=path,
                open_browser=True,
            )
            store_ms_token(
                TOKEN_ACCOUNT_CALENDAR, tokens, token_dir=self.config_service.dirs["config"]
            )
            clear_probe_cache("microsoft_graph_calendar")
            probe = probe_microsoft_graph(
                provider="microsoft_graph_calendar",
                token_dir=self.config_service.dirs["config"],
                force=True,
            )
            if not probe.connected:
                QMessageBox.warning(
                    self, tr("privacy.tab"), tr("integrations.probe_failed")
                )
                return
            app_cfg.settings.calendar_provider = "microsoft_graph"
            self.config_service.save(app_cfg)
            QMessageBox.information(self, tr("privacy.tab"), tr("privacy.connect_ok"))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(
                self,
                tr("privacy.tab"),
                f"{tr('privacy.connect_failed')}\n{type(exc).__name__}",
            )

    def _privacy_disconnect_selected(self) -> None:
        """Disconnect only the currently selected provider — no cross-provider wipe."""
        mail = str(self.mail_provider.currentData() or "none")
        cal = str(self.calendar_provider.currentData() or "none")
        token_dir = self.config_service.dirs["config"]
        errors: list[str] = []
        try:
            from integrations.mail.registry import resolve_mail_adapter
            from integrations.calendar.registry import resolve_calendar_adapter

            if mail != "none":
                adapter = resolve_mail_adapter(mail, token_dir=token_dir, allow_none=False)
                if adapter is not None:
                    adapter.disconnect(revoke_remote=True)
            if cal != "none":
                cadapter = resolve_calendar_adapter(cal, token_dir=token_dir, allow_none=False)
                if cadapter is not None:
                    cadapter.disconnect(revoke_remote=True)
        except Exception as exc:  # noqa: BLE001
            errors.append(type(exc).__name__)
        if errors:
            QMessageBox.warning(self, tr("privacy.tab"), tr("privacy.action_failed"))
        else:
            QMessageBox.information(self, tr("privacy.tab"), tr("privacy.action_ok"))

    def _privacy_disconnect_google(self) -> None:
        self._privacy_report(self._privacy_life().disconnect_google(revoke_remote=True))

    def _refresh_provider_status(self, settings) -> None:
        from integrations.mail.registry import resolve_mail_adapter
        from integrations.calendar.registry import resolve_calendar_adapter
        from integrations.providers.connection_probe import ConnectionState

        token_dir = self.config_service.dirs["config"]
        try:
            mad = resolve_mail_adapter(
                getattr(settings, "mail_provider", "none"),
                token_dir=token_dir,
                settings=settings,
                allow_none=True,
            )
            if mad is None:
                self.mail_status.setText(tr("integrations.status.none"))
            elif mad.is_connected():
                self.mail_status.setText(tr("integrations.status.connected"))
            else:
                # Token may exist but probe not OK — never show Verbunden.
                self.mail_status.setText(tr("integrations.status.not_connected"))
        except Exception:
            self.mail_status.setText(tr("integrations.status.unknown"))
        try:
            cad = resolve_calendar_adapter(
                getattr(settings, "calendar_provider", "none"),
                token_dir=token_dir,
                settings=settings,
                allow_none=True,
            )
            if cad is None:
                self.calendar_status.setText(tr("integrations.status.none"))
            elif cad.is_connected():
                self.calendar_status.setText(tr("integrations.status.connected"))
            else:
                self.calendar_status.setText(tr("integrations.status.not_connected"))
        except Exception:
            self.calendar_status.setText(tr("integrations.status.unknown"))
        _ = ConnectionState  # reserved for richer status labels

    def _privacy_delete_mail(self) -> None:
        self._privacy_report(self._privacy_life().delete_mail_cache())

    def _privacy_delete_calendar(self) -> None:
        self._privacy_report(self._privacy_life().delete_calendar_cache())

    def _privacy_delete_logs(self) -> None:
        self._privacy_report(self._privacy_life().delete_logs())

    def _privacy_delete_all(self) -> None:
        confirm = QMessageBox.question(
            self, tr("privacy.tab"), tr("profile.reset_confirm_wipe_all")
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        result = self.config_service.delete_all_local_data()
        if result.get("ok") and result.get("verified"):
            QMessageBox.information(self, tr("privacy.tab"), tr("profile.reset_wipe_done"))
        else:
            QMessageBox.warning(self, tr("privacy.tab"), tr("profile.reset_wipe_failed"))
