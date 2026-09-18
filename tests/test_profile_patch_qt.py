"""pytest-qt interactions for ApplicantSection CLEAR/SET persistence (PR20)."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6.QtWidgets")

from core.config import ApplicationProfile, QualificationsConfig, empty_app_config, load_config, save_config
from desktop.pages.profile_sections import ApplicantSection, QualificationsSection
from desktop.services.profile_merge import SOURCE_CV, SOURCE_MANUAL, set_field_origin, sync_application_summaries
from desktop.services.profile_patch import PatchOp


@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


def _paths(tmp_path):
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir(exist_ok=True)
    return dict(
        profile_path=cfg_dir / "profile.yaml",
        application_path=cfg_dir / "application_profile.yaml",
        settings_path=cfg_dir / "settings.yaml",
    )


def test_applicant_section_clear_languages_persists(qapp, tmp_path):
    section = ApplicantSection()
    app = ApplicationProfile(
        first_name="Anna",
        last_name="Alpha",
        email="anna.alpha@example.com",
        languages="Deutsch, Englisch",
        city="Berlin",
        country="DE",
    )
    set_field_origin(app, "languages", SOURCE_CV)
    section.load(app, sync_address_to_search=False)
    section.lang_text.setText("")  # explicit clear in UI
    section.save_into(app)
    assert app.languages == ""
    assert (app.field_origins or {}).get("languages") == SOURCE_MANUAL

    quals = QualificationsConfig()
    # Simulate profile save sync
    sync_application_summaries(app, quals, fill_empty=False)
    cfg = empty_app_config(root=tmp_path)
    cfg.application = app
    paths = _paths(tmp_path)
    save_config(cfg, **paths)
    loaded = load_config(**paths, root=tmp_path, strip_placeholders=False)
    assert loaded.application.languages == ""


def test_applicant_section_whitespace_is_clear(qapp):
    section = ApplicantSection()
    app = ApplicationProfile(first_name="Bruno", city="Hamburg")
    section.load(app, sync_address_to_search=False)
    section.first_name.setText("   ")
    section.save_into(app)
    assert app.first_name == ""
    assert (app.field_origins or {}).get("first_name") == SOURCE_MANUAL


def test_applicant_section_unicode_set(qapp, tmp_path):
    section = ApplicantSection()
    app = ApplicationProfile()
    section.load(app, sync_address_to_search=False)
    section.first_name.setText("Jürgen")
    section.city.setText("München")
    section.street.setText("Größe-Straße 1")
    section.save_into(app)
    assert app.first_name == "Jürgen"
    assert app.city == "München"
    cfg = empty_app_config(root=tmp_path)
    cfg.application = app
    paths = _paths(tmp_path)
    save_config(cfg, **paths)
    loaded = load_config(**paths, root=tmp_path, strip_placeholders=False)
    assert loaded.application.first_name == "Jürgen"


def test_qualifications_section_clear_skills_list(qapp, tmp_path):
    from core.config import SourcedText

    section = QualificationsSection()
    quals = QualificationsConfig(
        skills=[
            SourcedText(value="Excel", source=SOURCE_CV),
            SourcedText(value="Word", source=SOURCE_MANUAL),
        ]
    )
    section.load(quals)
    section.skills.set_items([])
    section.save_into(quals)
    assert quals.skills == []
    cfg = empty_app_config(root=tmp_path)
    cfg.profile.qualifications = quals
    paths = _paths(tmp_path)
    save_config(cfg, **paths)
    loaded = load_config(**paths, root=tmp_path, strip_placeholders=False)
    assert loaded.profile.qualifications.skills == []


def test_unchanged_fields_not_written_as_manual(qapp):
    section = ApplicantSection()
    app = ApplicationProfile(first_name="Clara", city="Köln", email="c@example.com")
    set_field_origin(app, "first_name", SOURCE_CV)
    section.load(app, sync_address_to_search=False)
    # Only change city
    section.city.setText("Bonn")
    section.save_into(app)
    assert app.city == "Bonn"
    assert (app.field_origins or {}).get("city") == SOURCE_MANUAL
    # first_name left alone → still CV origin
    assert (app.field_origins or {}).get("first_name") == SOURCE_CV
