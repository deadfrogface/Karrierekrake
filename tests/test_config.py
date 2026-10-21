"""Profile / config parsing tests."""

from pathlib import Path

from core.config import load_config


def test_load_example_configs():
    root = Path(__file__).resolve().parents[1]
    cfg = load_config(
        profile_path=root / "config" / "profile.yaml.example",
        application_path=root / "config" / "application_profile.yaml.example",
        settings_path=root / "config" / "settings.yaml.example",
    )
    assert cfg.profile.location.max_distance_km == 20
    assert cfg.settings.dry_run is True
    # Teamlead decision (PR144, 18.10.2026): default sources are only
    # Bundesagentur and Indeed; company_sites is opt-in.
    assert cfg.settings.enabled_sources == ["bundesagentur", "indeed"]
    assert cfg.application.first_name == ""
    assert cfg.application.email == ""


def test_existing_source_selection_is_not_extended_by_company_sites(tmp_path):
    """Formerly a one-time migration appended company_sites to every existing
    selection; that is revoked (Teamlead): a legacy selection stays as written."""
    settings = tmp_path / "settings.yaml"
    settings.write_text("enabled_sources: [bundesagentur, indeed]\n", encoding="utf-8")
    cfg = load_config(settings_path=settings)
    assert cfg.settings.enabled_sources == ["bundesagentur", "indeed"]
    settings.write_text("enabled_sources: [bundesagentur, indeed]\n"
                        "company_web_source_migrated: true\n", encoding="utf-8")
    cfg = load_config(settings_path=settings)
    assert cfg.settings.enabled_sources == ["bundesagentur", "indeed"]


def test_fresh_default_settings_enable_only_bundesagentur_and_indeed():
    from core.config import SettingsConfig

    assert SettingsConfig().enabled_sources == ["bundesagentur", "indeed"]


def test_legacy_settings_without_source_choice_get_only_ba_and_indeed(tmp_path):
    settings = tmp_path / "settings.yaml"
    settings.write_text("dry_run: true\n", encoding="utf-8")  # no enabled_sources, no migration flag
    cfg = load_config(settings_path=settings)
    assert cfg.settings.enabled_sources == ["bundesagentur", "indeed"]


def test_missing_settings_file_falls_back_to_only_ba_and_indeed(tmp_path):
    cfg = load_config(settings_path=tmp_path / "does-not-exist.yaml")
    assert cfg.settings.enabled_sources == ["bundesagentur", "indeed"]


def test_explicit_company_sites_opt_in_is_preserved(tmp_path):
    settings = tmp_path / "settings.yaml"
    for raw, expected in (
        ("enabled_sources: [bundesagentur, indeed, company_sites]\n",
         ["bundesagentur", "indeed", "company_sites"]),
        ("enabled_sources: [company_sites]\ncompany_web_source_migrated: true\n", ["company_sites"]),
        ("enabled_sources: [bundesagentur, company_sites]\n", ["bundesagentur", "company_sites"]),
    ):
        settings.write_text(raw, encoding="utf-8")
        assert load_config(settings_path=settings).settings.enabled_sources == expected, raw


def test_explicit_empty_source_choice_is_preserved(tmp_path):
    settings = tmp_path / "settings.yaml"
    settings.write_text("enabled_sources: []\n", encoding="utf-8")
    assert load_config(settings_path=settings).settings.enabled_sources == []


def test_saved_default_round_trip_keeps_only_ba_and_indeed(tmp_path):
    from core.config import save_config

    cfg = load_config(settings_path=tmp_path / "missing.yaml")
    target = tmp_path / "settings.yaml"
    save_config(cfg, profile_path=tmp_path / "profile.yaml",
                application_path=tmp_path / "application_profile.yaml", settings_path=target)
    reloaded = load_config(profile_path=tmp_path / "profile.yaml",
                           application_path=tmp_path / "application_profile.yaml", settings_path=target)
    assert reloaded.settings.enabled_sources == ["bundesagentur", "indeed"]
