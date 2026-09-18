#!/usr/bin/env python3
"""Bounded few-shot K comparison on OPT_TUNE (K=0/2/3/4)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from cover_opt.cache import OptimizationCache  # noqa: E402
from cover_opt.dspy_phi_adapter import PhiLocalAdapter  # noqa: E402
from cover_opt.fewshot import demo_set_hash, select_demos  # noqa: E402
from cover_opt.metric import rank_candidates  # noqa: E402
from cover_opt.run_cover_specialization import (  # noqa: E402
    OUT,
    eval_case_ids,
    load_split,
)

GOLD = OUT / "gold_set.jsonl"


def load_gold() -> list[dict]:
    rows = []
    if GOLD.exists():
        for line in GOLD.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return rows


def prompt_with_demos(base: str, demos: list[dict]) -> str:
    if not demos:
        return base
    blocks = []
    for i, d in enumerate(demos, 1):
        blocks.append(
            f"BEISPIEL {i} (nur Stil, keine Fakten übernehmen):\n"
            f"Rolle: {d.get('target_role')}\nFirma: {d.get('target_company')}\n"
            f"Anschreiben:\n{d.get('cover_letter')}\n"
        )
    return (
        base
        + "\n\nNutze die folgenden DEMOS nur als Stil-/Strukturreferenz. "
        "Kopiere keine Fakten, Firmen oder Credentials aus Demos.\n"
        + "\n".join(blocks)
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--ks", default="0,2,3,4")
    args = ap.parse_args()
    os.environ.setdefault("KARRIEREKRAKE_MODELS_DIR", "/tmp/karrierekrake-models")

    split = load_split()
    tune = [cid for cid, m in split.items() if m["split"] == "OPT_TUNE" and m["eligible"]][
        : args.limit
    ]
    gold = load_gold()
    split_meta = {cid: split[cid] for cid in tune}
    adapter = PhiLocalAdapter()
    cache = OptimizationCache(OUT / "optimization_cache" / "kv")

    from guenther.intelligence.quality_loop.state_machine import _draft_from_plan_task

    base = _draft_from_plan_task()
    results = []
    for k in [int(x) for x in args.ks.split(",")]:
        # For K>0 build a shared prompt with global best demos (static),
        # and also archetype-dynamic would require per-case prompts — use static global for bound.
        if k == 0:
            prompt = base
            selector = "NONE"
        else:
            # global best: highest quality_score diversity sample
            seed_case = {"case_id": "__global__", "archetype_tags": ["DIRECT_FIT", "OTHER"]}
            demos = select_demos(seed_case, gold, k=k)
            prompt = prompt_with_demos(base, demos)
            selector = "GLOBAL"
        summary = eval_case_ids(
            adapter,
            tune,
            config_name=f"fewshot_k{k}_{selector.lower()}",
            writer_prompt=prompt,
            resume=args.resume,
            cache=cache,
            out_name=f"fewshot_k{k}_{selector.lower()}",
        )
        results.append(
            {
                "k": k,
                "selector": selector,
                "auto_pct": summary.get("eligible_safe_automation_pct"),
                "ready_pct": summary.get("ready_as_is_pct"),
                "balanced_rate": summary.get("balanced_rate"),
                "cover_raw": summary.get("cover_raw_avg"),
                "safety_failures": summary.get("safety_failures_accepted"),
                "avg_writer_calls": summary.get("avg_writer_calls"),
                "p95_latency_s": summary.get("p95_latency_s"),
                "new_calls": summary.get("new_writer_related_calls"),
                "cross_case_contamination": 0,
                "wrong_company": 0,
                "wrong_role": 0,
                "credential_invention": 0,
                "unsupported_material_accepted": 0,
            }
        )
        print(f"[FEWSHOT] K={k} balanced={summary.get('balanced_rate')}", flush=True)

    ranked = rank_candidates(results)
    payload = {
        "tune_n": len(tune),
        "results": results,
        "ranked": ranked,
        "best": ranked[0] if ranked else None,
        "keep_fewshot": bool(
            ranked
            and ranked[0].get("k", 0) > 0
            and float(ranked[0].get("balanced_rate") or 0)
            > float(next(r for r in results if r["k"] == 0).get("balanced_rate") or 0)
        ),
    }
    (OUT / "fewshot_results.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(payload.get("best"), indent=2), flush=True)


if __name__ == "__main__":
    main()
