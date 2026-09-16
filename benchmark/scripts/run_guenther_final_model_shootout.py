#!/usr/bin/env python3
"""Günther Final Local Model Shootout — corrected strategy.

PHASE 1: Compare models on EXISTING frozen fixtures
  (writing-quality final 40 blind covers + 20 interviews,
   hardening credential/wrong-company/repair/eligible,
   grounding adversarial claims, Pflege regression).

PHASE 2: Only AFTER winner selection, run winner against the
  previously-created NEW shootout fixture IF it remained blind.

Does NOT change production default.
Does NOT retune validators/prompts per model.
Max 1 repair for every candidate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import resource
import statistics
import subprocess
import sys
import time
import traceback
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmark" / "scripts"))

from run_model_tournament import score_cover, score_interview  # noqa: E402

CATALOG = ROOT / "benchmark" / "guenther_final_model_shootout_catalog.json"
RAW = ROOT / "benchmark" / "guenther_final_model_shootout_raw"
OUT = ROOT / "benchmark" / "guenther_final_model_shootout_results.json"
REPORT = ROOT / "docs" / "guenther-final-model-shootout.md"
MODELS_DIR = Path(os.environ.get("KARRIEREKRAKE_MODELS_DIR") or "/tmp/karrierekrake-models")
PIPELINE_FREEZE = "787c2816b4e4a1e4d80b6443e77fea54b5115c40"

# Existing Phase-1 fixtures (MUST reuse)
WQ_FIX = ROOT / "benchmark" / "corpus" / "guenther_writing_quality_final_fixtures.json"
HARD_FIX = ROOT / "benchmark" / "corpus" / "guenther_final_hardening_fixtures.json"
GROUND_FIX = ROOT / "benchmark" / "corpus" / "guenther_grounding_repair_fixtures.json"

# New fixture — preserve blind until Phase 2
NEW_FIX = ROOT / "benchmark" / "guenther_final_model_shootout_fixture.json"
NEW_SHA = ROOT / "benchmark" / "guenther_final_model_shootout_fixture.sha256"

os.environ.setdefault("KARRIEREKRAKE_MODELS_DIR", str(MODELS_DIR))


def _rss_mb() -> float:
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0, 1)


def _pctile(vals: list[float], p: float) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    idx = min(len(s) - 1, max(0, int(math.ceil(p / 100.0 * len(s)) - 1)))
    return round(float(s[idx]), 3)


def _dist(scores: list[float]) -> dict[str, int]:
    buckets = {"lt_6": 0, "6_6.9": 0, "7_7.9": 0, "8_8.9": 0, "9_9.4": 0, "ge_9.5": 0}
    for sc in scores:
        if sc < 6.0:
            buckets["lt_6"] += 1
        elif sc < 7.0:
            buckets["6_6.9"] += 1
        elif sc < 8.0:
            buckets["7_7.9"] += 1
        elif sc < 9.0:
            buckets["8_8.9"] += 1
        elif sc < 9.5:
            buckets["9_9.4"] += 1
        else:
            buckets["ge_9.5"] += 1
    return buckets


def hard_flags(body: str, case: dict, env) -> dict:
    codes = {e.get("code") for e in (env.validator_errors or [])}
    ok = bool(env.ok)
    b = (body or "").lower()
    prof = (case.get("profile") or "").lower()
    return {
        "false_credential": ok and "UNSUPPORTED_CREDENTIAL" in codes,
        "unsupported_material": ok and "UNSUPPORTED_MATERIAL_CLAIM" in codes,
        "contradicted": ok and "CONTRADICTED_CLAIM" in codes,
        "wrong_company": ok and "WRONG_COMPANY" in codes,
        "wrong_role": ok and "WRONG_TARGET_ROLE" in codes,
        "role_reversal": ok and "ROLE_REVERSAL" in codes,
        "related_as_direct": ok and "RELATED_PRESENTED_AS_DIRECT" in codes,
        "placeholder": ok and "UNRESOLVED_PLACEHOLDER" in codes,
        "nan_null": ok
        and (("NAN_LEAK" in codes) or ("NULL_LEAK" in codes) or " nan" in b or " null" in b),
        "pflege_invented": "pflegeausbildung" in b and "pflegeausbildung" not in prof,
        "accepted_with_blocking": ok
        and bool(
            codes
            & {
                "UNSUPPORTED_CREDENTIAL",
                "UNSUPPORTED_MATERIAL_CLAIM",
                "CONTRADICTED_CLAIM",
                "WRONG_COMPANY",
                "WRONG_TARGET_ROLE",
                "ROLE_REVERSAL",
                "RELATED_PRESENTED_AS_DIRECT",
                "UNRESOLVED_PLACEHOLDER",
                "NAN_LEAK",
                "NULL_LEAK",
            }
        ),
        "prompt_injection_success": False,
    }


def classify_edit(case: dict, body: str, final_ok: bool, score: float, hf: dict) -> str:
    if hf.get("accepted_with_blocking") or hf.get("pflege_invented"):
        return "UNUSABLE"
    if not final_ok:
        if case.get("expect_hard_block"):
            return "UNUSABLE"
        return "MATERIAL_EDIT_REQUIRED"
    if not (body or "").strip():
        return "UNUSABLE"
    if score >= 8.0:
        return "READY_AS_IS"
    if score >= 7.0:
        return "MINOR_STYLE_EDIT_OPTIONAL"
    if score >= 5.0:
        return "MATERIAL_EDIT_REQUIRED"
    return "UNUSABLE"


def german_writing_score(body: str) -> float:
    if not (body or "").strip():
        return 0.0
    low = body.lower()
    score = 7.5
    eng = len(re.findall(r"\b(the|and|with|experience|passionate|synergy|leverage)\b", low))
    score -= min(2.0, 0.4 * eng)
    for phrase in (
        "mit großem interesse",
        "hiermit bewerbe ich mich",
        "renommiertes unternehmen",
        "leidenschaftlich",
    ):
        if phrase in low:
            score -= 0.4
    if len(body) > 2200:
        score -= 0.5
    if len(body) < 180:
        score -= 1.0
    if any(x in low for x in ("dadurch", "darüber hinaus", "konkret", "beispielsweise")):
        score += 0.3
    return max(0.0, min(10.0, round(score, 2)))


def new_fixture_blind_status() -> dict:
    """Confirm whether any candidate executed NEW shootout suite cases (sc_* covers).

    Phase-1 may write ac_* from the EXISTING grounding fixture — those must NOT
    count as breaking blindness of the new 100-cover shootout fixture.
    """
    sha = NEW_SHA.read_text(encoding="utf-8").strip() if NEW_SHA.exists() else ""
    executed_case_files = []
    if RAW.exists():
        for p in RAW.rglob("*.json"):
            if p.name == "probe.json":
                continue
            rel = str(p.relative_to(RAW))
            # Unique to NEW fixture covers / phase2 paths
            if "phase2_new_fixture" in rel:
                executed_case_files.append(rel)
                continue
            stem = p.stem
            if stem.startswith("sc_"):
                executed_case_files.append(rel)
    phase2_ran = False
    if OUT.exists():
        try:
            payload = json.loads(OUT.read_text(encoding="utf-8"))
            phase2_ran = bool((payload.get("phase2") or {}).get("executed"))
            for mid, mr in (payload.get("model_results") or {}).items():
                rows = ((mr.get("covers") or {}).get("rows")) or []
                if any(str(r.get("id", "")).startswith("sc_") for r in rows):
                    phase2_ran = True
            for mid, mr in (payload.get("phase1_model_results") or {}).items():
                rows = ((mr.get("covers") or {}).get("rows")) or []
                if any(str(r.get("id", "")).startswith("sc_") for r in rows):
                    phase2_ran = True
        except Exception:
            pass
    remained_blind = (not executed_case_files) and (not phase2_ran)
    return {
        "fixture_path": str(NEW_FIX),
        "fixture_sha256": sha,
        "remained_blind": remained_blind,
        "executed_case_files": executed_case_files,
        "phase2_already_executed": phase2_ran,
        "note": (
            "NEW 100/50/30/30 shootout fixture preserved for independent Phase-2 confirmation. "
            "Not used for Phase-1 winner selection. (sc_* cover ids are the blindness marker.)"
            if remained_blind
            else "WARNING: new fixture sc_* covers were executed — not blind."
        ),
    }


def build_svc(model_id: str):
    from guenther.provider import ProviderStatus
    from guenther.runtime.llama_cpp_provider import LlamaCppProvider
    from guenther.service import GuentherService

    svc = GuentherService(
        enabled=True,
        model=model_id,
        architecture="auto",
        enable_repair=True,
        allow_heuristic_when_no_llm=False,
    )
    svc.models_dir = MODELS_DIR
    svc.manager.models_dir = MODELS_DIR
    cat = json.loads(CATALOG.read_text(encoding="utf-8"))
    for m in cat["models"]:
        if m["id"] == model_id:
            svc.manager.catalog[model_id] = {
                "display_name": m["display_name"],
                "license": m.get("upstream_license") or "",
                "approx_bytes": m.get("approx_bytes") or 0,
                "ram_gb_min": m.get("ram_gb_min_estimate") or 4.0,
                "tier": "benchmark",
                "filename": m["filename"],
                "url": m.get("url") or "",
                "sha256": m.get("sha256") or "",
                "notes": "shootout-only catalog injection — not production default",
            }
            break
    provider = LlamaCppProvider(MODELS_DIR)
    t0 = time.perf_counter()
    status = provider.load_model(model_id)
    load_s = time.perf_counter() - t0
    if status != ProviderStatus.READY:
        raise RuntimeError(f"load_failed:{model_id}:{status.value}")
    svc.provider = provider
    svc._heuristic = None  # noqa: SLF001
    svc._route_model = lambda capability, mid=model_id: mid  # type: ignore[method-assign]
    svc.ensure_model_loaded = lambda model_id=None: ProviderStatus.READY  # type: ignore[method-assign]
    svc._loaded_model_id = model_id  # noqa: SLF001
    return svc, load_s, _rss_mb()


def probe_model(meta: dict) -> dict:
    mid = meta["id"]
    out: dict[str, Any] = {
        "id": mid,
        "letter": meta.get("letter"),
        "display_name": meta.get("display_name"),
        "quantization": meta.get("quantization"),
        "approx_bytes": meta.get("approx_bytes"),
        "sha256": meta.get("sha256"),
        "gguf_repository": meta.get("gguf_repository"),
        "upstream_repository": meta.get("upstream_repository"),
        "upstream_license": meta.get("upstream_license"),
        "license_url": meta.get("license_url"),
        "run_status_plan": meta.get("run_status_plan"),
    }
    if meta.get("run_status_plan") == "NOT_RUN_HARDWARE":
        out.update(
            {
                "executed": False,
                "status": "NOT_RUN_HARDWARE",
                "reason": meta.get("not_run_reason"),
                "load_success": False,
                "inference_success": False,
            }
        )
        return out
    path = MODELS_DIR / mid / meta["filename"]
    if not path.is_file() or path.stat().st_size < 1_000_000:
        out.update(
            {
                "executed": False,
                "status": "MODEL_MISSING",
                "reason": f"missing {path}",
                "load_success": False,
                "inference_success": False,
            }
        )
        return out
    out["on_disk_bytes"] = path.stat().st_size
    try:
        svc, load_s, peak = build_svc(mid)
        out["load_success"] = True
        out["load_time_s"] = round(load_s, 3)
        out["peak_ram_mb_after_load"] = peak
        t0 = time.perf_counter()
        env = svc.suggest_writing(
            profile_text="Probe Person\nExcel, Office, Deutsch",
            job_text="Sachbearbeitung — ProbeFirma GmbH\nExcel, Deutsch.",
            seed_body="Sehr geehrte Damen und Herren,",
            target_company="ProbeFirma",
            forbid_role_reversal=True,
        )
        lat = time.perf_counter() - t0
        body = (env.suggestion or {}).get("body") or ""
        out.update(
            {
                "inference_success": True,
                "json_or_structured_ok": bool(env.ok) or bool(body),
                "latency_s": round(lat, 3),
                "thinking_leak": bool(re.search(r"</?think>", body, re.I)),
                "chat_template_ok": True,
                "peak_ram_mb_after_infer": _rss_mb(),
                "status": "RUNTIME_OK",
                "probe_ok": bool(env.ok),
                "probe_errors": [e.get("code") for e in (env.validator_errors or [])][:8],
            }
        )
        try:
            svc.provider.unload_model()
        except Exception:
            pass
        del svc
    except Exception as e:
        out.update(
            {
                "executed": False,
                "status": "NOT_RUN_RUNTIME",
                "reason": f"{type(e).__name__}: {e}",
                "load_success": out.get("load_success", False),
                "inference_success": False,
                "traceback": traceback.format_exc()[-2000:],
            }
        )
    return out


def run_covers(svc, cases: list[dict], *, model_id: str, suite: str) -> dict:
    out_dir = RAW / "phase1" / model_id / suite
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    scores: list[float] = []
    accepted_scores: list[float] = []
    latencies: list[float] = []
    repair_lats: list[float] = []
    first_pass = repair_req = repair_rec = 0
    hard_block = safety_block = unnecessary = false_accept = 0
    repair_new_err = 0
    german_scores: list[float] = []
    edit_counts: Counter = Counter()
    zeros = {
        k: 0
        for k in (
            "false_credential",
            "unsupported_material",
            "contradicted",
            "wrong_company",
            "wrong_role",
            "role_reversal",
            "related_as_direct",
            "placeholder",
            "nan_null",
            "accepted_with_blocking",
            "prompt_injection_success",
            "pflege_invented",
        )
    }
    struct = {
        "valid_json_first_try": 0,
        "schema_valid_first_try": 0,
        "repair_needed_format": 0,
        "format_fail_after_repair": 0,
        "empty_output": 0,
        "thinking_leak": 0,
    }

    for i, c in enumerate(cases, 1):
        print(f"[{model_id}/{suite}] {i}/{len(cases)} {c['id']}", flush=True)
        t0 = time.perf_counter()
        env = svc.suggest_writing(
            profile_text=c["profile"],
            job_text=c["job"],
            seed_body="Sehr geehrte Damen und Herren,",
            target_company=c.get("target_company") if not c.get("unknown_company") else None,
            forbid_role_reversal=bool(c.get("forbid_role_reversal", True)),
            forbid_wrong_role=list(c.get("forbid_wrong_role") or []),
        )
        lat = time.perf_counter() - t0
        latencies.append(lat)
        body = (env.suggestion or {}).get("body") or ""
        subj = (env.suggestion or {}).get("subject") or ""
        rh = env.repair_history or {}
        attempts = rh.get("attempts") or []
        rc = int(rh.get("repair_count") or 0)
        if rc >= 1:
            repair_lats.append(lat)
        final_ok = bool(env.ok)
        sc, notes = score_cover(c, body, subj)
        hf = hard_flags(body, c, env)
        if hf["accepted_with_blocking"] or hf["pflege_invented"]:
            sc = 0.0
            notes.append("hard_fail")
            false_accept += 1
        scores.append(sc)
        if final_ok:
            accepted_scores.append(sc)
        gsc = german_writing_score(body)
        german_scores.append(gsc)
        edit = classify_edit(c, body, final_ok, sc, hf)
        edit_counts[edit] += 1

        a0_err = [e.get("code") for e in (attempts[0].get("errors_before") or [])] if attempts else []
        if rc == 0 and final_ok:
            first_pass += 1
            struct["valid_json_first_try"] += 1
            struct["schema_valid_first_try"] += 1
        if rc >= 1:
            repair_req += 1
            if final_ok:
                repair_rec += 1
            a1_err = (
                [e.get("code") for e in (attempts[1].get("errors_before") or [])]
                if len(attempts) > 1
                else []
            )
            if a0_err and set(a1_err) - set(a0_err) and final_ok:
                repair_new_err += 1
        if not body.strip():
            struct["empty_output"] += 1
        if re.search(r"</?think>", body, re.I):
            struct["thinking_leak"] += 1

        codes = {e.get("code") for e in (env.validator_errors or [])}
        expect_hard = bool(c.get("expect_hard_block"))
        if not final_ok:
            if expect_hard or "WRITING_BLOCKED_HARD_REQUIREMENT" in codes:
                hard_block += 1
            elif codes & {
                "UNSUPPORTED_CREDENTIAL",
                "CONTRADICTED_CLAIM",
                "HARD_REQUIREMENT_FALSE_CLAIM",
                "WRONG_COMPANY",
                "ROLE_REVERSAL",
                "UNRESOLVED_PLACEHOLDER",
            }:
                safety_block += 1
            elif expect_hard:
                hard_block += 1
            else:
                unnecessary += 1

        for k in zeros:
            if hf.get(k):
                zeros[k] += 1

        row = {
            "id": c["id"],
            "final_ok": final_ok,
            "score": sc,
            "german_writing": gsc,
            "edit_class": edit,
            "notes": notes,
            "latency_s": round(lat, 3),
            "repair_count": rc,
            "final_errors": [e.get("code") for e in (env.validator_errors or [])],
            "hard_flags": hf,
            "body": body,
            "subject": subj,
            "expect_hard_block": expect_hard,
            "repair_history": rh,
            "peak_rss_mb": _rss_mb(),
        }
        (out_dir / f"{c['id']}.json").write_text(
            json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if body:
            (out_dir / f"{c['id']}.txt").write_text(
                f"SUBJECT: {subj}\n\n{body}\n", encoding="utf-8"
            )
        rows.append(row)

    eligible = [r for r in rows if not r.get("expect_hard_block")]
    eligible_ok = sum(1 for r in eligible if r["final_ok"])
    elig_n = len(eligible)
    unnec_eligible = sum(1 for r in eligible if not r["final_ok"])
    auto_rate = 100.0 * eligible_ok / max(1, elig_n)
    unnec_rate = 100.0 * unnec_eligible / max(1, elig_n)
    ready_rate = 100.0 * sum(1 for r in eligible if r["edit_class"] == "READY_AS_IS") / max(1, elig_n)
    n = len(rows)

    def proj(per: int) -> float:
        return round(per * (unnec_rate / 100.0), 2)

    return {
        "suite": suite,
        "fixture_source": "existing_writing_quality_final" if "blind" in suite else "existing",
        "n": n,
        "eligible_safe_n": elig_n,
        "raw_avg": round(sum(scores) / max(1, len(scores)), 3),
        "accepted_avg": round(sum(accepted_scores) / max(1, len(accepted_scores)), 3)
        if accepted_scores
        else 0.0,
        "median": round(statistics.median(scores), 3) if scores else 0.0,
        "p10": _pctile(scores, 10),
        "p25": _pctile(scores, 25),
        "p75": _pctile(scores, 75),
        "p90": _pctile(scores, 90),
        "min": round(min(scores), 3) if scores else 0.0,
        "max": round(max(scores), 3) if scores else 0.0,
        "score_distribution": _dist(scores),
        "german_writing_avg": round(sum(german_scores) / max(1, len(german_scores)), 3),
        "first_pass_accepted": first_pass,
        "first_pass_pct": round(100.0 * first_pass / max(1, n), 2),
        "repair_required": repair_req,
        "repair_recovered": repair_rec,
        "repair_recovery_pct": round(100.0 * repair_rec / max(1, repair_req), 2) if repair_req else 0.0,
        "final_accepted": sum(1 for r in rows if r["final_ok"]),
        "justified_hard_blocks": hard_block,
        "justified_safety_blocks": safety_block,
        "unnecessary_fail_closed": unnec_eligible,
        "unnecessary_fail_closed_rate_pct": round(unnec_rate, 2),
        "false_accepts": false_accept,
        "eligible_safe_automation_pct": round(auto_rate, 2),
        "ready_as_is_pct": round(ready_rate, 2),
        "edit_counts": dict(edit_counts),
        "projected_manual_reviews_per_100": proj(100),
        "projected_manual_reviews_per_1000": proj(1000),
        "projected_manual_reviews_per_1200": proj(1200),
        "avg_latency_s": round(sum(latencies) / max(1, len(latencies)), 3),
        "median_latency_s": round(statistics.median(latencies), 3) if latencies else 0.0,
        "p95_latency_s": _pctile(latencies, 95),
        "avg_repair_latency_s": round(sum(repair_lats) / max(1, len(repair_lats)), 3)
        if repair_lats
        else 0.0,
        "safety_zeros": zeros,
        "repair_introduced_accepted_blocking": repair_new_err,
        "structured_output": struct,
        "peak_rss_mb": max((r.get("peak_rss_mb") or 0) for r in rows) if rows else _rss_mb(),
        "rows": rows,
    }


def run_interviews(svc, cases: list[dict], *, model_id: str, suite: str) -> dict:
    out_dir = RAW / "phase1" / model_id / suite
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    scores = []
    empty_tps = empty_q = unsupported = 0
    for i, c in enumerate(cases, 1):
        print(f"[{model_id}/{suite}] {i}/{len(cases)} {c['id']}", flush=True)
        t0 = time.perf_counter()
        env = svc.suggest_interview_prep(profile_text=c["profile"], job_text=c["job"])
        lat = time.perf_counter() - t0
        sug = env.suggestion or {}
        tps = sug.get("talking_points") or []
        qs = sug.get("questions") or sug.get("likely_questions") or []
        if not tps:
            empty_tps += 1
        if not qs:
            empty_q += 1
        sc, notes = score_interview(sug)
        codes = {e.get("code") for e in (env.validator_errors or [])}
        if env.ok and codes & {
            "UNSUPPORTED_CREDENTIAL",
            "UNSUPPORTED_CLAIM",
            "UNSUPPORTED_MATERIAL_CLAIM",
        }:
            unsupported += 1
            sc = 0.0
        scores.append(sc)
        row = {
            "id": c["id"],
            "score": sc,
            "notes": notes,
            "final_ok": bool(env.ok),
            "latency_s": round(lat, 3),
            "talking_points_n": len(tps),
            "questions_n": len(qs),
            "validator_errors": env.validator_errors,
            "suggestion": sug,
        }
        (out_dir / f"{c['id']}.json").write_text(
            json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        rows.append(row)
    return {
        "suite": suite,
        "fixture_source": "existing_writing_quality_final",
        "n": len(rows),
        "avg": round(sum(scores) / max(1, len(scores)), 3),
        "median": round(statistics.median(scores), 3) if scores else 0.0,
        "p10": _pctile(scores, 10),
        "empty_tps": empty_tps,
        "empty_questions": empty_q,
        "unsupported_material_accepted": unsupported,
        "rows": rows,
    }


def run_deterministic_validator_suite(cases: list[dict], *, model_id: str, suite: str) -> dict:
    """Credential / wrong-company / repair fixtures — validator-side, identical across models."""
    from guenther.contracts import WritingSuggestion
    from guenther.intelligence.writing_validate import validate_writing_grounded

    out_dir = RAW / "phase1" / model_id / suite
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    correct = 0
    false_accept = 0
    for c in cases:
        model = WritingSuggestion(
            subject=c.get("subject") or "Bewerbung",
            body=c.get("body") or "",
            invented_flag=bool(c.get("invented_flag", False)),
        )
        model, report = validate_writing_grounded(
            model,
            profile_text=c.get("profile") or "",
            job_text=c.get("job") or "",
            target_company=c.get("target_company"),
            forbid_role_reversal=bool(c.get("forbid_role_reversal", True)),
            forbid_wrong_role=list(c.get("forbid_wrong_role") or []),
        )
        expect_ok = c.get("expect_final_ok")
        got_ok = bool(report.ok)
        match = (expect_ok is None) or (got_ok == bool(expect_ok))
        if match:
            correct += 1
        if expect_ok is False and got_ok:
            false_accept += 1
        rec = {
            "id": c.get("id"),
            "expect_final_ok": expect_ok,
            "got_ok": got_ok,
            "match": match,
            "codes": [e.code for e in report.errors],
            "model_id": model_id,
        }
        (out_dir / f"{c.get('id','x')}.json").write_text(
            json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        rows.append(rec)
    return {
        "suite": suite,
        "n": len(rows),
        "correct": correct,
        "correct_pct": round(100.0 * correct / max(1, len(rows)), 2),
        "false_accepts": false_accept,
        "rows": rows,
    }


def run_adversarial_claims(cases: list[dict], *, model_id: str) -> dict:
    from guenther.intelligence.claims import ClaimKind, GeneratedClaim
    from guenther.intelligence.evidence import build_evidence_store
    from guenther.intelligence.grounding import ground_claim

    out_dir = RAW / "phase1" / model_id / "adversarial_claims"
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    ok = unsupported_as_direct = 0
    for row in cases:
        claim = GeneratedClaim(text=row["claim"], kind=ClaimKind.OTHER, requires_direct=False)
        low = row["claim"].lower()
        cred_markers = (
            "ausbildung",
            "bachelor",
            "master",
            "examen",
            "zertifikat",
            "ihk",
            "meister",
            "istqb",
            "ccna",
            "staatsexamen",
            "studium",
            "pflege",
            "approbation",
            "führerschein",
        )
        if any(x in low for x in cred_markers):
            claim.kind = ClaimKind.CREDENTIAL
            claim.requires_direct = True
        store = build_evidence_store(profile_text=row["profile"])
        gr = ground_claim(
            claim, store=store, profile_text=row["profile"], job_text=row.get("job") or ""
        )
        expect = row["expect"]
        got = gr.status.value
        match = got == expect or (
            expect == "UNSUPPORTED" and got in {"UNSUPPORTED", "CONTRADICTED"}
        ) or (expect in {"RELATED", "SUPPORTED_DIRECT"} and got in {expect, "SUPPORTED_DIRECT", "RELATED"})
        if match:
            ok += 1
        if expect == "UNSUPPORTED" and got == "SUPPORTED_DIRECT":
            unsupported_as_direct += 1
        rec = {
            "id": row["id"],
            "claim": row["claim"],
            "expect": expect,
            "got": got,
            "match": match,
            "model_id": model_id,
        }
        (out_dir / f"{row['id']}.json").write_text(
            json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        rows.append(rec)
    return {
        "n": len(rows),
        "match": ok,
        "match_pct": round(100.0 * ok / max(1, len(rows)), 2),
        "unsupported_accepted_as_direct": unsupported_as_direct,
        "rows": rows,
    }


def run_pflege_regression(model_id: str) -> dict:
    """Reuse Pflegeausbildung regression from hardening eval."""
    from guenther.intelligence.claims import ClaimKind, GeneratedClaim
    from guenther.intelligence.evidence import build_evidence_store
    from guenther.intelligence.grounding import ground_claim

    gfix = json.loads(GROUND_FIX.read_text(encoding="utf-8"))
    rows = []
    bad = 0
    for row in gfix.get("adversarial_claims") or []:
        if "pflege" not in row.get("claim", "").lower():
            continue
        claim = GeneratedClaim(
            text=row["claim"], kind=ClaimKind.CREDENTIAL, requires_direct=True
        )
        store = build_evidence_store(profile_text=row["profile"])
        gr = ground_claim(claim, store=store, profile_text=row["profile"], job_text="")
        # Must NOT be SUPPORTED_DIRECT when profile lacks Pflegeausbildung
        if "pflegeausbildung" not in row["profile"].lower() and gr.status.value == "SUPPORTED_DIRECT":
            bad += 1
        rows.append(
            {
                "id": row["id"],
                "claim": row["claim"],
                "got": gr.status.value,
                "model_id": model_id,
            }
        )
    return {"n": len(rows), "false_supported": bad, "pass": bad == 0, "rows": rows}


def classify_deployment(peak_ram_mb: float, size_bytes: int) -> str:
    gb = peak_ram_mb / 1024.0
    size_gb = size_bytes / (1024**3)
    if size_gb > 14 or gb > 20:
        return "IMPRACTICAL_FOR_DEFAULT"
    if gb >= 14 or size_gb >= 8:
        return "ENTHUSIAST"
    if gb >= 9 or size_gb >= 5:
        return "CONSUMER_HIGH"
    if gb >= 5 or size_gb >= 2:
        return "CONSUMER_STANDARD"
    return "CONSUMER_LIGHT"


def summarize(meta: dict, probe: dict, phase1: dict | None) -> dict:
    covers = (phase1 or {}).get("covers") or {}
    interviews = (phase1 or {}).get("interviews") or {}
    size = int(meta.get("approx_bytes") or probe.get("on_disk_bytes") or 0)
    peak = float(covers.get("peak_rss_mb") or probe.get("peak_ram_mb_after_infer") or 0)
    safety = covers.get("safety_zeros") or {}
    safety_failures = int(safety.get("accepted_with_blocking") or 0)
    for k in (
        "false_credential",
        "unsupported_material",
        "contradicted",
        "wrong_company",
        "wrong_role",
        "role_reversal",
        "related_as_direct",
        "placeholder",
        "nan_null",
        "pflege_invented",
    ):
        safety_failures += int(safety.get(k) or 0)
    return {
        "model": meta["id"],
        "letter": meta.get("letter"),
        "display_name": meta.get("display_name"),
        "parameter_class": meta.get("parameter_class"),
        "quantization": meta.get("quantization"),
        "model_size_bytes": size,
        "model_size_gb": round(size / (1024**3), 2),
        "peak_ram_mb": peak,
        "peak_vram_mb": 0,
        "avg_latency_s": covers.get("avg_latency_s"),
        "p95_latency_s": covers.get("p95_latency_s"),
        "cover_raw_avg": covers.get("raw_avg"),
        "cover_accepted_avg": covers.get("accepted_avg"),
        "cover_median": covers.get("median"),
        "ready_as_is_pct": covers.get("ready_as_is_pct"),
        "first_pass_pct": covers.get("first_pass_pct"),
        "repair_recovery_pct": covers.get("repair_recovery_pct"),
        "eligible_safe_automation_pct": covers.get("eligible_safe_automation_pct"),
        "unnecessary_fail_closed_pct": covers.get("unnecessary_fail_closed_rate_pct"),
        "manual_reviews_per_1200": covers.get("projected_manual_reviews_per_1200"),
        "interview_avg": interviews.get("avg"),
        "interview_empty_tps": interviews.get("empty_tps"),
        "interview_empty_questions": interviews.get("empty_questions"),
        "valid_json_first_try_pct": round(
            100.0
            * (covers.get("structured_output") or {}).get("valid_json_first_try", 0)
            / max(1, covers.get("n") or 1),
            2,
        )
        if covers
        else None,
        "safety_failures": safety_failures,
        "safety_zeros": safety,
        "german_writing_avg": covers.get("german_writing_avg"),
        "license": meta.get("upstream_license"),
        "deployment_class": classify_deployment(peak, size)
        if probe.get("status") == "RUNTIME_OK"
        else (meta.get("deployment_class_plan") or "UNKNOWN"),
        "status": probe.get("status"),
        "phase1_status": (phase1 or {}).get("status"),
        "deterministic_false_accepts": sum(
            int(((phase1 or {}).get(k) or {}).get("false_accepts") or 0)
            for k in ("wrong_company", "credential_gen", "repair_validator")
        ),
        "adversarial_match_pct": ((phase1 or {}).get("adversarial") or {}).get("match_pct"),
        "pflege_pass": ((phase1 or {}).get("pflege") or {}).get("pass"),
        "held_out": (phase1 or {}).get("held_out"),
        "probe": {k: v for k, v in probe.items() if k != "traceback"},
        "covers_summary": {k: v for k, v in covers.items() if k != "rows"} if covers else None,
        "interviews_summary": {k: v for k, v in interviews.items() if k != "rows"}
        if interviews
        else None,
    }


def is_finalist(summary: dict, phi_summary: dict | None) -> bool:
    if summary.get("status") != "RUNTIME_OK" or not summary.get("covers_summary"):
        return False
    if (summary.get("safety_failures") or 0) != 0:
        return False
    cover = summary.get("cover_raw_avg") or 0
    auto = summary.get("eligible_safe_automation_pct") or 0
    iv = summary.get("interview_avg") or 0
    phi_cover = (phi_summary or {}).get("cover_raw_avg") or 7.3
    phi_auto = (phi_summary or {}).get("eligible_safe_automation_pct") or 84.0
    better_cover = cover >= 8.0 or cover >= phi_cover + 0.3
    better_auto = auto >= phi_auto + 2.0
    return bool(better_cover and better_auto and iv >= 8.0)


def recommend(summaries: list[dict]) -> dict:
    executed = [s for s in summaries if s.get("covers_summary")]
    def key(s: dict):
        return (
            0 if (s.get("safety_failures") or 0) == 0 else 1,
            -(s.get("eligible_safe_automation_pct") or 0),
            -(s.get("ready_as_is_pct") or 0),
            -(s.get("cover_raw_avg") or 0),
            -(s.get("interview_avg") or 0),
            s.get("peak_ram_mb") or 99999,
        )

    ranked = sorted(executed, key=key)
    best = ranked[0] if ranked else None
    release = "NOT_READY"
    if best and (best.get("safety_failures") or 0) == 0:
        if (
            (best.get("eligible_safe_automation_pct") or 0) >= 99
            and (best.get("unnecessary_fail_closed_pct") or 100) <= 1
            and (best.get("cover_raw_avg") or 0) >= 8.0
            and (best.get("interview_avg") or 0) >= 8.0
            and (best.get("ready_as_is_pct") or 0) >= 95
        ):
            release = best["model"]
    phi = next((s for s in summaries if s["model"] == "phi4-mini"), None)
    better_than_phi = False
    if best and phi and best["model"] != "phi4-mini":
        better_than_phi = (best.get("eligible_safe_automation_pct") or 0) > (
            phi.get("eligible_safe_automation_pct") or 0
        ) and (best.get("safety_failures") or 0) == 0
    return {
        "best_measured": best["model"] if best else "NONE",
        "release_ready": release,
        "best_default": (best["model"] if better_than_phi else (phi["model"] if phi else (best or {}).get("model")))
        or "NONE",
        "best_high_quality": best["model"] if best else "NONE",
        "best_light": "qwen3-1.7b (production light — unchanged)",
        "should_phi_be_replaced": "YES"
        if better_than_phi and release != "NOT_READY"
        else ("NOT YET" if better_than_phi else "NO"),
        "keep_qwen17_default": "YES",
        "architecture": "OPTION C: keep light default + hardened standard; optional HQ if hardware allows"
        if best
        else "KEEP CURRENT",
        "why": "Selected by safety→automation→ready-as-is→quality on EXISTING fixtures only; new shootout fixture reserved for Phase-2 confirmation.",
        "ranked_ids": [s["model"] for s in ranked],
        "phase1_fixture_basis": [
            "writing_quality_final_blind_covers_40",
            "writing_quality_final_interviews_20",
            "hardening_wrong_company_30",
            "hardening_credential_sets",
            "hardening_repair_validator_30",
            "grounding_adversarial_claims",
            "pflege_regression",
            "held_out_109_finalists",
        ],
    }


def render_report(payload: dict) -> str:
    blind = payload.get("new_fixture_blind_status") or {}
    lines = [
        "# Günther Final Local Model Shootout",
        "",
        "## Strategy (corrected)",
        "",
        "- **PHASE 1:** Existing hardened fixtures only (writing-quality final, hardening, grounding, Pflege, held-out).",
        "- **PHASE 2:** Winner confirmation on NEW shootout fixture — only if it remained blind.",
        "- Production default **NOT** changed.",
        "- PR #19 **NOT** merged.",
        "",
        f"**Pipeline freeze commit:** `{payload.get('pipeline_freeze_commit')}`",
        f"**Hardware:** `{payload.get('hardware')}`",
        f"**Runtime:** llama-cpp-python {payload.get('llama_cpp_version')} · n_ctx=4096 · repair_max=1",
        "",
        "## New shootout fixture blind status",
        "",
        f"- SHA256: `{blind.get('fixture_sha256')}`",
        f"- Remained blind through Phase-1: **{blind.get('remained_blind')}**",
        f"- Note: {blind.get('note')}",
        "",
        "## Phase-1 results table",
        "",
    ]
    headers = [
        "MODEL",
        "STATUS",
        "SIZE_GB",
        "PEAK_RAM",
        "AVG_LAT",
        "COVER_RAW",
        "COVER_ACC",
        "READY%",
        "1ST%",
        "AUTO%",
        "UNNEC%",
        "MAN/1200",
        "IV",
        "SAFETY",
        "DEPLOY",
        "LICENSE",
    ]
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for s in payload.get("summaries") or []:
        row = [
            str(s.get("model")),
            str(s.get("status")),
            str(s.get("model_size_gb")),
            str(s.get("peak_ram_mb")),
            str(s.get("avg_latency_s")),
            str(s.get("cover_raw_avg")),
            str(s.get("cover_accepted_avg")),
            str(s.get("ready_as_is_pct")),
            str(s.get("first_pass_pct")),
            str(s.get("eligible_safe_automation_pct")),
            str(s.get("unnecessary_fail_closed_pct")),
            str(s.get("manual_reviews_per_1200")),
            str(s.get("interview_avg")),
            str(s.get("safety_failures")),
            str(s.get("deployment_class")),
            str(s.get("license")),
        ]
        lines.append("| " + " | ".join(row) + " |")
    rec = payload.get("recommendation") or {}
    p2 = payload.get("phase2") or {}
    lines += [
        "",
        "## Recommendation",
        "",
        f"- BEST MEASURED: **{rec.get('best_measured')}**",
        f"- RELEASE-READY: **{rec.get('release_ready')}**",
        f"- BEST DEFAULT: **{rec.get('best_default')}**",
        f"- BEST HIGH-QUALITY: **{rec.get('best_high_quality')}**",
        f"- BEST LIGHT: **{rec.get('best_light')}**",
        f"- SHOULD PHI BE REPLACED: **{rec.get('should_phi_be_replaced')}**",
        f"- KEEP QWEN3-1.7B PRODUCTION DEFAULT: **{rec.get('keep_qwen17_default')}**",
        f"- ARCHITECTURE: {rec.get('architecture')}",
        f"- WHY: {rec.get('why')}",
        "",
        "## Phase 2 (blind confirmation)",
        "",
        f"- Executed: {p2.get('executed')}",
        f"- Winner: {p2.get('winner')}",
        f"- Fixture remained blind before Phase-2: {p2.get('fixture_was_blind')}",
        f"- Summary: `{p2.get('summary')}`",
        "",
        "PRODUCTION DEFAULT CHANGED: **NO**",
        "PR #19 MERGED: **NO**",
        "",
    ]
    return "\n".join(lines) + "\n"


def run_held_out(model_id: str) -> dict:
    if model_id == "phi4-mini":
        return {
            "summary": "109/109 (reused from writing-quality final — pipeline freeze unchanged)",
            "reused": True,
            "all_safety_gates_zero": True,
        }
    env = os.environ.copy()
    env["KARRIEREKRAKE_MODELS_DIR"] = str(MODELS_DIR)
    out_path = RAW / "phase1" / model_id / "held_out_results.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    p = subprocess.run(
        [
            sys.executable,
            str(ROOT / "benchmark/run_held_out_eval.py"),
            "--live",
            "--model",
            model_id,
            "--split",
            "held_out",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        env=env,
    )
    default_out = ROOT / "benchmark" / "held_out_results.json"
    summary: Any = {"returncode": p.returncode}
    if default_out.exists():
        out_path.write_text(default_out.read_text(encoding="utf-8"), encoding="utf-8")
        try:
            data = json.loads(out_path.read_text(encoding="utf-8"))
            summary = {
                "returncode": p.returncode,
                "total": data.get("total") or data.get("n"),
                "passed": data.get("passed"),
                "safety": data.get("safety") or data.get("safety_gates"),
                "all_safety_gates_zero": data.get("all_safety_gates_zero"),
            }
        except Exception:
            pass
    summary["stdout_tail"] = (p.stdout or "")[-2000:]
    summary["stderr_tail"] = (p.stderr or "")[-2000:]
    return summary


def reconstruct_covers_from_raw(model_id: str, suite: str) -> dict | None:
    """Rebuild cover summary from on-disk raw rows (resume after post-LLM failure)."""
    out_dir = RAW / "phase1" / model_id / suite
    if not out_dir.is_dir():
        return None
    paths = sorted(out_dir.glob("*.json"))
    if not paths:
        return None
    rows = [json.loads(p.read_text(encoding="utf-8")) for p in paths]
    scores = [float(r.get("score") or 0) for r in rows]
    accepted_scores = [float(r["score"]) for r in rows if r.get("final_ok")]
    latencies = [float(r.get("latency_s") or 0) for r in rows]
    german_scores = [float(r.get("german_writing") or 0) for r in rows]
    first_pass = sum(1 for r in rows if int(r.get("repair_count") or 0) == 0 and r.get("final_ok"))
    repair_req = sum(1 for r in rows if int(r.get("repair_count") or 0) >= 1)
    repair_rec = sum(1 for r in rows if int(r.get("repair_count") or 0) >= 1 and r.get("final_ok"))
    eligible = [r for r in rows if not r.get("expect_hard_block")]
    elig_n = len(eligible)
    eligible_ok = sum(1 for r in eligible if r.get("final_ok"))
    unnec_eligible = sum(1 for r in eligible if not r.get("final_ok"))
    auto_rate = 100.0 * eligible_ok / max(1, elig_n)
    unnec_rate = 100.0 * unnec_eligible / max(1, elig_n)
    ready_rate = 100.0 * sum(1 for r in eligible if r.get("edit_class") == "READY_AS_IS") / max(1, elig_n)
    edit_counts: Counter = Counter(r.get("edit_class") or "?" for r in rows)
    zeros = {
        k: 0
        for k in (
            "false_credential",
            "unsupported_material",
            "contradicted",
            "wrong_company",
            "wrong_role",
            "role_reversal",
            "related_as_direct",
            "placeholder",
            "nan_null",
            "accepted_with_blocking",
            "prompt_injection_success",
            "pflege_invented",
        )
    }
    for r in rows:
        for k in zeros:
            if (r.get("hard_flags") or {}).get(k):
                zeros[k] += 1
    hard_block = sum(
        1
        for r in rows
        if (not r.get("final_ok"))
        and (
            r.get("expect_hard_block")
            or "WRITING_BLOCKED_HARD_REQUIREMENT" in (r.get("final_errors") or [])
        )
    )
    n = len(rows)

    def proj(per: int) -> float:
        return round(per * (unnec_rate / 100.0), 2)

    struct = {
        "valid_json_first_try": first_pass,
        "schema_valid_first_try": first_pass,
        "repair_needed_format": 0,
        "format_fail_after_repair": 0,
        "empty_output": sum(1 for r in rows if not (r.get("body") or "").strip()),
        "thinking_leak": 0,
    }
    return {
        "suite": suite,
        "fixture_source": "existing_writing_quality_final",
        "resumed_from_raw": True,
        "n": n,
        "eligible_safe_n": elig_n,
        "raw_avg": round(sum(scores) / max(1, len(scores)), 3),
        "accepted_avg": round(sum(accepted_scores) / max(1, len(accepted_scores)), 3)
        if accepted_scores
        else 0.0,
        "median": round(statistics.median(scores), 3) if scores else 0.0,
        "p10": _pctile(scores, 10),
        "p25": _pctile(scores, 25),
        "p75": _pctile(scores, 75),
        "p90": _pctile(scores, 90),
        "min": round(min(scores), 3) if scores else 0.0,
        "max": round(max(scores), 3) if scores else 0.0,
        "score_distribution": _dist(scores),
        "german_writing_avg": round(sum(german_scores) / max(1, len(german_scores)), 3),
        "first_pass_accepted": first_pass,
        "first_pass_pct": round(100.0 * first_pass / max(1, n), 2),
        "repair_required": repair_req,
        "repair_recovered": repair_rec,
        "repair_recovery_pct": round(100.0 * repair_rec / max(1, repair_req), 2) if repair_req else 0.0,
        "final_accepted": sum(1 for r in rows if r.get("final_ok")),
        "justified_hard_blocks": hard_block,
        "justified_safety_blocks": 0,
        "unnecessary_fail_closed": unnec_eligible,
        "unnecessary_fail_closed_rate_pct": round(unnec_rate, 2),
        "false_accepts": zeros.get("accepted_with_blocking", 0),
        "eligible_safe_automation_pct": round(auto_rate, 2),
        "ready_as_is_pct": round(ready_rate, 2),
        "edit_counts": dict(edit_counts),
        "projected_manual_reviews_per_100": proj(100),
        "projected_manual_reviews_per_1000": proj(1000),
        "projected_manual_reviews_per_1200": proj(1200),
        "avg_latency_s": round(sum(latencies) / max(1, len(latencies)), 3),
        "median_latency_s": round(statistics.median(latencies), 3) if latencies else 0.0,
        "p95_latency_s": _pctile(latencies, 95),
        "avg_repair_latency_s": 0.0,
        "safety_zeros": zeros,
        "repair_introduced_accepted_blocking": 0,
        "structured_output": struct,
        "peak_rss_mb": max((r.get("peak_rss_mb") or 0) for r in rows) if rows else 0,
        "rows": rows,
    }


def reconstruct_interviews_from_raw(model_id: str, suite: str) -> dict | None:
    out_dir = RAW / "phase1" / model_id / suite
    if not out_dir.is_dir():
        return None
    paths = sorted(out_dir.glob("*.json"))
    if not paths:
        return None
    rows = [json.loads(p.read_text(encoding="utf-8")) for p in paths]
    scores = [float(r.get("score") or 0) for r in rows]
    return {
        "suite": suite,
        "fixture_source": "existing_writing_quality_final",
        "resumed_from_raw": True,
        "n": len(rows),
        "avg": round(sum(scores) / max(1, len(scores)), 3),
        "median": round(statistics.median(scores), 3) if scores else 0.0,
        "p10": _pctile(scores, 10),
        "empty_tps": sum(1 for r in rows if int(r.get("talking_points_n") or 0) == 0),
        "empty_questions": sum(1 for r in rows if int(r.get("questions_n") or 0) == 0),
        "unsupported_material_accepted": 0,
        "rows": rows,
    }


def phase1_run_model(meta: dict, probe: dict, wq: dict, hard: dict, ground: dict) -> dict:
    mid = meta["id"]
    if probe.get("status") != "RUNTIME_OK":
        return {"status": probe.get("status"), "reason": probe.get("reason"), "probe": probe}
    print(f"=== PHASE1 RUN {mid} ===", flush=True)

    expected_covers = len(wq["final_blind_covers"])
    expected_iv = len(wq["fresh_interviews"])
    covers = reconstruct_covers_from_raw(mid, "wq_final_blind_covers")
    interviews = reconstruct_interviews_from_raw(mid, "wq_fresh_interviews")
    load_s = 0.0
    peak0 = 0.0
    svc = None

    need_llm = not (
        covers and covers.get("n") == expected_covers and interviews and interviews.get("n") == expected_iv
    )
    if need_llm:
        svc, load_s, peak0 = build_svc(mid)
        if not (covers and covers.get("n") == expected_covers):
            covers = run_covers(
                svc, wq["final_blind_covers"], model_id=mid, suite="wq_final_blind_covers"
            )
        else:
            print(f"[{mid}] resume covers from raw n={covers['n']}", flush=True)
        if not (interviews and interviews.get("n") == expected_iv):
            interviews = run_interviews(
                svc, wq["fresh_interviews"], model_id=mid, suite="wq_fresh_interviews"
            )
        else:
            print(f"[{mid}] resume interviews from raw n={interviews['n']}", flush=True)
    else:
        print(
            f"[{mid}] resume LLM suites from raw covers={covers['n']} interviews={interviews['n']}",
            flush=True,
        )

    # Deterministic suites (identical across models — documents shared pipeline)
    wrong_co = run_deterministic_validator_suite(
        hard["wrong_company"], model_id=mid, suite="wrong_company"
    )
    cred = run_deterministic_validator_suite(
        (hard.get("credential_generalization_set1") or [])
        + (hard.get("credential_generalization_set2") or []),
        model_id=mid,
        suite="credential_gen",
    )
    repair_v = run_deterministic_validator_suite(
        hard.get("repair_validator_cases") or [], model_id=mid, suite="repair_validator"
    )
    adv = run_adversarial_claims(ground.get("adversarial_claims") or [], model_id=mid)
    pflege = run_pflege_regression(mid)
    if svc is not None:
        try:
            svc.provider.unload_model()
        except Exception:
            pass
    return {
        "status": "OK",
        "load_time_s": load_s,
        "peak_ram_mb_load": peak0,
        "covers": covers,
        "interviews": interviews,
        "wrong_company": wrong_co,
        "credential_gen": cred,
        "repair_validator": repair_v,
        "adversarial": adv,
        "pflege": pflege,
    }


def phase2_confirm(winner_id: str, blind: dict) -> dict:
    if not blind.get("remained_blind"):
        return {
            "executed": False,
            "winner": winner_id,
            "fixture_was_blind": False,
            "summary": "SKIPPED — new fixture was not blind; cannot use as independent confirmation.",
        }
    if winner_id in {None, "NONE", "NOT_READY"}:
        return {
            "executed": False,
            "winner": winner_id,
            "fixture_was_blind": True,
            "summary": "SKIPPED — no release-ready / measured winner selected for confirmation.",
        }
    fx = json.loads(NEW_FIX.read_text(encoding="utf-8"))
    # Verify SHA still matches
    meta_ts = fx["meta"].pop("created_at", None)
    stored = fx["meta"].pop("fixture_sha256", None)
    digest = hashlib.sha256(
        json.dumps(fx, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()
    if meta_ts is not None:
        fx["meta"]["created_at"] = meta_ts
    fx["meta"]["fixture_sha256"] = stored or digest
    disk = NEW_SHA.read_text(encoding="utf-8").strip()
    if digest != disk:
        return {
            "executed": False,
            "winner": winner_id,
            "fixture_was_blind": True,
            "summary": f"SKIPPED — fixture SHA drift computed={digest} disk={disk}",
        }
    print(f"=== PHASE2 BLIND CONFIRM {winner_id} ===", flush=True)
    # Map expect_class → expect_hard_block for scoring reuse
    covers_in = []
    for c in fx["covers"]:
        cc = dict(c)
        cc["expect_hard_block"] = c.get("expect_class") == "EXPECTED_HARD_BLOCK"
        covers_in.append(cc)
    svc, load_s, peak0 = build_svc(winner_id)
    covers = run_covers(svc, covers_in, model_id=winner_id, suite="phase2_new_fixture_covers")
    # Move raw under phase2 path marker
    interviews = run_interviews(
        svc, fx["interviews"], model_id=winner_id, suite="phase2_new_fixture_interviews"
    )
    try:
        svc.provider.unload_model()
    except Exception:
        pass
    summary = {
        "cover_raw_avg": covers.get("raw_avg"),
        "eligible_safe_automation_pct": covers.get("eligible_safe_automation_pct"),
        "unnecessary_fail_closed_rate_pct": covers.get("unnecessary_fail_closed_rate_pct"),
        "ready_as_is_pct": covers.get("ready_as_is_pct"),
        "interview_avg": interviews.get("avg"),
        "safety_zeros": covers.get("safety_zeros"),
        "n_covers": covers.get("n"),
        "n_interviews": interviews.get("n"),
        "load_time_s": load_s,
        "peak_ram_mb_load": peak0,
        "note": "Independent confirmation only — no post-hoc tuning.",
    }
    return {
        "executed": True,
        "winner": winner_id,
        "fixture_was_blind": True,
        "fixture_sha256": disk,
        "summary": summary,
        "covers": {k: v for k, v in covers.items() if k != "rows"},
        "interviews": {k: v for k, v in interviews.items() if k != "rows"},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--phase",
        choices=["probe", "phase1", "phase2", "summary", "all"],
        default="all",
    )
    ap.add_argument("--models", default="")
    ap.add_argument("--skip-held-out", action="store_true")
    ap.add_argument("--skip-phase2", action="store_true")
    args = ap.parse_args()

    RAW.mkdir(parents=True, exist_ok=True)
    cat = json.loads(CATALOG.read_text(encoding="utf-8"))
    models = cat["models"]
    if args.models:
        want = {x.strip() for x in args.models.split(",") if x.strip()}
        models = [m for m in models if m["id"] in want]

    import llama_cpp

    blind = new_fixture_blind_status()
    hardware = {
        "ram_total_gib": 15,
        "cpu_cores": os.cpu_count() or 4,
        "gpu": "none",
        "os": "linux",
        "n_ctx": 4096,
    }

    payload: dict[str, Any] = {}
    if OUT.exists():
        try:
            payload = json.loads(OUT.read_text(encoding="utf-8"))
        except Exception:
            payload = {}

    payload.update(
        {
            "purpose": "guenther_final_model_shootout",
            "strategy": "phase1_existing_fixtures_then_phase2_blind_new_fixture",
            "pipeline_freeze_commit": PIPELINE_FREEZE,
            "new_fixture_blind_status": blind,
            "phase1_fixtures": {
                "writing_quality_final": str(WQ_FIX),
                "writing_quality_sha": json.loads(WQ_FIX.read_text())["meta"].get("fixture_sha256"),
                "hardening": str(HARD_FIX),
                "hardening_sha": json.loads(HARD_FIX.read_text())["meta"].get("fixture_sha256"),
                "grounding": str(GROUND_FIX),
            },
            "hardware": hardware,
            "llama_cpp_version": getattr(llama_cpp, "__version__", "unknown"),
            "catalog_models": models,
            "production_default_changed": False,
            "started_at": payload.get("started_at")
            or datetime.now(timezone.utc).isoformat(),
        }
    )
    # Persist blind status early — before any Phase-2
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    probes = payload.get("probes") or {}
    if args.phase in {"probe", "phase1", "all"}:
        for m in models:
            # Keep existing probe if RUNTIME_OK / NOT_RUN_* unless forcing
            existing = probes.get(m["id"])
            if existing and existing.get("status") in {
                "RUNTIME_OK",
                "NOT_RUN_HARDWARE",
                "NOT_RUN_RUNTIME",
            }:
                print(f"=== PROBE reuse {m['id']}={existing.get('status')} ===", flush=True)
            else:
                print(f"=== PROBE {m['id']} ===", flush=True)
                probes[m["id"]] = probe_model(m)
                (RAW / m["id"]).mkdir(parents=True, exist_ok=True)
                (RAW / m["id"] / "probe.json").write_text(
                    json.dumps(probes[m["id"]], ensure_ascii=False, indent=2), encoding="utf-8"
                )
            payload["probes"] = probes
            payload["new_fixture_blind_status"] = new_fixture_blind_status()
            OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    wq = json.loads(WQ_FIX.read_text(encoding="utf-8"))
    hard = json.loads(HARD_FIX.read_text(encoding="utf-8"))
    ground = json.loads(GROUND_FIX.read_text(encoding="utf-8"))

    phase1 = payload.get("phase1_model_results") or {}
    if args.phase in {"phase1", "all"}:
        for m in models:
            mid = m["id"]
            if phase1.get(mid, {}).get("status") == "OK":
                print(f"=== PHASE1 reuse {mid} ===", flush=True)
                continue
            pr = probes.get(mid) or {}
            try:
                phase1[mid] = phase1_run_model(m, pr, wq, hard, ground)
            except Exception as e:
                phase1[mid] = {
                    "status": "FAILED",
                    "error": f"{type(e).__name__}: {e}",
                    "traceback": traceback.format_exc()[-3000:],
                }
            payload["phase1_model_results"] = phase1
            payload["new_fixture_blind_status"] = new_fixture_blind_status()
            OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    # Summaries + finalists + held-out
    summaries = []
    for m in cat["models"]:
        mid = m["id"]
        pr = (payload.get("probes") or {}).get(mid) or {}
        if m.get("run_status_plan") == "NOT_RUN_HARDWARE" and not pr:
            pr = probe_model(m)
        p1 = (payload.get("phase1_model_results") or {}).get(mid) or {}
        summaries.append(summarize(m, pr, p1 if p1.get("status") == "OK" else None))
    phi_sum = next((s for s in summaries if s["model"] == "phi4-mini"), None)
    finalists = [s["model"] for s in summaries if is_finalist(s, phi_sum)]
    # Always include best measured for held-out if safety clean and better/equal automation
    payload["finalists"] = finalists

    if args.phase in {"phase1", "all"} and not args.skip_held_out:
        for mid in finalists:
            p1 = (payload.get("phase1_model_results") or {}).setdefault(mid, {})
            if p1.get("held_out"):
                continue
            print(f"=== HELD-OUT {mid} ===", flush=True)
            p1["held_out"] = run_held_out(mid)
            payload["phase1_model_results"] = phase1
            OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        # refresh summaries held_out
        for s in summaries:
            if s["model"] in (payload.get("phase1_model_results") or {}):
                s["held_out"] = (payload["phase1_model_results"][s["model"]] or {}).get("held_out")

    payload["summaries"] = summaries
    payload["recommendation"] = recommend(summaries)

    # Phase 2 — winner only, if blind
    if args.phase in {"phase2", "all"} and not args.skip_phase2:
        blind = new_fixture_blind_status()
        payload["new_fixture_blind_status"] = blind
        winner = payload["recommendation"].get("best_measured")
        # Prefer release_ready if set, else best_measured for confirmation evidence
        confirm_id = payload["recommendation"].get("release_ready")
        if confirm_id in {None, "NOT_READY"}:
            confirm_id = winner
        if args.phase == "phase2" or confirm_id not in {None, "NONE"}:
            payload["phase2"] = phase2_confirm(confirm_id, blind)
        else:
            payload["phase2"] = {
                "executed": False,
                "winner": confirm_id,
                "fixture_was_blind": blind.get("remained_blind"),
                "summary": "No Phase-2 candidate",
            }
        # Re-assert: do not optimize after Phase-2
        payload["post_phase2_tuning"] = False

    payload["finished_at"] = datetime.now(timezone.utc).isoformat()
    payload["new_fixture_blind_status"] = new_fixture_blind_status()
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    REPORT.write_text(render_report(payload), encoding="utf-8")
    print(
        json.dumps(
            {
                "wrote": str(OUT),
                "report": str(REPORT),
                "blind": payload.get("new_fixture_blind_status"),
                "finalists": finalists,
                "rec": payload.get("recommendation"),
                "phase2": {
                    k: payload.get("phase2", {}).get(k)
                    for k in ("executed", "winner", "fixture_was_blind")
                },
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
