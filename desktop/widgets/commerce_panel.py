"""Offline license import and explicit browser handoff; no merchant credentials."""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from PySide6.QtCore import Qt, QUrl, Signal, QTimer
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QCheckBox, QFileDialog, QGroupBox, QLabel, QMessageBox, QPushButton, QVBoxLayout
from core.commercial import sponsors
from core.commercial.license_file import current_license, import_license, license_path
from core.commercial.release_policy import load_policy, public_url
from desktop.widgets.confirm_dialog import confirm_action


class CommercePanel(QGroupBox):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__('Lizenz und Partnerhinweise', parent)
        layout = QVBoxLayout(self)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.status)
        self.import_button = QPushButton('Signierte Lizenzdatei importieren …')
        self.import_button.clicked.connect(self.import_file)
        layout.addWidget(self.import_button)
        self.remove_button = QPushButton('Lokale Lizenz entfernen …')
        self.remove_button.clicked.connect(self.remove_file)
        layout.addWidget(self.remove_button)
        self.links = {}
        for name, label in [('checkout_url', 'Angebot und Preis ansehen'),
                            ('customer_portal_url', 'Rechnungen und Zahlungsdaten verwalten'),
                            ('cancellation_url', 'Verträge hier kündigen'),
                            ('withdrawal_url', 'Vertrag widerrufen'),
                            ('terms_url', 'Vertragsbedingungen ansehen'),
                            ('privacy_url', 'Datenschutzinformationen ansehen')]:
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, key=name: self.open_link(key))
            self.links[name] = button
            layout.addWidget(button)
        self.ads = QCheckBox('Lokalen Partnerhinweis anzeigen (freiwillig, ohne Tracking)')
        self.ads.setAccessibleDescription('Keine Verbindung zum Werbepartner, solange Sie dessen Website nicht selbst öffnen. Jederzeit abwählbar.')
        self.ads.toggled.connect(self.change_consent)
        layout.addWidget(self.ads)
        self.refresh()
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(60_000)
        self.refresh_timer.timeout.connect(self.refresh)
        self.refresh_timer.start()

    def refresh(self):
        try:
            policy = load_policy()
        except (OSError, ValueError, TypeError):
            policy = {}
        license = current_license(policy=policy) if policy else None
        if license:
            end = datetime.fromtimestamp(license['expires_at'], timezone.utc).strftime('%d.%m.%Y %H:%M UTC')
            features = ', '.join(license['features']) or 'Keine Premiumberechtigung'
            mode = 'Testlizenz (keine Produktivfreischaltung)' if policy.get('environment') == 'sandbox' else 'Lizenz'
            self.status.setText(f'{mode} · gültig bis {end}\n{features}')
        else:
            self.status.setText('Kostenlose lokale Basis aktiv. Keine gültige Premiumlizenz installiert.')
        self.remove_button.setEnabled(license_path().exists())
        for name, button in self.links.items():
            enabled = bool(policy.get(name))
            if name == 'checkout_url':
                enabled = enabled and policy.get('sales_enabled') is True
            button.setEnabled(enabled)
        value = sponsors.campaign()
        self.ads.blockSignals(True)
        self.ads.setEnabled(value is not None)
        self.ads.setChecked(bool(value and sponsors.consented(value)))
        self.ads.blockSignals(False)

    def import_file(self):
        filename, _ = QFileDialog.getOpenFileName(self, 'Lizenz importieren', '', 'Lizenzdatei (*.json)')
        if not filename:
            return
        try:
            import_license(Path(filename))
        except (OSError, ValueError, TypeError):
            QMessageBox.warning(self, 'Lizenz nicht übernommen', 'Signatur, Gültigkeitszeitraum oder Lizenzstand ist ungültig. Ihre bisherige Lizenz bleibt erhalten.')
            return
        self.refresh(); self.changed.emit()

    def remove_file(self):
        if not confirm_action(self, 'Lokale Lizenz entfernen', 'Die kostenlose Basis bleibt nutzbar. Ein bestehender Vertrag wird dadurch nicht gekündigt.', confirm_text='Lizenz entfernen'):
            return
        try:
            license_path().unlink(missing_ok=True)
        except OSError:
            QMessageBox.warning(self, 'Lizenz', 'Die lokale Lizenz konnte nicht entfernt werden.')
        self.refresh(); self.changed.emit()

    def open_link(self, name):
        try:
            policy = load_policy()
            if name == 'checkout_url' and policy.get('sales_enabled') is not True:
                return
            url = public_url(policy[name])
        except (KeyError, OSError, ValueError, TypeError):
            QMessageBox.warning(self, 'Verbindung', 'Dieser Anbieterweg ist noch nicht eingerichtet.')
            return
        if confirm_action(self, 'Externe Anbieterwebsite', 'Im Browser wird die eingerichtete Anbieterwebsite geöffnet. Erst dort führen Sie eine Bestellung, Verwaltung oder Kündigung aus.', confirm_text='Website öffnen'):
            if not QDesktopServices.openUrl(QUrl(url)):
                QMessageBox.warning(self, 'Verbindung', 'Der Browser konnte nicht geöffnet werden.')

    def change_consent(self, allowed):
        try:
            sponsors.set_consent(allowed)
        except (OSError, ValueError):
            QMessageBox.warning(self, 'Partnerhinweis', 'Die Einstellung konnte nicht gespeichert werden.')
        self.refresh(); self.changed.emit()


class SponsorBanner(QGroupBox):
    def __init__(self, parent=None):
        super().__init__('Anzeige', parent)
        layout = QVBoxLayout(self)
        self.text = QLabel()
        self.text.setTextFormat(Qt.TextFormat.PlainText)
        self.text.setWordWrap(True)
        layout.addWidget(self.text)
        self.button = QPushButton('Website des Werbepartners öffnen …')
        self.button.clicked.connect(self.open_partner)
        layout.addWidget(self.button)
        self.refresh()
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(60_000)
        self.refresh_timer.timeout.connect(self.refresh)
        self.refresh_timer.start()

    def refresh(self):
        value = sponsors.visible_campaign()
        self.setVisible(value is not None)
        if value:
            self.text.setText(f"{value['advertiser']} · {value['title']}\n{value['body']}")

    def open_partner(self):
        value = sponsors.visible_campaign()
        if value and confirm_action(self, 'Werbepartner besuchen', 'Beim Öffnen der externen Website gelten die Datenschutzinformationen des Werbepartners.', confirm_text='Website öffnen'):
            QDesktopServices.openUrl(QUrl(public_url(value['url'])))
