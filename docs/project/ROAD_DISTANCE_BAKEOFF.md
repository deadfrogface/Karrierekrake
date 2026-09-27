# Road-Distance — BRouter produktiv (PR #100)

**Branch:** `cursor/local-road-distance-bakeoff-d85b`  
**Vergleichstyp:** Agent-VM Messungen — **kein** i3-Laptop- / Windows-EXE-Nachweis  
**Produktiver Distanzfilter:** Luftlinie nur Vorfilter → danach **BRouter-Fahrstrecke**

## Entscheidung

| Engine | Entscheidung | Begründung |
|--------|--------------|------------|
| **BRouter lokal** | **KEEP + verdrahtet** | Peak ≈ **428 MB** (Prozessgruppe), Segmente ≈ **0,71 GiB**, Auto-Start ohne manuellen Java-Server |
| **GraphHopper lokal** | **REJECT** | Peak ≈ **5976 MB** (früherer Bakeoff) |

## 30 Paare — Remeasure mit Island-Snap (Agent-VM)

| Metrik | Wert |
|--------|------|
| OK / n | **30 / 30** |
| Island-Fixes (allgemeiner Offset-Spiral, keine Orts-Sonderregeln) | C05 snap ≈ 111 m, X01 snap ≈ 132 m |
| Warme Wall 30 Routen | siehe `BROUTER_REMEASURE_30.json` |
| Peak RSS Prozessgruppe | **428 MB** |
| **Echter Kaltstart** (Java-Kill → Spawn → Port → erste Route) | **0,434 s** (Java→Port 0,201 s + erste Route 0,233 s) |
| Platte jar+Segmente+Profiles | ≈ **0,72 GiB** (Segmente dominant) |

Rohdaten: `artifacts/road_distance_bakeoff/BROUTER_REMEASURE_30.json`, `BROUTER_RESULTS.json`.

## Geo DE/NL/BE

| Fall | Ergebnis |
|------|----------|
| PLZ `6211` + `NL` | **RESOLVED** Maastricht, NL (nicht CH) |
| PLZ `6211` ohne Land | **AMBIGUOUS** (`plz_needs_country`) |
| Eupen BE `4700` | **RESOLVED** (BE bundliert) |
| Frankfurt ohne Zusatz | **AMBIGUOUS** |

Dataset: `data/geo` v2 (DE/AT/CH/NL/BE GeoNames).

## Distanzfilter (produktiv im Code)

1. Luftlinie > Radius → Exclude (Vorfilter)  
2. Sonst Fahrstrecke (BRouter) entscheidet  
3. UNKNOWN / fehlendes Segment / Routingfehler → Job **behalten**, UI: **„Fahrstrecke nicht bestimmbar (Grund)“** — keine Luftlinie als Fahrkilometer  

## Windows-EXE

Code: Auto-Install (jar/Segmente unter `%LOCALAPPDATA%\Karrierekrake\brouter`), Auto-Start/Stop am App-Lifecycle, OSM-Attribution, Segment-Updates mit If-Modified-Since.

**Auf Agent-VM nicht als Windows-EXE ausgeführt.** PR bleibt Draft bis EXE-Durchlauf auf Zielgerät belegt ist.

## Qwen / Parser / Anschreiben

**Unverändert.**
