"""Measure process-group peak memory against the i3 / 8 GB hard gate.

Windows puts the workload in one Job Object (no breakaway, assign-before-resume)
and reads PeakJobMemoryUsed. Other platforms use a process-group scaffold.

Agent-VM and CI numbers are not ship evidence. On the physical Intel Core i3
(11th gen) / 8 GB RAM laptop:

    set KARRIEREKRAKE_PHYSICAL_I3_8GB=1
    python scripts/run_i3_peak_job_benchmark.py --self-test
    python scripts/run_i3_peak_job_benchmark.py --cv C:\\path\\lebenslauf.pdf --attest-physical-i3

Exit 0: peak <= 3_300_000_000. Exit 2: hard fail. See
docs/devops/i3-8gb-peak-rss-gate.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.hardware_peak_gate import HARD_PEAK_RSS_BYTES  # noqa: E402
from core.local_llm_cv_gate import LOCAL_LLM_CV_KILL_WORDING, local_llm_cv_parsing_allowed  # noqa: E402
from devops.peak_rss_harness import (  # noqa: E402
    report_exit_code,
    run_contained_until_exit,
    run_self_test,
    write_report,
)


def _build_workload(args: argparse.Namespace, out_path: Path) -> list[str]:
    cmd = [
        sys.executable,
        "-m",
        "desktop.cv_import_child",
        "--cv",
        str(args.cv),
        "--out",
        str(out_path),
        "--backend",
        args.backend,
        "--llm-warmup",
        str(args.llm_warmup),
    ]
    if args.llm_cmd:
        cmd.extend(["--llm-cmd", args.llm_cmd])
    return cmd


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="i3 8GB process-group peak gate")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--cv", type=Path)
    parser.add_argument("--backend", choices=("current", "docling"), default="current")
    parser.add_argument("--llm-cmd", default="")
    parser.add_argument("--llm-warmup", type=float, default=3.0)
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument(
        "--enforce-limit",
        action="store_true",
        help="Windows: set the Job Object memory cap to the hard gate",
    )
    parser.add_argument(
        "--attest-physical-i3",
        action="store_true",
        help="Mark ship evidence only on Windows when KARRIEREKRAKE_PHYSICAL_I3_8GB=1",
    )
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args(argv)

    if args.self_test and args.cv:
        parser.error("use either --self-test or --cv")
    if args.llm_cmd and not local_llm_cv_parsing_allowed():
        payload = {
            "ok": False,
            "kind": "llm_disabled",
            "message": LOCAL_LLM_CV_KILL_WORDING,
            "hard_fail": False,
            "ship_evidence": False,
            "limit_bytes": HARD_PEAK_RSS_BYTES,
            "fallback_model": None,
        }
        _emit(payload, args.json_out)
        return 4
    if args.self_test:
        payload = run_self_test(timeout_s=min(args.timeout, 30.0))
        _emit(payload, args.json_out)
        return 2 if payload.get("hard_fail") else 0
    if args.cv is None:
        parser.error("--cv is required unless --self-test is set")
    if not args.cv.is_file():
        print(f"CV not found: {args.cv}", file=sys.stderr)
        return 1

    import tempfile

    with tempfile.TemporaryDirectory(prefix="kk-peak-cv-") as tmp:
        out_path = Path(tmp) / "import.json"
        workload = _build_workload(args, out_path)
        report = run_contained_until_exit(
            workload,
            timeout_s=args.timeout,
            console=True,
            enforce_memory_bytes=HARD_PEAK_RSS_BYTES if args.enforce_limit else None,
            attest_physical_i3=args.attest_physical_i3,
        )
        payload = report.as_dict()
        if out_path.is_file():
            try:
                payload["import_result"] = json.loads(out_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                payload["import_result"] = {"ok": False, "kind": "error", "message": "invalid json"}
        _emit(payload, args.json_out)
        return report_exit_code(report)


def _emit(payload: dict, json_out: Path | None) -> None:
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    print(text)
    if json_out is not None:
        write_report(json_out, payload)


if __name__ == "__main__":
    raise SystemExit(main())
