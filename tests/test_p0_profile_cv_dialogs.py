"""P0 gate: profile / CV import / dialog regressions (Leonie Brandt golden CV).

Fictional fixture only. Binding golden text:
``tests/fixtures/cv_corpus/Fake_Lebenslauf_Neuer_Blindtest_Leonie_Brandt.txt``
(+ generated PDF sibling with the same filename stem).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from core.config import (
    EducationEntry,
    ExperienceEntry,
    empty_app_config,
    load_config,
    save_config,
)
from core.cv_extract import extract_text
from core.cv_parser import (
    classify_non_language_token,
    is_known_language_name,
    parse_cv_text,
    parsed_to_qualifications,
)
from core.search_intent import SearchIntent, apply_clear_jobs_edit_to_intent
from desktop.services.profile_merge import (
    filter_parsed_for_import,
    replace_qualifications,
)
from desktop.pages.profile import _entry_description, _entry_title

FIXTURES = Path(__file__).parent / "fixtures" / "cv_corpus"
GOLDEN_TXT = FIXTURES / "Fake_Lebenslauf_Neuer_Blindtest_Leonie_Brandt.txt"
GOLDEN_PDF = FIXTURES / "Fake_Lebenslauf_Neuer_Blindtest_Leonie_Brandt.pdf"


def _paths(tmp_path: Path) -> dict[str, Path]:
    return {
        "profile_path": tmp_path / "profile.yaml",
        "application_path": tmp_path / "application_profile.yaml",
        "settings_path": tmp_path / "settings.yaml",
    }


def test_golden_fixture_files_present():
    assert GOLDEN_TXT.is_file(), f"missing golden text fixture: {GOLDEN_TXT}"
    assert GOLDEN_PDF.is_file(), f"missing golden PDF fixture: {GOLDEN_PDF}"


def test_empty_new_profile_has_no_berufsziel(tmp_path: Path):
    cfg = empty_app_config(root=tmp_path)
    assert cfg.profile.jobs.desired_titles == []
    assert cfg.profile.jobs.unwanted_titles == []
    assert cfg.profile.qualifications.education == []
    assert cfg.profile.qualifications.languages == []
    assert cfg.profile.qualifications.skill_values() == []
    paths = _paths(tmp_path)
    save_config(cfg, **paths)
    loaded = load_config(**paths, root=tmp_path, strip_placeholders=False)
    assert loaded.profile.jobs.desired_titles == []
    assert loaded.profile.search_intent.target_roles == []


def test_leonie_golden_cv_import_sections():
    text = GOLDEN_TXT.read_text(encoding="utf-8")
    parsed = parse_cv_text(text)
    q = parsed_to_qualifications(parsed)
    assert any("Büromanagement" in (e.qualification or "") for e in q.education)
    langs = {l.language for l in q.languages}
    assert langs >= {"Deutsch", "Englisch", "Schwedisch", "Spanisch"}
    for bad in ("Lean", "Power", "Beschwerdemanagement", "Datenschutz", "Lean Management", "Power BI"):
        assert bad not in langs
        assert not any(l.language == bad for l in q.languages)
    cert_names = " | ".join(c.name for c in q.certificates).lower()
    assert "lean management" in cert_names
    assert "beschwerdemanagement" in cert_names
    assert "datenschutz" in cert_names
    soft = " | ".join(q.software_values()).lower()
    assert "datev" in soft
    assert "excel" in soft or "office" in soft
    assert "power bi" in soft or "power bi" in cert_names
    skills = " | ".join(q.skill_values()).lower()
    assert "kommunikation" in skills or "organisation" in skills
    assert any(
        "lange aufgabenbeschreibung" in " ".join(e.responsibilities).lower()
        for e in q.work_experience
    )


def test_leonie_pdf_extract_and_parse():
    extracted = extract_text(GOLDEN_PDF) or ""
    assert "Leonie Brandt" in extracted
    q = parsed_to_qualifications(parse_cv_text(extracted))
    assert q.education, "Ausbildung must survive PDF extract"
    assert {l.language for l in q.languages} >= {"Deutsch", "Englisch"}
    assert not any(
        is_known_language_name(c.name) is False
        and c.name.lower() in {"lean", "power"}
        for c in q.certificates
    )
    lang_names = {l.language for l in q.languages}
    assert "Lean" not in lang_names
    assert "Power" not in lang_names
    assert "Beschwerdemanagement" not in lang_names


def test_sprachen_section_never_keeps_weiterbildungen():
    text = """
Leonie Brandt
Sprachen
Deutsch C2
Englisch B2
Lean Management
Power BI
Beschwerdemanagement
Datenschutz
"""
    q = parsed_to_qualifications(parse_cv_text(text))
    langs = {l.language for l in q.languages}
    assert langs == {"Deutsch", "Englisch"}
    blob = " | ".join(
        [*(c.name for c in q.certificates), *q.skill_values(), *q.software_values()]
    ).lower()
    assert "lean management" in blob
    assert "power bi" in blob
    assert "beschwerdemanagement" in blob
    assert "datenschutz" in blob


def test_classify_non_language_tokens():
    assert classify_non_language_token("Power BI") == "software"
    assert classify_non_language_token("Lean Management") == "certificate"
    assert classify_non_language_token("Datenschutz") == "certificate"
    assert classify_non_language_token("Beschwerdemanagement") == "certificate"
    assert is_known_language_name("Schwedisch")
    assert not is_known_language_name("Lean Management")
    assert not is_known_language_name("Power BI")


def test_education_entry_title_uses_qualification():
    entry = EducationEntry(qualification="Kauffrau für Büromanagement (IHK)", institution="Berlin")
    assert "Büromanagement" in _entry_title(entry)


def test_experience_description_keeps_long_responsibilities():
    long = (
        "Sehr lange Aufgabenbeschreibung die nicht abgeschnitten werden darf "
        "und viele Details enthält über Abstimmungen mit Krankenkassen"
    )
    entry = ExperienceEntry(title="Sachbearbeiterin", responsibilities=[long, "DATEV"])
    body = _entry_description(entry)
    assert long in body
    assert "DATEV" in body


def test_desired_titles_clear_persists_and_clears_search_intent(tmp_path: Path):
    cfg = empty_app_config(root=tmp_path)
    cfg.profile.jobs.desired_titles = [
        "Gehalts-/Lohnbuchhalter",
        "Sachbearbeiter",
        "Backoffice",
    ]
    cfg.profile.jobs.unwanted_titles = ["Elster"]
    cfg.profile.search_intent = SearchIntent(
        target_roles=list(cfg.profile.jobs.desired_titles),
        excluded_roles=list(cfg.profile.jobs.unwanted_titles),
    )
    paths = _paths(tmp_path)
    save_config(cfg, **paths)

    cfg2 = load_config(**paths, root=tmp_path, strip_placeholders=False)
    cfg2.profile.jobs.desired_titles = []
    cfg2.profile.jobs.unwanted_titles = []
    cfg2.profile.search_intent = apply_clear_jobs_edit_to_intent(
        cfg2.profile.search_intent, cfg2.profile.jobs
    )
    save_config(cfg2, **paths)
    loaded = load_config(**paths, root=tmp_path, strip_placeholders=False)
    assert loaded.profile.jobs.desired_titles == []
    assert loaded.profile.jobs.unwanted_titles == []
    assert loaded.profile.search_intent.target_roles == []
    assert loaded.profile.search_intent.excluded_roles == []


def test_save_config_does_not_resurrect_empty_jobs_from_intent(tmp_path: Path):
    """Stale SearchIntent must not refill deleted Berufsziel lists."""
    cfg = empty_app_config(root=tmp_path)
    cfg.profile.search_intent = SearchIntent(
        target_roles=["Sachbearbeiter", "Backoffice"],
        excluded_roles=["Elster"],
    )
    # Jobs intentionally empty (user deleted all) — intent still dirty.
    cfg.profile.jobs.desired_titles = []
    cfg.profile.jobs.unwanted_titles = []
    paths = _paths(tmp_path)
    save_config(cfg, **paths)
    loaded = load_config(**paths, root=tmp_path, strip_placeholders=False)
    assert loaded.profile.jobs.desired_titles == []
    assert loaded.profile.jobs.unwanted_titles == []


def test_education_persists_across_restart(tmp_path: Path):
    cfg = empty_app_config(root=tmp_path)
    text = GOLDEN_TXT.read_text(encoding="utf-8")
    incoming = parsed_to_qualifications(filter_parsed_for_import(parse_cv_text(text)))
    cfg.profile.qualifications = replace_qualifications(
        cfg.profile.qualifications, incoming
    )
    paths = _paths(tmp_path)
    save_config(cfg, **paths)
    loaded = load_config(**paths, root=tmp_path, strip_placeholders=False)
    assert any(
        "Büromanagement" in (e.qualification or "")
        for e in loaded.profile.qualifications.education
    )
    assert loaded.profile.qualifications.skill_values()
    assert loaded.profile.qualifications.software_values()


def test_dialog_geometry_clamps_to_available_screen(qapp=None):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6.QtWidgets")
    from PySide6.QtCore import QRect
    from PySide6.QtWidgets import QApplication, QDialog

    from desktop.widgets.dialog_geometry import clamp_saved_geometry, fit_dialog_to_screen

    app = QApplication.instance() or QApplication([])
    dlg = QDialog()
    dlg.setMinimumSize(200, 150)
    fit_dialog_to_screen(dlg, preferred_width=3000, preferred_height=3000, margin=24)
    screen = app.primaryScreen()
    avail = screen.availableGeometry() if screen else QRect(0, 0, 1280, 720)
    assert dlg.width() <= avail.width()
    assert dlg.height() <= avail.height()
    geo = clamp_saved_geometry(dlg, QRect(-100, -50, 5000, 4000))
    assert geo.x() >= avail.x()
    assert geo.y() >= avail.y()
    assert geo.width() <= avail.width()
    assert geo.height() <= avail.height()
