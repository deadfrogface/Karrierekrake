"""First-run wizard — ~3 steps: CV → search prefs → ready."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
    QWizard,
    QWizardPage,
)

from desktop.branding import logo_path
from desktop.i18n import tr
from desktop.services import ConfigService
from desktop.tray import apply_window_icon
from desktop.widgets import ListEditor
from desktop.widgets.scroll_page import wrap_scrollable


def _brand_banner(max_width: int = 360) -> QLabel:
    """MASTER A artwork for first-run onboarding (large presentation only)."""
    label = QLabel()
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    path = logo_path(master=True) or logo_path()
    if path is not None:
        pix = QPixmap(str(path))
        if not pix.isNull():
            label.setPixmap(
                pix.scaledToWidth(max_width, Qt.TransformationMode.SmoothTransformation)
            )
    return label


def _scroll_page_body(inner: QWidget) -> QScrollArea:
    return wrap_scrollable(inner, min_content_width=480)


class CvStepPage(QWizardPage):
    """Step 1 — optional CV selection / import hint."""

    def __init__(self) -> None:
        super().__init__()
        self.cv_path = ""
        self.banner = _brand_banner(340)
        self.intro = QLabel()
        self.intro.setWordWrap(True)
        self.label = QLabel()
        self.label.setWordWrap(True)
        self.pick = QPushButton()
        self.pick.setObjectName("PrimaryButton")
        self.pick.clicked.connect(self._pick)
        self.skip_hint = QLabel()
        self.skip_hint.setWordWrap(True)
        self.skip_hint.setObjectName("PageSubtitle")
        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setSpacing(12)
        layout.addWidget(self.banner)
        layout.addWidget(self.intro)
        layout.addWidget(self.label)
        layout.addWidget(self.pick)
        layout.addWidget(self.skip_hint)
        layout.addStretch()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(_scroll_page_body(inner))
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        self.setTitle(tr("wizard.step_cv_title"))
        self.intro.setText(tr("wizard.step_cv_body"))
        self.pick.setText(tr("btn.select_cv"))
        self.skip_hint.setText(tr("wizard.step_cv_skip"))
        if not self.cv_path:
            self.label.setText(tr("wizard.cv_none"))

    def _pick(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, tr("wizard.cv"), "", "Dokumente (*.pdf *.docx)"
        )
        if path:
            self.cv_path = path
            self.label.setText(path)


class PrefsStepPage(QWizardPage):
    """Step 2 — search preferences: titles, location, distance, remote."""

    def __init__(self) -> None:
        super().__init__()
        self.hint = QLabel()
        self.hint.setWordWrap(True)
        self.titles = ListEditor("placeholder.job_title", visible_rows=3)
        self.address = QLineEdit()
        self.distance = QDoubleSpinBox()
        self.distance.setRange(1, 200)
        self.distance.setValue(20)
        self.distance.setSuffix(" km")
        self.allow_remote = QCheckBox()
        self.allow_remote.setChecked(True)
        self.lbl_address = QLabel()
        self.lbl_distance = QLabel()
        self.lbl_titles = QLabel()
        form_host = QWidget()
        form = QFormLayout(form_host)
        form.addRow(self.lbl_address, self.address)
        form.addRow(self.lbl_distance, self.distance)
        form.addRow(self.allow_remote)
        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setSpacing(10)
        layout.addWidget(self.hint)
        layout.addWidget(self.lbl_titles)
        layout.addWidget(self.titles)
        layout.addWidget(form_host)
        layout.addStretch()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(_scroll_page_body(inner))
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        self.setTitle(tr("wizard.step_prefs_title"))
        self.hint.setText(tr("wizard.step_prefs_body"))
        self.lbl_titles.setText(tr("wizard.jobs_hint"))
        self.lbl_address.setText(tr("wizard.address"))
        self.lbl_distance.setText(tr("wizard.distance"))
        self.allow_remote.setText(tr("profile.allow_remote"))
        self.titles.retranslate()


class ReadyStepPage(QWizardPage):
    """Step 3 — mode choice with safe defaults (Ersteinrichtung demo)."""

    def __init__(self) -> None:
        super().__init__()
        self.body = QLabel()
        self.body.setWordWrap(True)
        self.body.setObjectName("PageSubtitle")
        self.body.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        self.search_only = QRadioButton()
        self.search_only.setChecked(True)
        self.search_desc = QLabel()
        self.search_desc.setWordWrap(True)
        self.search_desc.setObjectName("KkHint")

        self.review = QRadioButton()
        self.review_desc = QLabel()
        self.review_desc.setWordWrap(True)
        self.review_desc.setObjectName("KkHint")

        self.dry = QCheckBox()
        self.dry.setChecked(True)
        self.dry.setEnabled(False)  # always on for first run safety messaging

        search_card = QWidget()
        search_card.setObjectName("Card")
        sc = QVBoxLayout(search_card)
        sc.setContentsMargins(14, 12, 14, 12)
        sc.addWidget(self.search_only)
        sc.addWidget(self.search_desc)

        review_card = QWidget()
        review_card.setObjectName("Card")
        rc = QVBoxLayout(review_card)
        rc.setContentsMargins(14, 12, 14, 12)
        rc.addWidget(self.review)
        rc.addWidget(self.review_desc)

        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setSpacing(12)
        layout.addWidget(self.body)
        layout.addWidget(search_card)
        layout.addWidget(review_card)
        layout.addWidget(self.dry)
        layout.addStretch()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(_scroll_page_body(inner))
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        self.setTitle(tr("wizard.step_ready_title"))
        self.body.setText(tr("wizard.step_ready_body"))
        self.search_only.setText(tr("wizard.mode_search_title"))
        self.search_desc.setText(tr("wizard.mode_search_body"))
        self.review.setText(tr("wizard.mode_review_title"))
        self.review_desc.setText(tr("wizard.mode_review_body"))
        self.dry.setText(tr("settings.dry_run"))


class IntegrationsStepPage(QWizardPage):
    """Optional mail/calendar connect — skippable; failed login is not saved as success."""

    def __init__(self, config_service: ConfigService) -> None:
        super().__init__()
        self.config_service = config_service
        self._connected_ok = False
        self.body = QLabel()
        self.body.setWordWrap(True)
        self.body.setObjectName("PageSubtitle")
        self.opt_gmail = QRadioButton()
        self.opt_gcal = QRadioButton()
        self.opt_both = QRadioButton()
        self.opt_gmail.setChecked(True)
        self.connect_btn = QPushButton()
        self.connect_btn.setObjectName("PrimaryButton")
        self.connect_btn.clicked.connect(self._connect_selected)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setObjectName("KkHint")
        self.skip_hint = QLabel()
        self.skip_hint.setWordWrap(True)
        self.skip_hint.setObjectName("KkHint")
        card = QWidget()
        card.setObjectName("Card")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(14, 12, 14, 12)
        cl.addWidget(self.opt_gmail)
        cl.addWidget(self.opt_gcal)
        cl.addWidget(self.opt_both)
        cl.addWidget(self.connect_btn)
        cl.addWidget(self.status)
        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setSpacing(12)
        layout.addWidget(self.body)
        layout.addWidget(card)
        layout.addWidget(self.skip_hint)
        layout.addStretch()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(_scroll_page_body(inner))
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        self.setTitle(tr("wizard.step_integrations_title"))
        self.body.setText(tr("wizard.step_integrations_body"))
        self.opt_gmail.setText(tr("wizard.integrations_gmail"))
        self.opt_gcal.setText(tr("wizard.integrations_gcal"))
        self.opt_both.setText(tr("wizard.integrations_both"))
        self.connect_btn.setText(tr("wizard.integrations_connect"))
        self.skip_hint.setText(tr("wizard.integrations_skip"))
        if not self._connected_ok:
            self.status.setText(tr("wizard.integrations_status_idle"))

    def _connect_selected(self) -> None:
        from desktop.oauth_messages import message_for_google_outcome
        from integrations.gmail_auth import authorize_calendar_mode, authorize_gmail
        from PySide6.QtWidgets import QMessageBox

        app_cfg = self.config_service.load()
        settings = app_cfg.settings
        creds = Path(settings.gmail_credentials_path)
        if not creds.is_file():
            creds = self.config_service.dirs["root"] / settings.gmail_credentials_path
        want_mail = self.opt_gmail.isChecked() or self.opt_both.isChecked()
        want_cal = self.opt_gcal.isChecked() or self.opt_both.isChecked()
        ok_any = False
        last_msg = ""
        if want_mail:
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
                ok_any = True
            else:
                last_msg = message_for_google_outcome(outcome)
        if want_cal:
            mode = str(getattr(settings, "calendar_google_mode", "A") or "A").upper()
            if mode not in {"A", "B"}:
                mode = "A"
            outcome = authorize_calendar_mode(
                mode,
                credentials_path=creds,
                token_dir=self.config_service.dirs["config"],
                interactive=True,
                open_browser=True,
                privacy_policy_url=getattr(settings, "oauth_privacy_policy_url", "") or "",
                homepage_url=getattr(settings, "oauth_homepage_url", "") or "",
                oauth_env=getattr(settings, "oauth_environment", None),
            )
            if outcome.service is not None and not outcome.denied_features:
                app_cfg = self.config_service.load()
                app_cfg.settings.calendar_provider = "google_calendar"
                app_cfg.settings.calendar_google_mode = mode
                app_cfg.settings.calendar_freebusy_enabled = True
                self.config_service.save(app_cfg)
                ok_any = True
            else:
                last_msg = message_for_google_outcome(outcome)
        self._connected_ok = ok_any
        if ok_any:
            self.status.setText(tr("wizard.integrations_status_ok"))
            QMessageBox.information(self, tr("wizard.window_title"), tr("privacy.connect_ok"))
        else:
            self.status.setText(tr("wizard.integrations_status_failed"))
            QMessageBox.warning(
                self,
                tr("wizard.window_title"),
                last_msg or tr("wizard.integrations_status_failed"),
            )


class FirstRunWizard(QWizard):
    def __init__(
        self,
        config_service: ConfigService,
        parent=None,
        *,
        force: bool = False,
    ) -> None:
        super().__init__(parent)
        self.config_service = config_service
        self._force = force
        self.setMinimumSize(640, 560)
        self.setSizeGripEnabled(True)
        apply_window_icon(self)
        self.cv = CvStepPage()
        self.prefs = PrefsStepPage()
        self.integrations = IntegrationsStepPage(config_service)
        self.ready = ReadyStepPage()
        self.addPage(self.cv)
        self.addPage(self.prefs)
        self.addPage(self.integrations)
        self.addPage(self.ready)
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        self.setWindowTitle(tr("wizard.window_title"))
        self.setButtonText(QWizard.WizardButton.FinishButton, tr("wizard.cta_find_jobs"))
        for page in (self.cv, self.prefs, self.integrations, self.ready):
            if hasattr(page, "retranslate_ui"):
                page.retranslate_ui()

    def accept(self) -> None:
        cfg = self.config_service.load()
        cfg = self.config_service.apply_safe_defaults(cfg)
        titles = self.prefs.titles.get_items()
        if titles:
            cfg.profile.jobs.desired_titles = titles
        if self.prefs.address.text().strip():
            cfg.profile.location.home_address = self.prefs.address.text().strip()
        cfg.profile.location.max_distance_km = float(self.prefs.distance.value())
        cfg.profile.location.allow_remote = self.prefs.allow_remote.isChecked()
        if self.ready.review.isChecked():
            cfg.settings.mode = "review_before_submit"
        else:
            cfg.settings.mode = "search_only"
        cfg.settings.dry_run = True  # first-run always dry-run
        self.config_service.save(cfg)
        if self.cv.cv_path:
            self.config_service.copy_cv_into_storage(Path(self.cv.cv_path))
        # Only mark first-run done on Finish — cancel leaves the wizard for next launch.
        # OAuth success is saved only inside IntegrationsStepPage on real AuthOutcome.ok.
        self.config_service.mark_first_run_done()
        super().accept()
