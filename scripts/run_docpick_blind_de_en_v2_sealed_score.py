#!/usr/bin/env python3
"""Blind DE/EN v2 (NV3_50) Phase B — verify seal, then score once.

Does NOT re-extract. Does NOT modify parser, prompt, model, scorer, or GT.
Maps SOLUTION_SHEET.json → frozen V3.1 GT schema only via documented,
unambiguous transforms; unclear fields stay unscored / nicht_bewertbar.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from holdout_scorer_v3_1_date_norm import (  # noqa: E402
    METRIC_NAME,
    aggregate_v3_1,
    evaluate_doc_v3_1,
)

OUT = ROOT / "tests" / "docpick_blind_de_en_v2"
SEAL = OUT / "PHASE_A_EXTRACTION_SEAL.json"
FREEZE = OUT / "PARSER_FREEZE.json"
SUPPLIER_PDF_MANIFEST = OUT / "PDF_SHA256_MANIFEST.json"
SOLUTIONS_DIR = OUT / "phase_b_solutions"
SOLUTION_SHEET = SOLUTIONS_DIR / "SOLUTION_SHEET.json"
GT_MAPPED = SOLUTIONS_DIR / "expected_results_full_v3.json"
ADAPTER_NOTES = SOLUTIONS_DIR / "SCHEMA_ADAPTER_NOTES.json"
RESULT = OUT / "PHASE_B_COMPLETE_GT_ONLY_V3_1_RESULTS.json"
DONE = OUT / "PHASE_B_SCORING_DONE.json"

EXPECTED_SEAL_SHA256 = (
    "169624a339d4984e099c5633cdf7b579a654a9695f118a447f37a54bedf89a98"
)
EXPECTED_FREEZE_COMMIT = "801a92475c0f128634a940312e07f266f51539d6"
_STREET_HN = re.compile(r"^(.+?)\s+(\d+[a-zA-Z]?)$")


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_utf8(path: Path, text: str) -> None:
    path.write_bytes(text.encode("utf-8"))


def _pdf_text(path: Path) -> str:
    try:
        import pymupdf

        doc = pymupdf.open(path)
        return "\n".join(page.get_text() for page in doc)
    except Exception:
        try:
            import fitz

            doc = fitz.open(path)
            return "\n".join(page.get_text() for page in doc)
        except Exception:
            return ""


def verify_integrity(seal: dict[str, Any]) -> list[str]:
    """Return list of blocking integrity errors (empty = OK)."""
    errors: list[str] = []
    seal_hash = _sha256_file(SEAL)
    if seal_hash != EXPECTED_SEAL_SHA256:
        errors.append(f"seal SHA256 mismatch: got {seal_hash}")
    freeze = seal.get("parser_freeze") or {}
    if freeze.get("git_commit") != EXPECTED_FREEZE_COMMIT:
        errors.append(
            f"freeze commit {freeze.get('git_commit')} != {EXPECTED_FREEZE_COMMIT}"
        )
    if FREEZE.is_file():
        disk_freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
        if disk_freeze.get("git_commit") != EXPECTED_FREEZE_COMMIT:
            errors.append("PARSER_FREEZE.json commit drift")
        for key, exp in (freeze.get("file_sha256") or {}).items():
            path = ROOT / key
            if not path.is_file():
                errors.append(f"missing freeze file {key}")
                continue
            if _sha256_file(path) != exp:
                errors.append(f"parser/scorer file drift: {key}")
    model_path = Path((freeze.get("llm") or {}).get("model_path") or "")
    exp_model = (freeze.get("llm") or {}).get("model_sha256")
    if model_path.is_file() and exp_model:
        if _sha256_file(model_path) != exp_model:
            errors.append("model SHA256 drift vs freeze")
    if seal.get("n_documents") != 50 or seal.get("n_ok") != 50:
        errors.append(f"seal n_ok/n_documents={seal.get('n_ok')}/{seal.get('n_documents')}")
    if seal.get("gt_not_loaded") is not True:
        errors.append("seal.gt_not_loaded is not true")

    supplier = {
        d["document_id"]: d["sha256"]
        for d in json.loads(SUPPLIER_PDF_MANIFEST.read_text(encoding="utf-8"))[
            "documents"
        ]
    }
    for p in seal["predictions"]:
        pred_path = ROOT / p["prediction_file"]
        if not pred_path.is_file():
            errors.append(f"missing prediction {pred_path}")
            continue
        if _sha256_file(pred_path) != p["sha256"]:
            errors.append(f"prediction hash mismatch {p['id']}")
        pdf_path = ROOT / p["pdf"]
        exp_pdf = p.get("pdf_sha256") or supplier.get(p["id"])
        if not pdf_path.is_file():
            errors.append(f"missing PDF {pdf_path}")
            continue
        if _sha256_file(pdf_path) != exp_pdf:
            errors.append(f"PDF hash mismatch {p['id']}")
    return errors


def _split_name(full: str) -> tuple[str, str] | None:
    parts = [p for p in str(full or "").split() if p]
    if len(parts) == 2:
        return parts[0], parts[1]
    return None


def _split_street(street: str) -> tuple[str, str] | None:
    m = _STREET_HN.match(str(street or "").strip())
    if not m:
        return None
    return m.group(1).strip(), m.group(2).strip()


def map_solution_sheet_to_v3_gt(sheet: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Map supplier SOLUTION_SHEET → frozen COMPLETE_GT_ONLY_V3 schema.

    Unambiguous transforms only (documented). Ambiguous fields omitted so the
    frozen scorer records them as non-evaluable / nicht_bewertbar rather than
    inventing values.
    """
    notes: dict[str, Any] = {
        "adapter": "NV3_SOLUTION_SHEET_TO_V3",
        "scorer": METRIC_NAME,
        "unambiguous_transforms": [
            "document_id → documents[<id>.pdf] key",
            "document_language DE|EN → language de|en",
            "name 'First Last' (exactly 2 tokens) → name.{first_name,last_name}",
            "date_of_birth → dob (alias already supported by scorer)",
            "address.street 'Name N' → street + house_number (trailing house token)",
            "employment.title → position (scorer schema key)",
            "employment.end_date null + metadata date_semantics → 'heute'",
            "employment.start/end YYYY-MM left as-is (V3.1 date_norm equates MM/YYYY)",
            "licences → licenses",
            "languages[{name,level}] → [[name, level]]",
            "certificates string list unchanged",
            "career_note ignored (not a V3 scorer field; not mapped to target_role)",
            "education: only qualification present — institution/dates not invented",
        ],
        "per_document_ambiguities": [],
        "rejected_silent_mappings": [
            "Do not invent education.institution by splitting qualification commas",
            "Do not map career_note → target_role without explicit role label contract",
        ],
    }
    docs_out: dict[str, Any] = {}
    for raw in sheet["documents"]:
        did = raw["document_id"]
        pdf_key = f"{did}.pdf"
        amb: list[str] = []
        name_parts = _split_name(raw.get("name") or "")
        if name_parts is None:
            amb.append(f"name not exactly 2 tokens: {raw.get('name')!r} — name unscored")
            name_obj: dict[str, str] = {}
        else:
            name_obj = {"first_name": name_parts[0], "last_name": name_parts[1]}

        addr_in = raw.get("address") or {}
        street_split = _split_street(addr_in.get("street") or "")
        if street_split is None:
            amb.append(
                f"address.street not Name+HN: {addr_in.get('street')!r} — "
                "street/house_number left incomplete"
            )
            addr_out = {
                "street": addr_in.get("street") or "",
                "postal_code": addr_in.get("postal_code") or "",
                "city": addr_in.get("city") or "",
                "country": addr_in.get("country") or "",
            }
        else:
            addr_out = {
                "street": street_split[0],
                "house_number": street_split[1],
                "postal_code": addr_in.get("postal_code") or "",
                "city": addr_in.get("city") or "",
                "country": addr_in.get("country") or "",
            }

        employment = []
        for e in raw.get("employment") or []:
            if not isinstance(e, dict):
                amb.append("employment entry not a dict — skipped")
                continue
            end = e.get("end_date")
            if end is None:
                end_norm = "heute"  # metadata: null for ongoing
            else:
                end_norm = str(end)
            employment.append(
                {
                    "company": e.get("company") or "",
                    "position": e.get("title") or e.get("position") or "",
                    "start_date": e.get("start_date") or "",
                    "end_date": end_norm,
                }
            )

        education = []
        for e in raw.get("education") or []:
            if not isinstance(e, dict):
                amb.append("education entry not a dict — skipped")
                continue
            # Only fields present in sheet — do not invent institution/dates.
            education.append(
                {
                    "qualification": e.get("qualification") or "",
                }
            )

        languages = []
        for item in raw.get("languages") or []:
            if isinstance(item, dict):
                languages.append(
                    [str(item.get("name") or ""), str(item.get("level") or "")]
                )
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                languages.append([str(item[0]), str(item[1])])
            else:
                amb.append(f"language entry ambiguous: {item!r}")

        lang = str(raw.get("document_language") or "").strip().lower()
        if lang not in {"de", "en"}:
            amb.append(f"document_language unclear: {raw.get('document_language')!r}")

        if "career_note" in raw and raw.get("career_note"):
            # Explicitly not mapped — would be silent target_role invention.
            amb.append("career_note present but not mapped to any scorer field")

        gt_doc = {
            "language": lang if lang in {"de", "en"} else "unknown",
            "name": name_obj,
            "email": raw.get("email") or "",
            "phone": raw.get("phone") or "",
            "dob": raw.get("date_of_birth") or raw.get("dob") or "",
            "address": addr_out,
            "languages": languages,
            "licenses": list(raw.get("licences") or raw.get("licenses") or []),
            "employment": employment,
            "education": education,
            "skills": list(raw.get("skills") or []),
            "software": list(raw.get("software") or []),
            "certificates": list(raw.get("certificates") or []),
            "work_count": len(employment),
            "education_count": len(education),
            "missing": [],
            "document_id": did,
        }
        if not name_obj:
            gt_doc["missing"].extend(["name.first_name", "name.last_name"])
        if "house_number" not in addr_out:
            gt_doc["missing"].append("address.house_number")

        docs_out[pdf_key] = gt_doc
        if amb:
            notes["per_document_ambiguities"].append({"document_id": did, "notes": amb})

    mapped = {
        "id": "DOCPICK_BLIND_DE_EN_V2_NV3_PHASE_B",
        "source_sheet": "SOLUTION_SHEET.json",
        "scorer_target": METRIC_NAME,
        "documents": docs_out,
    }
    return mapped, notes


def main() -> int:
    if RESULT.is_file():
        print(f"REFUSE overwrite of existing {RESULT}", file=sys.stderr)
        return 3
    if not SEAL.is_file():
        print(f"missing seal {SEAL}", file=sys.stderr)
        return 2
    if not SOLUTION_SHEET.is_file():
        print(
            f"missing {SOLUTION_SHEET}\n"
            "Install PHASE_B_SOLUTIONS.zip under phase_b_solutions/ first.",
            file=sys.stderr,
        )
        return 2

    seal = json.loads(SEAL.read_text(encoding="utf-8"))
    integrity = verify_integrity(seal)
    if integrity:
        print("INTEGRITY FAILURE — stop without scoring:", file=sys.stderr)
        for e in integrity:
            print(f"  - {e}", file=sys.stderr)
        return 5

    # Phase B PDF manifest from zip must match Phase A supplier manifest.
    phase_b_pdf_manifest = SOLUTIONS_DIR / "PDF_SHA256_MANIFEST.json"
    if phase_b_pdf_manifest.is_file():
        if _sha256_file(phase_b_pdf_manifest) != _sha256_file(SUPPLIER_PDF_MANIFEST):
            print("Phase B PDF_SHA256_MANIFEST differs from Phase A — stop", file=sys.stderr)
            return 5

    sheet = json.loads(SOLUTION_SHEET.read_text(encoding="utf-8"))
    if len(sheet.get("documents") or []) != 50:
        print(f"SOLUTION_SHEET has {len(sheet.get('documents') or [])} docs, need 50", file=sys.stderr)
        return 2

    mapped, adapter_notes = map_solution_sheet_to_v3_gt(sheet)
    sheet_ids = {d["document_id"] for d in sheet["documents"]}
    seal_ids = {p["id"] for p in seal["predictions"]}
    if sheet_ids != seal_ids:
        print(
            f"document id set mismatch sheet={sorted(sheet_ids - seal_ids)} "
            f"seal={sorted(seal_ids - sheet_ids)}",
            file=sys.stderr,
        )
        return 5

    _write_utf8(GT_MAPPED, json.dumps(mapped, indent=2, ensure_ascii=False) + "\n")
    _write_utf8(ADAPTER_NOTES, json.dumps(adapter_notes, indent=2, ensure_ascii=False) + "\n")

    gt_docs = mapped["documents"]
    # Attach lang from GT onto seal prediction metadata for DE/EN split.
    lang_by_id = {
        Path(k).stem: (v.get("language") or "unknown") for k, v in gt_docs.items()
    }

    doc_results = []
    errors = []
    for p in seal["predictions"]:
        pred = json.loads((ROOT / p["prediction_file"]).read_text(encoding="utf-8"))
        pdf_name = Path(p["pdf"]).name
        gt = gt_docs[pdf_name]
        text = _pdf_text(ROOT / p["pdf"])
        dr = evaluate_doc_v3_1(p["id"], gt, pred, text)
        lang = lang_by_id.get(p["id"], p.get("lang") or "unknown")
        dr["lang"] = lang
        doc_results.append(dr)
        for r in dr["scored_rows"]:
            if r.status in {"wrong", "missing", "hallucinated", "wrong_category"}:
                errors.append(
                    {
                        "document": p["id"],
                        "lang": lang,
                        "field": r.field,
                        "group": r.group,
                        "status": r.status,
                        "expected": r.expected,
                        "actual": r.actual,
                    }
                )

    agg_wrap = aggregate_v3_1(doc_results)
    agg = dict(agg_wrap.get("complete_gt_scored") or {})
    nicht = agg_wrap.get("nicht_bewertbar") or {}

    perfect = sum(
        1
        for d in doc_results
        if d["scored_rows"] and all(r.status == "correct" for r in d["scored_rows"])
    )
    perfect_core = f"{perfect}/{len(doc_results)}"

    def lang_metrics(lang: str) -> dict[str, Any] | None:
        docs = [d for d in doc_results if d.get("lang") == lang]
        if not docs:
            return None
        from holdout_scorer_v3_complete_gt import aggregate_v3

        a = aggregate_v3(
            [
                {
                    "document": d["document"],
                    "scored_rows": d["scored_rows"],
                    "nicht_bewertbar": d["nicht_bewertbar"],
                }
                for d in docs
            ]
        )
        scored = a.get("complete_gt_scored") or a
        return {
            "n_documents": len(docs),
            "f1": scored.get("f1"),
            "precision": scored.get("precision"),
            "recall": scored.get("recall"),
            "field_total": scored.get("field_total"),
            "counts": scored.get("counts"),
            "nicht_bewertbar_n": (a.get("nicht_bewertbar") or {}).get("n_fields"),
        }

    by_group: dict[str, Counter] = defaultdict(Counter)
    for e in errors:
        by_group[e["group"]][e["status"]] += 1

    f1 = float(agg.get("f1") or 0.0)
    claim_99 = bool(
        f1 >= 0.99
        and (lang_metrics("de") or {}).get("f1", 0) >= 0.99
        and (lang_metrics("en") or {}).get("f1", 0) >= 0.99
    )

    out = {
        "test_type": "INDEPENDENT_BLIND_DE_EN_NV3_50",
        "metric_name": METRIC_NAME,
        "disclaimer": (
            "Independent synthetic Blind NV3 (n=50). Phase A sealed predictions only. "
            "Not Round regression. Schema adapter documented in SCHEMA_ADAPTER_NOTES.json. "
            "This block is the Blindresultat; any later parser work is Post-Analysis only."
        ),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "integrity": {
            "seal_sha256_verified": EXPECTED_SEAL_SHA256,
            "prediction_hashes_verified": True,
            "pdf_hashes_verified": True,
            "parser_freeze_commit": EXPECTED_FREEZE_COMMIT,
            "parser_scorer_files_match_freeze": True,
            "re_extraction": False,
            "parser_changed": False,
            "scorer_changed": False,
            "gt_changed": False,
        },
        "schema_adapter_notes_file": str(ADAPTER_NOTES.relative_to(ROOT)),
        "n_documents": len(doc_results),
        "performance_from_seal": seal.get("performance"),
        "coverage": {
            "perfect_core_on_scored_fields": perfect_core,
            "n_scored_fields_total": agg.get("field_total"),
        },
        "metrics_complete_gt_only_v3_1": {
            **agg,
            "perfect_core": perfect_core,
            "precision": agg.get("precision"),
            "recall": agg.get("recall"),
        },
        "nicht_bewertbar": nicht,
        "by_lang": {"de": lang_metrics("de"), "en": lang_metrics("en")},
        "errors_by_field_group": {g: dict(c) for g, c in sorted(by_group.items())},
        "real_errors": errors,
        "error_status_counts": dict(Counter(e["status"] for e in errors)),
        "claim_99_percent": claim_99,
        "claim_99_reason": (
            "Blind F1>=0.99 and DE-F1>=0.99 and EN-F1>=0.99 on COMPLETE_GT_ONLY_V3_1"
            if claim_99
            else "Threshold not met and/or incomplete evaluable coverage — see metrics."
        ),
        "post_analysis_forbidden_until_new_corpus": True,
    }
    _write_utf8(RESULT, json.dumps(out, indent=2, ensure_ascii=False, default=str) + "\n")
    _write_utf8(
        DONE,
        json.dumps(
            {
                "scored_at": datetime.now(timezone.utc).isoformat(),
                "result_file": str(RESULT.relative_to(ROOT)),
                "result_sha256": _sha256_file(RESULT),
                "n_ok_scored": len(doc_results),
            },
            indent=2,
        )
        + "\n",
    )
    print(
        json.dumps(
            {
                "ok": True,
                "f1": agg.get("f1"),
                "precision": agg.get("precision"),
                "recall": agg.get("recall"),
                "perfect_core": perfect_core,
                "de": out["by_lang"]["de"],
                "en": out["by_lang"]["en"],
                "counts": agg.get("counts"),
                "nicht_bewertbar_n": nicht.get("n_fields"),
                "errors_by_group": out["errors_by_field_group"],
                "claim_99": claim_99,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
