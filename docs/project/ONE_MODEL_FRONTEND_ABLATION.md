# Frontend-Ablation: Docling vs `cv_extract` (Known Dev)

**Korpus:** SMOKE DE/EN 10 (Sollwerte-Voll-GT)  
**Vergleichstyp:** Known development — **kein** Blind  
**Produktpfad:** `cv_extract` (pypdf / python-docx). Docling nur mit `KARRIEREKRAKE_CV_USE_DOCLING=1` (Eval), **nicht** in der Windows-EXE.

## Textmetriken

Quelle: `artifacts/one_model_dual_use/frontend_ablation/TEXT_ABLATION.json`

| Metrik | Wert |
|--------|------|
| Mean Token-Jaccard (cv_extract ↔ Docling) | **0,986** |
| Mean Char-Ratio cv_extract / Docling | **0,777** (Docling verbose Markdown) |
| Mean GT-Token-Coverage cv_extract | **0,945** |
| Mean GT-Token-Coverage Docling | **0,945** (identisch) |

**Fazit Text:** Auf dem SMOKE-Korpus verliert `cv_extract` praktisch keine GT-Tokens gegenüber Docling. Die kürzere Zeichenlänge kommt von weniger Markdown/Whitespace, nicht von fehlenden Fakten. Eine gute Docling-Metrik bleibt **kein** Produktnachweis, weil Docling+Torch auf dem Zielgerät nicht auslieferbar ist.

## LLM-Impact (Phi + Qwen, gleiches Docpick-Schema)

Fokussierter Lauf auf DE_01/02 + EN mit größtem Char-Diff; Cache unter `frontend_ablation/llm_cache/`.

### Partial (Qwen, DE_01 + DE_02, beide Frontends)

| Doc | cv_extract F1 | Docling F1 |
|-----|---------------|------------|
| DE_01 | 0,882 | **0,882** (identisch) |
| DE_02 | 0,983 | **0,983** (identisch) |

Bei gleicher GT-Coverage ändert das Frontend die Qwen-Scores auf diesen Docs nicht. Volle EN-Diff-Messung + Phi: `LLM_IMPACT.json` nach Laufende.

Messung: Agent-VM — **nicht** i3/8‑GB Job-Object.

## KEEP

- Produktions-Frontend bleibt **`cv_extract`**.
- Docling bleibt Eval-Opt-in.
