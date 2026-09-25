# Karrierekrake

Dieser Text beschreibt `main` mit Stand `dcae58b`.

Karrierekrake ist eine lokale Desktop-App (PySide6) für die Jobsuche und die Vorbereitung von Bewerbungen. Profil, Einstellungen und die Job-Datenbank liegen auf deinem PC unter `%LOCALAPPDATA%\Karrierekrake`. Ein Crash- oder Telemetrie-Uploader ist nicht enthalten; Protokolle bleiben lokal.

Die App bewirbt sich nicht von allein. Im Auslieferungszustand ist nur die Suche aktiv, Dry-Run ist an und automatisches Absenden ist aus. Ein finaler Klick auf Absenden im Browser bleibt dann aus. Arbeitgeber-Mails bleiben Entwürfe, bis du den Versand freigibst.

Screenshots und Demo-Video folgen (werden auf dem aktuellen Stand neu aufgenommen).

## Was es heute kann

Die Seitenleiste führt zu Übersicht, Jobs, Bewerbungen, Postfach, Profil und Einstellungen. Dazu gibt es Hilfe. Beim ersten Start öffnet sich ein Assistent mit drei Seiten: Lebenslauf (optional), Sucheinstellungen, Arbeitsmodus. Dry-Run bleibt dabei an.

Sprache ist Deutsch oder Englisch. Das Thema folgt dem System oder ist hell oder dunkel.

**Suche.** Standardmäßig aktiv sind nur die Bundesagentur für Arbeit und Indeed.

- Bundesagentur für Arbeit: `BundesagenturSource` in `search/bundesagentur.py`. Tests prüfen die Remote-Erkennung und den Health-Check.
- Indeed: `IndeedSource` in `search/indeed.py` mappt Zeilen von JobSpy. Tests prüfen diese Zuordnung.
- StepStone lässt sich einschalten: `StepstoneSource` in `search/stepstone.py`. Ein Test lässt die Suche gegen festes HTML laufen und erwartet einen Treffer.
- XING lässt sich einschalten: `XingSource` in `search/xing.py`. Ein Test lässt die Suche gegen festes JSON-LD laufen und erwartet einen Treffer.
- LinkedIn lässt sich einschalten. Der Abruf läuft über JobSpy und ist ungetestet.

**Standort.** Eine Postleitzahl mit Land und ein eindeutiger Ort werden lokal aufgelöst. Ein Ortsname ohne Land und eine Postleitzahl, die in mehreren Ländern vorkommt, bleiben unaufgelöst. Fehlt der Wohnort, sagt die Übersicht das. Liegt nur ein Text vor und der letzte Suchlauf hat den Wohnort nicht aufgelöst, bittet die Übersicht um eine Postleitzahl; die Jobs bleiben dann unabhängig von der Entfernung sichtbar.

Die Fahrtstrecke stellst du im Assistenten unter „Max. Pendelweg“ und unter Einstellungen → Erweitert → Suche als „Max. Fahrtstrecke (km)“ ein. In der Jobliste filterst du mit „Max. km“. Nach der fachlichen Einschätzung fallen Stellen außerhalb dieses Umkreises weg. Voll-Remote bleibt drin, wenn Remote erlaubt ist. Eine unbekannte Entfernung gilt nicht als 0 km. Die Jobkarte zeigt die Luftlinie, „Standort nicht prüfbar“ oder „Remote (kein Radius)“.

Der Knopf „Geodaten aktualisieren“ sitzt im Abschnitt Wohnort und lädt den lokalen Geodatensatz neu. Schlägt das fehl, bleibt der bisherige Datensatz. Keine Profilkarte öffnet diesen Abschnitt.

Eine laufende Suche kannst du abbrechen. In der Jobliste siehst du eine Einschätzung (sehr passend, passend, teilweise passend, nicht passend).

**Stellenanzeige.** Anzeigentexte werden mit BeautifulSoup in Klartext gewandelt, Inhalte von Skript- und Style-Tags fallen dabei weg. Eine Aufteilung in Aufgaben und Anforderungen gibt es in diesem Stand nicht.

**Lebenslauf.** Unter Profil liest du einen Lebenslauf ein. Das Einlesen läuft in einem eigenen Kindprozess, die Oberfläche bleibt bedienbar, und Abbrechen ist möglich. Brichst du ab, wird nichts übernommen. Der Parser ist deterministisch; lokales LLM-Parsing für Lebensläufe ist aus und der Schalter in den Einstellungen bleibt deaktiviert, bis ein Speichertest auf dem Zielgerät vorliegt. Die Speichersperre für diesen Pfad ist aktiv. Der Speicher-Peak auf der Zielhardware ist ungeprüft.

**Bewerbung vorbereiten.** Du kannst eine Bewerbung vorbereiten und vor dem Absenden prüfen. Unbekannte oder nur teilweise unterstützte Formulare werden nicht final abgeschickt. Ein endgültiger Submit-Klick ist nur vorgesehen, wenn du zugleich Vollautomatik wählst, Dry-Run ausschaltest und „Automatisch absenden“ einschaltest, und nur für ein vollständig unterstütztes Portal.

**Postfach.** Antwort- und Nachfass-Entwürfe bleiben Entwürfe. Der Versand ist standardmäßig aus. Ohne deine Freigabe pro Mail geht keine Arbeitgeber-Mail raus. Terminvorschläge werden nicht still in den Kalender geschrieben.

**Anschreiben-Entwurf (in Arbeit).** Ziel ist, dass jede Aussage im Entwurf durch dein Profil belegt ist. Die Sperren dafür sind noch nicht abgenommen (#75, #77). Ohne Günther, den lokalen Textgenerator (standardmäßig aus), entsteht der Entwurf aus einer Vorlage, und automatische Anschreiben sind voreingestellt an. Nichts geht ohne deine Freigabe raus.

Läuft die App schon, weist ein zweiter Start darauf hin. Ist kein System-Tray verfügbar, erscheint ein englischer Hinweis; die App bleibt nutzbar.

## In Arbeit

Offene Änderungen, nicht Teil dieses Stands und ohne Zusage, wann sie landen:

- Schärfere Ortsauflösung: exakter Ortsname statt Teilstring, Streuung in Kilometern, gleichnamige Orte wie Halle oder Frankfurt, frischer Hinweis am Wohnort in Übersicht, Einstellungen und Profil, und Kilometer in der Jobliste nur bei aufgelöstem Wohnort (#67).
- Aufteilung einer Stellenanzeige in Aufgaben und Anforderungen (#74).
- Zustände beim Lebenslauf-Einlesen und der Fußbereich (#70, #72).
- Schatten und Hover für Chips und Karten (#71).
- Anschreiben: Gold-Set und zusätzliche Sperren (#75, #77).
- Migrationslauf beim Beenden (#78).

## Bekannte Grenzen

- In einem gemeinsamen Abschnitt „Ausbildung und Berufserfahrung“ landen Zeilen ohne Ausbildungs-Stichwort bei der Berufserfahrung. Der Import übernimmt das so. Die Extraktion ist damit nicht zuverlässig.
- Es gibt keinen gezielten Filter für Cookie-Banner, „Jetzt bewerben“, Share-Widgets oder „Ähnliche Jobs“. Deren Text kann im Anzeigentext bleiben.
- Firmenkarriereseiten sind ein Platzhalter und liefern keine Treffer.
- Wenn Qt kein System-Tray meldet, lautet der Dialog auf Englisch: „System tray is not available. The app can still be used.“ Das wurde unter Linux beobachtet.

## Installation und Start

Die Skripte sind für Windows. `setup.bat` verlangt Python 3.11 oder neuer, legt `.venv` an, installiert `requirements-runtime.txt` und Playwright Chromium. Schlagen die Basistests fehl, erscheint nur eine Warnung; die Installation läuft weiter.

Start aus dem Quellbaum, nachdem `setup.bat` gelaufen ist:

```bat
start.bat
```

Dasselbe macht `python -m desktop.app`. Gleichwertig ist `python -m desktop`.

Eine EXE baust du mit `build.bat`. Das Skript führt die Tests aus und schreibt `dist\Karrierekrake.exe`. Chromium steckt nicht in der EXE. Der Browser wird bei Bedarf nach `%LOCALAPPDATA%\Karrierekrake\browsers` gelegt.

## Datenschutz und Datenablage

Unter `%LOCALAPPDATA%\Karrierekrake` legt die App diese Ordner an: `config`, `data` (SQLite), `logs`, `browser_profile`, `browsers`, `cvs`, `cache`, `cover_letters` und `models`. Suche und ein geöffneter Browser sprechen die Portale an, die du einschaltest. Die Datenbank und dein Profil bleiben auf diesem PC.

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

GPL-3.0. Der Text steht in `LICENSE`. Herkunft und Copyright stehen in `NOTICE`. Die lokalen Geodaten (GeoNames, CC BY 4.0) sind in `NOTICE` ab Zeile 123 genannt.
