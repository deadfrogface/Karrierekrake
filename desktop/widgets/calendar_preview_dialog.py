"""Local calendar preview. Selecting a suggestion never writes an event."""
from __future__ import annotations

from PySide6.QtCore import QDate, QLocale, Qt
from PySide6.QtGui import QColor, QTextCharFormat
from PySide6.QtWidgets import (
    QCalendarWidget, QDialog, QDialogButtonBox, QHBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem, QVBoxLayout,
)
from integrations.reply_draft import human_slot


class CalendarPreviewDialog(QDialog):
    def __init__(self, slots, *, title: str, parent=None):
        super().__init__(parent)
        self.slots = list(slots)
        self.selected_index = None
        self.setWindowTitle("Kalender-Vorschau")
        self.resize(800, 440)
        layout = QVBoxLayout(self)
        heading = QLabel(title)
        heading.setTextFormat(Qt.TextFormat.PlainText)
        heading.setWordWrap(True)
        layout.addWidget(heading)
        layout.addWidget(QLabel("Vorschau: Freie Terminvorschläge. Eintrag erst nach gesonderter Freigabe."))
        row = QHBoxLayout()
        self.calendar = QCalendarWidget()
        from desktop.i18n import i18n
        self.calendar.setLocale(QLocale("de_DE" if i18n.language == "de" else "en_GB"))
        self.calendar.setFirstDayOfWeek(Qt.DayOfWeek.Monday)
        row.addWidget(self.calendar)
        self.agenda = QTableWidget(0, 2)
        self.agenda.setHorizontalHeaderLabels(["Beginn", "Ende"])
        self.agenda.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.agenda.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.agenda.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.agenda.horizontalHeader().setStretchLastSection(True)
        row.addWidget(self.agenda, 1)
        layout.addLayout(row)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Diesen Vorschlag auswählen")
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Abbrechen")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        mark = QTextCharFormat()
        mark.setBackground(QColor("#b8e8df"))
        mark.setForeground(QColor("#123d36"))
        mark.setToolTip("Freier Terminvorschlag – noch nicht eingetragen")
        for slot in self.slots:
            self.calendar.setDateTextFormat(QDate(slot.start.year, slot.start.month, slot.start.day), mark)
        self.calendar.selectionChanged.connect(self._render_day)
        self.agenda.itemSelectionChanged.connect(self._select)
        if self.slots:
            first = self.slots[0].start
            self.calendar.setSelectedDate(QDate(first.year, first.month, first.day))
        self._render_day()

    def _render_day(self):
        self.selected_index = None
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        day = self.calendar.selectedDate()
        self.agenda.setRowCount(0)
        for index, slot in enumerate(self.slots):
            if (slot.start.year, slot.start.month, slot.start.day) != (day.year(), day.month(), day.day()):
                continue
            row = self.agenda.rowCount()
            self.agenda.insertRow(row)
            start = QTableWidgetItem(human_slot(slot.start.isoformat()))
            start.setData(Qt.ItemDataRole.UserRole, index)
            self.agenda.setItem(row, 0, start)
            self.agenda.setItem(row, 1, QTableWidgetItem(slot.end.strftime("%H:%M Uhr")))
        self.agenda.resizeColumnsToContents()
        if self.agenda.rowCount():
            self.agenda.selectRow(0)

    def _select(self):
        item = self.agenda.item(self.agenda.currentRow(), 0)
        self.selected_index = item.data(Qt.ItemDataRole.UserRole) if item else None
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(self.selected_index is not None)
