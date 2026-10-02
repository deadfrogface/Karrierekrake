"""Credential entry for standard IMAP and CalDAV accounts; never persists secrets."""
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QLabel, QVBoxLayout
from desktop.i18n import tr


class ProviderCredentialsDialog(QDialog):
    def __init__(self, *, calendar: bool, parent=None):
        super().__init__(parent)
        self.calendar = calendar
        self.setWindowTitle(tr("integrations.connect_caldav" if calendar else "integrations.connect_imap"))
        layout = QVBoxLayout(self)
        hint = QLabel(tr("integrations.credentials_hint"))
        hint.setWordWrap(True)
        layout.addWidget(hint)
        form = QFormLayout()
        self.server = QLineEdit()
        self.server.setPlaceholderText("https://calendar.example.org/" if calendar else "imap.example.org")
        self.username = QLineEdit()
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow(tr("integrations.server"), self.server)
        form.addRow(tr("integrations.username"), self.username)
        form.addRow(tr("integrations.password"), self.password)
        layout.addLayout(form)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        for field in (self.server, self.username, self.password):
            field.textChanged.connect(self._validate)
        self._validate()

    def _validate(self):
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(
            bool(self.server.text().strip() and self.username.text().strip() and self.password.text()))

    def credentials(self):
        result = {"username": self.username.text().strip(), "password": self.password.text()}
        result["base_url" if self.calendar else "host"] = self.server.text().strip()
        if not self.calendar:
            result.update(port=993, use_ssl=True)
        self.password.clear()
        return result
