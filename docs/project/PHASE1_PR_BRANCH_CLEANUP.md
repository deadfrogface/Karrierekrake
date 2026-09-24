# Phase 1 – PR/Branch-Bereinigung

Stand: Tip `82ad289` auf `cursor/docpick-qwen35-cv-replace-d85b` (Integrationsziel für Docpick, PR #62).

## Import-Pfad (verifiziert)

| Ref | Pfad | DET |
|-----|------|-----|
| **main** | `import_cv_canonical` → `parse_cv_text` (DET) | **aktiv** |
| **#62 Branch** | `import_cv_canonical` → `import_cv_docpick` | **kein Fallback** |

UI auf dem Branch: `desktop/workers.py` / `cv_import_dialog.py` → `core.cv_parser.import_cv` → Canonical → Docpick.

**Nicht behaupten:** Docpick ist produktiv auf main, solange #62 nicht gemerged ist.

## Offene PRs – Entscheidung

| PR | Inhalt | Entscheidung |
|----|--------|--------------|
| **#62** | Docpick+Qwen CV-Import | **behalten / Integrationsziel**; Merge blockiert bis CI grün + Qualität/Laufzeit akzeptiert |
| **#63** | UI Primary Actions Polish | **offen lassen** (unabhängig, MERGEABLE); nicht blockierend für Parser |
| **#61** | Docling+SmartResume Prototyp (Gate failed) | **schließen** – überholt durch #62 |
| **#60** | Phi vs DET Compare | **schließen** – Phi-Extract aus Produktion entfernt; DET bleibt nur auf main bis #62 |
| **#56** | Phi EXTRACT/WRITE ≥99% | **schließen** – PHI_EXTRACT entfernt; WRITE bleibt unabhängig |

## Merge-Blocker für #62 (explizit)

1. Qualität: Round2 F1 0,989; Round3 Partial ≈0,993 (18/40) – beides bekannte CVs, **kein** Blind-0,99
2. Blindtest-Blocker: kein unberührter DE/EN-Korpus mit voller GT (`DOCPICK_BLIND_BLOCKER.md`)
3. Laufzeit: LLM ~100 s/CV, Peak ~3,2 GB – Grenzen für Blindtest noch festzulegen
4. Abhängigkeiten: lokales llama.cpp + Qwen-Modell + Docling (nicht in Standard-CI)
5. Round3 voller Seal+Score noch ausstehend (Extract läuft)

## Branches

Arbeitsbranches der geschlossenen Spike-PRs bleiben remote, bis Commits nicht mehr referenziert werden; Löschung optional nach Close.
