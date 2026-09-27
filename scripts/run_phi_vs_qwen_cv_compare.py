#!/usr/bin/env python3
"""Phi-4-mini vs Qwen3.5-4B CV extract — same text, full schema, Scorer V2.

KNOWN-CV TEST (not an independent blind holdout): uses locked SMOKE_DE_EN_10_V1
fixtures that were already used in Docpick/OSS development. Results must not be
marketed as independent 99%% proof.

Protocol:
  1. Freeze GT path + scorer hash; do not read GT during extraction.
  2. Extract PDF→text once per document (core.cv_extract) — shared by both models.
  3. Both models fill ``KarrierekrakeCVSchema`` (full productive field set).
  4. Write + hash predictions, then score.

No DET. No DET fallback. Packaging/EXE import (PR #96) is out of scope here.
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
OUT = ROOT / "artifacts" / "phi_vs_qwen_cv_extract"
PHI_GGUF = Path(
    os.environ.get(
        "KARRIEREKRAKE_PHI_CV_MODEL",
        "/tmp/karrierekrake-models/phi4-mini/microsoft_Phi-4-mini-instruct-Q4_K_M.gguf",
    )
)
QWEN_GGUF = Path(
    os.environ.get(
        "KARRIEREKRAKE_CV_LLM_MODEL",
        "/tmp/karrierekrake-models/qwen3.5-4b/Qwen3.5-4B-Q4_K_M.gguf",
    )
)
LLM_BASE = os.environ.get("KARRIEREKRAKE_CV_LLM_BASE", "http://127.0.0.1:8765/v1")
MAX_TOKENS = int(os.environ.get("KARRIEREKRAKE_CV_LLM_MAX_TOKENS", "4096"))
N_CTX = int(os.environ.get("KARRIEREKRAKE_CV_LLM_N_CTX", "4096"))


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _peak_rss_mb() -> float:
    # Linux: ru_maxrss is kilobytes.
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def _llama_server_rss_mb() -> float:
    total_kb = 0
    proc = Path("/proc")
    try:
        for entry in proc.iterdir():
            if not entry.name.isdigit():
                continue
            try:
                cmdline = (entry / "cmdline").read_bytes().decode("utf-8", "ignore")
            except OSError:
                continue
            if "llama_cpp.server" not in cmdline and "llama-server" not in cmdline:
                continue
            try:
                for line in (entry / "status").read_text(encoding="utf-8").splitlines():
                    if line.startswith("VmRSS:"):
                        total_kb += int(line.split()[1])
                        break
            except OSError:
                continue
    except OSError:
        return 0.0
    return total_kb / 1024.0


def _group_peak_mb(*, include_server: bool) -> float:
    peak = _peak_rss_mb()
    if include_server:
        peak += _llama_server_rss_mb()
    return peak


def _http_available(base: str) -> bool:
    try:
        import httpx

        with httpx.Client(timeout=5.0) as client:
            return client.get(f"{base.rstrip('/')}/models").status_code == 200
    except Exception:  # noqa: BLE001
        return False


def _extraction_messages(text: str, schema_json: str) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You are a document data extraction assistant. "
                "Output ONLY valid JSON. No markdown. "
                "If a field is not found, use null. "
                "For arrays, include all matching items found. "
                "Do not invent values. "
                "Preserve diacritics and special letters in names exactly as written. "
                "employment.position is the job title only — never duty bullets. "
                "When a job has no end date / is current, set end_date to 'heute'. "
                "Keep incomplete education outcomes in qualification. "
                "/no_think"
            ),
        },
        {
            "role": "user",
            "content": (
                f"## JSON Schema\n{schema_json}\n\n"
                f"## Document Text\n{text}\n\n"
                "Extract the data and output valid JSON:"
            ),
        },
    ]


def _parse_llm_json(raw: str) -> dict[str, Any]:
    from docpick.llm.prompt import parse_llm_json

    data = parse_llm_json(raw)
    if not isinstance(data, dict):
        raise ValueError("LLM JSON root is not an object")
    return data


def _chat_inprocess(messages: list[dict[str, str]], *, model_path: Path) -> str:
    from llama_cpp import Llama

    n_threads = max(2, (os.cpu_count() or 2))
    llm = Llama(
        model_path=str(model_path),
        n_ctx=N_CTX,
        n_threads=n_threads,
        n_batch=512,
        verbose=False,
    )
    try:
        out = llm.create_chat_completion(
            messages=messages,
            temperature=0.0,
            max_tokens=MAX_TOKENS,
        )
        return str(out["choices"][0]["message"]["content"] or "")
    finally:
        del llm


def _chat_http(messages: list[dict[str, str]], *, base: str, model: str) -> str:
    from docpick.llm.vllm_provider import VLLMProvider

    provider = VLLMProvider(
        base_url=base,
        model=model,
        temperature=0.0,
        max_tokens=MAX_TOKENS,
        timeout=300,
    )
    if not provider.is_available():
        raise RuntimeError(f"LLM HTTP unavailable at {base}")
    return provider._call_chat(messages)


def extract_full_schema(
    text: str,
    *,
    model_label: str,
    model_path: Path,
    transport: str,
    schema_json: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (raw_schema_dict, meta). Empty dict on hard failure — never invents."""
    messages = _extraction_messages(text, schema_json)
    meta: dict[str, Any] = {
        "model_label": model_label,
        "model_path": str(model_path),
        "transport": transport,
        "tech_error": None,
        "raw_chars": 0,
    }
    try:
        if transport == "http":
            raw = _chat_http(messages, base=LLM_BASE, model=str(model_path))
        else:
            raw = _chat_inprocess(messages, model_path=model_path)
        meta["raw_chars"] = len(raw or "")
        data = _parse_llm_json(raw)
        return data, meta
    except Exception as exc:  # noqa: BLE001
        meta["tech_error"] = f"{type(exc).__name__}: {exc}"
        meta["traceback"] = traceback.format_exc(limit=6)
        return {}, meta


def to_parsed(raw: dict[str, Any], *, pipeline: str) -> dict[str, Any]:
    from core.cv_docpick_import import suggestion_to_parsed

    if not raw:
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
            "driving_license": [],
            "pipeline": pipeline,
            "tech_error": True,
        }
    parsed = suggestion_to_parsed(raw, source_text="")
    parsed["pipeline"] = pipeline
    parsed["phi_invoked"] = pipeline.startswith("PHI")
    return parsed


def schema_completeness(raw: dict[str, Any]) -> dict[str, Any]:
    """Check productive schema keys are present (null/[] allowed — missing key is not)."""
    required_top = [
        "name",
        "email",
        "phone",
        "date_of_birth",
        "address",
        "languages",
        "licenses",
        "skills",
        "software",
        "certificates",
        "employment",
        "education",
    ]
    missing = [k for k in required_top if k not in raw]
    return {
        "ok": not missing and bool(raw),
        "missing_keys": missing,
        "n_keys_present": sum(1 for k in required_top if k in raw),
        "n_keys_required": len(required_top),
    }


def import_roundtrip_ok(parsed: dict[str, Any]) -> dict[str, Any]:
    """Simulate profile-preview mapping used by the dialog (no GUI)."""
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
            (personal or {}).get("first_name")
            or (personal or {}).get("last_name")
            or (cleaned.get("emails") or [])
        )
        return {
            "ok": bool(has_identity),
            "has_identity": has_identity,
            "mapping_ok": True,
            "n_languages": len(getattr(quals, "languages", None) or []),
            "n_skills": len(getattr(quals, "skills", None) or []),
            "n_work": len(getattr(quals, "work_experience", None) or []),
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "mapping_ok": False, "error": f"{type(exc).__name__}: {exc}"}


def _score_side(
    *,
    label: str,
    docs_meta: list[dict[str, Any]],
    gt_docs: dict[str, Any],
    predictions: dict[str, dict[str, Any]],
    texts: dict[str, str],
    timings: dict[str, float],
    peaks: dict[str, float],
    schema_stats: dict[str, dict[str, Any]],
    import_stats: dict[str, dict[str, Any]],
    tech_errors: dict[str, str | None],
) -> dict[str, Any]:
    all_rows: list[FactResult] = []
    per_doc: dict[str, Any] = {}
    critical_all: list[dict[str, Any]] = []
    error_inventory: list[dict[str, Any]] = []
    by_lang_rows: dict[str, list[FactResult]] = {"de": [], "en": []}
    status_counts: Counter[str] = Counter()

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
        for r in rows:
            status_counts[r.status] += 1
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
            "peak_rss_mb": peaks.get(fname, 0.0),
            "schema": schema_stats.get(fname, {}),
            "import_roundtrip": import_stats.get(fname, {}),
            "tech_error": tech_errors.get(fname),
            "missing_fields": [r.field for r in errs if r.status == "missing"],
            "wrong_fields": [r.field for r in errs if r.status == "wrong"],
            "hallucinated_fields": [r.field for r in errs if r.status == "hallucinated"],
            "error_fields": [
                {"field": r.field, "group": r.group, "status": r.status}
                for r in errs[:50]
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
                    # Avoid dumping full CV strings into the public summary.
                    "expected_len": len(str(r.expected or "")),
                    "actual_len": len(str(r.actual or "")),
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
            "peak_rss_mb_max": max((v["peak_rss_mb"] for v in docs.values()), default=0.0),
            "tech_errors": sum(1 for v in docs.values() if v.get("tech_error")),
            "schema_complete_docs": sum(
                1 for v in docs.values() if (v.get("schema") or {}).get("ok")
            ),
            "import_ok_docs": sum(
                1 for v in docs.values() if (v.get("import_roundtrip") or {}).get("ok")
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
        "status_counts": dict(status_counts),
        "per_document": per_doc,
        "error_inventory_n": len(error_inventory),
        "error_inventory_sample": error_inventory[:40],
        "critical_kinds": dict(Counter(c["kind"] for c in invented)),
    }


def run_model_side(
    *,
    label: str,
    pipeline: str,
    model_path: Path,
    transport: str,
    docs_meta: list[dict[str, Any]],
    texts: dict[str, str],
    schema_json: str,
    pred_dir: Path,
    include_server_in_peak: bool,
    repeat_ids: set[str] | None = None,
) -> dict[str, Any]:
    pred_dir.mkdir(parents=True, exist_ok=True)
    predictions: dict[str, dict[str, Any]] = {}
    raws: dict[str, dict[str, Any]] = {}
    timings: dict[str, float] = {}
    peaks: dict[str, float] = {}
    schema_stats: dict[str, dict[str, Any]] = {}
    import_stats: dict[str, dict[str, Any]] = {}
    tech_errors: dict[str, str | None] = {}
    repeats: dict[str, Any] = {}

    for meta in docs_meta:
        fname = Path(meta["path"]).name
        doc_id = meta["id"]
        text = texts[fname]
        print(f"[{label}] {doc_id} transport={transport}", flush=True)
        t0 = time.perf_counter()
        rss0 = _group_peak_mb(include_server=include_server_in_peak)
        raw, meta_run = extract_full_schema(
            text,
            model_label=label,
            model_path=model_path,
            transport=transport,
            schema_json=schema_json,
        )
        elapsed = time.perf_counter() - t0
        rss1 = _group_peak_mb(include_server=include_server_in_peak)
        timings[fname] = elapsed
        peaks[fname] = max(rss0, rss1)
        tech_errors[fname] = meta_run.get("tech_error")
        schema_stats[fname] = schema_completeness(raw)
        parsed = to_parsed(raw, pipeline=pipeline)
        if meta_run.get("tech_error"):
            parsed["tech_error_detail"] = meta_run["tech_error"]
        import_stats[fname] = import_roundtrip_ok(parsed)
        predictions[fname] = parsed
        raws[fname] = raw

        payload = {
            "document_id": doc_id,
            "file": fname,
            "model": label,
            "transport": transport,
            "elapsed_s": elapsed,
            "peak_rss_mb": peaks[fname],
            "schema_completeness": schema_stats[fname],
            "import_roundtrip": import_stats[fname],
            "tech_error": tech_errors[fname],
            "raw": raw,
            "parsed": parsed,
        }
        body = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        out_path = pred_dir / f"{doc_id}.json"
        out_path.write_text(body, encoding="utf-8")
        payload["sha256"] = _sha256_bytes(body.encode("utf-8"))
        # rewrite with hash
        out_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(
            f"[{label}] {doc_id} done s={elapsed:.1f} schema_ok={schema_stats[fname]['ok']} "
            f"tech={bool(tech_errors[fname])}",
            flush=True,
        )

        if repeat_ids and doc_id in repeat_ids:
            raw2, meta2 = extract_full_schema(
                text,
                model_label=label,
                model_path=model_path,
                transport=transport,
                schema_json=schema_json,
            )
            repeats[doc_id] = {
                "same_raw": raw2 == raw,
                "tech_error_1": tech_errors[fname],
                "tech_error_2": meta2.get("tech_error"),
            }

    pred_hashes = {
        p.name: _sha256_file(p) for p in sorted(pred_dir.glob("*.json"))
    }
    return {
        "label": label,
        "pipeline": pipeline,
        "transport": transport,
        "model_path": str(model_path),
        "model_sha256": _sha256_file(model_path) if model_path.is_file() else None,
        "predictions": predictions,
        "timings": timings,
        "peaks": peaks,
        "schema_stats": schema_stats,
        "import_stats": import_stats,
        "tech_errors": tech_errors,
        "prediction_sha256": pred_hashes,
        "repeatability": repeats,
    }


def decide(phi_score: dict[str, Any], qwen_score: dict[str, Any]) -> dict[str, Any]:
    """Winner order: schema+import → no critical invented → quality DE/EN → runtime/RSS."""

    def side(score: dict[str, Any]) -> dict[str, Any]:
        m = score["metrics_all"]
        return {
            "schema_complete_docs": m["schema_complete_docs"],
            "import_ok_docs": m["import_ok_docs"],
            "n_documents": m["n_documents"],
            "invented_critical": m["invented_critical"],
            "tech_errors": m["tech_errors"],
            "f1": m["f1"],
            "f1_de": score["metrics_de"]["f1"],
            "f1_en": score["metrics_en"]["f1"],
            "perfect_core": m["perfect_core"],
            "hallucination_rate": m["hallucination_rate"],
            "avg_s": m["avg_s_per_cv"],
            "peak_rss_mb_max": m["peak_rss_mb_max"],
        }

    p = side(phi_score)
    q = side(qwen_score)
    n = p["n_documents"]

    def gates(s: dict[str, Any]) -> list[str]:
        fails: list[str] = []
        if s["schema_complete_docs"] < n:
            fails.append("incomplete_schema")
        if s["import_ok_docs"] < n:
            fails.append("import_roundtrip_failed")
        if s["tech_errors"] > 0:
            fails.append("tech_errors")
        if s["invented_critical"] > 0:
            fails.append("critical_invented")
        # Soft quality floors from locked manifest gate (known-CV, not blind).
        if s["f1"] < 0.9:
            fails.append("f1_below_0.9")
        if s["hallucination_rate"] > 0.03:
            fails.append("hallu_above_0.03")
        return fails

    p_fail = gates(p)
    q_fail = gates(q)

    # Hard disqualifiers for "usable production extractor"
    def hard_ok(fails: list[str]) -> bool:
        return not any(
            x in fails
            for x in (
                "incomplete_schema",
                "import_roundtrip_failed",
                "tech_errors",
                "critical_invented",
            )
        )

    decision = "kein Sieger"
    rationale: list[str] = []

    p_hard = hard_ok(p_fail)
    q_hard = hard_ok(q_fail)
    if p_hard and not q_hard:
        decision = "Phi"
        rationale.append("Nur Phi besteht Schema/Import/keine kritischen Erfindungen.")
    elif q_hard and not p_hard:
        decision = "Qwen"
        rationale.append("Nur Qwen besteht Schema/Import/keine kritischen Erfindungen.")
    elif not p_hard and not q_hard:
        decision = "kein Sieger"
        rationale.append("Beide verfehlen Schema/Import/kritische Halluzinations-Gates.")
    else:
        # Both hard-ok: compare quality then cost
        if (q["f1_de"], q["f1_en"], q["f1"], q["perfect_core"]) > (
            p["f1_de"],
            p["f1_en"],
            p["f1"],
            p["perfect_core"],
        ):
            decision = "Qwen"
            rationale.append("Beide hard-ok; Qwen höhere DE/EN/Gesamt-Qualität.")
        elif (p["f1_de"], p["f1_en"], p["f1"], p["perfect_core"]) > (
            q["f1_de"],
            q["f1_en"],
            q["f1"],
            q["perfect_core"],
        ):
            decision = "Phi"
            rationale.append("Beide hard-ok; Phi höhere DE/EN/Gesamt-Qualität.")
        else:
            # Tie on quality → runtime/memory (lower better)
            if (q["avg_s"], q["peak_rss_mb_max"]) < (p["avg_s"], p["peak_rss_mb_max"]):
                decision = "Qwen"
                rationale.append("Qualität gleich; Qwen schneller/leichter.")
            elif (p["avg_s"], p["peak_rss_mb_max"]) < (q["avg_s"], q["peak_rss_mb_max"]):
                decision = "Phi"
                rationale.append("Qualität gleich; Phi schneller/leichter.")
            else:
                decision = "kein Sieger"
                rationale.append("Hard-ok und Metriken unentschieden.")

        # Soft gate miss still noted
        if p_fail or q_fail:
            rationale.append(
                f"Weiche Manifest-Gates: Phi={p_fail or 'ok'}, Qwen={q_fail or 'ok'} "
                "(bekanntes SMOKE-Korpus, kein Blindanspruch)."
            )

    return {
        "decision": decision,
        "rationale": rationale,
        "phi": p,
        "qwen": q,
        "phi_gate_fails": p_fail,
        "qwen_gate_fails": q_fail,
        "production_path_changed": False,
        "note": (
            "Produktiven Modellpfad nicht umgestellt: Wechsel nur wenn Sieger "
            "Import- und Hardware-Gates besteht. Windows-EXE-Import (PR #96) "
            "ist von diesem Modellvergleich getrennt und hier nicht verifiziert."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    if not MANIFEST.is_file():
        print(f"missing {MANIFEST}", file=sys.stderr)
        return 2
    if not PHI_GGUF.is_file():
        print(f"missing Phi GGUF: {PHI_GGUF}", file=sys.stderr)
        return 2
    if not QWEN_GGUF.is_file():
        print(f"missing Qwen GGUF: {QWEN_GGUF}", file=sys.stderr)
        return 2

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest.get("locked") is True
    docs_meta = list(manifest["documents"])
    gt_path = ROOT / manifest["ground_truth"]
    # Load GT only for scoring after predictions are frozen (kept in memory sealed).
    gt_docs = json.loads(gt_path.read_text(encoding="utf-8"))["documents"]
    scorer_sha = _sha256_file(ROOT / "scripts" / "holdout_scorer_v2.py")
    gt_sha = _sha256_file(gt_path)
    manifest_sha = _sha256_file(MANIFEST)

    from core.cv_docpick_import import _schema_json_for_prompt
    from core.cv_extract import extract_text

    schema_json = _schema_json_for_prompt()
    schema_sha = _sha256_bytes(schema_json.encode("utf-8"))

    OUT.mkdir(parents=True, exist_ok=True)
    texts: dict[str, str] = {}
    text_hashes: dict[str, str] = {}
    for meta in docs_meta:
        pdf = ROOT / meta["path"]
        fname = pdf.name
        text = extract_text(pdf) or ""
        texts[fname] = text
        text_hashes[fname] = _sha256_bytes(text.encode("utf-8"))
        (OUT / f"text_{meta['id']}.sha256").write_text(
            text_hashes[fname] + "\n", encoding="utf-8"
        )

    seal_pre = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "comparison_type": "KNOWN_CV_TEST_NOT_BLIND",
        "manifest_id": manifest["manifest_id"],
        "manifest_sha256": manifest_sha,
        "ground_truth_sha256": gt_sha,
        "scorer_sha256": scorer_sha,
        "schema_sha256": schema_sha,
        "shared_text_sha256": text_hashes,
        "models": {
            "phi": {"path": str(PHI_GGUF), "sha256": _sha256_file(PHI_GGUF)},
            "qwen": {"path": str(QWEN_GGUF), "sha256": _sha256_file(QWEN_GGUF)},
        },
        "note": (
            "SMOKE_DE_EN_10_V1 was used in prior Docpick/OSS development. "
            "This is a head-to-head known-CV test, not an independent blind holdout."
        ),
    }
    (OUT / "PHASE_A_SEAL.json").write_text(
        json.dumps(seal_pre, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    # Prefer HTTP for Qwen if the already-running server serves this GGUF.
    qwen_transport = "http" if _http_available(LLM_BASE) else "inprocess"
    phi_transport = "inprocess"

    # Run Qwen first while server is warm; free the HTTP server before Phi
    # so in-process Phi peak RSS is not inflated by an idle Qwen server.
    qwen_side = run_model_side(
        label="qwen35-4b",
        pipeline="DOCPICK_QWEN35_4B",
        model_path=QWEN_GGUF,
        transport=qwen_transport,
        docs_meta=docs_meta,
        texts=texts,
        schema_json=schema_json,
        pred_dir=OUT / "predictions_qwen",
        include_server_in_peak=(qwen_transport == "http"),
        repeat_ids={"DE_01", "EN_01"},
    )
    if qwen_transport == "http":
        # Best-effort stop of local llama.cpp server before Phi in-process.
        try:
            import signal
            import subprocess

            subprocess.run(
                ["pkill", "-f", "llama_cpp.server"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(2)
        except Exception:  # noqa: BLE001
            pass
    phi_side = run_model_side(
        label="phi4-mini",
        pipeline="PHI_FULL_SCHEMA",
        model_path=PHI_GGUF,
        transport=phi_transport,
        docs_meta=docs_meta,
        texts=texts,
        schema_json=schema_json,
        pred_dir=OUT / "predictions_phi",
        include_server_in_peak=False,
        repeat_ids={"DE_01", "EN_01"},
    )

    # Freeze prediction hashes before scoring
    freeze = {
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "qwen_prediction_sha256": qwen_side["prediction_sha256"],
        "phi_prediction_sha256": phi_side["prediction_sha256"],
        "phase_a_seal_sha256": _sha256_file(OUT / "PHASE_A_SEAL.json"),
    }
    (OUT / "PREDICTION_FREEZE.json").write_text(
        json.dumps(freeze, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    qwen_score = _score_side(
        label="qwen35-4b",
        docs_meta=docs_meta,
        gt_docs=gt_docs,
        predictions=qwen_side["predictions"],
        texts=texts,
        timings=qwen_side["timings"],
        peaks=qwen_side["peaks"],
        schema_stats=qwen_side["schema_stats"],
        import_stats=qwen_side["import_stats"],
        tech_errors=qwen_side["tech_errors"],
    )
    phi_score = _score_side(
        label="phi4-mini",
        docs_meta=docs_meta,
        gt_docs=gt_docs,
        predictions=phi_side["predictions"],
        texts=texts,
        timings=phi_side["timings"],
        peaks=phi_side["peaks"],
        schema_stats=phi_side["schema_stats"],
        import_stats=phi_side["import_stats"],
        tech_errors=phi_side["tech_errors"],
    )

    decision = decide(phi_score, qwen_score)
    report = {
        "comparison_type": "KNOWN_CV_TEST_NOT_BLIND",
        "manifest_id": manifest["manifest_id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "seal": seal_pre,
        "freeze": freeze,
        "phi": {
            "transport": phi_side["transport"],
            "repeatability": phi_side["repeatability"],
            "score": {
                "metrics_all": phi_score["metrics_all"],
                "metrics_de": phi_score["metrics_de"],
                "metrics_en": phi_score["metrics_en"],
                "status_counts": phi_score["status_counts"],
                "critical_kinds": phi_score["critical_kinds"],
                "per_document": phi_score["per_document"],
            },
        },
        "qwen": {
            "transport": qwen_side["transport"],
            "repeatability": qwen_side["repeatability"],
            "score": {
                "metrics_all": qwen_score["metrics_all"],
                "metrics_de": qwen_score["metrics_de"],
                "metrics_en": qwen_score["metrics_en"],
                "status_counts": qwen_score["status_counts"],
                "critical_kinds": qwen_score["critical_kinds"],
                "per_document": qwen_score["per_document"],
            },
        },
        "decision": decision,
        "windows_exe_import_verified": False,
        "pr96_packaging_fix_separate": True,
    }
    (OUT / "COMPARE_REPORT.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    # Compact table for humans
    table = {
        "metric": [
            "schema_complete_docs",
            "import_ok_docs",
            "tech_errors",
            "invented_critical",
            "f1_all",
            "f1_de",
            "f1_en",
            "perfect_core",
            "hallucination_rate",
            "missing_count",
            "wrong_count",
            "avg_s_per_cv",
            "peak_rss_mb_max",
        ],
        "phi": [
            decision["phi"]["schema_complete_docs"],
            decision["phi"]["import_ok_docs"],
            decision["phi"]["tech_errors"],
            decision["phi"]["invented_critical"],
            round(decision["phi"]["f1"], 4),
            round(decision["phi"]["f1_de"], 4),
            round(decision["phi"]["f1_en"], 4),
            decision["phi"]["perfect_core"],
            round(decision["phi"]["hallucination_rate"], 4),
            phi_score["status_counts"].get("missing", 0),
            phi_score["status_counts"].get("wrong", 0),
            round(decision["phi"]["avg_s"], 1),
            round(decision["phi"]["peak_rss_mb_max"], 1),
        ],
        "qwen": [
            decision["qwen"]["schema_complete_docs"],
            decision["qwen"]["import_ok_docs"],
            decision["qwen"]["tech_errors"],
            decision["qwen"]["invented_critical"],
            round(decision["qwen"]["f1"], 4),
            round(decision["qwen"]["f1_de"], 4),
            round(decision["qwen"]["f1_en"], 4),
            decision["qwen"]["perfect_core"],
            round(decision["qwen"]["hallucination_rate"], 4),
            qwen_score["status_counts"].get("missing", 0),
            qwen_score["status_counts"].get("wrong", 0),
            round(decision["qwen"]["avg_s"], 1),
            round(decision["qwen"]["peak_rss_mb_max"], 1),
        ],
        "decision": decision["decision"],
        "rationale": decision["rationale"],
    }
    (OUT / "COMPARE_TABLE.json").write_text(
        json.dumps(table, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(table, ensure_ascii=False, indent=2), flush=True)
    print(f"decision={decision['decision']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
