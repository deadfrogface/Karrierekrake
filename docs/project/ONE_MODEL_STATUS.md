# One-Model Dual-Use — Zwischen-/Abschlussstand (ehrlich)

**Repo:** deadfrogface/Karrierekrake  
**Branch / PR:** `cursor/one-model-cv-write-d85b` / [#99](https://github.com/deadfrogface/Karrierekrake/pull/99)  
**Stand:** 2026-09-27 — **keine fertige App**, **99 % unabhängig nicht nachgewiesen**

## 1. Ein-Modell-Entscheidung

| | |
|--|--|
| **Kandidat** | **Qwen3.5-4B-Q4_K_M** (ein GGUF) für Extrakt **und** Anschreiben |
| Nicht | Phi (Schreib-Bakeoff schwächer; Extrakt nur knapper Sollwerte-Vorteil) |
| Nicht | Zwei Gewichte / Cloud / manueller Server / DET |

Belege: `ONE_MODEL_DUAL_USE_DECISION.md`, Write-Bakeoff, Sollwerte-Rescore, NV3 Blind (unverändert, Qwen Extrakt).

## 2. Korpus-Inventar

Siehe `ONE_MODEL_CORPUS_INVENTORY.md`. Alle bewertbaren DE/EN-Korpora erfasst; #97 „29 invented“ = Count-only-GT-Artefakt → Sollwerte-Rescore.

## 3. Phi vs Qwen (Known Dev, sofern nicht anders)

### Parser (SMOKE Sollwerte-Voll-GT, Reuse #97 Predictions)

| Modell | F1 | DE | EN | Invented-Flags | Perfect Core | Typ |
|--------|----|----|----|----------------|--------------|-----|
| Phi | 0,931 | 0,907 | 0,957 | 7 | 0 | Known Dev |
| Qwen | 0,928 | 0,932 | 0,923 | 7 | 0 | Known Dev |

NV3 Docpick-Blind Qwen F1 **0,980** — Frozen Blind, unverändert.

### Anschreiben (n=4 Known, gleiches PHI_WRITE-Gerüst)

| | Phi | Qwen |
|--|-----|------|
| Lesbarkeit | JSON-Leak / BEGIN_UNTRUSTED | saubere DE/EN-Briefe |
| Invented (Heuristik) | 2 | 0 |
| Avg Wall | ~55 s | ~28 s |
| Peak RSS (Agent-VM) | ~5,5 GB | ~5,7 GB |

## 4. Frontend Docling vs `cv_extract`

| Metrik | Wert |
|--------|------|
| Token-Jaccard (SMOKE 10) | 0,986 |
| GT-Token-Coverage | **identisch** 0,945 |
| Qwen F1 (n=5 fokussiert) | **cv_extract 0,960** > Docling 0,944 |
| Phi F1 (n=5) | **cv_extract 0,912** > Docling 0,868 |
| EN_01 Qwen | cv 0,971 vs Docling 0,889 (Δ −0,082) |

**KEEP:** Produktions-Frontend = `cv_extract`. Docling schadet auf EN-Zweispaltig.

## 5. KEEP / REVERT

Siehe `ONE_MODEL_KEEP_REVERT.md`. Soft-Grounding Skills/Software **REVERT** (F1 −0,005).

## 6. Windows-EXE / Import-Nachweis

| Prüfung | Status |
|---------|--------|
| Linux Child DE PDF + in-process Qwen | **ok=True** (~138 s, Agent-VM) |
| Linux Child EN PDF | **ok=True** (Emily Carter, 3 Jobs) |
| Linux Child DOCX (aus DE_01 Text) | **ok=True** |
| Fehlendes Modell → `model_missing` | **PASS** (kein CV in Message) |
| Beschädigte Datei → `unreadable_cv` | **PASS** |
| Timeout → `timeout` | **PASS** |
| Windows-EXE öffnen→import→Vorschau→Übernehmen→Restart | **OFFEN / UNGEPRÜFT** |
| Job-Object Peak ≤ 3 300 000 000 auf i3/8 GB | **OFFEN / UNGEPRÜFT** |

## 7. 99 %

| Aussage | Status |
|---------|--------|
| Known Dev/Regression kann hohe F1 zeigen | ja, **kein** unabhängiger Nachweis |
| Unabhängiger 99 %-Blind nach Freeze | **fehlt** |
| Statusformel | **„99 % unabhängig nicht nachgewiesen“** |

## 8. Hardware

Alle Laufzeit-/RSS-Zahlen = **Agent-VM**. Ship-Gate i3/8 GB Job Object: **OFFEN**.

## Entscheidung (klar)

**Ein Modell:** Qwen3.5-4B-Q4_K_M — vorläufiger Produktkandidat für Extrakt **und** Anschreiben.  
**Nicht fertig:** Windows-EXE-E2E und i3-RAM-Gate offen → **keine fertige App**.  
**Nicht 99 % unabhängig.**