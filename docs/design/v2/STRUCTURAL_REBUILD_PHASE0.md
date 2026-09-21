# V2 Structural Rebuild — Phase 0 Audit

**Status:** COMPLETE (mapping before implementation)  
**Branch:** `cursor/v2-uiux-refactor-d85b`  
**Demo source of truth:** `docs/design/v2/mockups/*.html` (approved batch Sep 2026)

## Principle

FUNCTIONAL PRESERVATION ≠ SPATIAL PRESERVATION.

Demos define composition. Product defines capability. Progressive disclosure for everything that would crowd a primary surface.

## Demo files (canonical)

| Screen | File |
|--------|------|
| Übersicht | `Uebersicht.html` |
| Jobs | `Jobs.html` |
| Suche läuft | `Suche_Laeuft.html` |
| Keine Treffer | `Keine_Treffer.html` |
| Bewerbungen | `Bewerbungen.html` |
| Bewerbungsdetail | `Bewerbungsdetail.html` |
| Bewerbungsvorschau | `Bewerbungsvorschau.html` |
| Postfach | `Postfach.html` |
| Zuordnung prüfen | `Zuordnung_Pruefen.html` |
| Interview Vorbereitung | `Interview_Vorbereitung.html` |
| Profil | `Profil.html` |
| Profil bearbeiten / CV | `Profil_Bearbeiten_CV_Import.html` |
| Einstellungen | `Einstellungen.html` |
| Ersteinrichtung | `Ersteinrichtung.html` |
| Global Components | `Global_Components.html` |
| Job / App / Inbox / Interview states | `*_States.html` |

Note: filenames `Keine_Treffer` / `Bewerbungsvorschau` were swapped in an earlier upload; corrected on disk.

## Current pages (production)

| Page | File | Density | Rebuild posture |
|------|------|---------|-----------------|
| Shell | `main_window.py` | — | Keep V2 nav; refine chrome |
| Übersicht | `dashboard.py` | moderate | Align to demo rhythm (drop permanent secondary button wall) |
| Jobs | `jobs.py` | crowded | Card list + Weitere-Filter drawer; SearchIntent stays progressive |
| Bewerbungen | `applications.py` | moderate | Table → detail navigation like demo |
| Postfach | `inbox.py` + `lifecycle.py` | crowded | Split list/detail; refresh icon; contextual actions |
| Profil | `profile.py` | crowded | **1:1 demo read cards + edit drawers** |
| Suche | `search.py` | crowded | Keep off primary nav; Jobs → Suchparameter |
| Settings | `settings.py` | crowded | Grouped IA like demo |
| Logs | `logs.py` | sparse | Diagnostik only |
| Wizard | `wizard/` | — | Staged onboarding |

## Control classification legend

| Class | Meaning |
|-------|---------|
| KEEP_PRIMARY | Always visible on page |
| KEEP_SECONDARY | Visible but lower emphasis |
| MOVE | Relocate to another surface |
| COLLAPSE | Behind expandable / Weitere / details |
| CONTEXTUAL | Only when item selected |
| DETAIL_ONLY | Only on detail page |
| OVERFLOW_MENU | Behind … |
| DIALOG | Modal / drawer |
| REMOVE_DUPLICATE | Drop redundant UI control (capability kept elsewhere) |

## Overview — control map (high level)

### Übersicht (`DashboardPage`)
| Control | Class | New home |
|---------|-------|----------|
| Greeting + Jobs suchen | KEEP_PRIMARY | Header CTA |
| Action queue card | KEEP_PRIMARY | Warteschlange |
| 4 KPIs | KEEP_PRIMARY | Kennzahlen |
| Last/next run | KEEP_SECONDARY | System Info cards |
| Mode/dry-run line | KEEP_SECONDARY | Soft meta / Settings mirror |
| Cancel while running | CONTEXTUAL | Suche-läuft header |
| Apply / Test / Pause / Review / Clear jobs | OVERFLOW_MENU or MOVE | Overflow „Aktionen“ / Settings / Bewerbungen |
| Advanced run stats (raw/dup/ATS) | COLLAPSE | Erweitert / Diagnose |

### Jobs
| Control | Class | New home |
|---------|-------|----------|
| Keyword/Ort/Radius/Model + Suchen | KEEP_PRIMARY | Compact search bar |
| Weitere Filter | KEEP_PRIMARY | Opens drawer with remaining result filters |
| Sort combo | KEEP_SECONDARY | Result toolbar |
| Job cards | KEEP_PRIMARY | 60% list |
| Detail + Bewerbung vorbereiten | DETAIL_ONLY | 40% panel |
| SearchIntent full editor | MOVE | Suchparameter page / drawer entry |
| age_days | REMOVE_DUPLICATE | Hidden dead control (capability never wired) |
| Table columns dump | MOVE | Prefer cards; table optional dense mode later |

### Bewerbungen
| Control | Class | New home |
|---------|-------|----------|
| Search/status/sort | KEEP_PRIMARY | Toolbar |
| Exception banner | KEEP_PRIMARY | Alert → Zuordnung/Review |
| Row click | KEEP_PRIMARY | → Bewerbungsdetail |
| Preview / Open URL | CONTEXTUAL / DETAIL_ONLY | Detail actions |
| Timeline | DETAIL_ONLY | Bewerbungsdetail |

### Postfach
| Control | Class | New home |
|---------|-------|----------|
| Refresh icon | KEEP_PRIMARY | Header icon button |
| Message list | KEEP_PRIMARY | Left pane |
| Detail + Antwort vorbereiten / Bewerbung öffnen | CONTEXTUAL | Detail action bar |
| Zuordnung prüfen / Entwurf / Interview | CONTEXTUAL / OVERFLOW_MENU | Selected message |
| Permanent 6-button row | REMOVE_DUPLICATE | Replaced by contextual actions |
| ApprovalPanel | DIALOG | Keep for consequential actions |

### Profil
| Control | Class | New home |
|---------|-------|----------|
| Aus CV importieren | KEEP_PRIMARY | Header CTA |
| Read cards (2-col) | KEEP_PRIMARY | Demo composition |
| Bearbeiten / Hinzufügen | DIALOG | Right drawer per section |
| Full endless form | REMOVE_DUPLICATE | Replaced by read+drawer |
| Save | DIALOG | Drawer Speichern / Cancel |
| Reset / wipe scopes | OVERFLOW_MENU | Documents card … or Settings Datenschutz |
| SearchIntent fields | MOVE | Never on Profile (Suchparameter) |
| Career desired titles display | KEEP_PRIMARY | Berufsziel card (profile.jobs; edit drawer) |

### Settings
| Control | Class | New home |
|---------|-------|----------|
| Tab dump | MOVE | Inner nav groups like demo |
| Safety limits | COLLAPSE | Sicherheitsgrenzen |
| Danger zone | COLLAPSE | Gefahrenbereich |
| Günther model | KEEP_SECONDARY | Integrationen / Günther group |
| Browser repair | MOVE | Erweitert / Diagnose |

## Feature parity matrix (capability)

| FEATURE | OLD LOCATION | NEW LOCATION | ACCESS PATH | STATUS |
|---------|--------------|--------------|-------------|--------|
| Start search | Dashboard buttons | Übersicht header | Jobs suchen | PRESERVED |
| Cancel search | Dashboard | Suche-läuft header | Abbrechen | MOVED |
| Pause automation | Dashboard | Overflow / Settings Automation | … | MOVED |
| Apply run | Dashboard | Overflow / Bewerbungen | … | MOVED |
| Apply test | Dashboard | Settings Erweitert / Overflow | … | MOVED |
| Review queue | Dashboard | Action queue + Bewerbungen banner | Jetzt prüfen | PRESERVED |
| Clear jobs | Dashboard | Overflow confirm | … | MOVED |
| Job filters | Jobs form | Compact + Weitere Filter drawer | Jobs | PRESERVED |
| Job sort | Table headers | Explicit sort (no discard) | Jobs toolbar | PRESERVED |
| Prepare application | Jobs/Apps | Detail primary CTA | Jobs detail / Apps detail | PRESERVED |
| SearchIntent edit | Search page | Suchparameter (via Jobs) | Jobs → Suchparameter | PRESERVED |
| Application list | Apps table | Demo table + detail | Bewerbungen | PRESERVED |
| Case timeline | Apps split | Bewerbungsdetail | Detail | MOVED |
| Mail refresh | Lifecycle button | Postfach refresh icon | Header | MOVED |
| Ambiguous association | Lifecycle buttons | Zuordnung prüfen flow | Postfach contextual | PRESERVED |
| Reply draft | Lifecycle | Contextual + approval | Postfach | PRESERVED |
| Calendar proposal | Lifecycle | Interview / Approval | Contextual | PRESERVED |
| Interview prep | Lifecycle msgbox | Interview Vorbereitung screen | Detail CTA | MOVED |
| Günther actions | GuentherActionsBar always | Contextual only | Case/message/job | MOVED |
| Profile view/edit/save | Endless form | Cards + drawers | Profil | PRESERVED |
| CV import/replace/reset | Profile CV section | Header + Documents card | Profil | PRESERVED |
| Gmail/Calendar OAuth | Settings Privacy | Settings Integrationen | Settings | PRESERVED |
| Privacy wipe/export | Settings Privacy | Datenschutz + Gefahrenbereich | Settings | PRESERVED |
| Dry-run / modes | Settings + Dashboard | Settings Automation + soft meta | Settings | PRESERVED |
| Logs/diagnose | Settings Advanced | Erweitert → Diagnose | Settings | PRESERVED |
| Tray search/pause | Tray | Tray | Tray | PRESERVED |
| First-run wizard | Wizard | Ersteinrichtung staged | Startup | PRESERVED |
| A11y names/focus/DPI | design_system/a11y | Must not regress | All pages | PRESERVED |

## Implementation sequence (locked)

1. Phase 0 docs ← this file  
2. Global components from `Global_Components.html`  
3. Profil 1:1 (+ edit/CV drawers)  
4. Postfach structural  
5. Bewerbungen + Detail + Vorschau  
6. Jobs card UI + Weitere-Filter drawer  
7. Übersicht declutter  
8. Interview / Zuordnung / Settings / Onboarding / States  
9. A11y + DPI + screenshots + final report  

## Explicit non-goals

- No domain rewrite  
- No new UI framework  
- No mobile work in this pass  
- No inventing statuses / fake % marketing headlines  
- No auto-approve consequential actions  
