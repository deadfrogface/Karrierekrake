"""Branding, status labels, and demo seed helpers."""

from __future__ import annotations

from pathlib import Path

from desktop.branding import (
    COLOR_NAVY,
    COLOR_ORANGE,
    COLOR_TEAL,
    DATA_DIR_NAME,
    DISPLAY_NAME,
    TAGLINE_DE,
    icon_path,
    logo_path,
)
from desktop.demo_data import seed_demo_database
from desktop.i18n import TRANSLATIONS, i18n
from desktop.status_labels import status_badge_kind, status_label
from desktop.theme import stylesheet_for
from desktop.wizard import FirstRunWizard


def test_display_brand_changeable_without_data_dir_rename():
    assert DISPLAY_NAME == "Karrierekrake"
    assert DATA_DIR_NAME == "Karrierekrake"
    assert TAGLINE_DE.startswith("FINDE.")
    assert COLOR_NAVY == "#132238"
    assert COLOR_TEAL == "#18A999"
    assert COLOR_ORANGE == "#E86A45"
    assert icon_path(256) is not None
    assert icon_path(256).is_file()
    assert logo_path(master=True) is not None and logo_path(master=True).is_file()
    assert (Path("assets/brand/app.ico")).is_file()
    assert (Path("assets/brand/social-preview.png")).is_file()
    assert (Path("assets/brand/karrierekrake-app-icon-master.png")).is_file()
    assert (Path("assets/brand/karrierekrake-logo-master.png")).is_file()
    for size in (16, 24, 32, 48, 64, 128, 256, 512, 1024):
        p = Path(f"assets/brand/icons/icon-{size}.png")
        assert p.is_file(), p


def test_no_user_facing_stellenanker_strings():
    for lang, table in TRANSLATIONS.items():
        blob = " ".join(table.values()).lower()
        assert "stellenanker" not in blob, lang
    readme = Path("README.md").read_text(encoding="utf-8").lower()
    assert "stellenanker" not in readme
    assert "karrierekrake" in readme


def test_status_labels_map_without_changing_enums():
    i18n.set_language("de")
    assert status_label("needs_review") == "Prüfung nötig"
    assert status_label("applied") == "Beworben"
    assert status_badge_kind("failed") == "danger"
    i18n.set_language("en")
    assert status_label("needs_review") == "Needs review"


def test_new_i18n_keys_present_both_languages():
    for key in (
        "btn.find_jobs",
        "btn.prepare_application",
        "wizard.step_cv_title",
        "wizard.cta_find_jobs",
        "settings.advanced",
        "status_label.captcha",
        "brand.tagline",
        "about.title",
        "about.open",
        "about.tech",
    ):
        assert key in TRANSLATIONS["de"]
        assert key in TRANSLATIONS["en"]
    assert set(TRANSLATIONS["de"]) == set(TRANSLATIONS["en"])
    assert TRANSLATIONS["de"]["app.name"] == "Karrierekrake"
    assert TRANSLATIONS["en"]["app.name"] == "Karrierekrake"


def test_wizard_has_four_pages(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from desktop.services import ConfigService

    app = QApplication.instance() or QApplication([])
    wiz = FirstRunWizard(ConfigService())
    assert len(wiz.pageIds()) == 4
    assert hasattr(wiz, "integrations")
    wiz.close()
    _ = app


def test_stylesheets_include_design_tokens():
    light = stylesheet_for("light")
    dark = stylesheet_for("dark")
    assert "HeroCard" in light and "HeroCard" in dark
    assert "PrimaryButton" in light
    assert COLOR_TEAL in light or COLOR_TEAL.lower() in light.lower()
    assert COLOR_NAVY in light
    assert light != dark


def test_demo_seed_is_fictional(tmp_path):
    db = tmp_path / "demo.db"
    n = seed_demo_database(db)
    assert n >= 3
    from core.database import Database

    jobs = Database(db).list_jobs(limit=50)
    assert any("Nordlicht" in (j.company or "") for j in jobs)
    assert all("example.com" in (j.url or "") for j in jobs)


def test_packaging_spec_embeds_icon_and_brand_assets():
    spec = Path("packaging/Karrierekrake.spec").read_text(encoding="utf-8")
    assert "assets" in spec and "brand" in spec
    assert "icon=_ICON" in spec or "icon=_ICON" in spec.replace(" ", "")
