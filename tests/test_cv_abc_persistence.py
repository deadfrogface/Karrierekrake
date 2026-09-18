"""Fictional CV fixtures A→B→C replace + YAML persistence restart tests."""

from __future__ import annotations

from pathlib import Path

from core.config import ApplicationProfile, QualificationsConfig, load_config, save_config
from core.cv_parser import normalize_driving_license, parse_cv_text, parsed_to_qualifications
from desktop.services.profile_merge import (
    SOURCE_CV,
    apply_personal_updates,
    personal_from_parsed,
    plan_personal_import,
    replace_qualifications,
    sync_application_summaries,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _apply_replace(cv_name: str, app: ApplicationProfile, quals: QualificationsConfig):
    text = (FIXTURES / cv_name).read_text(encoding="utf-8")
    parsed = parse_cv_text(text)
    incoming = parsed_to_qualifications(parsed)
    plan = plan_personal_import(app, personal_from_parsed(parsed), mode="replace")
    apply_personal_updates(app, plan.updates, source=SOURCE_CV)
    quals = replace_qualifications(quals, incoming)
    sync_application_summaries(app, quals, fill_empty=True)
    return app, quals, parsed


def test_fixtures_abc_distinct_layouts():
    pa = personal_from_parsed(parse_cv_text((FIXTURES / "cv_a.txt").read_text(encoding="utf-8")))
    pb = personal_from_parsed(parse_cv_text((FIXTURES / "cv_b.txt").read_text(encoding="utf-8")))
    pc = personal_from_parsed(parse_cv_text((FIXTURES / "cv_c.txt").read_text(encoding="utf-8")))
    assert pa["first_name"] == "Anna"
    assert pb["first_name"] == "Bruno"
    assert pc["first_name"] == "Clara"
    assert pa["city"] == "Berlin"
    assert pb["city"] == "München"
    assert pc["city"] == "Nürnberg"


def test_driving_license_normalized_to_classes():
    assert normalize_driving_license("Klasse B (PKW)") == ["B"]
    assert normalize_driving_license("Klasse B, BE") == ["B", "BE"]
    assert normalize_driving_license(["Führerschein", "BE"]) == ["BE"]
    parsed_c = parse_cv_text((FIXTURES / "cv_c.txt").read_text(encoding="utf-8"))
    codes = [d["value"] for d in parsed_c["driving_license"]]
    assert codes == ["B", "BE"]
    assert "Führerschein" not in codes


def test_heading_never_becomes_value():
    text = """
Test Person
test.person@example.com

Führerschein
Führerschein

Sprachen
Deutsch – C1
"""
    parsed = parse_cv_text(text)
    assert all(v.get("value") != "Führerschein" for v in parsed["driving_license"])


def test_replace_a_to_b_to_c_clears_previous():
    app = ApplicationProfile()
    quals = QualificationsConfig()
    app, quals, _ = _apply_replace("cv_a.txt", app, quals)
    assert app.first_name == "Anna"
    assert any(l.language == "Französisch" for l in quals.languages)

    app, quals, _ = _apply_replace("cv_b.txt", app, quals)
    assert app.first_name == "Bruno"
    assert not any(l.language == "Französisch" for l in quals.languages)
    assert any(l.language == "Spanisch" for l in quals.languages)
    assert not any("DATEV" in s for s in quals.software_values())

    app, quals, parsed = _apply_replace("cv_c.txt", app, quals)
    assert app.first_name == "Clara"
    assert app.last_name == "Gamma"
    assert app.city == "Nürnberg"
    assert "Bruno" not in app.full_name
    assert "München" not in (app.city or "")
    assert not any(l.language == "Spanisch" for l in quals.languages)
    assert any(l.language == "Italienisch" for l in quals.languages)
    assert not any("Python" in s for s in quals.software_values())
    assert any("Jira" in s for s in quals.software_values())
    assert any("Projektkoordinatorin" in e.title for e in quals.work_experience)
    assert not any("Softwareentwickler" in e.title for e in quals.work_experience)
    assert quals.driving_values() == ["B", "BE"]
    assert parsed["confidence"]["languages"] == "high"


def test_abc_persistence_survives_reload(tmp_path: Path):
    app = ApplicationProfile()
    quals = QualificationsConfig()
    for name in ("cv_a.txt", "cv_b.txt", "cv_c.txt"):
        app, quals, _ = _apply_replace(name, app, quals)

    root = Path(__file__).resolve().parents[1]
    cfg = load_config(
        profile_path=root / "config" / "profile.yaml.example",
        application_path=root / "config" / "application_profile.yaml.example",
        settings_path=root / "config" / "settings.yaml.example",
        root=tmp_path,
    )
    cfg.application = app
    cfg.profile.qualifications = quals
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir(exist_ok=True)
    save_config(
        cfg,
        profile_path=cfg_dir / "profile.yaml",
        application_path=cfg_dir / "application_profile.yaml",
        settings_path=cfg_dir / "settings.yaml",
    )

    # Simulate app restart
    again = load_config(
        profile_path=cfg_dir / "profile.yaml",
        application_path=cfg_dir / "application_profile.yaml",
        settings_path=cfg_dir / "settings.yaml",
        root=tmp_path,
        strip_placeholders=False,
    )
    assert again.application.first_name == "Clara"
    assert again.application.city == "Nürnberg"
    assert any(l.language == "Italienisch" for l in again.profile.qualifications.languages)
    assert not any(l.language == "Französisch" for l in again.profile.qualifications.languages)
    assert not any(l.language == "Spanisch" for l in again.profile.qualifications.languages)
    assert again.profile.qualifications.driving_values() == ["B", "BE"]
