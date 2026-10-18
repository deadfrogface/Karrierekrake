"""packaging/license_evidence.json must describe the versions that are actually pinned.

The SBOM exporter (scripts/distribution_license.py) only accepts a license file
whose package name, exact version and SHA256 match an evidence entry. An entry
for a version that is no longer pinned is therefore dead evidence. This test
ties the evidence to constraints-runtime.txt (the pin file the build installs
with ``-c``) and requires evidence for the JobSpy network stack.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "packaging" / "license_evidence.json"
CONSTRAINTS = ROOT / "constraints-runtime.txt"

# python-jobspy and the distributions on its HTTP path (requests session for
# Indeed/LinkedIn, curl_cffi imported by jobspy.util) plus its HTML dependency.
JOBSPY_NETWORK_STACK = {
    "python-jobspy",
    "curl-cffi",
    "cffi",
    "requests",
    "urllib3",
    "certifi",
    "idna",
    "charset-normalizer",
    "markdownify",
}


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).casefold()


def _pins() -> dict[str, str]:
    pins: dict[str, str] = {}
    for raw in CONSTRAINTS.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        match = re.fullmatch(r"([A-Za-z0-9_.\-]+)==([^\s;]+)", line)
        if match:
            pins[_norm(match.group(1))] = match.group(2)
    return pins


def _entries() -> list[dict]:
    return json.loads(EVIDENCE.read_text(encoding="utf-8"))["entries"]


def test_constraints_parse_contains_jobspy_pin():
    # Guard against a parser that silently returns nothing.
    assert "python-jobspy" in _pins()


def test_license_evidence_versions_match_runtime_pins():
    pins = _pins()
    mismatches = [
        f"{entry['name']}: evidence {entry['version']} != pinned {pins[_norm(entry['name'])]}"
        for entry in _entries()
        if _norm(entry["name"]) in pins and pins[_norm(entry["name"])] != entry["version"]
    ]
    assert mismatches == []


def test_license_evidence_entries_are_pinned():
    pins = _pins()
    unpinned = [entry["name"] for entry in _entries() if _norm(entry["name"]) not in pins]
    assert unpinned == []


def test_jobspy_network_stack_has_evidence():
    present = {_norm(entry["name"]) for entry in _entries()}
    assert sorted(JOBSPY_NETWORK_STACK - present) == []


def test_license_evidence_entries_are_unique():
    names = [_norm(entry["name"]) for entry in _entries()]
    assert len(names) == len(set(names))


@pytest.mark.parametrize("entry", _entries(), ids=lambda e: e["name"])
def test_installed_license_file_matches_evidence(entry):
    """Where the pinned version is installed, the recorded file hash must be real."""
    try:
        dist = importlib.metadata.distribution(entry["name"])
    except importlib.metadata.PackageNotFoundError:
        pytest.skip(f"{entry['name']} not installed")
    if dist.version != entry["version"]:
        pytest.skip(f"{entry['name']} {dist.version} installed, evidence is {entry['version']}")
    digests = [
        hashlib.sha256(Path(dist.locate_file(file)).read_bytes()).hexdigest()
        for file in dist.files or ()
        if Path(str(file)).name == entry["filename"]
    ]
    assert entry["sha256"] in digests
