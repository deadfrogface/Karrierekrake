#!/usr/bin/env python3
"""POST-ANALYSIS offline Phi Language-only benchmark.

Experimental only — does NOT wire into import_cv / production.

Phi receives only the detected language/licence section block (+ few neighbour
lines), never the full CV. Outputs strict languages+licences JSON.

Usage:
  python scripts/run_phi_language_only_benchmark.py
  python scripts/run_phi_language_only_benchmark.py --limit 10 --repeat 3
"""

from __future__ import annotations

import argparse
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

from holdout_scorer_v2 import match_language_pairs, pred_view  # noqa: E402

HOLDOUT = ROOT / "tests" / "final_holdout"
PDF_DIR = HOLDOUT / "phase_a_pdfs"
GT_PATH = HOLDOUT / "phase_b_solutions" / "expected_results.json"
OUT = ROOT / "artifacts" / "final_holdout" / "post_analysis_language" / "phi_language_only"
MODEL_CANDIDATES = [
    Path(os.sep) / "tmp" / "karrierekrake-models" / "phi4-mini" / "microsoft_Phi-4-mini-instruct-Q4_K_M.gguf",
    Path(os.environ.get("KARRIEREKRAKE_PHI_MODEL", "")),
]

SYSTEM_PROMPT = """You extract ONLY human languages and driving licences from the given CV fragment.
Rules:
- Only values explicitly present in the fragment.
- Never invent a language or level.
- Never infer a CEFR level that is not written.
- Programming languages (Python, Java, R, SQL, C++, …) are NOT human languages.
- A bare C1 next to Führerschein/Driving licence is a licence class, not a language level.
- Evidence must be a verbatim substring of the fragment.
- If unsure, use null for level or omit the item.
- Return ONLY JSON matching the schema. No other profile fields.
"""

SCHEMA_HINT = """{
  "languages": [{"name": "...", "level": null, "evidence": "..."}],
  "licences": [{"class": "...", "evidence": "..."}]
}"""


def _peak_rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def _extract_language_block(text: str) -> str:
    """DET section split: return languages body + heading context (offline)."""
    from core.cv_sections import is_heading, split_named_sections

    lines = text.splitlines()
    heading_line = ""
    for line in lines:
        if is_heading(line.strip()) == "languages":
            heading_line = line.strip()
            break
    secs = split_named_sections(text)
    body = secs.get("languages") or ""
    if not body and not heading_line:
        # Fallback: grab lines around language-ish headings for Phi input only.
        buf: list[str] = []
        capture = False
        for line in lines:
            low = line.strip().lower()
            if re.search(r"\b(sprachen|languages|sprachkenntnisse|fremdsprachen)\b", low) and len(low) < 80:
                capture = True
                buf.append(line.strip())
                continue
            if capture and is_heading(line.strip()) and is_heading(line.strip()) != "languages":
                break
            if capture:
                buf.append(line.strip())
        return "\n".join(buf[:40]).strip()
    parts = [heading_line, body] if heading_line else [body]
    # Few neighbour lines after block (licence sometimes follows)
    return "\n".join(p for p in parts if p).strip()


def _load_model(path: Path):
    from llama_cpp import Llama

    t0 = time.perf_counter()
    llm = Llama(
        model_path=str(path),
        n_ctx=2048,
        n_threads=max(2, (os.cpu_count() or 2) // 2),
        n_batch=256,
        verbose=False,
    )
    load_s = time.perf_counter() - t0
    return llm, load_s


def _phi_extract(llm, block: str) -> tuple[dict[str, Any], float, bool]:
    user = (
        f"Fragment:\n```\n{block}\n```\n\n"
        f"Return JSON only, schema:\n{SCHEMA_HINT}"
    )
    t0 = time.perf_counter()
    invalid = False
    try:
        out = llm.create_chat_completion(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user},
            ],
            temperature=0.0,
            max_tokens=256,
        )
        content = out["choices"][0]["message"]["content"]
    except Exception as exc:  # noqa: BLE001
        return {"languages": [], "licences": [], "error": str(exc)}, time.perf_counter() - t0, True

    elapsed = time.perf_counter() - t0
    # Extract JSON object
    m = re.search(r"\{.*\}", content or "", re.S)
    if not m:
        return {"languages": [], "licences": [], "raw": content}, elapsed, True
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return {"languages": [], "licences": [], "raw": content}, elapsed, True
    if not isinstance(data, dict):
        return {"languages": [], "licences": [], "raw": content}, elapsed, True
    langs = data.get("languages") if isinstance(data.get("languages"), list) else []
    lics = data.get("licences") if isinstance(data.get("licences"), list) else []
    # Evidence must appear in block
    clean_langs = []
    for item in langs:
        if not isinstance(item, dict):
            invalid = True
            continue
        name = str(item.get("name") or "").strip()
        evidence = str(item.get("evidence") or "").strip()
        if not name:
            continue
        if evidence and evidence not in block:
            invalid = True
            continue
        if not evidence:
            # require name at least appears
            if name.lower() not in block.lower():
                invalid = True
                continue
        level = item.get("level")
        if level is not None:
            level = str(level).strip() or None
        clean_langs.append({"name": name, "level": level, "evidence": evidence or name})
    clean_lics = []
    for item in lics:
        if not isinstance(item, dict):
            invalid = True
            continue
        cls = str(item.get("class") or "").strip().upper()
        evidence = str(item.get("evidence") or "").strip()
        if not cls:
            continue
        if evidence and evidence not in block:
            invalid = True
            continue
        clean_lics.append({"class": cls, "evidence": evidence or cls})
    return {"languages": clean_langs, "licences": clean_lics}, elapsed, invalid


def _to_pred(phi: dict[str, Any]) -> dict[str, Any]:
    langs = [
        {"language": x["name"], "level": x.get("level") or "", "source": "phi_language_only"}
        for x in phi.get("languages") or []
    ]
    lics = [{"value": x["class"], "source": "phi_language_only"} for x in phi.get("licences") or []]
    return {"languages": langs, "driving_license": lics, "personal": {}}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--repeat", type=int, default=3, help="Repeatability runs on first N docs")
    ap.add_argument("--repeat-docs", type=int, default=20)
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    model_path = next((p for p in MODEL_CANDIDATES if p and p.is_file()), None)
    if model_path is None:
        result = {
            "protocol": "POST_ANALYSIS_PHI_LANGUAGE_ONLY_V1",
            "status": "MODEL_UNAVAILABLE",
            "label": "POST-ANALYSIS",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "note": "No Phi GGUF found; Phi not integrated. DET comparison stands.",
        }
        (OUT.parent / "phi_language_results.json").write_text(
            json.dumps(result, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(result, indent=2))
        return

    from core.cv_extract import extract_text

    gt_docs = json.loads(GT_PATH.read_text(encoding="utf-8"))["documents"]
    pdfs = sorted(PDF_DIR.glob("FH_*.pdf"))[: args.limit]

    print(f"Loading model {model_path} …", flush=True)
    peak0 = _peak_rss_mb()
    llm, load_s = _load_model(model_path)
    peak_load = _peak_rss_mb()

    per_doc: list[dict[str, Any]] = []
    tp = fp = fn = 0
    lic_tp = lic_fp = lic_fn = 0
    invalid_n = 0
    hallu = 0
    timings: list[float] = []

    for pdf in pdfs:
        fname = pdf.name
        text = extract_text(pdf)
        block = _extract_language_block(text)
        phi_out, elapsed, invalid = _phi_extract(llm, block)
        timings.append(elapsed)
        if invalid:
            invalid_n += 1
        pred = _to_pred(phi_out)
        (OUT / f"{pdf.stem}.json").write_text(
            json.dumps(
                {
                    "document_id": pdf.stem,
                    "block": block,
                    "phi": phi_out,
                    "prediction": pred,
                    "timing_s": elapsed,
                    "invalid": invalid,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        g = gt_docs[fname]
        rows, stats = match_language_pairs(g.get("languages") or [], pred.get("languages") or [])
        tp += stats["entry_tp"]
        fp += stats["entry_fp"]
        fn += stats["entry_fn"]
        hallu += sum(1 for r in rows if r.status == "hallucinated")
        exp_lic = {str(x).upper() for x in (g.get("licenses") or []) if str(x).strip()}
        act_lic = {str(x.get("value") or "").upper() for x in pred.get("driving_license") or []}
        act_lic.discard("")
        lic_tp += len(exp_lic & act_lic)
        lic_fp += len(act_lic - exp_lic)
        lic_fn += len(exp_lic - act_lic)
        per_doc.append(
            {
                "document": fname,
                "timing_s": round(elapsed, 3),
                "n_lang": len(pred["languages"]),
                "invalid": invalid,
                "lang_tp": stats["entry_tp"],
                "lang_fp": stats["entry_fp"],
                "lang_fn": stats["entry_fn"],
            }
        )

    def f1(t, f_p, f_n):
        prec = t / (t + f_p) if (t + f_p) else 0.0
        rec = t / (t + f_n) if (t + f_n) else 0.0
        return prec, rec, (2 * prec * rec / (prec + rec) if (prec + rec) else 0.0)

    l_prec, l_rec, l_f1 = f1(tp, fp, fn)
    lic_prec, lic_rec, lic_f1 = f1(lic_tp, lic_fp, lic_fn)

    # Repeatability on first N docs
    repeat_docs = pdfs[: args.repeat_docs]
    repeat_rows: list[dict[str, Any]] = []
    for pdf in repeat_docs:
        text = extract_text(pdf)
        block = _extract_language_block(text)
        runs = []
        for _ in range(args.repeat):
            phi_out, _, invalid = _phi_extract(llm, block)
            runs.append({"phi": phi_out, "invalid": invalid})
        identical = all(json.dumps(r["phi"], sort_keys=True) == json.dumps(runs[0]["phi"], sort_keys=True) for r in runs)
        repeat_rows.append({"document": pdf.name, "identical": identical, "runs": len(runs)})

    peak = max(peak_load, _peak_rss_mb())
    results = {
        "protocol": "POST_ANALYSIS_PHI_LANGUAGE_ONLY_V1",
        "label": "POST-ANALYSIS",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model_path": str(model_path),
        "model_load_s": round(load_s, 3),
        "n_documents": len(pdfs),
        "language_precision": round(l_prec, 4),
        "language_recall": round(l_rec, 4),
        "language_f1": round(l_f1, 4),
        "licence_precision": round(lic_prec, 4),
        "licence_recall": round(lic_rec, 4),
        "licence_f1": round(lic_f1, 4),
        "language_hallucination_count": hallu,
        "invalid_output_rate": round(invalid_n / max(1, len(pdfs)), 4),
        "timing_s_mean": round(sum(timings) / max(1, len(timings)), 4),
        "timing_s_total": round(sum(timings), 3),
        "peak_rss_mb": round(peak, 2),
        "peak_rss_mb_before_load": round(peak0, 2),
        "production_integration": False,
        "per_document": per_doc,
    }
    (OUT.parent / "phi_language_results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (OUT.parent / "phi_repeatability.json").write_text(
        json.dumps(
            {
                "label": "POST-ANALYSIS",
                "repeat": args.repeat,
                "n_docs": len(repeat_rows),
                "identical_rate": round(
                    sum(1 for r in repeat_rows if r["identical"]) / max(1, len(repeat_rows)), 4
                ),
                "documents": repeat_rows,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "language_f1": results["language_f1"],
        "licence_f1": results["licence_f1"],
        "invalid_output_rate": results["invalid_output_rate"],
        "timing_s_mean": results["timing_s_mean"],
        "peak_rss_mb": results["peak_rss_mb"],
        "model_load_s": results["model_load_s"],
        "identical_rate": sum(1 for r in repeat_rows if r["identical"]) / max(1, len(repeat_rows)),
    }, indent=2))


if __name__ == "__main__":
    main()
