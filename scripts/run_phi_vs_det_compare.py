#!/usr/bin/env python3
"""Offline Phi vs DET comparison on a pre-locked Mini-30 DE/EN sample.

- Does NOT change the productive CV extraction path.
- Uses identical PDF text, GT, and unchanged Scorer V2 for both sides.
- One Phi config only (phi4-mini + SYSTEM_PHI_EXTRACT + suggest_cv_extract).
- Known corpus = development data; not an independent blind test.

Usage:
  python scripts/run_phi_vs_det_compare.py
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
from pathlib import Path
from typing import Any

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

OUT = ROOT / "artifacts" / "phi_vs_det_compare"
MANIFEST_PATH = OUT / "SAMPLE_MANIFEST_LOCKED.json"


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


def _serialize(parsed: dict[str, Any]) -> dict[str, Any]:
    def conv(o: Any) -> Any:
        if isinstance(o, dict):
            return {str(k): conv(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [conv(x) for x in o]
        if isinstance(o, (str, int, float, bool)) or o is None:
            return o
        if hasattr(o, "model_dump"):
            return conv(o.model_dump())
        return str(o)

    return conv(parsed)


def run_det(path: Path) -> dict[str, Any]:
    from core.cv_parser import import_cv

    parsed = import_cv(path, guenther_enabled=False)
    parsed["pipeline"] = "DET_PRODUCT"
    return parsed


def run_phi_only(path: Path, *, text: str) -> dict[str, Any]:
    """Offline prototype: PHI_EXTRACT mapped to parsed shape; no DET content fill."""
    from guenther.model_manager import PRODUCTION_MODEL_ID
    from guenther.service import get_guenther_service

    svc = get_guenther_service(enabled=True, model=PRODUCTION_MODEL_ID, refresh=False)
    env = svc.suggest_cv_extract(text)
    suggestion = dict(env.suggestion or {}) if env.ok else {}
    if env.ok and hasattr(env.suggestion, "model_dump"):
        suggestion = env.suggestion.model_dump()

    langs: list[dict[str, str]] = []
    for item in suggestion.get("languages") or []:
        if isinstance(item, str):
            parts = [p.strip() for p in item.replace("–", "-").replace("—", "-").split("-", 1)]
            if len(parts) == 1:
                # also allow "Deutsch (C1)" / "Deutsch C1"
                import re

                m = re.match(r"^(.+?)\s*[\(\[]?\s*([A-C][12]|Native|Muttersprache|mother\s*tongue)\s*[\)\]]?\s*$", parts[0], re.I)
                if m:
                    langs.append({"language": m.group(1).strip(), "level": m.group(2).strip()})
                else:
                    langs.append({"language": parts[0], "level": ""})
            else:
                langs.append({"language": parts[0], "level": parts[1]})
        elif isinstance(item, dict):
            langs.append(
                {
                    "language": str(item.get("language") or item.get("name") or ""),
                    "level": str(item.get("level") or ""),
                }
            )

    certs = []
    for c in suggestion.get("certificates") or []:
        if isinstance(c, dict):
            certs.append(c)
        else:
            certs.append({"name": str(c), "issuer": "", "year": ""})

    parsed: dict[str, Any] = {
        "personal": {"full_name": suggestion.get("full_name") or ""},
        "emails": list(suggestion.get("emails") or []),
        "phones": list(suggestion.get("phones") or []),
        "skills": list(suggestion.get("skills") or []),
        "software": [],
        "languages": langs,
        "education": [
            {"qualification": e, "institution": "", "start_date": "", "end_date": ""}
            for e in (suggestion.get("education") or [])
            if isinstance(e, str)
        ]
        + [e for e in (suggestion.get("education") or []) if isinstance(e, dict)],
        "work_experience": [
            {
                "title": t,
                "company": "",
                "start_date": "",
                "end_date": "",
                "responsibilities": [],
            }
            for t in (suggestion.get("experience_titles") or [])
            if isinstance(t, str)
        ],
        "certificates": certs,
        "driving_license": "",
        "intelligence_status": "phi_only" if env.ok else "GUENTHER_UNAVAILABLE",
        "phi_invoked": bool(env.ok),
        "pipeline": "PHI_ONLY_OFFLINE",
        "phi_safety_notes": list(env.safety_notes or []),
        "phi_model_id": env.model_id or PRODUCTION_MODEL_ID,
        "phi_raw_ok": bool(env.ok),
        "phi_error": None if env.ok else (env.error or env.provider_status),
    }
    name = (suggestion.get("full_name") or "").strip().split()
    if name:
        parsed["personal"]["first_name"] = name[0]
        parsed["personal"]["last_name"] = " ".join(name[1:]) if len(name) > 1 else ""
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
        doc_id = meta["id"]
        fname = f"{doc_id}.pdf"
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
            "error_fields": [
                {"field": r.field, "group": r.group, "status": r.status}
                for r in errs
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
        use = rows
        if doc_filter is not None:
            use = [r for r in rows if r.document in doc_filter]
        agg = aggregate_v2(use) if use else {
            "precision": 0.0,
            "recall": 0.0,
            "f1": 0.0,
            "hallucination_rate": 0.0,
            "field_accuracy": 0.0,
            "counts": {},
        }
        if doc_filter is None:
            docs = per_doc
        else:
            docs = {k: v for k, v in per_doc.items() if k in doc_filter}
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

    de_docs = {f"{m['id']}.pdf" for m in docs_meta if m["lang"] == "de"}
    en_docs = {f"{m['id']}.pdf" for m in docs_meta if m["lang"] == "en"}

    return {
        "label": label,
        "metrics_all": pack(all_rows),
        "metrics_de": pack(by_lang_rows["de"], de_docs),
        "metrics_en": pack(by_lang_rows["en"], en_docs),
        "per_document": per_doc,
        "error_inventory": error_inventory,
        "critical_invented": invented,
        "critical_kinds": dict(Counter(c["kind"] for c in invented)),
    }


def main() -> int:
    if not MANIFEST_PATH.is_file():
        print(f"missing locked manifest: {MANIFEST_PATH}", file=sys.stderr)
        return 2

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert manifest.get("locked") is True
    docs_meta = list(manifest["documents"])
    gt_path = ROOT / manifest["ground_truth"]
    gt_raw = json.loads(gt_path.read_text(encoding="utf-8"))
    gt_docs = gt_raw["documents"]

    scorer_sha = hashlib.sha256(
        (ROOT / "scripts" / "holdout_scorer_v2.py").read_bytes()
    ).hexdigest()
    expected_sha = (manifest.get("scorer") or {}).get("sha256")
    if expected_sha and scorer_sha != expected_sha:
        print(
            f"scorer hash mismatch: expected {expected_sha}, got {scorer_sha}",
            file=sys.stderr,
        )
        return 3

    from core.cv_extract import extract_text

    OUT.mkdir(parents=True, exist_ok=True)
    pred_det_dir = OUT / "predictions_det"
    pred_phi_dir = OUT / "predictions_phi"
    pred_det_dir.mkdir(exist_ok=True)
    pred_phi_dir.mkdir(exist_ok=True)

    texts: dict[str, str] = {}
    paths: dict[str, Path] = {}
    for meta in docs_meta:
        fname = f"{meta['id']}.pdf"
        pdf = ROOT / meta["path"]
        if not pdf.is_file():
            print(f"missing PDF {pdf}", file=sys.stderr)
            return 4
        texts[fname] = extract_text(pdf) or ""
        paths[fname] = pdf

    # --- DET pass ---
    rss_before_det = _peak_rss_mb()
    det_preds: dict[str, dict[str, Any]] = {}
    det_timings: dict[str, float] = {}
    t_det0 = time.perf_counter()
    for meta in docs_meta:
        fname = f"{meta['id']}.pdf"
        t0 = time.perf_counter()
        try:
            parsed = run_det(paths[fname])
        except Exception as exc:  # noqa: BLE001
            parsed = {
                "pipeline": "DET_PRODUCT",
                "tech_error": str(exc),
                "traceback": traceback.format_exc(),
            }
        det_timings[fname] = time.perf_counter() - t0
        det_preds[fname] = parsed
        (pred_det_dir / f"{meta['id']}.json").write_text(
            json.dumps(_serialize(parsed), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    det_wall = time.perf_counter() - t_det0
    det_peak = _peak_rss_mb()

    # --- Phi pass (single config) ---
    tech_fix_used = 0
    phi_preds: dict[str, dict[str, Any]] = {}
    phi_timings: dict[str, float] = {}
    phi_load_error: str | None = None
    t_phi0 = time.perf_counter()
    try:
        # Warm service once
        from guenther.model_manager import PRODUCTION_MODEL_ID
        from guenther.service import get_guenther_service

        svc = get_guenther_service(enabled=True, model=PRODUCTION_MODEL_ID, refresh=True)
        _ = svc  # keep reference
    except Exception as exc:  # noqa: BLE001
        phi_load_error = f"{type(exc).__name__}: {exc}"

    for meta in docs_meta:
        fname = f"{meta['id']}.pdf"
        t0 = time.perf_counter()
        try:
            if phi_load_error:
                parsed = {
                    "pipeline": "PHI_ONLY_OFFLINE",
                    "phi_invoked": False,
                    "intelligence_status": "GUENTHER_UNAVAILABLE",
                    "phi_error": phi_load_error,
                }
            else:
                parsed = run_phi_only(paths[fname], text=texts[fname])
                # At most one technical fix: retry once on empty/unavailable envelope
                if (
                    tech_fix_used < 1
                    and not parsed.get("phi_raw_ok")
                    and not parsed.get("emails")
                    and not (parsed.get("personal") or {}).get("first_name")
                ):
                    tech_fix_used += 1
                    parsed = run_phi_only(paths[fname], text=texts[fname])
                    parsed["technical_retry"] = True
        except Exception as exc:  # noqa: BLE001
            if tech_fix_used < 1:
                tech_fix_used += 1
                try:
                    parsed = run_phi_only(paths[fname], text=texts[fname])
                    parsed["technical_retry_after_exception"] = str(exc)
                except Exception as exc2:  # noqa: BLE001
                    parsed = {
                        "pipeline": "PHI_ONLY_OFFLINE",
                        "tech_error": str(exc2),
                        "prior_error": str(exc),
                        "traceback": traceback.format_exc(),
                    }
            else:
                parsed = {
                    "pipeline": "PHI_ONLY_OFFLINE",
                    "tech_error": str(exc),
                    "traceback": traceback.format_exc(),
                }
        phi_timings[fname] = time.perf_counter() - t0
        phi_preds[fname] = parsed
        (pred_phi_dir / f"{meta['id']}.json").write_text(
            json.dumps(_serialize(parsed), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    phi_wall = time.perf_counter() - t_phi0
    phi_peak = _peak_rss_mb()

    det_score = _score_side(
        label="DET",
        docs_meta=docs_meta,
        gt_docs=gt_docs,
        predictions=det_preds,
        texts=texts,
        timings=det_timings,
    )
    phi_score = _score_side(
        label="PHI",
        docs_meta=docs_meta,
        gt_docs=gt_docs,
        predictions=phi_preds,
        texts=texts,
        timings=phi_timings,
    )

    gates = manifest["hardware_gates_predeclared"]
    det_f1 = float(det_score["metrics_all"]["f1"])
    phi_f1 = float(phi_score["metrics_all"]["f1"])
    delta_f1 = phi_f1 - det_f1
    ram_ok = phi_peak <= float(gates["max_peak_rss_mb"])
    clearly = delta_f1 >= float(gates["clearly_better_delta_f1"]) and ram_ok
    decision = (
        "Phi für neuen Blindtest prüfen" if clearly else "Phi-Versuch stoppen"
    )

    result = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "commit": _git(),
        "manifest_id": manifest["manifest_id"],
        "disclaimer": (
            "Known Mini-30 development sample — not an independent blind test. "
            "IH2 frozen F1 0.7246 is context only. PR#59 ~0.73 was section-accuracy, not F1."
        ),
        "scorer_sha256": scorer_sha,
        "tech_fix_used": tech_fix_used,
        "phi_load_error": phi_load_error,
        "phi_config": manifest["phi_config"],
        "performance": {
            "det": {
                "wall_s": det_wall,
                "avg_s_per_cv": det_score["metrics_all"]["avg_s_per_cv"],
                "peak_rss_mb": det_peak,
                "rss_before_mb": rss_before_det,
            },
            "phi": {
                "wall_s": phi_wall,
                "avg_s_per_cv": phi_score["metrics_all"]["avg_s_per_cv"],
                "peak_rss_mb": phi_peak,
            },
        },
        "gates": gates,
        "gate_evaluation": {
            "delta_f1": delta_f1,
            "clearly_better_f1": delta_f1 >= float(gates["clearly_better_delta_f1"]),
            "ram_ok": ram_ok,
            "time_budget_specified": gates.get("max_avg_s_per_cv") is not None,
        },
        "decision": decision,
        "det": det_score,
        "phi": phi_score,
        "not_proven": [
            "Generalization to unseen real CVs",
            "Independent blind-test superiority",
            "Productive replacement safety",
            "That section-accuracy equals F1 (it does not)",
            "That IH2 post-analysis F1 1.0 is an independent result (it is not)",
        ],
    }

    out_json = OUT / "COMPARE_RESULTS.json"
    out_json.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )

    def line(tag: str, m: dict[str, Any], perf: dict[str, Any]) -> None:
        print(
            f"{tag}: P={m['precision']:.4f} R={m['recall']:.4f} F1={m['f1']:.4f} "
            f"hallu={m['hallucination_rate']:.4f} perfect_core={m['perfect_core']}/{m['n_documents']} "
            f"invented={m['invented_critical']} avg_s={m['avg_s_per_cv']:.3f} "
            f"peak_rss_mb={perf['peak_rss_mb']:.1f}"
        )

    print(f"manifest={manifest['manifest_id']} commit={result['commit'][:12]}")
    line("DET_ALL", det_score["metrics_all"], result["performance"]["det"])
    line("PHI_ALL", phi_score["metrics_all"], result["performance"]["phi"])
    line("DET_DE ", det_score["metrics_de"], result["performance"]["det"])
    line("PHI_DE ", phi_score["metrics_de"], result["performance"]["phi"])
    line("DET_EN ", det_score["metrics_en"], result["performance"]["det"])
    line("PHI_EN ", phi_score["metrics_en"], result["performance"]["phi"])
    print(f"delta_f1={delta_f1:+.4f} decision={decision}")
    print(f"wrote {out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
