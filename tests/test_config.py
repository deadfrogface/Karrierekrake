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
    assert "bundesagentur" in cfg.settings.enabled_sources
    assert "company_sites" in cfg.settings.enabled_sources
    assert cfg.application.first_name == ""
    assert cfg.application.email == ""


def test_existing_source_selection_gets_one_time_company_search_migration(tmp_path):
    settings = tmp_path / "settings.yaml"
    settings.write_text("enabled_sources: [bundesagentur, indeed]\n", encoding="utf-8")
    cfg = load_config(settings_path=settings)
    assert cfg.settings.enabled_sources == ["bundesagentur", "indeed", "company_sites"]
    settings.write_text("enabled_sources: [bundesagentur, indeed]\n"
                        "company_web_source_migrated: true\n", encoding="utf-8")
    cfg = load_config(settings_path=settings)
    assert cfg.settings.enabled_sources == ["bundesagentur", "indeed"]
