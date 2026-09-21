# Günther — Hardware tiers & graceful degradation (Phase 5)

> **NEXT-01:** Binding target is **ONE Phi model** with unavailable/manual path — not Qwen fallback.  
> See [`docs/architecture/canonical-product-decisions.md`](architecture/canonical-product-decisions.md).  
> **PR19 freeze note:** Current *recommended* primary for STANDARD/POWER is **Phi-4-mini**; LIGHT still falls back to **Qwen3-1.7B** in code (CHANGE required). Historical rows below may describe earlier Qwen Autopick.



| Tier | Detection | Default model | Degradation |
|------|-----------|---------------|-------------|
| LIGHT | &lt;8 GB RAM or ≤2 CPUs | qwen3-1.7b | If missing/OOM → deterministic Karrierekrake only; UI „Günther nicht verfügbar“ |
| STANDARD | 8–16 GB typical | qwen3-4b | OOM → try LIGHT model → else heuristic/off |
| POWER | ≥24 GB RAM | qwen3-4b (optional higher quant later) | Same offline rules; no cloud |

Auto model = `graceful_model_fallback(detect_hardware().tier, "auto")`.
