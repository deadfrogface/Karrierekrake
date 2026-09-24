# Phase 1 – PR/Branch-Bereinigung

Stand: Tip `cursor/docpick-qwen35-cv-replace-d85b` (Integrationsziel für Docpick).

## Import-Pfad (verifiziert)

| Ref | Pfad | DET |
|-----|------|-----|
| **main** (`98109a9`) | `import_cv_canonical` → `parse_cv_text` (DET) | **aktiv** |
| **#62 Branch** | `import_cv_canonical` → `import_cv_docpick` | **kein Fallback** |

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

1. CI: cv-regression Pytest ohne Docling (fix: importorskip) + Windows `mkdir -p artifacts` (Fix: New-Item -Force)
2. Qualität: Round2 F1 0,989 auf bekannten CVs, Perfect Core 23/40 – **kein** Blind-0,99
3. Laufzeit: ~88 s/CV, Peak ~3,2 GB – Grenzen für Blindtest noch festzulegen
4. Abhängigkeiten: lokales llama.cpp + Qwen-Modell + Docling (nicht in Standard-CI)

## Branches

Arbeitsbranches der geschlossenen Spike-PRs bleiben remote, bis Commits nicht mehr referenziert werden; Löschung optional nach Close.
