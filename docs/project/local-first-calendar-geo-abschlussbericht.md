# Abschlussbericht — Local-first Geo + Google Calendar (PR #54)

**Branch:** `cursor/local-first-calendar-geo-d85b`  
**Aktualisiert:** 2026-09-22T01:28:29+00:00  
**HEAD:** `c525d83`  
**Windows Smoke Nachweis-Commit:** `cd67fbc` (run `35670758748`)  

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

Tests: `tests/test_calendar_mode_ui.py`, `tests/test_calendar_oauth_modes.py` — grün.

## 3. Vollständige Test-Suite

### Befehl
```bash
python -m pytest -m "not network" --timeout=120 -q --tb=line
```

### Ergebnisse
| Lauf | Log | Ergebnis |
|------|-----|----------|
| Vor Fix (`--timeout=60`) | `/tmp/full-pytest4.log` | 5 failed, 4585 passed, 21 skipped |
| Nach Brand/Distance-Fix | `/tmp/full-pytest5.log` | 2 failed (Guenther-Timeout + Abschlussbericht-Casing), 4588 passed |
| Re-Run nach Stabilisierung | `/tmp/full-pytest6.log` | 1 failed (Abschlussbericht enthielt noch verbotene Schreibweise), 4589 passed — behoben, siehe Lauf 7 |
| Final | `/tmp/full-pytest7.log` | **4590 passed**, 21 skipped, 2 deselected in 1066.55s |

PR#54-Regressionen behoben:
- Brand-Schreibweise auf kanonisches `Karrierekrake` vereinheitlicht
- `test_hard_exclude_unknown_distance_onsite` prüft Radius via `distance_exclude`
- Guenther-Service-Test nutzt `HeuristicProvider` (kein llama_cpp-Load unter Suite-Last)

## 4. Linux DEV Onefile (PyInstaller)

```bash
python -m PyInstaller --noconfirm --clean packaging/Karrierekrake.spec
```

| Feld | Wert |
|------|------|
| Pfad | `/workspace/dist/Karrierekrake` |
| Größe | 271103448 Bytes |
| SHA-256 | `61d29b03fef452207d4bf7d6609b95806e5bdbb4cb4e9fa684987c71f9890306` |
| Content-Scan | `python scripts/scan_release_artifact.py --exe dist/Karrierekrake --dist dist --fail-on-empty` → **OK, 0 forbidden hits** (4042 paths) |
| Isolierter EXE-Smoke | `LOCALAPPDATA=<empty> QT_QPA_PLATFORM=offscreen KARRIEREKRAKE_SMOKE_TEST=1 ./dist/Karrierekrake` → **SMOKE_TEST_OK** |

## 5. Isolierter Smoke (leeres Nutzerverzeichnis)

```bash
python scripts/smoke_local_first_isolated.py
```

Gates (alle OK): `first_start_empty_profile`, `geo_dataset_seed`, `plz_resolve_de`, `haversine`, `enrich_near`, `radius_excludes_far`, `local_job_search`, `ics_valid`, `ics_stable_uid`, `restart_geo`, `no_maps_module`.

Report: `/opt/cursor/artifacts/local_first_isolated_smoke.json`

## 6. Windows DEV EXE

Native PE-Build auf diesem Linux-Agenten nicht möglich. Nachweis über GitHub Actions:

| Feld | Wert |
|------|------|
| Workflow | `windows-smoke.yml` |
| Run | https://github.com/deadfrogface/Karrierekrake/actions/runs/35670758748 |
| Head SHA | `cd67fbc40036c7e8a3bfb5f27f3fc260e97c38f6` |
| Conclusion | **success** (`qt-smoke` + `build-and-exe-smoke`) |
| Artifact | `Karrierekrake-Windows-Smoke` |
| EXE-Pfad (Artifact) | `Karrierekrake.exe` |
| Größe | 216845112 Bytes |
| SHA-256 | `f2c9544e95c7a7f46c5dafda85ee256fe70bd21e6fd784ff65e5a00a5f7e45e0` |
| Content-Gate | **passed**, hit_count=0 |
| Isolierter LOCALAPPDATA-Smoke | **SMOKE_TEST_OK** (pages=8) |
| Gates im Job | Privacy-Scan, PyInstaller onefile, Production content gate, isolierter EXE-Smoke, Legacy-DB-Migration, Reset-Check |


## 7. Content-Policy

Verboten im Artifact: Maps-Imports, API-Keys, Dev-Credentials, Testdaten, lokale Entwicklerpfade.  
Linux-Scan: **0 Hits**. Windows: Content-Gate im Smoke-Job **grün**.  
Hinweis: Byte-String `client_secret` im Linux-Binary stammt nur aus OpenAI-SDK-Modulnamen (`openai.resources.realtime.client_secrets`) — kein Credential.

## 8. Offene Eigentümer-Follow-ups

- Production Desktop-OAuth-Client + Consent/Verifizierung
- Homepage-/Datenschutz-URLs
- GeoNames-/OSS-Lizenzprüfung im Release

## 9. Windows CI Fix (Geo Hash)

Windows `unit-tests` failed with `hash mismatch DE` because Git autocrlf turned bundled `data/geo/geonames/*.txt` into CRLF. Fix: LF-normalized SHA-256 in `core/geo_dataset.py`, rewrite-to-LF on seed, and `.gitattributes` `data/geo/** text eol=lf`.
