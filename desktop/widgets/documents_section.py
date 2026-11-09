"""Profile section for Arbeitszeugnisse, certificates and other files that go out with an application."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from desktop.i18n import i18n

_KIND_LABEL = {"zeugnis": ("Arbeitszeugnis", "Reference letter"), "zertifikat": ("Zertifikat", "Certificate"),
               "sonstiges": ("Dokument", "Document")}


def _t(de: str, en: str) -> str:
    return en if i18n.language == "en" else de


class DocumentsSection(QGroupBox):
    changed = Signal()

    def __init__(self, config_service, parent=None) -> None:
        super().__init__(_t("Zeugnisse und weitere Unterlagen", "References and other documents"), parent)
        self.config_service = config_service
        self.hint = QLabel(_t(
            "Diese Dateien gehen mit jeder Bewerbung mit, wenn das Formular es zulässt. Aus Zeugnissen und "
            "Zertifikaten übernimmt Karrierekrake Aufgaben, Software und Zertifikate in dein Profil – nur, was dort steht.",
            "These files go out with every application when the form allows it. From references and certificates "
            "Karrierekrake adds tasks, software and certificates to your profile – only what is written there."))
        self.hint.setWordWrap(True)
        self.hint.setObjectName("Muted")
        self.list = QListWidget()
        self.list.setMaximumHeight(150)
        self.add_btn = QPushButton(_t("Dokument hinzufügen …", "Add document …"))
        self.remove_btn = QPushButton(_t("Entfernen", "Remove"))
        self.remove_btn.setObjectName("SecondaryButton")
        self.result = QLabel()
        self.result.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.addWidget(self.hint)
        layout.addWidget(self.list)
        row = QHBoxLayout()
        row.addWidget(self.add_btn)
        row.addWidget(self.remove_btn)
        row.addStretch()
        layout.addLayout(row)
        layout.addWidget(self.result)
        self.add_btn.clicked.connect(self.add_documents)
        self.remove_btn.clicked.connect(self.remove_selected)
        self.list.itemChanged.connect(self._on_item_changed)
        self.reload()

    def reload(self) -> None:
        self.list.blockSignals(True)
        self.list.clear()
        for doc in self.config_service.extra_documents():
            kind = _KIND_LABEL.get(str(doc.get("kind") or "sonstiges"), _KIND_LABEL["sonstiges"])
            item = QListWidgetItem(f"{_t(*kind)} · {Path(doc['path']).name}"
                                   + _t("  (mit Bewerbung senden)", "  (send with application)"))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if doc.get("send", True) else Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, doc["id"])
            self.list.addItem(item)
        self.list.blockSignals(False)
        self.remove_btn.setEnabled(self.list.count() > 0)

    def add_documents(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, _t("Dokumente auswählen", "Choose documents"), "",
            _t("Dokumente (*.pdf *.docx *.doc *.txt)", "Documents (*.pdf *.docx *.doc *.txt)"))
        notes: list[str] = []
        for path in paths:
            try:
                entry, changes = self.config_service.add_extra_document(Path(path))
            except Exception as exc:  # noqa: BLE001 - show it, keep the other files
                QMessageBox.warning(self, _t("Dokument", "Document"), f"{Path(path).name}: {exc}")
                continue
            notes.extend(changes)
        self.reload()
        if notes:
            self.result.setText("\n".join(f"• {n}" for n in notes[:8]))
            self.changed.emit()
        elif paths:
            self.result.setText(_t("Hinzugefügt. Daraus ließ sich nichts Neues für dein Profil lesen.",
                                   "Added. Nothing new for your profile could be read from it."))

    def remove_selected(self) -> None:
        item = self.list.currentItem()
        if item is not None:
            self.config_service.remove_document(str(item.data(Qt.ItemDataRole.UserRole)))
            self.reload()

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        self.config_service.set_document_send(
            str(item.data(Qt.ItemDataRole.UserRole)), item.checkState() == Qt.CheckState.Checked)
