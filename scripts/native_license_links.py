"""Link native files to the license text that covers them (T08.05.04).

A native file without a Python-distribution license is linked, not guessed, to one of:
  distro-copyright:<bom-ref>   the Ubuntu package it belongs to; the package's copyright file is in the notices
  python-license-file:CPython  the CPython runtime; its LICENSE.txt (with the incorporated-software licenses) is in the notices
  ms-redistributable:<family>  a Microsoft runtime redistributable (UCRT / Visual C++ runtime)
Anything else stays an unresolved ``native:`` entry of the license review.
"""
from __future__ import annotations

from pathlib import PurePosixPath

MS_FAMILIES = (
    (("api-ms-win-", "ucrtbase.dll"), "ucrt"),
    (("vcruntime", "msvcp", "concrt", "vcomp"), "vcrt"),
)
SECTION_MS = "--- Microsoft redistributable runtime files ---"
SECTION_PYTHON = "--- CPython / build-interpreter LICENSE.txt ---"
MS_NOTICE = (
    "\n" + SECTION_MS + "\n"
    "The Windows package contains the Microsoft Universal C Runtime (api-ms-win-*.dll, ucrtbase.dll) and the "
    "Visual C++ runtime (VCRUNTIME*.dll, MSVCP*.dll, VCOMP*.dll). They are Microsoft's redistributable files, shipped unchanged "
    "under Microsoft's redistribution terms for these files. They are not part of PySide6 or any other package "
    "next to which they are stored. They come with the compiler and operating system the program is built for "
    "and only enable the program to run there."
)
EVIDENCE_KINDS = ("distro-copyright", "python-license-file", "ms-redistributable")


def ms_redistributable_family(name: str) -> str | None:
    leaf = PurePosixPath(str(name).replace("\\", "/")).name.lower()
    return next((family for prefixes, family in MS_FAMILIES if leaf.startswith(prefixes)), None)


def evidence_for(name: str, os_owner: dict | None, missing_distro: set[str], python_owner: dict | None,
                 python_notice_present: bool) -> str | None:
    if ms_redistributable_family(name):
        return "ms-redistributable:" + ms_redistributable_family(name)
    if os_owner and os_owner["name"] not in missing_distro:
        return "distro-copyright:" + os_owner["bom-ref"]
    if python_owner and python_notice_present:
        return "python-license-file:CPython"
    return None


def evidence_of(component: dict) -> str | None:
    return next((p["value"] for p in component.get("properties", []) if p.get("name") == "kk:license-evidence"), None)
