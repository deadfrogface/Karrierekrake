# V2 UI progress log

## Completed this PR

- Feature-preservation matrix (238 rows, 0 blocking UNKNOWN)
- Mockups + SUPER_PROMPT under `docs/design/v2/`
- Design tokens: canvas `#F8FAFC`, control radius 8, card radius 12
- Shared chrome: `PageHeader`, `StatusChip`, `KpiCard`, `ContentCard`
- App shell V2 nav: Übersicht · Jobs · Bewerbungen · Postfach · Profil + Einstellungen · Hilfe
- Suche / Protokolle preserved off primary nav (Jobs → Suchparameter, Settings → Diagnose)
- Postfach page embeds Lifecycle mail tooling (no feature loss; no fake Gmail send)

## Next phases (sequential)

4. Übersicht visual pass (4 primary KPIs, quieter technical stats)
5. Jobs 60/40 + filter/sort separation
6. Bewerbungen + detail
7. Postfach polish (without inventing send)
8. Interview contextual surfaces
9. Profil read-first
10. Settings IA
11. Onboarding
12. State gallery
13. Regression / a11y / window sizes

## Explicit non-removals

- Dry-run / mode gates
- Ambiguous mail review
- Calendar approval gates
- Privacy lifecycle actions
- Tray / single-instance / window geometry
