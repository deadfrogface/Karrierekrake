# V2 Structural Rebuild — Final Report (A–S)

Status after Settings / Onboarding / Search-running / Empty-state work on
`cursor/v2-uiux-refactor-d85b`.

## A — Phase 0 / demos
Done. Inventory + parity in `STRUCTURAL_REBUILD_PHASE0.md`; demos under `mockups/`.

## B — Global components
Done. `v2_chrome`: PageHeader, StatusChip, KpiCard, ContentCard, EmptyStatePanel,
TagChip, DataItem, SectionEditDrawer, IconActionButton.

## C — Profil
Done. Read-first cards + edit/CV drawers; SearchIntent not merged into profile.

## D — Postfach
Done. Split list/detail, refresh spin, contextual primary + overflow; empty panel;
Zuordnung prüfen dialog for ambiguous association.

## E — Bewerbungen
Done. Demo toolbar + detail nav with timeline; preview/open on detail.

## F — Jobs
Done. Card list, Weitere-Filter drawer, sort kept; empty state with widen /
adjust filters / search parameters CTAs.

## G — Übersicht
Done. 4 KPIs; overflow „Weitere Aktionen…“; **Suche läuft** banner + header
cancel (demo-aligned).

## H — Interview / Zuordnung
Done. Dedicated dialogs; no silent best-match; no invented match %.

## I — Settings
Done. Side-nav: Allgemein / Automation / Kommunikation / Integrationen /
Daten & Datenschutz / Erweitert; Sicherheitsgrenzen + Gefahrenbereich collapsed.

## J — Onboarding
Done. Ersteinrichtung ready step uses mode cards + locked dry-run messaging.

## K — Feature preservation
Capabilities retained (search, apply, pause, OAuth, privacy wipe, Günther,
association, calendar proposal, interview prep). Access paths moved per parity matrix.

## L — i18n
DE/EN key parity enforced in tests (`test_ui_prefs`, V2 suites).

## M — A11y
Existing `test_a11y_*` + design-system accessible names remain green.
Primary actions keep accessible names (refresh, cancel search, settings save, …).

## N — DPI
`test_a11y_dpi_layout` green (100/125/150% token scaling).

## O — Privacy / mock data
V2 mockup emails sanitized to RFC6761 `*.example` (privacy/security/Windows smoke).

## P — Brand
`Karrierekrake` capitalization consistent in i18n / branding tests.

## Q — Progressive disclosure
Settings safety/danger collapsed; Jobs Weitere-Filter in drawer; dashboard
secondary actions in overflow.

## R — Tests added this pass
- `tests/test_v2_assoc_interview.py`
- `tests/test_v2_settings.py`
- Search-running coverage in `tests/test_v2_overview.py`

## S — Remaining polish (non-blocking)
- Optional visual screenshots of each page at 100/125/150% (manual / CI artifact)
- Bewerbungsvorschau fine visual pass if demo still diverges
- ManagePullRequest forge rename Jobhuntsaver→Karrierekrake blocks auto PR body sync
