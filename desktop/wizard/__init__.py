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
from desktop.tray import app_icon
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


class FirstRunWizard(QWizard):
    def __init__(self, config_service: ConfigService, parent=None) -> None:
        super().__init__(parent)
        self.config_service = config_service
        self.setMinimumSize(640, 520)
        self.setSizeGripEnabled(True)
        self.setWindowIcon(app_icon())
        self.cv = CvStepPage()
        self.prefs = PrefsStepPage()
        self.ready = ReadyStepPage()
        self.addPage(self.cv)
        self.addPage(self.prefs)
        self.addPage(self.ready)
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        self.setWindowTitle(tr("wizard.window_title"))
        self.setButtonText(QWizard.WizardButton.FinishButton, tr("wizard.cta_find_jobs"))
        for page in (self.cv, self.prefs, self.ready):
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
        self.config_service.mark_first_run_done()
        super().accept()
