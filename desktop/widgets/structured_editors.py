"""Structured profile editors (languages, education, experience, certificates)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.config import (
    CertificateEntry,
    EducationEntry,
    ExperienceEntry,
    LanguageEntry,
)
from desktop.i18n import tr
from desktop.services.profile_merge import SOURCE_MANUAL
from desktop.widgets.dialog_geometry import fit_dialog_to_screen


def _run_entry_dialog(dlg: QDialog, *, preferred_width: int = 480, preferred_height: int = 420) -> int:
    fit_dialog_to_screen(dlg, preferred_width=preferred_width, preferred_height=preferred_height)
    return int(dlg.exec())


class _EntryListEditor(QWidget):
    """List with add/edit/remove opening a dialog."""

    def __init__(self, empty_hint: str, parent=None, *, visible_rows: int = 3) -> None:
        super().__init__(parent)
        self._hint = empty_hint
        self.hint_label = QLabel(empty_hint)
        self.list = QListWidget()
        self.list.setMinimumHeight(22 * max(2, visible_rows))
        self.list.setMaximumHeight(22 * max(3, visible_rows) + 8)
        self.list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._items: list = []
        self.add_btn = QPushButton()
        self.edit_btn = QPushButton()
        self.remove_btn = QPushButton()
        for b in (self.add_btn, self.edit_btn, self.remove_btn):
            b.setObjectName("SecondaryButton")
        self.add_btn.clicked.connect(self._add)
        self.edit_btn.clicked.connect(self._edit)
        self.remove_btn.clicked.connect(self._remove)
        self.retranslate()
        row = QHBoxLayout()
        row.addWidget(self.add_btn)
        row.addWidget(self.edit_btn)
        row.addWidget(self.remove_btn)
        row.addStretch()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self.hint_label)
        layout.addWidget(self.list)
        layout.addLayout(row)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def retranslate(self) -> None:
        self.add_btn.setText(tr("btn.add"))
        self.edit_btn.setText(tr("btn.edit"))
        self.remove_btn.setText(tr("btn.remove"))


    def _refresh(self) -> None:
        self.list.clear()
        for item in self._items:
            self.list.addItem(item.label() if hasattr(item, "label") else str(item))

    def _add(self) -> None:
        item = self.create_item()
        if item is None:
            return
        self._items.append(item)
        self._refresh()

    def _edit(self) -> None:
        row = self.list.currentRow()
        if row < 0 or row >= len(self._items):
            return
        item = self.edit_item(self._items[row])
        if item is None:
            return
        self._items[row] = item
        self._refresh()

    def _remove(self) -> None:
        row = self.list.currentRow()
        if row < 0:
            return
        self._items.pop(row)
        self._refresh()

    def create_item(self):
        raise NotImplementedError

    def edit_item(self, existing):
        raise NotImplementedError

    def get_items(self) -> list:
        return list(self._items)

    def set_items(self, items: list | None) -> None:
        self._items = list(items or [])
        self._refresh()


class LanguageEditor(_EntryListEditor):
    def __init__(self, parent=None) -> None:
        super().__init__("Sprache und Niveau (z. B. Englisch | C1)", parent)

    def create_item(self):
        return self._dialog()

    def edit_item(self, existing: LanguageEntry):
        return self._dialog(existing)

    def _dialog(self, existing: LanguageEntry | None = None) -> LanguageEntry | None:
        dlg = QDialog(self)
        dlg.setWindowTitle("Sprache")
        lang = QLineEdit(existing.language if existing else "")
        level = QLineEdit(existing.level if existing else "")
        level.setPlaceholderText("C1 / C2 / B2 …")
        form = QFormLayout()
        form.addRow("Sprache", lang)
        form.addRow("Niveau", level)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout = QVBoxLayout(dlg)
        layout.addLayout(form)
        layout.addWidget(buttons)
        if _run_entry_dialog(dlg, preferred_width=420, preferred_height=260) != QDialog.DialogCode.Accepted:
            return None
        if not lang.text().strip():
            return None
        return LanguageEntry(language=lang.text().strip(), level=level.text().strip())


class EducationEditor(_EntryListEditor):
    def __init__(self, parent=None) -> None:
        super().__init__("Ausbildung / Schule", parent)

    def create_item(self):
        return self._dialog()

    def edit_item(self, existing: EducationEntry):
        return self._dialog(existing)

    def _dialog(self, existing: EducationEntry | None = None) -> EducationEntry | None:
        dlg = QDialog(self)
        dlg.setWindowTitle("Ausbildung")
        fields = {
            "qualification": QLineEdit(existing.qualification if existing else ""),
            "institution": QLineEdit(existing.institution if existing else ""),
            "location": QLineEdit(existing.location if existing else ""),
            "start_date": QLineEdit(existing.start_date if existing else ""),
            "end_date": QLineEdit(existing.end_date if existing else ""),
            "completion_date": QLineEdit(existing.completion_date if existing else ""),
        }
        form = QFormLayout()
        form.addRow("Abschluss / Qualifikation", fields["qualification"])
        form.addRow("Einrichtung / Firma", fields["institution"])
        form.addRow("Ort", fields["location"])
        form.addRow("Beginn", fields["start_date"])
        form.addRow("Ende", fields["end_date"])
        form.addRow("Abschlussdatum", fields["completion_date"])
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout = QVBoxLayout(dlg)
        layout.addLayout(form)
        layout.addWidget(buttons)
        if _run_entry_dialog(dlg, preferred_width=520, preferred_height=420) != QDialog.DialogCode.Accepted:
            return None
        entry = EducationEntry(**{k: w.text().strip() for k, w in fields.items()})
        entry.source = (existing.source if existing and existing.source else SOURCE_MANUAL)
        if not entry.qualification and not entry.institution:
            return None
        return entry


class ExperienceEditor(_EntryListEditor):
    def __init__(self, parent=None) -> None:
        super().__init__("Berufserfahrung", parent)

    def create_item(self):
        return self._dialog()

    def edit_item(self, existing: ExperienceEntry):
        return self._dialog(existing)

    def _dialog(self, existing: ExperienceEntry | None = None) -> ExperienceEntry | None:
        dlg = QDialog(self)
        dlg.setWindowTitle("Berufserfahrung")
        title = QLineEdit(existing.title if existing else "")
        company = QLineEdit(existing.company if existing else "")
        location = QLineEdit(existing.location if existing else "")
        start = QLineEdit(existing.start_date if existing else "")
        end = QLineEdit(existing.end_date if existing else "")
        resp = QPlainTextEdit()
        if existing:
            resp.setPlainText("\n".join(existing.responsibilities))
        resp.setPlaceholderText("Eine Aufgabe pro Zeile")
        resp.setMinimumHeight(120)
        form = QFormLayout()
        form.addRow("Position", title)
        form.addRow("Firma", company)
        form.addRow("Ort", location)
        form.addRow("Beginn", start)
        form.addRow("Ende / aktuell", end)
        form.addRow("Aufgaben", resp)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout = QVBoxLayout(dlg)
        layout.addLayout(form)
        layout.addWidget(buttons)
        if _run_entry_dialog(dlg, preferred_width=560, preferred_height=560) != QDialog.DialogCode.Accepted:
            return None
        responsibilities = [
            ln.strip(" -•\t")
            for ln in resp.toPlainText().splitlines()
            if ln.strip()
        ]
        entry = ExperienceEntry(
            title=title.text().strip(),
            company=company.text().strip(),
            location=location.text().strip(),
            start_date=start.text().strip(),
            end_date=end.text().strip(),
            responsibilities=responsibilities,
            source=(existing.source if existing and existing.source else SOURCE_MANUAL),
        )
        if not entry.title and not entry.company:
            return None
        return entry


class CertificateEditor(_EntryListEditor):
    def __init__(self, parent=None) -> None:
        super().__init__("Zertifikate / Weiterbildungen", parent)

    def create_item(self):
        return self._dialog()

    def edit_item(self, existing: CertificateEntry):
        return self._dialog(existing)

    def _dialog(self, existing: CertificateEntry | None = None) -> CertificateEntry | None:
        dlg = QDialog(self)
        dlg.setWindowTitle("Zertifikat / Weiterbildung")
        name = QLineEdit(existing.name if existing else "")
        issuer = QLineEdit(existing.issuer if existing else "")
        date = QLineEdit(existing.date if existing else "")
        form = QFormLayout()
        form.addRow("Bezeichnung", name)
        form.addRow("Anbieter", issuer)
        form.addRow("Datum", date)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout = QVBoxLayout(dlg)
        layout.addLayout(form)
        layout.addWidget(buttons)
        if _run_entry_dialog(dlg, preferred_width=480, preferred_height=300) != QDialog.DialogCode.Accepted:
            return None
        if not name.text().strip():
            return None
        return CertificateEntry(
            name=name.text().strip(),
            issuer=issuer.text().strip(),
            date=date.text().strip(),
            source=(existing.source if existing and existing.source else SOURCE_MANUAL),
        )
