#!/usr/bin/env python3
"""Real GGUF inference benchmark for Günther — no simulation.

Loads each installed catalog model via llama-cpp-python and runs the
fictional DE corpus through GuentherService with the live provider.
"""

from __future__ import annotations

import json
import os
import sys
import time
import traceback
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from benchmark.metrics import (
    ModelBenchmarkResult,
    pick_winner,
    score_association,
    score_cv,
    score_email_class,
    score_interview,
    score_writing,
    write_results,
)
from guenther.runtime.llama_cpp_provider import LlamaCppProvider
from guenther.service import GuentherService


MODELS_DIR = Path(os.environ.get("KARRIEREKRAKE_MODELS_DIR", "/tmp/karrierekrake-models"))
CORPUS = ROOT / "benchmark" / "corpus" / "guenther_de_fictional.json"
OUT = ROOT / "benchmark" / "results_live_gguf.json"

SIZE_HINTS = {"qwen3-1.7b": 1.28, "qwen3-4b": 2.50}


def run_model(model_id: str, corpus: dict) -> ModelBenchmarkResult:
    svc = GuentherService(enabled=True, model=model_id, allow_heuristic_when_no_llm=False)
    svc.models_dir = MODELS_DIR
    svc.manager.models_dir = MODELS_DIR
    provider = LlamaCppProvider(MODELS_DIR)
    status = provider.load_model(model_id)
    if status.value != "ready":
        raise RuntimeError(f"load_failed:{model_id}:{status.value}")
    svc.provider = provider
    svc._heuristic = None  # noqa: SLF001 — force live path only

    result = ModelBenchmarkResult(
        model_id=model_id,
        provider_id=provider.provider_id,
        size_hint_gb=SIZE_HINTS.get(model_id, 9.9),
    )
    t0 = time.perf_counter()
    soft_errors: list[str] = []

    def _record_fail(task_id: str, reason: str) -> None:
        soft_errors.append(f"{task_id}:{reason}")
        result.tasks.append(
            __import__("benchmark.metrics", fromlist=["TaskScore"]).TaskScore(
                task_id=task_id,
                ok=False,
                penalty=8.0,
                notes=[f"live_invalid:{reason}"],
            )
        )

    cv = corpus["cv"]
    env = svc.suggest_cv_extract(cv["text"])
    if not env.ok:
        _record_fail("cv", env.fallback_reason)
    else:
        result.tasks.append(score_cv(cv, env.suggestion, cv["text"]))

    from integrations.email_classify import classify_email

    for em in corpus["emails"]:
        det = classify_email(em["subject"], em["body"])
        env = svc.suggest_email_class(
            em["subject"],
            em["body"],
            deterministic_category=det.category,
            deterministic_false_rejection_blocked=det.false_rejection_blocked,
        )
        if not env.ok:
            _record_fail(em["id"], env.fallback_reason)
        else:
            result.tasks.append(score_email_class(em, env.suggestion))

    from integrations.email_associate import associate_email

    for assoc in corpus["associations"]:
        det = associate_email(
            sender=assoc["sender"], subject=assoc["subject"], cases=assoc["cases"]
        )
        env = svc.suggest_association(
            sender=assoc["sender"],
            subject=assoc["subject"],
            cases=assoc["cases"],
            deterministic_case_id=det.case_id,
            deterministic_ambiguous=det.ambiguous,
        )
        if not env.ok:
            _record_fail(assoc["id"], env.fallback_reason)
        else:
            result.tasks.append(score_association(assoc, env.suggestion))

    cl = corpus["cover_letter"]
    job = corpus["jobs"][0]
    env = svc.suggest_writing(
        profile_text=cv["text"], job_text=job["text"], seed_body=cl["seed"]
    )
    if not env.ok:
        _record_fail("writing", env.fallback_reason)
    else:
        if not env.suggestion.get("body"):
            env.suggestion["body"] = cl["seed"]
        result.tasks.append(score_writing(cl, env.suggestion))

    prep = corpus["interview_prep"]
    env = svc.suggest_evidence_assist(
        profile_text=cv["text"],
        job_text=corpus["jobs"][1]["text"],
        existing_evidence=prep["evidence"],
    )
    if not env.ok:
        _record_fail("evidence", env.fallback_reason)
    else:
        result.tasks.append(score_interview(prep, {"items": env.suggestion.get("items") or []}))

    env2 = svc.suggest_interview_prep(
        profile_text=cv["text"], job_text=job["text"], evidence=prep["evidence"]
    )
    if not env2.ok:
        _record_fail("interview_prep", env2.fallback_reason)
    else:
        result.tasks.append(
            score_writing(
                {"id": "prep_writing", "must_not_contain": prep["must_not_claim_direct"]},
                {"body": " ".join(env2.suggestion.get("talking_points") or []), "subject": ""},
            )
        )

    elapsed = time.perf_counter() - t0
    result.tasks.append(
        __import__("benchmark.metrics", fromlist=["TaskScore"]).TaskScore(
            task_id="wall_time",
            ok=True,
            penalty=0.0,
            notes=[f"elapsed_s={elapsed:.1f}", f"provider={provider.provider_id}"]
            + ([f"soft_errors={';'.join(soft_errors)}"] if soft_errors else []),
        )
    )
    result.finalize()
    provider.unload_model()
    return result


def main() -> int:
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    models = [m for m in ("qwen3-1.7b", "qwen3-4b") if (MODELS_DIR / m).exists()]
    if not models:
        print(json.dumps({"error": "no_models_installed", "dir": str(MODELS_DIR)}))
        return 2

    results: list[ModelBenchmarkResult] = []
    errors: dict[str, str] = {}
    for mid in models:
        print(f"=== LIVE GGUF RUN {mid} ===", flush=True)
        try:
            r = run_model(mid, corpus)
            results.append(r)
            print(
                json.dumps(
                    {
                        "model": mid,
                        "safety_penalty": r.safety_penalty,
                        "meets_safety": r.meets_safety_threshold,
                        "utility": r.utility_score,
                        "total_penalty": r.total_penalty,
                    }
                ),
                flush=True,
            )
        except Exception as exc:
            errors[mid] = f"{type(exc).__name__}: {exc}"
            traceback.print_exc()
            print(f"FAILED {mid}: {errors[mid]}", flush=True)

    winner = pick_winner(results)
    payload = {
        "mode": "live_gguf",
        "models_dir": str(MODELS_DIR),
        "results": [
            {
                **{k: v for k, v in asdict(r).items() if k != "tasks"},
                "tasks": [asdict(t) for t in r.tasks],
            }
            for r in results
        ],
        "errors": errors,
        "winner": winner.model_id if winner else None,
        "gated": False,
    }
    write_results(OUT, payload)
    # Also merge summary into results.json note file
    summary_path = ROOT / "benchmark" / "results_live_summary.json"
    write_results(
        summary_path,
        {
            "winner": payload["winner"],
            "errors": errors,
            "models_run": [r.model_id for r in results],
            "safety": {r.model_id: r.meets_safety_threshold for r in results},
            "safety_penalty": {r.model_id: r.safety_penalty for r in results},
            "utility": {r.model_id: r.utility_score for r in results},
        },
    )
    print(json.dumps({"wrote": str(OUT), "winner": payload["winner"], "errors": errors}, indent=2))
    return 0 if results and not errors else (0 if results else 1)


if __name__ == "__main__":
    raise SystemExit(main())
