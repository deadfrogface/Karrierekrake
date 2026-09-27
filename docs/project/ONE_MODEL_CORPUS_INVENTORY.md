# Korpus-Inventar — One-Model Dual-Use Arbeit

**Branch:** `cursor/one-model-cv-write-d85b`  
**Basis:** `main` @ `ffa648e` (bis PR #95)  
**Drafts:** #96 Packaging (nicht produktiv), #97 Phi-vs-Qwen Extrakt (nicht produktiv), #98 DET±Phi Retest (nicht produktiv)

## Draft-Stand (gelesen, nicht als Prod)

| PR | Stand | Inhalt | CI |
|----|-------|--------|-----|
| **#96** | Draft OPEN `c49a6ab` | Docpick+llama shippen, `cv_extract` statt Docling, Auto-LLM, stufenspezifische Fehler | smoke/privacy grün; **security** fail (`diskcache`/PYSEC-2026-2447) |
| **#97** | Draft OPEN | Isolierter Phi-vs-Qwen Extrakt auf SMOKE; Entscheidung „kein Sieger“ | Known-CV |
| **#98** | Draft OPEN | Phi im DET/Docling-Stack | Known-CV; DET±Phi ≠ Phi allein |

## Korpora (DE/EN mit GT)

| ID | n | DE/EN | Format | GT | Bemerkung |
|----|---|-------|--------|-----|-----------|
| SMOKE_DE_EN_10_V1 | 10 | 5/5 | PDF | JSON **count-only** emp/edu; Sollwerte-TXT **voll** | #97 invented = GT-Artefakt |
| HOLDOUT_100 | 100 | 94/6 | PDF | voll | Frozen DET/Phi-Pipelines |
| MINI_HOLDOUT_30 | 30 | 26/4 | PDF | voll | |
| FINAL_HOLDOUT_50 | 50 | 45/5 | PDF | voll | |
| FINAL_INDEPENDENT_50_V2 | 50 | gemischt | PDF | voll | DET independent bar |
| DOCPICK_BLIND_V1 | 4 | 2/2 | PDF | voll v3 | kleine Blindprobe |
| DOCPICK_BLIND_V2 (NV3) | 50 | 25/25 | PDF | voll v3 | Qwen Docpick Blind F1 0,980 |
| DOCPICK_BLIND_V3 | 0 | — | — | Scaffold | keine PDFs |
| REGRESSION_KNOWN (R8) | 40 | =SMOKE+MINI | PDF | gemischt | known regression |
| Leonie Brandt | 1 | DE | PDF+TXT | **keine** GT | ausgeschlossen |
| Fail-cases | 2 | — | corrupt | demo | |

**Distinct PDFs ≈ 297** (keine Byte-Duplikate zwischen Korpora). Keine DOCX in den Korpora. `private/cvs/` leer.

## #97 „29 invented“ — Klärung

`tests/fixtures/cv_corpus/expected_results.json` liefert für alle 10 SMOKE-Docs nur `education_count` / `work_count` (keine Listen). Scorer V2 setzt dann `expect_absent` → jeder echte Extrakt = `invented_*`.

Beleg Audit: `tests/docpick_qwen35/AUDIT_INVENTED_AND_PR_SUMMARY.json` — **28 Flags, 0 echte Halluzinationen** (text-grounded). Voll-GT für dieselben PDFs: `CV_Parser_Sollwerte_Vollstaendig.txt`.

→ #97-Invented auf SMOKE sind **keine** belastbare Modellschwäche; Rescore gegen Sollwerte erforderlich.

## Vorhandene Predictions (Reuse)

| Pfad | Modell/Pfad | Korpus |
|------|-------------|--------|
| `artifacts/phi_vs_qwen_cv_extract/predictions_{phi,qwen}/` | Allein-LLM Vollschema | SMOKE 10 |
| `tests/docpick_*/frozen_predictions/` / NV3 | Docpick+Qwen | Blind/Regression |
| `artifacts/holdout_100/frozen_baseline_predictions/B1_phi_only/` | Phi allein | HO100 |
| `artifacts/phi_full_parser_retest/` | DET±Phi / Docling | SMOKE (Hybrid — nicht Phi allein) |

## Hardware-Gate

i3/8 GB Job-Object Peak ≤ 3 300 000 000 Bytes: **OFFEN / UNGEPRÜFT** (`DOCPICK_LAPTOP_RAM_GATE_STATUS.md`). Agent-VM ≠ Ship-Evidence.
