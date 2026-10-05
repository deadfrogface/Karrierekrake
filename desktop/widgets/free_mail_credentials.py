"""Presets for free mailbox access; passwords leave the dialog only on approval."""
from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QVBoxLayout


class FreeMailCredentialsDialog(QDialog):
    PRESETS = (
        ('Gmail', 'imap.gmail.com', 'Google-App-Passwort: zweistufige Bestätigung erforderlich. Falls nicht verfügbar: EML/MBOX importieren.'),
        ('WEB.DE', 'imap.web.de', 'IMAP im WEB.DE-Konto aktivieren; bei 2FA ein anwendungsspezifisches Passwort verwenden.'),
        ('T-Online', 'secureimap.t-online.de', 'Das separate Passwort für E-Mail-Programme verwenden, nicht das Telekom-Login-Passwort.'),
        ('Outlook.com', 'outlook.office365.com', 'Outlook benötigt OAuth. Kostenlose IMAP-Anmeldung mit einer registrierten Microsoft-Desktop-App; alternativ EML/MBOX importieren.'),
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(480)
        self.setWindowTitle('E-Mail kostenlos verbinden')
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.provider = QComboBox()
        self.provider.addItems([p[0] for p in self.PRESETS])
        self.username = QLineEdit()
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.client_id = QLineEdit()
        form.addRow('Anbieter', self.provider)
        form.addRow('E-Mail-Adresse', self.username)
        self.password_label = QLabel('App-/E-Mail-Programm-Passwort')
        form.addRow(self.password_label, self.password)
        self.client_label = QLabel('Microsoft Desktop-Client-ID')
        form.addRow(self.client_label, self.client_id)
        layout.addLayout(form)
        self.hint = QLabel()
        self.hint.setWordWrap(True)
        self.hint.setOpenExternalLinks(True)
        layout.addWidget(self.hint)
        layout.addWidget(QLabel('Ein Postfach gleichzeitig. Nachrichten werden nur gelesen und lokal sortiert.'))
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.provider.currentIndexChanged.connect(self._update)
        for field in (self.username, self.password, self.client_id):
            field.textChanged.connect(self._validate)
        self._update()

    def _update(self):
        outlook = self.provider.currentIndex() == 3
        for widget in (self.client_label, self.client_id):
            widget.setVisible(outlook)
        for widget in (self.password_label, self.password):
            widget.setVisible(not outlook)
        text = self.PRESETS[self.provider.currentIndex()][2]
        if self.provider.currentIndex() == 0:
            text += ' <a href="https://myaccount.google.com/apppasswords">Google-App-Passwort erstellen</a> (16 Zeichen; kein normales Google-Passwort).'
        self.hint.setText(text)
        self._validate()

    def _validate(self):
        credential = self.client_id.text().strip() if self.provider.currentIndex() == 3 else self.password.text()
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(bool(self.username.text().strip() and credential))

    def credentials(self):
        index = self.provider.currentIndex()
        secret = dict(host=self.PRESETS[index][1], port=993, use_ssl=True, username=self.username.text().strip())
        if index == 3:
            secret.update(oauth2=True, client_id=self.client_id.text().strip())
        else:
            secret['password'] = self.password.text()
        self.password.clear()
        return secret
