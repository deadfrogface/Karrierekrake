"""Horizontal rail of the application steps with their proof (see desktop.viewmodels.evidence_rail)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from desktop.viewmodels.evidence_rail import DONE, FAILED, OPEN, UNCERTAIN, RailStep

_SYMBOL = {DONE: "✓", UNCERTAIN: "!", FAILED: "✕", OPEN: ""}


def _colors():
    from desktop.design_system.tokens import tokens_for_theme

    app = QApplication.instance()
    theme = app.property("kk_palette_theme") if app is not None else None
    return tokens_for_theme("dark" if theme == "dark" else "light").colors


class EvidenceRail(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("DetailPanel")
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(14, 12, 14, 12)
        self._layout.setSpacing(6)
        self._widgets: list[QWidget] = []

    def bind(self, steps: list[RailStep]) -> None:
        for widget in self._widgets:
            self._layout.removeWidget(widget)
            widget.hide()
            widget.setParent(None)
            widget.deleteLater()
        self._widgets = []
        colors = _colors()
        tone = {DONE: colors.success, UNCERTAIN: colors.warning, FAILED: colors.error, OPEN: colors.border}
        for index, step in enumerate(steps):
            column = QWidget()
            box = QVBoxLayout(column)
            box.setContentsMargins(4, 0, 4, 0)
            box.setSpacing(4)
            dot = QLabel(_SYMBOL[step.state])
            dot.setFixedSize(26, 26)
            dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
            filled = step.state != OPEN
            dot.setStyleSheet(
                f"background:{tone[step.state] if filled else 'transparent'};"
                f"color:{'#ffffff' if filled else colors.muted};border-radius:13px;font-weight:700;"
                f"border:2px solid {tone[step.state]};")
            title = QLabel(f"<b>{step.label}</b>")
            title.setWordWrap(True)
            hint = QLabel(step.evidence)
            hint.setWordWrap(True)
            hint.setStyleSheet(f"color:{colors.warning if step.state == UNCERTAIN else colors.muted};")
            dot_row = QHBoxLayout()
            dot_row.setContentsMargins(0, 0, 0, 0)
            dot_row.setSpacing(8)
            dot_row.addWidget(dot)
            if index < len(steps) - 1:
                line = QFrame()
                line.setFixedHeight(2)
                line.setStyleSheet(f"background:{tone[step.state] if step.state == DONE else colors.border};")
                dot_row.addWidget(line, 1, Qt.AlignmentFlag.AlignVCenter)
            box.addLayout(dot_row)
            box.addWidget(title)
            box.addWidget(hint)
            box.addStretch(1)
            self._layout.addWidget(column, 1)
            self._widgets.append(column)
        self.setAccessibleDescription(", ".join(f"{s.label}: {s.state}" for s in steps))
