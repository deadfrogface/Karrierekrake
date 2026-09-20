"""Reusable list editor widget (add/remove string items)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from desktop.i18n import tr
from desktop.design_system.a11y import annotate_list_editor


class ListEditor(QWidget):
    def __init__(
        self,
        placeholder: str = "",
        parent=None,
        *,
        visible_rows: int = 3,
        accessible_list_name: str = "",
    ) -> None:
        super().__init__(parent)
        self._placeholder_key_or_text = placeholder
        self._accessible_list_name = accessible_list_name
        self.list = QListWidget()
        self.list.setMinimumHeight(22 * max(2, visible_rows))
        self.list.setMaximumHeight(22 * max(3, visible_rows) + 8)
        self.list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.input = QLineEdit()
        self._set_placeholder(placeholder)
        self.add_btn = QPushButton()
        self.remove_btn = QPushButton()
        self.add_btn.setObjectName("SecondaryButton")
        self.remove_btn.setObjectName("SecondaryButton")
        self.add_btn.clicked.connect(self._add)
        self.remove_btn.clicked.connect(self._remove)
        self.input.returnPressed.connect(self._add)
        self.retranslate()

        row = QHBoxLayout()
        row.addWidget(self.input, 1)
        row.addWidget(self.add_btn)
        row.addWidget(self.remove_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self.list)
        layout.addLayout(row)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._apply_a11y()

    def _apply_a11y(self) -> None:
        annotate_list_editor(
            list_widget=self.list,
            input_widget=self.input,
            add_button=self.add_btn,
            remove_button=self.remove_btn,
            list_name=self._accessible_list_name or tr("a11y.list_editor"),
            input_name=self.input.placeholderText() or tr("placeholder.add_entry"),
        )

    def _set_placeholder(self, text: str) -> None:
        self.input.setPlaceholderText(text or tr("placeholder.add_entry"))

    def retranslate(self) -> None:
        self.add_btn.setText(tr("btn.add"))
        self.remove_btn.setText(tr("btn.remove"))
        # If placeholder looks like a translation key, resolve it
        ph = self._placeholder_key_or_text
        if ph.startswith("placeholder.") or ph.startswith("profile."):
            self._set_placeholder(tr(ph))
        elif not ph:
            self._set_placeholder(tr("placeholder.add_entry"))
        else:
            self._set_placeholder(ph)
        if hasattr(self, "list"):
            self._apply_a11y()

    def _add(self) -> None:
        text = self.input.text().strip()
        if not text:
            return
        self.list.addItem(text)
        self.input.clear()

    def _remove(self) -> None:
        for item in self.list.selectedItems():
            self.list.takeItem(self.list.row(item))

    def get_items(self) -> list[str]:
        return [self.list.item(i).text() for i in range(self.list.count())]

    def set_items(self, items: list[str] | None) -> None:
        self.list.clear()
        for item in items or []:
            if item:
                self.list.addItem(str(item))
