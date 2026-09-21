# KarriereKrake V2 UI — Design references & preservation

## Sources

| File | Role |
|------|------|
| `SUPER_PROMPT.md` | Binding implementation rules (HTML = look, Repo = function) |
| `feature-preservation-matrix.md` | Every end-user feature → V2 target |
| `mockups/*.html` | Visual design references only — **not** a feature spec |

## Colors (canonical)

- Navy `#132238`
- Teal `#18A999` / Hover `#148F82`
- Background `#F8FAFC`
- Orange `#E86A45` (brand accent only)

## Navigation (V2)

Primary: Übersicht · Jobs · Bewerbungen · Postfach · Profil  
Utility: Einstellungen · Hilfe  
Preserved off-nav: Suche (`Jobs → Suchparameter…`), Protokolle (`Einstellungen → Erweitert`)

## Rules (short)

1. Never drop a repo feature because a mockup omitted it.
2. Never invent mockup-only capabilities (e.g. Gmail send if read-only).
3. No HTML/Tailwind/WebView port — PySide6 design system only.
4. No hard-coded demo KPIs (75%, fake names, …).
5. BFSG/legal claims remain separate (`docs/accessibility/`).

## Phase status

| Phase | Status |
|-------|--------|
| 0 Inventory | Done |
| 1 Feature matrix | Done (0 blocking UNKNOWN) |
| 2 Design tokens / chrome | In progress |
| 3 App shell / nav | In progress |
| 4–13 Page migrations | Sequential follow-ups |
