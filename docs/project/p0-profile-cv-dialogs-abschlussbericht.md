# P0 Gate: Profil / CV-Import / Dialoge — Abschlussbericht

**Branch:** `cursor/p0-profile-cv-dialogs-d85b`  
**Commit:** `3b1ee19cb03c32ae7b4cc622c346a9a4f0272bd1`  
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

Build läuft über GitHub Actions `windows-smoke` auf dem Branch. Agent kann kein natives Windows-EXE ausführen; PE-Build + EXE-Smoke = CI-Artefakt.

PR-Erstellung via API/ManagePullRequest in dieser Umgebung **403 / Tool fehlt** — Branch ist gepusht:
https://github.com/deadfrogface/Karrierekrake/compare/main...cursor/p0-profile-cv-dialogs-d85b

## Done-Gate Status

| Kriterium | Status |
|-----------|--------|
| Dialoge nutzbar / clamp | ✅ Code + Geometrie-Smoke |
| Ausbildung aus PDF/Text | ✅ |
| Sprachen / Skills / Software / WB getrennt | ✅ |
| Kein unaufgefordertes Berufsziel | ✅ (Empty + Anti-Resurrection; Vorschläge nur Button) |
| Werte editier-/löschbar + Restart | ✅ |
| Windows EXE neu gebaut | ⏳ CI `windows-smoke` |
| Full clean-profile Smoke evidenced | ✅ Linux-Agent; Windows = CI |

## Nicht getestet (explizit)

Jobsuche, Bewerbung, Gmail, Calendar.
