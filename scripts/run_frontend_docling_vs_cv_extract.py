#!/usr/bin/env python3
"""Frontend ablation: Docling vs shipped cv_extract on the same CVs.

Text metrics always. Optional LLM impact (--run-llm) for Phi and Qwen on
both frontend texts with identical Docpick schema prompts. Caches by
(model, frontend, text_sha256).

KNOWN development corpus — not an independent blind.
Docling metrics ≠ product solution (Docling not shippable in Windows EXE).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import resource
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from rescore_phi_qwen_smoke_sollwerte import (  # noqa: E402
    _parse_sollwerte,
    _pred_to_parsed,
)

CORPUS = ROOT / "tests" / "fixtures" / "cv_corpus"
SOLL = CORPUS / "CV_Parser_Sollwerte_Vollstaendig.txt"
OUT = ROOT / "artifacts" / "one_model_dual_use" / "frontend_ablation"
CACHE = OUT / "llm_cache"

MODELS = {
    "qwen": {
        "id": "qwen3.5-4b",
        "path": Path("/tmp/karrierekrake-models/qwen3.5-4b/Qwen3.5-4B-Q4_K_M.gguf"),
    },
    "phi": {
        "id": "phi4-mini",
        "path": Path(
            "/tmp/karrierekrake-models/phi4-mini/microsoft_Phi-4-mini-instruct-Q4_K_M.gguf"
        ),
    },
}

PDFS = sorted(
    p.name
    for p in CORPUS.glob("*.pdf")
    if p.name.startswith(("DE_", "EN_")) and "Blindtest" not in p.name
)


def _rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _token_set(text: str) -> set[str]:
    return {t for t in re.findall(r"[A-Za-zÄÖÜäöüß0-9@.+-]{2,}", text.lower())}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _gt_tokens(gt: dict[str, Any]) -> set[str]:
    parts: list[str] = []
    for k in (
        "first_name",
        "last_name",
        "email",
        "phone",
        "street",
        "house_number",
        "postal_code",
        "city",
        "country",
        "dob",
        "licenses",
    ):
        v = gt.get(k) or ""
        if v:
            parts.append(str(v))
    for lang in gt.get("languages") or []:
        if isinstance(lang, dict):
            parts.extend([str(lang.get("language") or ""), str(lang.get("level") or "")])
        else:
            parts.append(str(lang))
    for row in (gt.get("education") or []) + (gt.get("employment") or []):
        if isinstance(row, dict):
            parts.extend(str(x) for x in row.values() if x)
    for s in (gt.get("skills") or []) + (gt.get("software") or []) + (
        gt.get("certificates") or []
    ):
        if isinstance(s, dict):
            parts.append(str(s.get("name") or s))
        else:
            parts.append(str(s))
    return _token_set(" ".join(parts))


def extract_texts() -> dict[str, dict[str, Any]]:
    from core.cv_document_backends import extract_current, extract_docling

    rows: dict[str, dict[str, Any]] = {}
    for fname in PDFS:
        path = CORPUS / fname
        row: dict[str, Any] = {"file": fname, "lang": "de" if fname.startswith("DE_") else "en"}
        for name, fn in (("cv_extract", extract_current), ("docling", extract_docling)):
            t0 = time.perf_counter()
            err = None
            text = ""
            try:
                text = fn(path) or ""
            except Exception as exc:  # noqa: BLE001
                err = f"{type(exc).__name__}: {exc}"
            row[name] = {
                "chars": len(text),
                "sha256": _sha(text) if text else "",
                "elapsed_s": round(time.perf_counter() - t0, 3),
                "error": err,
                "text": text,
            }
        a = _token_set(row["cv_extract"]["text"])
        b = _token_set(row["docling"]["text"])
        row["token_jaccard"] = round(_jaccard(a, b), 4)
        row["char_ratio_cv_over_docling"] = (
            round(row["cv_extract"]["chars"] / row["docling"]["chars"], 4)
            if row["docling"]["chars"]
            else None
        )
        only_cv = sorted(a - b)[:40]
        only_doc = sorted(b - a)[:40]
        row["tokens_only_in_cv_extract_sample"] = only_cv
        row["tokens_only_in_docling_sample"] = only_doc
        rows[fname] = row
    return rows


def attach_gt_coverage(rows: dict[str, dict[str, Any]], soll: dict[str, dict]) -> None:
    for fname, row in rows.items():
        g_raw = soll.get(fname)
        if not g_raw:
            row["gt_coverage"] = None
            continue
        gt = g_raw.get("_scorer_flat") or g_raw
        need = _gt_tokens(gt)
        cov = {}
        for fe in ("cv_extract", "docling"):
            have = _token_set(row[fe]["text"])
            missing = sorted(need - have)
            cov[fe] = {
                "gt_tokens": len(need),
                "present": len(need & have),
                "missing_count": len(missing),
                "missing_sample": missing[:25],
                "coverage": round(len(need & have) / len(need), 4) if need else 1.0,
            }
        row["gt_coverage"] = cov


_LLM: dict[str, Any] = {}


def _get_llm(model_key: str):
    if model_key in _LLM:
        return _LLM[model_key]
    from llama_cpp import Llama

    meta = MODELS[model_key]
    path = meta["path"]
    if not path.is_file():
        raise FileNotFoundError(str(path))
    llm = Llama(
        model_path=str(path),
        n_ctx=8192,
        n_threads=max(1, (os.cpu_count() or 2) // 2),
        verbose=False,
    )
    _LLM[model_key] = llm
    return llm


def _llm_json(model_key: str, text: str) -> dict[str, Any]:
    from core.cv_docpick_import import _extraction_messages
    from docpick.llm.prompt import parse_llm_json

    llm = _get_llm(model_key)
    messages = _extraction_messages(text)
    # Cap document text for context; keep schema intact.
    user = messages[1]["content"]
    if len(user) > 12000:
        # Keep schema header; trim document body.
        head, _, rest = user.partition("## Document Text\n")
        body, _, tail = rest.rpartition("\n\nExtract the data")
        body = body[:9000]
        messages[1]["content"] = f"{head}## Document Text\n{body}\n\nExtract the data{tail}"
    t0 = time.perf_counter()
    rss0 = _rss_mb()
    out = llm.create_chat_completion(
        messages=messages,
        temperature=0.0,
        max_tokens=2048,
    )
    raw = out["choices"][0]["message"]["content"] or ""
    try:
        data = parse_llm_json(raw)
    except Exception:  # noqa: BLE001
        data = {}
    return {
        "raw": raw,
        "data": data if isinstance(data, dict) else {},
        "elapsed_s": round(time.perf_counter() - t0, 3),
        "peak_rss_mb": round(max(rss0, _rss_mb()), 1),
        "hardware_note": "Agent-VM measurement — not i3/8GB Job Object",
    }


def run_llm_impact(
    rows: dict[str, dict[str, Any]],
    soll: dict[str, dict],
    *,
    models: list[str],
) -> dict[str, Any]:
    from holdout_scorer_v2 import (
        aggregate_v2,
        build_evidence_for_doc,
        evaluate_doc_v2,
        perfect_document,
    )
    from run_final_holdout_phase_b_eval import (
        classify_critical,
        group_metrics,
        prepare_gt_for_scorer,
    )

    CACHE.mkdir(parents=True, exist_ok=True)
    results: dict[str, Any] = {}
    for model_key in models:
        per_fe_rows: dict[str, list] = {"cv_extract": [], "docling": []}
        docs_out: list[dict[str, Any]] = []
        for fname, row in rows.items():
            g_raw = soll.get(fname)
            if not g_raw:
                continue
            g = prepare_gt_for_scorer(g_raw.get("_scorer_flat") or g_raw)
            doc_entry: dict[str, Any] = {"file": fname, "lang": row["lang"]}
            for fe in ("cv_extract", "docling"):
                text = row[fe]["text"]
                if not text.strip():
                    doc_entry[fe] = {"error": "empty_text"}
                    continue
                text_sha = row[fe]["sha256"]
                cache_path = CACHE / f"{model_key}__{fe}__{text_sha[:16]}.json"
                if cache_path.is_file():
                    payload = json.loads(cache_path.read_text(encoding="utf-8"))
                    reused = True
                else:
                    payload = _llm_json(model_key, text)
                    payload["model"] = MODELS[model_key]["id"]
                    payload["frontend"] = fe
                    payload["text_sha256"] = text_sha
                    payload["file"] = fname
                    cache_path.write_text(
                        json.dumps(payload, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    reused = False
                pred = _pred_to_parsed(payload.get("data") or {})
                evidence = build_evidence_for_doc(fname, g, text)
                rows_v2 = evaluate_doc_v2(fname, g, pred, evidence)
                crit = classify_critical(rows_v2)
                agg = aggregate_v2(rows_v2)
                entry = {
                    "file": fname,
                    "frontend": fe,
                    "reused_cache": reused,
                    "elapsed_s": payload.get("elapsed_s"),
                    "peak_rss_mb": payload.get("peak_rss_mb"),
                    "f1": agg.get("f1"),
                    "precision": agg.get("precision"),
                    "recall": agg.get("recall"),
                    "perfect_core": perfect_document(rows_v2, core_only=True),
                    "n_critical": len(crit),
                    "critical_kinds": [c.get("kind") for c in crit],
                    "field_groups": group_metrics(rows_v2),
                }
                doc_entry[fe] = entry
                per_fe_rows[fe].extend(rows_v2)
            docs_out.append(doc_entry)
        results[model_key] = {
            "model_id": MODELS[model_key]["id"],
            "by_frontend": {
                fe: {
                    **aggregate_v2(per_fe_rows[fe]),
                    "perfect_core_docs": sum(
                        1 for d in docs_out if d.get(fe, {}).get("perfect_core")
                    ),
                    "n_docs": sum(1 for d in docs_out if fe in d and "error" not in d[fe]),
                }
                for fe in ("cv_extract", "docling")
            },
            "documents": docs_out,
            "comparison_type": "KNOWN_FRONTEND_ABLATION_NOT_BLIND",
            "hardware_note": "Agent-VM — not i3/8GB Job Object ship evidence",
        }
    return results


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-llm", action="store_true", help="Run Phi+Qwen on both frontends")
    ap.add_argument(
        "--models",
        default="qwen,phi",
        help="Comma list: qwen,phi",
    )
    ap.add_argument("--text-only", action="store_true")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    print("Extracting texts (cv_extract + docling)…", flush=True)
    rows = extract_texts()
    soll = _parse_sollwerte(SOLL.read_text(encoding="utf-8"))
    attach_gt_coverage(rows, soll)

    text_report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "comparison_type": "KNOWN_FRONTEND_TEXT_ABLATION_NOT_BLIND",
        "note": (
            "Docling is eval-only (KARRIEREKRAKE_CV_USE_DOCLING). "
            "Product EXE ships cv_extract only."
        ),
        "n_docs": len(rows),
        "summary": {
            "mean_jaccard": round(
                sum(r["token_jaccard"] for r in rows.values()) / max(1, len(rows)), 4
            ),
            "mean_char_ratio_cv_over_docling": round(
                sum(
                    (r["char_ratio_cv_over_docling"] or 0)
                    for r in rows.values()
                    if r["char_ratio_cv_over_docling"] is not None
                )
                / max(
                    1,
                    sum(
                        1
                        for r in rows.values()
                        if r["char_ratio_cv_over_docling"] is not None
                    ),
                ),
                4,
            ),
            "gt_coverage_mean": {
                fe: round(
                    sum(
                        (r.get("gt_coverage") or {}).get(fe, {}).get("coverage") or 0
                        for r in rows.values()
                    )
                    / max(1, len(rows)),
                    4,
                )
                for fe in ("cv_extract", "docling")
            },
        },
        "documents": {
            k: {kk: vv for kk, vv in v.items() if kk != "text" and not (
                isinstance(vv, dict) and "text" in vv
            )}
            | {
                fe: {sk: sv for sk, sv in v[fe].items() if sk != "text"}
                for fe in ("cv_extract", "docling")
            }
            for k, v in rows.items()
        },
    }
    # Fix nested text strip more carefully
    clean_docs = {}
    for k, v in rows.items():
        clean_docs[k] = {
            "file": v["file"],
            "lang": v["lang"],
            "token_jaccard": v["token_jaccard"],
            "char_ratio_cv_over_docling": v["char_ratio_cv_over_docling"],
            "tokens_only_in_cv_extract_sample": v["tokens_only_in_cv_extract_sample"],
            "tokens_only_in_docling_sample": v["tokens_only_in_docling_sample"],
            "gt_coverage": v.get("gt_coverage"),
            "cv_extract": {sk: sv for sk, sv in v["cv_extract"].items() if sk != "text"},
            "docling": {sk: sv for sk, sv in v["docling"].items() if sk != "text"},
        }
    text_report["documents"] = clean_docs
    (OUT / "TEXT_ABLATION.json").write_text(
        json.dumps(text_report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(text_report["summary"], indent=2), flush=True)

    # Persist full texts for reproducibility (gitignored under artifacts/**)
    texts_dir = OUT / "texts"
    texts_dir.mkdir(exist_ok=True)
    for fname, row in rows.items():
        for fe in ("cv_extract", "docling"):
            (texts_dir / f"{Path(fname).stem}__{fe}.txt").write_text(
                row[fe]["text"], encoding="utf-8"
            )

    if args.text_only or not args.run_llm:
        print("Text ablation done. Pass --run-llm for model impact.", flush=True)
        return 0

    models = [m.strip() for m in args.models.split(",") if m.strip() in MODELS]
    print(f"Running LLM impact for {models}…", flush=True)
    llm_report = run_llm_impact(rows, soll, models=models)
    (OUT / "LLM_IMPACT.json").write_text(
        json.dumps(llm_report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    for mk, block in llm_report.items():
        print(f"=== {mk} ===", flush=True)
        for fe, agg in block["by_frontend"].items():
            print(
                f"  {fe}: F1={agg.get('f1')} P={agg.get('precision')} "
                f"R={agg.get('recall')} n={agg.get('n_docs')} "
                f"PC={agg.get('perfect_core_docs')}",
                flush=True,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
