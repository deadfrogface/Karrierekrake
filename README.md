# Karrierekrake

Karrierekrake ist eine lokale Desktop-App (PySide6) für die Jobsuche und die Vorbereitung von Bewerbungen. Profil, Einstellungen und die Job-Datenbank liegen auf deinem PC unter `%LOCALAPPDATA%\Karrierekrake`. Ein Crash- oder Telemetrie-Uploader ist nicht enthalten; Protokolle bleiben lokal.

Die App bewirbt sich nicht von allein. Im Auslieferungszustand ist nur die Suche aktiv, Dry-Run ist an und automatisches Absenden ist aus. Ein finaler Klick auf Absenden im Browser bleibt dann aus. Arbeitgeber-Mails bleiben Entwürfe, bis du den Versand freigibst.

Screenshots und Demo-Video folgen (werden auf dem aktuellen Stand neu aufgenommen).

## Was es heute kann

Die Seitenleiste führt zu Übersicht, Jobs, Bewerbungen, Postfach, Profil und Einstellungen. Dazu gibt es Hilfe. Beim ersten Start öffnet sich ein Assistent mit drei Seiten: Lebenslauf (optional), Sucheinstellungen, Arbeitsmodus. Dry-Run bleibt dabei an.

Sprache ist Deutsch oder Englisch. Das Thema folgt dem System oder ist hell oder dunkel.

**Suche.** Eingeschaltet sind voreingestellt die Bundesagentur für Arbeit und Indeed. StepStone und XING lassen sich in den Einstellungen dazuschalten. Jede Quelle hat einen eigenen Adapter und Tests:

- Bundesagentur für Arbeit: `BundesagenturSource` in `search/bundesagentur.py`. Tests prüfen die Remote-Erkennung und den Health-Check.
- Indeed: `IndeedSource` in `search/indeed.py` mappt Zeilen von JobSpy. Tests prüfen diese Zuordnung.
- StepStone: `StepstoneSource` in `search/stepstone.py`. Ein Test lässt die Suche gegen festes HTML laufen und erwartet einen Treffer.
- XING: `XingSource` in `search/xing.py`. Ein Test lässt die Suche gegen festes JSON-LD laufen und erwartet einen Treffer.

Eine laufende Suche kannst du abbrechen. In der Jobliste siehst du eine Einschätzung (sehr passend, passend, teilweise passend, nicht passend).

**Stellenanzeige.** Kommt die Beschreibung als HTML in einem JSON-LD-Feld, wird sie in Klartext gewandelt. Dabei fallen Skripte, Styles, JSON-LD-Blöcke und Tracking-Pixel aus dem Text. Was danach noch sichtbar ist, steht unter „Bekannte Grenzen“. Eine Aufteilung in Aufgaben und Anforderungen gibt es in diesem Stand nicht.

**Lebenslauf.** Unter Profil liest du einen Lebenslauf ein. Das Einlesen läuft in einem eigenen Kindprozess, die Oberfläche bleibt bedienbar, und Abbrechen ist möglich. Bricht du ab, wird nichts übernommen. Der Parser ist deterministisch; lokales LLM-Parsing für Lebensläufe ist aus und der Schalter in den Einstellungen bleibt deaktiviert, bis ein Speichertest auf dem Zielgerät vorliegt. Die Speichersperre für diesen Pfad ist aktiv. Der Speicher-Peak auf der Zielhardware ist ungeprüft.

**Bewerbung vorbereiten.** Du kannst eine Bewerbung vorbereiten und vor dem Absenden prüfen. Unbekannte oder nur teilweise unterstützte Formulare werden nicht final abgeschickt. Ein endgültiger Submit-Klick ist nur vorgesehen, wenn du zugleich Vollautomatik wählst, Dry-Run ausschaltest und „Automatisch absenden“ einschaltest, und nur für ein vollständig unterstütztes Portal.

**Postfach.** Antwort- und Nachfass-Entwürfe bleiben Entwürfe. Der Versand ist standardmäßig aus. Ohne deine Freigabe pro Mail geht keine Arbeitgeber-Mail raus. Terminvorschläge werden nicht still in den Kalender geschrieben.

**Anschreiben-Entwurf (in Arbeit).** Günther, lokal und standardmäßig aus, darf nur vorschlagen, was in deinem Profil belegt ist. Eine behauptete Qualifikation ohne Beleg im Profil wird abgelehnt. Nichts davon geht ohne deine Freigabe raus.

Läuft die App schon, weist ein zweiter Start darauf hin. Ist kein System-Tray verfügbar, erscheint ein englischer Hinweis; die App bleibt nutzbar.

## In Arbeit

Offene Änderungen, nicht Teil dieses Stands und ohne Zusage, wann sie landen:

- Standort und Umkreis: Auflösen einer Postleitzahl (zum Beispiel Berlin-Mitte über 10115), Hinweis bei mehrdeutigen Orten wie Halle oder Frankfurt, und der Distanzfilter (#67).
- Aufteilung einer Stellenanzeige in Aufgaben und Anforderungen (#74).
- Zustände beim Lebenslauf-Einlesen und der Fußbereich (#70, #72).
- Schatten und Hover für Chips und Karten (#71).
- Absturz auf der Profilseite nach erneutem Aktualisieren (#73).
- Anschreiben: Gold-Set und zusätzliche Sperren (#75, #77).
- Migrationslauf beim Beenden (#78).

## Bekannte Grenzen

- In einem gemeinsamen Abschnitt „Ausbildung und Berufserfahrung“ landen Zeilen ohne Ausbildungs-Stichwort bei der Berufserfahrung. Der Import übernimmt das so. Die Extraktion ist damit nicht zuverlässig.
- Nach der Textwandlung einer Anzeige bleiben Cookie-Hinweise, der Text „Jetzt bewerben“, Teilen-Elemente, „Ähnliche Jobs“ und das geschützte Leerzeichen aus `&nbsp;` stehen.
- LinkedIn steht in den Quell-Einstellungen. Der vorhandene Test prüft nur die Zeilenzuordnung, keinen Abruf. Firmenkarriereseiten sind ein Platzhalter und liefern keine Treffer.
- Wenn Qt kein System-Tray meldet, lautet der Dialog auf Englisch: „System tray is not available. The app can still be used.“ Das wurde unter Linux beobachtet.

## Installation und Start

Die Skripte sind für Windows. `setup.bat` verlangt Python 3.11 oder neuer, legt `.venv` an, installiert `requirements-runtime.txt` und Playwright Chromium.

Start aus dem Quellbaum, nachdem `setup.bat` gelaufen ist:

```bat
start.bat
```

Dasselbe macht `python -m desktop.app`. Gleichwertig ist `python -m desktop`.

Eine EXE baust du mit `build.bat`. Das Skript führt die Tests aus und schreibt `dist\Karrierekrake.exe`. Chromium steckt nicht in der EXE. Der Browser wird bei Bedarf nach `%LOCALAPPDATA%\Karrierekrake\browsers` gelegt.

## Datenschutz und Datenablage

Unter `%LOCALAPPDATA%\Karrierekrake` liegen unter anderem `config`, `data` (SQLite), `logs`, `cvs`, `cover_letters`, `browser_profile`, `browsers` und `models`. Suche und ein geöffneter Browser sprechen die Portale an, die du einschaltest. Die Datenbank und dein Profil bleiben auf diesem PC.

Im Dateninventar ist kein Sentry-, Telemetrie- oder Crash-Uploader eingetragen. Lokale Protokolle gibt es. Im Repository sind `.env`, Browser-Profile und abgelegte Lebensläufe unter `private/cvs/` von Git ausgeschlossen.

## Entwicklung und Tests

```bat
call .venv\Scripts\activate.bat
pip install -r requirements-dev.txt
python -m pytest -q
python -m desktop.app
```

`setup.bat` installiert pytest zusätzlich und führt `python -m pytest tests -q` aus. `build.bat` bricht ab, wenn `python -m pytest -q` fehlschlägt.

## Lizenz

GPL-3.0. Der Text steht in `LICENSE`. Herkunft und Copyright stehen in `NOTICE`.
