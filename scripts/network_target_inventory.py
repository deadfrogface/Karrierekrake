"""Static inventory of outbound network targets in the *packaged* code (T07.06).

Scans the first-party packages that PyInstaller collects
(``packaging/kk_content_policy.ALLOWED_FIRST_PARTY_PREFIXES`` minus
``EXCLUDED_FIRST_PARTY_MODULES``) plus the JobSpy scrapers Karrierekrake uses
(Indeed, LinkedIn) for literal URL hosts and quoted mail-server host names.
Reads files only; performs no network access.

Usage: python scripts/network_target_inventory.py [--json]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
URL_RE = re.compile(r"\b(?:https?|wss?)://([A-Za-z0-9][A-Za-z0-9.\-]*[A-Za-z0-9])(?::\d+)?")
MAIL_HOST_RE = re.compile(
    r"""["']((?:imap|smtp|pop3?)[a-z0-9\-]*\.[a-z0-9.\-]+\.[a-z]{2,}|outlook\.office365\.com)["']""")
# Third-party modules shipped in the package whose targets Karrierekrake triggers.
JOBSPY_MODULES = ("jobspy/indeed", "jobspy/linkedin", "jobspy/util.py")


def _policy():
    path = ROOT / "packaging" / "kk_content_policy.py"
    spec = importlib.util.spec_from_file_location("kk_content_policy_inv", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _excluded(rel: str, excluded: tuple[str, ...]) -> bool:
    mod = rel[:-3].replace("/", ".")
    return any(mod == e or mod.startswith(e + ".") for e in excluded)


def _scan_file(path: Path, label: str, hosts: dict[str, set[str]]) -> None:
    text = path.read_text(encoding="utf-8", errors="ignore")
    for match in URL_RE.finditer(text):
        hosts[match.group(1).lower().rstrip(".")].add(label)
    for match in MAIL_HOST_RE.finditer(text):
        hosts[match.group(1).lower()].add(label)


def scan(root: Path = ROOT) -> dict[str, list[str]]:
    policy = _policy()
    hosts: dict[str, set[str]] = defaultdict(set)
    for prefix in policy.ALLOWED_FIRST_PARTY_PREFIXES:
        base = root / prefix
        for path in sorted(base.rglob("*.py")) if base.is_dir() else []:
            rel = path.relative_to(root).as_posix()
            if _excluded(rel, policy.EXCLUDED_FIRST_PARTY_MODULES):
                continue
            _scan_file(path, rel, hosts)
    spec = importlib.util.find_spec("jobspy")
    if spec and spec.origin:
        site = Path(spec.origin).parent.parent
        for rel in JOBSPY_MODULES:
            target = site / rel
            files = [target] if target.is_file() else sorted(target.rglob("*.py"))
            for path in files:
                _scan_file(path, "third_party:" + path.relative_to(site).as_posix(), hosts)
    return {host: sorted(labels) for host, labels in sorted(hosts.items())}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = scan()
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        for host, labels in result.items():
            print(f"{host}\t{len(labels)}\t{labels[0]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
