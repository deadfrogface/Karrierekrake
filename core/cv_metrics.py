"""Field-level CV extraction metrics against Sollwerte ground truth.

Used for baseline / ablation / final reports. Does not change ground truth.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(_ROOT / "scripts"))

from run_cv_sollwerte_corpus import (  # type: ignore[import-not-found]
    _is_absent,
    _norm,
    _parse_edu,
    _parse_lang,
    _digits,
    evaluate,
)


@dataclass
class FieldResult:
    document: str
    field: str
    expected: Any
    actual: Any
    status: str  # correct | wrong | missing | hallucinated | wrong_category
    phi_involved: bool = False
    extractor_path: str = "deterministic"
    notes: str = ""


@dataclass
class DocMetrics:
    document: str
    field_results: list[FieldResult] = field(default_factory=list)
    perfect: bool = False
    extractor_path: str = "deterministic"
    phi_involved: bool = False
    elapsed_s: float = 0.0


def classify_failures(
    document: str,
    parsed: dict[str, Any],
    exp: dict[str, Any],
    *,
    phi_involved: bool = False,
    extractor_path: str = "deterministic",
) -> DocMetrics:
    """Expand evaluate() fails into typed FieldResult rows + inferred corrects."""
    fails = evaluate(parsed, exp)
    fail_fields = {f["field"] for f in fails}
    results: list[FieldResult] = []

    for f in fails:
        kind = f.get("kind") or "mismatch"
        if kind == "invented":
            status = "hallucinated"
        elif kind in {"wrong_category", "trap"}:
            status = "wrong_category"
        elif kind == "count" and (f.get("got") or 0) < (f.get("expected") or 0):
            status = "missing"
        elif f.get("got") in (None, "", [], {}):
            status = "missing"
        else:
            status = "wrong"
        results.append(
            FieldResult(
                document=document,
                field=f["field"],
                expected=f.get("expected"),
                actual=f.get("got"),
                status=status,
                phi_involved=phi_involved,
                extractor_path=extractor_path,
                notes=str(kind),
            )
        )

    # Positive checks for key present expected fields (approximation for accuracy denom)
    checked: list[tuple[str, Any, Any]] = []
    personal = parsed.get("personal") or {}
    if not _is_absent(exp.get("VORNAME")):
        checked.append(("VORNAME", exp["VORNAME"], personal.get("first_name")))
    if not _is_absent(exp.get("NACHNAME")):
        checked.append(("NACHNAME", exp["NACHNAME"], personal.get("last_name")))
    if not _is_absent(exp.get("E-MAIL")):
        checked.append(("E-MAIL", exp["E-MAIL"], parsed.get("emails")))
    if not _is_absent(exp.get("TELEFON")):
        checked.append(("TELEFON", exp["TELEFON"], parsed.get("phones")))

    exp_n = int(exp.get("SPRACHEN_ANZAHL") or 0)
    for i in range(1, exp_n + 1):
        raw = exp.get(f"SPRACHE_{i}") or ""
        if raw and not _is_absent(raw):
            checked.append((f"SPRACHE_{i}", raw, parsed.get("languages")))

    for i in range(1, int(exp.get("BERUFE_ANZAHL") or 0) + 1):
        raw = exp.get(f"BERUF_{i}") or ""
        if raw and not _is_absent(raw):
            checked.append((f"BERUF_{i}", raw, parsed.get("work_experience")))

    for i in range(1, int(exp.get("AUSBILDUNG_ANZAHL") or 0) + 1):
        raw = exp.get(f"AUSBILDUNG_{i}") or ""
        if raw and not _is_absent(raw):
            checked.append((f"AUSBILDUNG_{i}", raw, parsed.get("education")))

    for name, expected, actual in checked:
        if name in fail_fields:
            continue
        results.append(
            FieldResult(
                document=document,
                field=name,
                expected=expected,
                actual=actual,
                status="correct",
                phi_involved=phi_involved,
                extractor_path=extractor_path,
            )
        )

    # Explicit absent-must-stay-empty checks that passed
    for key in ("TELEFON", "GEBURTSDATUM", "STRASSE", "PLZ"):
        if _is_absent(exp.get(key)) and key not in fail_fields:
            results.append(
                FieldResult(
                    document=document,
                    field=f"{key}_ABSENT",
                    expected="NICHT VORHANDEN",
                    actual=None,
                    status="correct",
                    phi_involved=phi_involved,
                    extractor_path=extractor_path,
                    notes="absence_preserved",
                )
            )

    dm = DocMetrics(
        document=document,
        field_results=results,
        perfect=len(fails) == 0,
        extractor_path=extractor_path,
        phi_involved=phi_involved,
    )
    return dm


def aggregate(docs: list[DocMetrics]) -> dict[str, Any]:
    all_f = [fr for d in docs for fr in d.field_results]
    n = len(all_f) or 1
    counts = {
        "correct": sum(1 for f in all_f if f.status == "correct"),
        "wrong": sum(1 for f in all_f if f.status == "wrong"),
        "missing": sum(1 for f in all_f if f.status == "missing"),
        "hallucinated": sum(1 for f in all_f if f.status == "hallucinated"),
        "wrong_category": sum(1 for f in all_f if f.status == "wrong_category"),
    }
    tp = counts["correct"]
    fp = counts["hallucinated"] + counts["wrong"] + counts["wrong_category"]
    fn = counts["missing"]
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {
        "documents": len(docs),
        "perfect_documents": sum(1 for d in docs if d.perfect),
        "document_perfect_match_rate": (
            sum(1 for d in docs if d.perfect) / len(docs) if docs else 0.0
        ),
        "field_total": len(all_f),
        "counts": counts,
        "field_accuracy": counts["correct"] / n,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "false_positive_rate": (counts["hallucinated"] + counts["wrong"]) / n,
        "missing_field_rate": counts["missing"] / n,
        "wrong_category_rate": counts["wrong_category"] / n,
        "fields": [asdict(f) for f in all_f],
        "doc_summaries": [
            {
                "document": d.document,
                "perfect": d.perfect,
                "phi_involved": d.phi_involved,
                "extractor_path": d.extractor_path,
                "elapsed_s": d.elapsed_s,
                "fail_count": sum(1 for f in d.field_results if f.status != "correct"),
            }
            for d in docs
        ],
    }


# Re-export helpers used by callers that import from this module
__all__ = [
    "FieldResult",
    "DocMetrics",
    "classify_failures",
    "aggregate",
    "_norm",
    "_is_absent",
    "_parse_lang",
    "_parse_edu",
    "_digits",
]
