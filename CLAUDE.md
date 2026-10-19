# Karrierekrake — Hinweise für Claude Code

Lokale Desktop-App (PySide6, Python 3.11+) für Jobsuche und Bewerbungen. Windows ist das Hauptziel, macOS/Linux werden ebenfalls gebaut.
Branch-Regeln: siehe @AGENTS.md (immer frisch von `origin/main` abzweigen, keine gemergten Branches weiterverwenden).

## Leitlinien (nicht verhandelbar)

- **Local-first:** kein eigener Server, keine kostenpflichtigen APIs, keine Cloud-KI im freien Pfad. Geo über lokale DE/AT/CH-GeoNames, nicht Google Maps.
- **Kein Google-Zwang:** Gmail/Kalender optional; der Verbinden-Button bleibt. Keinen eigenen Kalender bauen.
- **Standardbrowser des Nutzers** verwenden (Firefox/Edge ok), Chrome nicht erzwingen.
- **Sicherheit:** Dry-Run standardmäßig an; bei CAPTCHA/2FA/Review vor dem Absenden stoppen; unbekannte ATS nie blind absenden.
- **CV-Parsing ist deterministisch** (Phi/C1 entfernt). Keine LLM-Abhängigkeit in den Parser zurückbringen.
- **Stabilität vor Features:** keine Freezes (lange Arbeit in QThread/Workern, nie im UI-Thread), keine Abstürze bei Modell-Downloads oder Login.
- UI-Texte auf Deutsch, für Laien verständlich.

## Struktur

| Ordner | Inhalt |
|---|---|
| `app/`, `desktop/` | Einstieg, Qt-UI (`pages/`, `widgets/`, `viewmodels/`, `wizard/`, `services/`) |
| `core/` | Domänenlogik: CV-Parser, Matcher, DB, Geo, Updates, Modell-Download |
| `search/` | Jobquellen (Bundesagentur, Indeed, ATS, Firmenseiten) |
| `apply/` | ATS-Formular-Adapter (Greenhouse, Lever, Workday, …) |
| `browser/` | Playwright-Browserverwaltung, Site-Pausen |
| `integrations/` | Mail/Kalender (Gmail, Outlook, iCloud, CalDAV), OAuth, Follow-ups |
| `guenther/` | Optionaler lokaler KI-Assistent „Günther“ |
| `mobile/`, `contracts/` | Mobile Apps + gemeinsame JSON-Schemas |
| `scripts/` | CI, Packaging, Benchmarks, Korpus-Auswertung |
| `tests/` | pytest; Holdout-/Blind-Korpora liegen als Zips/Ordner hier |
| `docs/` | Architektur, ADRs, Audits |

## Befehle

```bash
# Setup (Linux/macOS): bash .cursor/install.sh   ·   Windows: setup.bat
source .venv/bin/activate            # Windows: .venv\Scripts\activate
QT_QPA_PLATFORM=offscreen python -m pytest -q -m "not network" tests/test_<bereich>*.py   # gezielt testen
python scripts/run_cv_corpus.py && python scripts/run_cv_sollwerte_corpus.py         # CV-Korpus
python scripts/privacy_scan.py       # muss vor jedem PR grün sein
ruff check <geänderte Dateien>
```

- Die volle Suite ist groß (CI shardet sie 6-fach). Lokal nur betroffene Tests laufen lassen, nicht alles.
- `network`-markierte Tests sind optional und laufen nicht in CI.
- Holdout-/Blind-Daten (`tests/*holdout*`, `*_PHASE_B_SOLUTIONS*`) **nie** zum Tunen des Parsers verwenden; nur zum Auswerten.

## Arbeitsweise

- Vor Behauptungen wie „behoben“ oder „läuft“: Test/Befehl ausführen und Ergebnis zeigen.
- Kleine, fokussierte PRs; Diff gegen `main` darf nur beabsichtigte Änderungen enthalten.
- Keine Secrets/Tokens committen (gitleaks + privacy_scan laufen in CI).
