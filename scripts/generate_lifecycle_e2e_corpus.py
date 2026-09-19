#!/usr/bin/env python3
"""Generate versioned synthetic lifecycle E2E corpora (PR33).

No real inbox data. Deterministic seeds. Writes:
  tests/fixtures/lifecycle_e2e/*.json + manifest.json
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.lifecycle_e2e import FACTORY_SEED, SCHEMA_VERSION  # noqa: E402
from tests.lifecycle_e2e.factory import (  # noqa: E402
    iter_calendar_cases,
    iter_full_lifecycles,
    iter_injection_mails,
    iter_recruiting_mails,
    iter_status_transitions,
)
from tests.lifecycle_e2e.schema import schema_meta  # noqa: E402

OUT = ROOT / "tests" / "fixtures" / "lifecycle_e2e"


def _write(name: str, items: list[dict]) -> Path:
    payload = {
        **schema_meta(),
        "factory_seed": FACTORY_SEED,
        "count": len(items),
        "items": items,
    }
    path = OUT / name
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    files = {
        "recruiting_mails.json": list(iter_recruiting_mails(500)),
        "injection_mails.json": list(iter_injection_mails(75)),
        "status_transitions.json": list(iter_status_transitions(300)),
        "calendar_cases.json": list(iter_calendar_cases(200)),
        "full_lifecycles.json": list(iter_full_lifecycles(50)),
    }
    hashes: dict[str, str] = {}
    counts: dict[str, int] = {}
    for name, items in files.items():
        path = _write(name, items)
        hashes[name] = _sha(path)
        counts[name] = len(items)
        print(f"wrote {name}: {len(items)}")

    # Reference existing corpora (not duplicated).
    assoc = ROOT / "tests" / "fixtures" / "association" / "competing_application_corpus.json"
    replies = ROOT / "tests" / "fixtures" / "replies" / "reply_safety_corpus.json"
    assoc_n = len(json.loads(assoc.read_text(encoding="utf-8")).get("scenarios") or [])
    reply_n = len(json.loads(replies.read_text(encoding="utf-8")).get("scenarios") or [])
    hashes["association/competing_application_corpus.json"] = _sha(assoc)
    hashes["replies/reply_safety_corpus.json"] = _sha(replies)

    manifest = {
        **schema_meta(),
        "factory_seed": FACTORY_SEED,
        "schema_version": SCHEMA_VERSION,
        "counts": {
            "recruiting_mails": counts["recruiting_mails.json"],
            "injection_mails": counts["injection_mails.json"],
            "status_transitions": counts["status_transitions.json"],
            "calendar_cases": counts["calendar_cases.json"],
            "full_lifecycles": counts["full_lifecycles.json"],
            "association_cases": assoc_n,
            "reply_cases": reply_n,
        },
        "hashes": hashes,
        "minimums": {
            "recruiting_mails": 500,
            "association_cases": 250,
            "status_transitions": 300,
            "calendar_cases": 200,
            "reply_cases": 150,
            "injection_mails": 75,
            "full_lifecycles": 50,
        },
    }
    man_path = OUT / "manifest.json"
    man_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"manifest: {man_path}")
    for key, need in manifest["minimums"].items():
        got = manifest["counts"][key]
        if got < need:
            raise SystemExit(f"corpus shortfall {key}: {got} < {need}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
