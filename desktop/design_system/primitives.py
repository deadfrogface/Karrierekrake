"""Reusable PySide6 primitives for the design system."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from desktop.design_system.a11y import bind_label, set_accessible_name
from desktop.design_system.icons import status_glyph, try_qtawesome_icon
from desktop.design_system.polish import polish_chip


class ButtonVariant(str, Enum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    GHOST = "ghost"


class ValidationState(str, Enum):
    NONE = ""
    ERROR = "error"
    WARNING = "warning"
    SUCCESS = "success"


_BUTTON_OBJECT = {
    ButtonVariant.PRIMARY: "KkPrimary",
    ButtonVariant.SECONDARY: "KkSecondary",
    ButtonVariant.GHOST: "KkGhost",
}


class KkButton(QPushButton):
    """Shared button with focus/disabled object names."""

    def __init__(
        self,
        text: str = "",
        *,
        variant: ButtonVariant | str = ButtonVariant.PRIMARY,
        parent: QWidget | None = None,
        accessible_name: str = "",
    ) -> None:
        super().__init__(text, parent)
        self.setObjectName("KkPrimitive")
        self.set_variant(variant)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        set_accessible_name(self, accessible_name or text)

    def set_variant(self, variant: ButtonVariant | str) -> None:
        if isinstance(variant, str):
            variant = ButtonVariant(variant)
        self.setObjectName(_BUTTON_OBJECT[variant])


class KkLineEdit(QLineEdit):
    """Input with validation property ``kkState`` for QSS."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        accessible_name: str = "",
        placeholder: str = "",
    ) -> None:
        super().__init__(parent)
        self.setObjectName("KkInput")
        if placeholder:
            self.setPlaceholderText(placeholder)
        if accessible_name:
            set_accessible_name(self, accessible_name)
        self._state = ValidationState.NONE

    def set_validation_state(self, state: ValidationState | str) -> None:
        if isinstance(state, str):
            state = ValidationState(state) if state else ValidationState.NONE
        self._state = state
        self.setProperty("kkState", state.value)
        # Force style refresh
        style = self.style()
        if style is not None:
            style.unpolish(self)
            style.polish(self)

    @property
    def validation_state(self) -> ValidationState:
        return self._state


class KkCard(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("KkCard")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(16, 16, 16, 16)
        self._layout.setSpacing(8)

    def body_layout(self) -> QVBoxLayout:
        return self._layout


class KkStatusBadge(QLabel):
    """Status chip — always includes a text glyph so color is not the only cue."""

    def __init__(
        self,
        text: str = "",
        *,
        kind: Literal["success", "warning", "error", "info", "muted"] = "info",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.set_kind(kind, text)
        polish_chip(self)

    def set_kind(
        self,
        kind: Literal["success", "warning", "error", "info", "muted"],
        text: str = "",
    ) -> None:
        mapping = {
            "success": "KkStatusSuccess",
            "warning": "KkStatusWarning",
            "error": "KkStatusError",
            "info": "BadgeInfo",
            "muted": "BadgeMuted",
        }
        self.setObjectName(mapping.get(kind, "BadgeMuted"))
        glyph = status_glyph(kind)
        label = text.strip()
        self.setText(f"{glyph} {label}".strip() if label else glyph)
        set_accessible_name(self, label or kind)
        icon = try_qtawesome_icon(
            {
                "success": "fa5s.check-circle",
                "warning": "fa5s.exclamation-triangle",
                "error": "fa5s.times-circle",
                "info": "fa5s.info-circle",
                "muted": "fa5s.circle",
            }.get(kind, "fa5s.circle")
        )
        if icon is not None:
            # Keep text glyph; icon is optional enrichment only.
            self.setToolTip(label or kind)


class KkFormField(QWidget):
    """Label + input + hint/error row with buddy binding."""

    def __init__(
        self,
        label: str,
        *,
        parent: QWidget | None = None,
        placeholder: str = "",
    ) -> None:
        super().__init__(parent)
        self.setObjectName("KkPrimitive")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.label = QLabel(label)
        self.input = KkLineEdit(accessible_name=label, placeholder=placeholder)
        bind_label(self.label, self.input, accessible_name=label)
        self.hint = QLabel()
        self.hint.setObjectName("KkHint")
        self.hint.setWordWrap(True)
        self.error = QLabel()
        self.error.setObjectName("KkErrorText")
        self.error.setWordWrap(True)
        self.error.hide()
        layout.addWidget(self.label)
        layout.addWidget(self.input)
        layout.addWidget(self.hint)
        layout.addWidget(self.error)

    def set_hint(self, text: str) -> None:
        self.hint.setText(text)
        self.hint.setVisible(bool(text))

    def set_error(self, text: str) -> None:
        self.error.setText(text)
        self.error.setVisible(bool(text))
        self.input.set_validation_state(
            ValidationState.ERROR if text else ValidationState.NONE
        )


class KkDialog(QDialog):
    """Minimal dialog shell with accessible title."""

    def __init__(
        self,
        title: str = "",
        *,
        parent: QWidget | None = None,
        buttons: QDialogButtonBox.StandardButton = QDialogButtonBox.StandardButton.Ok,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("KkDialog")
        self.setWindowTitle(title)
        set_accessible_name(self, title)
        self._root = QVBoxLayout(self)
        self._root.setSpacing(12)
        self.body = QVBoxLayout()
        self._root.addLayout(self.body)
        from desktop.widgets.confirm_dialog import label_button_box

        self.button_box = label_button_box(QDialogButtonBox(buttons))
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self._root.addWidget(self.button_box)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)

    def content_layout(self) -> QVBoxLayout:
        return self.body
