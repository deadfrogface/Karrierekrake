"""V2 shared shell primitives — visual language only (no new product features)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from desktop.design_system.a11y import set_accessible_name
from desktop.design_system.icons import status_glyph


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
    """Quiet KPI tile for Übersicht — values must be live, never demo hardcodes."""

    def __init__(
        self,
        label: str = "",
        value: str = "0",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(4)
        self.value_label = QLabel(value)
        self.value_label.setObjectName("PageTitle")
        self.caption = QLabel(label)
        self.caption.setObjectName("PageSubtitle")
        layout.addWidget(self.value_label)
        layout.addWidget(self.caption)
        set_accessible_name(self, f"{label}: {value}")

    def set_value(self, value: str | int, label: str | None = None) -> None:
        self.value_label.setText(str(value))
        if label is not None:
            self.caption.setText(label)
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

    def body(self) -> QVBoxLayout:
        return self._body
