# PHI_EXTRACTION_REMOVAL_AUDIT

Stand: Branch `cursor/holdout-100-d85b` @ `5f4127d`  
Entscheidung: PHI_EXTRACT aus produktivem CV-Import entfernen; PHI_WRITE erhalten.

| Fundstelle | aktuelle Funktion | EXTRACT oder WRITE | produktiv erreichbar? | Aktion | Begründung |
| ---------- | ----------------- | ------------------ | --------------------: | ------ | ---------- |
| `core/cv_intelligence.py` `import_cv_canonical` | DET only; ignoriere `guenther_*` | EXTRACT | ja | REMOVE (Phi-Zweig) **DONE** | Messungen: DET besser; kein Fallback |
| `core/cv_intelligence.py` `reconcile_phi_into_parsed` | Phi-Lücken füllen | EXTRACT | nein (nur historisch) | KEEP_FOR_HISTORICAL_EVALUATION | Tests/Holdout-Scripts |
| `core/cv_parser.py` `import_cv` | Wrapper → canonical DET | EXTRACT | ja | REFACTOR_SHARED_COMPONENT **DONE** | Parameter ignorieren, nur DET |
| `desktop/widgets/cv_import_dialog.py` | `import_cv(..., guenther_enabled=False)` | EXTRACT | ja | REMOVE (Phi-Pfad) **DONE** | Import darf Günther nicht triggern |
| `desktop/widgets/cv_import_dialog.py` Preview Pipeline | DET-Status | EXTRACT | ja | REMOVE / REFACTOR **DONE** | `cv_import.pipeline_det` |
| `desktop/pages/settings.py` Günther-Toggle | Modell für Günther | WRITE (überladen) | ja | KEEP_FOR_WRITE + Docs | Toggle bleibt für Schreiben |
| `desktop/i18n.py` `settings.guenther_hint` | Hint erwähnt Extraktion unklar | beide | ja | REFACTOR_SHARED_COMPONENT | Klar: nur Schreiben |
| `guenther/service.py` `suggest_cv_extract` / `_split` | PHI_EXTRACT Inference | EXTRACT | nur wenn aufgerufen | KEEP_FOR_HISTORICAL_EVALUATION | Holdout/Baseline-Scripts |
| `guenther/prompts.py` `SYSTEM_PHI_EXTRACT` | Extract-Systemprompt | EXTRACT | indirekt | KEEP_FOR_HISTORICAL_EVALUATION | Writer-Prompt getrennt halten |
| `guenther/prompts.py` `SYSTEM_PHI_WRITE` | Schreib-Systemprompt | WRITE | ja | KEEP_FOR_WRITE | Anschreiben etc. |
| `guenther/validation.py` `validate_cv_extract` | Grounding für Extract | EXTRACT | indirekt | KEEP_FOR_HISTORICAL_EVALUATION | |
| `guenther/intelligence/routing.py` `cv_extract` capability | Routing | EXTRACT | indirekt | REFACTOR_SHARED_COMPONENT | Capability bleibt historisch; Produktion ruft nicht |
| `guenther/service.py` writing / plan / draft | PHI_WRITE | WRITE | ja | KEEP_FOR_WRITE | |
| `scripts/run_holdout_100_predictions.py` Phi/C1 pipes | Evaluation | EXTRACT | nein (eval) | KEEP_FOR_HISTORICAL_EVALUATION | Frozen Holdout |
| `scripts/run_phi_extraction_baseline.py` | Baseline | EXTRACT | nein | KEEP_FOR_HISTORICAL_EVALUATION | |
| `tests/test_phi_extract_pipeline.py` | Extract-Tests | EXTRACT | nein | KEEP_FOR_HISTORICAL_EVALUATION + neue Negativtests | |
| `tests/test_next02_phi_cv.py` `phi_invoked` | erwartete Phi-Import | EXTRACT | nein | REFACTOR | muss „nie aufrufen“ beweisen |
| `tests/test_phi_write_no_hallucination.py` | Writer | WRITE | nein | KEEP_FOR_WRITE | |
| `docs/project/HOLDOUT_100_*.md` / PHI reports | Historie | — | nein | KEEP_FOR_HISTORICAL_EVALUATION | Marker setzen |
| `artifacts/holdout_100/*` | Predictions/Metriken | — | nein | KEEP_FOR_HISTORICAL_EVALUATION | |

## Nicht betroffen (WRITE / Produkt unrelated)

* Cover-Letter-Pipeline, Günther Quality Loop, Model Manager Download (für Writer)
* Job-Remote `hybrid` Flags (Wort „hybrid“ ≠ Extraktions-Hybrid)

## Produktiver Extraktionspfad nach Removal

```text
import_cv / import_cv_canonical
  → extract_text
  → parse_cv_text
  → apply_verify_repair_pipeline (deterministisch)
  → kein Phi, kein C1
```
