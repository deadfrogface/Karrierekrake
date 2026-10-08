"""Documented provider mail endpoints, not proof of live account access."""
MAIL_ENDPOINTS = {
    "gmx": ("imap.gmx.net", 993, "mail.gmx.net", 587, "https://hilfe.gmx.net/pop-imap/imap/imap-serverdaten.html"),
    "webde": ("imap.web.de", 993, "smtp.web.de", 587, "https://hilfe.web.de/pop-imap/imap/imap-serverdaten.html"),
    "microsoft": ("outlook.office365.com", 993, "smtp-mail.outlook.com", 587, "https://support.microsoft.com/de-de/outlook/pop-imap-and-smtp-settings-for-outlook-com"),
    "icloud": ("imap.mail.me.com", 993, "smtp.mail.me.com", 587, "https://support.apple.com/de-at/102525"),
}
CLICK_PATHS = {
    "gmx": "GMX: Einstellungen → POP3/IMAP-Abruf → IMAP aktivieren.",
    "webde": "WEB.DE: Einstellungen → POP3/IMAP-Abruf → IMAP aktivieren.",
    "google": "Google-Konto → Sicherheit → Anmeldung bei Google; bei privaten Gmail-Konten ist IMAP bereits aktiv.",
    "microsoft": "Outlook.com: Einstellungen → E-Mail → Weiterleitung und IMAP → IMAP aktivieren → Speichern.",
    "icloud": "Apple Account → Anmeldung und Sicherheit → App-spezifische Passwörter.",
    "t-online": "Telekom Kundencenter → E-Mail-Passwort für E-Mail-Programme.",
    "yahoo": "Yahoo-Konto → Kontosicherheit → App-Anmeldung prüfen.",
    "freenet": "freenet-Konto → Tarifdetails und E-Mail-Einstellungen.",
    "other": "Offizielle Anbieterhilfe → Servereinstellungen für E-Mail und Kalender.",
}
