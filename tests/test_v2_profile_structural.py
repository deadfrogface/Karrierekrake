"""Structural Profil rebuild — demo card layout + drawers, no endless form."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication

from desktop.i18n import i18n, tr
from desktop.pages.profile import ProfilePage
from desktop.services import ConfigService


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def config_service(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    from desktop import paths as paths_mod

    def fake_dirs():
        root = tmp_path / "Karrierekrake"
        dirs = {
            "root": root,
            "config": root / "config",
            "data": root / "data",
            "logs": root / "logs",
            "browser_profile": root / "browser_profile",
            "browsers": root / "browsers",
            "cvs": root / "cvs",
            "cache": root / "cache",
            "cover_letters": root / "cover_letters",
        }
        for p in dirs.values():
            p.mkdir(parents=True, exist_ok=True)
        return dirs

    monkeypatch.setattr(paths_mod, "ensure_app_dirs", fake_dirs)
    monkeypatch.setattr("desktop.services.ensure_app_dirs", fake_dirs)
    return ConfigService()


def test_profile_uses_demo_cards_not_endless_form(qapp, config_service):
    i18n.set_language("de")
    page = ProfilePage(config_service)
    page.load_from_config()
    assert page.card_personal.isVisibleTo(page) or not page.card_personal.isHidden()
    assert page.import_cv_btn.text() == tr("profile.import_from_cv")
    assert page.card_personal.title_label.text() == tr("profile.card_personal")
    assert page.card_career.title_label.text() == tr("profile.card_career")
    # Editors exist for capability but are not the primary surface
    assert page.applicant.isHidden()
    assert page.save_btn.isHidden()


def test_profile_cards_reflect_saved_identity(qapp, config_service, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.StandardButton.Ok)
    i18n.set_language("de")
    page = ProfilePage(config_service)
    page.load_from_config()
    page.applicant.first_name.setText("Damiano")
    page.applicant.last_name.setText("Rossi")
    page.save()
    page.load_from_config()
    values = [item.value.text() for item in page._personal_items]
    assert "Damiano" in values
    assert "Rossi" in values
