#!/usr/bin/env python3
"""Benchmark document backends: CURRENT vs pymupdf4llm vs docling.

Measures downstream Sollwerte field quality (not text aesthetics).
Optional deps are skipped when unavailable.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from core.cv_document_backends import list_backends  # noqa: E402
from core.cv_metrics import aggregate, classify_failures  # noqa: E402
from core.cv_parser import parse_cv_text  # noqa: E402
from run_cv_sollwerte_corpus import CORPUS, PDFS, SOLL, parse_sollwerte  # noqa: E402


def run_backend(name: str) -> dict:
    from core.cv_document_backends import extract_with_backend

    soll = parse_sollwerte(SOLL)
    docs = []
    t0 = time.perf_counter()
    for pdf in PDFS:
        path = CORPUS / pdf
        exp = soll.get(pdf)
        if not path.is_file() or not exp:
            continue
        started = time.perf_counter()
        try:
            text = extract_with_backend(path, name)
        except Exception as exc:  # noqa: BLE001
            return {"backend": name, "error": f"{type(exc).__name__}: {exc}"}
        parsed = parse_cv_text(text)
        dm = classify_failures(
            pdf, parsed, exp, phi_involved=False, extractor_path=name
        )
        dm.elapsed_s = time.perf_counter() - started
        docs.append(dm)
    metrics = aggregate(docs)
    metrics["backend"] = name
    metrics["wall_s"] = time.perf_counter() - t0
    return metrics


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--json",
        type=Path,
        default=ROOT / "artifacts" / "phi_extraction" / "document_backend_benchmark.json",
    )
    args = ap.parse_args()
    availability = list_backends()
    report = {"availability": availability, "results": {}}
    for name, meta in availability.items():
        if not meta.get("available"):
            report["results"][name] = {"skipped": True, "reason": meta.get("detail")}
            print(f"SKIP {name}: {meta.get('detail')}")
            continue
        m = run_backend(name)
        report["results"][name] = m
        if "error" in m:
            print(f"FAIL {name}: {m['error']}")
        else:
            c = m["counts"]
            print(
                f"{name}: perfect={m['perfect_documents']}/{m['documents']} "
                f"acc={m['field_accuracy']:.4f} F1={m['f1']:.4f} "
                f"ok={c['correct']} wrong={c['wrong']} miss={c['missing']} "
                f"hallu={c['hallucinated']} t={m['wall_s']:.1f}s"
            )
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
