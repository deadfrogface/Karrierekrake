"""V2 Postfach page — mail association / drafts (preserves Lifecycle mail flows).

Does not invent Gmail send. Read-only sync + local drafts / review only.
"""

from __future__ import annotations

from PySide6.QtWidgets import QVBoxLayout, QWidget

from desktop.i18n import tr
from desktop.pages.lifecycle import LifecyclePage
from desktop.services import ConfigService
from desktop.design_system.v2_chrome import PageHeader


class InboxPage(QWidget):
    """Postfach surface: reuses LifecyclePage mail/case tooling without deleting it."""

    def __init__(self, config_service: ConfigService, parent=None) -> None:
        super().__init__(parent)
        self.config_service = config_service
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.header = PageHeader(tr("nav.inbox"), tr("inbox.subtitle"))
        layout.addWidget(self.header)
        # Full lifecycle tooling preserved (mail link, drafts, calendar, prep).
        self.lifecycle = LifecyclePage(config_service)
        layout.addWidget(self.lifecycle, 1)

    def retranslate_ui(self) -> None:
        self.header.set_texts(tr("nav.inbox"), tr("inbox.subtitle"))
        if hasattr(self.lifecycle, "retranslate_ui"):
            self.lifecycle.retranslate_ui()

    def refresh(self) -> None:
        if hasattr(self.lifecycle, "refresh"):
            self.lifecycle.refresh()
