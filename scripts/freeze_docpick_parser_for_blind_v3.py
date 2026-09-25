#!/usr/bin/env python3
"""Freeze Docpick parser/model/config/scorer hashes for Blind DE/EN v3.

Does NOT run extraction. Writes tests/docpick_blind_de_en_v3/PARSER_FREEZE.json.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests" / "docpick_blind_de_en_v3"

FILES = [
    "core/cv_docpick_import.py",
    "core/cv_extract_confirmation.py",
    "core/cv_parser.py",
    "core/cover_letter.py",
    "desktop/services/profile_merge.py",
]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _git_head() -> str:
    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip()
        )
    except Exception:  # noqa: BLE001
        return "UNKNOWN"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    # Locate scorer module without importing GT
    scorer_candidates = [
        ROOT / "scripts" / "run_docpick_round8_sealed_score_v3_1.py",
        ROOT / "core" / "cv_metrics.py",
    ]
    scorer_hashes = {
        str(p.relative_to(ROOT)): _sha256(p) for p in scorer_candidates if p.is_file()
    }
    file_hashes = {
        rel: _sha256(ROOT / rel) for rel in FILES if (ROOT / rel).is_file()
    }
    freeze = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "test_type": "DOCPICK_BLIND_DE_EN_V3_PARSER_FREEZE",
        "commit": _git_head(),
        "model": {
            "id": "Qwen/Qwen3.5-4B",
            "artifact": "Qwen3.5-4B-Q4_K_M.gguf",
            "serving": "llama.cpp OpenAI-compatible server",
        },
        "scorer": {
            "metric": "COMPLETE_GT_ONLY_V3_1_DATE_NORM",
            "note": "Scorer must not change to raise F1; hashes recorded for integrity.",
            "file_sha256": scorer_hashes,
        },
        "parser_file_sha256": file_hashes,
        "peak_rss_gate_bytes": 3_300_000_000,
        "laptop_ram_gate": "OFFEN – Messung ausgesetzt",
        "det_fallback": False,
        "disclaimer": (
            "Freeze for upcoming unseen ≥50 DE/EN blind. "
            "Round8 F1 0.999 is post-analysis on known CVs only. "
            "NV3 frozen blind F1 0.980 remains binding until v3 Phase B."
        ),
        "blind_corpus_ready": False,
        "blocker": (
            "Need PHASE_A_PDFS.zip (≥50 unseen DE/EN) + later PHASE_B_SOLUTIONS.zip"
        ),
    }
    out = OUT / "PARSER_FREEZE.json"
    out.write_text(json.dumps(freeze, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(freeze, indent=2))
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
