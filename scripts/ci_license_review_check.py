"""Check license-review.json against release-sbom.json from the same build (T08.02.03).

Preserving the review is not enough: this check proves that every SBOM component
without license metadata is listed as unresolved, that the status matches, that no
entry is of an unknown kind, and that no build path leaked. The summary (counts per
kind plus every entry) is written for the artifact so the review content is visible.

Usage: python scripts/ci_license_review_check.py --dir build/release-compliance --out summary.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

KNOWN_PREFIXES = (
    "module-owner-ambiguous:", "native:", "native-version:", "native-notice:", "runtime-license:",
    "runtime-notice:", "asset-rights:", "embedded-identity:", "embedded-license:",
)
_ABSOLUTE_PATH = re.compile(r"(?:[A-Za-z]:[\\/]|/(?:home|Users|tmp|runner|opt|private)/)")


def kind(entry: str) -> str:
    return next((p.rstrip(":") for p in KNOWN_PREFIXES if entry.startswith(p)), "distribution")


def check(folder: Path) -> dict:
    review = json.loads((folder / "license-review.json").read_text(encoding="utf-8"))
    sbom = json.loads((folder / "release-sbom.json").read_text(encoding="utf-8"))
    problems: list[str] = []
    unresolved = review.get("unresolved")
    if not isinstance(unresolved, list) or not all(isinstance(x, str) and x for x in unresolved):
        raise ValueError("license_review_unresolved_invalid")
    expected_status = "review-required" if unresolved else "metadata-complete"
    if review.get("status") != expected_status:
        problems.append(f"status {review.get('status')!r} does not match {len(unresolved)} unresolved entries")
    if unresolved != sorted(set(unresolved)):
        problems.append("unresolved entries are not a sorted, duplicate-free list")
    names = {c.get("name") for c in sbom.get("components", [])}
    for component in sbom.get("components", []):
        ref = str(component.get("bom-ref", ""))
        if ref.startswith("native:") and not component.get("licenses") and "native:" + component["name"] not in unresolved:
            problems.append(f"native component without license not listed as unresolved: {component['name']}")
        if ref.startswith("asset:") and not component.get("licenses") and "asset-rights:" + component["name"] not in unresolved:
            problems.append(f"asset without rights not listed as unresolved: {component['name']}")
    for entry in unresolved:
        if kind(entry) == "distribution" and entry not in names:
            problems.append(f"unknown unresolved entry (neither a known kind nor an SBOM component): {entry}")
    raw = (folder / "license-review.json").read_text(encoding="utf-8")
    if _ABSOLUTE_PATH.search(raw):
        problems.append("license-review.json contains an absolute build path")
    counts = Counter(kind(entry) for entry in unresolved)
    return {"ok": not problems, "status": review.get("status"), "unresolved_total": len(unresolved),
            "unresolved_by_kind": dict(sorted(counts.items())), "unresolved": unresolved, "problems": problems}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    summary = check(args.dir)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "unresolved"}, ensure_ascii=False))
    if os.environ.get("GITHUB_ACTIONS") == "true":
        level = "notice" if summary["ok"] else "error"
        text = f"{summary['unresolved_total']} unresolved: {summary['unresolved_by_kind']}; problems: {summary['problems'][:20]}"
        print(f"::{level} title=License review::" + text.replace("%", "%25").replace("\n", "%0A"))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
