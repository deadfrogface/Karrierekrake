"""Shared background load of the DACH postal/place index."""

from __future__ import annotations

import os
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication, QLabel, QMessageBox, QVBoxLayout, QWidget

from core.config import LocationConfig
from core.geo_dataset import get_geo_dataset_manager, reset_geo_dataset_manager_for_tests
from core.geo_normalize import normalize_place_fields
from core.geo_resolve import (
    bind_ui_thread,
    hold_geo_preload_for_tests,
    preload_geo_index_async,
    reset_pgeocode_index_for_tests,
    resolve_city_pgeocode,
    resolve_place,
)
from core.location import home_location_notice
from desktop.i18n import i18n
from desktop.pages.dashboard import bind_home_notice_label
from desktop.pages.profile import ProfilePage
from desktop.services import ConfigService

import core.geo_resolve as geo_resolve


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


def _wait_thread(thread: threading.Thread | None) -> None:
    assert thread is not None
    thread.join(timeout=30)
    assert not thread.is_alive()


def test_preload_runs_in_the_background(geo_ready):
    thread = preload_geo_index_async()
    assert thread is not None
    assert thread is not threading.current_thread()
    assert thread.ident != threading.get_ident()
    _wait_thread(thread)
    assert "DE" in geo_resolve._pgeocode_index
    assert "AT" in geo_resolve._pgeocode_index
    assert "CH" in geo_resolve._pgeocode_index


def test_callers_share_one_nominatim_instance(geo_ready):
    _wait_thread(preload_geo_index_async())
    first = geo_resolve._pgeocode_nominatim("DE")
    second = geo_resolve._pgeocode_nominatim("DE")
    assert first is not None and first is second
    seen: dict[str, object] = {}

    def _other() -> None:
        seen["nom"] = geo_resolve._pgeocode_nominatim("DE")

    worker = threading.Thread(target=_other)
    worker.start()
    worker.join(timeout=10)
    assert seen["nom"] is first


def test_ui_thread_does_not_false_resolve_while_the_index_loads(qapp, geo_ready):
    i18n.set_language("de")
    hold = threading.Event()
    hold_geo_preload_for_tests(hold)
    bind_ui_thread()
    thread = preload_geo_index_async()
    assert thread is not None
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline and not thread.is_alive():
        time.sleep(0.01)
    assert thread.is_alive()

    munich = LocationConfig(
        home_address="Leopoldstraße 1, 80802 München",
        city="München",
        postal_code="80802",
        country="DE",
    )
    loading = home_location_notice(munich)
    assert loading.status != "resolved"
    assert loading.ask_postal is True
    assert munich.home_latitude is None and munich.home_longitude is None

    halle = LocationConfig(home_address="Halle", city="Halle", postal_code="", country="DE")
    while_loading = home_location_notice(halle)
    assert while_loading.status != "resolved"
    label = QLabel()
    bind_home_notice_label(label, while_loading)
    assert label.isVisible()
    assert "aufgelöst" not in label.text()
    assert "Postleitzahl" in label.text()

    hold.set()
    _wait_thread(thread)

    ready = home_location_notice(
        LocationConfig(
            home_address="Leopoldstraße 1, 80802 München",
            city="München",
            postal_code="80802",
            country="DE",
        )
    )
    assert ready.status == "resolved"
    halle_done = resolve_city_pgeocode("Halle", "DE")
    assert halle_done.status == "AMBIGUOUS"
    assert halle_done.latitude is None and halle_done.longitude is None


def test_other_thread_waits_for_the_same_instance(geo_ready):
    hold = threading.Event()
    hold_geo_preload_for_tests(hold)
    loader = preload_geo_index_async()
    assert loader is not None
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline and not loader.is_alive():
        time.sleep(0.01)
    assert loader.is_alive()
    seen: dict[str, object] = {}

    def _wait_for_index() -> None:
        seen["nom"] = geo_resolve._pgeocode_nominatim("DE")

    waiter = threading.Thread(target=_wait_for_index)
    waiter.start()
    time.sleep(0.1)
    assert waiter.is_alive()
    hold.set()
    waiter.join(timeout=30)
    _wait_thread(loader)
    assert seen["nom"] is geo_resolve._pgeocode_nominatim("DE")


def test_repeated_resolve_hits_the_postal_table_once(geo_ready):
    _wait_thread(preload_geo_index_async())
    nom = geo_resolve._pgeocode_nominatim("DE")
    calls = {"n": 0}
    original = nom.query_postal_code

    def _counted(code):
        calls["n"] += 1
        return original(code)

    nom.query_postal_code = _counted
    place = normalize_place_fields(postal_code="10115", city="Berlin", country_code="DE")
    first = resolve_place(place, allow_network=False)
    second = resolve_place(place, allow_network=False)
    assert first.status == "RESOLVED"
    assert second is first
    assert calls["n"] == 1
    assert geo_resolve.CITY_SPREAD_MAX_KM == 35.0


class _Host(QWidget):
    def __init__(self, page: ProfilePage) -> None:
        super().__init__()
        self.profile = page
        layout = QVBoxLayout(self)
        layout.addWidget(page)

    def refresh_all(self) -> None:
        self.profile.load_from_config()


def test_profile_save_resolves_geo_once(qapp, config_service, geo_ready, monkeypatch):
    i18n.set_language("de")
    _wait_thread(preload_geo_index_async())
    page = ProfilePage(config_service)
    host = _Host(page)
    host.show()
    qapp.processEvents()
    calls = {"postal": 0, "city": 0, "cards": 0}
    original_postal = geo_resolve.resolve_postal_pgeocode
    original_city = geo_resolve.resolve_city_pgeocode
    original_cards = page.refresh_cards

    def _postal(*args, **kwargs):
        calls["postal"] += 1
        return original_postal(*args, **kwargs)

    def _city(*args, **kwargs):
        calls["city"] += 1
        return original_city(*args, **kwargs)

    def _cards() -> None:
        calls["cards"] += 1
        original_cards()

    monkeypatch.setattr(geo_resolve, "resolve_postal_pgeocode", _postal)
    monkeypatch.setattr(geo_resolve, "resolve_city_pgeocode", _city)
    page.refresh_cards = _cards  # type: ignore[method-assign]
    dialogs: list[str] = []

    def _information(*args, **kwargs):
        dialogs.append(str(args[2] if len(args) > 2 else ""))
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr("desktop.pages.profile.QMessageBox.information", _information)
    page.applicant.street.setText("Alexanderplatz 1")
    page.applicant.postal_code.setText("10115")
    page.applicant.city.setText("Berlin")
    page.applicant.app_country.setText("DE")
    page.save_btn.click()
    qapp.processEvents()
    assert calls["cards"] == 1
    assert dialogs == ["Gespeichert."]
    assert calls["postal"] + calls["city"] <= 1
    assert "aufgelöst" in page.home_status.text()
    assert not page.home_status.isHidden()
