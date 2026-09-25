"""Holdout Scorer V3 — COMPLETE_GT / NICHT_BEWERTBAR split.

Preserves Scorer V2 unchanged. This module is a **new metric**:
``COMPLETE_GT_ONLY_V3`` (+ explicit ``nicht_bewertbar`` accounting).

Rules (do not confuse with V2):
- Employment / education / skills / software / certificates are **only**
  scored when the ground-truth document contains a **non-empty list of
  full values** (objects or strings). A mere ``*_count`` is **not**
  sufficient → facts are recorded as ``nicht_bewertbar``, never as
  ``hallucinated`` or ``correct``.
- Scalars / languages / licenses use the same evidence rules as V2 when
  evaluable.
- Does **not** write or modify ground-truth files or V2 result JSON.

Usage:
  from holdout_scorer_v3_complete_gt import evaluate_doc_v3, aggregate_v3
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

# Reuse V2 matching helpers without changing V2 behaviour.
from holdout_scorer_v2 import (  # noqa: E402
    FactResult,
    aggregate_v2,
    build_evidence_for_doc,
    evaluate_doc_v2,
    pred_view,
    text_contains,
)

METRIC_NAME = "COMPLETE_GT_ONLY_V3"
METRIC_DISCLAIMER = (
    "Not overall F1. Excludes count-only employment/education/list fields "
    "as nicht_bewertbar. Does not replace Scorer V2 historical results."
)


@dataclass
class NichtBewertbarFact:
    document: str
    field: str
    group: str
    reason: str
    gt_keys_present: list[str]
    pred_summary: Any
    text_grounded: bool | None = None


def gt_has_full_list(gt: dict[str, Any], key: str) -> bool:
    raw = gt.get(key)
    return isinstance(raw, list) and len(raw) > 0


def list_field_gt_status(gt: dict[str, Any], key: str) -> tuple[str, str]:
    """Return (status, reason) for list-valued GT fields.

    status: complete | count_only | absent
    """
    if gt_has_full_list(gt, key):
        return "complete", f"full {key} list present"
    count_key = {
        "employment": "work_count",
        "education": "education_count",
        "skills": "skills_count",
        "software": "software_count",
        "certificates": "certificates_count",
    }.get(key)
    if count_key and gt.get(count_key) is not None:
        return "count_only", f"only {count_key}={gt.get(count_key)}; no full {key} list"
    return "absent", f"no {key} list and no count"


def _pred_list_summary(pred: dict[str, Any], group: str) -> Any:
    pv = pred_view(pred)
    if group == "employment":
        return pv.get("employment") or []
    if group == "education":
        return pv.get("education") or []
    if group == "skills":
        return pv.get("skills") or []
    if group == "software":
        return pv.get("software") or []
    if group == "certificates":
        raw = pv.get("certificates") or []
        return [c.get("name") if isinstance(c, dict) else str(c) for c in raw]
    return None


def _entries_text_grounded(items: Any, text: str) -> bool:
    if not items:
        return True
    if not isinstance(items, list):
        return text_contains(items, text)
    ok = True
    for a in items:
        if isinstance(a, dict):
            blob = " ".join(
                str(a.get(k) or "")
                for k in ("company", "position", "title", "institution", "qualification", "name")
            )
            if blob.strip() and not (
                text_contains(blob, text)
                or any(text_contains(str(v), text) for v in a.values() if v)
            ):
                ok = False
        else:
            if str(a).strip() and not text_contains(str(a), text):
                ok = False
    return ok


def evaluate_doc_v3(
    fname: str,
    gt: dict[str, Any],
    pred: dict[str, Any] | None,
    pdf_text: str,
) -> dict[str, Any]:
    """Score one document under COMPLETE_GT_ONLY_V3 rules.

    Returns scored FactResults plus nicht_bewertbar records. Never labels
    count-only employment/education extracts as hallucinated/correct.
    """
    # Build V2 evidence, then strip list fields that are not complete GT
    # so V2's expect_absent path is not used for those groups.
    evidence = build_evidence_for_doc(fname, gt, pdf_text)
    ev = dict(evidence.get("evaluable_fields") or {})
    non_ev = dict(evidence.get("non_evaluable_fields") or {})
    nicht: list[NichtBewertbarFact] = []

    for key, group in (
        ("employment", "employment"),
        ("education", "education"),
        ("skills", "skills"),
        ("software", "software"),
        ("certificates", "certificates"),
    ):
        status, reason = list_field_gt_status(gt, key)
        pred_sum = _pred_list_summary(pred or {}, group)
        if status != "complete":
            # Remove from evaluable so V2 does not invent expect_absent FPs
            ev.pop(key, None)
            non_ev[key] = reason
            grounded = _entries_text_grounded(pred_sum, pdf_text) if pred_sum else None
            nicht.append(
                NichtBewertbarFact(
                    document=fname,
                    field=key,
                    group=group,
                    reason=reason,
                    gt_keys_present=[
                        k
                        for k in (
                            key,
                            {
                                "employment": "work_count",
                                "education": "education_count",
                                "skills": "skills_count",
                                "software": "software_count",
                                "certificates": "certificates_count",
                            }[key],
                        )
                        if k in gt
                    ],
                    pred_summary=pred_sum,
                    text_grounded=grounded,
                )
            )

    evidence_v3 = {
        **evidence,
        "evaluable_fields": ev,
        "non_evaluable_fields": non_ev,
        "scorer": METRIC_NAME,
    }
    rows = evaluate_doc_v2(fname, gt, pred, evidence_v3)
    # Tag rows
    for r in rows:
        r.document = fname
    return {
        "document": fname,
        "scored_rows": rows,
        "nicht_bewertbar": nicht,
        "evidence": evidence_v3,
    }


def aggregate_v3(doc_results: list[dict[str, Any]]) -> dict[str, Any]:
    scored: list[FactResult] = []
    nicht: list[dict[str, Any]] = []
    for dr in doc_results:
        scored.extend(dr["scored_rows"])
        for n in dr["nicht_bewertbar"]:
            nicht.append(asdict(n) if isinstance(n, NichtBewertbarFact) else n)

    agg = aggregate_v2(scored) if scored else {
        "field_total": 0,
        "counts": {},
        "f1": 0.0,
        "precision": 0.0,
        "recall": 0.0,
        "hallucination_rate": 0.0,
        "missing_field_rate": 0.0,
    }
    missing = [r for r in scored if r.status == "missing"]
    hallu = [r for r in scored if r.status == "hallucinated"]
    wrong = [r for r in scored if r.status in {"wrong", "wrong_category"}]

    return {
        "metric_name": METRIC_NAME,
        "disclaimer": METRIC_DISCLAIMER,
        "complete_gt_scored": {
            **agg,
            "n_missing": len(missing),
            "n_hallucinated": len(hallu),
            "n_wrong": len(wrong),
            "missing_fields": [
                {"document": r.document, "field": r.field, "expected": r.expected} for r in missing
            ],
            "hallucinated_fields": [
                {
                    "document": r.document,
                    "field": r.field,
                    "expected": r.expected,
                    "actual": r.actual,
                }
                for r in hallu
            ],
            "wrong_fields": [
                {
                    "document": r.document,
                    "field": r.field,
                    "status": r.status,
                    "expected": r.expected,
                    "actual": r.actual,
                }
                for r in wrong
            ],
        },
        "nicht_bewertbar": {
            "n_fields": len(nicht),
            "by_group": dict(Counter(n["group"] for n in nicht)),
            "by_reason": dict(Counter(n["reason"] for n in nicht)),
            "cases": nicht,
        },
        "quality_claim_scope": [
            "COMPLETE_GT_ONLY_V3 F1 applies only to fields with full GT values.",
            "Employment/education quality cannot be claimed when GT is count-only.",
            "Not a blind-test result and not a 99% claim.",
        ],
    }


def score_predictions(
    *,
    manifest_path: Path,
    gt_path: Path,
    predictions: dict[str, dict[str, Any]],
    texts: dict[str, str],
) -> dict[str, Any]:
    """Score a prediction map with V3; leave V2 results untouched."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    gt_docs = json.loads(gt_path.read_text(encoding="utf-8"))["documents"]
    doc_results = []
    for meta in manifest["documents"]:
        fname = Path(meta["path"]).name
        doc_results.append(
            evaluate_doc_v3(fname, gt_docs[fname], predictions.get(fname), texts.get(fname, ""))
        )
    return {
        "metric_name": METRIC_NAME,
        "manifest_id": manifest.get("manifest_id"),
        "aggregate": aggregate_v3(doc_results),
        "per_document": [
            {
                "document": dr["document"],
                "n_scored": len(dr["scored_rows"]),
                "n_nicht_bewertbar": len(dr["nicht_bewertbar"]),
                "statuses": dict(Counter(r.status for r in dr["scored_rows"])),
            }
            for dr in doc_results
        ],
    }


if __name__ == "__main__":
    print(METRIC_NAME)
    print(METRIC_DISCLAIMER)
    print("Import evaluate_doc_v3 / aggregate_v3 / score_predictions from tests or runners.")
