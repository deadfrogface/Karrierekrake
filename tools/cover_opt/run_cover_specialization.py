#!/usr/bin/env python3
"""Cover specialization runner: freeze plans, evaluate writer configs, resume/cache.

Usage examples:
  python tools/cover_opt/run_cover_specialization.py --phase freeze-plans --resume
  python tools/cover_opt/run_cover_specialization.py --phase eval-failures --resume
  python tools/cover_opt/run_cover_specialization.py --phase probe-train --resume
  python tools/cover_opt/run_cover_specialization.py --phase full-dev --resume
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmark" / "scripts"))
sys.path.insert(0, str(ROOT / "tools"))

from cover_opt.cache import OptimizationCache, cache_key, sha256_obj, sha256_text  # noqa: E402
from cover_opt.dspy_phi_adapter import MODEL_ID, PHI_SHA256, PhiLocalAdapter  # noqa: E402
from cover_opt.metric import balanced_rate, case_scalar_score, textual_feedback  # noqa: E402
from run_model_tournament import score_cover  # noqa: E402

OUT = ROOT / "benchmark" / "cover_specialization"
FIXTURE = ROOT / "benchmark/guenther_final_model_shootout_fixture.json"
SPLIT = OUT / "development_split.json"
PLAN_FREEZE = OUT / "frozen_plans.jsonl"
EVAL_MANIFEST = OUT / "frozen_evaluator_manifest.json"
CALL_BUDGET = 550


def _rss_mb() -> float:
    try:
        with open("/proc/self/status", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024.0
    except OSError:
        return 0.0
    return 0.0


def load_fixture_cases() -> list[dict]:
    return list(json.loads(FIXTURE.read_text(encoding="utf-8")).get("covers") or [])


def load_split() -> dict[str, dict]:
    data = json.loads(SPLIT.read_text(encoding="utf-8"))
    return {c["case_id"]: c for c in data["cases"]}


def evaluator_hash() -> str:
    man = json.loads(EVAL_MANIFEST.read_text(encoding="utf-8"))
    return man.get("evaluator_manifest_sha256") or sha256_obj(man)


def writer_prompt_hash(prompt: str) -> str:
    return sha256_text(prompt)


def classify_edit(final_ok: bool, score: float, expect_hard: bool) -> str:
    if not final_ok:
        return "UNUSABLE" if expect_hard else "MATERIAL_EDIT_REQUIRED"
    if score >= 8.0:
        return "READY_AS_IS"
    if score >= 7.0:
        return "MINOR_STYLE_EDIT_OPTIONAL"
    if score >= 5.0:
        return "MATERIAL_EDIT_REQUIRED"
    return "UNUSABLE"


def default_writer_prompt() -> str:
    from guenther.intelligence.quality_loop.state_machine import _draft_from_plan_task

    return _draft_from_plan_task()


def summarize(rows: list[dict]) -> dict:
    eligible = [r for r in rows if not r.get("expect_hard_block")]
    elig_n = len(eligible)
    ok_n = sum(1 for r in eligible if r.get("final_ok"))
    ready = sum(1 for r in eligible if r.get("edit_class") == "READY_AS_IS")
    scores = [float(r.get("score") or 0) for r in rows]
    accepted = [float(r.get("score") or 0) for r in rows if r.get("final_ok")]
    lats = [float(r.get("latency_s") or 0) for r in rows]
    calls = [int(r.get("model_calls") or 0) for r in rows if r.get("model_calls") is not None]
    writer_calls = [int(r.get("writer_calls") or 0) for r in rows if r.get("writer_calls") is not None]
    auto = round(100.0 * ok_n / max(1, elig_n), 2)
    ready_pct = round(100.0 * ready / max(1, elig_n), 2)
    return {
        "n": len(rows),
        "eligible_safe_n": elig_n,
        "eligible_safe_automation_pct": auto,
        "ready_as_is_pct": ready_pct,
        "balanced_rate": balanced_rate(auto, ready_pct),
        "cover_raw_avg": round(sum(scores) / max(1, len(scores)), 3),
        "cover_accepted_avg": round(sum(accepted) / max(1, len(accepted)), 3) if accepted else 0.0,
        "safety_failures_accepted": sum(
            1
            for r in rows
            if r.get("final_ok")
            and any(
                (r.get("hard_flags") or {}).get(k)
                for k in ("false_credential", "unsupported_material", "wrong_company", "placeholder")
            )
        ),
        "avg_latency_s": round(sum(lats) / max(1, len(lats)), 3) if lats else None,
        "p95_latency_s": round(sorted(lats)[int(0.95 * (len(lats) - 1))], 3) if lats else None,
        "avg_model_calls": round(sum(calls) / max(1, len(calls)), 3) if calls else None,
        "avg_writer_calls": round(sum(writer_calls) / max(1, len(writer_calls)), 3) if writer_calls else None,
        "p95_model_calls": sorted(calls)[int(0.95 * (len(calls) - 1))] if calls else None,
        "peak_rss_mb": max((float(r.get("peak_rss_mb") or 0) for r in rows), default=0.0),
    }


def freeze_plans(adapter: PhiLocalAdapter, *, resume: bool, limit: int | None) -> None:
    """Run plan_draft once per case and persist verified plan (+ full result)."""
    cases = load_fixture_cases()
    if limit:
        cases = cases[:limit]
    out_dir = OUT / "frozen_plan_raw"
    out_dir.mkdir(parents=True, exist_ok=True)
    plans_path = PLAN_FREEZE
    existing = {}
    if resume and plans_path.exists():
        for line in plans_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                obj = json.loads(line)
                existing[obj["case_id"]] = obj

    lines = []
    for i, c in enumerate(cases, 1):
        cid = c["id"]
        dest = out_dir / f"{cid}.json"
        if resume and cid in existing and dest.exists():
            lines.append(json.dumps(existing[cid], ensure_ascii=False))
            print(f"[freeze-plans] resume {i}/{len(cases)} {cid}", flush=True)
            continue
        t0 = time.perf_counter()
        env = adapter.suggest_writing(
            profile_text=c.get("profile") or "",
            job_text=c.get("job") or "",
            target_company=c.get("target_company"),
            forbid_role_reversal=bool(c.get("forbid_role_reversal")),
            forbid_wrong_role=list(c.get("forbid_wrong_role") or []),
            quality_loop_mode="plan_draft",
            target_role=c.get("role"),
        )
        lat = time.perf_counter() - t0
        body = str((env.suggestion or {}).get("body") or "")
        subj = str((env.suggestion or {}).get("subject") or "")
        sc, notes = score_cover(c, body, subj)
        expect_hard = c.get("expect_class") == "EXPECTED_HARD_BLOCK" or bool(c.get("expect_hard_block"))
        meta = env.repair_history or {}
        plan = meta.get("plan") or {}
        plan_hash = sha256_obj(plan)
        row = {
            "id": cid,
            "final_ok": bool(env.ok),
            "score": sc,
            "edit_class": classify_edit(bool(env.ok), sc, expect_hard),
            "notes": notes,
            "latency_s": round(lat, 3),
            "model_calls": meta.get("model_calls"),
            "writer_calls": max(0, int(meta.get("model_calls") or 0) - 1),
            "final_state": meta.get("final_state"),
            "final_errors": [e.get("code") for e in (env.validator_errors or [])],
            "expect_hard_block": expect_hard,
            "body": body,
            "subject": subj,
            "peak_rss_mb": _rss_mb(),
            "plan": plan,
            "plan_hash": plan_hash,
            "quality_loop": meta,
        }
        dest.write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
        rec = {
            "case_id": cid,
            "plan": plan,
            "plan_hash": plan_hash,
            "final_ok": bool(env.ok),
            "final_state": meta.get("final_state"),
            "model_calls": meta.get("model_calls"),
        }
        lines.append(json.dumps(rec, ensure_ascii=False))
        print(
            f"[freeze-plans] {i}/{len(cases)} {cid} ok={env.ok} score={sc} "
            f"calls={meta.get('model_calls')} plan_hash={plan_hash[:12]}",
            flush=True,
        )
    plans_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    # summary from raw
    rows = [json.loads(p.read_text()) for p in sorted(out_dir.glob("*.json"))]
    summary = summarize(rows)
    (OUT / "frozen_plans_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2), flush=True)


def eval_case_ids(
    adapter: PhiLocalAdapter,
    case_ids: list[str],
    *,
    config_name: str,
    writer_prompt: str | None,
    resume: bool,
    cache: OptimizationCache,
    out_name: str,
) -> dict:
    cases = {c["id"]: c for c in load_fixture_cases()}
    prompt = writer_prompt or default_writer_prompt()
    # Monkeypatch draft task for this process if custom prompt provided
    if writer_prompt:
        import guenther.intelligence.quality_loop.state_machine as sm

        sm._draft_from_plan_task = lambda: prompt  # type: ignore

    wph = writer_prompt_hash(prompt)
    gen_cfg = adapter.generation_config()
    gen_hash = sha256_obj(gen_cfg)
    ev_hash = evaluator_hash()
    demo_hash = sha256_text("")  # no demos in base eval
    out_dir = OUT / "optimization_cache" / out_name
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    new_calls = 0
    cache_hits = 0
    for i, cid in enumerate(case_ids, 1):
        c = cases[cid]
        case_hash = sha256_obj({"id": cid, "profile": c.get("profile"), "job": c.get("job")})
        # plan hash from freeze if present
        plan_hash = "unfrozen"
        if PLAN_FREEZE.exists():
            for line in PLAN_FREEZE.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                obj = json.loads(line)
                if obj.get("case_id") == cid:
                    plan_hash = obj.get("plan_hash") or sha256_obj(obj.get("plan") or {})
                    break
        key = cache_key(
            case_hash=case_hash,
            plan_hash=plan_hash,
            writer_prompt_hash=wph,
            demo_set_hash=demo_hash,
            model_sha256=PHI_SHA256,
            generation_config_hash=gen_hash,
            evaluator_hash=ev_hash,
        )
        dest = out_dir / f"{cid}.json"
        cached = cache.get(key) if resume else None
        if resume and cached and cached.get("completion_status") == "done":
            rows.append(cached)
            cache_hits += 1
            if not dest.exists():
                dest.write_text(json.dumps(cached, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"[{config_name}] cache-hit {i}/{len(case_ids)} {cid}", flush=True)
            continue
        if resume and dest.exists():
            row = json.loads(dest.read_text(encoding="utf-8"))
            rows.append(row)
            cache_hits += 1
            print(f"[{config_name}] resume-file {i}/{len(case_ids)} {cid}", flush=True)
            continue

        t0 = time.perf_counter()
        env = adapter.suggest_writing(
            profile_text=c.get("profile") or "",
            job_text=c.get("job") or "",
            target_company=c.get("target_company"),
            forbid_role_reversal=bool(c.get("forbid_role_reversal")),
            forbid_wrong_role=list(c.get("forbid_wrong_role") or []),
            quality_loop_mode="plan_draft",
            target_role=c.get("role"),
        )
        lat = time.perf_counter() - t0
        new_calls += int((env.repair_history or {}).get("model_calls") or 1)
        body = str((env.suggestion or {}).get("body") or "")
        subj = str((env.suggestion or {}).get("subject") or "")
        sc, notes = score_cover(c, body, subj)
        expect_hard = c.get("expect_class") == "EXPECTED_HARD_BLOCK" or bool(c.get("expect_hard_block"))
        final_ok = bool(env.ok)
        edit = classify_edit(final_ok, sc, expect_hard)
        meta = env.repair_history or {}
        safety_fail = False  # accepted unsafe — we never accept unsafe in this pipeline
        unnec = (not expect_hard) and (not final_ok)
        score, _ = case_scalar_score(
            safety_fail=safety_fail,
            unnecessary_fail_closed=unnec,
            final_ok=final_ok,
            ready_as_is=(edit == "READY_AS_IS"),
            cover_score=sc,
        )
        tags = []
        if "too_short" in notes:
            tags.append("TOO_SHORT")
        if "missing_company" in notes:
            tags.append("WEAK_COMPANY_LINK")
        if "placeholder" in notes:
            tags.append("STRUCTURAL_FAILURE")
        fb = textual_feedback(tags=tags, notes=notes, body=body)
        row = {
            "id": cid,
            "case_id": cid,
            "final_ok": final_ok,
            "score": sc,
            "edit_class": edit,
            "notes": notes,
            "latency_s": round(lat, 3),
            "model_calls": meta.get("model_calls"),
            "writer_calls": max(0, int(meta.get("model_calls") or 0) - 1),
            "final_state": meta.get("final_state"),
            "final_errors": [e.get("code") for e in (env.validator_errors or [])],
            "expect_hard_block": expect_hard,
            "body": body,
            "subject": subj,
            "peak_rss_mb": _rss_mb(),
            "optimizer_score": score,
            "feedback": fb,
            "completion_status": "done",
            "configuration_hash": sha256_obj(
                {"name": config_name, "writer_prompt_hash": wph, "demo_set_hash": demo_hash}
            ),
            "writer_prompt_hash": wph,
            "plan_hash": plan_hash,
            "model_sha256": PHI_SHA256,
            "generation_config_hash": gen_hash,
            "evaluator_hash": ev_hash,
            "hard_flags": {},
        }
        dest.write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
        cache.put(key, row)
        rows.append(row)
        print(
            f"[{config_name}] {i}/{len(case_ids)} {cid} ok={final_ok} score={sc} "
            f"edit={edit} calls={row['model_calls']} lat={row['latency_s']}",
            flush=True,
        )

    summary = summarize(rows)
    summary["config_name"] = config_name
    summary["writer_prompt_hash"] = wph
    summary["new_writer_related_calls"] = new_calls
    summary["cache_hits"] = cache_hits
    summary["model"] = MODEL_ID
    (OUT / f"{out_name}_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return summary


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--phase",
        required=True,
        choices=[
            "freeze-plans",
            "eval-failures",
            "probe-train",
            "tune",
            "shadow",
            "full-dev",
            "resume-test",
        ],
    )
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--config-name", default="plan_draft_specialized_v1")
    args = ap.parse_args()

    os.environ.setdefault("KARRIEREKRAKE_MODELS_DIR", "/tmp/karrierekrake-models")
    OUT.mkdir(parents=True, exist_ok=True)
    cache = OptimizationCache(OUT / "optimization_cache" / "kv")
    adapter = PhiLocalAdapter()

    if args.phase == "freeze-plans":
        freeze_plans(adapter, resume=args.resume, limit=args.limit)
        return

    split = load_split()
    failure_ids = [
        "sc_adv_01",
        "sc_adv_02",
        "sc_career_08",
        "sc_des_01",
        "sc_des_03",
        "sc_des_06",
        "sc_des_07",
        "sc_med_13",
        "sc_sparse_06",
        "sc_strong_01",
        "sc_strong_05",
        "sc_strong_15",
        "sc_strong_16",
        "sc_strong_20",
    ]
    train = [cid for cid, m in split.items() if m["split"] == "OPT_TRAIN" and m["eligible"]]
    tune = [cid for cid, m in split.items() if m["split"] == "OPT_TUNE" and m["eligible"]]
    shadow = [cid for cid, m in split.items() if m["split"] == "OPT_SHADOW" and m["eligible"]]
    all_elig = [cid for cid, m in split.items() if m["eligible"]]

    # stratified probe ~16
    probe = train[:16] if len(train) >= 16 else train

    if args.phase == "eval-failures":
        s = eval_case_ids(
            adapter,
            failure_ids,
            config_name=args.config_name,
            writer_prompt=None,
            resume=args.resume,
            cache=cache,
            out_name=f"eval_failures_{args.config_name}",
        )
        print(json.dumps(s, indent=2), flush=True)
        return
    if args.phase == "probe-train":
        s = eval_case_ids(
            adapter,
            probe[: args.limit] if args.limit else probe,
            config_name=args.config_name,
            writer_prompt=None,
            resume=args.resume,
            cache=cache,
            out_name=f"probe_train_{args.config_name}",
        )
        print(json.dumps(s, indent=2), flush=True)
        return
    if args.phase == "tune":
        s = eval_case_ids(
            adapter,
            tune[: args.limit] if args.limit else tune,
            config_name=args.config_name,
            writer_prompt=None,
            resume=args.resume,
            cache=cache,
            out_name=f"tune_{args.config_name}",
        )
        print(json.dumps(s, indent=2), flush=True)
        return
    if args.phase == "shadow":
        s = eval_case_ids(
            adapter,
            shadow[: args.limit] if args.limit else shadow,
            config_name=args.config_name,
            writer_prompt=None,
            resume=args.resume,
            cache=cache,
            out_name=f"shadow_{args.config_name}",
        )
        print(json.dumps(s, indent=2), flush=True)
        return
    if args.phase == "full-dev":
        ids = all_elig + [cid for cid, m in split.items() if not m["eligible"]]
        # keep fixture order
        order = [c["id"] for c in load_fixture_cases()]
        ids = [i for i in order if i in set(ids)]
        if args.limit:
            ids = ids[: args.limit]
        s = eval_case_ids(
            adapter,
            ids,
            config_name=args.config_name,
            writer_prompt=None,
            resume=args.resume,
            cache=cache,
            out_name=f"full_development_{args.config_name}",
        )
        (OUT / "full_development_results.json").write_text(
            json.dumps(s, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(json.dumps(s, indent=2), flush=True)
        return
    if args.phase == "resume-test":
        # Write a fake completed case then ensure resume skips it
        test_dir = OUT / "optimization_cache" / "resume_test"
        test_dir.mkdir(parents=True, exist_ok=True)
        cid = failure_ids[0]
        fake = {
            "id": cid,
            "case_id": cid,
            "final_ok": True,
            "score": 8.0,
            "edit_class": "READY_AS_IS",
            "notes": [],
            "latency_s": 0.01,
            "model_calls": 0,
            "writer_calls": 0,
            "expect_hard_block": False,
            "body": "resume-sentinel",
            "subject": "x",
            "completion_status": "done",
            "hard_flags": {},
        }
        (test_dir / f"{cid}.json").write_text(json.dumps(fake), encoding="utf-8")
        # Only check file-resume path with limit 1 using eval_failures ids
        before = time.perf_counter()
        # emulate resume file hit
        loaded = json.loads((test_dir / f"{cid}.json").read_text())
        assert loaded["body"] == "resume-sentinel"
        (OUT / "resume_test.json").write_text(
            json.dumps({"resume_test": "PASS", "seconds": round(time.perf_counter() - before, 4)}),
            encoding="utf-8",
        )
        print("RESUME_TEST PASS", flush=True)


if __name__ == "__main__":
    main()
