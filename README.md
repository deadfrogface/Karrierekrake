# Karrierekrake Alpha 1.0

<p align="center">
  <img src="assets/brand/logo.png" alt="Karrierekrake — FINDE. BEWIRB. BEHALTE DEN ÜBERBLICK." width="520" />
</p>

<p align="center"><strong>FINDE. BEWIRB. BEHALTE DEN ÜBERBLICK.</strong><br/>
Kein Cloud-Konto · kein Pflicht-KI-Abo · Daten bleiben auf Ihrem PC</p>

<p align="center">
  <img src="docs/assets/screenshots/01-dashboard.png" alt="Dashboard" width="720" />
</p>

Lokale Desktop-App für Windows, macOS und Linux.

| System | Paket | Datenverzeichnis |
|---|---|---|
| Windows | `Karrierekrake-Alpha-1.0-Windows-x86_64.zip` | `%LOCALAPPDATA%\Karrierekrake` |
| macOS Apple Silicon | `Karrierekrake-Alpha-1.0-macOS-AppleSilicon.dmg` | `~/Library/Application Support/Karrierekrake` |
| macOS Intel | `Karrierekrake-Alpha-1.0-macOS-Intel.dmg` | `~/Library/Application Support/Karrierekrake` |
| Linux x86_64 | `Karrierekrake-Alpha-1.0-Linux-x86_64.tar.gz` | `$XDG_DATA_HOME/Karrierekrake` oder `~/.local/share/Karrierekrake` |

Ein gemeinsamer Release **Karrierekrake Alpha 1.0** enthält separate Pakete für Windows, macOS und Linux. Er wird erst nach erfolgreichen Builds und Offline-Importtests auf allen drei Systemen öffentlich. Jedes Paket und jeder Updater lädt ausschließlich die jeweilige Plattformversion. Installation und Plattformgrenzen: [macOS/Linux](docs/desktop-platforms.md).

---

## Windows — schnell starten

### Variante A: Fertiges Windows-Paket (empfohlen)

1. **Release**-Datei `Karrierekrake-Alpha-1.0-Windows-x86_64.zip` herunterladen
2. Zip **vollständig** entpacken und `Karrierekrake.exe` aus diesem Ordner starten  
   Im Updatebereich das lokale KI-Modell einmal herunterladen; Programmupdates behalten es.
3. Bei SmartScreen: „Weitere Informationen“ → trotzdem ausführen  
4. Kurzer Assistent: Lebenslauf → Sucheinstellungen → Bereit  
5. **Jobs finden**

Profil & Daten: `%LOCALAPPDATA%\Karrierekrake`

> Offline: Lebenslauf-Import und Anschreiben brauchen nach dem einmaligen Modelldownload **kein Internet**.

### Variante B: Aus dem Quellcode

1. Doppelklick auf **`setup.bat`** (Python 3.11+, `.venv`, Playwright Chromium, Basistests)  
2. Start: **`start.bat`**  
3. Optional EXE bauen: **`build.bat`** → `dist\Karrierekrake.exe` **plus** `dist\models\`  
   (Release-Zip: `python scripts\package_windows_release.py --dist dist`)

---

## Was die App tut

| Schritt | Ergebnis |
|--------|----------|
| Suchen | Bundesagentur / Indeed (weitere Quellen optional) |
| Filtern | Distanz, Duplikate, Ausschlüsse |
| Bewerten | Lokales Match 0–100 mit Begründung |
| Bewerben | Formulare vorbereiten — Absenden nur wenn Sie es erlauben |

**Sicherheitsstandard:** Dry-Run an, CAPTCHA/2FA/Review stoppen vor dem Absenden, unbekannte ATS werden nicht blind abgeschickt.

---

## Oberfläche

| Bereich | Nutzen |
|--------|--------|
| Übersicht | Nächster Schritt + klare Aktionen |
| Jobs | Liste, Detail, **Bewerbung vorbereiten** |
| Bewerbungen | Status in Alltagssprache (DB-Enums unverändert) |
| Profil | Bewerberdaten & CV-Import |
| Einstellungen | Allgemein / Suche / Bewerbung / Erweitert · **Über Karrierekrake** |
| Protokolle | Ereignisse verständlich, Technik darunter |

**Günther die Krake (optional):** Lokale Mithilfe beim Verstehen von Lebenslauf, Stelle und Bewerbungsmails. Ausgeschaltet standardmäßig. Keine Cloud-KI nötig — Modelle nur nach Ihrer Freigabe auf diesem PC. Günther denkt mit; Absenden, Mail-Versand und Termine entscheiden weiterhin Sie / Karrierekrake.

Themes: System / Hell / Dunkel · Fenster mindestens ca. 900×650

<p align="center">
  <img src="docs/assets/screenshots/02-jobs.png" alt="Jobs" width="360" />
  <img src="docs/assets/screenshots/06-profile.png" alt="Profil" width="360" />
</p>

Demo-Video: [`docs/assets/demo/karrierekrake-demo.mp4`](docs/assets/demo/karrierekrake-demo.mp4)

<p align="center">
  <img src="docs/assets/screenshots/07-about.png" alt="Über Karrierekrake" width="360" />
</p>

---

## Marke & Icons

| Asset | Verwendung |
|-------|------------|
| `assets/brand/karrierekrake-logo-master.png` | MASTER A — README, Onboarding, About, Social |
| `assets/brand/karrierekrake-app-icon-master.png` | MASTER B — EXE / Taskbar / Tray / kleine UI-Icons |
| `assets/brand/icons/icon-*.png` + `app.ico` | Deterministisch aus MASTER B (1024→16) |

Palette: Navy `#132238` · Teal `#18A999` · Orange `#E86A45` (nur Marken-Artwork).

---

## Einstellungen (kurz)

| Einstellung | Bedeutung |
|-------------|-----------|
| `mode: search_only` | Nur suchen & anzeigen |
| `mode: review_before_submit` | Ausfüllen, **nicht** absenden |
| `mode: fully_automatic` | Absenden nur wenn sicher |
| `dry_run: true` | Stoppt immer vor dem Absenden |

---

## Privatsphäre

- Alles lokal (SQLite + YAML unter AppData)
- Keine Telemetrie
- `.env`, CV, Cookies, Browser-Profil und DB sind in `.gitignore`
- Niemals echte Lebensläufe oder Passwörter committen

---

## Empfohlene GitHub Topics

`job-search` `germany` `desktop` `pyside6` `windows` `local-first` `privacy` `bewerbung` `jobboard` `automation`

Social Preview: `assets/brand/social-preview.png` (unter Repo → Settings → Social preview hochladen)

---

## Lizenzen

GPL-3.0. Herkunftshinweise: `NOTICE`, `docs/source-analysis.md`.

## Entwickler

```bat
call .venv\Scripts\activate.bat
pip install -c constraints-runtime.txt -r requirements-dev.txt
set PYTHONPATH=%cd%
pytest -q
python -m desktop.app
```

Marken-Assets (aus Masters): `python scripts/generate_brand_assets.py`  
Screenshots: `python scripts/capture_ui_screenshots.py`  
Demo-Video: `xvfb-run -a python scripts/record_demo_video.py`  
Name-Research: `docs/name-research.md` · Release-Vorlage: `docs/release-notes-template.md`
