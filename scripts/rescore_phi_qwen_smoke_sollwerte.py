#!/usr/bin/env python3
"""Rescore existing #97 Phi/Qwen SMOKE predictions against full Sollwerte GT.

Does NOT re-run models. Clarifies that Scorer-V2 ``invented_*`` on count-only
JSON GT are nicht_bewertbar / GT artifacts when Sollwerte lists exist.

KNOWN development corpus — not an independent blind.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from holdout_scorer_v2 import (  # noqa: E402
    aggregate_v2,
    build_evidence_for_doc,
    evaluate_doc_v2,
    perfect_document,
)
from run_final_holdout_phase_b_eval import classify_critical, group_metrics  # noqa: E402

SOLL = ROOT / "tests" / "fixtures" / "cv_corpus" / "CV_Parser_Sollwerte_Vollstaendig.txt"
PRED_ROOT = ROOT / "artifacts" / "phi_vs_qwen_cv_extract"
OUT = ROOT / "artifacts" / "one_model_dual_use"
CV_DIR = ROOT / "tests" / "fixtures" / "cv_corpus"


def _parse_sollwerte(text: str) -> dict[str, dict[str, Any]]:
    blocks = re.split(r"\nDATEI:\s*", text)
    out: dict[str, dict[str, Any]] = {}
    for block in blocks[1:]:
        lines = block.strip().splitlines()
        if not lines:
            continue
        fname = lines[0].strip()
        body = "\n".join(lines[1:])
        g: dict[str, Any] = {
            "first_name": "",
            "last_name": "",
            "email": "",
            "phone": "",
            "street": "",
            "house_number": "",
            "postal_code": "",
            "city": "",
            "country": "",
            "dob": "",
            "languages": [],
            "licenses": "",
            "education": [],
            "employment": [],
            "skills": [],
            "software": [],
            "certificates": [],
        }

        def grab(key: str) -> str:
            m = re.search(rf"^{re.escape(key)}:\s*(.+)$", body, re.M)
            if not m:
                return ""
            v = m.group(1).strip()
            return "" if v.upper().startswith("NICHT VORHANDEN") else v

        g["first_name"] = grab("VORNAME")
        g["last_name"] = grab("NACHNAME")
        g["email"] = grab("E-MAIL")
        g["phone"] = grab("TELEFON")
        g["street"] = grab("STRASSE")
        g["house_number"] = grab("HAUSNUMMER")
        g["postal_code"] = grab("PLZ")
        g["city"] = grab("ORT")
        country = grab("LAND")
        g["country"] = country
        g["dob"] = grab("GEBURTSDATUM")

        for m in re.finditer(
            r"^BERUF_\d+:\s*([^\|]+)\|\s*([^\|]+)\|\s*([^|]+?)(?:\||$)",
            body,
            re.M,
        ):
            dates = m.group(1).strip()
            title = m.group(2).strip()
            company = m.group(3).strip().split(",")[0].strip()
            start, end = "", ""
            if " - " in dates:
                start, end = [x.strip() for x in dates.split(" - ", 1)]
            g["employment"].append(
                {
                    "company": company,
                    "position": title,
                    "title": title,
                    "start_date": start,
                    "end_date": end,
                }
            )

        for m in re.finditer(
            r"^AUSBILDUNG_\d+:\s*([^\|]+)\|\s*([^\|]+)\|\s*(.+)$",
            body,
            re.M,
        ):
            dates = m.group(1).strip()
            qual = m.group(2).strip()
            inst = m.group(3).strip()
            start, end = "", ""
            if " - " in dates:
                start, end = [x.strip() for x in dates.split(" - ", 1)]
            g["education"].append(
                {
                    "institution": inst,
                    "qualification": qual,
                    "start_date": start,
                    "end_date": end,
                }
            )

        for m in re.finditer(r"^SPRACHE_\d+:\s*([^|]+)\|\s*([^|]+)", body, re.M):
            g["languages"].append(
                {"language": m.group(1).strip(), "level": m.group(2).strip()}
            )

        lic = []
        for m in re.finditer(r"^FUEHRERSCHEIN_\d+:\s*(.+)$", body, re.M):
            lic.append(m.group(1).strip())
        g["licenses"] = " ".join(lic)

        soft = grab("SOFTWARE")
        if soft:
            g["software"] = [x.strip() for x in soft.split("|") if x.strip()]
        skills = grab("SKILLS")
        if skills:
            g["skills"] = [x.strip() for x in skills.split("|") if x.strip()]
        for m in re.finditer(r"^ZERTIFIKAT_\d+:\s*([^|]+)", body, re.M):
            g["certificates"].append({"name": m.group(1).strip(), "issuer": "", "date": ""})

        # Shape expected by prepare_gt / evaluate — store dual keys
        out[fname] = {
            "name": {"first_name": g["first_name"], "last_name": g["last_name"]},
            "email": g["email"],
            "phone": g["phone"],
            "address": {
                "street": g["street"],
                "house_number": g["house_number"],
                "postal_code": g["postal_code"],
                "city": g["city"],
                "country": g["country"],
            },
            "dob": g["dob"],
            "languages": [[x["language"], x["level"]] for x in g["languages"]],
            "licenses": lic,
            "education": g["education"],
            "employment": g["employment"],
            "skills": g["skills"],
            "software": g["software"],
            "certificates": [c["name"] for c in g["certificates"]],
            "_scorer_flat": g,
            "language": "de" if fname.startswith("DE_") else "en",
        }
    return out


def _pred_to_parsed(raw: dict[str, Any]) -> dict[str, Any]:
    """Map schema-ish prediction JSON to scorer parsed shape."""
    if "work_experience" in raw or "personal" in raw:
        return raw
    # Docpick/Karrierekrake schema from #97
    name = raw.get("name") or {}
    if isinstance(name, str):
        parts = name.split(None, 1)
        name = {"first_name": parts[0] if parts else "", "last_name": parts[1] if len(parts) > 1 else ""}
    addr = raw.get("address") or {}
    langs = []
    for item in raw.get("languages") or []:
        if isinstance(item, (list, tuple)) and item:
            langs.append({"language": item[0], "level": item[1] if len(item) > 1 else ""})
        elif isinstance(item, dict):
            langs.append(item)
        elif isinstance(item, str):
            langs.append({"language": item, "level": ""})
    emp = []
    for e in raw.get("employment") or []:
        if not isinstance(e, dict):
            continue
        emp.append(
            {
                "company": e.get("company") or "",
                "position": e.get("position") or e.get("title") or "",
                "title": e.get("position") or e.get("title") or "",
                "start_date": e.get("start_date") or "",
                "end_date": e.get("end_date") or "",
            }
        )
    edu = []
    for e in raw.get("education") or []:
        if not isinstance(e, dict):
            continue
        edu.append(
            {
                "institution": e.get("institution") or "",
                "qualification": e.get("qualification") or e.get("degree") or "",
                "start_date": e.get("start_date") or "",
                "end_date": e.get("end_date") or "",
            }
        )
    certs = []
    for c in raw.get("certificates") or []:
        if isinstance(c, str):
            certs.append({"name": c, "issuer": "", "date": ""})
        elif isinstance(c, dict):
            certs.append(c)
    lic = raw.get("licenses") or []
    if isinstance(lic, str):
        lic_s = lic
    else:
        lic_s = " ".join(str(x) for x in lic)
    return {
        "personal": {
            "first_name": name.get("first_name") or "",
            "last_name": name.get("last_name") or "",
            "street": addr.get("street") or "",
            "house_number": addr.get("house_number") or "",
            "postal_code": addr.get("postal_code") or "",
            "city": addr.get("city") or "",
            "country": addr.get("country") or "",
            "date_of_birth": raw.get("date_of_birth") or raw.get("dob") or "",
        },
        "emails": [raw["email"]] if raw.get("email") else [],
        "phones": [raw["phone"]] if raw.get("phone") else [],
        "languages": langs,
        "education": edu,
        "work_experience": emp,
        "skills": list(raw.get("skills") or []),
        "software": list(raw.get("software") or []),
        "certificates": certs,
        "driving_license": lic_s,
    }


def score_side(label: str, pred_dir: Path, gt: dict[str, dict[str, Any]]) -> dict[str, Any]:
    from run_final_holdout_phase_b_eval import prepare_gt_for_scorer

    all_rows = []
    per = {}
    by_lang = {"de": [], "en": []}
    for fname, g_raw in gt.items():
        stem = Path(fname).stem
        # predictions named DE_01.json etc.
        short = "_".join(stem.split("_")[:2]) + ".json"
        path = pred_dir / short
        if not path.exists():
            # try full stem
            path = pred_dir / f"{stem}.json"
        if not path.exists():
            per[fname] = {"error": f"missing pred {short}"}
            continue
        raw = json.loads(path.read_text(encoding="utf-8"))
        # strip meta wrappers
        if "suggestion" in raw and isinstance(raw["suggestion"], dict):
            raw = raw["suggestion"]
        pred = _pred_to_parsed(raw)
        g = prepare_gt_for_scorer(g_raw)
        # evidence text from PDF extract if available
        text_path = PRED_ROOT / f"text_{fname}.sha256"
        pdf = CV_DIR / fname
        text = ""
        if pdf.exists():
            try:
                from core.cv_extract import extract_text

                text = extract_text(pdf) or ""
            except Exception:  # noqa: BLE001
                text = ""
        evidence = build_evidence_for_doc(fname, g, text)
        rows = evaluate_doc_v2(fname, g, pred, evidence)
        all_rows.extend(rows)
        lang = g_raw.get("language") or "de"
        by_lang[lang].extend(rows)
        crit = classify_critical(rows)
        errs = [r for r in rows if r.status not in {"correct", "skipped"}]
        per[fname] = {
            "lang": lang,
            "perfect": perfect_document(rows),
            "perfect_core": perfect_document(rows, core_only=True),
            "n_critical": len(crit),
            "critical_kinds": [c.get("kind") for c in crit],
            "n_errors": len(errs),
        }
    invented = [
        c
        for c in classify_critical(all_rows)
        if c["status"] == "hallucinated" and str(c.get("kind") or "").startswith("invented_")
    ]
    # text-ground check for invented
    grounded = 0
    ungrounded = 0
    for c in invented:
        # rough: if we have no text skip
        ungrounded += 1  # filled below if needed
    agg = aggregate_v2(all_rows)
    return {
        "label": label,
        "metrics": {
            **agg,
            "perfect_core": sum(1 for v in per.values() if v.get("perfect_core")),
            "perfect_documents": sum(1 for v in per.values() if v.get("perfect")),
            "invented_critical_flags": len(invented),
            "n_documents": len(per),
            "by_group": group_metrics(all_rows),
        },
        "metrics_de": aggregate_v2(by_lang["de"]) if by_lang["de"] else {},
        "metrics_en": aggregate_v2(by_lang["en"]) if by_lang["en"] else {},
        "per_document": per,
        "note": (
            "Rescored against full Sollwerte GT (employment/education lists). "
            "KNOWN corpus — not blind. Prior count-only invented flags are obsolete here."
        ),
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    gt = _parse_sollwerte(SOLL.read_text(encoding="utf-8"))
    (OUT / "sollwerte_gt_parsed.json").write_text(
        json.dumps(gt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    results = {}
    for label, sub in (("phi", "predictions_phi"), ("qwen", "predictions_qwen")):
        d = PRED_ROOT / sub
        if not d.is_dir():
            results[label] = {"error": f"missing {d}"}
            continue
        print(f"Scoring {label} from {d} ...", flush=True)
        results[label] = score_side(label, d, gt)
        m = results[label]["metrics"]
        print(
            f"  F1={m.get('f1')} DE={results[label]['metrics_de'].get('f1')} "
            f"EN={results[label]['metrics_en'].get('f1')} "
            f"invented_flags={m.get('invented_critical_flags')} "
            f"perfect_core={m.get('perfect_core')}",
            flush=True,
        )
    report = {
        "comparison_type": "KNOWN_DEV_RESCORE_SOLLWERTE_NOT_BLIND",
        "source_predictions": str(PRED_ROOT),
        "ground_truth": str(SOLL),
        "results": results,
        "interpretation": (
            "If invented_critical_flags drop sharply vs #97 (29), those flags were "
            "GT count-only artifacts, not proven model hallucinations."
        ),
    }
    (OUT / "SMOKE_SOLLWERTE_RESCORE.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({k: v.get("metrics") if isinstance(v, dict) else v for k, v in results.items()}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
