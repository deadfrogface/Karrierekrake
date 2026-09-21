# V2 UI progress log — STRUCTURAL rebuild

## Phase 0
- Approved demos under `docs/design/v2/mockups/`
- `STRUCTURAL_REBUILD_PHASE0.md` — inventory, control classes, parity matrix

## Completed (structural, not reskin)
- Global primitives: `ProfileSectionCard`, `DataItem`, `TagChip`, `SectionEditDrawer`, `EmptyStatePanel`, …
- **Profil:** read-first 2-col cards + edit drawers (demo 1:1); SearchIntent stays separate
- **Postfach:** list/detail split, refresh icon + spin while busy, contextual primary + … menu; Lifecycle chrome hidden; empty state panel
- **Bewerbungen:** demo toolbar + alert; click/double-click opens detail with timeline; preview/open on detail
- **Jobs:** card list + Weitere-Filter drawer
- **Übersicht:** secondary control wall → overflow „Weitere Aktionen…“ (capabilities kept)
- **Zuordnung prüfen** + **Interview vorbereiten** dedicated dialogs (wired from Postfach / Lebenszyklus)
- **Einstellungen:** side-nav IA (Allgemein / Automation / Kommunikation / Integrationen / Datenschutz / Erweitert); Sicherheitsgrenzen + Gefahrenbereich collapsed
- **Ersteinrichtung:** Ready step mode cards aligned with demo copy

## Still sequential
- State gallery polish (Suche läuft / Keine Treffer / Integration states)
- Bewerbungsvorschau visual pass
- A11y + DPI + screenshots + final report A–S
