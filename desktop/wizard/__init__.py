"""Guided setup: model, profile, search, accounts, browser and review."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QInputDialog,
    QMessageBox,
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
from desktop.account_connections import AccountConnectionsMixin
from desktop.workers import (
    FunctionWorker,
    BrowserCheckWorker,
    BrowserRepairWorker,
    connect_queued,
    start_worker,
)
from desktop.tray import apply_window_icon
from desktop.widgets import ListEditor
from desktop.widgets.scroll_page import wrap_scrollable


def _provider_label(value: str, *, calendar=False) -> str:
    if value == "none":
        return tr("integrations.status.none")
    keys = (
        {
            "generic_caldav": "integrations.calendar.other",
            "local_ics": "free.calendar.ics",
            "google_calendar": "integrations.calendar.google",
        }
        if calendar
        else {
            "generic_imap": "integrations.mail.other",
            "google_gmail": "integrations.mail.google",
        }
    )
    return tr(keys[value]) if value in keys else str(value)


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

    def __init__(self, config_service: ConfigService) -> None:
        super().__init__()
        self.config_service = config_service
        self.cv_path = config_service.load().application.cv_path or ""
        self.banner = _brand_banner(140)
        self.intro = QLabel()
        self.intro.setWordWrap(True)
        self.label = QLabel()
        self.label.setWordWrap(True)
        self.pick = QPushButton()
        self.pick.setObjectName("PrimaryButton")
        self.pick.clicked.connect(self._pick)
        self.import_btn = QPushButton(tr("profile.import_from_cv"))
        self.import_btn.clicked.connect(self._import)
        self.import_btn.setEnabled(bool(self.cv_path))
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
        layout.addWidget(self.import_btn)
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
        self.label.setText(self.cv_path or tr("wizard.cv_none"))

    def _pick(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, tr("wizard.cv"), "", "Dokumente (*.pdf *.docx)"
        )
        if path:
            self.cv_path = path
            self.label.setText(path)
            self.import_btn.setEnabled(True)

    def _import(self) -> None:
        from desktop.widgets.cv_import_dialog import CvImportDialog

        cfg = self.config_service.load()
        dialog = CvImportDialog(
            Path(self.cv_path),
            cfg.profile.qualifications,
            cfg.application,
            self,
            settings=cfg.settings,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.result_quals is None:
            return
        chosen = self.config_service.copy_cv_into_storage(
            Path(dialog.cv_path), role="cv"
        )
        cfg = self.config_service.load()
        cfg.profile.qualifications = dialog.result_quals
        if dialog.result_application is not None:
            cfg.application = dialog.result_application
        cfg.application.cv_path = str(chosen)
        self.config_service.save(cfg)
        self.cv_path = str(chosen)
        self.label.setText(tr("profile.cv_updated"))


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

    def initializePage(self):
        wizard = self.wizard()
        from core.cv_llm_runtime import resolve_cv_model_path

        cfg = wizard.config_service.load()
        self.body.setText(
            tr(
                "setup.summary",
                model=(
                    tr("setup.ready")
                    if resolve_cv_model_path()
                    else tr("setup.pending")
                ),
                cv=(
                    Path(wizard.cv.cv_path).name
                    if wizard.cv.cv_path
                    else tr("setup.pending")
                ),
                location=wizard.prefs.address.text().strip() or tr("setup.pending"),
                mail=_provider_label(cfg.settings.mail_provider),
                calendar=_provider_label(cfg.settings.calendar_provider, calendar=True),
                browser=wizard.browser.status.text(),
            )
        )


class ModelStepPage(QWizardPage):
    def __init__(self):
        super().__init__()
        from desktop.widgets.update_panel import UpdatePanel

        self.setTitle(tr("setup.model.title"))
        layout = QVBoxLayout(self)
        hint = QLabel(tr("setup.model.body"))
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.updates = UpdatePanel(self)
        self.updates.title.setText(tr("setup.model.card"))
        self.updates.check_button.hide()
        self.updates.version.hide()
        layout.addWidget(self.updates)
        layout.addStretch()


class IntegrationsStepPage(AccountConnectionsMixin, QWizardPage):
    """Use free provider connections; all network operations run off the UI thread."""

    def __init__(self, config_service: ConfigService):
        super().__init__()
        self.config_service = config_service
        self._account_task_active = False
        self._closed = False
        self.mail_provider = QComboBox(self)
        self.calendar_provider = QComboBox(self)
        for combo, values in (
            (self.mail_provider, ("none", "generic_imap")),
            (self.calendar_provider, ("none", "generic_caldav", "local_ics")),
        ):
            for value in values:
                combo.addItem(value, value)
            combo.hide()
        layout = QVBoxLayout(self)
        self.body = QLabel(tr("setup.accounts.body"))
        self.body.setWordWrap(True)
        layout.addWidget(self.body)
        self.mail_btn = QPushButton(tr("setup.accounts.mail"))
        self.mail_btn.clicked.connect(self._connect_free_mail)
        self.calendar_btn = QPushButton(tr("setup.accounts.calendar"))
        self.calendar_btn.clicked.connect(self._choose_calendar)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.mail_btn)
        layout.addWidget(self.calendar_btn)
        layout.addWidget(self.status)
        layout.addStretch()
        self.retranslate_ui()

    def retranslate_ui(self):
        self.setTitle(tr("setup.accounts.title"))
        self._refresh_status()

    def initializePage(self):
        self._refresh_status()

    def _refresh_status(self):
        settings = self.config_service.load().settings
        self.status.setText(
            tr(
                "setup.accounts.status",
                mail=_provider_label(settings.mail_provider),
                calendar=_provider_label(settings.calendar_provider, calendar=True),
            )
        )

    def _choose_calendar(self):
        choice, ok = QInputDialog.getItem(
            self,
            "Kalender",
            "Verbindung auswählen",
            [
                "Apple / iCloud",
                "Privater ICS-Link (nur Lesen)",
                "ICS-Datei importieren",
            ],
            0,
            False,
        )
        if ok:
            {
                "Apple / iCloud": self._connect_icloud,
                "Privater ICS-Link (nur Lesen)": self._connect_private_ics_feed,
                "ICS-Datei importieren": self._import_calendar_snapshot,
            }[choice]()

    def isComplete(self):
        return not self._account_task_active

    def _run_account_task(self, operation, success, cleanup=None):
        if self._account_task_active:
            return
        self._account_task_active = True
        self.completeChanged.emit()
        self.mail_btn.setEnabled(False)
        self.calendar_btn.setEnabled(False)
        self.status.setText(tr("setup.accounts.checking"))

        def done(value, failed=False):
            try:
                if self._closed:
                    return
                if failed:
                    from desktop.oauth_messages import message_for_account_error

                    self.status.setText(message_for_account_error(value))
                else:
                    try:
                        success(value)
                        self._refresh_status()
                    except Exception as exc:
                        from desktop.oauth_messages import message_for_account_error

                        self.status.setText(message_for_account_error(exc))
            finally:
                if cleanup is not None:
                    cleanup()
                self._account_task_active = False
                if not self._closed:
                    self.mail_btn.setEnabled(True)
                    self.calendar_btn.setEnabled(True)
                    self.completeChanged.emit()

        self._account_worker = FunctionWorker(operation)
        connect_queued(self._account_worker.finished, lambda value: done(value))
        connect_queued(self._account_worker.failed, lambda error: done(error, True))
        self._account_thread = start_worker(self._account_worker)


class BrowserStepPage(QWizardPage):
    def __init__(self):
        super().__init__()
        self._closed = False
        self._busy = False
        self.setTitle(tr("setup.browser.title"))
        layout = QVBoxLayout(self)
        hint = QLabel(tr("setup.browser.body"))
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.status = QLabel(tr("setup.browser.unchecked"))
        self.status.setWordWrap(True)
        self.check_btn = QPushButton(tr("setup.browser.check"))
        self.install_btn = QPushButton(tr("setup.browser.install"))
        self.check_btn.clicked.connect(lambda: self._run(BrowserCheckWorker()))
        self.install_btn.clicked.connect(lambda: self._run(BrowserRepairWorker()))
        layout.addWidget(self.status)
        layout.addWidget(self.check_btn)
        layout.addWidget(self.install_btn)
        layout.addStretch()

    def _run(self, worker):
        if self._busy:
            return
        self._busy = True
        self.status.setText(tr("setup.browser.busy"))
        self.check_btn.setEnabled(False)
        self.install_btn.setEnabled(False)

        def done(ok, message):
            self._busy = False
            if self._closed:
                return
            self.status.setText(message)
            self.check_btn.setEnabled(True)
            self.install_btn.setEnabled(True)

        self._worker = worker
        connect_queued(worker.finished, done)
        self._thread = start_worker(worker)


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
        self.model = ModelStepPage()
        self.cv = CvStepPage(config_service)
        self.prefs = PrefsStepPage()
        self.integrations = IntegrationsStepPage(config_service)
        self.browser = BrowserStepPage()
        self.ready = ReadyStepPage()
        cfg = config_service.load()
        self.prefs.titles.set_items(cfg.profile.jobs.desired_titles)
        self.prefs.address.setText(cfg.profile.location.home_address or "")
        self.prefs.distance.setValue(cfg.profile.location.max_distance_km)
        self.prefs.allow_remote.setChecked(cfg.profile.location.allow_remote_germany)
        self.ready.review.setChecked(cfg.settings.mode == "review_before_submit")
        self.addPage(self.model)
        self.addPage(self.cv)
        self.addPage(self.prefs)
        self.addPage(self.integrations)
        self.addPage(self.browser)
        self.addPage(self.ready)
        self.model.updates.restart_requested.connect(self._restart)
        self.retranslate_ui()
        meta = config_service.load_meta()
        draft = meta.get("setup_draft", {})
        if isinstance(draft, dict):
            self.prefs.titles.set_items(
                draft.get("titles", cfg.profile.jobs.desired_titles)
            )
            self.prefs.address.setText(
                draft.get("address", cfg.profile.location.home_address or "")
            )
            self.prefs.distance.setValue(
                draft.get("distance", cfg.profile.location.max_distance_km)
            )
            self.prefs.allow_remote.setChecked(
                draft.get("remote", cfg.profile.location.allow_remote_germany)
            )
            self.ready.review.setChecked(
                draft.get("review", cfg.settings.mode == "review_before_submit")
            )
            if draft.get("cv"):
                self.cv.cv_path = draft["cv"]
                self.cv.label.setText(draft["cv"])
                self.cv.import_btn.setEnabled(True)
        start = meta.get("setup_page", 0) if not force else 0
        self._resume_page = start if start in self.pageIds() else 0
        self._resume_applied = False

    def showEvent(self, event):
        super().showEvent(event)
        if not self._resume_applied:
            self._resume_applied = True
            # Replay page transitions so Back can still reach earlier setup steps.
            for _ in range(self._resume_page):
                if not self.currentPage().isComplete():
                    break
                self.next()

    def retranslate_ui(self) -> None:
        self.setWindowTitle(tr("wizard.window_title"))
        self.setButtonText(QWizard.WizardButton.FinishButton, tr("setup.finish"))
        self.setButtonText(QWizard.WizardButton.BackButton, tr("setup.back"))
        self.setButtonText(QWizard.WizardButton.NextButton, tr("setup.next"))
        self.setButtonText(QWizard.WizardButton.CancelButton, tr("btn.cancel"))
        for page in (self.cv, self.prefs, self.integrations, self.ready):
            if hasattr(page, "retranslate_ui"):
                page.retranslate_ui()

    def accept(self) -> None:
        self.integrations._closed = True
        self.browser._closed = True
        cfg = self.config_service.load()
        cfg = self.config_service.apply_safe_defaults(cfg)
        titles = self.prefs.titles.get_items()
        cfg.profile.jobs.desired_titles = titles
        cfg.profile.location.home_address = self.prefs.address.text().strip()
        cfg.profile.location.max_distance_km = float(self.prefs.distance.value())
        cfg.profile.location.allow_remote_germany = self.prefs.allow_remote.isChecked()
        if self.ready.review.isChecked():
            cfg.settings.mode = "review_before_submit"
        else:
            cfg.settings.mode = "search_only"
        cfg.settings.dry_run = True  # first-run always dry-run
        self.config_service.save(cfg)
        if self.cv.cv_path and Path(self.cv.cv_path).is_file():
            stored = self.config_service.copy_cv_into_storage(
                Path(self.cv.cv_path), role="cv"
            )
            cfg = self.config_service.load()
            cfg.application.cv_path = str(stored)
            self.config_service.save(cfg)
        # Account connections save their configuration only after successful verification.
        self.config_service.mark_first_run_done()
        super().accept()

    def _restart(self):
        # Windows model installation needs an application restart. Do not mark setup complete.
        self.reject()
        parent = self.parent()
        while parent is not None and not hasattr(parent, "force_quit"):
            parent = parent.parent()
        if parent is not None:
            parent.force_quit()

    def reject(self) -> None:
        self.integrations._closed = True
        self.browser._closed = True
        meta = self.config_service.load_meta()
        meta["setup_page"] = max(0, self.currentId())
        meta["setup_draft"] = {
            "titles": self.prefs.titles.get_items(),
            "address": self.prefs.address.text(),
            "distance": self.prefs.distance.value(),
            "remote": self.prefs.allow_remote.isChecked(),
            "review": self.ready.review.isChecked(),
            "cv": self.cv.cv_path,
        }
        self.config_service.save_meta(meta)
        # Completion is only recorded by Finish, never by Cancel or closing the window.
        super().reject()
