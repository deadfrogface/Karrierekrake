#!/usr/bin/env python3
"""ThinkPad raw peak-memory run via the repo's scripts/run_i3_peak_job_benchmark.py.

LABEL: "ThinkPad, speed/peak raw data, not i3 evidence".

Separate step of the CV speed test. It runs the full contained import job
(scripts/run_i3_peak_job_benchmark.py -> python -m desktop.cv_import_child ->
import_cv -> import_cv_docpick, Windows Job Object PeakJobMemoryUsed) once per
selected CV with the PRODUCT defaults: n_ctx from resolve_cv_llm_n_ctx (4096),
threads from resolve_cv_llm_thread_plan (no thread/n_ctx/max_tokens env set),
product import-timeout formula (KARRIEREKRAKE_CV_IMPORT_TIMEOUT_S not set),
llama-cpp-python 0.3.35 (checked).

Hard rules enforced here:
* --attest-physical-i3 is never passed (and any extra arg containing "attest" is refused);
* KARRIEREKRAKE_PHYSICAL_I3_8GB is removed from the child environment;
* nothing writes or modifies a PEAK_ATTESTATION entry (guenther/setup_models.py at
  47e8f83b; this script writes only into --out and never touches the repo or docs).
  Guard: sha256 of guenther/setup_models.py is taken before and after every CV;
  any change aborts the run and is reported;
* --enforce-limit is not passed (raw number, no 3.3 GB cap inside the job);
* the output is refused if the repo script reports ship_evidence=True.

Usage (Windows):
  py thinkpad_peak_raw.py --repo C:\\...\\repo-47e8f83b --model C:\\...\\Qwen3.5-4B-Q4_K_M.gguf --out C:\\...\\results-peak [--cvs DE_01]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

LABEL = "ThinkPad, speed/peak raw data, not i3 evidence"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import thinkpad_cv_bench as bench  # noqa: E402  (sysinfo, llama info, repo info, preflight)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--repo-commit", default=None)
    ap.add_argument("--model", required=True)
    ap.add_argument("--expect-model-sha256", default=None)
    ap.add_argument("--out", required=True)
    ap.add_argument("--cvs", default="", help="comma list of CV names/prefixes (default: all 10)")
    ap.add_argument("--timeout", type=float, default=3600.0, help="run_i3_peak_job_benchmark --timeout per CV")
    ap.add_argument("--allow-concurrent", action="store_true", help="skip the other-python/llama preflight")
    ap.add_argument("--allow-other-llama", action="store_true", help="NOT for ThinkPad numbers")
    a = ap.parse_args(argv)

    repo = Path(a.repo).resolve()
    script = repo / "scripts" / "run_i3_peak_job_benchmark.py"
    if not script.is_file():
        raise SystemExit(f"{script} missing")
    import llama_cpp
    if llama_cpp.__version__ != bench.PINNED_LLAMA_CPP_PYTHON and not a.allow_other_llama:
        raise SystemExit(f"llama-cpp-python {llama_cpp.__version__} != {bench.PINNED_LLAMA_CPP_PYTHON}")
    found = bench.other_python_llama_processes()
    if found and not a.allow_concurrent:
        raise SystemExit("ABORT: other python/llama processes running (parallel letter run?): "
                         + json.dumps(found, ensure_ascii=False))
    rinfo = bench.repo_info(repo, a.repo_commit)
    if not rinfo.get("commit"):
        raise SystemExit("repo commit unknown")
    model = Path(a.model).resolve()
    model_sha = bench.sha256_file(model)
    if a.expect_model_sha256 and a.expect_model_sha256.lower() != model_sha:
        raise SystemExit(f"model sha256 {model_sha} != expected")
    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    sandbox = out / "_sandbox"
    (sandbox / "models").mkdir(parents=True, exist_ok=True)
    (sandbox / "data").mkdir(parents=True, exist_ok=True)

    env = {k: v for k, v in os.environ.items() if not k.startswith("KARRIEREKRAKE_")}
    cleared = sorted(k for k in os.environ if k.startswith("KARRIEREKRAKE_"))
    env.update({
        "KARRIEREKRAKE_CV_LLM_MODEL": str(model),
        "KARRIEREKRAKE_MODELS_DIR": str(sandbox / "models"),
        "KARRIEREKRAKE_DATA_DIR": str(sandbox / "data"),
        "KARRIEREKRAKE_CV_LLM_BASE": "http://127.0.0.1:9/v1",   # no dev server -> in-process like a user machine
        "PYTHONPATH": str(repo),
    })
    assert "KARRIEREKRAKE_PHYSICAL_I3_8GB" not in env

    att_file = repo / "guenther" / "setup_models.py"
    att_sha0 = bench.sha256_file(att_file) if att_file.is_file() else None

    def guard_attestation():
        now = bench.sha256_file(att_file) if att_file.is_file() else None
        if now != att_sha0:
            raise SystemExit(f"ABORT: {att_file} (PEAK_ATTESTATION) changed during the run "
                             f"({att_sha0} -> {now}); this step must never touch it")

    docs = bench.corpus_documents(repo)
    if a.cvs:
        want = [s.strip() for s in a.cvs.split(",") if s.strip()]
        docs = [(n, e) for n, e in docs if any(n == w or n.startswith(w) for w in want)]
    session = {
        "label": LABEL, "not_i3_evidence": True, "ship_evidence_expected": False,
        "started": bench.now_iso(), "repo_commit": rinfo["commit"], "repo": rinfo,
        "argv": sys.argv, "model": {"path": str(model), "sha256": model_sha, "bytes": model.stat().st_size},
        "product_defaults": "n_ctx/threads/max_tokens/import-timeout not overridden (product formula)",
        "env_set": {k: env[k] for k in env if k.startswith("KARRIEREKRAKE_")}, "env_cleared": cleared,
        "system": bench.system_info(), "llama": bench.llama_info(), "runs": [],
        "peak_attestation_file": {"path": "guenther/setup_models.py", "sha256_before": att_sha0,
                                  "note": "read-only; PEAK_ATTESTATION is never written by this step"},
    }
    sp = out / "peak_raw_session.json"
    for cv_name, _exp in docs:
        cv = repo / "tests" / "fixtures" / "cv_corpus" / cv_name
        jo = out / f"peak_raw.{Path(cv_name).stem}.repo_report.json"
        cmd = [sys.executable, str(script), "--cv", str(cv), "--timeout", str(a.timeout), "--json-out", str(jo)]
        if any("attest" in c for c in cmd):
            raise SystemExit("refusing: attest flag in command")
        t0 = time.perf_counter()
        p = subprocess.run(cmd, cwd=str(repo), env=env, capture_output=True, text=True, encoding="utf-8",
                           errors="replace")
        wall = time.perf_counter() - t0
        guard_attestation()
        rep = json.loads(jo.read_text(encoding="utf-8")) if jo.is_file() else None
        if rep is not None and rep.get("ship_evidence"):
            jo.unlink()
            raise SystemExit("repo script reported ship_evidence=True - output discarded (must never happen here)")
        imp = (rep or {}).get("import_result") or {}
        rec = {"cv": cv_name, "label": LABEL, "exit_code": p.returncode, "wall_s": round(wall, 2),
               "peak_bytes": (rep or {}).get("peak_bytes"), "method": (rep or {}).get("method"),
               "platform": (rep or {}).get("platform"), "limit_bytes_reference_only": (rep or {}).get("limit_bytes"),
               "hard_fail_flag_reference_only": (rep or {}).get("hard_fail"),
               "ship_evidence": (rep or {}).get("ship_evidence"), "notes": (rep or {}).get("notes"),
               "import_ok": imp.get("ok"), "import_kind": imp.get("kind"), "llm_step": imp.get("llm_step"),
               "repo_report_file": jo.name, "stderr_tail": p.stderr[-3000:]}
        (out / f"peak_raw.{Path(cv_name).stem}.stdout.txt").write_text(p.stdout, encoding="utf-8")
        session["runs"].append(rec)
        print(f"[{LABEL}] {cv_name}: peak {rec['peak_bytes']} B ({rec['method']}), import ok={rec['import_ok']} "
              f"kind={rec['import_kind']}, exit {p.returncode}, {rec['wall_s']} s", flush=True)
        sp.write_text(json.dumps(session, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    peaks = [r["peak_bytes"] for r in session["runs"] if isinstance(r.get("peak_bytes"), int)]
    session["max_peak_bytes"] = max(peaks) if peaks else None
    guard_attestation()
    session["peak_attestation_file"]["sha256_after"] = att_sha0
    session["finished"] = bench.now_iso()
    sp.write_text(json.dumps(session, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(f"[{LABEL}] max peak {session['max_peak_bytes']} B -> {sp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
