"""PR20: Profile patch persistence / deletion / anti-resurrection regressions.

No PII fixtures — fictional names only (Anna Alpha, etc.).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from core.config import (
    ApplicationProfile,
    EducationEntry,
    ExperienceEntry,
    LanguageEntry,
    QualificationsConfig,
    SourcedText,
    empty_app_config,
    load_config,
    save_config,
)
from desktop.services.profile_merge import (
    SOURCE_CV,
    SOURCE_MANUAL,
    apply_personal_updates,
    personal_from_parsed,
    plan_personal_import,
    preserve_sourced_on_edit,
    replace_qualifications,
    set_field_origin,
    sync_application_summaries,
)
from desktop.services.profile_patch import (
    PATCH_SCHEMA_VERSION,
    FieldPatch,
    PatchOp,
    ProfilePatch,
    apply_profile_patch,
    build_application_patches,
    normalize_patch_value,
    validate_profile_patch,
)


# ---------------------------------------------------------------------------
# Reproduction: cleared summary fields must not resurrect from CV quals
# ---------------------------------------------------------------------------


def test_manual_clear_languages_summary_not_resurrected_by_sync():
    """Bug: clear languages → pop origin → sync refills from quals."""
    app = ApplicationProfile(languages="Deutsch, Englisch")
    set_field_origin(app, "languages", SOURCE_CV)
    quals = QualificationsConfig(
        languages=[
            LanguageEntry(language="Deutsch", level="C2", source=SOURCE_CV),
            LanguageEntry(language="Englisch", level="B2", source=SOURCE_CV),
        ]
    )
    # Simulate ApplicantSection.save_into clearing the field
    patches = build_application_patches(
        app,
        {"languages": ""},
    )
    apply_profile_patch(app, quals, ProfilePatch(application=patches))
    assert app.languages == ""
    assert (app.field_origins or {}).get("languages") == SOURCE_MANUAL

    sync_application_summaries(app, quals)
    assert app.languages == "", "CV quals must not resurrect a manually cleared summary"


def test_manual_clear_education_and_employment_summaries():
    app = ApplicationProfile(
        education="Bachelor",
        current_employment="Sachbearbeiter",
        work_experience="3 Jahre",
        driving_license="B",
    )
    for name in ("education", "current_employment", "work_experience", "driving_license"):
        set_field_origin(app, name, SOURCE_CV)
    quals = QualificationsConfig(
        education=[EducationEntry(qualification="Bachelor Informatik", source=SOURCE_CV)],
        work_experience=[ExperienceEntry(title="Sachbearbeiter", company="X", source=SOURCE_CV)],
        driving_license=[SourcedText(value="B", source=SOURCE_CV)],
    )
    patches = build_application_patches(
        app,
        {
            "education": "",
            "current_employment": "",
            "work_experience": "",
            "driving_license": "",
        },
    )
    apply_profile_patch(app, quals, ProfilePatch(application=patches))
    sync_application_summaries(app, quals)
    assert app.education == ""
    assert app.current_employment == ""
    assert app.work_experience == ""
    assert app.driving_license == ""


def test_cv_import_then_manual_clear_persists_reload(tmp_path: Path):
    cfg = empty_app_config(root=tmp_path)
    cfg.application.first_name = "Anna"
    cfg.application.last_name = "Alpha"
    cfg.application.email = "anna.alpha@example.com"
    cfg.application.languages = "Deutsch"
    cfg.application.field_origins = {
        "first_name": SOURCE_CV,
        "last_name": SOURCE_CV,
        "email": SOURCE_CV,
        "languages": SOURCE_CV,
    }
    cfg.profile.qualifications = QualificationsConfig(
        languages=[LanguageEntry(language="Deutsch", level="C1", source=SOURCE_CV)],
        skills=[SourcedText(value="Excel", source=SOURCE_CV)],
    )
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()
    paths = dict(
        profile_path=cfg_dir / "profile.yaml",
        application_path=cfg_dir / "application_profile.yaml",
        settings_path=cfg_dir / "settings.yaml",
    )
    save_config(cfg, **paths)

    loaded = load_config(**paths, root=tmp_path, strip_placeholders=False)
    patches = build_application_patches(
        loaded.application,
        {
            "first_name": "Anna",
            "last_name": "Alpha",
            "email": "anna.alpha@example.com",
            "languages": "",  # explicit clear
        },
    )
    apply_profile_patch(
        loaded.application,
        loaded.profile.qualifications,
        ProfilePatch(application=patches),
    )
    # Mimic former save() side-effect
    sync_application_summaries(loaded.application, loaded.profile.qualifications)
    save_config(loaded, **paths)

    again = load_config(**paths, root=tmp_path, strip_placeholders=False)
    assert again.application.languages == ""
    assert again.application.first_name == "Anna"


# ---------------------------------------------------------------------------
# Patch semantics: UNCHANGED / SET / CLEAR are distinct
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected_op,expected_val",
    [
        (None, PatchOp.UNCHANGED, None),
        ("", PatchOp.CLEAR, None),
        ("   ", PatchOp.CLEAR, None),  # whitespace-only → CLEAR for text fields
        ("Hallo", PatchOp.SET, "Hallo"),
        ("  Hallo  ", PatchOp.SET, "Hallo"),
        ("äöüß", PatchOp.SET, "äöüß"),
    ],
)
def test_normalize_patch_value_text(raw, expected_op, expected_val):
    op, val = normalize_patch_value(raw, kind="text")
    assert op == expected_op
    assert val == expected_val


def test_unchanged_does_not_overwrite_storage():
    app = ApplicationProfile(first_name="Anna", city="Berlin")
    set_field_origin(app, "first_name", SOURCE_CV)
    quals = QualificationsConfig()
    patch = ProfilePatch(
        application={
            "first_name": FieldPatch(op=PatchOp.UNCHANGED),
            "city": FieldPatch(op=PatchOp.SET, value="München"),
            "email": FieldPatch(op=PatchOp.CLEAR),
        }
    )
    apply_profile_patch(app, quals, patch)
    assert app.first_name == "Anna"
    assert app.city == "München"
    assert app.email == ""
    assert (app.field_origins or {}).get("city") == SOURCE_MANUAL
    assert (app.field_origins or {}).get("email") == SOURCE_MANUAL


def test_validate_rejects_set_without_value():
    bad = ProfilePatch(application={"first_name": FieldPatch(op=PatchOp.SET, value=None)})
    errors = validate_profile_patch(bad)
    assert errors


def test_delete_section_skills():
    quals = QualificationsConfig(
        skills=[SourcedText(value="Excel", source=SOURCE_CV)],
        software=[SourcedText(value="Word", source=SOURCE_MANUAL)],
    )
    app = ApplicationProfile()
    patch = ProfilePatch(
        qualifications={"skills": FieldPatch(op=PatchOp.DELETE_SECTION)}
    )
    apply_profile_patch(app, quals, patch)
    assert quals.skills == []
    assert quals.software_values() == ["Word"]


def test_list_member_delete_via_set():
    prev = [
        SourcedText(value="Excel", source=SOURCE_CV),
        SourcedText(value="Word", source=SOURCE_CV),
        SourcedText(value="DATEV", source=SOURCE_MANUAL),
    ]
    out = preserve_sourced_on_edit(prev, ["Word", "DATEV"])
    assert [s.value for s in out] == ["Word", "DATEV"]
    assert out[0].source == SOURCE_CV
    assert out[1].source == SOURCE_MANUAL


def test_clear_full_list():
    prev = [SourcedText(value="Excel", source=SOURCE_CV)]
    assert preserve_sourced_on_edit(prev, []) == []
    assert preserve_sourced_on_edit(prev, ["", "  "]) == []


# ---------------------------------------------------------------------------
# Roundtrip create/edit/clear/restart
# ---------------------------------------------------------------------------


def _roundtrip_paths(tmp_path: Path) -> dict:
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir(exist_ok=True)
    return dict(
        profile_path=cfg_dir / "profile.yaml",
        application_path=cfg_dir / "application_profile.yaml",
        settings_path=cfg_dir / "settings.yaml",
    )


def test_create_save_restart(tmp_path: Path):
    cfg = empty_app_config(root=tmp_path)
    paths = _roundtrip_paths(tmp_path)
    patch = ProfilePatch(
        application={
            "first_name": FieldPatch(op=PatchOp.SET, value="Clara"),
            "last_name": FieldPatch(op=PatchOp.SET, value="Gamma"),
            "email": FieldPatch(op=PatchOp.SET, value="clara.gamma@example.com"),
            "city": FieldPatch(op=PatchOp.SET, value="Nürnberg"),
        }
    )
    apply_profile_patch(cfg.application, cfg.profile.qualifications, patch)
    save_config(cfg, **paths)
    loaded = load_config(**paths, root=tmp_path, strip_placeholders=False)
    assert loaded.application.first_name == "Clara"
    assert loaded.application.city == "Nürnberg"


def test_edit_save_restart(tmp_path: Path):
    cfg = empty_app_config(root=tmp_path)
    paths = _roundtrip_paths(tmp_path)
    cfg.application.first_name = "Bruno"
    cfg.application.city = "München"
    save_config(cfg, **paths)
    loaded = load_config(**paths, root=tmp_path, strip_placeholders=False)
    apply_profile_patch(
        loaded.application,
        loaded.profile.qualifications,
        ProfilePatch(
            application={
                "first_name": FieldPatch(op=PatchOp.SET, value="Bruno"),
                "city": FieldPatch(op=PatchOp.SET, value="Hamburg"),
            }
        ),
    )
    save_config(loaded, **paths)
    again = load_config(**paths, root=tmp_path, strip_placeholders=False)
    assert again.application.city == "Hamburg"
    assert again.application.first_name == "Bruno"


def test_clear_field_save_restart(tmp_path: Path):
    cfg = empty_app_config(root=tmp_path)
    paths = _roundtrip_paths(tmp_path)
    cfg.application.phone = "+49 170 0000000"
    cfg.application.field_origins = {"phone": SOURCE_CV}
    save_config(cfg, **paths)
    loaded = load_config(**paths, root=tmp_path, strip_placeholders=False)
    apply_profile_patch(
        loaded.application,
        loaded.profile.qualifications,
        ProfilePatch(application={"phone": FieldPatch(op=PatchOp.CLEAR)}),
    )
    save_config(loaded, **paths)
    again = load_config(**paths, root=tmp_path, strip_placeholders=False)
    assert again.application.phone == ""
    assert (again.application.field_origins or {}).get("phone") == SOURCE_MANUAL


def test_unicode_roundtrip(tmp_path: Path):
    cfg = empty_app_config(root=tmp_path)
    paths = _roundtrip_paths(tmp_path)
    apply_profile_patch(
        cfg.application,
        cfg.profile.qualifications,
        ProfilePatch(
            application={
                "first_name": FieldPatch(op=PatchOp.SET, value="Jürgen"),
                "street": FieldPatch(op=PatchOp.SET, value="Größe-Straße 12"),
                "city": FieldPatch(op=PatchOp.SET, value="München"),
            }
        ),
    )
    save_config(cfg, **paths)
    loaded = load_config(**paths, root=tmp_path, strip_placeholders=False)
    assert loaded.application.first_name == "Jürgen"
    assert "Größe" in loaded.application.street
    assert loaded.application.city == "München"


def test_whitespace_field_is_clear_not_unchanged(tmp_path: Path):
    cfg = empty_app_config(root=tmp_path)
    paths = _roundtrip_paths(tmp_path)
    cfg.application.first_name = "Anna"
    save_config(cfg, **paths)
    loaded = load_config(**paths, root=tmp_path, strip_placeholders=False)
    patches = build_application_patches(loaded.application, {"first_name": "   "})
    assert patches["first_name"].op == PatchOp.CLEAR
    apply_profile_patch(
        loaded.application, loaded.profile.qualifications, ProfilePatch(application=patches)
    )
    save_config(loaded, **paths)
    again = load_config(**paths, root=tmp_path, strip_placeholders=False)
    assert again.application.first_name == ""


# ---------------------------------------------------------------------------
# CV import → manual edit / clear
# ---------------------------------------------------------------------------


def test_cv_import_then_manual_edit_persists(tmp_path: Path):
    from core.cv_parser import parse_cv_text, parsed_to_qualifications

    text = """Anna Alpha
Testweg 1
10115 Berlin
anna.alpha@example.com
+49 170 1111111

Sprachen
Deutsch – C2
Englisch – B2

Skills
Excel
"""
    parsed = parse_cv_text(text)
    cfg = empty_app_config(root=tmp_path)
    plan = plan_personal_import(cfg.application, personal_from_parsed(parsed), mode="replace")
    apply_personal_updates(cfg.application, plan.updates, source=SOURCE_CV)
    cfg.profile.qualifications = replace_qualifications(
        cfg.profile.qualifications, parsed_to_qualifications(parsed)
    )
    sync_application_summaries(cfg.application, cfg.profile.qualifications, fill_empty=True)

    # Manual edit of name
    apply_profile_patch(
        cfg.application,
        cfg.profile.qualifications,
        ProfilePatch(
            application={
                "first_name": FieldPatch(op=PatchOp.SET, value="Annabelle"),
                "city": FieldPatch(op=PatchOp.SET, value="Potsdam"),
            }
        ),
    )
    paths = _roundtrip_paths(tmp_path)
    save_config(cfg, **paths)
    loaded = load_config(**paths, root=tmp_path, strip_placeholders=False)
    assert loaded.application.first_name == "Annabelle"
    assert loaded.application.city == "Potsdam"
    assert (loaded.application.field_origins or {}).get("first_name") == SOURCE_MANUAL


def test_cv_import_then_manual_clear_skill_list(tmp_path: Path):
    quals = QualificationsConfig(
        skills=[
            SourcedText(value="Excel", source=SOURCE_CV),
            SourcedText(value="Word", source=SOURCE_CV),
        ]
    )
    quals.skills = preserve_sourced_on_edit(quals.skills, [])
    cfg = empty_app_config(root=tmp_path)
    cfg.profile.qualifications = quals
    paths = _roundtrip_paths(tmp_path)
    save_config(cfg, **paths)
    loaded = load_config(**paths, root=tmp_path, strip_placeholders=False)
    assert loaded.profile.qualifications.skills == []


# ---------------------------------------------------------------------------
# Section / total reset
# ---------------------------------------------------------------------------


def test_section_reset_qualifications_only():
    app = ApplicationProfile(first_name="Anna")
    quals = QualificationsConfig(
        skills=[SourcedText(value="Excel", source=SOURCE_CV)],
        languages=[LanguageEntry(language="Deutsch", level="C1", source=SOURCE_CV)],
    )
    apply_profile_patch(
        app,
        quals,
        ProfilePatch(
            qualifications={
                "skills": FieldPatch(op=PatchOp.DELETE_SECTION),
                "languages": FieldPatch(op=PatchOp.DELETE_SECTION),
                "software": FieldPatch(op=PatchOp.DELETE_SECTION),
                "education": FieldPatch(op=PatchOp.DELETE_SECTION),
                "work_experience": FieldPatch(op=PatchOp.DELETE_SECTION),
                "certificates": FieldPatch(op=PatchOp.DELETE_SECTION),
                "driving_license": FieldPatch(op=PatchOp.DELETE_SECTION),
            }
        ),
    )
    assert app.first_name == "Anna"
    assert quals.skills == []
    assert quals.languages == []


def test_delete_profile_op_clears_application_and_quals():
    app = ApplicationProfile(first_name="Anna", email="a@example.com", cv_path="x.pdf")
    quals = QualificationsConfig(skills=[SourcedText(value="X", source=SOURCE_CV)])
    apply_profile_patch(
        app,
        quals,
        ProfilePatch(delete_profile=True),
    )
    assert app.first_name == ""
    assert app.email == ""
    assert app.cv_path == ""
    assert quals.skills == []


def test_patch_schema_version_constant():
    assert isinstance(PATCH_SCHEMA_VERSION, int)
    assert PATCH_SCHEMA_VERSION >= 1


# ---------------------------------------------------------------------------
# Crash / partial-write: atomic YAML replace keeps prior good file
# ---------------------------------------------------------------------------


def test_partial_write_does_not_destroy_original(tmp_path: Path, monkeypatch):
    cfg = empty_app_config(root=tmp_path)
    paths = _roundtrip_paths(tmp_path)
    cfg.application.first_name = "Safe"
    save_config(cfg, **paths)

    import core.config as config_mod

    real_replace = os.replace
    calls = {"n": 0}

    def boom_replace(src, dst):
        calls["n"] += 1
        if Path(dst).name == "application_profile.yaml" and calls["n"] >= 1:
            # Simulate crash after tmp written but before replace for application
            raise OSError("simulated crash mid-replace")
        return real_replace(src, dst)

    monkeypatch.setattr(config_mod.os, "replace", boom_replace)
    cfg.application.first_name = "Corrupt"
    with pytest.raises(OSError):
        save_config(cfg, **paths)

    # Original application file must still be readable with Safe
    again = load_config(**paths, root=tmp_path, strip_placeholders=False)
    assert again.application.first_name == "Safe"


def test_config_service_reset_and_delete_all(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    from desktop.services import ConfigService

    svc = ConfigService()
    cfg = svc.load()
    cfg.application.first_name = "Anna"
    cfg.application.email = "anna.alpha@example.com"
    cfg.profile.qualifications.skills = [SourcedText(value="Excel", source=SOURCE_CV)]
    (svc.dirs["cvs"] / "cv.pdf").write_bytes(b"%PDF")
    (svc.dirs["data"] / "jobs.db").write_bytes(b"SQLite")
    (svc.dirs["logs"] / "app.log").write_text("log", encoding="utf-8")
    svc.save(cfg)

    emptied = svc.reset_to_empty_profile(clear_search_prefs=False)
    assert emptied.application.first_name == ""
    assert emptied.profile.qualifications.skills == []
    assert list(svc.dirs["cvs"].iterdir()) == []

    # Re-seed then wipe all local product data
    cfg = svc.load()
    cfg.application.first_name = "Bruno"
    svc.save(cfg)
    (svc.dirs["cvs"] / "b.pdf").write_bytes(b"%PDF")
    (svc.dirs["data"] / "jobs.db").write_bytes(b"SQLite")
    report = svc.delete_all_local_data()
    assert report["removed"]
    assert cfg.application  # object still in memory; disk empty
    assert not (svc.dirs["config"] / "application_profile.yaml").exists() or (
        load_config(
            profile_path=svc.profile_path,
            application_path=svc.application_path,
            settings_path=svc.settings_path,
            root=svc.dirs["root"],
            strip_placeholders=False,
        ).application.first_name
        == ""
    )
    # After wipe, load should bootstrap empty-safe examples without personal data
    again = svc.reload()
    assert again.application.first_name in ("",)


# ---------------------------------------------------------------------------
# Expanded unit matrix (PR20 target ~80 profile/config cases)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("field_name", [
    "first_name", "last_name", "street", "postal_code", "city", "email", "phone",
    "date_of_birth", "driving_license", "work_authorization", "notice_period",
    "earliest_start_date", "salary_expectation", "current_employment", "education",
    "work_experience", "languages", "willingness_to_travel", "willingness_to_relocate",
    "remote_preference", "linkedin_url", "portfolio_url",
])
def test_clear_each_application_text_field(field_name: str):
    app = ApplicationProfile(**{field_name: "Wert"})
    set_field_origin(app, field_name, SOURCE_CV)
    quals = QualificationsConfig()
    apply_profile_patch(
        app, quals, ProfilePatch(application={field_name: FieldPatch(op=PatchOp.CLEAR)})
    )
    expected = "DE" if field_name == "country" else ""
    if field_name == "country":
        app2 = ApplicationProfile(country="AT")
        apply_profile_patch(
            app2, quals, ProfilePatch(application={"country": FieldPatch(op=PatchOp.CLEAR)})
        )
        assert app2.country == "DE"
    else:
        assert getattr(app, field_name) == expected
        assert (app.field_origins or {}).get(field_name) == SOURCE_MANUAL


@pytest.mark.parametrize("field_name,value", [
    ("first_name", "Änna"),
    ("city", "Gießen"),
    ("street", "Straße ß"),
    ("salary_expectation", "50.000 € brutto"),
    ("languages", "Deutsch, Français"),
])
def test_set_unicode_values(field_name: str, value: str):
    app = ApplicationProfile()
    quals = QualificationsConfig()
    apply_profile_patch(
        app, quals, ProfilePatch(application={field_name: FieldPatch(op=PatchOp.SET, value=value)})
    )
    assert getattr(app, field_name) == value


@pytest.mark.parametrize("section", [
    "languages", "education", "work_experience", "certificates", "skills", "software", "driving_license",
])
def test_delete_each_qualification_section(section: str):
    quals = QualificationsConfig(
        skills=[SourcedText(value="X", source=SOURCE_CV)],
        software=[SourcedText(value="Y", source=SOURCE_CV)],
        languages=[LanguageEntry(language="Deutsch", level="C1", source=SOURCE_CV)],
        education=[EducationEntry(qualification="Abitur", source=SOURCE_CV)],
        work_experience=[ExperienceEntry(title="Job", company="Co", source=SOURCE_CV)],
        certificates=[],
        driving_license=[SourcedText(value="B", source=SOURCE_CV)],
    )
    # seed certificates if needed
    from core.config import CertificateEntry
    quals.certificates = [CertificateEntry(name="Z", source=SOURCE_CV)]
    app = ApplicationProfile(first_name="Keep")
    apply_profile_patch(
        app, quals, ProfilePatch(qualifications={section: FieldPatch(op=PatchOp.DELETE_SECTION)})
    )
    assert getattr(quals, section) == []
    assert app.first_name == "Keep"


def test_merge_field_patch_incoming_wins():
    from desktop.services.profile_patch import merge_field_patch
    a = FieldPatch(op=PatchOp.SET, value="A")
    b = FieldPatch(op=PatchOp.CLEAR)
    assert merge_field_patch(a, b).op == PatchOp.CLEAR
    assert merge_field_patch(b, FieldPatch(op=PatchOp.UNCHANGED)).op == PatchOp.CLEAR


def test_build_patches_absent_key_means_unchanged():
    app = ApplicationProfile(first_name="Anna", city="Berlin")
    patches = build_application_patches(app, {"city": "Hamburg"})
    assert "first_name" not in patches
    assert patches["city"].op == PatchOp.SET


def test_set_same_value_emits_unchanged_or_noop():
    app = ApplicationProfile(first_name="Anna")
    patches = build_application_patches(app, {"first_name": "Anna"})
    assert patches["first_name"].op == PatchOp.UNCHANGED


def test_validate_rejects_delete_section_on_application():
    bad = ProfilePatch(application={"first_name": FieldPatch(op=PatchOp.DELETE_SECTION)})
    assert validate_profile_patch(bad)


def test_validate_unknown_qualification_section():
    bad = ProfilePatch(qualifications={"nope": FieldPatch(op=PatchOp.CLEAR)})
    assert any("unknown" in e for e in validate_profile_patch(bad))


def test_normalize_list_empty_is_clear():
    op, val = normalize_patch_value([], kind="list")
    assert op == PatchOp.CLEAR
    assert val == []
    op2, val2 = normalize_patch_value(["  ", ""], kind="list")
    assert op2 == PatchOp.CLEAR
    op3, val3 = normalize_patch_value(["Excel", "  Word  "], kind="list")
    assert op3 == PatchOp.SET
    assert val3 == ["Excel", "Word"]


def test_cv_sync_fill_empty_true_fills_untagged():
    app = ApplicationProfile(languages="")
    quals = QualificationsConfig(
        languages=[LanguageEntry(language="Deutsch", level="C1", source=SOURCE_CV)]
    )
    sync_application_summaries(app, quals, fill_empty=True)
    assert "Deutsch" in app.languages
    assert (app.field_origins or {}).get("languages") == SOURCE_CV


def test_cv_sync_fill_empty_false_leaves_untagged_empty():
    app = ApplicationProfile(languages="")
    quals = QualificationsConfig(
        languages=[LanguageEntry(language="Deutsch", level="C1", source=SOURCE_CV)]
    )
    sync_application_summaries(app, quals, fill_empty=False)
    assert app.languages == ""


def test_untagged_nonempty_allows_cv_refresh():
    app = ApplicationProfile(languages="Alt")
    quals = QualificationsConfig(
        languages=[LanguageEntry(language="Neu", level="B1", source=SOURCE_CV)]
    )
    sync_application_summaries(app, quals, fill_empty=False)
    assert "Neu" in app.languages


# ---------------------------------------------------------------------------
# Roundtrip / deletion matrix (~30)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", [
    "A", "ä", "ß", "Straße 1", "a@b.c", "+49 1", "2020-01-01", "B", "EU",
])
def test_roundtrip_set_clear_set(tmp_path: Path, value: str):
    cfg = empty_app_config(root=tmp_path)
    paths = _roundtrip_paths(tmp_path)
    apply_profile_patch(
        cfg.application,
        cfg.profile.qualifications,
        ProfilePatch(application={"first_name": FieldPatch(op=PatchOp.SET, value=value)}),
    )
    save_config(cfg, **paths)
    loaded = load_config(**paths, root=tmp_path, strip_placeholders=False)
    assert loaded.application.first_name == value
    apply_profile_patch(
        loaded.application,
        loaded.profile.qualifications,
        ProfilePatch(application={"first_name": FieldPatch(op=PatchOp.CLEAR)}),
    )
    save_config(loaded, **paths)
    again = load_config(**paths, root=tmp_path, strip_placeholders=False)
    assert again.application.first_name == ""


def test_delete_profile_then_save_restart(tmp_path: Path):
    cfg = empty_app_config(root=tmp_path)
    paths = _roundtrip_paths(tmp_path)
    cfg.application.first_name = "X"
    cfg.profile.qualifications.skills = [SourcedText(value="Y", source=SOURCE_CV)]
    save_config(cfg, **paths)
    loaded = load_config(**paths, root=tmp_path, strip_placeholders=False)
    apply_profile_patch(
        loaded.application,
        loaded.profile.qualifications,
        ProfilePatch(delete_profile=True),
    )
    save_config(loaded, **paths)
    again = load_config(**paths, root=tmp_path, strip_placeholders=False)
    assert again.application.first_name == ""
    assert again.profile.qualifications.skills == []


def test_reset_keeps_search_titles(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    from desktop.services import ConfigService

    svc = ConfigService()
    cfg = svc.load()
    cfg.application.first_name = "Anna"
    cfg.profile.jobs.desired_titles = ["Sachbearbeiter", "Assistent"]
    svc.save(cfg)
    emptied = svc.reset_profile_and_documents(clear_search_prefs=False)
    assert emptied.application.first_name == ""
    assert emptied.profile.jobs.desired_titles == ["Sachbearbeiter", "Assistent"]


def test_wipe_creates_backup_hint(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    from desktop.services import ConfigService

    svc = ConfigService()
    cfg = svc.load()
    cfg.application.first_name = "Anna"
    svc.save(cfg)
    report = svc.delete_all_local_data()
    assert "removed" in report
    assert report.get("schema") == PATCH_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Hypothesis roundtrips
# ---------------------------------------------------------------------------


def test_hypothesis_normalize_text_roundtrip_ops():
    hypothesis = pytest.importorskip("hypothesis")
    from hypothesis import given, strategies as st

    @given(st.one_of(st.none(), st.text(max_size=40)))
    def _prop(raw):
        op, val = normalize_patch_value(raw, kind="text")
        if raw is None:
            assert op == PatchOp.UNCHANGED
        elif not str(raw).strip():
            assert op == PatchOp.CLEAR
        else:
            assert op == PatchOp.SET
            assert val == str(raw).strip()
            assert val  # non-empty

    _prop()


def test_hypothesis_set_clear_persist(tmp_path: Path):
    hypothesis = pytest.importorskip("hypothesis")
    from hypothesis import given, settings, strategies as st

    alphabet = "abcdefghijklmnopqrstuvwxyzäöüßÄÖÜ "
    strat = st.text(alphabet=alphabet, min_size=1, max_size=24).filter(lambda s: s.strip())

    @settings(max_examples=40, deadline=None)
    @given(strat)
    def _prop(name: str):
        root = tmp_path / repr(hash(name))
        root.mkdir(exist_ok=True)
        cfg = empty_app_config(root=root)
        paths = _roundtrip_paths(root)
        apply_profile_patch(
            cfg.application,
            cfg.profile.qualifications,
            ProfilePatch(application={"first_name": FieldPatch(op=PatchOp.SET, value=name.strip())}),
        )
        save_config(cfg, **paths)
        loaded = load_config(**paths, root=root, strip_placeholders=False)
        assert loaded.application.first_name == name.strip()
        apply_profile_patch(
            loaded.application,
            loaded.profile.qualifications,
            ProfilePatch(application={"first_name": FieldPatch(op=PatchOp.CLEAR)}),
        )
        save_config(loaded, **paths)
        again = load_config(**paths, root=root, strip_placeholders=False)
        assert again.application.first_name == ""

    _prop()
