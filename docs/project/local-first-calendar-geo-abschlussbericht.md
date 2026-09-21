# Abschlussbericht — Local-first Geo + Google Calendar (PR #54)

**Branch:** `cursor/local-first-calendar-geo-d85b`  
**Stand:** in Fortschreibung (Befehle/Hashes unten = tatsächlich ausgeführt)

## 1. Zielbild (erfüllt)

- Kein Karrierekrake-Backend / Token-Proxy
- Kein Google Maps / Places / Routes / Distance Matrix / Nominatim-Produktionspfad
- Bundled DACH-Geo + Haversine `haversine_v1` („ca. X km Luftlinie“)
- Pipeline: fachliches Matching **vor** lokaler Geoauflösung/Radius
- Calendar Mode A (nur FreeBusy) / Mode B (FreeBusy + `calendar.events.owned`) mit Rechteanzeige **vor** OAuth
- Tokens nur Keyring; ICS-Fallback lokal

## 2. Kalender-Modi (UI)

In den Google-/Kalendereinstellungen (`desktop/pages/settings.py`):

| Modus | Nutzerwahl | OAuth-Scopes (sichtbar vor Consent) |
|-------|------------|-------------------------------------|
| **A** | nur Verfügbarkeit prüfen | FreeBusy |
| **B** | Verfügbarkeit prüfen **und** bestätigte Termine eintragen | FreeBusy + `calendar.events.owned` |

Tests: `tests/test_calendar_mode_ui.py`, `tests/test_calendar_oauth_modes.py`.

## 3. Vollständige Test-Suite

```bash
python -m pytest -m "not network" --timeout=120 -q --tb=line
```

- Log: `/tmp/full-pytest5.log`
- Vorherige Suite (`--timeout=60`, `/tmp/full-pytest4.log`): **5 failed / 4585 passed**
  - PR#54-Regressionen behoben: Brand-Casing `Karrierekrake`→`Karrierekrake`; `test_hard_exclude_unknown_distance_onsite` → `distance_exclude`
  - Timeout-Flakes (adversarial / guenther) bei 60s unter Last → Re-Run mit `--timeout=120`

*(Ergebnis der aktuellen Suite wird hier nach Abschluss eingetragen.)*

## 4. Linux DEV Onefile (PyInstaller)

```bash
python -m PyInstaller --noconfirm --clean packaging/Karrierekrake.spec
```

| Feld | Wert |
|------|------|
| Pfad | `/workspace/dist/Karrierekrake` |
| SHA-256 | *(nach Rebuild)* |
| Content-Scan | `python scripts/scan_release_artifact.py --exe dist/Karrierekrake --dist dist --fail-on-empty` |

## 5. Isolierter Smoke (leeres Nutzerverzeichnis)

```bash
python scripts/smoke_local_first_isolated.py
```

Gates: Erststart (leeres Profil), Geo-Seed, PLZ, Haversine, lokale Jobsuche (Match→Geo→Radius), Radiusfilter, ICS-Fallback, Neustart, kein `integrations.maps`.

Report: `/opt/cursor/artifacts/local_first_isolated_smoke.json` — **ok: true** (Stand nach Smoke-Erweiterung).

## 6. Windows DEV EXE

Auf diesem Linux-Agenten ist kein PE-Build möglich. Nachweis über GitHub Actions `windows-smoke.yml` (Job `build-and-exe-smoke`):

- PyInstaller onefile `dist/Karrierekrake.exe`
- Production content gate + Manifest
- Packaged EXE smoke in isoliertem `LOCALAPPDATA`
- Artifact: `Karrierekrake-Windows-Smoke`

*(Run-ID, EXE-Pfad im Artifact, SHA-256 nach grünem CI-Lauf.)*

## 7. Content-Policy (keine Maps/Keys/Dev-Pfade)

Verboten im Artifact (u. a.): Maps-Imports, API-Keys, Dev-Credentials, Testdaten, lokale Entwicklerpfade (`/workspace`, `/home/…`). Gate: `scripts/scan_release_artifact.py` + `packaging/kk_content_policy.py`.

## 8. Offene Eigentümer-Follow-ups

- Production Desktop-OAuth-Client + Consent/Verifizierung
- Homepage-/Datenschutz-URLs
- GeoNames-/OSS-Lizenzprüfung im Release
