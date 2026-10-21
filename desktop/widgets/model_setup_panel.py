"""One-click setup download with an offline recommendation and isolated probe."""
from __future__ import annotations

import re
import logging

from PySide6.QtCore import QEvent, QRect, QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetrics, QPalette
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFrame, QLabel, QListView, QPushButton, QProgressBar, QSizePolicy, QStyle,
    QStyledItemDelegate, QStyleOptionButton, QStyleOptionComboBox, QStyleOptionViewItem, QStylePainter,
    QVBoxLayout,
    QWidget,
)

from desktop.design_system.flow_layout import FlowLayout
from desktop.i18n import i18n, tr
from desktop.widgets.confirm_dialog import confirm_action
from desktop.widgets.model_fit import adapt_setup_recommendation, free_ram_only_lock
from desktop.workers import FunctionWorker, connect_queued, start_worker
from guenther.setup_models import (
    SETUP_MODEL_CATALOG, inspect_setup_device, install_recommended_model,
    selected_model_id, selected_model_path,
)

LOG = logging.getLogger("karrierekrake")

# Product decision pending (Damiano): a model that the device check says does
# not fit stays locked. Setting this to True enables the second variant: the
# main button becomes "Trotzdem installieren …", an explicit confirmation
# dialog is required and the override is logged. Keep False until decided.
ALLOW_UNFIT_OVERRIDE = False

_FAILURE_KEYS = {
    "connection_timeout": "timeout", "connection_interrupted": "interrupted",
    "dns_failed": "dns", "tls_failed": "tls",
    "insufficient_disk": "disk", "write_permission_denied": "permission",
    "checksum_mismatch": "checksum", "invalid_download_response": "response",
    "invalid_download_range": "response",
    "download_size_mismatch": "size",
}


def model_failure_code(error) -> str:
    """Fixed, non-private diagnostic code for logs and the secondary code line.

    The text is chosen by the downloader's error code only, never by the
    exception type or its diagnostic: guenther.model_manager reports
    ``tls_failed`` for an SSL EOF with an empty .part file and
    ``connection_interrupted`` once bytes are saved (resume case).
    """
    from guenther.model_manager import download_failure_code

    code = download_failure_code(error) if isinstance(error, OSError) else str(error)
    if code in _FAILURE_KEYS or re.fullmatch(r"http_[1-5][0-9]{2}", code) or code in {
            "activation_failed", "cancelled"}:
        return code
    if re.fullmatch(r"model_probe_[a-z_]{1,40}", code):
        return code
    # Never display or log arbitrary exception strings, URLs or filesystem paths.
    return "download_failed"


def failure_diagnostic(code: str, diagnostic, error=None) -> str:
    """Never-empty diagnostic for the failure log line.

    The downloader/probe diagnostic is used when present (already bounded and
    path-free). Otherwise only the fixed code and the exception class name are
    logged, never the exception text (it may contain paths or user data).
    """
    if isinstance(diagnostic, str) and diagnostic.strip():
        return diagnostic.strip()[:400]
    text = f"category={code}"
    if error is not None:
        name = re.sub(r"[^A-Za-z0-9_]", "", type(error).__name__)[:64]
        text += f" exception={name or 'unknown'}"
    return text


def model_failure_message(code: str) -> str:
    """Plain-language explanation without technical codes."""
    if code.startswith("model_probe"):
        return tr("setup.model.probe_failed")
    if code == "http_416":
        # Only when no partial download exists or no restart is left
        # (guenther.model_manager); a new attempt restarts from byte zero once.
        return tr("setup.model.error.http_416")
    if code.startswith("http_"):
        return tr("setup.model.error.http")
    if code in _FAILURE_KEYS:
        return tr("setup.model.error." + _FAILURE_KEYS[code])
    if code == "activation_failed":
        return tr("setup.model.error.activation")
    return tr("setup.model.failed")


def model_failure_text(error):
    """Plain message plus the secondary code line (used where only one string fits)."""
    code = model_failure_code(error)
    return model_failure_message(code) + "\n" + tr("setup.model.error_code", code=code)


def format_gb(num_bytes: float) -> str:
    # Binary units, labelled "GB" like Windows Explorer shows drives and RAM.
    text = f"{num_bytes / 1024 ** 3:.1f}"
    return text.replace(".", ",") if i18n.language == "de" else text


def format_total_gb(gib: float) -> str:
    # 16 GiB -> "16", 7.7 GiB -> "7,7": never round a 7.7 GiB device up to "8".
    return f"{gib:.0f}" if abs(gib - round(gib)) < 0.05 else format_gb(gib * 1024 ** 3)


def _hint(label: QLabel) -> QLabel:
    label.setObjectName("ModelSetupHint")
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label


def reserve_bold_width(button: QPushButton) -> None:
    """Keep room for the semibold text the stylesheet uses for default/focused buttons.

    The size hint is computed at regular weight; once the button becomes the
    focused default (e.g. "Erneut versuchen" after an error) the semibold text
    would otherwise be clipped at 100 % and 200 % scaling.
    """
    if isinstance(button, WrappingPushButton):
        # Wrapping buttons measure with semibold metrics themselves; a fixed
        # minimum of the full one-line text would widen the 640 px window.
        button.setMinimumWidth(0)
        button.updateGeometry()
        return
    regular = QFontMetrics(button.font()).horizontalAdvance(button.text())
    bold_font = QFont(button.font())
    bold_font.setWeight(QFont.Weight.Bold)
    bold = QFontMetrics(bold_font).horizontalAdvance(button.text())
    button.setMinimumWidth(0)
    button.setMinimumWidth(button.sizeHint().width() + max(0, bold - regular) + 4)



# Width (in characters) the closed combo asks for, small on purpose: longer
# entries wrap onto more lines instead of widening the card (wider Windows
# fonts included). Nothing is elided: the lock reason (" · gesperrt: …")
# always stays fully visible.
MODEL_CHOICE_MIN_CHARS = 20
_UNBOUNDED = 1 << 20


def wrapped_text_height(metrics: QFontMetrics, width: int, text: str) -> int:
    """Height of ``text`` word-wrapped into ``width`` px (what drawText paints)."""
    return metrics.boundingRect(QRect(0, 0, max(1, width), _UNBOUNDED),
                                int(Qt.TextFlag.TextWordWrap), text).height()


class WrappingItemDelegate(QStyledItemDelegate):
    """Popup rows wrap long entries onto more lines; never elided.

    The row is as wide as the popup and as tall as the wrapped text, so a long
    German entry with its lock reason is shown completely at 640 px and with
    large fonts (200 %).
    """

    def __init__(self, combo: QComboBox):
        super().__init__(combo)
        self._combo = combo

    def available_width(self) -> int:
        view = self._combo.view()
        width = view.viewport().width() if view.isVisible() else 0
        return max(1, width or self._combo.width())

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        option.features |= QStyleOptionViewItem.ViewItemFeature.WrapText
        option.textElideMode = Qt.TextElideMode.ElideNone

    def row_option(self, index, width: int | None = None) -> QStyleOptionViewItem:
        """Style option of one row laid out at ``width`` px (as painted)."""
        view = self._combo.view()
        option = QStyleOptionViewItem()
        option.initFrom(view)
        # Same font as the view's own item options (initFrom does not copy it).
        option.font = view.font()
        option.fontMetrics = view.fontMetrics()
        option.rect = QRect(0, 0, width or self.available_width(), _UNBOUNDED)
        self.initStyleOption(option, index)
        return option

    def sizeHint(self, option, index):
        opt = QStyleOptionViewItem(option)
        width = self.available_width()
        opt.rect = QRect(0, 0, width, _UNBOUNDED)
        hint = super().sizeHint(opt, index)
        return QSize(min(hint.width(), width), hint.height())


class WrappingComboBox(QComboBox):
    """Closed combo that wraps the current entry instead of eliding it."""

    def __init__(self, parent=None):
        super().__init__(parent)
        policy = self.sizePolicy()
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)
        self.setItemDelegate(WrappingItemDelegate(self))
        view = self.view()
        view.setWordWrap(True)
        view.setTextElideMode(Qt.TextElideMode.ElideNone)
        if isinstance(view, QListView):
            # Re-layout rows (wrapped heights) whenever the popup width changes.
            view.setResizeMode(QListView.ResizeMode.Adjust)
            view.setUniformItemSizes(False)

    def _style_option(self, width: int | None = None, focused: bool | None = None) -> QStyleOptionComboBox:
        option = QStyleOptionComboBox()
        self.initStyleOption(option)
        if width is not None:
            option.rect = QRect(0, 0, width, super().sizeHint().height())
        if focused is not None:
            focus = QStyle.StateFlag.State_HasFocus
            option.state = (option.state | focus) if focused else (option.state & ~focus)
        return option

    def text_rect(self, width: int | None = None, focused: bool | None = None) -> QRect:
        """Area the current text is painted into (minus the 1 px label inset)."""
        option = self._style_option(width, focused)
        rect = self.style().subControlRect(
            QStyle.ComplexControl.CC_ComboBox, option, QStyle.SubControl.SC_ComboBoxEditField, self)
        return rect.adjusted(1, 0, -1, 0)

    def displayed_text(self) -> str:
        """Exactly the text paintEvent draws (word-wrapped, never elided)."""
        return self.currentText() or self.placeholderText()

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        # One-line combo height plus whatever the wrapped text needs beyond
        # the one-line text area (exact: same rect and flags as paintEvent).
        # Focus may change the frame (app stylesheet: thicker :focus border),
        # so reserve the height the wrapped text needs in either state.
        base = super().sizeHint().height()
        extra = 0
        for focused in (False, True):
            area = self.text_rect(width, focused)
            text_h = wrapped_text_height(self.fontMetrics(), area.width(), self.displayed_text())
            extra = max(extra, text_h - area.height())
        return base + extra

    def sizeHint(self):
        hint = super().sizeHint()
        return QSize(hint.width(), self.heightForWidth(hint.width()))

    def longest_word_width(self) -> int:
        """Widest single word of any entry (or the placeholder) in this font."""
        texts = [self.itemText(i) for i in range(self.count())] + [self.placeholderText()]
        fm = self.fontMetrics()
        return max((fm.horizontalAdvance(word) for text in texts for word in text.split()), default=0)

    def minimumSizeHint(self):
        # Qt's floor is minimumContentsLength x width of "X", which grows with
        # the font (Segoe UI at large sizes: 856 px > the 640 px window). The
        # entry wraps, so only its longest word must fit on one line.
        hint = super().minimumSizeHint()
        option = self._style_option()
        frame = self.style().sizeFromContents(
            QStyle.ContentsType.CT_ComboBox, option, QSize(0, self.fontMetrics().height()), self).width()
        word_floor = max(self.longest_word_width() + 2 + frame, self.minimumWidth())
        width = min(hint.width(), word_floor)
        return QSize(width, self.heightForWidth(width))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if event.oldSize().width() != event.size().width():
            self.updateGeometry()

    def changeEvent(self, event):
        super().changeEvent(event)
        # Stylesheet / font changes alter the wrapped height: drop cached hints.
        if event.type() in {QEvent.Type.FontChange, QEvent.Type.StyleChange}:
            self.updateGeometry()

    def showEvent(self, event):
        super().showEvent(event)
        self.updateGeometry()

    def paintEvent(self, _event):
        painter = QStylePainter(self)
        option = self._style_option()
        text = self.displayed_text()
        option.currentText = ""
        painter.drawComplexControl(QStyle.ComplexControl.CC_ComboBox, option)
        painter.drawControl(QStyle.ControlElement.CE_ComboBoxLabel, option)
        role = QPalette.ColorRole.ButtonText
        if not self.currentText():
            role = QPalette.ColorRole.PlaceholderText
        flags = int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap)
        self.style().drawItemText(painter, self.text_rect(), flags, option.palette,
                                  self.isEnabled(), text, role)


class WrappingPushButton(QPushButton):
    """Push button whose label wraps onto more lines instead of widening the card.

    Minimum width is the longest single word (semibold) plus the style padding,
    so a long German label ("Ausgewähltes Modell herunterladen") at 200 % or
    with a wider system font (Ubuntu, Windows Segoe UI) cannot push a 640 px
    window wider. ``text()`` stays the full label (screen readers, tests);
    only the painting wraps. At 100 % the label stays on one line.
    """

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        policy = self.sizePolicy()
        # QPushButton's default horizontal policy (Minimum) makes layouts use
        # sizeHint (one line) as the floor; Preferred lets them use the
        # longest-word minimumSizeHint below.
        policy.setHorizontalPolicy(QSizePolicy.Policy.Preferred)
        # Fixed (the QPushButton default) caps the height at the one-line
        # sizeHint and would clip a wrapped label; Minimum may grow.
        policy.setVerticalPolicy(QSizePolicy.Policy.Minimum)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)

    def bold_metrics(self) -> QFontMetrics:
        """Metrics of the semibold text the stylesheet uses for default/focused buttons."""
        font = QFont(self.font())
        font.setWeight(QFont.Weight.Bold)
        return QFontMetrics(font)

    def _padding(self) -> QSize:
        option = QStyleOptionButton()
        self.initStyleOption(option)
        option.text = ""
        return self.style().sizeFromContents(QStyle.ContentsType.CT_PushButton, option, QSize(0, 0), self)

    def _text_rect(self, width: int) -> QRect:
        option = QStyleOptionButton()
        self.initStyleOption(option)
        option.rect = QRect(0, 0, width, self.height())
        return self.style().subElementRect(QStyle.SubElement.SE_PushButtonContents, option, self)

    def _bold_reserve(self) -> int:
        regular = self.fontMetrics().horizontalAdvance(self.text())
        return max(0, self.bold_metrics().horizontalAdvance(self.text()) - regular) + 4

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        single = super().sizeHint().height()
        text_w = max(1, width - self._padding().width())
        lines_h = wrapped_text_height(self.bold_metrics(), text_w, self.text())
        return max(single, lines_h + single - self.fontMetrics().height())

    def sizeHint(self) -> QSize:
        # One line with room for the semibold default/focused text (as
        # reserve_bold_width did), so at 100 % the label never wraps.
        hint = super().sizeHint()
        width = hint.width() + self._bold_reserve()
        return QSize(width, self.heightForWidth(width))

    def minimumSizeHint(self) -> QSize:
        metrics = self.bold_metrics()
        words = self.text().split() or [""]
        # Semibold metrics + 4 px hinting reserve: the longest word never clips.
        width = max(metrics.horizontalAdvance(word) for word in words) + 4 + self._padding().width()
        width = max(width, self.minimumWidth())
        # Height of one line: layouts take the real height from heightForWidth;
        # a wrapped minimum height here would make every 100 % button tall.
        return QSize(width, super().sizeHint().height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if event.oldSize().width() != event.size().width():
            self.updateGeometry()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in {QEvent.Type.FontChange, QEvent.Type.StyleChange}:
            self.updateGeometry()

    def wraps(self) -> bool:
        """True when the label does not fit on one line at the current width."""
        area = self._text_rect(self.width())
        return self.bold_metrics().horizontalAdvance(self.text()) + 4 > area.width()

    def paintEvent(self, event):
        if not self.wraps():
            super().paintEvent(event)
            return
        painter = QStylePainter(self)
        option = QStyleOptionButton()
        self.initStyleOption(option)
        text = option.text
        option.text = ""
        painter.drawControl(QStyle.ControlElement.CE_PushButton, option)
        flags = int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap)
        self.style().drawItemText(painter, self._text_rect(self.width()), flags, option.palette,
                                  self.isEnabled(), text, QPalette.ColorRole.ButtonText)


class _ButtonRow(QWidget):
    """Buttons side by side; they move onto a new line when the card is narrow.

    Minimum width is the widest button's longest word (labels wrap, see
    WrappingPushButton), never the sum of all buttons, so large fonts or a
    wider system font cannot widen the 640 px wizard.
    """

    def __init__(self, buttons, parent=None):
        super().__init__(parent)
        layout = FlowLayout(self, h_spacing=8, v_spacing=6)
        for button in buttons:
            layout.addWidget(button)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)


def locked_item_color() -> QColor:
    """Design-system secondary text (muted) for locked list entries.

    Locked entries are disabled items; their text must never fall back to the
    faint disabled palette colour (Fusion light ~#BEBEBE on white, 1.9:1).
    Without the app stylesheet the combo menu draws them in this colour
    (light #5A6B7A on #FFFFFF 5.5:1); with the app stylesheet the list's QSS
    text colour applies (light #1C2430 on #EFEFEF, dark #E8EEF4 on #1A2430).
    Dark muted #9AB5B6 on #1A2430 is 7.2:1. All >= 4.5:1 (WCAG AA).
    """
    from desktop.design_system.tokens import tokens_for_theme

    app = QApplication.instance()
    theme = app.property("kk_palette_theme") if app is not None else None
    return QColor(tokens_for_theme("dark" if theme == "dark" else "light").colors.muted)


def _blocked_note(block_reason: str) -> str:
    """Visible note for a locked model.

    Missing FREE memory is the one block the person can fix right now, so it
    gets its own next step (close other programs, then check again) instead
    of the generic "choose another model" hint.
    """
    if block_reason == "low_free_ram":
        return tr("setup.model.blocked_note_low_free_ram")
    return tr("setup.model.blocked_note", reason=tr("setup.model.block." + block_reason))

class ModelSetupPanel(QFrame):
    state_changed = Signal()
    model_ready = Signal(str)
    download_progress = Signal(object)

    def __init__(self, parent=None, *, context: str = "settings"):
        super().__init__(parent)
        self.busy = False
        self._closed = False
        self.context = context
        self.recommendation = None
        self.fit = None
        self.state = "init"
        self.failed_model_id = None
        self._pending_progress = None
        # True while the status shows the "choose a model first" message.
        self._no_choice_message = False
        self.setObjectName("KkCard")
        layout = QVBoxLayout(self)
        self.title = QLabel(tr("setup.model.card"))
        self.title.setObjectName("CardTitle")
        layout.addWidget(self.title)
        self.specs = QLabel()
        self.specs.setWordWrap(True)
        layout.addWidget(self.specs)
        self.recommended = QLabel()
        self.recommended.setWordWrap(True)
        layout.addWidget(self.recommended)
        self.warnings = _hint(QLabel())
        layout.addWidget(self.warnings)
        self.choice_label = QLabel(tr("setup.model.choice_label"))
        layout.addWidget(self.choice_label)
        self.model_choice = WrappingComboBox()
        self.model_choice.setAccessibleName(tr("setup.model.choice_a11y"))
        self.model_choice.setPlaceholderText(tr("setup.model.choose_placeholder"))
        # Long German entries must not force the card (wizard min. 640 px) wider.
        self.model_choice.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.model_choice.setMinimumContentsLength(MODEL_CHOICE_MIN_CHARS)
        self.choice_label.setBuddy(self.model_choice)
        self.model_choice.currentIndexChanged.connect(self._choice_changed)
        layout.addWidget(self.model_choice)
        self.fit_note = QLabel()
        self.fit_note.setWordWrap(True)
        self.fit_note.setObjectName("WarningLabel")
        layout.addWidget(self.fit_note)
        self.unverified_note = _hint(QLabel())
        layout.addWidget(self.unverified_note)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.error_code = _hint(QLabel())
        layout.addWidget(self.error_code)
        self.busy_hint = _hint(QLabel())
        layout.addWidget(self.busy_hint)
        self.progress_bar = QProgressBar()
        self.progress_bar.setAccessibleName(tr("setup.model.progress_a11y"))
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)
        self.install_button = WrappingPushButton(tr("setup.model.download_selected"))
        self.install_button.setObjectName("KkPrimary")
        self.install_button.clicked.connect(self.install)
        self.recheck_button = WrappingPushButton(tr("setup.model.recheck"))
        self.recheck_button.setObjectName("SecondaryButton")
        self.recheck_button.clicked.connect(self.recheck)
        self.cancel_button = WrappingPushButton(tr("setup.model.cancel_download"))
        self.cancel_button.setAccessibleName(tr("setup.model.cancel_a11y"))
        self.cancel_button.clicked.connect(self.cancel)
        self.cancel_button.hide()
        # Same order as before (tab order follows creation): install, recheck, cancel.
        self.button_row = _ButtonRow((self.install_button, self.recheck_button, self.cancel_button))
        layout.addWidget(self.button_row)
        self.download_progress.connect(self._show_progress)
        # Only a local RAM/CPU/disk snapshot; no model load or network at startup.
        self.refresh_recommendation()

    # ---- device check -------------------------------------------------
    def _installed_model_id(self):
        installed_path = selected_model_path()
        mid = selected_model_id() if installed_path is not None else None
        return mid if mid in SETUP_MODEL_CATALOG else None

    def refresh_recommendation(self):
        if self.busy:
            return
        previous_choice = self.model_choice.currentData()
        try:
            self.recommendation = inspect_setup_device()
            installed_mid = self._installed_model_id()
            self.fit = adapt_setup_recommendation(self.recommendation, installed_model_id=installed_mid)
        except Exception:
            LOG.warning("model_setup_device_check_failed", exc_info=False)
            self.recommendation = None
            self.fit = None
            self._set_state("specs_failed")
            return
        fit = self.fit
        self.specs.setText(tr("setup.model.specs", ram=format_total_gb(fit.total_gib),
                              free=format_gb(fit.available_gib * 1024 ** 3),
                              disk=format_gb(fit.free_disk_bytes), cores=fit.physical_cores))
        self.model_choice.blockSignals(True)
        self.model_choice.clear()
        labelled = fit.labelled_recommended_id
        for model in fit.models:
            size = format_gb(model.approx_bytes)
            if not model.fits:
                text = tr("setup.model.item", name=model.display_name, size=size)
            elif model.model_id == labelled:
                text = tr("setup.model.item_recommended", name=model.display_name, size=size)
            elif model.peak_unverified:
                text = tr("setup.model.item_unverified", name=model.display_name, size=size)
            else:
                text = tr("setup.model.item", name=model.display_name, size=size)
            if model.installed:
                text += tr("setup.model.item_installed_suffix")
            if not model.fits:
                # Visible lock reason in the entry itself, not only after selection.
                text += tr("setup.model.item_locked_suffix",
                           reason=tr("setup.model.block." + model.block_reason))
            self.model_choice.addItem(text, model.model_id)
            index = self.model_choice.count() - 1
            self.model_choice.setItemData(index, text, Qt.ItemDataRole.ToolTipRole)
            if not model.fits:
                # Locked: listed, but neither clickable nor reachable by keyboard.
                item = self.model_choice.model().item(index)
                item.setFlags(item.flags() & ~(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable))
                item.setForeground(QBrush(locked_item_color()))
            # Screen readers get the lock reason / measurement state as a sentence.
            spoken = text
            if not model.fits:
                spoken = model.display_name + ". " + tr(
                    "setup.model.blocked_a11y", reason=tr("setup.model.block." + model.block_reason))
            elif model.peak_unverified:
                spoken = text + ". " + tr("setup.model.unverified_note")
            self.model_choice.setItemData(index, spoken, Qt.ItemDataRole.AccessibleTextRole)
        self.model_choice.setEnabled(True)
        keep = previous_choice if fit.model(previous_choice) is not None else None
        target = keep or (installed_mid if fit.model(installed_mid) is not None else None) \
            or fit.preselected_id
        # No recommendation: nothing is preselected; download needs an explicit choice.
        self.model_choice.setCurrentIndex(self.model_choice.findData(target) if target else -1)
        self.model_choice.blockSignals(False)
        if installed_mid:
            self._set_state("installed")
        elif fit.any_fits:
            self._set_state("ready")
        else:
            self._set_state("no_fit")

    def recheck(self):
        """Only re-run the device check. Never starts a download."""
        if self.busy or self._closed:
            return
        before = self.state
        self.refresh_recommendation()
        if self.state in {"no_fit", "specs_failed"} and self.state == before:
            self.status.setText(tr("setup.model.recheck_same"))
        (self.install_button if self.install_button.isEnabled() else self.recheck_button).setFocus()

    # ---- presentation -------------------------------------------------
    def selected_fit(self):
        return self.fit.model(self.model_choice.currentData()) if self.fit else None

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in {QEvent.Type.PaletteChange, QEvent.Type.StyleChange}:
            # Theme switch: keep locked entries in the current muted colour.
            color = locked_item_color()
            for row in range(self.model_choice.count()):
                item = self.model_choice.model().item(row)
                if item is not None and not item.isEnabled():
                    item.setForeground(QBrush(color))

    def _locked_by_free_ram(self) -> bool:
        """True only if closing programs would unlock at least one model.

        A locked, not-installed model whose ONLY blocking condition is
        current free RAM (installed RAM ok, file fits the disk), computed from
        the fit inputs and not from the shown reason string.
        """
        fit = self.fit
        return fit is not None and any(
            not m.fits and not m.installed and m.model_id in SETUP_MODEL_CATALOG
            and free_ram_only_lock(SETUP_MODEL_CATALOG[m.model_id], fit.total_gib,
                                   fit.available_gib, fit.free_disk_bytes, m.model_id)
            for m in fit.models)

    def _choice_changed(self, _index):
        if self.busy:
            return
        if self._no_choice_message and self.selected_fit() is not None:
            # A model is chosen now: replace the "choose first" message.
            self._no_choice_message = False
            self._set_state(self.state)
            return
        if self.state == "error" and self.model_choice.currentData() != self.failed_model_id:
            self._set_state("installed" if self._installed_model_id() else "ready")
        else:
            self._sync()

    def _set_state(self, state):
        self.state = state
        self._no_choice_message = False
        if state not in {"error"}:
            self.error_code.clear()
        fit = self.fit
        if state == "specs_failed":
            self.specs.setText("")
            self.recommended.setText(tr("setup.model.specs_failed"))
            self.status.setText(self._continue_without_ai())
            self.model_choice.clear()
            self.model_choice.setEnabled(False)
        elif state == "no_fit":
            reason = (fit.reason if fit and fit.reason else "ram_too_small")
            self.recommended.setText(tr("setup.model.no_fit") + "\n" + tr("setup.model.no_fit." + reason))
            self.status.setText(self._continue_without_ai())
        elif state in {"ready", "installed"}:
            labelled = fit.model(fit.labelled_recommended_id) if fit else None
            pre = fit.model(fit.preselected_id) if fit else None
            if labelled is not None:
                self.recommended.setText(tr("setup.model.recommended", name=labelled.display_name,
                                            size=format_gb(labelled.approx_bytes)))
            elif pre is not None:
                self.recommended.setText(tr("setup.model.preselected", name=pre.display_name,
                                            size=format_gb(pre.approx_bytes)))
            else:
                self.recommended.setText(tr("setup.model.choose_hint"))
            if state == "installed":
                mid = self._installed_model_id()
                # The wizard says "continue setup"; Settings names the active model.
                ready_key = "setup.model.ready" if self.context == "wizard" else "setup.model.ready_settings"
                self.status.setText(tr(ready_key, name=SETUP_MODEL_CATALOG[mid]["display_name"])
                                    + " " + tr("setup.model.can_switch"))
            else:
                self.status.setText(tr("setup.model.optional"))
        warn = [tr("setup.model.warning." + w) for w in (fit.warnings if fit else ())]
        self.warnings.setText("\n".join(warn))
        self.warnings.setVisible(bool(warn) and state not in {"specs_failed"})
        self._sync()
        self.state_changed.emit()

    def _continue_without_ai(self):
        return tr("setup.model.continue_without_ai_wizard" if self.context == "wizard"
                  else "setup.model.continue_without_ai")

    def _sync(self):
        """Single place that sets every button text/state; nothing is left stale."""
        self._sync_inner()
        for button in (self.install_button, self.recheck_button, self.cancel_button):
            reserve_bold_width(button)

    def _sync_inner(self):
        busy = self.busy
        choice = self.selected_fit()
        self.cancel_button.setVisible(busy)
        self.progress_bar.setVisible(busy)
        self.busy_hint.setVisible(busy)
        self.busy_hint.setText(tr("setup.model.busy_hint_wizard" if self.context == "wizard"
                                  else "setup.model.busy_hint") if busy else "")
        locked_choice = choice is not None and not choice.fits
        # Free RAM is the one lock the person can fix now (close programs,
        # check again), so that hint is shown without selecting the entry.
        free_ram_hint = not busy and not locked_choice and self._locked_by_free_ram() \
            and self.state not in {"specs_failed"}
        self.recheck_button.setVisible(not busy and self.state in {"specs_failed", "no_fit"}
                                       or (not busy and locked_choice) or free_ram_hint)
        self.recheck_button.setEnabled(not busy)
        self.model_choice.setEnabled(not busy and self.model_choice.count() > 0)
        # The closed combo wraps a long entry; the tooltip repeats the full text.
        self.model_choice.setToolTip(self.model_choice.currentText())
        self.model_choice.updateGeometry()
        self.error_code.setVisible(bool(self.error_code.text()))
        # Note for a blocked model: visible text and accessible name, never colour only.
        if locked_choice and not busy:
            self.fit_note.setText(_blocked_note(choice.block_reason))
            self.fit_note.show()
        elif free_ram_hint:
            self.fit_note.setText(tr("setup.model.free_ram_hint"))
            self.fit_note.show()
        else:
            self.fit_note.clear()
            self.fit_note.hide()
        if choice is not None and choice.fits and choice.peak_unverified and not busy:
            self.unverified_note.setText(tr("setup.model.unverified_note"))
            self.unverified_note.show()
        else:
            self.unverified_note.clear()
            self.unverified_note.hide()
        button = self.install_button
        button.setAccessibleDescription("")
        if busy:
            button.setText(tr("setup.model.download_selected"))
            button.setEnabled(False)
            button.setAccessibleName(tr("setup.model.download_selected"))
            return
        if self.state == "specs_failed" or choice is None:
            button.setText(tr("setup.model.download_selected"))
            button.setEnabled(False)
            button.setAccessibleName(tr("setup.model.download_unavailable" if self.state == "specs_failed"
                                        else "setup.model.choose_first"))
            return
        if not choice.fits:
            reason = tr("setup.model.block." + choice.block_reason)
            if ALLOW_UNFIT_OVERRIDE:
                button.setText(tr("setup.model.override"))
                button.setEnabled(True)
                button.setAccessibleName(tr("setup.model.override") + " " +
                                         _blocked_note(choice.block_reason))
            else:
                button.setText(tr("setup.model.blocked_button"))
                button.setEnabled(False)
                button.setAccessibleName(tr("setup.model.blocked_a11y", reason=reason))
            return
        button.setEnabled(True)
        if self.state == "error" and choice.model_id == self.failed_model_id:
            text = tr("setup.model.retry")
            button.setAccessibleName(tr("setup.model.retry_a11y"))
            button.setAccessibleDescription(self.status.text() + " " + self.error_code.text())
        elif choice.installed:
            text = tr("setup.model.reverify")
            button.setAccessibleName(text)
        else:
            text = tr("setup.model.download_selected")
            name = text
            if choice.peak_unverified:
                name = text + ". " + tr("setup.model.unverified_note")
            button.setAccessibleName(name)
        button.setText(text)

    # ---- installation -------------------------------------------------
    def _confirm_unfit_override(self, choice) -> bool:
        reason = tr("setup.model.block." + choice.block_reason)
        # Labeled buttons (no Qt Yes/No); destructive keeps "Nicht installieren"
        # as the default button, like the former default No.
        return confirm_action(
            self, tr("setup.model.override_title"),
            tr("setup.model.override_body", name=choice.display_name, reason=reason),
            confirm_text=tr("setup.model.override_confirm"),
            cancel_text=tr("setup.model.override_cancel"),
            destructive=True)

    def install(self):
        if self.busy or self._closed:
            return
        # Check current resources again; another application may have consumed RAM.
        self.refresh_recommendation()
        choice = self.selected_fit()
        if choice is None:
            # Never end silently: say why nothing starts.
            self._explain_no_choice()
            return
        if not choice.fits:
            # The visible fit note (set by refresh_recommendation above) names the lock reason.
            if not ALLOW_UNFIT_OVERRIDE or not self._confirm_unfit_override(choice):
                return
            LOG.warning("model_setup_unfit_override model_id=%s reason=%s",
                        choice.model_id, choice.block_reason)
        mid = choice.model_id
        self.busy = True
        self.failed_model_id = None
        self.error_code.clear()
        self.cancel_button.setEnabled(True)
        self._pending_progress = None
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.status.setText(tr("setup.model.downloading"))
        self.state = "busy"
        self._sync()
        self.cancel_button.setFocus()
        self.state_changed.emit()
        worker = FunctionWorker(lambda: install_recommended_model(
            mid, cancelled=worker._cancel.is_set, progress=self._emit_progress))

        def done(value, failed=False):
            self.busy = False
            if self._closed:
                self.state_changed.emit()
                return
            if worker._cancel.is_set():
                self.refresh_recommendation()
                self.status.setText(tr("setup.model.cancelled"))
                self.install_button.setFocus()
                return
            if failed:
                self._show_failure(mid, model_failure_code(value),
                                   getattr(value, "download_diagnostic", ""), value)
                return
            active_path = selected_model_path()
            active_id = selected_model_id() if active_path is not None else None
            if active_path is None or active_id != mid:
                self._show_failure(mid, "activation_failed", "")
                return
            self.refresh_recommendation()
            self.model_ready.emit(mid)

        connect_queued(worker.finished, done)
        connect_queued(worker.failed, lambda error: done(error, True))
        self.worker = worker
        self.thread = start_worker(worker)

    def _explain_no_choice(self):
        """Visible reason why install() starts nothing when no model is selected.

        If some model in the list can be chosen, ask for that choice. If none
        can (empty list, nothing fits, device check failed), the card already
        names the reason; the status repeats how to continue without AI.
        """
        selectable = self.fit is not None and any(
            m.fits or m.installed for m in self.fit.models) and self.model_choice.count() > 0
        if self.state != "specs_failed" and selectable:
            message = tr("setup.model.choose_first_message")
            self._no_choice_message = True
        else:
            message = self._continue_without_ai()
        self.status.setText(message)
        self.status.show()
        self._sync()
        # Same text for screen readers on the (disabled) main button.
        self.install_button.setAccessibleDescription(message)
        (self.model_choice if self.model_choice.isEnabled() else self.recheck_button).setFocus()

    def _show_failure(self, mid, code, diagnostic, error=None):
        LOG.error("model_setup_failed model_id=%s reason=%s diagnostic=%s", mid, code,
                  failure_diagnostic(code, diagnostic, error))
        self.refresh_recommendation()
        index = self.model_choice.findData(mid)
        if index >= 0:
            self.model_choice.blockSignals(True)
            self.model_choice.setCurrentIndex(index)
            self.model_choice.blockSignals(False)
        self.failed_model_id = mid
        self.state = "error"
        self.status.setText(model_failure_message(code))
        self.error_code.setText(tr("setup.model.error_code", code=code))
        self._sync()
        self.state_changed.emit()
        if self.install_button.isEnabled():
            self.install_button.setFocus(Qt.FocusReason.OtherFocusReason)

    def _emit_progress(self, progress):
        # Throttle worker→GUI messages: never queue one event per megabyte.
        value = (progress.status, int(100 * progress.bytes_done / progress.bytes_total)
                 if progress.bytes_total else 0)
        if value != self._pending_progress:
            self._pending_progress = value
            from dataclasses import replace
            self.download_progress.emit(replace(progress))

    def _show_progress(self, progress):
        if self._closed or not self.busy:
            return
        if progress.status == "retrying":
            self.status.setText(tr("setup.model.retrying"))
        elif progress.status in {"checking", "verifying", "testing"}:
            self.progress_bar.setRange(0, 0)
            self.status.setText(tr("setup.model.testing" if progress.status == "testing" else "setup.model.verifying"))
        elif progress.status == "downloading":
            self.status.setText(tr("setup.model.downloading"))
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(min(99, int(100 * progress.bytes_done / progress.bytes_total))
                                       if progress.bytes_total else 0)

    def cancel(self):
        worker = getattr(self, "worker", None)
        if self.busy and worker is not None:
            worker.request_cancel()
            self.cancel_button.setEnabled(False)
            self.status.setText(tr("setup.model.cancelling"))

    def shutdown(self):
        self._closed = True
        self.cancel()
