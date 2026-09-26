"""V2 shared shell primitives — visual language only (no new product features)."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QAbstractButton,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from desktop.design_system.a11y import set_accessible_name
from desktop.design_system.icons import status_glyph
from desktop.design_system.polish import (
    apply_button_icon,
    make_close_button,
    polish_card,
    polish_chip,
    polish_interactive,
)


class PageHeader(QWidget):
    """Compact page title + optional subtitle (V2 desktop hierarchy)."""

    def __init__(
        self,
        title: str = "",
        subtitle: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("V2PageHeader")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 8)
        layout.setSpacing(2)
        self.title = QLabel(title)
        self.title.setObjectName("PageTitle")
        self.subtitle = QLabel(subtitle)
        self.subtitle.setObjectName("PageSubtitle")
        self.subtitle.setWordWrap(True)
        self.subtitle.setVisible(bool(subtitle))
        layout.addWidget(self.title)
        layout.addWidget(self.subtitle)
        set_accessible_name(self.title, title)

    def set_texts(self, title: str, subtitle: str = "") -> None:
        self.title.setText(title)
        set_accessible_name(self.title, title)
        self.subtitle.setText(subtitle)
        self.subtitle.setVisible(bool(subtitle))


class StatusChip(QLabel):
    """Status chip with text glyph — never color-only (V2 / a11y)."""

    _KIND_OBJECT = {
        "success": "BadgeOk",
        "ok": "BadgeOk",
        "warning": "BadgeWarn",
        "warn": "BadgeWarn",
        "error": "BadgeDanger",
        "danger": "BadgeDanger",
        "info": "BadgeInfo",
        "muted": "BadgeMuted",
    }

    def __init__(
        self,
        text: str = "",
        *,
        kind: str = "info",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.set_status(text, kind=kind)
        polish_chip(self)

    def set_status(self, text: str, *, kind: str = "info") -> None:
        glyph_kind = {
            "ok": "success",
            "warn": "warning",
            "danger": "error",
            "success": "success",
            "warning": "warning",
            "error": "error",
            "info": "info",
            "muted": "muted",
        }.get(kind, "info")
        glyph = status_glyph(glyph_kind)
        body = (text or "").strip()
        composed = f"{glyph}: {body}" if body else glyph
        self.setText(composed)
        self.setObjectName(self._KIND_OBJECT.get(kind, "BadgeInfo"))
        set_accessible_name(self, composed)
        style = self.style()
        if style is not None:
            style.unpolish(self)
            style.polish(self)


class KpiCard(QFrame):
    """Compact KPI tile — large number is the visual focus (demo hierarchy)."""

    activated = Signal()

    def __init__(
        self,
        label: str = "",
        value: str = "0",
        *,
        hint: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(2)
        self.caption = QLabel(label)
        self.caption.setObjectName("PageSubtitle")
        self.value_label = QLabel(value)
        self.value_label.setObjectName("KpiValue")
        self.hint_label = QLabel(hint)
        self.hint_label.setObjectName("KkHint")
        self.hint_label.setVisible(bool(hint))
        layout.addWidget(self.caption)
        layout.addWidget(self.value_label)
        layout.addWidget(self.hint_label)
        set_accessible_name(self, f"{label}: {value}")
        self._clickable = False
        polish_card(self)

    def set_clickable(self, clickable: bool, *, tooltip: str = "") -> None:
        """Only cards that actually navigate get the pointer/hover/focus affordance."""
        self._clickable = bool(clickable)
        self.setProperty("kkClickable", "true" if clickable else "false")
        self.setCursor(
            Qt.CursorShape.PointingHandCursor if clickable else Qt.CursorShape.ArrowCursor
        )
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus if clickable else Qt.FocusPolicy.NoFocus)
        self.setToolTip(tooltip if clickable else "")
        style = self.style()
        if style is not None:
            style.unpolish(self)
            style.polish(self)

    def is_clickable(self) -> bool:
        return self._clickable

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if (
            self._clickable
            and event.button() == Qt.MouseButton.LeftButton
            and self.rect().contains(event.position().toPoint())
        ):
            self.activated.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if self._clickable and event.key() in (
            Qt.Key.Key_Return,
            Qt.Key.Key_Enter,
            Qt.Key.Key_Space,
        ):
            self.activated.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def set_value(
        self,
        value: str | int,
        label: str | None = None,
        *,
        hint: str | None = None,
    ) -> None:
        self.value_label.setText(str(value))
        if label is not None:
            self.caption.setText(label)
        if hint is not None:
            self.hint_label.setText(hint)
            self.hint_label.setVisible(bool(hint))
        set_accessible_name(self, f"{self.caption.text()}: {self.value_label.text()}")


class ContentCard(QFrame):
    """White surface card with subtle border (V2)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self._body = QVBoxLayout(self)
        self._body.setContentsMargins(16, 16, 16, 16)
        self._body.setSpacing(12)
        polish_card(self)

    def body(self) -> QVBoxLayout:
        return self._body


class EmptyStatePanel(QWidget):
    """Calm empty / blocked state — title + body, optional primary CTA."""

    def __init__(
        self,
        title: str = "",
        body: str = "",
        *,
        action_text: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("EmptyStatePanel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 32, 24, 32)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title = QLabel(title)
        self.title.setObjectName("NextActionTitle")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title.setWordWrap(True)
        self.body = QLabel(body)
        self.body.setObjectName("PageSubtitle")
        self.body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.body.setWordWrap(True)
        self.action_btn = QPushButton(action_text)
        self.action_btn.setObjectName("SecondaryButton")
        self.action_btn.setVisible(bool(action_text))
        layout.addWidget(self.title)
        layout.addWidget(self.body)
        layout.addWidget(self.action_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        set_accessible_name(self, title or body)

    def set_texts(self, title: str, body: str = "", *, action_text: str = "") -> None:
        self.title.setText(title)
        self.body.setText(body)
        self.body.setVisible(bool(body))
        self.action_btn.setText(action_text)
        self.action_btn.setVisible(bool(action_text))
        set_accessible_name(self, title or body)


class IconActionButton(QPushButton):
    """Compact secondary icon/text button (card header actions)."""

    def __init__(self, text: str = "", *, accessible_name: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("SecondaryButton")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        set_accessible_name(self, accessible_name or text)


class TagChip(QLabel):
    """Compact tag / chip for skills and career goals.

    Horizontal size never shrinks below the text need — a wrapping ``FlowLayout``
    moves chips to the next line instead of eliding. Very long tokens wrap
    inside the chip when the parent line is narrower than the text.
    """

    def __init__(
        self,
        text: str = "",
        *,
        kind: str = "neutral",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)
        mapping = {
            "wanted": "BadgeOk",
            "unwanted": "BadgeDanger",
            "neutral": "BadgeMuted",
            "more": "BadgeMuted",
        }
        self.setObjectName(mapping.get(kind, "BadgeMuted"))
        self.setWordWrap(True)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        # Minimum: layout must not squash pills; Preferred height allows wrap.
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
        set_accessible_name(self, text)
        polish_chip(self)

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        if width <= 0:
            return int(self.sizeHint().height())
        metrics = self.fontMetrics()
        rect = metrics.boundingRect(
            0,
            0,
            max(24, int(width)),
            4000,
            int(Qt.TextFlag.TextWordWrap),
            self.text(),
        )
        return int(rect.height() + 8)


class DataItem(QWidget):
    """Label + value stack used in profile data grids."""

    def __init__(self, label: str = "", value: str = "—", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self.label = QLabel(label)
        self.label.setObjectName("KkHint")
        self.value = QLabel(value or "—")
        self.value.setObjectName("PageSubtitle")
        self.value.setWordWrap(True)
        layout.addWidget(self.label)
        layout.addWidget(self.value)
        set_accessible_name(self, f"{label}: {value or '—'}")

    def set_pair(self, label: str, value: str) -> None:
        self.label.setText(label)
        self.value.setText(value or "—")
        set_accessible_name(self, f"{label}: {value or '—'}")


class ProfileSectionCard(QFrame):
    """Demo-aligned profile section card with header action + expand/collapse.

    Clicking free card surface (not Bearbeiten/Hinzufügen or other buttons)
    toggles ``expanded``. Keyboard: Space / Enter. Hover uses soft shadow +
    border lift without changing geometry.
    """

    expandedChanged = Signal(bool)

    def __init__(
        self,
        title: str = "",
        *,
        action_text: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setProperty("kkClickable", "true")
        self.setProperty("kkExpanded", "false")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._expanded = False
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        header = QHBoxLayout()
        header.setContentsMargins(16, 14, 16, 14)
        header.setSpacing(8)
        self.expand_indicator = QToolButton()
        self.expand_indicator.setObjectName("GhostButton")
        self.expand_indicator.setAutoRaise(True)
        self.expand_indicator.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.expand_indicator.setCursor(Qt.CursorShape.PointingHandCursor)
        self.expand_indicator.setFixedSize(28, 28)
        self.expand_indicator.clicked.connect(self.toggle_expanded)
        apply_button_icon(self.expand_indicator, "chevron_down", color="#5a6b7a", size=14)
        header.addWidget(self.expand_indicator)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("NextActionTitle")
        self.title_label.setWordWrap(True)
        self.title_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.title_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        header.addWidget(self.title_label, stretch=1)
        self.action_btn = IconActionButton(action_text)
        self.action_btn.setVisible(bool(action_text))
        # Action keeps its own hit target — must not bubble into expand toggle.
        self.action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        header.addWidget(self.action_btn)
        root.addLayout(header)
        self._body = QVBoxLayout()
        self._body.setContentsMargins(16, 0, 16, 16)
        self._body.setSpacing(12)
        root.addLayout(self._body)
        set_accessible_name(self, title)
        # Interactive hover shadow (same resting metrics as polish_card) —
        # geometry stays fixed; only blur/alpha/border change on hover.
        polish_interactive(
            self,
            blur=22.0,
            y_offset=6.0,
            alpha=28,
            cursor=True,
            hover_blur=14.0,
            hover_y=4.0,
            hover_alpha=40,
            press=False,
        )
        self._sync_expand_chrome()

    def body(self) -> QVBoxLayout:
        return self._body

    def is_expanded(self) -> bool:
        return self._expanded

    def set_expanded(self, expanded: bool) -> None:
        want = bool(expanded)
        if want == self._expanded:
            self._sync_expand_chrome()
            return
        self._expanded = want
        self.setProperty("kkExpanded", "true" if want else "false")
        self._sync_expand_chrome()
        style = self.style()
        if style is not None:
            style.unpolish(self)
            style.polish(self)
        self.expandedChanged.emit(want)

    def toggle_expanded(self) -> None:
        self.set_expanded(not self._expanded)

    def _sync_expand_chrome(self) -> None:
        from desktop.i18n import tr

        icon = "chevron_up" if self._expanded else "chevron_down"
        apply_button_icon(self.expand_indicator, icon, color="#5a6b7a", size=14)
        tip = tr("profile.collapse") if self._expanded else tr("profile.expand")
        self.expand_indicator.setToolTip(tip)
        set_accessible_name(self.expand_indicator, tip)
        title = self.title_label.text()
        set_accessible_name(self, f"{title} — {tip}")

    def set_title(self, title: str) -> None:
        self.title_label.setText(title)
        self._sync_expand_chrome()

    def set_action_text(self, text: str) -> None:
        self.action_btn.setText(text)
        set_accessible_name(self.action_btn, text)
        self.action_btn.setVisible(bool(text))

    def _is_interactive_target(self, widget: QWidget | None) -> bool:
        cur: QWidget | None = widget
        while cur is not None and cur is not self:
            if cur is self.expand_indicator or cur is self.action_btn:
                return True
            if isinstance(cur, QAbstractButton):
                return True
            if cur.property("kkKeepInteractive"):
                return True
            flags = getattr(cur, "textInteractionFlags", None)
            if callable(flags):
                try:
                    interaction = flags()
                    if interaction & Qt.TextInteractionFlag.LinksAccessibleByMouse:
                        return True
                except Exception:
                    pass
            cur = cur.parentWidget()
        return False

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(
            event.position().toPoint()
        ):
            child = self.childAt(event.position().toPoint())
            if not self._is_interactive_target(child):
                self.toggle_expanded()
                event.accept()
                return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.toggle_expanded()
            event.accept()
            return
        super().keyPressEvent(event)


class SectionEditDrawer(QDialog):
    """Right-side edit drawer — Speichern / Abbrechen (demo pattern)."""

    def __init__(self, title: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(420)
        self.setMaximumWidth(720)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(12)
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("PageTitle")
        self.title_label.setWordWrap(True)
        title_row.addWidget(self.title_label, stretch=1)
        # Top-right: close (X) only — primary Speichern stays bottom-right
        self.close_btn = make_close_button(parent=self)
        self.close_btn.clicked.connect(self.reject)
        title_row.addWidget(self.close_btn, alignment=Qt.AlignmentFlag.AlignTop)
        layout.addLayout(title_row)
        self._host = QVBoxLayout()
        self._host.setContentsMargins(0, 0, 0, 0)
        from desktop.widgets.dialog_geometry import wrap_dialog_body

        self._scroll_host = QWidget()
        self._scroll_host.setLayout(self._host)
        self._scroll = wrap_dialog_body(self._scroll_host)
        layout.addWidget(self._scroll, stretch=1)
        buttons = QHBoxLayout()
        buttons.addStretch()
        self.cancel_btn = QPushButton()
        self.cancel_btn.setObjectName("SecondaryButton")
        self.save_btn = QPushButton()
        self.save_btn.setObjectName("PrimaryButton")
        polish_interactive(self.save_btn)
        self.cancel_btn.clicked.connect(self.reject)
        self.save_btn.clicked.connect(self.accept)
        buttons.addWidget(self.cancel_btn)
        buttons.addWidget(self.save_btn)
        layout.addLayout(buttons)
        self._content: QWidget | None = None

    def set_texts(self, *, title: str, save: str, cancel: str) -> None:
        self.setWindowTitle(title)
        self.title_label.setText(title)
        self.title_label.setToolTip(title)
        self.save_btn.setText(save)
        self.cancel_btn.setText(cancel)
        set_accessible_name(self.save_btn, save)
        set_accessible_name(self.cancel_btn, cancel)
        apply_button_icon(self.save_btn, "save", color="#ffffff")
        self.close_btn.setToolTip(cancel or "Schließen")
        set_accessible_name(self.close_btn, cancel or "Schließen")

    def present(self, content: QWidget) -> int:
        if self._content is not None:
            self._host.removeWidget(self._content)
        self._content = content
        content.setVisible(True)
        self._host.addWidget(content)
        from desktop.widgets.dialog_geometry import fit_dialog_to_screen

        fit_dialog_to_screen(self, preferred_width=560, preferred_height=640)
        self.save_btn.setDefault(True)
        self.save_btn.setAutoDefault(True)
        return int(self.exec())

    def take_content(self) -> QWidget | None:
        content = self._content
        if content is not None:
            self._host.removeWidget(content)
            content.setParent(None)
            self._content = None
        return content
