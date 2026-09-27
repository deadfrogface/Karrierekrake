# Road-Distance Bakeoff — BRouter vs GraphHopper (lokal)

**Branch:** `cursor/local-road-distance-bakeoff-d85b`  
**Vergleichstyp:** Agent-VM Messungen — **kein** i3-Laptop-Nachweis  
**Produktiver Distanzfilter:** unverändert (weiter Luftlinie `haversine_v1`)

## Entscheidung

| Engine | Entscheidung | Begründung |
|--------|--------------|------------|
| **BRouter lokal** | **KEEP** (Integrations-Scaffold) | Peak ≈ **385 MB**, Segmente ≈ **0,60 GiB**, kein OSM-Import, Auto-Start als Kindprozess ohne Account/API-Key; mit Qwen auf Agent-VM 16 GiB gleichzeitig lauffähig |
| **GraphHopper lokal** | **REJECT** (Produkt) | Peak ≈ **5976 MB**, OSM-Quelle ≈ **7,7 GiB** + Graph-Cache ≈ **1,05 GiB**, Kaltstart inkl. Import **339 s**; zusammen mit Qwen (~5,6 GiB) auf 8 GB-Laptop nicht tragbar |

Öffentliche Web-UIs (BRouter/OSRM/GraphHopper) wurden **nicht** als Backend genutzt (nur manuelle Plausibilität erlaubt; hier nicht automatisiert belastet).

## OSM-Daten

| Quelle | Objekt-Timestamp (osmium) | HTTP Last-Modified | Größe lokal |
|--------|---------------------------|--------------------|-------------|
| Geofabrik NRW/Nds/HE/RP + NL + BE | **2026-09-26T20:22:51Z** | 2026-09-27 ~01–03 UTC | Summe Extracts **3,85 GiB**; merged **~3,9 GiB** |
| BRouter segments4 `E0_N45,E0_N50,E5_N45,E5_N50` | — | **2026-09-27 01:03:01 GMT** | **0,60 GiB** |

Details: `artifacts/road_distance_bakeoff/OSM_DATA_META.json`, `STORAGE_FOOTPRINT.json`.

## 30 Paare — Messwerte (Agent-VM)

| Metrik | BRouter | GraphHopper |
|--------|---------|-------------|
| OK / n | **28 / 30** | **30 / 30** |
| Missing | C05 (Brüssel→Airport), X01 (Aachen→Maastricht) — `target island detected` | 0 |
| Wall 30 Routen | 28,8 s | 0,30 s |
| Mean s/Route | 0,96 s | 0,007 s |
| Peak RSS Prozessgruppe | **385 MB** | **5976 MB** |
| Kaltstart | erste Route **0,29 s** (Server schon oben; Java-Start vernachlässigbar) | **339 s** inkl. Import+CH |
| Offensichtliche Umwege (Heuristik) | C04 flagged | keine |

Rohdaten: `BROUTER_RESULTS.json`, `GRAPHHOPPER_RESULTS.json`, `PAIRS_30.json`.

## Installation / Updates (Windows — Design, nicht auf Laptop gemessen)

| Thema | BRouter | GraphHopper |
|-------|---------|-------------|
| Runtime | JRE/JDK (mitgeliefert oder System) | JRE + großer Import |
| Karten | `.rd5`-Segmente nach Bedarf laden | Geofabrik-PBF mergen + Graph bauen |
| Update | Segment-HTTP ersetzen (Last-Modified) | PBF neu + Graph neu (Minuten–Stunden) |
| Nutzeraktion | **kein** manueller Serverstart (App startet Kindprozess) | Import-Dauer problematisch |
| Account/Cloud | nein | nein (lokal) |

## Concurrent Qwen (Agent-VM)

| | Wert |
|--|------|
| Qwen maxRSS | **5582 MB** |
| BRouter währenddessen | **~324 MB** |
| MemAvailable dabei | ~6,0 GiB von 16 GiB |
| GraphHopper allein | **5976 MB** |

→ GH+Qwen auf i3/8 GB: **REJECT**. BRouter+Qwen: auf Agent-VM ok; **Laptop weiterhin offen**.

## Geo: Stellenort → Koordinaten (bestehend)

Spotcheck `GEO_RESOLVE_SPOTCHECK.json` (lokales GeoNames/pgeocode):

| Fall | Ergebnis |
|------|----------|
| Frankfurt (ohne Zusatz) | **AMBIGUOUS** → keine Distanz |
| PLZ 50667 DE | RESOLVED postal_centroid |
| PLZ 6211 + NL („Maastricht“) | **falsch** → Buchs LU, CH (PLZ-Kollision) |
| Eupen BE PLZ 4700 | **UNKNOWN** offline (BE nicht im DACH-Bundle) |
| Leerer Ort / Fantasie-Stadt | UNKNOWN |
| UI-Label | `Luftlinie` explizit; `DISTANCE_UNKNOWN` bei Unresolved |

**Regel bestätigt:** Unbekannte Position darf **keine** exakte Fahrstrecke werden. Luftlinie nur Vorfilter / klar gekennzeichnet.

## Grenzfahrten / fehlende Segmente

- Mit 4 BRouter-Kacheln: 5/6 Cross-Border OK; X01 Island-Snap.
- Fehlende Kachel → Route fehlt klar (nicht still Luftlinie).
- Aufwand Update: betroffene `.rd5` neu laden (~50–250 MB/Kachel).

## Integrations-Scaffold (dieser Branch)

Opt-in Modul **ohne** Anbindung an den produktiven Distanzfilter:

- `core/road_route_brouter.py` — Start/Stop, Route, Attribution
- Segment-Download-Helfer
- Tests Grenzpaare (Mock + optional Live)
- Flag default **aus**

Qwen-Parser/Anschreiben: **unverändert**.
