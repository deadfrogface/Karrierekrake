"""Plain-language, step-by-step instructions for connecting a mailbox or a calendar."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
)


def _steps(*items: str, note: str = "") -> str:
    rows = "".join(f"<li style='margin-bottom:6px'>{item}</li>" for item in items)
    tail = f"<p style='margin-top:8px'>{note}</p>" if note else ""
    return f"<ol style='margin-left:-12px'>{rows}</ol>{tail}"


# Index = position in FreeMailCredentialsDialog.PRESETS.
MAIL_GUIDES = {
    0: ("So verbindest du Gmail (kostenlos, mit App-Passwort)", _steps(
        "Ein <b>App-Passwort</b> ist ein zweites, nur für Karrierekrake gültiges Passwort aus 16 Buchstaben. "
        "Dein normales Google-Passwort funktioniert hier nicht und gibst du hier auch nicht ein.",
        "Öffne <a href='https://myaccount.google.com/security'>myaccount.google.com/security</a> und melde dich an.",
        "Schalte unter „So melden Sie sich bei Google an“ die <b>Bestätigung in zwei Schritten</b> ein, falls sie "
        "noch aus ist (Handynummer bestätigen). Ohne sie gibt es keine App-Passwörter.",
        "Öffne <a href='https://myaccount.google.com/apppasswords'>myaccount.google.com/apppasswords</a>. "
        "Alternativ: im Suchfeld oben „App-Passwörter“ eingeben.",
        "Name eingeben, zum Beispiel <b>Karrierekrake</b>, und auf <b>Erstellen</b> klicken.",
        "Google zeigt ein gelbes Feld mit 16 Buchstaben. <b>Kopiere sie</b> (Leerzeichen sind egal). "
        "Das Passwort wird nur dieses eine Mal angezeigt.",
        "Hier im Fenster: bei „E-Mail-Adresse“ deine Gmail-Adresse eintragen, bei „Passwort“ die 16 Buchstaben "
        "einfügen, auf <b>OK</b> klicken.",
        note="Karrierekrake liest Mails nur und markiert oder löscht nichts. Beim ersten Abruf werden die Mails der "
             "letzten 90 Tage geladen. Bietet Google kein App-Passwort an (zum Beispiel bei Firmen- oder "
             "Schulkonten): Mails über „Google Takeout“ exportieren und mit „EML / MBOX importieren“ laden.")),
    1: ("So verbindest du WEB.DE", _steps(
        "Melde dich bei <a href='https://web.de'>web.de</a> an und öffne <b>Einstellungen → POP3/IMAP Abruf</b>.",
        "Aktiviere den <b>IMAP-Zugriff</b> und speichere.",
        "Hast du die Zwei-Faktor-Anmeldung an, erstelle unter „Sicherheit“ ein <b>Anwendungspasswort</b> für "
        "externe Programme und nutze dieses unten.",
        "Hier: E-Mail-Adresse und Passwort eintragen, <b>OK</b>.")),
    2: ("So verbindest du T-Online", _steps(
        "Öffne im Kundencenter <b>Einstellungen → E-Mail-Programme</b> und lege ein <b>E-Mail-Passwort für "
        "externe Programme</b> fest. Das ist ein anderes als dein Telekom-Login-Passwort.",
        "Hier: deine vollständige T-Online-Adresse und dieses E-Mail-Passwort eintragen, <b>OK</b>.")),
    3: ("So verbindest du Outlook.com", _steps(
        "Outlook.com erlaubt Programmen nur die Anmeldung über Microsofts eigene Freigabe. Das ist für Einsteiger "
        "aufwendig.",
        "<b>Einfacher Weg:</b> Exportiere in Outlook.com einzelne Mails oder einen Ordner als Datei und lade sie "
        "hier mit <b>EML / MBOX importieren</b>.",
        "Fortgeschrittene können eine eigene Microsoft-Desktop-App registrieren und deren Client-ID hier eintragen.")),
    4: ("So verbindest du einen anderen Anbieter", _steps(
        "Suche in der Hilfe deines Anbieters nach „IMAP-Einstellungen“. Du brauchst den <b>IMAP-Server</b> "
        "(zum Beispiel imap.beispiel.de) und Port 993.",
        "Aktiviere IMAP im Konto, falls nötig, und lege ein <b>App-Passwort</b> oder „Passwort für "
        "E-Mail-Programme“ an.",
        "Hier: Server, E-Mail-Adresse und Passwort eintragen, <b>OK</b>.")),
}

# name -> (steps html, a link can be used)
CALENDAR_GUIDES = {
    "Google Kalender": (_steps(
        "Öffne am Computer <a href='https://calendar.google.com'>calendar.google.com</a>.",
        "Klicke oben rechts auf das <b>Zahnrad → Einstellungen</b>.",
        "Links unter „Einstellungen für meine Kalender“ deinen Kalender anklicken (meist dein Name).",
        "Nach unten scrollen bis <b>„Kalender integrieren“</b>. Dort steht die "
        "<b>„Geheime Adresse im iCal-Format“</b>.",
        "Klicke auf das Kopieren-Symbol daneben.",
        "Hier unten auf <b>„Link einfügen“</b> klicken und den Link einfügen.",
        note="Wichtig: Die geheime Adresse ist wie ein Passwort. Gib sie niemandem. Du kannst sie in Google "
             "jederzeit zurücksetzen. Karrierekrake kann damit deinen Kalender nur lesen, nichts ändern."), True),
    "Samsung Kalender": (_steps(
        "Der Samsung Kalender auf dem Handy synchronisiert meist mit deinem <b>Google-Konto</b>. Dann sind deine "
        "Termine auch in Google Kalender zu sehen.",
        "Folge in diesem Fall der Anleitung für <b>Google Kalender</b> (Auswahl oben).",
        "Nutzt du nur das Samsung-Konto: Exportiere den Kalender auf dem Handy als <b>.ics-Datei</b>, "
        "schicke sie dir per E-Mail und wähle sie hier mit <b>„Datei auswählen“</b>."), True),
    "Apple Kalender / iCloud": (_steps(
        "Am Mac: <b>Kalender-App → Ablage → Exportieren → Exportieren …</b> und speichere die Datei "
        "(Endung .ics).",
        "Am iPhone gibt es keinen direkten Export. Nutze dort die Mac-Variante oder "
        "<a href='https://www.icloud.com/calendar'>icloud.com/calendar</a> am Computer.",
        "Hier unten auf <b>„Datei auswählen“</b> klicken und die .ics-Datei wählen.",
        note="Eine Datei ist eine Momentaufnahme: Neue Termine erscheinen erst, wenn du sie erneut lädst."), False),
    "Outlook.com / Microsoft": (_steps(
        "Öffne <a href='https://outlook.live.com/calendar'>outlook.live.com/calendar</a> und klicke auf das "
        "<b>Zahnrad → Alle Outlook-Einstellungen → Kalender → Freigegebene Kalender</b>.",
        "Wähle unter „Kalender veröffentlichen“ deinen Kalender, Berechtigung <b>„Alle Details anzeigen“</b>, "
        "und klicke auf <b>Veröffentlichen</b>.",
        "Kopiere den <b>ICS-Link</b> (nicht den HTML-Link).",
        "Hier unten auf <b>„Link einfügen“</b> klicken."), True),
    "Ich habe eine .ics-Datei": (_steps(
        "Eine <b>.ics-Datei</b> ist einfach eine Datei mit deinen Terminen, die jedes Kalenderprogramm "
        "exportieren kann.",
        "Hier unten auf <b>„Datei auswählen“</b> klicken und die Datei wählen.",
        note="Eine Datei ist eine Momentaufnahme. Neue Termine erscheinen erst, wenn du die Datei erneut lädst. "
             "Mit einem Link (siehe Google Kalender) aktualisiert sich der Kalender von selbst."), False),
}


class CalendarConnectDialog(QDialog):
    """Pick the calendar app, read the steps, then choose link or file. ``choice`` is 'link' or 'file'."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Kalender kostenlos verbinden")
        self.setMinimumSize(560, 520)
        self.choice = ""
        layout = QVBoxLayout(self)
        intro = QLabel("<b>Welchen Kalender nutzt du?</b> Karrierekrake liest deine Termine nur, "
                       "damit es Bewerbungstermine und freie Zeiten erkennt.")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.app = QComboBox()
        self.app.addItems(list(CALENDAR_GUIDES))
        layout.addWidget(self.app)
        self.steps = QTextBrowser()
        self.steps.setOpenExternalLinks(True)
        layout.addWidget(self.steps, 1)
        row = QHBoxLayout()
        self.link_btn = QPushButton("Link einfügen …")
        self.link_btn.setObjectName("PrimaryButton")
        self.file_btn = QPushButton("Datei auswählen …")
        self.file_btn.setObjectName("SecondaryButton")
        cancel = QPushButton("Abbrechen")
        row.addStretch(1)
        row.addWidget(cancel)
        row.addWidget(self.file_btn)
        row.addWidget(self.link_btn)
        layout.addLayout(row)
        self.link_btn.clicked.connect(lambda: self._done("link"))
        self.file_btn.clicked.connect(lambda: self._done("file"))
        cancel.clicked.connect(self.reject)
        self.app.currentIndexChanged.connect(self._update)
        self._update()

    def _update(self) -> None:
        html, link_possible = CALENDAR_GUIDES[self.app.currentText()]
        self.steps.setHtml(html)
        self.link_btn.setEnabled(link_possible)
        self.link_btn.setToolTip("" if link_possible else "Für diesen Kalender nimmst du die Datei.")

    def _done(self, choice: str) -> None:
        self.choice = choice
        self.accept()
