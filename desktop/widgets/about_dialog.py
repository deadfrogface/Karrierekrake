"""About dialog — Karrierekrake brand artwork + technical identity note."""

from __future__ import annotations

import platform
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from desktop import __version__
from desktop.branding import (
    DISPLAY_NAME,
    EXE_BASENAME,
    SHORT_DESCRIPTION_DE,
    SHORT_DESCRIPTION_EN,
    TAGLINE_DE,
    TAGLINE_EN,
    logo_path,
)
from desktop.i18n import i18n, tr
from desktop.tray import apply_window_icon
from desktop.widgets.confirm_dialog import label_button_box
from desktop.widgets.dialog_geometry import fit_dialog_to_screen, wrap_dialog_body


def executable_label() -> str:
    if sys.platform == "win32":
        return f"{EXE_BASENAME}.exe"
    return f"{EXE_BASENAME} ({platform.system() or sys.platform})"


def _default_data_dir() -> Path:
    from desktop.paths import app_data_dir

    return app_data_dir()


class AboutDialog(QDialog):
    def __init__(self, parent=None, *, data_dir: Path | str | None = None) -> None:
        super().__init__(parent)
        self.data_dir = Path(data_dir) if data_dir else _default_data_dir()
        self.setWindowTitle(tr("about.title"))
        apply_window_icon(self)
        self.setMinimumWidth(480)
        outer = QVBoxLayout(self)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        self.art = QLabel()
        self.art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        path = logo_path(master=True) or logo_path()
        if path is not None:
            pix = QPixmap(str(path))
            if not pix.isNull():
                self.art.setPixmap(
                    pix.scaledToWidth(
                        self._logo_width(pix), Qt.TransformationMode.SmoothTransformation
                    )
                )
        layout.addWidget(self.art)

        self.title = QLabel()
        self.title.setObjectName("PageTitle")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title)

        self.tagline = QLabel()
        self.tagline.setObjectName("PageSubtitle")
        self.tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tagline.setWordWrap(True)
        layout.addWidget(self.tagline)

        self.body = QLabel()
        self.body.setWordWrap(True)
        self.body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.body)

        self.help_hint = QLabel()
        self.help_hint.setObjectName("KkNotice")
        self.help_hint.setWordWrap(True)
        self.help_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.help_hint)

        self.data_label = QLabel()
        self.data_label.setObjectName("PageSubtitle")
        self.data_label.setWordWrap(True)
        self.data_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.data_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.data_label)

        self.tech = QLabel()
        self.tech.setObjectName("PageSubtitle")
        self.tech.setWordWrap(True)
        self.tech.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.tech)
        outer.addWidget(wrap_dialog_body(body), stretch=1)

        buttons = label_button_box(QDialogButtonBox(QDialogButtonBox.StandardButton.Ok))
        self.open_data_btn = QPushButton()
        self.open_data_btn.clicked.connect(self._open_data_dir)
        buttons.addButton(self.open_data_btn, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.accepted.connect(self.accept)
        outer.addWidget(buttons)
        self.retranslate_ui()
        margins = outer.contentsMargins()
        fit_dialog_to_screen(
            self,
            preferred_width=max(480, body.sizeHint().width() + margins.left() + margins.right() + 24),
            preferred_height=body.sizeHint().height()
            + buttons.sizeHint().height()
            + outer.spacing()
            + margins.top()
            + margins.bottom()
            + 8,
        )

    def _logo_width(self, pix: QPixmap) -> int:
        """Shrink the artwork on short screens so the text and buttons stay visible."""
        screen = self.screen() or QGuiApplication.primaryScreen()
        avail_h = screen.availableGeometry().height() if screen is not None else 900
        ratio = pix.height() / max(1, pix.width())
        max_art_h = max(120, int(avail_h * 0.38))
        return max(160, min(420, int(max_art_h / max(ratio, 0.01))))

    def _open_data_dir(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.data_dir)))

    def retranslate_ui(self) -> None:
        lang = (i18n.language or "de").lower()
        self.setWindowTitle(tr("about.title"))
        self.title.setText(f"{DISPLAY_NAME}  ·  v{__version__}")
        self.tagline.setText(TAGLINE_EN if lang.startswith("en") else TAGLINE_DE)
        self.body.setText(
            SHORT_DESCRIPTION_EN if lang.startswith("en") else SHORT_DESCRIPTION_DE
        )
        self.help_hint.setText(tr("about.help_hint"))
        self.data_label.setText(tr("about.data_dir", path=str(self.data_dir)))
        self.open_data_btn.setText(tr("about.open_data_dir"))
        self.tech.setText(tr("about.tech", display=DISPLAY_NAME, exe=executable_label()))
