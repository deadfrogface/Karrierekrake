#!/usr/bin/env python3
"""Offline Docpick + Qwen3.5-4B CV extract vs DET (Scorer V2).

Outside productive path. Docling PDF text + Docpick schema LLM (local llama.cpp).
qwen3vl-resume-parser skipped (8B VL ~17GB — not realistic on 15 GiB / no CUDA).

Usage:
  # Requires llama.cpp OpenAI server on DOCPICK_LLM_BASE (default :8765)
  python scripts/run_docpick_qwen35_compare.py
"""

from __future__ import annotations

import hashlib
import json
import resource
import sys
import time
import traceback
from collections import Counter
from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from holdout_scorer_v2 import (  # noqa: E402
    FactResult,
    aggregate_v2,
    build_evidence_for_doc,
    evaluate_doc_v2,
    perfect_document,
)
from run_final_holdout_phase_b_eval import (  # noqa: E402
    classify_critical,
    group_metrics,
    prepare_gt_for_scorer,
)

MANIFEST = ROOT / "tests" / "oss_cv_replace" / "SAMPLE_MANIFEST_LOCKED.json"
OUT = ROOT / "artifacts" / "docpick_qwen35_compare"
MODEL_ID = str(Path(os.sep) / "tmp" / "karrierekrake-models" / "qwen3.5-4b" / "Qwen3.5-4B-Q4_K_M.gguf")
LLM_BASE = "http://127.0.0.1:8765/v1"


# --- Karrierekrake full import schema (Docpick Pydantic) ---------------------


class NameModel(BaseModel):
    first_name: str | None = None
    last_name: str | None = None


class AddressModel(BaseModel):
    street: str | None = None
    house_number: str | None = None
    postal_code: str | None = None
    city: str | None = None
    country: str | None = None


class LanguageEntry(BaseModel):
    language: str | None = None
    level: str | None = None


class EmploymentEntry(BaseModel):
    company: str | None = None
    position: str | None = None
    start_date: str | None = None
    end_date: str | None = None


class EducationEntry(BaseModel):
    institution: str | None = None
    qualification: str | None = None
    start_date: str | None = None
    end_date: str | None = None


class KarrierekrakeCVSchema(BaseModel):
    """Full productive CV-import field set for Docpick extraction.

    Keep in sync with ``core.cv_docpick_import.KarrierekrakeCVSchema``:
    list fields before employment/education; DE/EN section descriptions.
    """

    name: NameModel | None = None
    email: str | None = None
    phone: str | None = None
    date_of_birth: str | None = None
    address: AddressModel | None = None
    languages: list[LanguageEntry] = Field(default_factory=list)
    licenses: list[str] = Field(
        default_factory=list,
        description="Driving licence classes only (e.g. B, BE, C1), not CEFR language levels.",
    )
    skills: list[str] = Field(
        default_factory=list,
        description=(
            "Competencies from sections named Skills, Key Skills, Kenntnisse, "
            "or similar. Do not put software tool names here."
        ),
    )
    software: list[str] = Field(
        default_factory=list,
        description=(
            "Software, systems, and tools from sections named Software, Systems, "
            "Tools, IT-Kenntnisse, or similar (e.g. Microsoft 365, SAP, Excel)."
        ),
    )
    certificates: list[str] = Field(
        default_factory=list,
        description=(
            "Certificate and short-course titles from sections named Certificates, "
            "Certifications, Training, Weiterbildung(en), Weiterbildungen, "
            "or non-degree items under Education & Training. Extract each course "
            "or certificate name as a string (year optional, not required). "
            "Do not leave this array empty when such items appear in the text."
        ),
    )
    employment: list[EmploymentEntry] = Field(default_factory=list)
    education: list[EducationEntry] = Field(
        default_factory=list,
        description=(
            "Formal education / degrees only (school, university, apprenticeship). "
            "Short trainings and certificates belong in certificates, not here."
        ),
    )


def _peak_rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def _git() -> str:
    import subprocess

    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except Exception:  # noqa: BLE001
        return ""


_docling = None


def extract_text_docling(path: Path) -> str:
    global _docling
    from docling.document_converter import DocumentConverter

    if _docling is None:
        _docling = DocumentConverter()
    return _docling.convert(str(path)).document.export_to_markdown() or ""


def normalize_license_token(s: str) -> str:
    t = (s or "").strip()
    for prefix in ("klasse ", "class ", "führerschein ", "driving licence ", "driving license "):
        if t.lower().startswith(prefix):
            t = t[len(prefix) :].strip()
    return t


def suggestion_to_parsed(data: dict[str, Any], *, apply_license_norm: bool = False) -> dict[str, Any]:
    name = data.get("name") or {}
    if not isinstance(name, dict):
        name = {}
    addr = data.get("address") or {}
    if not isinstance(addr, dict):
        addr = {}
    langs = []
    for item in data.get("languages") or []:
        if isinstance(item, dict):
            langs.append(
                {
                    "language": str(item.get("language") or ""),
                    "level": str(item.get("level") or ""),
                }
            )
    work = []
    for e in data.get("employment") or []:
        if not isinstance(e, dict):
            continue
        work.append(
            {
                "title": str(e.get("position") or e.get("title") or ""),
                "company": str(e.get("company") or ""),
                "start_date": str(e.get("start_date") or ""),
                "end_date": str(e.get("end_date") or ""),
                "responsibilities": [],
            }
        )
    edu = []
    for e in data.get("education") or []:
        if not isinstance(e, dict):
            continue
        edu.append(
            {
                "institution": str(e.get("institution") or ""),
                "qualification": str(e.get("qualification") or ""),
                "start_date": str(e.get("start_date") or ""),
                "end_date": str(e.get("end_date") or ""),
            }
        )
    lic_list = []
    for x in data.get("licenses") or []:
        tok = str(x)
        if apply_license_norm:
            tok = normalize_license_token(tok)
        lic_list.append(tok)
    certs = []
    for c in data.get("certificates") or []:
        if isinstance(c, dict):
            certs.append(c)
        else:
            certs.append({"name": str(c), "issuer": "", "year": ""})
    return {
        "personal": {
            "first_name": str(name.get("first_name") or ""),
            "last_name": str(name.get("last_name") or ""),
            "street": str(addr.get("street") or ""),
            "house_number": str(addr.get("house_number") or ""),
            "postal_code": str(addr.get("postal_code") or ""),
            "city": str(addr.get("city") or ""),
            "country": str(addr.get("country") or ""),
            "date_of_birth": str(data.get("date_of_birth") or ""),
        },
        "emails": [data["email"]] if data.get("email") else [],
        "phones": [data["phone"]] if data.get("phone") else [],
        "languages": langs,
        "driving_license": " ".join(lic_list),
        "education": edu,
        "work_experience": work,
        "skills": [str(x) for x in (data.get("skills") or [])],
        "software": [str(x) for x in (data.get("software") or [])],
        "certificates": certs,
        "pipeline": "DOCPICK_QWEN35_4B",
        "phi_invoked": False,
    }


def run_det(path: Path) -> dict[str, Any]:
    from core.cv_parser import import_cv

    parsed = import_cv(path, guenther_enabled=False)
    parsed["pipeline"] = "DET_PRODUCT"
    return parsed


def run_docpick(path: Path, text: str, provider, *, apply_license_norm: bool = False) -> dict[str, Any]:
    data = provider.extract_fields(text, KarrierekrakeCVSchema)
    if not isinstance(data, dict):
        data = {}
    parsed = suggestion_to_parsed(data, apply_license_norm=apply_license_norm)
    parsed["_raw"] = data
    return parsed


def _score_side(
    *,
    label: str,
    docs_meta: list[dict[str, Any]],
    gt_docs: dict[str, Any],
    predictions: dict[str, dict[str, Any]],
    texts: dict[str, str],
    timings: dict[str, float],
) -> dict[str, Any]:
    all_rows: list[FactResult] = []
    per_doc: dict[str, Any] = {}
    critical_all: list[dict[str, Any]] = []
    error_inventory: list[dict[str, Any]] = []
    by_lang_rows: dict[str, list[FactResult]] = {"de": [], "en": []}

    for meta in docs_meta:
        fname = Path(meta["path"]).name
        lang = meta["lang"]
        g = prepare_gt_for_scorer(gt_docs[fname])
        text = texts[fname]
        pred = predictions[fname]
        evidence = build_evidence_for_doc(fname, g, text)
        rows = evaluate_doc_v2(fname, g, pred, evidence)
        all_rows.extend(rows)
        by_lang_rows[lang].extend(rows)
        crit = classify_critical(rows)
        critical_all.extend(crit)
        errs = [r for r in rows if r.status not in {"correct", "skipped"}]
        per_doc[fname] = {
            "lang": lang,
            "perfect": perfect_document(rows),
            "perfect_core": perfect_document(rows, core_only=True),
            "n_errors": len(errs),
            "n_critical": len(crit),
            "elapsed_s": timings.get(fname, 0.0),
            "missing_fields": [r.field for r in errs if r.status == "missing"],
            "error_fields": [
                {"field": r.field, "group": r.group, "status": r.status}
                for r in errs[:40]
            ],
        }
        for r in errs:
            error_inventory.append(
                {
                    "document": fname,
                    "lang": lang,
                    "field": r.field,
                    "group": r.group,
                    "status": r.status,
                    "expected": r.expected,
                    "actual": r.actual,
                }
            )

    invented = [
        c
        for c in critical_all
        if c["status"] == "hallucinated"
        and str(c.get("kind") or "").startswith("invented_")
    ]

    def pack(rows: list[FactResult], doc_filter: set[str] | None = None) -> dict[str, Any]:
        use = rows if doc_filter is None else [r for r in rows if r.document in doc_filter]
        agg = (
            aggregate_v2(use)
            if use
            else {
                "precision": 0.0,
                "recall": 0.0,
                "f1": 0.0,
                "hallucination_rate": 0.0,
                "field_accuracy": 0.0,
            }
        )
        docs = (
            per_doc
            if doc_filter is None
            else {k: v for k, v in per_doc.items() if k in doc_filter}
        )
        return {
            **agg,
            "perfect_documents": sum(1 for v in docs.values() if v["perfect"]),
            "perfect_core": sum(1 for v in docs.values() if v["perfect_core"]),
            "invented_critical": len(
                [c for c in invented if doc_filter is None or c["document"] in doc_filter]
            ),
            "n_documents": len(docs),
            "avg_s_per_cv": (
                sum(v["elapsed_s"] for v in docs.values()) / len(docs) if docs else 0.0
            ),
            "by_group": group_metrics(use) if use else {},
        }

    de_docs = {Path(m["path"]).name for m in docs_meta if m["lang"] == "de"}
    en_docs = {Path(m["path"]).name for m in docs_meta if m["lang"] == "en"}
    return {
        "label": label,
        "metrics_all": pack(all_rows),
        "metrics_de": pack(by_lang_rows["de"], de_docs),
        "metrics_en": pack(by_lang_rows["en"], en_docs),
        "per_document": per_doc,
        "error_inventory": error_inventory,
        "critical_kinds": dict(Counter(c["kind"] for c in invented)),
    }


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--license-norm",
        action="store_true",
        help="One allowed technical correction: strip Klasse/Class prefixes on licences",
    )
    args = ap.parse_args()

    if not MANIFEST.is_file():
        print(f"missing {MANIFEST}", file=sys.stderr)
        return 2
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest.get("locked") is True
    docs_meta = list(manifest["documents"])
    gt_path = ROOT / manifest["ground_truth"]
    gt_docs = json.loads(gt_path.read_text(encoding="utf-8"))["documents"]
    scorer_sha = hashlib.sha256(
        (ROOT / "scripts" / "holdout_scorer_v2.py").read_bytes()
    ).hexdigest()

    from docpick.llm.vllm_provider import VLLMProvider

    provider = VLLMProvider(
        base_url=LLM_BASE,
        model=MODEL_ID,
        temperature=0.0,
        max_tokens=2048,
        timeout=300,
    )
    if not provider.is_available():
        print(f"LLM server not available at {LLM_BASE}", file=sys.stderr)
        return 3

    OUT.mkdir(parents=True, exist_ok=True)
    pred_det = OUT / "predictions_det"
    pred_cand = OUT / "predictions_docpick"
    pred_det.mkdir(exist_ok=True)
    pred_cand.mkdir(exist_ok=True)

    from core.cv_extract import extract_text as extract_current

    texts_det: dict[str, str] = {}
    texts_cand: dict[str, str] = {}
    paths: dict[str, Path] = {}
    for meta in docs_meta:
        pdf = ROOT / meta["path"]
        fname = pdf.name
        paths[fname] = pdf
        texts_det[fname] = extract_current(pdf) or ""
        try:
            texts_cand[fname] = extract_text_docling(pdf)
        except Exception as exc:  # noqa: BLE001
            print(f"Docling fail {fname}: {exc}", file=sys.stderr)
            texts_cand[fname] = texts_det[fname]

    # DET
    det_preds: dict[str, dict[str, Any]] = {}
    det_timings: dict[str, float] = {}
    t0 = time.perf_counter()
    for meta in docs_meta:
        fname = Path(meta["path"]).name
        s = time.perf_counter()
        try:
            det_preds[fname] = run_det(paths[fname])
        except Exception as exc:  # noqa: BLE001
            det_preds[fname] = {"pipeline": "DET_PRODUCT", "tech_error": str(exc)}
        det_timings[fname] = time.perf_counter() - s
        (pred_det / f"{meta['id']}.json").write_text(
            json.dumps(det_preds[fname], ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
    det_wall = time.perf_counter() - t0
    det_peak = _peak_rss_mb()

    # Docpick candidate
    cand_preds: dict[str, dict[str, Any]] = {}
    cand_timings: dict[str, float] = {}
    tech_fix_used = 1 if args.license_norm else 0
    t0 = time.perf_counter()
    for meta in docs_meta:
        fname = Path(meta["path"]).name
        s = time.perf_counter()
        try:
            cand_preds[fname] = run_docpick(
                paths[fname],
                texts_cand[fname],
                provider,
                apply_license_norm=args.license_norm,
            )
        except Exception as exc:  # noqa: BLE001
            # at most one technical retry without schema change
            if tech_fix_used < 1:
                tech_fix_used += 1
                try:
                    cand_preds[fname] = run_docpick(
                        paths[fname],
                        texts_cand[fname],
                        provider,
                        apply_license_norm=args.license_norm,
                    )
                    cand_preds[fname]["_technical_retry"] = str(exc)
                except Exception as exc2:  # noqa: BLE001
                    cand_preds[fname] = {
                        "pipeline": "DOCPICK_QWEN35_4B",
                        "tech_error": str(exc2),
                        "prior": str(exc),
                        "traceback": traceback.format_exc(),
                    }
            else:
                cand_preds[fname] = {
                    "pipeline": "DOCPICK_QWEN35_4B",
                    "tech_error": str(exc),
                    "traceback": traceback.format_exc(),
                }
        cand_timings[fname] = time.perf_counter() - s
        (pred_cand / f"{meta['id']}.json").write_text(
            json.dumps(cand_preds[fname], ensure_ascii=False, indent=2, default=str)
            + "\n",
            encoding="utf-8",
        )
        print(f"CAND {meta['id']} {cand_timings[fname]:.1f}s", flush=True)
    cand_wall = time.perf_counter() - t0
    cand_peak = _peak_rss_mb()

    det_score = _score_side(
        label="DET",
        docs_meta=docs_meta,
        gt_docs=gt_docs,
        predictions=det_preds,
        texts=texts_det,
        timings=det_timings,
    )
    cand_score = _score_side(
        label="DOCPICK_QWEN35",
        docs_meta=docs_meta,
        gt_docs=gt_docs,
        predictions=cand_preds,
        texts=texts_cand,
        timings=cand_timings,
    )

    from core.cv_docpick_import import (
        CV_IMPORT_PEAK_RSS_BYTES_MAX,
        CV_IMPORT_PEAK_RSS_MB_MAX,
    )

    gate = {
        "min_f1": 0.90,
        "max_hallucination_rate": 0.03,
        "max_invented_employment_education": 0,
        "min_processing_success": 10,
        # Hard fail above 3_300_000_000 bytes — Job Object on i3 / 8 GB Win.
        # Soft ≤12000 MB is obsolete. Agent-VM ≠ ship evidence. No Phi fallback.
        "max_peak_rss_bytes": CV_IMPORT_PEAK_RSS_BYTES_MAX,
        "max_peak_rss_mb": CV_IMPORT_PEAK_RSS_MB_MAX,
        "max_peak_rss_gb": CV_IMPORT_PEAK_RSS_BYTES_MAX / 1e9,
        "max_avg_s_per_cv": 120,
        "max_avg_s_note": "Assumption — no product CV-import latency SLA",
        "peak_rss_note": (
            "Hard Peak ≤ 3_300_000_000 bytes (Windows Job Object process group). "
            "RETIRED_NOT_A_PASS: former soft 12 GB ceiling is not a pass. Agent-VM numbers are not ship evidence."
        ),
    }
    m = cand_score["metrics_all"]
    n_ok = sum(1 for p in cand_preds.values() if not p.get("tech_error"))
    gate_pass = (
        float(m["f1"]) >= gate["min_f1"]
        and float(m["hallucination_rate"]) <= gate["max_hallucination_rate"]
        and int(m["invented_critical"]) <= gate["max_invented_employment_education"]
        and n_ok >= gate["min_processing_success"]
        and cand_peak <= gate["max_peak_rss_mb"]
        and float(m["avg_s_per_cv"]) <= gate["max_avg_s_per_cv"]
    )
    status = (
        "GATE_PASSED — freeze & request blind DE/EN set"
        if gate_pass
        else "DET-Ersatz noch nicht erreicht."
    )

    result = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "commit": _git(),
        "manifest_id": manifest.get("manifest_id"),
        "architecture": "Docling text + Docpick VLLMProvider schema extract + Qwen3.5-4B-Q4_K_M (llama.cpp)",
        "model": {
            "id": "Qwen/Qwen3.5-4B",
            "artifact": MODEL_ID,
            "quant": "Q4_K_M",
            "license": "Apache-2.0",
        },
        "skipped_countercandidate": {
            "id": "sukhrobnurali/qwen3vl-resume-parser",
            "reason": "Qwen3-VL-8B ~8.8B BF16 (~17GB weights); host 15 GiB RAM, no CUDA — not realistic",
        },
        "scorer_sha256": scorer_sha,
        "tech_fix_used": tech_fix_used,
        "license_norm": bool(args.license_norm),
        "test_status": "known_fixtures_not_blind",
        "disclaimer": (
            "Known SMOKE_DE_EN_10 fixtures — not an independent blind test. "
            "Do not claim 0.99. IH2 frozen DET F1 0.7246 is separate context."
        ),
        "gate": gate,
        "gate_passed": gate_pass,
        "status": status,
        "productive_det_unchanged": True,
        "performance": {
            "det": {
                "wall_s": det_wall,
                "avg_s_per_cv": det_score["metrics_all"]["avg_s_per_cv"],
                "peak_rss_mb": det_peak,
            },
            "docpick_qwen35": {
                "wall_s": cand_wall,
                "avg_s_per_cv": cand_score["metrics_all"]["avg_s_per_cv"],
                "peak_rss_mb": cand_peak,
            },
        },
        "det": det_score,
        "docpick_qwen35": cand_score,
        "processing_success": f"{n_ok}/{len(docs_meta)}",
    }
    out_json = OUT / "COMPARE_RESULTS.json"
    out_json.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )

    def line(tag: str, mm: dict[str, Any], peak: float) -> None:
        print(
            f"{tag}: P={mm['precision']:.4f} R={mm['recall']:.4f} F1={mm['f1']:.4f} "
            f"hallu={mm['hallucination_rate']:.4f} perfect_core={mm['perfect_core']}/{mm['n_documents']} "
            f"invented={mm['invented_critical']} avg_s={mm['avg_s_per_cv']:.1f} peak_mb={peak:.0f}"
        )

    print(f"gate_passed={gate_pass} license_norm={args.license_norm}")
    line("DET_ALL", det_score["metrics_all"], det_peak)
    line("DOC_ALL", cand_score["metrics_all"], cand_peak)
    line("DET_DE ", det_score["metrics_de"], det_peak)
    line("DOC_DE ", cand_score["metrics_de"], cand_peak)
    line("DET_EN ", det_score["metrics_en"], det_peak)
    line("DOC_EN ", cand_score["metrics_en"], cand_peak)
    print(status)
    print(f"wrote {out_json}")
    return 0 if gate_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
