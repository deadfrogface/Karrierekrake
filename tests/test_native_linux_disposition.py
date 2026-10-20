"""T06.05.04.03: mechanical checks of the 2026-10-20 Linux candidate disposition.

Only claims that follow from the committed audit data are asserted here:
version ranges, architecture, and absence of the affected tool/daemon package
from the shipped package list. Threat-model claims (malicious X server,
privileged mount, local config only) are not provable this way and are not
asserted.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SEC = ROOT / "docs" / "security"
DISPOSITION = json.loads((SEC / "NATIVE_LINUX_CANDIDATE_DISPOSITION_2026-10-20.json").read_text(encoding="utf-8"))
TRIAGE = json.loads((SEC / "NATIVE_LINUX_CANDIDATE_TRIAGE_2026-10-17.json").read_text(encoding="utf-8"))
AUDIT = json.loads((SEC / "NATIVE_LINUX_ARTIFACT_AUDIT_2026-10-16.json").read_text(encoding="utf-8"))
BY_ID = {c["id"]: c for c in DISPOSITION["candidates"]}
TRIAGE_BY_ID = {c["id"]: c for c in TRIAGE["candidates"]}
SHIPPED_PACKAGES = {q["component"].removeprefix("os-package:").split(":")[0] for q in AUDIT["queries"]}
SHIPPED_FILES = {u["component"].rsplit("/", 1)[-1] for u in AUDIT["unverified"]}

# Lowest affected upstream version stated in the advisory text.
VERSION_FLOOR = {
    "UBUNTU-CVE-2026-85091": (1, 3, 1, 2),  # zlib 1.3.1.2 through 1.3.2
    "UBUNTU-CVE-2026-102633": (2, 7, 2),  # expat 2.7.2 through 2.8.5
}
ARCH_32BIT_ONLY = ("UBUNTU-CVE-2026-89157", "UBUNTU-CVE-2026-89158")
# Affected program/daemon -> distribution package that would ship it, and file names.
TOOL_NOT_SHIPPED = {
    "UBUNTU-CVE-2022-41409": ({"pcre2-utils"}, {"pcre2test"}),
    "UBUNTU-CVE-2022-4899": ({"zstd"}, {"zstd"}),
    "UBUNTU-CVE-2018-5709": ({"krb5-admin-server", "krb5-kdc"}, {"kadmin", "kadmin.local", "kdb5_util"}),
    "UBUNTU-CVE-2023-34969": ({"dbus", "dbus-daemon"}, {"dbus-daemon"}),
    "UBUNTU-CVE-2026-40228": ({"systemd"}, {"systemd-journald"}),
    "UBUNTU-CVE-2020-25697": ({"xserver-xorg-core"}, {"Xorg"}),
    "UBUNTU-CVE-2026-75466": ({"libturbojpeg"}, {"libturbojpeg.so.0"}),
}


def _upstream(debian_version: str) -> tuple[int, ...]:
    core = debian_version.split(":", 1)[-1]
    core = re.split(r"[-+~]", core, maxsplit=1)[0]
    core = core.replace(".dfsg", "")
    return tuple(int(part) for part in core.split(".") if part.isdigit())


def test_every_triage_candidate_has_one_disposition() -> None:
    assert set(BY_ID) == set(TRIAGE_BY_ID)
    assert len(BY_ID) == 50
    for cid, c in BY_ID.items():
        assert c["status"] in {"OFFEN", "IMPLEMENTIERT – PRÜFUNG OFFEN", "FERTIG"}, cid
        assert c["reasoning"], cid
        assert c["jammy_fixed_version"] is None, cid


@pytest.mark.parametrize("cid", sorted(VERSION_FLOOR))
def test_shipped_version_is_below_the_affected_range(cid: str) -> None:
    assert BY_ID[cid]["class"] == "nicht_betroffene_version"
    for inst in TRIAGE_BY_ID[cid]["package_instances"]:
        assert _upstream(inst["source_version"]) < VERSION_FLOOR[cid], inst


@pytest.mark.parametrize("cid", ARCH_32BIT_ONLY)
def test_32bit_only_candidates_ship_amd64_only(cid: str) -> None:
    assert BY_ID[cid]["class"] == "nicht_betroffene_architektur"
    for inst in TRIAGE_BY_ID[cid]["package_instances"]:
        assert inst["binary_package"].endswith(":amd64"), inst


@pytest.mark.parametrize("cid", sorted(TOOL_NOT_SHIPPED))
def test_affected_tool_is_not_in_the_shipped_package(cid: str) -> None:
    assert BY_ID[cid]["class"] == "nicht_betroffene_komponente"
    packages, files = TOOL_NOT_SHIPPED[cid]
    assert not packages & SHIPPED_PACKAGES, packages & SHIPPED_PACKAGES
    assert not files & SHIPPED_FILES, files & SHIPPED_FILES


def test_withdrawn_lz4_candidate_is_classified_as_rejected_not_unreachable() -> None:
    """CVE-2025-62813 is REJECTED at CVE.org and withdrawn in OSV (independent review 2026-10-20)."""
    c = BY_ID["UBUNTU-CVE-2025-62813"]
    assert c["class"] == "zurueckgezogen"
    assert "REJECTED" in c["reasoning"]


def test_cairosvg_is_not_a_dependency() -> None:
    assert BY_ID["UBUNTU-CVE-2026-107378"]["class"] == "nicht_betroffene_komponente"
    pins = "".join(p.read_text(encoding="utf-8").lower() for p in ROOT.glob("requirements*.txt"))
    pins += (ROOT / "constraints-runtime.txt").read_text(encoding="utf-8").lower()
    assert "cairosvg" not in pins
    assert "cairosvg" not in {name.lower() for name in SHIPPED_FILES}
