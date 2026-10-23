"""First-steps checklist for the overview page: what is done, what comes next, one click to each step."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QPushButton, QSizePolicy, QWidget

from desktop.design_system.v2_chrome import ContentCard


class GettingStartedCard(ContentCard):
    dismissed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("GettingStartedCard")
        self.body().setSpacing(2)
        head = QHBoxLayout()
        self.title = QLabel("Erste Schritte")
        self.title.setObjectName("NextActionTitle")
        self.count = QLabel()
        self.count.setObjectName("KkHint")
        self.dismiss_btn = QPushButton("Ausblenden")
        self.dismiss_btn.setObjectName("GhostButton")
        self.dismiss_btn.setFlat(True)
        self.dismiss_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.dismiss_btn.clicked.connect(self.dismissed)
        head.addWidget(self.title)
        head.addWidget(self.count)
        head.addStretch(1)
        head.addWidget(self.dismiss_btn)
        self.body().addLayout(head)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(6)
        self.bar.setStyleSheet("QProgressBar{background:rgba(127,127,127,0.25);border:none;border-radius:3px;}"
                               "QProgressBar::chunk{background:#14B8A6;border-radius:3px;}")
        self.body().addWidget(self.bar)
        self._rows: list[QWidget] = []

    def set_steps(self, steps: list[tuple[str, str, bool, Callable[[], None] | None, str]]) -> None:
        """Each step: (title, hint, done, action, action label)."""
        for row in self._rows:
            self.body().removeWidget(row)
            row.hide()  # deleteLater alone leaves the old row painted until the event loop catches up
            row.setParent(None)
            row.deleteLater()
        self._rows = []
        done = sum(1 for _title, _hint, ok, _action, _label in steps if ok)
        self.count.setText(f"{done} von {len(steps)} erledigt")
        self.bar.setRange(0, max(1, len(steps)))
        self.bar.setValue(done)
        for title, hint, ok, action, label in steps:
            row = QWidget()
            layout = QHBoxLayout(row)
            layout.setContentsMargins(0, 2, 0, 2)
            layout.setSpacing(10)
            mark = QLabel("✓" if ok else "○")
            mark.setFixedWidth(20)
            mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
            mark.setObjectName("KkSuccessMark" if ok else "KkHint")
            # A finished step only needs its title; the hint is for what is still to do.
            text = QLabel(f"<b>{title}</b>" if ok else f"<b>{title}</b><br><span style='opacity:0.75'>{hint}</span>")
            text.setWordWrap(True)
            text.setTextFormat(Qt.TextFormat.RichText)
            layout.addWidget(mark)
            layout.addWidget(text, 1)
            if not ok and action is not None:
                button = QPushButton(label or "Los")
                button.setObjectName("SecondaryButton")
                button.setCursor(Qt.CursorShape.PointingHandCursor)
                button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
                button.clicked.connect(lambda _=False, cb=action: cb())
                layout.addWidget(button)
            self.body().addWidget(row)
            self._rows.append(row)
