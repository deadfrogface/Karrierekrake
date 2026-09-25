"""Profil speichern baut die Karten genau einmal auf.

Auf dem Stand mit direktem ``refresh_cards()`` plus ``refresh_all()`` ist
dieser Test rot, weil ``load_from_config()`` die Karten ein zweites Mal baut.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication, QMessageBox, QVBoxLayout, QWidget

from core.geo_dataset import get_geo_dataset_manager, reset_geo_dataset_manager_for_tests
from core.geo_resolve import reset_pgeocode_index_for_tests
from desktop.i18n import i18n
from desktop.pages.profile import ProfilePage
from desktop.services import ConfigService


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def geo_ready(tmp_path, monkeypatch):
    reset_geo_dataset_manager_for_tests()
    reset_pgeocode_index_for_tests()
    monkeypatch.setenv("KARRIEREKRAKE_GEO_DATA_DIR", str(tmp_path / "geo_active"))
    info = get_geo_dataset_manager().ensure_active()
    assert info.valid, info.message
    yield
    reset_geo_dataset_manager_for_tests()
    reset_pgeocode_index_for_tests()


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
        for path in dirs.values():
            path.mkdir(parents=True, exist_ok=True)
        return dirs

    monkeypatch.setattr(paths_mod, "ensure_app_dirs", fake_dirs)
    monkeypatch.setattr("desktop.services.ensure_app_dirs", fake_dirs)
    return ConfigService()


class _Host(QWidget):
    """Fenster mit ``refresh_all``, wie das Hauptfenster es anbietet."""

    def __init__(self, page: ProfilePage) -> None:
        super().__init__()
        self.profile = page
        layout = QVBoxLayout(self)
        layout.addWidget(page)

    def refresh_all(self) -> None:
        self.profile.load_from_config()


def test_save_builds_cards_once_and_shows_one_dialog(qapp, config_service, geo_ready, monkeypatch):
    i18n.set_language("de")
    page = ProfilePage(config_service)
    host = _Host(page)
    host.show()
    qapp.processEvents()
    page.load_from_config()

    calls = {"cards": 0}
    original = page.refresh_cards

    def _counted() -> None:
        calls["cards"] += 1
        original()

    page.refresh_cards = _counted  # type: ignore[method-assign]
    dialogs: list[str] = []

    def _information(*args, **kwargs):
        text = args[2] if len(args) > 2 else ""
        dialogs.append(str(text))
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr("desktop.pages.profile.QMessageBox.information", _information)
    monkeypatch.setattr(
        "desktop.pages.profile.QMessageBox.warning",
        lambda *args, **kwargs: pytest.fail(f"warning: {args!r}"),
    )

    page.applicant.city.setText("Berlin")
    page.applicant.postal_code.setText("")
    page.applicant.street.setText("Alexanderplatz 1")
    page.applicant.app_country.setText("DE")
    page.save_btn.click()
    qapp.processEvents()

    assert calls["cards"] == 1
    assert dialogs == ["Gespeichert."]
    values = [item.value.text() for item in page._personal_items]
    assert any("Berlin" in value for value in values)
    assert "aufgelöst" in page.home_status.text()
    assert "nicht prüfbar" not in page.home_status.text()
    assert not page.home_status.isHidden()
    loc = config_service.load().profile.location
    assert "Berlin" in (loc.city or loc.home_address)
    assert loc.home_latitude is None
