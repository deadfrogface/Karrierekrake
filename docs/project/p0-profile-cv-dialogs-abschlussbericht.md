# P0 Gate: Profil / CV-Import / Dialoge — Abschlussbericht

**Branch:** `cursor/p0-profile-cv-dialogs-d85b`  
**Commit:** `6f92b5b46ac69e6688784f9f21736a809e70d6ef`  
**Datum:** 2026-09-22  
**Scope:** Nur P0-Gate (kein PR-#54 Feature-Weiterbau). Jobsuche / Bewerbung / Gmail / Calendar **nicht** als getestet markiert.

## Golden CV

| Datei | Status |
|-------|--------|
| `Fake_Lebenslauf_Neuer_Blindtest_Leonie_Brandt.pdf` | **Im Repo ursprünglich nicht gefunden** (Suche unter fixtures/testdata/private/docs/opt) |
| Ersatz / Binding | `tests/fixtures/cv_corpus/Fake_Lebenslauf_Neuer_Blindtest_Leonie_Brandt.txt` + generiertes PDF gleichen Namens (fiktiv, Blindtest-Inhalt laut Problemlist) |

## Was kaputt war (Root Causes)

1. **Ausbildung unsichtbar:** UI `_entry_title` prüfte nicht `qualification` → Karte zeigte „—“.
2. **Lange Berufserfahrung abgeschnitten:** Karte las `description`/`summary`, nicht `responsibilities`.
3. **Weiterbildungen als Sprachen:** `_parse_one_language` akzeptierte beliebige Tokens („Lean“, „Power“…).
4. **Zertifikate unter Sprachen-Karte** gerendert (UI-Vermischung).
5. **Berufsziel nicht löschbar:** `save_config` schrieb `SearchIntent.target_roles` zurück in leere `jobs.desired_titles` (Resurrection). Profile-Save synchronisierte Clears nicht in Intent.
6. **Dialoge:** feste Größen ohne Clamp an `QScreen.availableGeometry`, Edit-Drawer ohne Scroll → Buttons unerreichbar.

## Fixes

| Stream | Änderung |
|--------|----------|
| A/B | Ausbildung-Anzeige + Persistenz-Tests; CV→Quals unverändert kanonisch |
| C | Language-Allowlist + Reklassifikation Sprachen→Software/Skill/Zertifikat |
| D | Anti-Resurrection in `save_config`; Career-Drawer ruft `apply_clear_jobs_edit_to_intent`; keine stillen Ausschluss-Prefills bei Vorschlägen |
| E | `desktop/widgets/dialog_geometry.py`; Drawer/CV-Import/Entry-Dialoge fit+scroll |
| F | `tests/test_p0_profile_cv_dialogs.py` + Agent-Smoke JSON |

## Befehle / Evidenz

```bash
export HOME=/home/ubuntu
pytest -q tests/test_p0_profile_cv_dialogs.py   # focused P0
# zusätzlich grün: test_cv_*, test_search_intent, test_profile_search_ux, test_qt_smoke, …
```

### Linux DEV onefile (Agent)

| Feld | Wert |
|------|------|
| Path | `/workspace/dist/Karrierekrake` |
| SHA-256 | `a1db6c4d22df213f207df91ba79b82f80dce9c627115f4526bceb639c71132e7` |
| Size | 270408016 bytes (~258 MiB) |
| Meta | `artifacts/Karrierekrake-linux-dev-onefile.meta.txt` |
| Smoke | `docs/project/p0_profile_cv_dialogs_smoke.json` + `/opt/cursor/artifacts/p0_profile_cv_dialogs_smoke.json` |

Clean-profile Smoke (Agent, offscreen): Empty → Golden-CV-Import → Ausbildung/Sprachen/Skills/Weiterbildung → Berufsziel löschen → Restart → Dialog-Clamp — **ALL_OK**.

### Windows EXE

`windows-smoke` läuft auf `pull_request` + `push` zu `main` (+ `workflow_dispatch`).  
In dieser Agent-Umgebung: **kein** ManagePullRequest-Tool, `gh` PR/dispatch → HTTP 403.  
Branch ist gepusht — PR manuell öffnen, dann baut CI das Windows-EXE:

https://github.com/deadfrogface/Karrierekrake/compare/main...cursor/p0-profile-cv-dialogs-d85b

Linux-Agent-Smoke (Clean-Profile + Golden-CV + Dialog-Clamp) ist **ALL_OK** unter  
`docs/project/p0_profile_cv_dialogs_smoke.json` und `/opt/cursor/artifacts/p0_profile_cv_dialogs_smoke.json`.

### Done-Gate Status

| Kriterium | Status |
|-----------|--------|
| Dialoge nutzbar / clamp | ✅ Code + Geometrie-Smoke |
| Ausbildung aus PDF/Text | ✅ |
| Sprachen / Skills / Software / WB getrennt | ✅ |
| Kein unaufgefordertes Berufsziel | ✅ (Empty + Anti-Resurrection; Vorschläge nur Button) |
| Werte editier-/löschbar + Restart | ✅ |
| Windows EXE neu gebaut | ⏳ wartet auf PR / workflow_dispatch (403 hier) |
| Full clean-profile Smoke evidenced | ✅ Linux-Agent; Windows = nach PR-CI |

## Nicht getestet (explizit)

Jobsuche, Bewerbung, Gmail, Calendar.
