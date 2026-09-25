# Phase 1 – PR/Branch-Bereinigung

Stand: siehe `ABSCHLUSSBERICHT_DOCPICK_PHASEN.md` (Tip `447f5fd`, PR #62).

## Import-Pfad (verifiziert)

| Ref | Pfad | DET |
|-----|------|-----|
| **main** | `import_cv_canonical` → `parse_cv_text` (DET) | **aktiv** |
| **#62 Branch** | `import_cv_canonical` → `import_cv_docpick` | **kein Fallback** |

**Nicht behaupten:** Docpick ist produktiv auf main, solange #62 nicht gemerged ist.

## Offene PRs – Entscheidung

| PR | Inhalt | Entscheidung |
|----|--------|--------------|
| **#62** | Docpick+Qwen CV-Import | **behalten / Integrationsziel** |
| **#63** | UI Primary Actions Polish | **offen lassen**; CI-Fix `1c5f550` gepusht; Merge erst bei grüner CI |
| **#61** | Docling+SmartResume Spike | **schließen** – überholt durch #62 |
| **#60** | Phi vs DET Compare | **schließen** – Phi-Extract entfernt |
| **#56** | Phi EXTRACT/WRITE ≥99% | **schließen** – PHI_EXTRACT entfernt |

**Close durch Agent:** fehlgeschlagen (HTTP 403 / kein ManagePullRequest).  
Texte: `docs/project/PR_CLOSE_COMMENTS_56_60_61.md`.

## Merge-Blocker für #62

1. Qualität: Round2 F1 0,989; Round3 Partial ≈0,990 (36/40) — bekannte CVs, **kein** Blind-0,99
2. Blindtest-Blocker: `DOCPICK_BLIND_BLOCKER.md`
3. Laufzeit: LLM ~100 s/CV, Peak ~2,5–3,2 GB
4. Round3 voller Seal+Score noch ausstehend (Extract läuft)
5. Abhängigkeiten: lokales llama.cpp + Qwen + Docling (nicht in Standard-CI)
