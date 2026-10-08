"""Small offline provider catalogue and safe local HTML setup guides."""
from __future__ import annotations

from html import escape

PROVIDERS = {
    "gmx": ("GMX", "IMAP/SMTP", "CalDAV", "Öffne die GMX-Einstellungen und aktiviere IMAP/POP3-Zugriff.", "Richte ein separates Mail-Passwort ein, falls dein Konto es verlangt."),
    "webde": ("WEB.DE", "IMAP/SMTP", "CalDAV", "Aktiviere den Zugriff über IMAP/POP3 in den WEB.DE-Einstellungen.", "Erstelle bei Bedarf ein anwendungsspezifisches Passwort."),
    "google": ("Google / Gmail", "OAuth2 oder unterstütztes App-Passwort", "Google Calendar OAuth oder ICS (nur Lesen)", "Prüfe die Google-Kontosicherheit und wähle eine vom Konto unterstützte Anmeldemethode.", "Für direkte Kalendersynchronisierung benötigt KarriereKrake eine freigegebene OAuth-Verbindung."),
    "microsoft": ("Outlook / Hotmail / Microsoft 365", "OAuth2", "Microsoft Graph oder ICS (nur Lesen)", "Melde dich über die offizielle Microsoft-Anmeldung an; ein normales Passwort in IMAP reicht häufig nicht.", "Bei Firmenkonten kann eine Administratorfreigabe notwendig sein."),
    "icloud": ("Apple / iCloud", "IMAP/SMTP", "CalDAV", "Aktiviere Zwei-Faktor-Authentifizierung für deinen Apple Account.", "Erstelle ein anwendungsspezifisches Passwort für kompatible Drittanbieter-Apps."),
    "t-online": ("Telekom / T-Online", "IMAP/SMTP", "ICS falls angeboten", "Erstelle im Telekom-Konto ein separates E-Mail-Passwort.", "Trage dieses Passwort im Verbindungsdialog ein."),
    "yahoo": ("Yahoo Mail", "IMAP/SMTP", "ICS falls angeboten", "Prüfe die verfügbaren Anmeldemethoden in den Yahoo-Kontosicherheitseinstellungen.", "Verwende eine vom Konto unterstützte App-Authentifizierung."),
    "freenet": ("freenet Mail", "IMAP/SMTP", "ICS falls angeboten", "Prüfe, ob IMAP in deinem Tarif und Konto verfügbar ist.", "Aktiviere bei Bedarf den externen Zugriff."),
    "other": ("Anderer Anbieter", "IMAP/SMTP falls unterstützt", "CalDAV/ICS falls unterstützt", "Prüfe die offiziellen IMAP-, SMTP- und Kalender-Einstellungen des Anbieters.", "Nutze nur offizielle Serveradressen und unterstützte Anmeldemethoden."),
}


def guide_html(provider: str, service: str = "both") -> str:
    if provider not in PROVIDERS:
        raise ValueError("Unbekannter Anbieter")
    if service not in ("mail", "calendar", "both"):
        raise ValueError("Unbekannter Dienst")
    name, mail, calendar, first, second = PROVIDERS[provider]
    steps = [
        f"Öffne die offiziellen Kontoeinstellungen von {name}.",
        first,
        second,
        "Öffne KarriereKrake → Einstellungen → Integrationen und wähle den Anbieter.",
        "Verbinde das Konto und führe einen Lese-Verbindungstest durch.",
        "Aktiviere Schreibzugriff nur nach ausdrücklicher Freigabe. Teste das Anlegen eines Termins oder den E-Mail-Versand separat.",
    ]
    rows = "".join(f"<li>{escape(step)}</li>" for step in steps)
    capabilities = []
    if service in ("mail", "both"):
        capabilities.append(f"<p><b>E-Mail:</b> {escape(mail)}</p>")
    if service in ("calendar", "both"):
        capabilities.append(f"<p><b>Kalender:</b> {escape(calendar)}</p>")
    return ('<!doctype html><html lang="de"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<style>body{font:16px system-ui;max-width:760px;margin:3rem auto;padding:0 1rem;line-height:1.65}'
            'li{margin:0.8rem 0}aside{background:#f2f3f5;padding:1rem;border-radius:8px}</style></head><body>'
            f'<h1>Wie richte ich {escape(name)} in KarriereKrake ein?</h1>'
            + "".join(capabilities) + f'<ol>{rows}</ol>'
            '<aside><b>Legende:</b> IMAP = E-Mails lesen; SMTP = E-Mails senden; '
            'CalDAV = Kalender synchronisieren; ICS = Kalenderdatei, häufig nur Import/Lesen; '
            'OAuth = sichere Anmeldung über den Anbieter.</aside>'
            '<p><b>Hinweis:</b> Diese Anleitung beschreibt mögliche Verbindungswege, '
            'keinen bestätigten Live-Test. Einzelne Konten und Tarife können abweichen.</p></body></html>')
