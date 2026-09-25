#!/usr/bin/env python3
"""NV3 Post-Analysis targeted check (education empty + invented heute).

NOT a blind test. Does NOT modify frozen Phase-A predictions or the scorer.
Writes under tests/docpick_blind_de_en_v2/post_analysis_round8/.
"""

from __future__ import annotations

import json
import resource
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT = ROOT / "tests/docpick_blind_de_en_v2/post_analysis_round8"
PDF_DIR = ROOT / "tests/docpick_blind_de_en_v2/phase_a_pdfs"
SHEET = ROOT / "tests/docpick_blind_de_en_v2/phase_b_solutions/SOLUTION_SHEET.json"

IDS_EDU = [
    "NV3_005",
    "NV3_011",
    "NV3_014",
    "NV3_015",
    "NV3_018",
    "NV3_019",
    "NV3_031",
    "NV3_034",
    "NV3_043",
    "NV3_049",
]
IDS_HEUTE = ["NV3_007", "NV3_014", "NV3_021", "NV3_035", "NV3_049"]


def _norm_end(s: str | None) -> str | None:
    if not s:
        return None
    import re

    t = str(s).strip()
    if t.lower() in {"heute", "present", "current"}:
        return "heute"
    m = re.match(r"^(\d{4})-(\d{1,2})$", t)
    if m:
        return f"{int(m.group(2)):02d}/{m.group(1)}"
    m = re.match(r"^(\d{1,2})/(\d{4})$", t)
    if m:
        return f"{int(m.group(1)):02d}/{m.group(2)}"
    return t


def main() -> int:
    from core.cv_docpick_import import import_cv_docpick

    OUT.mkdir(parents=True, exist_ok=True)
    sheet = json.loads(SHEET.read_text(encoding="utf-8"))
    by_id = {d["document_id"]: d for d in sheet["documents"]}
    ids = sorted(set(IDS_EDU) | set(IDS_HEUTE))
    rows: list[dict] = []
    t0 = time.time()
    for did in ids:
        pdf = PDF_DIR / f"{did}.pdf"
        print(f"START {did}", flush=True)
        t1 = time.time()
        parsed = import_cv_docpick(pdf)
        dt = time.time() - t1
        edu = parsed.get("education") or []
        emp = (parsed.get("work_experience") or [{}])[0]
        entry = by_id[did]
        exp_qual = ((entry.get("education") or [{}])[0].get("qualification") or "")
        exp_end = _norm_end((entry.get("employment") or [{}])[0].get("end_date"))
        got_qual = edu[0].get("qualification") if edu else ""
        got_end = emp.get("end_date")
        edu_ok = bool(edu) and (
            exp_qual.lower() in got_qual.lower()
            or got_qual.lower() in exp_qual.lower()
            or any(
                tok.lower() in got_qual.lower()
                for tok in exp_qual.replace(",", " ").split()
                if len(tok) > 3
            )
        )
        if did in IDS_HEUTE:
            heute_ok = (
                got_end == "heute" if exp_end is None else got_end == exp_end
            )
        else:
            heute_ok = None
        row = {
            "id": did,
            "sec": round(dt, 1),
            "edu_n": len(edu),
            "got_qual": (got_qual or "")[:80],
            "exp_qual": exp_qual[:80],
            "edu_ok": edu_ok,
            "emp_end": got_end,
            "exp_end": exp_end,
            "heute_ok": heute_ok,
            "education": edu,
            "work0": emp,
        }
        rows.append(row)
        print(json.dumps({k: row[k] for k in row if k not in {"education", "work0"}}, ensure_ascii=False), flush=True)
        (OUT / f"pred_{did}.json").write_text(
            json.dumps(parsed, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
    summary = {
        "test_type": "POST_ANALYSIS_TARGETED_NOT_BLIND",
        "disclaimer": "Post-Analysis only. Frozen NV3 F1 0.980 unchanged. No 99% claim.",
        "TOTAL_S": round(time.time() - t0, 1),
        "PEAK_RSS_MB": round(rss, 1),
        "n": len(ids),
        "edu_filled": sum(1 for r in rows if r["id"] in IDS_EDU and r["edu_n"] > 0),
        "edu_ok": sum(1 for r in rows if r["id"] in IDS_EDU and r["edu_ok"]),
        "edu_n": len(IDS_EDU),
        "heute_ok": sum(1 for r in rows if r["id"] in IDS_HEUTE and r["heute_ok"]),
        "heute_n": len(IDS_HEUTE),
        "rows": [{k: r[k] for k in r if k not in {"education", "work0"}} for r in rows],
    }
    (OUT / "TARGETED_SUMMARY.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print("SUMMARY", json.dumps({k: v for k, v in summary.items() if k != "rows"}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
