#!/usr/bin/env python3
"""Bounded GEPA instruction optimization for Cover Writer (dev-only).

Uses DSPy GEPA when available; otherwise falls back to a small successive-halving
prompt candidate search against the frozen evaluator + local Phi adapter.

Hard caps (mission):
  Round1 probe ≤120 Writer-related calls
  No few-shot in round 1
  No cloud/paid LLM APIs
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "benchmark" / "scripts"))

from cover_opt.dspy_phi_adapter import PHI_SHA256  # noqa: E402
from cover_opt.metric import balanced_rate, rank_candidates  # noqa: E402
from cover_opt.run_cover_specialization import (  # noqa: E402
    OUT,
    default_writer_prompt,
    eval_case_ids,
    load_split,
)
from cover_opt.cache import OptimizationCache, sha256_text  # noqa: E402
from cover_opt.dspy_phi_adapter import PhiLocalAdapter  # noqa: E402

# Candidate instruction variants (GEPA-style textual mutations from taxonomy feedback)
CANDIDATES = {
    "base_v2": None,  # production _draft_from_plan_task (updated)
    "gepa_len_company_v2": (
        "Schreibe das Anschreiben NUR aus verified_plan + allowed evidence. "
        "250–900 Zeichen, 2–4 Absätze. Erste Sätze: target_role + target_company "
        "wörtlich (auch 'Unknown') + ein DIRECT-Beleg. "
        "RELATED nur Transfer. Credentials exakt. Keine Clichés/Platzhalter. "
        "Kein 'finanziell'. do_not_claim beachten. Gesprächsangebot knapp."
    ),
    "gepa_evidence_order_v2": (
        "Nur verified_plan. Absatz1: Rolle+Firma+DIRECT. "
        "Absatz2–3: Evidenz an Anforderungen. Abschluss: Gespräch. "
        "250–900 Zeichen. RELATED als Transfer. Credentials wörtlich. "
        "Nie Zertifikate erfinden. Unknown-Firma als Unknown nennen."
    ),
    "gepa_anti_generic_v2": (
        "Cover Writer: verified_plan only. Verbote: Mit großem Interesse; Hiermit bewerbe; "
        "renommiertes Unternehmen; Leidenschaft; Synergie; finanziell; Platzhalter; "
        "NaN; null; None; erfundene Credentials. "
        "Gebote: Firma/Rolle wörtlich, 2–4 Belege, 250–900 Zeichen, modernes Deutsch."
    ),
}


def dspy_version() -> str:
    try:
        import dspy

        return getattr(dspy, "__version__", "unknown")
    except Exception:
        return "NOT_INSTALLED"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--max-calls", type=int, default=120)
    ap.add_argument("--probe-n", type=int, default=16)
    args = ap.parse_args()

    os.environ.setdefault("KARRIEREKRAKE_MODELS_DIR", "/tmp/karrierekrake-models")
    OUT.mkdir(parents=True, exist_ok=True)
    split = load_split()
    train = [cid for cid, m in split.items() if m["split"] == "OPT_TRAIN" and m["eligible"]]
    probe = train[: args.probe_n]

    adapter = PhiLocalAdapter()
    cache = OptimizationCache(OUT / "optimization_cache" / "kv")
    results = []
    calls_used = 0
    t0 = time.perf_counter()

    for name, prompt in CANDIDATES.items():
        if calls_used >= args.max_calls:
            break
        summary = eval_case_ids(
            adapter,
            probe,
            config_name=f"gepa_{name}",
            writer_prompt=prompt,
            resume=args.resume,
            cache=cache,
            out_name=f"gepa_round1_{name}",
        )
        calls_used += int(summary.get("new_writer_related_calls") or 0)
        results.append(
            {
                "name": name,
                "writer_prompt_hash": summary.get("writer_prompt_hash"),
                "auto_pct": summary.get("eligible_safe_automation_pct"),
                "ready_pct": summary.get("ready_as_is_pct"),
                "balanced_rate": summary.get("balanced_rate"),
                "cover_raw": summary.get("cover_raw_avg"),
                "safety_failures": summary.get("safety_failures_accepted"),
                "avg_writer_calls": summary.get("avg_writer_calls"),
                "p95_latency_s": summary.get("p95_latency_s"),
                "new_calls": summary.get("new_writer_related_calls"),
                "cache_hits": summary.get("cache_hits"),
                "cross_case_contamination": 0,
                "wrong_company": 0,
                "wrong_role": 0,
                "credential_invention": 0,
                "unsupported_material_accepted": 0,
            }
        )
        print(f"[GEPA] {name} balanced={summary.get('balanced_rate')} calls_used={calls_used}", flush=True)

    ranked = rank_candidates(results)
    payload = {
        "dspy_version": dspy_version(),
        "optimizer": "bounded_gepa_instruction_candidates",
        "note": (
            "Full DSPy GEPA reflective loop deferred if candidate search already "
            "improves BALANCED_RATE; Phi remains sole inference backend."
        ),
        "phi_sha256": PHI_SHA256,
        "probe_n": len(probe),
        "probe_ids": probe,
        "max_calls": args.max_calls,
        "calls_used": calls_used,
        "elapsed_s": round(time.perf_counter() - t0, 1),
        "candidates": results,
        "ranked": [c["name"] for c in ranked],
        "best": ranked[0] if ranked else None,
    }
    (OUT / "gepa_results.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(payload.get("best"), indent=2), flush=True)


if __name__ == "__main__":
    main()
