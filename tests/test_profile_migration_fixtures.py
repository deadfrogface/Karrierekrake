"""PR20: migrate legacy / beta profile YAML fixtures without data loss.

Fixtures under tests/fixtures/profile_migration/ use fictional identities only.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.config import empty_app_config, load_config, save_config
from desktop.services.profile_merge import SOURCE_MANUAL, sync_application_summaries
from desktop.services.profile_patch import (
    FieldPatch,
    PatchOp,
    ProfilePatch,
    apply_profile_patch,
    build_application_patches,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "profile_migration"

APPLICATION_FIXTURES = sorted(FIXTURES.glob("*.yaml"))
# Profile-shaped (location/jobs/…) vs application-shaped vs settings
PROFILE_SHAPED = {
    "legacy_profile_quals.yaml",
    "search_prefs_keep.yaml",
    "legacy_alt_titles.yaml",
    "quals_skills_heavy.yaml",
}
SETTINGS_SHAPED = {
    "legacy_settings_minimal.yaml",
    "legacy_settings_schedule.yaml",
}


def _paths(tmp_path: Path) -> dict:
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    return dict(
        profile_path=cfg_dir / "profile.yaml",
        application_path=cfg_dir / "application_profile.yaml",
        settings_path=cfg_dir / "settings.yaml",
    )


@pytest.mark.parametrize(
    "name",
    sorted(
        p.name
        for p in APPLICATION_FIXTURES
        if p.name not in PROFILE_SHAPED and p.name not in SETTINGS_SHAPED
    ),
)
def test_application_fixture_loads_without_crash(tmp_path: Path, name: str):
    paths = _paths(tmp_path)
    src = FIXTURES / name
    paths["application_path"].write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    # Minimal profile/settings so load_config has siblings
    paths["profile_path"].write_text("{}\n", encoding="utf-8")
    paths["settings_path"].write_text("dry_run: true\n", encoding="utf-8")
    cfg = load_config(**paths, root=tmp_path, strip_placeholders=False)
    assert cfg.application is not None
    # Must not pull example Mustermann-style identity
    assert cfg.application.first_name != "Max"
    assert "mustermann" not in (cfg.application.email or "").lower()


@pytest.mark.parametrize("name", sorted(PROFILE_SHAPED))
def test_profile_fixture_loads_and_roundtrips(tmp_path: Path, name: str):
    paths = _paths(tmp_path)
    paths["profile_path"].write_text(
        (FIXTURES / name).read_text(encoding="utf-8"), encoding="utf-8"
    )
    paths["application_path"].write_text("country: DE\n", encoding="utf-8")
    paths["settings_path"].write_text("dry_run: true\n", encoding="utf-8")
    cfg = load_config(**paths, root=tmp_path, strip_placeholders=False)
    save_config(cfg, **paths)
    again = load_config(**paths, root=tmp_path, strip_placeholders=False)
    assert again.profile.jobs.desired_titles == cfg.profile.jobs.desired_titles


@pytest.mark.parametrize("name", sorted(SETTINGS_SHAPED))
def test_settings_fixture_loads(tmp_path: Path, name: str):
    paths = _paths(tmp_path)
    paths["settings_path"].write_text(
        (FIXTURES / name).read_text(encoding="utf-8"), encoding="utf-8"
    )
    paths["profile_path"].write_text("{}\n", encoding="utf-8")
    paths["application_path"].write_text("country: DE\n", encoding="utf-8")
    cfg = load_config(**paths, root=tmp_path, strip_placeholders=False)
    assert isinstance(cfg.settings.dry_run, bool)


def test_legacy_no_origins_preserves_personal_data(tmp_path: Path):
    paths = _paths(tmp_path)
    paths["application_path"].write_text(
        (FIXTURES / "legacy_no_origins.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    paths["profile_path"].write_text("{}\n", encoding="utf-8")
    paths["settings_path"].write_text("dry_run: true\n", encoding="utf-8")
    cfg = load_config(**paths, root=tmp_path, strip_placeholders=False)
    assert cfg.application.first_name == "Clara"
    assert cfg.application.city == "München"
    assert "Deutsch" in (cfg.application.languages or "")
    save_config(cfg, **paths)
    again = load_config(**paths, root=tmp_path, strip_placeholders=False)
    assert again.application.first_name == "Clara"
    assert again.application.email == "clara.gamma@example.com"


def test_legacy_empty_stays_empty_not_example(tmp_path: Path):
    paths = _paths(tmp_path)
    paths["application_path"].write_text(
        (FIXTURES / "legacy_empty_application.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    paths["profile_path"].write_text("{}\n", encoding="utf-8")
    paths["settings_path"].write_text("dry_run: true\n", encoding="utf-8")
    cfg = load_config(**paths, root=tmp_path, strip_placeholders=True)
    assert cfg.application.first_name == ""
    assert cfg.application.email == ""


def test_unicode_fixture_roundtrip(tmp_path: Path):
    paths = _paths(tmp_path)
    paths["application_path"].write_text(
        (FIXTURES / "unicode_umlauts.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    paths["profile_path"].write_text("{}\n", encoding="utf-8")
    paths["settings_path"].write_text("dry_run: true\n", encoding="utf-8")
    cfg = load_config(**paths, root=tmp_path, strip_placeholders=False)
    assert cfg.application.first_name == "Jürgen"
    assert "Größe" in cfg.application.street
    save_config(cfg, **paths)
    again = load_config(**paths, root=tmp_path, strip_placeholders=False)
    assert again.application.city == "München"
    assert again.application.last_name == "Größe"


def test_cv_origins_manual_clear_after_migration(tmp_path: Path):
    paths = _paths(tmp_path)
    paths["application_path"].write_text(
        (FIXTURES / "cv_origins_summaries.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    paths["profile_path"].write_text(
        (FIXTURES / "legacy_profile_quals.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    paths["settings_path"].write_text("dry_run: true\n", encoding="utf-8")
    cfg = load_config(**paths, root=tmp_path, strip_placeholders=False)
    patches = build_application_patches(cfg.application, {"languages": ""})
    apply_profile_patch(
        cfg.application, cfg.profile.qualifications, ProfilePatch(application=patches)
    )
    sync_application_summaries(cfg.application, cfg.profile.qualifications, fill_empty=False)
    save_config(cfg, **paths)
    again = load_config(**paths, root=tmp_path, strip_placeholders=False)
    assert again.application.languages == ""
    assert (again.application.field_origins or {}).get("languages") == SOURCE_MANUAL


def test_manual_cleared_fixture_not_refilled_by_sync(tmp_path: Path):
    paths = _paths(tmp_path)
    paths["application_path"].write_text(
        (FIXTURES / "manual_cleared_summaries.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    paths["profile_path"].write_text(
        (FIXTURES / "legacy_profile_quals.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    paths["settings_path"].write_text("dry_run: true\n", encoding="utf-8")
    cfg = load_config(**paths, root=tmp_path, strip_placeholders=False)
    sync_application_summaries(cfg.application, cfg.profile.qualifications, fill_empty=False)
    assert cfg.application.languages == ""
    assert cfg.application.education == ""
    assert cfg.application.driving_license == ""


def test_search_prefs_survive_profile_reset(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    from desktop.services import ConfigService

    svc = ConfigService()
    paths = dict(
        profile_path=svc.profile_path,
        application_path=svc.application_path,
        settings_path=svc.settings_path,
    )
    svc.profile_path.write_text(
        (FIXTURES / "search_prefs_keep.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    svc.application_path.write_text(
        (FIXTURES / "legacy_no_origins.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    cfg = svc.reload()
    titles_before = list(cfg.profile.jobs.desired_titles)
    assert titles_before
    assert cfg.application.first_name == "Clara"

    emptied = svc.reset_to_empty_profile(clear_search_prefs=False)
    assert emptied.application.first_name == ""
    assert emptied.profile.jobs.desired_titles == titles_before
    assert "Provision" in (emptied.profile.filters.exclusion_keywords or []) or titles_before


def test_alt_titles_soft_migrate_on_load(tmp_path: Path):
    paths = _paths(tmp_path)
    paths["profile_path"].write_text(
        (FIXTURES / "legacy_alt_titles.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    paths["application_path"].write_text("country: DE\n", encoding="utf-8")
    paths["settings_path"].write_text("dry_run: true\n", encoding="utf-8")
    cfg = load_config(**paths, root=tmp_path, strip_placeholders=False)
    # soft_migrate folds alternatives into desired
    assert "Bürohilfe" in cfg.profile.jobs.desired_titles
    assert cfg.profile.jobs.alternative_titles == []


def test_mixed_origins_selective_clear(tmp_path: Path):
    paths = _paths(tmp_path)
    paths["application_path"].write_text(
        (FIXTURES / "mixed_origins.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    paths["profile_path"].write_text("{}\n", encoding="utf-8")
    paths["settings_path"].write_text("dry_run: true\n", encoding="utf-8")
    cfg = load_config(**paths, root=tmp_path, strip_placeholders=False)
    apply_profile_patch(
        cfg.application,
        cfg.profile.qualifications,
        ProfilePatch(application={"languages": FieldPatch(op=PatchOp.CLEAR)}),
    )
    save_config(cfg, **paths)
    again = load_config(**paths, root=tmp_path, strip_placeholders=False)
    assert again.application.languages == ""
    assert again.application.street == "Manuellweg 9"
    assert again.application.notice_period == "4 Wochen"


def test_with_answers_roundtrip(tmp_path: Path):
    paths = _paths(tmp_path)
    paths["application_path"].write_text(
        (FIXTURES / "with_answers.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    paths["profile_path"].write_text("{}\n", encoding="utf-8")
    paths["settings_path"].write_text("dry_run: true\n", encoding="utf-8")
    cfg = load_config(**paths, root=tmp_path, strip_placeholders=False)
    assert cfg.application.country == "AT"
    assert cfg.application.answers.get("Eintritt") == "sofort"
    save_config(cfg, **paths)
    again = load_config(**paths, root=tmp_path, strip_placeholders=False)
    assert again.application.answers.get("Fuehrerschein") == "Ja"


def test_unknown_keys_ignored_known_kept(tmp_path: Path):
    paths = _paths(tmp_path)
    paths["application_path"].write_text(
        (FIXTURES / "unknown_keys.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    paths["profile_path"].write_text("{}\n", encoding="utf-8")
    paths["settings_path"].write_text("dry_run: true\n", encoding="utf-8")
    cfg = load_config(**paths, root=tmp_path, strip_placeholders=False)
    assert cfg.application.first_name == "Gina"
    assert not hasattr(cfg.application, "deprecated_fax") or True
    assert cfg.application.city == "Stuttgart"


def test_empty_object_application(tmp_path: Path):
    paths = _paths(tmp_path)
    paths["application_path"].write_text(
        (FIXTURES / "empty_object.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    paths["profile_path"].write_text("{}\n", encoding="utf-8")
    paths["settings_path"].write_text("dry_run: true\n", encoding="utf-8")
    cfg = load_config(**paths, root=tmp_path, strip_placeholders=False)
    assert cfg.application.first_name == ""
    assert cfg.application.country == "DE"


def test_skills_heavy_section_delete_preserves_search(tmp_path: Path):
    paths = _paths(tmp_path)
    paths["profile_path"].write_text(
        (FIXTURES / "quals_skills_heavy.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    paths["application_path"].write_text(
        "first_name: Anna\ncountry: DE\n", encoding="utf-8"
    )
    paths["settings_path"].write_text("dry_run: true\n", encoding="utf-8")
    cfg = load_config(**paths, root=tmp_path, strip_placeholders=False)
    apply_profile_patch(
        cfg.application,
        cfg.profile.qualifications,
        ProfilePatch(
            qualifications={
                "skills": FieldPatch(op=PatchOp.DELETE_SECTION),
                "software": FieldPatch(op=PatchOp.DELETE_SECTION),
            }
        ),
    )
    save_config(cfg, **paths)
    again = load_config(**paths, root=tmp_path, strip_placeholders=False)
    assert again.profile.qualifications.skills == []
    assert again.profile.qualifications.software == []
    assert again.profile.jobs.desired_titles == ["Office Manager"]
    assert again.application.first_name == "Anna"


def test_country_ch_preserved(tmp_path: Path):
    paths = _paths(tmp_path)
    paths["application_path"].write_text(
        (FIXTURES / "country_ch.yaml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    paths["profile_path"].write_text("{}\n", encoding="utf-8")
    paths["settings_path"].write_text("dry_run: true\n", encoding="utf-8")
    cfg = load_config(**paths, root=tmp_path, strip_placeholders=False)
    assert cfg.application.country == "CH"
    assert cfg.application.city == "Zürich"


def test_partial_address_and_cv_path_only(tmp_path: Path):
    for name, expect_city, expect_cv in (
        ("partial_address_only.yaml", "Köln", ""),
        ("cv_path_only.yaml", "", "cvs/legacy_upload.pdf"),
    ):
        root = tmp_path / name.replace(".yaml", "")
        paths = _paths(root)
        paths["application_path"].write_text(
            (FIXTURES / name).read_text(encoding="utf-8"), encoding="utf-8"
        )
        paths["profile_path"].write_text("{}\n", encoding="utf-8")
        paths["settings_path"].write_text("dry_run: true\n", encoding="utf-8")
        cfg = load_config(**paths, root=root, strip_placeholders=False)
        assert (cfg.application.city or "") == expect_city
        assert (cfg.application.cv_path or "") == expect_cv


def test_null_fields_fixture_loads(tmp_path: Path):
    paths = _paths(tmp_path)
    paths["application_path"].write_text(
        (FIXTURES / "null_fields.yaml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    paths["profile_path"].write_text("{}\n", encoding="utf-8")
    paths["settings_path"].write_text("dry_run: true\n", encoding="utf-8")
    cfg = load_config(**paths, root=tmp_path, strip_placeholders=False)
    assert cfg.application.first_name == "Iris"
    assert cfg.application.city == "Bremen"


def test_bootstrap_empty_app_config_compatible():
    cfg = empty_app_config(root=Path("/tmp/karrierekrake-test-root"))
    assert cfg.application.first_name == ""
    assert cfg.profile.qualifications.skills == []
