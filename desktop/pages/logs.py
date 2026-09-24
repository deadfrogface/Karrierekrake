"""Logs viewer — plain-language events with technical details secondary."""

from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from desktop.design_system.polish import apply_button_icon, footer_actions_layout, polish_interactive
from desktop.i18n import tr
from desktop.services import ConfigService

_LEVEL_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:,\d+)?)\s+"
    r"(?P<level>DEBUG|INFO|WARNING|ERROR|CRITICAL)\s+"
    r"(?P<logger>[\w.]+)?\s*:?\s*(?P<msg>.*)$"
)


def _humanize_line(line: str) -> tuple[str, str]:
    """Return (plain_summary, technical_line)."""
    raw = line.rstrip()
    if not raw:
        return "", ""
    m = _LEVEL_RE.match(raw)
    if not m:
        return raw[:120], raw
    level = m.group("level")
    msg = (m.group("msg") or "").strip()
    ts = m.group("ts")
    lower = msg.lower()
    if "captcha" in lower:
        plain = tr("logs.event.captcha")
    elif "needs_review" in lower or "needs review" in lower:
        plain = tr("logs.event.review")
    elif "dry run" in lower or "dry_run" in lower:
        plain = tr("logs.event.dry_run")
    elif "search" in lower and ("start" in lower or "begin" in lower):
        plain = tr("logs.event.search_start")
    elif "search" in lower and ("finish" in lower or "done" in lower or "complete" in lower):
        plain = tr("logs.event.search_done")
    elif "error" in lower or level in {"ERROR", "CRITICAL"}:
        plain = tr("logs.event.error")
    elif "apply" in lower:
        plain = tr("logs.event.apply")
    elif "duplicate" in lower or "dedup" in lower:
        plain = tr("logs.event.dedup")
    else:
        plain = msg[:100] if msg else level
    summary = f"{ts[11:19] if len(ts) >= 19 else ts} · {plain}"
    return summary, raw


class LogsPage(QWidget):
    def __init__(self, config_service: ConfigService, parent=None) -> None:
        super().__init__(parent)
        self.config_service = config_service
        self._tech_lines: list[str] = []

        self.page_title = QLabel()
        self.page_title.setObjectName("PageTitle")
        self.page_subtitle = QLabel()
        self.page_subtitle.setObjectName("PageSubtitle")
        self.page_subtitle.setWordWrap(True)

        self.events = QListWidget()
        self.events.setObjectName("EventList")
        self.events.currentRowChanged.connect(self._show_tech)
        self.tech = QPlainTextEdit()
        self.tech.setObjectName("LogPlain")
        self.tech.setReadOnly(True)
        self.tech_label = QLabel()
        self.tech_label.setObjectName("PageSubtitle")

        splitter = QSplitter()
        splitter.setOrientation(Qt.Orientation.Vertical)
        splitter.addWidget(self.events)
        tech_wrap = QWidget()
        tech_layout = QVBoxLayout(tech_wrap)
        tech_layout.setContentsMargins(0, 0, 0, 0)
        tech_layout.addWidget(self.tech_label)
        tech_layout.addWidget(self.tech)
        splitter.addWidget(tech_wrap)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        self.refresh_btn = QPushButton()
        self.refresh_btn.setObjectName("SecondaryButton")
        self.refresh_btn.clicked.connect(self.refresh)
        polish_interactive(self.refresh_btn, blur=12.0, y_offset=2.0, alpha=28)

        layout = QVBoxLayout(self)
        layout.addWidget(self.page_title)
        layout.addWidget(self.page_subtitle)
        layout.addWidget(splitter, 1)
        # Refresh is a secondary action — bottom-right, not a top primary CTA
        layout.addLayout(footer_actions_layout(self.refresh_btn))
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        self.page_title.setText(tr("logs.page_title"))
        self.page_subtitle.setText(tr("logs.page_subtitle"))
        self.refresh_btn.setText(tr("logs.refresh"))
        apply_button_icon(self.refresh_btn, "refresh", color="#1c2430")
        self.tech_label.setText(tr("logs.technical"))

    def _show_tech(self, row: int) -> None:
        if 0 <= row < len(self._tech_lines):
            self.tech.setPlainText(self._tech_lines[row])
        else:
            self.tech.clear()

    def refresh(self) -> None:
        cfg = self.config_service.load()
        logs_dir = Path(cfg.settings.logs_dir)
        if not logs_dir.is_absolute():
            logs_dir = cfg.root / logs_dir
        self.events.clear()
        self._tech_lines = []
        self.tech.clear()
        if not logs_dir.exists():
            self.events.addItem(tr("logs.empty"))
            return
        files = sorted(logs_dir.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not files:
            files = sorted(logs_dir.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not files:
            self.events.addItem(tr("logs.empty"))
            return
        latest = files[0]
        try:
            text = latest.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            self.events.addItem(f"{tr('logs.read_error')}: {exc}")
            return
        lines = text.splitlines()[-400:]
        for line in lines:
            summary, tech = _humanize_line(line)
            if not summary:
                continue
            self.events.addItem(QListWidgetItem(summary))
            self._tech_lines.append(tech)
        if self.events.count() == 0:
            self.events.addItem(tr("logs.empty"))
