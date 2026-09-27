# Road-Distance — BRouter produktiv (PR #100)

**Branch:** `cursor/local-road-distance-bakeoff-d85b`  
**Vergleichstyp:** Agent-VM Messungen — **kein** i3-Laptop- / Windows-EXE-Nachweis  
**Produktiver Distanzfilter:** unsichtbare Luftlinie nur als Vorfilter → **BRouter-Fahrstrecke** entscheidet und wird angezeigt

## Suchablauf

1. **Unsichtbarer Vorfilter:** Luftlinie (`airline_km`) berechnen. Nur wenn Luftlinie **sicher größer** als der max. Fahrstrecken-Radius (`>`), Job sofort ausschließen. Bei Gleichheit weiter mit BRouter.
2. **Fahrstrecke:** Für übrige Jobs BRouter. Nur `distance_km` mit `distance_source=brouter_v1` entscheidet den Radius und erscheint in der UI.
3. **Unklar / BRouter down:** Job behalten, UI „Fahrstrecke nicht bestimmbar (…)“. Niemals Luftlinie als Fahrstrecke anzeigen oder als Endentscheidung nutzen.

Nachweis: `tests/test_airline_prefilter_road_final.py`.

## Entscheidung

| Engine | Entscheidung | Begründung |
|--------|--------------|------------|
| **BRouter lokal** | **KEEP + verdrahtet** | Peak ≈ **428 MB** (Prozessgruppe), Segmente ≈ **0,71 GiB**, Auto-Start ohne manuellen Java-Server |
| **GraphHopper lokal** | **REJECT** | Peak ≈ **5976 MB** (früherer Bakeoff) |

## 30 Paare — Remeasure mit Island-Snap (Agent-VM)

| Metrik | Wert |
|--------|------|
| OK / n | **30 / 30** |
| Island-Fixes (allgemeiner Offset-Spiral) | C05 ≈111 m, X01 ≈132 m |
| **Echter Kaltstart** | **0,434 s** |
| Peak RSS Prozessgruppe | **428 MB** |
| Platte | **≈0,72 GiB** |

## Geo DE/NL/BE

| Fall | Ergebnis |
|------|----------|
| PLZ `6211` + `NL` | Maastricht, NL |
| PLZ `6211` ohne Land | AMBIGUOUS |
| Eupen BE `4700` | RESOLVED |

## Windows-EXE

Code: Auto-Install unter `%LOCALAPPDATA%\Karrierekrake\brouter`, Auto-Start/Stop, OSM-Attribution. Smoke: `Karrierekrake.exe --smoke-brouter` bzw. `scripts/smoke_brouter_windows.py`.

**Auf Agent-VM nicht als Windows-EXE ausgeführt** (kein Windows-Worker verbunden). Proxy-Lauf: `WINDOWS_EXE_SMOKE.json` mit `comparison_type=NOT_WINDOWS_AGENT_VM_PROXY`. **PR bleibt Draft**, bis Zielgerät belegt ist.

## Qwen / Parser / Anschreiben

**Unverändert.**
