"""T08.05.03 / T08.05.07: Qt license choice, source availability and the 'no own patches' statement."""
from __future__ import annotations

from pathlib import Path

from scripts import copyleft_sources as cs

ROOT = Path(__file__).resolve().parents[1]


def _pkg(name, version, license_name):
    return {"type": "library", "name": name, "version": version, "bom-ref": f"pkg:pypi/{name}@{version}",
            "licenses": [{"license": {"name": license_name}}]}


COMPONENTS = [
    _pkg("PySide6", "6.11.2", "LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only"),
    _pkg("certifi", "2026.10.19", "MPL-2.0"),
    _pkg("requests", "2.40.0", "Apache-2.0"),
    {"type": "library", "name": "libpcre3", "version": "2:8.39", "bom-ref": "os-package:libpcre3"},
]


def test_copyleft_components_are_selected_by_license_and_distro_origin():
    names = [c["name"] for c in cs.copyleft_components(COMPONENTS)]
    assert names == ["libpcre3", "certifi", "PySide6"] and "requests" not in names


def test_notice_sections_name_choice_source_and_patch_statement():
    text = "\n".join(cs.notice_sections(ROOT, COMPONENTS))
    assert cs.SECTION_QT in text and "LGPL-3.0-only" in text and "GNU LESSER GENERAL PUBLIC LICENSE" in text
    assert "https://download.qt.io/official_releases/qt/6.11/6.11.2/" in text and "apt-get source libpcre3=2:8.39" in text
    assert "Own patches: none" in text and cs.check_notice_text(text, COMPONENTS) == []


def test_missing_parts_are_reported():
    text = "\n".join(cs.notice_sections(ROOT, COMPONENTS))
    assert cs.check_notice_text(text.replace(cs.SECTION_QT, "x"), COMPONENTS) == ["Qt / PySide6 license choice and source notice missing"]
    problems = cs.check_notice_text(text.replace("- certifi 2026.10.19 |", "- gone |"), COMPONENTS)
    assert problems == ["copyleft component without source entry: certifi"]
    assert "source availability section missing" in cs.check_notice_text("nothing", COMPONENTS)


def test_no_own_patches_exist_so_the_statement_stays_true():
    ignored = {".git", ".venv", "node_modules", "build", "dist", "third_party", "mobile", "website"}
    patches = [p for p in ROOT.rglob("*.patch") if not ignored & set(p.relative_to(ROOT).parts)]
    assert patches == []
    for workflow in (ROOT / ".github" / "workflows").glob("*.yml"):
        body = workflow.read_text(encoding="utf-8")
        assert "git apply" not in body and "patch -p" not in body, workflow.name
