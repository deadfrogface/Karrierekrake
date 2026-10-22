"""Help window: first steps, the questions people actually ask, and the way into the connection guides."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QPushButton,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
)

FIRST_STEPS = """
<h3>In fünf Schritten zu deiner ersten Bewerbung</h3>
<ol>
<li style='margin-bottom:6px'><b>Profil prüfen.</b> Unter <i>Profil</i> stehen deine Stationen, Ausbildung und Kenntnisse
aus dem Lebenslauf. Schreib bei jeder Station kurz auf, <b>was du dort gemacht hast</b>. Daraus entsteht später dein
Anschreiben, und das Programm schreibt nur, was dort steht.</li>
<li style='margin-bottom:6px'><b>Suche starten.</b> Auf der <i>Übersicht</i> auf <i>Jobs suchen</i> klicken. Das Programm
fragt die Jobportale nach Stellen in deiner Nähe.</li>
<li style='margin-bottom:6px'><b>Treffer ansehen.</b> Unter <i>Jobs</i> zeigt jede Karte, wie gut die Stelle passt und
warum. „Min. Match“ blendet schwächere Treffer aus, „0“ zeigt alles.</li>
<li style='margin-bottom:6px'><b>Bewerbung vorbereiten.</b> Auf einen Job klicken, dann <i>Bewerbung vorbereiten</i>.
Du siehst Lebenslauf und Anschreiben als Entwurf. Nichts wird ohne dich abgeschickt.</li>
<li style='margin-bottom:6px'><b>Antworten im Blick behalten (optional).</b> Verbinde unter <i>Postfach</i> dein
E-Mail-Konto, damit Antworten von Arbeitgebern deiner Bewerbung zugeordnet werden.</li>
</ol>
"""

FAQ = """
<h3>Häufige Fragen</h3>

<p><b>Warum zeigt die Jobliste so wenige Treffer?</b><br>
Der Filter „Min. Match“ steht standardmäßig auf 60 Prozent und „Max. km“ auf deinen Umkreis. Setze „Min. Match“ auf 0, um
alles zu sehen. Ein Job mit 100 Prozent ist praktisch nicht erreichbar, weil Gehalt und Kenntnisse nur zählen, wenn die
Anzeige sie nennt.</p>

<p><b>Warum schreibt das Programm für manche Jobs kein Anschreiben?</b><br>
Es nutzt nur, was in deinem Profil steht. Findet es zur Anzeige keine passende Station oder Kenntnis, bricht es ab, statt
etwas zu erfinden. Ergänze unter <i>Profil</i> deine Aufgaben und Kenntnisse oder such eine Stelle, die näher an deiner
Erfahrung liegt.</p>

<p><b>Warum fehlt bei manchen Jobs der Anzeigentext?</b><br>
Manche Portale liefern in der Liste nur eine Überschrift. Bei XING lädt das Programm den vollen Text, sobald du
<i>Bewerbung vorbereiten</i> wählst. Bei anderen öffnest du die Anzeige mit <i>Job öffnen</i>.</p>

<p><b>Warum sehe ich nicht alle meine Mails?</b><br>
Das Postfach zeigt nur Mails, die zu Bewerbungen gehören. Rechnungen, Werbung und Privates sind ausgeblendet. Unter
„Alle Nachrichten“ im Filter siehst du sie trotzdem.</p>

<p><b>Wo liegen meine Daten?</b><br>
Nur auf diesem Computer, im Ordner, den du im Fenster <i>Über Karrierekrake</i> öffnen kannst. Nichts davon wird an uns
geschickt. Löschen kannst du alles unter <i>Einstellungen → Daten &amp; Datenschutz</i>.</p>

<p><b>Was passiert mit meinem Postfach-Passwort?</b><br>
Es wird nur lokal gespeichert. Karrierekrake liest Mails nur und markiert oder löscht nichts.</p>

<p><b>Es klappt etwas nicht.</b><br>
Unter <i>Einstellungen → Erweitert</i> öffnest du die Protokolle. Dort steht, was passiert ist, in Alltagssprache, die Einzelheiten darunter. Bitte
schick keine Protokolle mit privaten Daten weiter, ohne sie vorher anzusehen.</p>
"""


class HelpDialog(QDialog):
    def __init__(self, parent=None, *, data_dir=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Hilfe")
        self.setMinimumSize(620, 560)
        self._data_dir = data_dir
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        from desktop.widgets.connection_guide import CALENDAR_GUIDES, MAIL_GUIDES

        mail = "".join(f"<h3>{title}</h3>{steps}" for title, steps in MAIL_GUIDES.values())
        calendar = "".join(f"<h3>{name}</h3>{html}" for name, (html, _link) in CALENDAR_GUIDES.items())
        for title, html in (("Erste Schritte", FIRST_STEPS), ("Häufige Fragen", FAQ),
                            ("Postfach verbinden", mail), ("Kalender verbinden", calendar)):
            view = QTextBrowser()
            view.setOpenExternalLinks(True)
            view.setHtml(html)
            self.tabs.addTab(view, title)
        layout.addWidget(self.tabs, 1)
        row = QHBoxLayout()
        self.about_btn = QPushButton("Über Karrierekrake …")
        self.about_btn.setObjectName("SecondaryButton")
        close = QPushButton("Schließen")
        close.setObjectName("PrimaryButton")
        row.addWidget(self.about_btn)
        row.addStretch(1)
        row.addWidget(close)
        layout.addLayout(row)
        self.about_btn.clicked.connect(self._show_about)
        close.clicked.connect(self.accept)

    def _show_about(self) -> None:
        from desktop.widgets.about_dialog import AboutDialog

        AboutDialog(self, data_dir=self._data_dir).exec()
