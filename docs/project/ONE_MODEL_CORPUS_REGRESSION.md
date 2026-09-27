# Korpus-Regression — Known Dev (kein neuer Blind-99-%-Claim)

**Branch:** `cursor/one-model-cv-write-d85b`  
**Produktmodell:** `qwen3.5-4b` / `Qwen3.5-4B-Q4_K_M.gguf`  
**Vergleichstyp:** Known development / Frozen archive — **kein** neuer Blindkorpus

## Abdeckung

| Korpus | n | DE/EN | GT | Rolle in diesem Auftrag |
|--------|---|-------|-----|-------------------------|
| SMOKE_DE_EN_10 | 10 | 5/5 | Sollwerte voll | Known Rescore Extrakt |
| Frontend-Ablation Fokus | 5 | 2/3 | Sollwerte | Frontend KEEP `cv_extract` |
| DOCPICK_BLIND_V2 (NV3) | 50 | 25/25 | v3 | **Frozen Blind** Qwen F1 **0,980** — unverändert |
| HOLDOUT_100 / MINI / FINAL* | ~230 | gemischt | voll | Archiv (historisch DET/Phi) — nicht neu als Prod-Score |
| ZIP-Korpora / private/cvs | — | — | — | leer / keine neuen PDFs |
| DOCX in Korpora | 0 | — | — | Fail-/Smoke-DOCX separat (Child-Smoke) |

**Duplikate:** Distinct PDFs ≈ 297; keine Byte-Duplikate zwischen Korpora (siehe `ONE_MODEL_CORPUS_INVENTORY.md`).  
**Unvollständige GT:** SMOKE `expected_results.json` ist count-only → invented-Flags dort **GT-Artefakt**, nicht Modellhalluzination (Sollwerte-Rescore).

## Parser (Known)

| Lauf | Modell | Frontend | F1 | DE | EN | Bemerkung |
|------|--------|----------|----|----|----|-----------|
| SMOKE Sollwerte Rescore | Qwen | Allein-LLM Predictions | **0,928** | 0,932 | 0,923 | Known; invent=7 |
| SMOKE Sollwerte Rescore | Phi (Archiv) | Allein-LLM | 0,930 | 0,907 | 0,957 | Historisch — nicht Prod |
| Frontend Ablation n=5 | **Qwen** | **`cv_extract`** | **0,960** | — | — | **KEEP** Frontend |
| Frontend Ablation n=5 | Qwen | Docling | 0,944 | — | — | Eval only |
| NV3 Blind (Frozen) | Qwen Docpick | (sealed) | **0,980** | 0,990 | 0,971 | Unabhängiger Blind — **unverändert** |

Soft-Grounding-Versuch: **REVERT** (F1 −0,005). Siehe `ONE_MODEL_KEEP_REVERT.md`.

## Anschreiben (Known Samples, Agent-VM)

Quelle: `artifacts/one_model_dual_use/writing_purge_samples/SAMPLES.json`

| Lang | ok | elapsed_s | peak_rss_MB | Hinweise |
|------|----|-----------|-------------|----------|
| de | true | ~181 | ~5703 | READY_AUTOMATIC; unload nach Schreiben |
| en | true | ~102 | ~5700 | English body (`lang_check` en_hits≫de); nach Sprachfix |

Parameter nach Sample-Lauf: `temperature=0.2`, Writing `max_tokens=900`, Ziellänge 250–1000 Zeichen.  
**Hardware-Hinweis:** Agent-VM — **nicht** i3 Job-Object; 3,3‑GB-Gate unverändert OFFEN.

Bakeoff (Archiv): Qwen avg ~28 s vs Phi ~55 s, Qwen invented 0 — Known, nicht Blind.

## KEEP / REVERT

| Änderung | Entscheidung |
|----------|--------------|
| Sole Qwen `PRODUCTION_MODEL_ID` | KEEP |
| Frontend `cv_extract` | KEEP |
| Soft-Grounding Extrakt | REVERT |
| Schreib-Sprache an Job koppeln | KEEP (Fix nach EN-DE-Bug) |
| NV3 Blind F1 0,980 | Frozen — kein neuer 99-%-Claim |

## Was diese Tabelle nicht beweist

- Keine fertige Windows-EXE nur durch Unit-/Known-Scores  
- Kein i3/8 GB ≤ 3,3 GB Nachweis  
- Kein neuer unabhängiger Blind-99 %
