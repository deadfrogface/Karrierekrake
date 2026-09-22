#!/usr/bin/env python3
"""Evaluate frozen Holdout-100 predictions against ground truth.

ONLY run AFTER predictions are fully written.
Reads: artifacts/holdout_100/frozen_baseline_predictions/
       tests/holdout_100/expected_results_full.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

HOLDOUT = ROOT / "tests" / "holdout_100"
GT_PATH = HOLDOUT / "expected_results_full.json"
PRED_ROOT = ROOT / "artifacts" / "holdout_100" / "frozen_baseline_predictions"
OUT = ROOT / "artifacts" / "holdout_100"


def _norm(s: Any) -> str:
    s = str(s or "").strip().lower()
    s = s.replace("–", "-").replace("—", "-").replace("−", "-")
    s = re.sub(r"\s+", " ", s)
    return s


def _digits(s: Any) -> str:
    return re.sub(r"\D", "", str(s or ""))


def _is_empty(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, (list, dict)) and len(v) == 0:
        return True
    if isinstance(v, str) and not v.strip():
        return True
    return False


def load_gt() -> dict[str, Any]:
    raw = json.loads(GT_PATH.read_text(encoding="utf-8"))
    # Accept either {docs: [...]} or {filename: {...}} or list
    if isinstance(raw, dict) and "documents" in raw:
        docs = raw["documents"]
        if isinstance(docs, list):
            return {d.get("file") or d.get("filename") or d.get("id"): d for d in docs}
        return docs
    if isinstance(raw, list):
        return {d.get("file") or d.get("filename") or d.get("id"): d for d in raw}
    # map by keys that look like pdf names
    if all(str(k).endswith(".pdf") for k in raw.keys()):
        return raw
    return raw


def pred_personal(p: dict[str, Any]) -> dict[str, Any]:
    pers = p.get("personal") or {}
    return pers


def get_field_actual(pred: dict[str, Any], field: str) -> Any:
    pers = pred_personal(pred)
    mapping = {
        "first_name": pers.get("first_name") or "",
        "last_name": pers.get("last_name") or "",
        "full_name": pers.get("full_name")
        or f"{pers.get('first_name') or ''} {pers.get('last_name') or ''}".strip(),
        "email": (pred.get("emails") or [None])[0] if pred.get("emails") else pers.get("email"),
        "emails": pred.get("emails") or [],
        "phone": (pred.get("phones") or [None])[0] if pred.get("phones") else pers.get("phone"),
        "phones": pred.get("phones") or [],
        "street": pers.get("street") or pers.get("address") or "",
        "postal_code": pers.get("postal_code") or "",
        "city": pers.get("city") or "",
        "country": pers.get("country") or "",
        "date_of_birth": pers.get("date_of_birth") or "",
        "languages": pred.get("languages") or [],
        "education": pred.get("education") or [],
        "work_experience": pred.get("work_experience") or [],
        "skills": pred.get("skills") or [],
        "software": pred.get("software") or [],
        "certificates": pred.get("certificates") or [],
        "driving_license": pred.get("driving_license") or "",
    }
    return mapping.get(field)


def gt_get(doc: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for k in keys:
        if k in doc and doc[k] is not None:
            return doc[k]
    # nested personal
    pers = doc.get("personal") or doc.get("contact") or {}
    for k in keys:
        if isinstance(pers, dict) and k in pers:
            return pers[k]
    return default


def compare_scalar(expected: Any, actual: Any, *, kind: str = "text") -> str:
    """Return correct|wrong|missing|hallucinated."""
    exp_empty = _is_empty(expected)
    act_empty = _is_empty(actual)
    if exp_empty and act_empty:
        return "correct"
    if exp_empty and not act_empty:
        return "hallucinated"
    if not exp_empty and act_empty:
        return "missing"
    if kind == "phone":
        if _digits(expected) and _digits(expected) in _digits(actual):
            return "correct"
        return "wrong"
    if kind == "email":
        if _norm(expected) == _norm(actual) or _norm(expected) in _norm(actual):
            return "correct"
        return "wrong"
    if _norm(expected) in _norm(actual) or _norm(actual) in _norm(expected):
        return "correct"
    return "wrong"


def compare_lang_list(expected: Any, actual: Any) -> list[dict[str, Any]]:
    results = []
    exp_list = expected if isinstance(expected, list) else []
    act_list = actual if isinstance(actual, list) else []
    act_names = []
    for a in act_list:
        if isinstance(a, dict):
            act_names.append(_norm(a.get("language") or a.get("name") or ""))
        else:
            act_names.append(_norm(str(a).split("-")[0]))
    for e in exp_list:
        if isinstance(e, dict):
            name = e.get("language") or e.get("name") or e.get("sprache") or ""
            level = e.get("level") or e.get("niveau") or ""
        elif isinstance(e, str):
            parts = [p.strip() for p in e.replace("–", "-").split("-", 1)]
            name, level = parts[0], parts[1] if len(parts) > 1 else ""
        else:
            name, level = str(e), ""
        n = _norm(name)
        if not n:
            continue
        if any(n in a or a in n for a in act_names if a):
            results.append({"field": f"language:{name}", "status": "correct", "expected": e, "actual": act_list})
        else:
            results.append({"field": f"language:{name}", "status": "missing", "expected": e, "actual": act_list})
    # hallucinations: actual languages not in expected names
    exp_names = set()
    for e in exp_list:
        if isinstance(e, dict):
            exp_names.add(_norm(e.get("language") or e.get("name") or ""))
        else:
            exp_names.add(_norm(str(e).split("-")[0]))
    for a, an in zip(act_list, act_names):
        if an and not any(an in en or en in an for en in exp_names if en):
            # possible wrong_category if looks like skill
            status = "hallucinated"
            results.append({"field": f"language_extra:{an}", "status": status, "expected": None, "actual": a})
    return results


def compare_named_entries(
    expected: Any,
    actual: Any,
    *,
    name_keys: tuple[str, ...],
    field_prefix: str,
) -> list[dict[str, Any]]:
    results = []
    exp_list = expected if isinstance(expected, list) else []
    act_list = actual if isinstance(actual, list) else []

    def names(lst: list, keys: tuple[str, ...]) -> list[str]:
        out = []
        for item in lst:
            if isinstance(item, dict):
                for k in keys:
                    if item.get(k):
                        out.append(_norm(item.get(k)))
                        break
                else:
                    out.append(_norm(json.dumps(item, ensure_ascii=False)))
            else:
                out.append(_norm(item))
        return out

    exp_n = names(exp_list, name_keys)
    act_n = names(act_list, name_keys)
    for i, en in enumerate(exp_n):
        if not en:
            continue
        if any(en in a or a in en for a in act_n if a):
            results.append(
                {
                    "field": f"{field_prefix}:{i}",
                    "status": "correct",
                    "expected": exp_list[i],
                    "actual": act_list,
                }
            )
        else:
            results.append(
                {
                    "field": f"{field_prefix}:{i}",
                    "status": "missing",
                    "expected": exp_list[i],
                    "actual": act_list,
                }
            )
    for j, an in enumerate(act_n):
        if an and not any(an in en or en in an for en in exp_n if en):
            results.append(
                {
                    "field": f"{field_prefix}_extra:{j}",
                    "status": "hallucinated",
                    "expected": None,
                    "actual": act_list[j] if j < len(act_list) else an,
                }
            )
    return results


def evaluate_doc(doc_name: str, gt: dict[str, Any], pred: dict[str, Any] | None) -> list[dict[str, Any]]:
    if pred is None:
        return [{"field": "_document", "status": "missing", "expected": "prediction", "actual": None}]
    rows: list[dict[str, Any]] = []

    # Flexible GT key access
    first = gt_get(gt, "first_name", "VORNAME", "vorname")
    last = gt_get(gt, "last_name", "NACHNAME", "nachname")
    email = gt_get(gt, "email", "E-MAIL", "e_mail", "emails")
    if isinstance(email, list):
        email = email[0] if email else ""
    phone = gt_get(gt, "phone", "TELEFON", "telefon", "phones")
    if isinstance(phone, list):
        phone = phone[0] if phone else ""
    street = gt_get(gt, "street", "STRASSE", "strasse", "address_street")
    plz = gt_get(gt, "postal_code", "PLZ", "plz", "zip")
    city = gt_get(gt, "city", "ORT", "ort")
    country = gt_get(gt, "country", "LAND", "land")
    dob = gt_get(gt, "date_of_birth", "GEBURTSDATUM", "dob")

    checks = [
        ("first_name", first, get_field_actual(pred, "first_name"), "text"),
        ("last_name", last, get_field_actual(pred, "last_name"), "text"),
        ("email", email, get_field_actual(pred, "email"), "email"),
        ("phone", phone, get_field_actual(pred, "phone"), "phone"),
        ("street", street, get_field_actual(pred, "street"), "text"),
        ("postal_code", plz, get_field_actual(pred, "postal_code"), "text"),
        ("city", city, get_field_actual(pred, "city"), "text"),
        ("country", country, get_field_actual(pred, "country"), "text"),
        ("date_of_birth", dob, get_field_actual(pred, "date_of_birth"), "text"),
    ]
    for field, exp, act, kind in checks:
        if exp is None and field in ("country", "date_of_birth", "street", "postal_code"):
            # unknown if key absent entirely — skip
            if field not in gt and not any(
                k in gt for k in (
                    "STRASSE", "PLZ", "ORT", "LAND", "GEBURTSDATUM",
                    "street", "postal_code", "city", "country", "date_of_birth",
                    "personal", "contact", "address",
                )
            ):
                continue
        status = compare_scalar(exp, act, kind=kind)
        rows.append({"field": field, "status": status, "expected": exp, "actual": act})

    langs = gt_get(gt, "languages", "sprachen", "SPRACHEN", default=[])
    rows.extend(compare_lang_list(langs or [], get_field_actual(pred, "languages")))

    edu = gt_get(gt, "education", "ausbildung", "AUSBILDUNG", default=[])
    rows.extend(
        compare_named_entries(
            edu or [],
            get_field_actual(pred, "education"),
            name_keys=("qualification", "degree", "title", "name", "abschluss"),
            field_prefix="education",
        )
    )
    work = gt_get(gt, "work_experience", "experience", "employment", "berufserfahrung", default=[])
    rows.extend(
        compare_named_entries(
            work or [],
            get_field_actual(pred, "work_experience"),
            name_keys=("title", "position", "role", "company", "arbeitgeber"),
            field_prefix="work",
        )
    )
    skills = gt_get(gt, "skills", "kenntnisse", "SKILLS", default=[])
    if isinstance(skills, str):
        skills = [s.strip() for s in skills.split(",") if s.strip()]
    rows.extend(
        compare_named_entries(
            skills or [],
            [{"name": s} for s in (get_field_actual(pred, "skills") or [])],
            name_keys=("name",),
            field_prefix="skill",
        )
    )
    software = gt_get(gt, "software", "tools", "SOFTWARE", default=[])
    if isinstance(software, str):
        software = [s.strip() for s in software.split(",") if s.strip()]
    rows.extend(
        compare_named_entries(
            software or [],
            [{"name": s} for s in (get_field_actual(pred, "software") or [])],
            name_keys=("name",),
            field_prefix="software",
        )
    )
    certs = gt_get(gt, "certificates", "zertifikate", "CERTIFICATES", default=[])
    rows.extend(
        compare_named_entries(
            certs or [],
            get_field_actual(pred, "certificates"),
            name_keys=("name", "title", "certificate"),
            field_prefix="certificate",
        )
    )
    licence = gt_get(gt, "driving_license", "fuehrerschein", "führerschein", "license", default="")
    rows.append(
        {
            "field": "driving_license",
            "status": compare_scalar(licence, get_field_actual(pred, "driving_license")),
            "expected": licence,
            "actual": get_field_actual(pred, "driving_license"),
        }
    )
    for r in rows:
        r["document"] = doc_name
    return rows


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows) or 1
    counts = defaultdict(int)
    for r in rows:
        counts[r["status"]] += 1
    tp = counts["correct"]
    fp = counts["hallucinated"] + counts["wrong"]
    fn = counts["missing"]
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    # critical FP weight
    critical_penalty = counts["hallucinated"] * 5 + counts["wrong"] * 3 + counts["missing"] * 1
    quality_score = max(0.0, 1.0 - critical_penalty / max(1, n * 2))
    return {
        "field_total": len(rows),
        "counts": dict(counts),
        "field_accuracy": counts["correct"] / n,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "hallucination_rate": counts["hallucinated"] / n,
        "missing_field_rate": counts["missing"] / n,
        "false_positive_rate": fp / n,
        "critical_penalty": critical_penalty,
        "quality_score": quality_score,
    }


def load_pipeline_predictions(name: str) -> dict[str, dict[str, Any]]:
    d = PRED_ROOT / name
    out = {}
    if not d.is_dir():
        return out
    for f in d.glob("HO_*.json"):
        rec = json.loads(f.read_text(encoding="utf-8"))
        out[rec.get("document") or f.name.replace(".json", ".pdf")] = rec
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pipelines", default="")
    args = ap.parse_args()

    if not PRED_ROOT.is_dir():
        raise SystemExit("missing frozen predictions dir")

    # Discover pipelines with summaries
    pipelines = []
    for p in sorted(PRED_ROOT.iterdir()):
        if p.is_dir() and (p / "_summary.json").exists():
            pipelines.append(p.name)
    if args.pipelines:
        pipelines = [x.strip() for x in args.pipelines.split(",") if x.strip()]

    gt_all = load_gt()
    # normalize keys to filenames
    gt_by_file: dict[str, Any] = {}
    if isinstance(gt_all, dict):
        for k, v in gt_all.items():
            if k in ("schema_version", "meta", "documents"):
                continue
            if isinstance(v, dict):
                fname = v.get("file") or v.get("filename") or (k if str(k).endswith(".pdf") else None)
                if fname:
                    gt_by_file[str(fname)] = v
                elif str(k).endswith(".pdf"):
                    gt_by_file[str(k)] = v
        if not gt_by_file and "documents" in gt_all:
            for d in gt_all["documents"]:
                gt_by_file[d.get("file") or d.get("filename")] = d

    print(f"GT documents: {len(gt_by_file)} keys sample={list(gt_by_file)[:3]}")

    pipeline_results = {}
    per_document = {}
    per_field_all = []
    perf = {}

    for pipe in pipelines:
        summary_path = PRED_ROOT / pipe / "_summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        if summary.get("status") == "NOT_AVAILABLE":
            pipeline_results[pipe] = summary
            continue
        preds = load_pipeline_predictions(pipe)
        rows: list[dict[str, Any]] = []
        perfect = 0
        critical_docs = 0
        doc_rows_map = {}
        for fname, gt in sorted(gt_by_file.items()):
            rec = preds.get(fname)
            pred = (rec or {}).get("prediction")
            doc_rows = evaluate_doc(fname, gt, pred)
            for r in doc_rows:
                r["pipeline"] = pipe
            rows.extend(doc_rows)
            doc_rows_map[fname] = doc_rows
            statuses = {r["status"] for r in doc_rows}
            if statuses <= {"correct"}:
                perfect += 1
            if "hallucinated" in statuses or "wrong" in statuses:
                critical_docs += 1
        agg = aggregate(rows)
        agg.update(
            {
                "pipeline": pipe,
                "perfect_documents": perfect,
                "documents_with_critical": critical_docs,
                "document_perfect_match_rate": perfect / max(1, len(gt_by_file)),
                "wall_s": summary.get("wall_s"),
                "avg_s": summary.get("avg_s"),
                "median_s": summary.get("median_s"),
                "p95_s": summary.get("p95_s"),
                "peak_rss_mb": summary.get("peak_rss_mb"),
                "n_documents": summary.get("n_documents"),
            }
        )
        pipeline_results[pipe] = agg
        per_document[pipe] = {
            fname: {
                "counts": dict(
                    defaultdict(
                        int,
                        {
                            s: sum(1 for r in doc_rows_map[fname] if r["status"] == s)
                            for s in ("correct", "wrong", "missing", "hallucinated")
                        },
                    )
                ),
                "rows": doc_rows_map[fname],
            }
            for fname in doc_rows_map
        }
        per_field_all.extend(rows)
        perf[pipe] = {
            "wall_s": summary.get("wall_s"),
            "avg_s": summary.get("avg_s"),
            "median_s": summary.get("median_s"),
            "p95_s": summary.get("p95_s"),
            "peak_rss_mb": summary.get("peak_rss_mb"),
        }
        print(
            f"{pipe}: acc={agg['field_accuracy']:.4f} F1={agg['f1']:.4f} "
            f"hallu={agg['hallucination_rate']:.4f} perfect={perfect}/{len(gt_by_file)} "
            f"quality={agg['quality_score']:.4f} avg_s={agg.get('avg_s')}"
        )

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "pipeline_results.json").write_text(
        json.dumps(pipeline_results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT / "per_document_results.json").write_text(
        json.dumps(per_document, ensure_ascii=False), encoding="utf-8"
    )
    (OUT / "per_field_results.json").write_text(
        json.dumps(per_field_all[:50000], ensure_ascii=False), encoding="utf-8"
    )
    (OUT / "performance_results.json").write_text(
        json.dumps(perf, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"wrote results under {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
