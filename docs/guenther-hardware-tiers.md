# Günther — Hardware tiers & graceful degradation (Phase 5)

| Tier | Detection | Default model | Degradation |
|------|-----------|---------------|-------------|
| LIGHT | &lt;8 GB RAM or ≤2 CPUs | qwen3-1.7b | If missing/OOM → deterministic Karrierekrake only; UI „Günther nicht verfügbar“ |
| STANDARD | 8–16 GB typical | qwen3-4b | OOM → try LIGHT model → else heuristic/off |
| POWER | ≥24 GB RAM | qwen3-4b (optional higher quant later) | Same offline rules; no cloud |

Auto model = `graceful_model_fallback(detect_hardware().tier, "auto")`.
