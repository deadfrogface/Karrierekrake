"""packaging/license_evidence.json must describe the versions that are actually pinned.

The SBOM exporter (scripts/distribution_license.py) only accepts a license file
whose package name, exact version and SHA256 match an evidence entry. An entry
for a version that is no longer pinned is therefore dead evidence. This test
ties the evidence to constraints-runtime.txt (the pin file the build installs
with ``-c``) and requires evidence for the search network stack.
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

# The distributions on the HTTP path of our own Indeed / LinkedIn clients (requests session).
SEARCH_NETWORK_STACK = {
    "requests",
    "urllib3",
    "certifi",
    "idna",
    "charset-normalizer",
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


def test_constraints_parse_contains_requests_pin():
    # Guard against a parser that silently returns nothing.
    assert "requests" in _pins()


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


def test_search_network_stack_has_evidence():
    present = {_norm(entry["name"]) for entry in _entries()}
    assert sorted(SEARCH_NETWORK_STACK - present) == []


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
    # Exact digests only: the reference file or a digest recorded for a
    # platform wheel (same text, other bytes, e.g. CRLF on win_amd64).
    accepted = {entry["sha256"], *entry.get("platform_sha256", {}).values()}
    assert accepted & set(digests), (digests, sorted(accepted))


# Digests of the LICENSE file in the official win_amd64 wheels (pip download
# --platform win_amd64 --python-version 3.12, 18.10.2026): same text as the
# reference digest, CRLF line ends. Unit-test shards run on Windows.
WIN_AMD64_LICENSE_SHA256 = {
    "charset-normalizer": "18577485d3704f1a479ded8e573c0976cfed315fd2fd17983fa988da4c2f70d1",
}


def test_windows_wheel_license_digests_are_recorded():
    by_name = {_norm(entry["name"]): entry for entry in _entries()}
    missing = {
        name: digest
        for name, digest in WIN_AMD64_LICENSE_SHA256.items()
        if by_name[name].get("platform_sha256", {}).get("win_amd64") != digest
    }
    assert missing == {}


def test_platform_digests_are_well_formed():
    for entry in _entries():
        variants = entry.get("platform_sha256", {})
        assert isinstance(variants, dict), entry["name"]
        for platform, digest in variants.items():
            assert re.fullmatch(r"[a-z0-9_]+", platform), (entry["name"], platform)
            assert re.fullmatch(r"[0-9a-f]{64}", digest), (entry["name"], platform)
            assert digest != entry["sha256"], (entry["name"], platform)
