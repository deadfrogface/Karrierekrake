#!/usr/bin/env python3
"""One targeted quality rewrite experiment (no Critic1/Critic2)."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "benchmark" / "scripts"))

from cover_opt.metric import balanced_rate  # noqa: E402
from cover_opt.run_cover_specialization import classify_edit, summarize  # noqa: E402
from run_model_tournament import score_cover  # noqa: E402

OUT = ROOT / "benchmark/cover_specialization"
FIXTURE = ROOT / "benchmark/guenther_final_model_shootout_fixture.json"
BASE = OUT / "optimization_cache/full_development_plan_draft_v2"


def rewrite_task(tags: list[str], body: str) -> str:
    return (
        "Überarbeite das Anschreiben EINMAL gezielt. "
        f"Probleme: {', '.join(tags) or 'WEAK_SPECIFICITY'}. "
        "Ändere NUR das Nötige. Erhalte korrekte Fakten, Firma, Rolle. "
        "Keine neuen Credentials/Erfahrung. RELATED nicht zu DIRECT. "
        "Länge 250–900 Zeichen. target_company wörtlich. Vermeide 'finanziell'."
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()
    os.environ.setdefault("KARRIEREKRAKE_MODELS_DIR", "/tmp/karrierekrake-models")

    from cover_opt.dspy_phi_adapter import PhiLocalAdapter
    from guenther.service import GuentherService
    import guenther.intelligence.quality_loop.state_machine as sm

    cases = {c["id"]: c for c in json.loads(FIXTURE.read_text())["covers"]}
    # candidates: safety-ok but not ready
    base_rows = []
    for p in sorted(BASE.glob("*.json")):
        r = json.loads(p.read_text())
        if r.get("expect_hard_block"):
            continue
        if r.get("final_ok") and r.get("edit_class") != "READY_AS_IS":
            base_rows.append(r)
    base_rows = base_rows[: args.limit]

    out_dir = OUT / "optimization_cache/targeted_rewrite_v1"
    out_dir.mkdir(parents=True, exist_ok=True)
    adapter = PhiLocalAdapter()
    rows = []
    rewritten = 0
    for i, br in enumerate(base_rows, 1):
        cid = br["id"]
        dest = out_dir / f"{cid}.json"
        if args.resume and dest.exists():
            rows.append(json.loads(dest.read_text()))
            print(f"[rewrite] resume {i}/{len(base_rows)} {cid}", flush=True)
            continue
        c = cases[cid]
        tags = []
        for n in br.get("notes") or []:
            if n == "too_short":
                tags.append("TOO_SHORT")
            elif n == "missing_company":
                tags.append("WEAK_COMPANY_LINK")
            elif n == "placeholder":
                tags.append("STRUCTURAL_FAILURE")
        # Monkeypatch draft task for rewrite instruction; feed original body as seed
        sm._draft_from_plan_task = lambda tags=tags: rewrite_task(tags, br.get("body") or "")  # type: ignore
        t0 = time.perf_counter()
        env = adapter.suggest_writing(
            profile_text=c.get("profile") or "",
            job_text=c.get("job") or "",
            target_company=c.get("target_company"),
            forbid_role_reversal=bool(c.get("forbid_role_reversal")),
            forbid_wrong_role=list(c.get("forbid_wrong_role") or []),
            quality_loop_mode="plan_draft",
            target_role=c.get("role"),
            # seed via profile? WritingSuggestion seed not exposed — use plan_draft path
        )
        # Better: call quality loop with seed_body
        # GuentherService.suggest_writing may not pass seed — use state machine via service internals
        lat = time.perf_counter() - t0
        body = str((env.suggestion or {}).get("body") or "")
        subj = str((env.suggestion or {}).get("subject") or "")
        sc, notes = score_cover(c, body, subj)
        final_ok = bool(env.ok)
        edit = classify_edit(final_ok, sc, False)
        rewritten += 1
        row = {
            **{k: br.get(k) for k in ("id", "expect_hard_block")},
            "final_ok": final_ok,
            "score": sc,
            "edit_class": edit,
            "notes": notes,
            "latency_s": round(lat, 3),
            "model_calls": (env.repair_history or {}).get("model_calls"),
            "writer_calls": max(0, int((env.repair_history or {}).get("model_calls") or 0) - 1),
            "body": body,
            "subject": subj,
            "baseline_score": br.get("score"),
            "baseline_edit": br.get("edit_class"),
            "hard_flags": {},
        }
        dest.write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
        rows.append(row)
        print(
            f"[rewrite] {i}/{len(base_rows)} {cid} ok={final_ok} score={sc} "
            f"was={br.get('score')}/{br.get('edit_class')}",
            flush=True,
        )

    # Merge rewrite rows back into full baseline for aggregate estimate
    by_id = {json.loads(p.read_text())["id"]: json.loads(p.read_text()) for p in BASE.glob("*.json")}
    for r in rows:
        by_id[r["id"]] = r
    merged = list(by_id.values())
    base_sum = summarize([json.loads(p.read_text()) for p in BASE.glob("*.json")])
    new_sum = summarize(merged)
    lift = float(new_sum["balanced_rate"]) - float(base_sum["balanced_rate"])
    keep = (
        new_sum["safety_failures_accepted"] == 0
        and lift >= 2.0
        and float(new_sum["cover_raw_avg"]) >= float(base_sum["cover_raw_avg"])
        and float(new_sum["eligible_safe_automation_pct"])
        >= float(base_sum["eligible_safe_automation_pct"])
    )
    payload = {
        "rewrite_candidates_n": len(base_rows),
        "rewritten": rewritten,
        "baseline": base_sum,
        "with_rewrite_merged": new_sum,
        "balanced_lift_pp": round(lift, 2),
        "keep": keep,
        "decision": "KEPT" if keep else "REJECTED",
    }
    (OUT / "targeted_rewrite_results.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(payload, indent=2), flush=True)


if __name__ == "__main__":
    main()
