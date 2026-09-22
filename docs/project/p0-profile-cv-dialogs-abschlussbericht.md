# P0 Gate: Profil / CV-Import / Dialoge — Abschlussbericht

**Branch:** `cursor/p0-profile-cv-dialogs-d85b`  
**Commit (Windows-Smoke-Build):** `04a98838389a47c90eb1db1b06fe35e35d40bba7`  
**Datum:** 2026-09-22  
**Scope:** Nur P0-Gate (kein PR-#54 Feature-Weiterbau). Jobsuche / Bewerbung / Gmail / Calendar **nicht** als getestet markiert.

## Golden CV

| Datei | Status |
|-------|--------|
| `tests/fixtures/cv_corpus/Fake_Lebenslauf_Neuer_Blindtest_Leonie_Brandt.pdf` | ✅ vorhanden |
| `tests/fixtures/cv_corpus/Fake_Lebenslauf_Neuer_Blindtest_Leonie_Brandt.txt` | ✅ vorhanden (Blindtest-Inhalt) |

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
pytest -q tests/test_p0_profile_cv_dialogs.py   # focused P0 — 12 passed
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

### Windows EXE (CI Windows Smoke)

| Feld | Wert |
|------|------|
| Run | https://github.com/deadfrogface/Karrierekrake/actions/runs/35679796168 |
| Commit | `04a98838389a47c90eb1db1b06fe35e35d40bba7` |
| Artifact | `Karrierekrake-Windows-Smoke` |
| EXE size | 216136580 bytes |
| SHA-256 | `324225f7cbc65604cd49aeda6cfb1d9828c68ce0d61c4f5f1c35772f8e78538f` |
| console | false (WINDOWS_GUI) |
| SMOKE_TEST_OK | **yes** |
| Local copies | `/opt/cursor/artifacts/Karrierekrake.exe.sha256`, `build_metadata.txt`, `windows_smoke_test_result.txt`, `p0_windows_smoke_gate_status.md` |

Trigger: temporärer Push-Trigger auf Branch `cursor/p0-profile-cv-dialogs-d85b` in `windows-smoke.yml` (ManagePullRequest / `workflow_dispatch` / `gh` PR → 403 in Agent-Env).

Compare (PR manuell öffnen):  
https://github.com/deadfrogface/Karrierekrake/compare/main...cursor/p0-profile-cv-dialogs-d85b

### Done-Gate Status

| Kriterium | Status |
|-----------|--------|
| Dialoge nutzbar / clamp | ✅ Code + Geometrie-Smoke |
| Aufbau aus PDF/Text | ✅ |
| Sprachen / Skills / Software / WB getrennt | ✅ |
| Kein unaufgefordertes Berufsziel | ✅ (Empty + Anti-Resurrection; Vorschläge nur Button) |
| Werte editier-/löschbar + Restart | ✅ |
| Windows EXE neu gebaut | ✅ Run 35679796168 @ `04a9883` |
| Packaged EXE Smoke | ✅ `SMOKE_TEST_OK` |
| Full clean-profile Smoke (Profil/CV/Dialoge) | ✅ Linux-Agent; Windows = packaged startup/migration/reset smoke |
| GitHub PR registriert | ❌ ManagePullRequest fehlt; Compare-URL nutzen |

## Nicht getestet (explizit)

Jobsuche, Bewerbung, Gmail, Calendar.
