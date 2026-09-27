# KEEP / REVERT — One-Model Dual-Use Iterationen

**Branch:** `cursor/one-model-cv-write-d85b`  
Alle Metriken: **Known Dev/Regression**, kein unabhängiger Blind.

| ID | Änderung | Korpus | Ergebnis | Entscheidung |
|----|----------|--------|----------|--------------|
| SG-1 | Soft-Grounding Skills/Software/Zertifikate via `evidence_in_source` | SMOKE Sollwerte | Qwen F1 −0,005; Phi F1 −0,005; invented 7→8 | **REVERT** |
| FE-1 | Produktions-Frontend = `cv_extract` (Docling Eval-only) | SMOKE Text | Jaccard 0,986; GT-Coverage identisch 0,945 | **KEEP** |
| MM-1 | Sole production id `qwen3.5-4b` (Catalog/Settings/Routing) | Unit-Tests | 64 focused tests grün | **KEEP** |
| PKG-1 | #96 Packaging/Auto-LLM/Child-Fehlercodes (übernommen) | Unit + Linux Child DE_01 | Child `ok=True` Agent-VM; Windows-EXE E2E offen | **KEEP** (mit offenen Gates) |
| WR-1 | Write-Bakeoff → Qwen statt Phi als Schreibmodell | n=4 Known | Qwen 0 invented, lesbar; Phi JSON-Leak | **KEEP** (provisorisch) |

## Fehlerklassen (Sollwerte-Rescore, Known)

Häufig: Zertifikate/Software missing oder scorer-seitig „invented“; DE_02 Layout bei Phi kritisch (wrong edu/emp). Textverlust Frontend ≠ Ursache auf SMOKE (Coverage gleich).

## Stop-Regel

SG-1 gestoppt — kein allgemeiner Gewinn; keine dokumentbezogenen Sonderregeln nachgeschoben.
