"""Holdout Scorer V3.1 — COMPLETE_GT_ONLY + employment/education date equivalence.

Preserves:
- Scorer V2 unchanged
- COMPLETE_GT_ONLY_V3 historical results unchanged
- Ground-truth files unchanged
- Original prediction values unchanged (equality only at compare time)

Metric name: COMPLETE_GT_ONLY_V3_1_DATE_NORM
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from cv_date_normalize import dates_semantically_equal
from holdout_scorer_v2 import FactResult, aggregate_v2
from holdout_scorer_v3_complete_gt import (  # noqa: E402
    aggregate_v3,
    evaluate_doc_v3,
)

METRIC_NAME = "COMPLETE_GT_ONLY_V3_1_DATE_NORM"
METRIC_DISCLAIMER = (
    "Same COMPLETE_GT_ONLY scope as V3, plus semantic equality for "
    "employment/education start_date/end_date spellings (e.g. 02/2019 ≡ 2019-02). "
    "Not a parser change. Not overall F1. Does not replace V2 or V3 history."
)


def _is_emp_edu_date_field(field: str) -> bool:
    f = field or ""
    return f.endswith(".start_date") or f.endswith(".end_date")


def apply_date_norm_to_rows(rows: list[FactResult]) -> tuple[list[FactResult], int]:
    """Reclassify format-equivalent date wrongs as correct. Returns (rows, n_flipped)."""
    out: list[FactResult] = []
    flipped = 0
    for r in rows:
        if (
            r.status == "wrong"
            and _is_emp_edu_date_field(r.field)
            and dates_semantically_equal(r.expected, r.actual)
        ):
            flipped += 1
            out.append(
                FactResult(
                    r.document,
                    r.field,
                    r.group,
                    "correct",
                    expected=r.expected,
                    actual=r.actual,
                    critical=r.critical,
                    skip_reason=(r.skip_reason or "") + "|date_norm_v3_1",
                )
            )
        else:
            out.append(r)
    return out, flipped


def evaluate_doc_v3_1(
    fname: str,
    gt: dict[str, Any],
    pred: dict[str, Any] | None,
    pdf_text: str,
) -> dict[str, Any]:
    base = evaluate_doc_v3(fname, gt, pred, pdf_text)
    scored, flipped = apply_date_norm_to_rows(base["scored_rows"])
    return {
        **base,
        "scored_rows": scored,
        "date_norm_flipped": flipped,
        "scorer": METRIC_NAME,
    }


def aggregate_v3_1(doc_results: list[dict[str, Any]]) -> dict[str, Any]:
    # Rebuild aggregate from date-normalized rows
    flipped_total = sum(int(dr.get("date_norm_flipped") or 0) for dr in doc_results)
    # Use V3 aggregate helper structure but with normalized rows
    normalized_docs = []
    for dr in doc_results:
        normalized_docs.append(
            {
                "document": dr["document"],
                "scored_rows": dr["scored_rows"],
                "nicht_bewertbar": dr["nicht_bewertbar"],
            }
        )
    agg = aggregate_v3(normalized_docs)
    agg["metric_name"] = METRIC_NAME
    agg["disclaimer"] = METRIC_DISCLAIMER
    agg["date_norm_flipped_fields"] = flipped_total
    return agg
