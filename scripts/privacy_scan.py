#!/usr/bin/env python3
"""Scan tracked files for likely personal / local-machine data before commit.

Fictional example.com addresses and placeholder fixture names are allowed.
Real Windows user paths and known leaked CV fingerprints are not.
"""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN = [
    (
        "windows_user_path",
        re.compile(r"(?i)(?:[A-Z]:\\|\\\\)Users\\[A-Za-z0-9._-]+\\"),
    ),
    (
        "unix_home_user",
        re.compile(r"(?i)/(?:home|Users)/[A-Za-z0-9._-]+/(?:Desktop|Documents|Downloads)/"),
    ),
]

# Original leaked fingerprints (must remain detectable if reintroduced).
# Built from parts so casual file reads are less useful as a CV dump.
_FP_PARTS = [
    ("Up", "way", r"\s+Germany"),
    (r"\bZA\s+", "AG", r"\b"),
    ("Fitness", "kaufmann", ""),
    ("Integra", "Well", ""),
    ("Body", "Number1", ""),
    (r"\bFit", "group", r"\b"),
    ("Gemeinschaftsschule", r"\s+", "Erbach"),
    ("EMS-", "Lizenz", ""),
    ("Zumba-", "Trainerlizenz", ""),
    ("Internationaler", r"\s+", "Surfschein"),
    ("Opti", "Office", ""),
    ("ZA:", "EASY", ""),
    ("Up", "way", r"\s+Backoffice"),
    ("Tabellarischer", r"\s+Lebenslauf\s+", r"\d"),
    ("Users[/\\\\]+", "damia", "[/\\\\]"),
]


def _fingerprint_regexes() -> list[re.Pattern[str]]:
    out: list[re.Pattern[str]] = []
    for parts in _FP_PARTS:
        out.append(re.compile("".join(parts), re.I))
    return out


CV_FINGERPRINTS = _fingerprint_regexes()

ALLOW_EMAIL_DOMAINS = {"example.com", "example.org", "example.net", "localhost"}

# RFC 6761 special-use TLDs — safe for fixtures (corp.example, foo.test, …).
_SPECIAL_USE_TLDS = frozenset({"example", "test", "invalid", "localhost"})

# Project fixture convention: example.<ccTLD> (example.de, example.at, …) and
# example.co.uk — fictional mailbox labels, not production contact data.
_EXAMPLE_SLD = re.compile(r"^example\.[a-z0-9.-]+$", re.I)
# Apple asset catalogs use filenames like Icon@2x.png — not email addresses.
_APPLE_SCALE_DOMAIN = re.compile(r"^\dx\.(?:png|jpe?g|gif|webp)$", re.I)


def _email_domain_allowed(domain: str) -> bool:
    d = (domain or "").lower().rstrip(".")
    if not d:
        return False
    if d in ALLOW_EMAIL_DOMAINS:
        return True
    if _APPLE_SCALE_DOMAIN.match(d):
        return True
    if any(d == root or d.endswith("." + root) for root in ALLOW_EMAIL_DOMAINS):
        return True
    # e.g. corp.example / mail.test — not real registrable domains
    tld = d.rsplit(".", 1)[-1]
    if tld in _SPECIAL_USE_TLDS:
        return True
    # Fixture mailboxes used across DE/EN holdout corpora
    if _EXAMPLE_SLD.match(d):
        return True
    return False


EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")

SKIP_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".dll",
    ".pyd",
    ".exe",
    ".whl",
    ".zip",
}

# This script intentionally contains fingerprint fragments.
ALLOWLIST_PATHS = {
    "scripts/privacy_scan.py",
    "docs/privacy-cleanup-audit.md",
}

# Upstream audit snapshots retain original example addresses from MIT/Apache sources.
ALLOWLIST_PREFIXES = (
    "third_party/post-application-audit/",
)

# Flutter/Xcode asset catalogs (Contents.json references *@2x.png etc.)
ALLOWLIST_PATH_GLOBS_EMAIL = (
    ".xcassets/",
)


def tracked_files() -> list[Path]:
    proc = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    )
    out: list[Path] = []
    for raw in proc.stdout.split(b"\0"):
        if not raw:
            continue
        out.append(ROOT / raw.decode("utf-8", errors="replace"))
    return out


def scan_text(path: Path, text: str) -> list[str]:
    hits: list[str] = []
    rel = path.relative_to(ROOT).as_posix()
    if rel in ALLOWLIST_PATHS or any(rel.startswith(p) for p in ALLOWLIST_PREFIXES):
        # Still forbid absolute Windows user paths even in docs/scripts.
        for name, rx in FORBIDDEN:
            if rx.search(text) and "damia" in text.lower():
                hits.append(f"{rel}: pattern {name}")
        return hits
    for name, rx in FORBIDDEN:
        if rx.search(text):
            hits.append(f"{rel}: pattern {name}")
    for rx in CV_FINGERPRINTS:
        if rx.search(text):
            hits.append(f"{rel}: CV fingerprint match")
            break
    for m in EMAIL_RE.finditer(text):
        domain = m.group(1).lower()
        if any(token in rel for token in ALLOWLIST_PATH_GLOBS_EMAIL):
            continue
        if not _email_domain_allowed(domain):
            hits.append(f"{rel}: non-example email domain @{domain}")
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all-files", action="store_true", help="Also scan untracked under repo")
    args = parser.parse_args()

    files = tracked_files()
    if args.all_files:
        for p in ROOT.rglob("*"):
            if p.is_file() and ".git" not in p.parts and ".venv" not in p.parts:
                files.append(p)

    hits: list[str] = []
    for path in files:
        if not path.is_file():
            continue
        if path.suffix.lower() in SKIP_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        hits.extend(scan_text(path, text))

    if hits:
        print("Privacy scan FAILED:")
        for h in hits:
            print(" -", h)
        return 1
    print("Privacy scan OK (no suspicious personal data in tracked files).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
