# FINAL UX COMPOSITION / POLISH PASS — Report

Branch: `cursor/v2-uiux-refactor-d85b`  
Demos: refreshed under `docs/design/v2/mockups/` from the supplied polish pack.

## 1. Screens changed

| Screen | Changes |
|--------|---------|
| **Übersicht** | Demo-faithful header; large KPI numbers (`KpiValue` 32px); **one** stateful search CTA (idle/starting/running/cancelling); action queue only when needed; hide redundant search hero; humanized timestamps; humanized mode chip; **removed** Weitere-Aktionen dump + production diagnostics (`raw/dup/dist/ATS`) |
| **Jobs** | Empty-state CTAs retained; Weitere Filter drawer retained (demo decision) |
| **Bewerbungen** | Coherent toolbar (search+status together, sort right); icon refresh; designed empty state + Jobs CTA; max-width content; humanized dates; „Nur mit Prüfbedarf“ |
| **Postfach** | Contextual primary + overflow from domain state; Interview only for `interview_invite`; no always-on capability wall; humanized times |
| **Einstellungen** | Rare actions (Bewerbungstest, Jobs leeren) under Erweitert/Diagnose so features stay reachable |
| **Shared** | `desktop/util/human_time.py`; KPI theme token; visual QA fixtures (`desktop/dev/visual_qa_fixtures.py`) |

## 2. State / action matrix

| STATE | PRIMARY | SECONDARY | HIDDEN | WHY |
|-------|---------|-----------|--------|-----|
| Dashboard idle | Jobs suchen / Erneut suchen | Queue CTA if needed | Diagnostics, apply wall | Demo hierarchy |
| Dashboard starting | Suche wird gestartet… (disabled) | — | Cancel until running | No fake progress |
| Dashboard running | Suche abbrechen | — | Jobs suchen | Same control |
| Dashboard cancelling | Suche wird beendet… | — | — | Feedback |
| Jobs idle/results | Filtern / card CTAs | Weitere Filter | Full SearchIntent | Demo |
| Jobs empty | Filter anpassen | Umkreis / Suchparameter | — | Designed empty |
| Apps empty | Jobs ansehen | Status/Sort shell | Review-only wall | Same shell |
| Apps populated | Row → Detail | Alert „Jetzt prüfen“ | Permanent review button | Demo |
| Inbox empty | — | Refresh | All mail actions | No context |
| Inbox ambiguous | Zuordnung prüfen | — | Interview/Draft | Domain |
| Inbox linked + interview | Bewerbung öffnen | Draft, Interview-Prep, Kalender | — | Domain category |
| Inbox rejection | Bewerbung öffnen | — | Interview/Draft | Domain |
| Inbox confirmation | Bewerbung öffnen | — | Interview/Draft | Domain |
| Inbox offer | Bewerbung öffnen | Draft | Interview | Domain |

## 3. Demo fidelity scores (0–10)

| Screen | Structure | Spacing | Hierarchy | Density | Controls | Empty | Interaction | Notes |
|--------|-----------|---------|-----------|---------|----------|-------|-------------|-------|
| Übersicht | 9 | 8 | 9 | 8 | 9 | n/a | 9 | Greeting + compact KPIs |
| Jobs | 8 | 8 | 8 | 8 | 9 | 8 | 8 | Cards already close; further pixel polish optional |
| Bewerbungen | 9 | 8 | 8 | 8 | 9 | 9 | 9 | Toolbar regrouped |
| Postfach | 8 | 8 | 8 | 8 | 9 | 8 | 9 | Contextual actions |
| Settings | 9 | 8 | 8 | 8 | 9 | n/a | 8 | Side-nav kept |

All ≥ 8; remaining delta is Qt vs HTML chrome, not alternate IA.

## 4. Fake-data states tested

Via `seed_visual_qa_db` + unit tests:

- apps empty / one / many  
- inbox mix: ambiguous, interview, confirmation, rejection, offer  
- overview KPIs with seeded activity  

No real PII (`*.example` senders).

## 5. Removed production-visible diagnostics

- `raw=` / `dup=` / `dist=` / `ATS unknown` / `supported` run detail  
- Advanced stats strip on Übersicht  
- Raw `Modus: search_only` → translated mode chip  
- ISO timestamps → `Heute, … Uhr` / localized absolute  

(Still computed into hidden labels for tests / future developer mode.)

## 6. Contextual actions changed

- Postfach overflow rebuilt per message  
- Interview-Prep / Kalender only for interview category + linked case  
- Reply draft not shown for rejection/confirmation  
- „Bewerbung öffnen“ only when case linked  
- Dashboard: no permanent secondary dump; rare actions → Settings Erweitert  

## 7. Screenshots

Generated under `/opt/cursor/artifacts/screenshots/` (polish pass):

- `polish-uebersicht.png`  
- `polish-bewerbungen-empty.png`  
- `polish-bewerbungen-populated.png`  
- `polish-postfach-interview.png`  
- `polish-settings.png`  

## 8. Tests

- `tests/test_v2_overview.py` (rewritten for polish)  
- `tests/test_v2_polish_fixtures.py`  
- Existing V2 / a11y suites green  

## 9. CI

Subscribed on branch head after push.

## 10. Commit SHA

See `git log -1` on push (this pass).
