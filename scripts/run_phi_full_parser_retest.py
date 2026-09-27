#!/usr/bin/env python3
"""Retest Phi inside the historical CV parser stack (not isolated LLM).

KNOWN-CV TEST on SMOKE_DE_EN_10_V1 — not a blind holdout.

Pipelines (offline only; production import stays Docpick+Qwen):

  DET_VERIFY       — cv_extract → parse_cv_text → verify_repair
  DET_PHI          — DET_VERIFY + suggest_cv_extract → reconcile_phi → verify
  DOCLING_DET      — Docling → parse_cv_text → verify_repair
  DOCLING_DET_PHI  — DOCLING_DET + Phi reconcile + verify

Critical: do NOT call ``import_cv`` — on current main it is Docpick+Qwen,
which would mix packaging/model choices into this parser-system retest.
"""

from __future__ import annotations

import hashlib
import json
import os
import resource
import sys
import time
import traceback
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

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
GT_PATH = ROOT / "tests" / "fixtures" / "cv_corpus" / "expected_results.json"
OUT = ROOT / "artifacts" / "phi_full_parser_retest"
PHI_GGUF = Path(
    os.environ.get(
        "KARRIEREKRAKE_PHI_CV_MODEL",
        "/tmp/karrierekrake-models/phi4-mini/microsoft_Phi-4-mini-instruct-Q4_K_M.gguf",
    )
)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _peak_rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def _load_manifest() -> list[dict[str, Any]]:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    docs = data.get("documents") or data.get("samples") or []
    out: list[dict[str, Any]] = []
    for d in docs:
        if isinstance(d, str):
            p = ROOT / "tests" / "fixtures" / "cv_corpus" / d
            lang = "de" if d.startswith("DE_") else "en"
            out.append({"id": Path(d).stem, "path": str(p), "lang": lang, "filename": d})
            continue
        rel = d.get("path") or ""
        path = ROOT / rel if rel and not Path(rel).is_absolute() else Path(rel) if rel else Path()
        fname = Path(rel).name if rel else (d.get("filename") or d.get("file") or f"{d.get('id')}.pdf")
        if not path.exists():
            alt = ROOT / "tests" / "fixtures" / "cv_corpus" / Path(fname).name
            path = alt if alt.exists() else path
        lang = (d.get("lang") or d.get("language") or ("de" if str(fname).startswith("DE_") else "en")).lower()
        out.append(
            {
                "id": str(d.get("id") or Path(fname).stem),
                "path": str(path),
                "lang": "de" if lang.startswith("de") else "en",
                "filename": Path(fname).name,
            }
        )
    return out


def _extract_text(path: Path, backend: str) -> str:
    from core.cv_document_backends import extract_with_backend

    return extract_with_backend(path, backend) or ""


def _det_verify(text: str) -> dict[str, Any]:
    from core.cv_parser import parse_cv_text
    from core.cv_verify_repair import apply_verify_repair_pipeline

    parsed = parse_cv_text(text)
    parsed = apply_verify_repair_pipeline(parsed, text)
    return parsed


def _apply_phi(parsed: dict[str, Any], text: str) -> dict[str, Any]:
    """Historical gap-fill: PHI_EXTRACT → validate → reconcile → verify."""
    from core.cv_intelligence import reconcile_phi_into_parsed
    from core.cv_verify_repair import apply_verify_repair_pipeline
    from guenther.model_manager import PRODUCTION_MODEL_ID
    from guenther.service import get_guenther_service

    # Point Günther at the known GGUF if models dir is empty for phi4-mini.
    if PHI_GGUF.is_file():
        os.environ.setdefault("KARRIEREKRAKE_MODELS_DIR", str(PHI_GGUF.parent.parent))
        # Some installs look for model under <dir>/phi4-mini/*.gguf
        models_root = PHI_GGUF.parent.parent
        os.environ["KARRIEREKRAKE_MODELS_DIR"] = str(models_root)

    svc = get_guenther_service(enabled=True, model=PRODUCTION_MODEL_ID, refresh=False)
    env = svc.suggest_cv_extract(text)
    if not env.ok:
        parsed = dict(parsed)
        parsed["phi_invoked"] = False
        parsed["intelligence_status"] = "GUENTHER_UNAVAILABLE"
        parsed["phi_error"] = "; ".join(env.safety_notes or []) or "suggest_cv_extract failed"
        return parsed
    sug = dict(env.suggestion or {})
    sug["_model_id"] = env.model_id or PRODUCTION_MODEL_ID
    parsed = reconcile_phi_into_parsed(parsed, sug, cv_text=text)
    parsed = apply_verify_repair_pipeline(parsed, text)
    parsed["phi_invoked"] = True
    parsed["intelligence_status"] = "phi_invoked"
    parsed["phi_raw_suggestion"] = sug
    return parsed


def run_pipeline(
    path: Path, *, backend: str, with_phi: bool, pipeline: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    meta: dict[str, Any] = {
        "pipeline": pipeline,
        "backend": backend,
        "with_phi": with_phi,
        "tech_error": None,
        "text_chars": 0,
        "text_sha256": "",
    }
    try:
        text = _extract_text(path, backend)
        meta["text_chars"] = len(text)
        meta["text_sha256"] = _sha256_bytes(text.encode("utf-8"))
        parsed = _det_verify(text)
        if with_phi:
            parsed = _apply_phi(parsed, text)
        parsed["document_backend"] = backend
        parsed["pipeline"] = pipeline
        parsed["source_text_chars"] = len(text)
        return parsed, meta
    except Exception as exc:  # noqa: BLE001
        meta["tech_error"] = f"{type(exc).__name__}: {exc}"
        meta["traceback"] = traceback.format_exc(limit=8)
        return {
            "personal": {},
            "emails": [],
            "phones": [],
            "languages": [],
            "education": [],
            "work_experience": [],
            "certificates": [],
            "software": [],
            "skills": [],
            "driving_license": "",
            "pipeline": pipeline,
            "tech_error": True,
        }, meta


def import_roundtrip_ok(parsed: dict[str, Any]) -> dict[str, Any]:
    try:
        from core.cv_parser import parsed_to_qualifications
        from desktop.services.profile_merge import (
            filter_parsed_for_import,
            personal_from_parsed,
        )

        cleaned = filter_parsed_for_import(parsed)
        quals = parsed_to_qualifications(cleaned)
        personal = personal_from_parsed(cleaned)
        has_identity = bool(
            (personal.get("first_name") or personal.get("last_name") or personal.get("full_name"))
            or (cleaned.get("emails") or [])
        )
        return {
            "ok": bool(quals is not None and personal is not None and has_identity),
            "has_identity": has_identity,
            "mapping_ok": True,
            "n_languages": len((quals or {}).get("languages") or cleaned.get("languages") or []),
            "n_skills": len((quals or {}).get("skills") or cleaned.get("skills") or []),
            "n_work": len(
                (quals or {}).get("work_experience") or cleaned.get("work_experience") or []
            ),
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}", "has_identity": False}


def score_pipeline(
    *,
    label: str,
    docs_meta: list[dict[str, Any]],
    gt_docs: dict[str, Any],
    predictions: dict[str, dict[str, Any]],
    texts: dict[str, str],
    timings: dict[str, float],
    peaks: dict[str, float],
    run_meta: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    all_rows: list[FactResult] = []
    per_doc: dict[str, Any] = {}
    critical_all: list[dict[str, Any]] = []
    by_lang_rows: dict[str, list[FactResult]] = {"de": [], "en": []}

    for meta in docs_meta:
        fname = meta["filename"]
        lang = meta["lang"]
        g_raw = gt_docs.get(fname)
        if g_raw is None:
            raise KeyError(f"GT missing for {fname}")
        g = prepare_gt_for_scorer(g_raw)
        text = texts[fname]
        pred = predictions[fname]
        evidence = build_evidence_for_doc(fname, g, text)
        rows = evaluate_doc_v2(fname, g, pred, evidence)
        all_rows.extend(rows)
        by_lang_rows[lang].extend(rows)
        crit = classify_critical(rows)
        critical_all.extend(crit)
        errs = [r for r in rows if r.status not in {"correct", "skipped"}]
        rm = run_meta.get(fname) or {}
        ir = import_roundtrip_ok(pred)
        per_doc[fname] = {
            "lang": lang,
            "perfect": perfect_document(rows),
            "perfect_core": perfect_document(rows, core_only=True),
            "n_errors": len(errs),
            "n_critical": len(crit),
            "elapsed_s": timings.get(fname, 0.0),
            "peak_rss_mb": peaks.get(fname, 0.0),
            "tech_error": rm.get("tech_error"),
            "phi_invoked": bool(pred.get("phi_invoked")),
            "import_roundtrip": ir,
            "missing_fields": [r.field for r in errs if r.status == "missing"][:20],
            "wrong_fields": [r.field for r in errs if r.status == "wrong"][:20],
            "hallucinated_fields": [r.field for r in errs if r.status == "hallucinated"][:20],
            "error_fields": [
                {"field": r.field, "group": r.group, "status": r.status} for r in errs[:40]
            ],
        }

    invented = [
        c
        for c in critical_all
        if c["status"] == "hallucinated" and str(c.get("kind") or "").startswith("invented_")
    ]
    kind_counts = Counter(str(c.get("kind") or "") for c in invented)

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
                "counts": {},
            }
        )
        docs = (
            per_doc if doc_filter is None else {k: v for k, v in per_doc.items() if k in doc_filter}
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
            "peak_rss_mb_max": max((v["peak_rss_mb"] for v in docs.values()), default=0.0),
            "tech_errors": sum(1 for v in docs.values() if v.get("tech_error")),
            "import_ok_docs": sum(1 for v in docs.values() if (v.get("import_roundtrip") or {}).get("ok")),
            "phi_invoked_docs": sum(1 for v in docs.values() if v.get("phi_invoked")),
            "by_group": group_metrics(use) if use else {},
        }

    de_docs = {m["filename"] for m in docs_meta if m["lang"] == "de"}
    en_docs = {m["filename"] for m in docs_meta if m["lang"] == "en"}
    return {
        "label": label,
        "metrics_all": pack(all_rows),
        "metrics_de": pack(by_lang_rows["de"], de_docs),
        "metrics_en": pack(by_lang_rows["en"], en_docs),
        "critical_kinds": dict(kind_counts),
        "per_document": per_doc,
    }


PIPELINES: dict[str, tuple[str, bool]] = {
    "DET_VERIFY": ("current", False),
    "DET_PHI": ("current", True),
    "DOCLING_DET": ("docling", False),
    "DOCLING_DET_PHI": ("docling", True),
}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    docs_meta = _load_manifest()
    gt_blob = json.loads(GT_PATH.read_text(encoding="utf-8"))
    gt_docs = gt_blob["documents"]

    seal = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "comparison_type": "KNOWN_CV_TEST_NOT_BLIND",
        "manifest_id": "SMOKE_DE_EN_10_V1",
        "note": (
            "Phi retested inside historical parser stack (text→DET→verify±Phi). "
            "Not an independent blind holdout. Production path unchanged (Docpick+Qwen)."
        ),
        "manifest_sha256": _sha256_file(MANIFEST),
        "ground_truth_sha256": _sha256_file(GT_PATH),
        "scorer_sha256": _sha256_file(ROOT / "scripts" / "holdout_scorer_v2.py"),
        "phi_gguf": str(PHI_GGUF),
        "phi_gguf_sha256": _sha256_file(PHI_GGUF) if PHI_GGUF.is_file() else None,
        "pipelines": list(PIPELINES),
    }
    (OUT / "PHASE_A_SEAL.json").write_text(
        json.dumps(seal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    # Shared texts per backend (hash before any scoring)
    shared_texts: dict[str, dict[str, str]] = {"current": {}, "docling": {}}
    text_hashes: dict[str, dict[str, str]] = {"current": {}, "docling": {}}
    for backend in ("current", "docling"):
        for meta in docs_meta:
            path = Path(meta["path"])
            text = _extract_text(path, backend)
            shared_texts[backend][meta["filename"]] = text
            text_hashes[backend][meta["filename"]] = _sha256_bytes(text.encode("utf-8"))
            (OUT / f"text_{backend}_{meta['filename']}.sha256").write_text(
                text_hashes[backend][meta["filename"]] + "\n", encoding="utf-8"
            )

    results: dict[str, Any] = {}
    freeze: dict[str, Any] = {"frozen_at": None, "predictions": {}}

    for name, (backend, with_phi) in PIPELINES.items():
        print(f"=== {name} (backend={backend}, phi={with_phi}) ===", flush=True)
        pred_dir = OUT / "predictions" / name
        pred_dir.mkdir(parents=True, exist_ok=True)
        predictions: dict[str, dict[str, Any]] = {}
        timings: dict[str, float] = {}
        peaks: dict[str, float] = {}
        run_meta: dict[str, dict[str, Any]] = {}
        pred_hashes: dict[str, str] = {}

        for meta in docs_meta:
            fname = meta["filename"]
            path = Path(meta["path"])
            print(f"  {fname} ...", flush=True)
            t0 = time.perf_counter()
            parsed, rm = run_pipeline(path, backend=backend, with_phi=with_phi, pipeline=name)
            elapsed = time.perf_counter() - t0
            peak = _peak_rss_mb()
            timings[fname] = elapsed
            peaks[fname] = peak
            run_meta[fname] = rm
            predictions[fname] = parsed
            out_path = pred_dir / f"{Path(fname).stem}.json"
            payload = json.dumps(parsed, ensure_ascii=False, indent=2, default=str) + "\n"
            out_path.write_text(payload, encoding="utf-8")
            pred_hashes[out_path.name] = _sha256_bytes(payload.encode("utf-8"))
            print(
                f"    {elapsed:.1f}s peak={peak:.0f}MB tech={rm.get('tech_error')} "
                f"phi={parsed.get('phi_invoked')}",
                flush=True,
            )

        freeze["predictions"][name] = pred_hashes
        # Score only after this pipeline's predictions are written+hashed
        score = score_pipeline(
            label=name,
            docs_meta=docs_meta,
            gt_docs=gt_docs,
            predictions=predictions,
            texts=shared_texts[backend],
            timings=timings,
            peaks=peaks,
            run_meta=run_meta,
        )
        results[name] = score
        m = score["metrics_all"]
        print(
            f"  → F1={m['f1']:.4f} DE={score['metrics_de']['f1']:.4f} "
            f"EN={score['metrics_en']['f1']:.4f} perfect_core={m['perfect_core']} "
            f"invented={m['invented_critical']} hallu={m['hallucination_rate']:.3f} "
            f"avg_s={m['avg_s_per_cv']:.1f} peak={m['peak_rss_mb_max']:.0f}",
            flush=True,
        )

    freeze["frozen_at"] = datetime.now(timezone.utc).isoformat()
    freeze["text_hashes"] = text_hashes
    freeze["phase_a_seal_sha256"] = _sha256_file(OUT / "PHASE_A_SEAL.json")
    (OUT / "PREDICTION_FREEZE.json").write_text(
        json.dumps(freeze, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    # Decision among these offline pipelines only (does not change production).
    ranked = sorted(
        results.items(),
        key=lambda kv: (
            -kv[1]["metrics_all"]["perfect_core"],
            -kv[1]["metrics_de"]["f1"],
            -kv[1]["metrics_en"]["f1"],
            -kv[1]["metrics_all"]["f1"],
            kv[1]["metrics_all"]["invented_critical"],
            kv[1]["metrics_all"]["avg_s_per_cv"],
            kv[1]["metrics_all"]["peak_rss_mb_max"],
        ),
    )
    best_name, best = ranked[0]
    det_only = results["DET_VERIFY"]["metrics_all"]
    det_phi = results["DET_PHI"]["metrics_all"]
    phi_helps = (
        det_phi["f1"] > det_only["f1"] + 0.01
        and det_phi["invented_critical"] <= det_only["invented_critical"]
        and det_phi["hallucination_rate"] <= det_only["hallucination_rate"] + 0.01
    )

    decision = {
        "best_offline_pipeline": best_name,
        "phi_improves_det_on_known_smoke": phi_helps,
        "production_path_changed": False,
        "rationale": [
            "Offline retest of historical DET±Phi (±Docling) stack on known SMOKE CVs.",
            "Production remains Docpick+Qwen; this run does not promote Phi.",
            (
                "Phi improves DET on this known corpus."
                if phi_helps
                else "Phi does not clearly improve DET on this known corpus (quality/hallu)."
            ),
            f"Best offline by quality ranking: {best_name}.",
        ],
        "windows_exe_import_verified": False,
        "note": "KNOWN_CV_TEST_NOT_BLIND — no independent 99% claim.",
    }

    table = {
        "metric": [
            "f1_all",
            "f1_de",
            "f1_en",
            "perfect_core",
            "invented_critical",
            "hallucination_rate",
            "missing_count",
            "wrong_count",
            "tech_errors",
            "import_ok_docs",
            "avg_s_per_cv",
            "peak_rss_mb_max",
            "phi_invoked_docs",
        ],
    }
    for name, score in results.items():
        m = score["metrics_all"]
        counts = m.get("counts") or {}
        table[name] = [
            round(m["f1"], 4),
            round(score["metrics_de"]["f1"], 4),
            round(score["metrics_en"]["f1"], 4),
            m["perfect_core"],
            m["invented_critical"],
            round(m["hallucination_rate"], 4),
            counts.get("missing", 0),
            counts.get("wrong", 0),
            m["tech_errors"],
            m["import_ok_docs"],
            round(m["avg_s_per_cv"], 1),
            round(m["peak_rss_mb_max"], 1),
            m["phi_invoked_docs"],
        ]

    report = {
        "comparison_type": "KNOWN_CV_TEST_NOT_BLIND",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "seal": seal,
        "freeze": freeze,
        "pipelines": results,
        "decision": decision,
        "table": table,
    }
    (OUT / "COMPARE_REPORT.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8"
    )
    (OUT / "COMPARE_TABLE.json").write_text(
        json.dumps({"table": table, "decision": decision}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print("\n=== TABLE ===", flush=True)
    print(json.dumps(table, indent=2), flush=True)
    print(json.dumps(decision, indent=2, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
