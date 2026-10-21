"""Source availability for the copyleft parts of a build (T08.05.03, T08.05.07).

The notices of every package carry (a) the license choice for Qt / PySide6, (b) a source-availability
list with the exact version of every copyleft component and where its source is, and (c) the statement
about own patches. ``ci_license_review_check`` refuses a package whose notices lack any of them.
"""
from __future__ import annotations

import re
from pathlib import Path

COPYLEFT = re.compile(r"\b(?:A|L)?GPL|\bMPL|\bEPL|\bCDDL|\bEUPL", re.IGNORECASE)
QT_DISTRIBUTIONS = {"pyside6", "pyside6-essentials", "pyside6-addons", "shiboken6"}
REPOSITORY = "https://github.com/deadfrogface/Karrierekrake"
SECTION_QT = "--- Qt / PySide6: license choice and source availability ---"
SECTION_SOURCES = "--- source availability of copyleft components ---"
PATCH_STATEMENT = (
    "Own patches: none. No third-party component is modified before packaging (no patch files, no patch step "
    "in the build or CI; tests/test_copyleft_sources.py fails if one appears). Components built from source are "
    "pinned by URL and SHA-256: OpenSSL and cryptography for Intel macOS in packaging/intel_crypto_sources.json, "
    "CPython archives in packaging/ci_python_runtimes.json."
)


def _license_text(component: dict) -> str:
    names = []
    for entry in component.get("licenses", []):
        lic = entry.get("license") or {}
        names.append(lic.get("id") or lic.get("name") or entry.get("expression") or "")
    return " | ".join(n for n in names if n)


def _is_distribution(component: dict) -> bool:
    return str(component.get("bom-ref", "")).startswith("pkg:")


def copyleft_components(components: list[dict]) -> list[dict]:
    """Python distributions with a copyleft license term, and every distro package (all ship source)."""
    found = []
    for component in components:
        ref = str(component.get("bom-ref", ""))
        if ref.startswith("os-package:") or (_is_distribution(component) and COPYLEFT.search(_license_text(component))):
            found.append(component)
    return sorted(found, key=lambda c: (str(c.get("bom-ref", "")).split(":")[0], str(c["name"]).lower()))


def source_location(component: dict) -> str:
    name, version = component["name"], component.get("version") or "unknown"
    if str(component.get("bom-ref", "")).startswith("os-package:"):
        return (f"Ubuntu source of binary package {name} {version}: `apt-get source {name}={version}` or "
                f"https://packages.ubuntu.com/source/jammy/{name}")
    if name.lower().replace("_", "-") in QT_DISTRIBUTIONS:
        return (f"Qt {version}: https://download.qt.io/official_releases/qt/{'.'.join(version.split('.')[:2])}/{version}/ ; "
                f"PySide6/shiboken6 {version}: https://code.qt.io/cgit/pyside/pyside-setup.git (tag v{version})")
    return f"https://pypi.org/project/{name}/{version}/#files (source distribution)"


def qt_present(components: list[dict]) -> bool:
    return any(_is_distribution(c) and str(c["name"]).lower().replace("_", "-") in QT_DISTRIBUTIONS for c in components)


def notice_sections(root: Path, components: list[dict]) -> list[str]:
    """Notice text for the build: Qt license choice, source availability list, patch statement."""
    out: list[str] = []
    if qt_present(components):
        lgpl = (Path(root) / "packaging" / "licenses" / "LGPL-3.0.txt").read_text(encoding="utf-8")
        gpl = (Path(root) / "packaging" / "licenses" / "GPL-3.0.txt").read_text(encoding="utf-8")
        version = next(c.get("version") for c in components
                       if _is_distribution(c) and str(c["name"]).lower().replace("_", "-") in QT_DISTRIBUTIONS)
        out += [
            "\n" + SECTION_QT,
            (f"Karrierekrake uses Qt and PySide6 {version} under the GNU Lesser General Public License, version 3 "
             "(LGPL-3.0-only), one of the licenses the Qt for Python wheels offer (LGPL-3.0-only OR GPL-2.0-only OR "
             "GPL-3.0-only). The Qt Commercial license text some wheels carry is not used."),
            "Source: " + source_location({"name": "PySide6", "version": version}),
            ("Replacing Qt: the Linux, macOS and Windows packages carry Qt as separate shared libraries inside the "
             "package folder (Windows: the _internal folder next to Karrierekrake.exe) and can be exchanged for an "
             "interface-compatible build of the same Qt version."),
            "\n--- LGPL-3.0 (chosen license for Qt / PySide6) ---",
            lgpl,
            "\n--- GPL-3.0 (the LGPL-3.0 incorporates its terms) ---",
            gpl,
        ]
    listed = copyleft_components(components)
    out += ["\n" + SECTION_SOURCES,
            "The corresponding source of the following components is available from the locations below, in the "
            "exact version shipped. On request to the publisher named in the program's About dialog we also send it, "
            "for three years after the last release that contains the component.",
            PATCH_STATEMENT]
    out += [f"- {c['name']} {c.get('version') or '(version unknown)'} | {_license_text(c) or 'see distro copyright text'} | "
            f"{source_location(c)}" for c in listed]
    return out


def check_notice_text(text: str, components: list[dict]) -> list[str]:
    """Problems of a shipped notices text against the SBOM components of the same build."""
    problems = []
    if qt_present(components):
        if SECTION_QT not in text:
            problems.append("Qt / PySide6 license choice and source notice missing")
        if "GNU LESSER GENERAL PUBLIC LICENSE" not in text:
            problems.append("LGPL-3.0 text missing although Qt / PySide6 is shipped")
    if SECTION_SOURCES not in text:
        problems.append("source availability section missing")
    else:
        section = text.split(SECTION_SOURCES, 1)[1]
        for component in copyleft_components(components):
            line = f"- {component['name']} {component.get('version') or '(version unknown)'} |"
            if line not in section:
                problems.append(f"copyleft component without source entry: {component['name']}")
    return problems
