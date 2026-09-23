#!/usr/bin/env python3
"""Evaluate frozen Holdout-100 predictions against expected_results_full.json.

Run ONLY after frozen predictions are complete and sealed.
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

CRITICAL_FIELDS = {
    "first_name",
    "last_name",
    "email",
    "employment",
    "education",
    "languages",
    "licenses",
}


def _norm(s: Any) -> str:
    s = str(s or "").strip().lower()
    s = s.replace("–", "-").replace("—", "-").replace("−", "-")
    s = re.sub(r"\s+", " ", s)
    return s


def _digits(s: Any) -> str:
    return re.sub(r"\D", "", str(s or ""))


def _empty(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, (list, dict)) and len(v) == 0:
        return True
    if isinstance(v, str) and not str(v).strip():
        return True
    return False


def load_gt() -> dict[str, Any]:
    raw = json.loads(GT_PATH.read_text(encoding="utf-8"))
    docs = raw.get("documents") or {}
    if isinstance(docs, dict):
        return docs
    raise SystemExit("unexpected GT documents shape")


def resolve_pred_dir(name: str) -> Path:
    d = PRED_ROOT / name
    alias = d / "USE_PIPELINE.txt"
    if alias.is_file():
        return PRED_ROOT / alias.read_text(encoding="utf-8").strip()
    return d


def load_predictions(name: str) -> dict[str, dict[str, Any]]:
    d = resolve_pred_dir(name)
    out: dict[str, dict[str, Any]] = {}
    if not d.is_dir():
        return out
    for f in d.glob("HO_*.json"):
        rec = json.loads(f.read_text(encoding="utf-8"))
        out[rec.get("document") or (f.stem + ".pdf")] = rec
    return out


def pred_view(pred: dict[str, Any] | None) -> dict[str, Any]:
    if not pred:
        return {}
    pers = pred.get("personal") or {}
    out = {
        "first_name": pers.get("first_name") or "",
        "last_name": pers.get("last_name") or "",
        "email": (pred.get("emails") or [""])[0] if pred.get("emails") else "",
        "phone": (pred.get("phones") or [""])[0] if pred.get("phones") else "",
        "street": pers.get("street") or "",
        "house_number": pers.get("house_number") or "",
        "postal_code": pers.get("postal_code") or "",
        "city": pers.get("city") or "",
        "country": pers.get("country") or "",
        "dob": pers.get("date_of_birth") or "",
        "languages": pred.get("languages") or [],
        "education": pred.get("education") or [],
        "employment": pred.get("work_experience") or [],
        "skills": pred.get("skills") or [],
        "software": pred.get("software") or [],
        "certificates": pred.get("certificates") or [],
        "licenses": pred.get("driving_license") or "",
        "target_role": pred.get("target_role") or "",
    }
    lic = out["licenses"]
    if isinstance(lic, list):
        parts = []
        for item in lic:
            if isinstance(item, dict):
                parts.append(str(item.get("value") or item.get("name") or ""))
            else:
                parts.append(str(item))
        out["licenses"] = " ".join(p for p in parts if p)
    return out


def scalar_status(expected: Any, actual: Any, *, kind: str = "text") -> str:
    if _empty(expected) and _empty(actual):
        return "correct"
    if _empty(expected) and not _empty(actual):
        return "hallucinated"
    if not _empty(expected) and _empty(actual):
        return "missing"
    if kind == "phone":
        ed, ad = _digits(expected), _digits(actual)
        if ed and ed in ad:
            return "correct"
        # allow last 6 digits match
        if len(ed) >= 6 and ed[-6:] in ad:
            return "correct"
        return "wrong"
    if kind == "email":
        if _norm(expected) == _norm(actual):
            return "correct"
        return "wrong"
    if _norm(expected) == _norm(actual):
        return "correct"
    if _norm(expected) in _norm(actual) or _norm(actual) in _norm(expected):
        return "correct"
    return "wrong"


def list_membership(
    expected_items: list[str],
    actual_items: list[str],
    *,
    prefix: str,
) -> list[dict[str, Any]]:
    rows = []
    exp_n = [_norm(x) for x in expected_items if _norm(x)]
    act_n = [_norm(x) for x in actual_items if _norm(x)]
    for i, e in enumerate(exp_n):
        if any(e in a or a in e for a in act_n):
            rows.append({"field": f"{prefix}:{i}", "status": "correct", "expected": expected_items[i], "actual": actual_items})
        else:
            rows.append({"field": f"{prefix}:{i}", "status": "missing", "expected": expected_items[i], "actual": actual_items})
    for j, a in enumerate(act_n):
        if not any(a in e or e in a for e in exp_n):
            rows.append({"field": f"{prefix}_extra:{j}", "status": "hallucinated", "expected": None, "actual": actual_items[j] if j < len(actual_items) else a})
    return rows


def evaluate_doc(fname: str, gt: dict[str, Any], pred: dict[str, Any] | None) -> list[dict[str, Any]]:
    pv = pred_view(pred)
    name = gt.get("name") or {}
    addr = gt.get("address") or {}
    rows: list[dict[str, Any]] = []

    def add(field: str, expected: Any, actual: Any, kind: str = "text", group: str = "personal") -> None:
        # If GT lists field as deliberately missing, empty actual is correct; inventing is hallucination
        missing = set(gt.get("missing") or [])
        if field in missing or (isinstance(expected, str) and expected.upper() in {"", "NULL", "NONE"}):
            st = "correct" if _empty(actual) else "hallucinated"
        else:
            st = scalar_status(expected, actual, kind=kind)
        rows.append(
            {
                "document": fname,
                "field": field,
                "group": group,
                "status": st,
                "expected": expected,
                "actual": actual,
                "critical": field in CRITICAL_FIELDS or group in {"employment", "education", "languages"},
            }
        )

    add("first_name", name.get("first_name"), pv["first_name"], group="personal")
    add("last_name", name.get("last_name"), pv["last_name"], group="personal")
    add("email", gt.get("email"), pv["email"], kind="email", group="personal")
    add("phone", gt.get("phone"), pv["phone"], kind="phone", group="personal")
    add("street", addr.get("street"), pv["street"], group="address")
    add("house_number", addr.get("house_number"), pv["house_number"], group="address")
    add("postal_code", addr.get("postal_code"), pv["postal_code"], group="address")
    add("city", addr.get("city"), pv["city"], group="address")
    add("country", addr.get("country"), pv["country"], group="address")
    add("dob", gt.get("dob"), pv["dob"], group="personal")

    # languages: GT [[name, level], ...]
    exp_langs = []
    for item in gt.get("languages") or []:
        if isinstance(item, (list, tuple)) and item:
            exp_langs.append(str(item[0]))
        elif isinstance(item, dict):
            exp_langs.append(str(item.get("language") or item.get("name") or ""))
        else:
            exp_langs.append(str(item))
    act_langs = []
    for item in pv["languages"]:
        if isinstance(item, dict):
            act_langs.append(str(item.get("language") or ""))
        else:
            act_langs.append(str(item))
    for r in list_membership(exp_langs, act_langs, prefix="language"):
        r.update({"document": fname, "group": "languages", "critical": True})
        # wrong_category if non-language hallucinated into languages
        if r["status"] == "hallucinated":
            r["status"] = "wrong_category"
            r["error_class"] = "language_skill_confusion"
        rows.append(r)

    # education
    exp_edu = [str(e.get("qualification") or "") for e in (gt.get("education") or [])]
    act_edu = []
    for e in pv["education"]:
        if isinstance(e, dict):
            act_edu.append(str(e.get("qualification") or e.get("degree") or ""))
        else:
            act_edu.append(str(e))
    for r in list_membership(exp_edu, act_edu, prefix="education"):
        r.update({"document": fname, "group": "education", "critical": True})
        rows.append(r)

    # employment: match on position OR company
    exp_pos = [str(e.get("position") or "") for e in (gt.get("employment") or [])]
    exp_co = [str(e.get("company") or "") for e in (gt.get("employment") or [])]
    act_pos, act_co = [], []
    for e in pv["employment"]:
        if isinstance(e, dict):
            act_pos.append(str(e.get("title") or e.get("position") or ""))
            act_co.append(str(e.get("company") or ""))
        else:
            act_pos.append(str(e))
            act_co.append("")
    # position match
    for i, ep in enumerate(exp_pos):
        en = _norm(ep)
        cn = _norm(exp_co[i]) if i < len(exp_co) else ""
        hit = any(en and (en in _norm(a) or _norm(a) in en) for a in act_pos) or any(
            cn and (cn in _norm(a) or _norm(a) in cn) for a in act_co
        )
        rows.append(
            {
                "document": fname,
                "field": f"employment:{i}",
                "group": "employment",
                "status": "correct" if hit else "missing",
                "expected": {"position": ep, "company": exp_co[i] if i < len(exp_co) else ""},
                "actual": pv["employment"],
                "critical": True,
            }
        )
    # hallucinated jobs
    for j, ap in enumerate(act_pos):
        an = _norm(ap)
        cn = _norm(act_co[j]) if j < len(act_co) else ""
        if not an and not cn:
            continue
        hit = any(an and (an in _norm(e) or _norm(e) in an) for e in exp_pos) or any(
            cn and (cn in _norm(e) or _norm(e) in cn) for e in exp_co
        )
        if not hit:
            rows.append(
                {
                    "document": fname,
                    "field": f"employment_extra:{j}",
                    "group": "employment",
                    "status": "hallucinated",
                    "expected": None,
                    "actual": pv["employment"][j] if j < len(pv["employment"]) else ap,
                    "critical": True,
                }
            )

    for group, key, act_key in (
        ("skills", "skills", "skills"),
        ("software", "software", "software"),
    ):
        exp = [str(x) for x in (gt.get(key) or [])]
        act = [str(x) for x in (pv.get(act_key) or [])]
        for r in list_membership(exp, act, prefix=group[:-1] if group.endswith("s") else group):
            r.update({"document": fname, "group": group, "critical": False})
            rows.append(r)

    exp_cert = []
    for c in gt.get("certificates") or []:
        exp_cert.append(c if isinstance(c, str) else str((c or {}).get("name") or c))
    act_cert = []
    for c in pv["certificates"]:
        act_cert.append(c.get("name") if isinstance(c, dict) else str(c))
    for r in list_membership(exp_cert, act_cert, prefix="certificate"):
        r.update({"document": fname, "group": "certificates", "critical": False})
        rows.append(r)

    # licenses
    exp_lic = gt.get("licenses") or []
    exp_lic_s = " ".join(str(x) for x in exp_lic)
    act_lic = str(pv["licenses"] or "")
    if not exp_lic and _empty(act_lic):
        st = "correct"
    elif not exp_lic and not _empty(act_lic):
        st = "hallucinated"
    elif exp_lic and _empty(act_lic):
        st = "missing"
    else:
        st = "correct" if any(_norm(x) in _norm(act_lic) for x in exp_lic) else "wrong"
    rows.append(
        {
            "document": fname,
            "field": "licenses",
            "group": "licenses",
            "status": st,
            "expected": exp_lic,
            "actual": act_lic,
            "critical": True,
        }
    )

    # target_role: future role must NOT appear as employment (trap)
    target = gt.get("target_role") or ""
    if target:
        in_emp = any(_norm(target) in _norm(x) for x in act_pos)
        rows.append(
            {
                "document": fname,
                "field": "target_role_not_employment",
                "group": "employment",
                "status": "wrong_category" if in_emp else "correct",
                "expected": "not_in_employment",
                "actual": "present_in_employment" if in_emp else "absent",
                "critical": True,
                "error_class": "wrong_entity_link" if in_emp else None,
            }
        )

    return rows


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows) or 1
    counts: dict[str, int] = defaultdict(int)
    for r in rows:
        counts[r["status"]] += 1
    tp = counts["correct"]
    fp = counts["hallucinated"] + counts["wrong"] + counts["wrong_category"]
    fn = counts["missing"]
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    # weighting: hallu*5, wrong_category*4, wrong*3, missing*1
    penalty = (
        counts["hallucinated"] * 5
        + counts["wrong_category"] * 4
        + counts["wrong"] * 3
        + counts["missing"] * 1
    )
    quality = max(0.0, 1.0 - penalty / max(1.0, n * 3.0))
    by_group: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in rows:
        by_group[r.get("group") or "other"][r["status"]] += 1
    return {
        "field_total": len(rows),
        "counts": dict(counts),
        "field_accuracy": counts["correct"] / n,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "hallucination_rate": counts["hallucinated"] / n,
        "missing_field_rate": counts["missing"] / n,
        "wrong_category_rate": counts["wrong_category"] / n,
        "false_positive_rate": fp / n,
        "critical_penalty": penalty,
        "quality_score": quality,
        "by_group": {g: dict(c) for g, c in by_group.items()},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pipelines", default="")
    args = ap.parse_args()

    gt = load_gt()
    pipelines = []
    for p in sorted(PRED_ROOT.iterdir()):
        if p.is_dir() and (p / "_summary.json").exists() and not p.name.startswith("_"):
            pipelines.append(p.name)
    if args.pipelines:
        pipelines = [x.strip() for x in args.pipelines.split(",") if x.strip()]

    pipeline_results: dict[str, Any] = {}
    per_document: dict[str, Any] = {}
    per_field: list[dict[str, Any]] = []
    perf: dict[str, Any] = {}
    errors: list[dict[str, Any]] = []

    for pipe in pipelines:
        summary = json.loads((PRED_ROOT / pipe / "_summary.json").read_text(encoding="utf-8"))
        if summary.get("status") == "NOT_AVAILABLE":
            pipeline_results[pipe] = summary
            continue
        preds = load_predictions(pipe)
        rows: list[dict[str, Any]] = []
        perfect = 0
        critical_docs = 0
        doc_map = {}
        for fname, gtd in sorted(gt.items()):
            rec = preds.get(fname)
            pred = (rec or {}).get("prediction")
            doc_rows = evaluate_doc(fname, gtd, pred)
            for r in doc_rows:
                r["pipeline"] = pipe
            rows.extend(doc_rows)
            doc_map[fname] = doc_rows
            statuses = {r["status"] for r in doc_rows}
            if statuses <= {"correct"}:
                perfect += 1
            if any(r["status"] in {"hallucinated", "wrong", "wrong_category"} and r.get("critical") for r in doc_rows):
                critical_docs += 1
            for r in doc_rows:
                if r["status"] != "correct":
                    errors.append(
                        {
                            "document": fname,
                            "field": r["field"],
                            "expected": r.get("expected"),
                            "actual": r.get("actual"),
                            "pipeline": pipe,
                            "error_class": r.get("error_class") or r["status"],
                            "group": r.get("group"),
                            "critical": r.get("critical"),
                            "layout": gtd.get("layout"),
                            "language": gtd.get("language"),
                            "traps": gtd.get("traps"),
                        }
                    )
        agg = aggregate(rows)
        agg.update(
            {
                "pipeline": pipe,
                "perfect_documents": perfect,
                "documents_with_critical": critical_docs,
                "document_perfect_match_rate": perfect / max(1, len(gt)),
                "wall_s": summary.get("wall_s"),
                "avg_s": summary.get("avg_s"),
                "median_s": summary.get("median_s"),
                "p95_s": summary.get("p95_s"),
                "peak_rss_mb": summary.get("peak_rss_mb"),
                "alias_of": summary.get("alias_of"),
            }
        )
        pipeline_results[pipe] = agg
        per_document[pipe] = {
            fname: {
                "counts": {
                    s: sum(1 for r in doc_map[fname] if r["status"] == s)
                    for s in ("correct", "wrong", "missing", "hallucinated", "wrong_category")
                }
            }
            for fname in doc_map
        }
        per_field.extend(rows)
        perf[pipe] = {
            k: summary.get(k)
            for k in ("wall_s", "avg_s", "median_s", "p95_s", "peak_rss_mb", "n_ok", "n_error")
        }
        print(
            f"{pipe}: acc={agg['field_accuracy']:.4f} F1={agg['f1']:.4f} "
            f"hallu={agg['hallucination_rate']:.4f} wcat={agg['wrong_category_rate']:.4f} "
            f"perfect={perfect}/{len(gt)} crit_docs={critical_docs} "
            f"quality={agg['quality_score']:.4f} avg_s={agg.get('avg_s')}"
        )

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "pipeline_results.json").write_text(
        json.dumps(pipeline_results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT / "per_document_results.json").write_text(
        json.dumps(per_document, ensure_ascii=False), encoding="utf-8"
    )
    # store compact per-field (errors + sample corrects would be huge) — store all errors + summary counts already in pipeline
    (OUT / "per_field_results.json").write_text(
        json.dumps({"n_rows": len(per_field), "errors_only_in_error_inventory": True}, indent=2),
        encoding="utf-8",
    )
    (OUT / "performance_results.json").write_text(
        json.dumps(perf, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT / "error_inventory.json").write_text(
        json.dumps(errors, ensure_ascii=False), encoding="utf-8"
    )
    # ranking
    ranked = sorted(
        (
            (k, v)
            for k, v in pipeline_results.items()
            if isinstance(v, dict) and "field_accuracy" in v
        ),
        key=lambda kv: (kv[1]["quality_score"], kv[1]["f1"], -float(kv[1].get("avg_s") or 0)),
        reverse=True,
    )
    (OUT / "ranking.json").write_text(
        json.dumps(
            [
                {
                    "rank": i + 1,
                    "pipeline": k,
                    "field_accuracy": v["field_accuracy"],
                    "f1": v["f1"],
                    "hallucination_rate": v["hallucination_rate"],
                    "wrong_category_rate": v["wrong_category_rate"],
                    "perfect_documents": v["perfect_documents"],
                    "avg_s": v.get("avg_s"),
                    "peak_rss_mb": v.get("peak_rss_mb"),
                    "documents_with_critical": v["documents_with_critical"],
                    "quality_score": v["quality_score"],
                }
                for i, (k, v) in enumerate(ranked)
            ],
            indent=2,
        ),
        encoding="utf-8",
    )
    print("RANKING:")
    for i, (k, v) in enumerate(ranked, 1):
        print(
            f"  {i}. {k} acc={v['field_accuracy']:.4f} F1={v['f1']:.4f} "
            f"hallu={v['hallucination_rate']:.4f} perfect={v['perfect_documents']} "
            f"avg_s={v.get('avg_s')} quality={v['quality_score']:.4f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
