# Frontend-Ablation: Docling vs `cv_extract` (Known Dev)

**Korpus:** SMOKE DE/EN (fokussiert: DE_01/02 + EN_01/02/04)  
**Vergleichstyp:** Known development — **kein** Blind  
**Produktpfad:** `cv_extract` (pypdf / python-docx). Docling nur mit `KARRIEREKRAKE_CV_USE_DOCLING=1` (Eval), **nicht** in der Windows-EXE.

## Textmetriken (SMOKE 10)

Quelle: `artifacts/one_model_dual_use/frontend_ablation/TEXT_ABLATION.json`

| Metrik | Wert |
|--------|------|
| Mean Token-Jaccard (cv_extract ↔ Docling) | **0,986** |
| Mean Char-Ratio cv_extract / Docling | **0,777** (Docling verbose Markdown) |
| Mean GT-Token-Coverage cv_extract | **0,945** |
| Mean GT-Token-Coverage Docling | **0,945** (identisch) |

## LLM-Impact (gleiches Docpick-Schema, Agent-VM)

Quelle: `artifacts/one_model_dual_use/frontend_ablation/LLM_IMPACT.json`  
n=5 fokussierte Docs (BEIDE Modelle, BEIDE Frontends).

| Modell | Frontend | F1 | Precision | Recall |
|--------|----------|----|-----------|--------|
| **Qwen3.5-4B** | **cv_extract** | **0,960** | 0,932 | 0,990 |
| Qwen3.5-4B | Docling | 0,944 | 0,930 | 0,959 |
| Phi-4-mini | cv_extract | 0,912 | 0,966 | 0,864 |
| Phi-4-mini | Docling | 0,868 | 0,932 | 0,812 |

Pro Doc (Δ = Docling − cv_extract):

| Doc | Qwen Δ | Phi Δ |
|-----|--------|-------|
| DE_01 | 0 | 0 |
| DE_02 | 0 | +0,012 |
| EN_01 | **−0,082** | 0 |
| EN_02 | −0,013 | **−0,222** |
| EN_04 | 0 | 0 |

**Fazit:** Das auslieferbare `cv_extract` ist für **beide** Modelle besser oder gleich. Docling-Markdown schadet auf EN-Zweispaltig. Docling-Metrik ≠ Produktlösung.

Messung: Agent-VM — **nicht** i3/8‑GB Job-Object.

## KEEP

- Produktions-Frontend bleibt **`cv_extract`**.
- Docling bleibt Eval-Opt-in.
