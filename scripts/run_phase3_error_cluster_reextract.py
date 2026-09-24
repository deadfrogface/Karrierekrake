#!/usr/bin/env python3
"""Phase-3 focused re-extract on Round2 error-cluster documents (known CVs).

NOT a blind test. Measures whether general prompt/norm fixes reduce the
dominant missing ``employment end_date=heute`` cluster. DET is never used.
"""

from __future__ import annotations

import json
import resource
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT = ROOT / "tests" / "docpick_qwen35" / "phase3_error_cluster"
OUT.mkdir(parents=True, exist_ok=True)

# Documents that Round2 marked missing employment:0.end_date == "heute"
# (plus a couple of education incomplete cases). Paths only — no GT loaded here.
TARGETS = [
    ("MH_005", ROOT / "tests/mini_holdout_30/phase_a_pdfs/MH_005.pdf"),
    ("MH_009", ROOT / "tests/mini_holdout_30/phase_a_pdfs/MH_009.pdf"),
    ("MH_013", ROOT / "tests/mini_holdout_30/phase_a_pdfs/MH_013.pdf"),
    ("MH_017", ROOT / "tests/mini_holdout_30/phase_a_pdfs/MH_017.pdf"),
    ("MH_021", ROOT / "tests/mini_holdout_30/phase_a_pdfs/MH_021.pdf"),
    ("MH_025", ROOT / "tests/mini_holdout_30/phase_a_pdfs/MH_025.pdf"),
    ("MH_029", ROOT / "tests/mini_holdout_30/phase_a_pdfs/MH_029.pdf"),
]


def _rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def main() -> int:
    from core.cv_docpick_import import import_cv_docpick

    rows = []
    t_all = time.perf_counter()
    peak = _rss_mb()
    for doc_id, pdf in TARGETS:
        if not pdf.is_file():
            rows.append({"doc": doc_id, "error": f"missing:{pdf}"})
            continue
        t0 = time.perf_counter()
        try:
            parsed = import_cv_docpick(pdf)
            work = parsed.get("work_experience") or []
            edu = parsed.get("education") or []
            row = {
                "doc": doc_id,
                "ok": True,
                "s": round(time.perf_counter() - t0, 3),
                "pipeline": parsed.get("pipeline"),
                "work0_end": (work[0].get("end_date") if work else None),
                "work0_title": (work[0].get("title") if work else None),
                "edu0_qual": (edu[0].get("qualification") if edu else None),
                "edu0_end": (edu[0].get("end_date") if edu else None),
                "software": parsed.get("software") or [],
                "name": (parsed.get("personal") or {}),
            }
        except Exception as exc:  # noqa: BLE001
            row = {
                "doc": doc_id,
                "ok": False,
                "s": round(time.perf_counter() - t0, 3),
                "error": f"{type(exc).__name__}: {exc}",
            }
        peak = max(peak, _rss_mb())
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)

    report = {
        "test_type": "PHASE3_ERROR_CLUSTER_KNOWN_CVS_NOT_BLIND",
        "disclaimer": "Known Round2 error-cluster only. Not F1. Not independent 99%.",
        "n": len(rows),
        "wall_s": round(time.perf_counter() - t_all, 3),
        "peak_rss_mb": round(peak, 1),
        "rows": rows,
        "heute_hits": sum(1 for r in rows if r.get("work0_end") == "heute"),
    }
    out = OUT / "CLUSTER_REEXTRACT.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {out} heute_hits={report['heute_hits']}/{len(rows)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
