#!/usr/bin/env python3
"""Demonstrate explicit CV-import fail-cases (hard fail, no silent hang).

Writes evidence JSON under tests/docpick_qwen35/fail_cases/.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT = ROOT / "tests" / "docpick_qwen35" / "fail_cases"


def _run_case(name: str, fn) -> dict:
    t0 = time.perf_counter()
    try:
        fn()
        return {
            "case": name,
            "raised": False,
            "code": None,
            "message": None,
            "wall_s": round(time.perf_counter() - t0, 3),
            "pass": False,
            "note": "expected CvImportError was not raised",
        }
    except Exception as exc:  # noqa: BLE001
        code = getattr(exc, "code", None)
        return {
            "case": name,
            "raised": True,
            "code": code,
            "message": str(exc)[:300],
            "wall_s": round(time.perf_counter() - t0, 3),
            "pass": code == name or (name == "peak_rss_exceeded" and code == "peak_rss_exceeded"),
            "exception_type": type(exc).__name__,
        }


def main() -> int:
    from core.cv_docpick_import import (
        CV_IMPORT_PEAK_RSS_MB_MAX,
        CvImportError,
        _enforce_peak_rss,
        _enforce_timeout,
        cv_path_peak_rss_mb,
        import_cv_docpick,
    )

    OUT.mkdir(parents=True, exist_ok=True)
    empty = OUT / "empty.pdf"
    empty.write_bytes(b"")
    corrupt = OUT / "corrupt.pdf"
    corrupt.write_bytes(b"\x00\x01\x02NOT_A_PDF!!!!")

    results = []

    results.append(_run_case("empty_cv", lambda: import_cv_docpick(empty)))
    # Normalize expected code
    if results[-1]["code"] == "empty_cv":
        results[-1]["pass"] = True

    results.append(_run_case("unreadable_cv", lambda: import_cv_docpick(corrupt)))
    if results[-1]["code"] == "unreadable_cv":
        results[-1]["pass"] = True

    def _timeout() -> None:
        # Force immediate timeout without hanging (elapsed already over limit).
        _enforce_timeout(time.monotonic() - 999.0, stage="demo")

    results.append(_run_case("timeout", _timeout))
    if results[-1]["code"] == "timeout":
        results[-1]["pass"] = True

    def _peak() -> None:
        rss = cv_path_peak_rss_mb()
        if rss <= CV_IMPORT_PEAK_RSS_MB_MAX:
            # Still demonstrate the hard-fail path via enforce with staged label.
            # On this host RSS is typically already over 3.3 GB with llama loaded.
            raise AssertionError(
                f"expected peak>{CV_IMPORT_PEAK_RSS_MB_MAX}, got {rss:.1f} — "
                "cannot demo peak fail on a thin footprint"
            )
        _enforce_peak_rss(stage="demo")

    peak_row = _run_case("peak_rss_exceeded", _peak)
    if peak_row["code"] == "peak_rss_exceeded":
        peak_row["pass"] = True
    peak_row["measured_cv_path_rss_mb"] = round(cv_path_peak_rss_mb(), 1)
    peak_row["gate_mb"] = CV_IMPORT_PEAK_RSS_MB_MAX
    results.append(peak_row)

    summary = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "all_pass": all(r["pass"] for r in results),
        "cases": results,
        "note": (
            "Fail-cases must raise CvImportError with stable codes; "
            "no silent hang / no infinite UI wait."
        ),
    }
    out = OUT / "FAIL_CASES_DEMO.json"
    out.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if summary["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
