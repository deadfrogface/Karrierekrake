"""Credential dialogs shared by settings and onboarding.

Hosts provide config_service, provider combos and an asynchronous _run_account_task.
"""

from pathlib import Path
from PySide6.QtWidgets import QDialog, QFileDialog, QInputDialog, QMessageBox


class AccountConnectionsMixin:
    def _connect_free_mail(self):
        from desktop.widgets.free_mail_credentials import FreeMailCredentialsDialog

        dialog = FreeMailCredentialsDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        secret = dialog.credentials()
        token_dir = self.config_service.dirs["config"]

        def connect():
            from integrations.mail.imap.adapter import (
                validate_imap_secret,
                store_imap_secret,
            )

            if secret.get("oauth2"):
                from integrations.mail.imap.outlook_auth import login_outlook

                login_outlook(secret)
            validate_imap_secret(secret)
            store_imap_secret(secret, token_dir=token_dir)

        def finished(_):
            from integrations.providers.connection_probe import clear_probe_cache

            cfg = self.config_service.load()
            cfg.settings.mail_provider = "generic_imap"
            cfg.settings.gmail_sync_enabled = False
            self.config_service.save(cfg)
            clear_probe_cache("generic_imap")
            self.mail_provider.setCurrentIndex(
                self.mail_provider.findData("generic_imap")
            )
            QMessageBox.information(
                self,
                "Kostenloser Sortierer",
                "Postfach verbunden. Im Posteingang auf Aktualisieren klicken. Nachrichten werden nur gelesen und lokal sortiert.",
            )

        self._run_account_task(connect, finished, cleanup=secret.clear)

    def _connect_icloud(self):
        from desktop.widgets.provider_credentials import ProviderCredentialsDialog

        dialog = ProviderCredentialsDialog(calendar=True, parent=self)
        dialog.setWindowTitle("Apple / iCloud verbinden")
        dialog.server.setText("https://caldav.icloud.com/")
        dialog.server.setReadOnly(True)
        dialog.username.setPlaceholderText("Apple-ID")
        dialog.password.setPlaceholderText(
            "Anwendungsspezifisches Apple-Passwort (2FA)"
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        secret = dialog.credentials()
        allow_write = dialog.allow_write.isChecked()
        token_dir = self.config_service.dirs["config"]

        def verify():
            from integrations.calendar.caldav.client import LiveCaldavClient

            return LiveCaldavClient(secret).discover_calendars()

        def finished(calendars):
            from integrations.calendar.caldav.adapter import store_caldav_secret
            from integrations.providers.connection_probe import clear_probe_cache

            selected, ok = QInputDialog.getItem(
                self, "iCloud-Kalender", "Kalender auswählen", calendars, 0, False
            )
            if not ok:
                return
            secret["calendar_path"] = selected
            store_caldav_secret(secret, token_dir=token_dir)
            cfg = self.config_service.load()
            cfg.settings.calendar_provider = "generic_caldav"
            cfg.settings.allow_calendar_write = allow_write
            cfg.settings.calendar_freebusy_enabled = True
            self.config_service.save(cfg)
            self.calendar_provider.setCurrentIndex(
                self.calendar_provider.findData("generic_caldav")
            )
            clear_probe_cache("generic_caldav")
            QMessageBox.information(
                self,
                "Apple / iCloud",
                "Kalender verbunden. Schreiben erfordert weiterhin Ihre ausdrückliche Freigabe.",
            )

        self._run_account_task(verify, finished, cleanup=secret.clear)

    def _connect_private_ics_feed(self):
        from PySide6.QtWidgets import QInputDialog

        url, ok = QInputDialog.getText(
            self,
            "Privaten ICS-Kalender abonnieren",
            "Privaten HTTPS-iCal-Link einfügen (nur Lesen, wie ein Passwort behandeln):",
        )
        if not ok or not url.strip():
            return
        url = url.strip()
        destination = self.config_service.dirs["cache"] / "calendar-snapshot.ics"

        def prepare():
            from integrations.calendar.local_ics import refresh_private_ics

            return refresh_private_ics(url, destination)

        def finished(_):
            cfg = self.config_service.load()
            cfg.settings.local_calendar_path = str(destination)
            cfg.settings.local_calendar_feed_url = url
            cfg.settings.calendar_provider = "local_ics"
            cfg.settings.calendar_freebusy_enabled = True
            self.config_service.save(cfg)
            self.calendar_provider.setCurrentIndex(
                self.calendar_provider.findData("local_ics")
            )
            QMessageBox.information(
                self,
                "Kalender abonniert",
                "Privater ICS-Kalender verbunden (nur Lesen). Er wird bei Bedarf "
                "spätestens nach sechs Stunden erneut abgerufen. Keine Google API.",
            )

        self._run_account_task(prepare, finished)

    def _import_calendar_snapshot(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Google / Samsung / Apple: Kalenderdatei",
            "",
            "Kalenderdateien (*.ics)",
        )
        if not path:
            # Cancelling file selection must not unexpectedly open another dialog.
            return
        destination = self.config_service.dirs["cache"] / "calendar-snapshot.ics"

        def prepare():
            from integrations.calendar.local_ics import read_calendar

            return read_calendar(path).to_ical()

        def finished(data):
            import os
            from datetime import datetime

            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_suffix(".tmp")
            temporary.write_bytes(data)
            os.replace(temporary, destination)
            cfg = self.config_service.load()
            cfg.settings.local_calendar_path = str(destination)
            cfg.settings.local_calendar_feed_url = ""
            cfg.settings.calendar_provider = "local_ics"
            cfg.settings.calendar_freebusy_enabled = True
            self.config_service.save(cfg)
            self.calendar_provider.setCurrentIndex(
                self.calendar_provider.findData("local_ics")
            )
            QMessageBox.information(
                self,
                "Kalenderkopie importiert",
                "Stand: "
                + datetime.now().strftime("%d.%m.%Y %H:%M")
                + "\nKeine Live-Synchronisation. Nach Kalenderänderungen neu importieren; spätestens nach sieben Tagen.\nSamsung: den zugrunde liegenden Google-/anderen Kalender exportieren. Termine nur auf dem Telefon sind hier nicht automatisch verfügbar.",
            )

        self._run_account_task(prepare, finished)
