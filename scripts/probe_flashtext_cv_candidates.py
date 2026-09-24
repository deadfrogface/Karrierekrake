#!/usr/bin/env python3
"""FlashText candidate probe for known software/skills — diagnostic only.

Does NOT write into the productive import path. Measures recall extras,
false extras, and timing vs Docpick-only predictions (Round3 seal).
Negated / aspired / job-ad-only mentions are filtered.
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from flashtext import KeywordProcessor  # noqa: E402

from core.cv_parser import _KNOWN_SOFTWARE_TOKENS  # noqa: E402

# Small general lexicon (not document-specific). Unknown skills stay with LLM.
_EXTRA_SKILLS = (
    "projektmanagement",
    "kundenkommunikation",
    "disposition",
    "qualitätsprüfung",
    "qualitätssicherung",
    "schichtübergabe",
    "instandhaltung",
    "bestandsprüfung",
    "montageplanung",
    "reporting",
    "stakeholder-kommunikation",
    "prozessüberwachung",
)

_NEGATION = re.compile(
    r"(?i)\b("
    r"keine|kein|ohne|nicht|no|without|lack(?:s|ing)?|aspir(?:e|ing)|"
    r"wünsch|wunsch|lernen|learn(?:ing)?|interess(?:e|iert)|desired|"
    r"job\s*ad|stellenanzeige|anforder"
    r")\b"
)


def _context_ok(text: str, start: int, end: int) -> bool:
    window = text[max(0, start - 40) : end + 40]
    return not bool(_NEGATION.search(window))


def main() -> int:
    kp = KeywordProcessor(case_sensitive=False)
    for tok in sorted(set(_KNOWN_SOFTWARE_TOKENS) | set(_EXTRA_SKILLS), key=len, reverse=True):
        kp.add_keyword(tok)

    seal = json.loads(
        (
            ROOT
            / "tests/docpick_qwen35/regression_known_cvs_round3/PHASE_A_EXTRACTION_SEAL.json"
        ).read_text(encoding="utf-8")
    )
    pred_dir = ROOT / "tests/docpick_qwen35/regression_known_cvs_round3/frozen_predictions"

    t0 = time.perf_counter()
    n_docs = 0
    extra_software = 0
    extra_skills = 0
    false_extra = 0  # negated context
    spans = 0
    for meta in seal["predictions"]:
        pdf = ROOT / meta["pdf"]
        if not pdf.is_file():
            continue
        try:
            from core.cv_docpick_import import extract_cv_text

            text = extract_cv_text(pdf)
        except Exception:
            continue
        n_docs += 1
        matches = kp.extract_keywords(text, span_info=True)
        pred = json.loads(
            (pred_dir / f"{meta['corpus_id']}__{meta['id']}.json").read_text(
                encoding="utf-8"
            )
        )
        have_soft = {s.lower() for s in (pred.get("software") or [])}
        have_skill = {s.lower() for s in (pred.get("skills") or [])}
        for kw, start, end in matches:
            spans += 1
            if not _context_ok(text, start, end):
                false_extra += 1
                continue
            low = kw.lower()
            if low in _KNOWN_SOFTWARE_TOKENS or any(
                low == t or t in low for t in _KNOWN_SOFTWARE_TOKENS
            ):
                if low not in have_soft and not any(low in h for h in have_soft):
                    extra_software += 1
            else:
                if low not in have_skill and not any(low in h for h in have_skill):
                    extra_skills += 1
    elapsed = time.perf_counter() - t0
    report = {
        "tool": "flashtext",
        "n_documents": n_docs,
        "keyword_hits_with_span": spans,
        "extra_software_vs_round3_pred": extra_software,
        "extra_skills_vs_round3_pred": extra_skills,
        "rejected_negated_or_aspired": false_extra,
        "wall_s": round(elapsed, 3),
        "decision": "REJECT",
        "reason": (
            "Candidates-only probe: extras are unvalidated against GT and do not "
            "prove net F1 gain. No productive merge without a controlled A/B on "
            "sealed preds. Short/ambiguous tokens remain a risk."
        ),
    }
    out = ROOT / "artifacts" / "flashtext_probe_round3.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
