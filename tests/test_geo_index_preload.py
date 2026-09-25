"""Shared background load of the DACH postal/place index."""

from __future__ import annotations

import os
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QEventLoop
from PySide6.QtWidgets import QApplication, QLabel, QMessageBox, QVBoxLayout, QWidget

from core.config import LocationConfig
from core.geo_dataset import get_geo_dataset_manager, reset_geo_dataset_manager_for_tests
from core.geo_normalize import normalize_place_fields
from core.geo_resolve import (
    bind_ui_thread,
    hold_geo_preload_for_tests,
    preload_geo_index_async,
    preload_worker_ident,
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


def _pump_until_worker_recorded(qapp: QApplication, timeout_s: float = 10.0) -> int:
    """Pump the GUI loop until the loader body has stored its thread ident.

    ``Event.wait`` returns as soon as the worker records itself. The timeout
    only bounds a hang. There is no sleep-then-assert.
    """
    deadline = time.monotonic() + timeout_s
    while preload_worker_ident() is None:
        if time.monotonic() >= deadline:
            pytest.fail("preload worker did not record its thread")
        qapp.processEvents(QEventLoop.ProcessEventsFlag.AllEvents)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        geo_resolve._preload_worker_recorded.wait(timeout=min(0.05, remaining))
    ident = preload_worker_ident()
    if ident is None:
        pytest.fail("preload worker did not record its thread")
    return ident


def _wait_thread(thread: threading.Thread | None) -> None:
    assert thread is not None
    thread.join(timeout=30)
    assert not thread.is_alive()


def test_main_window_preloads_off_gui_thread_only_after_show(qapp, config_service, geo_ready, monkeypatch):
    monkeypatch.setattr("desktop.tray.AppTray.show", lambda self: None)
    from desktop.main_window import MainWindow

    hold = threading.Event()
    hold_geo_preload_for_tests(hold)
    win = MainWindow(config_service)
    try:
        qapp.processEvents(QEventLoop.ProcessEventsFlag.AllEvents)
        assert not win.isVisible()
        assert preload_worker_ident() is None
        assert geo_resolve._preload_thread is None
        gui_ident = threading.get_ident()
        win.show()
        ident = _pump_until_worker_recorded(qapp)
        assert win.isVisible()
        assert ident != gui_ident
        assert ident != threading.main_thread().ident
        worker = geo_resolve._preload_thread
        assert worker is not None
        assert worker.ident == ident
        assert worker is not threading.current_thread()
        assert worker.is_alive()
    finally:
        hold.set()
        worker = geo_resolve._preload_thread
        win._shutting_down = True
        win.close()
        qapp.processEvents(QEventLoop.ProcessEventsFlag.AllEvents)
        if worker is not None:
            worker.join(timeout=30)


def test_ui_arm_returns_while_load_lock_is_held(geo_ready):
    """The GUI starter must not acquire ``_load_lock``."""
    bind_ui_thread()
    held = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    def _hold() -> None:
        geo_resolve._load_lock.acquire()
        try:
            held.set()
            release.wait(timeout=5)
        finally:
            geo_resolve._load_lock.release()

    def _unstick() -> None:
        if not finished.wait(timeout=1.0):
            release.set()

    blocker = threading.Thread(target=_hold)
    blocker.start()
    assert held.wait(timeout=2)
    threading.Thread(target=_unstick, daemon=True).start()
    try:
        started = time.monotonic()
        thread = geo_resolve.arm_geo_index_from_ui()
        elapsed = time.monotonic() - started
        finished.set()
    finally:
        release.set()
        blocker.join(timeout=5)
    assert thread is not None
    assert elapsed < 0.5
    assert thread is not threading.current_thread()
    _wait_thread(thread)


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


def _persisted_place_text(cfg) -> str:
    loc = cfg.profile.location
    app = cfg.application
    return " ".join(
        str(part or "")
        for part in (
            loc.home_address,
            loc.city,
            loc.postal_code,
            loc.home_geocoded_address,
            app.street,
            app.postal_code,
            app.city,
            app.country,
        )
    )


def _pump_until_label(qapp: QApplication, label, predicate, timeout_s: float = 15.0) -> str:
    """Deliver queued UI slots until ``predicate(text)``. No sleep-then-assert."""
    deadline = time.monotonic() + timeout_s
    while not predicate(label.text()):
        if time.monotonic() >= deadline:
            pytest.fail(f"label stayed {label.text()!r}")
        qapp.processEvents(QEventLoop.ProcessEventsFlag.AllEvents)
    return label.text()


def test_save_during_preload_resolves_10115_from_the_same_load(
    qapp, config_service, geo_ready, monkeypatch
):
    """save() returns while the preload Event is still unset.

    GeoNames ``DE.txt`` labels PLZ 10115 as place_name ``Berlin``
    (52.5323, 13.3846), not the district name Berlin-Mitte. The queued
    ready slot must publish that directory place from the same one load.
    """
    monkeypatch.setattr("desktop.tray.AppTray.show", lambda self: None)
    from desktop.main_window import MainWindow

    i18n.set_language("de")
    builds: list[tuple[str, int | None]] = []
    original_build = geo_resolve._build_nominatim

    def _counted(country_code: str):
        builds.append((country_code, threading.get_ident()))
        return original_build(country_code)

    monkeypatch.setattr(geo_resolve, "_build_nominatim", _counted)
    dialogs: list[str] = []

    def _information(*args, **kwargs):
        dialogs.append(str(args[2] if len(args) > 2 else ""))
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr("desktop.pages.profile.QMessageBox.information", _information)

    def _warning(*args, **kwargs):
        raise AssertionError(args)

    monkeypatch.setattr("desktop.pages.profile.QMessageBox.warning", _warning)

    hold = threading.Event()
    hold_geo_preload_for_tests(hold)
    win = MainWindow(config_service)
    try:
        qapp.processEvents(QEventLoop.ProcessEventsFlag.AllEvents)
        win.show()
        worker_ident = _pump_until_worker_recorded(qapp)
        loader = geo_resolve._preload_thread
        assert loader is not None and loader.is_alive()
        assert builds == []
        gui_ident = threading.get_ident()
        assert worker_ident != gui_ident

        page = win.profile
        page.applicant.street.setText("")
        page.applicant.postal_code.setText("10115")
        page.applicant.city.setText("")
        page.applicant.app_country.setText("DE")
        assert not hold.is_set()
        page.save_btn.click()
        # save() has returned. A blocking save would still be inside click().
        assert not hold.is_set()
        assert dialogs == ["Gespeichert."]
        assert builds == []
        assert geo_resolve._preload_thread is loader
        saved = config_service.load()
        assert saved.application.postal_code == "10115"
        assert saved.profile.location.postal_code == "10115"
        assert "nicht auflösbar" not in _persisted_place_text(saved)
        assert "nicht prüfbar" not in _persisted_place_text(saved)

        hold.set()
        text = _pump_until_label(
            qapp,
            page.home_status,
            lambda value: "Berlin" in value and "aufgelöst" in value,
        )
        assert "nicht auflösbar" not in text
        assert "nicht prüfbar" not in text
        finished = config_service.load()
        loc = finished.profile.location
        assert loc.postal_code == "10115"
        assert loc.city == "Berlin"
        # GeoNames place_name for 10115 is Berlin, not the district Berlin-Mitte.
        assert "Berlin-Mitte" not in text
        assert "Berlin-Mitte" not in _persisted_place_text(finished)
        assert loc.home_latitude == pytest.approx(52.5323)
        assert loc.home_longitude == pytest.approx(13.3846)
        assert "nicht auflösbar" not in _persisted_place_text(finished)
        assert "nicht prüfbar" not in _persisted_place_text(finished)
        assert [code for code, _ident in builds] == ["DE", "AT", "CH"]
        assert {ident for _code, ident in builds} == {worker_ident}
        assert dialogs == ["Gespeichert."]
    finally:
        hold.set()
        win._shutting_down = True
        win.close()
        qapp.processEvents(QEventLoop.ProcessEventsFlag.AllEvents)
        worker = geo_resolve._preload_thread
        if worker is not None:
            worker.join(timeout=30)


def test_unresolvable_plz_still_shows_the_hint_after_preload(
    qapp, config_service, geo_ready, monkeypatch
):
    monkeypatch.setattr("desktop.tray.AppTray.show", lambda self: None)
    from desktop.i18n import tr
    from desktop.main_window import MainWindow

    i18n.set_language("de")
    dialogs: list[str] = []

    def _information(*args, **kwargs):
        dialogs.append(str(args[2] if len(args) > 2 else ""))
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr("desktop.pages.profile.QMessageBox.information", _information)
    hold = threading.Event()
    hold_geo_preload_for_tests(hold)
    win = MainWindow(config_service)
    try:
        win.show()
        _pump_until_worker_recorded(qapp)
        page = win.profile
        page.applicant.street.setText("")
        page.applicant.postal_code.setText("00000")
        page.applicant.city.setText("")
        page.applicant.app_country.setText("DE")
        assert not hold.is_set()
        page.save_btn.click()
        assert not hold.is_set()
        assert dialogs == ["Gespeichert."]
        saved = config_service.load()
        assert saved.application.postal_code == "00000"
        assert saved.profile.location.postal_code == "00000"
        assert "nicht auflösbar" not in _persisted_place_text(saved)
        hold.set()
        text = _pump_until_label(
            qapp,
            page.home_status,
            lambda value: "aufgelöst" not in value and "nicht prüfbar" in value,
        )
        assert text == tr("dash.home_plz_hint")
        loc = config_service.load().profile.location
        assert loc.postal_code == "00000"
        assert loc.home_latitude is None and loc.home_longitude is None
        assert "nicht auflösbar" not in _persisted_place_text(config_service.load())
    finally:
        hold.set()
        win._shutting_down = True
        win.close()
        qapp.processEvents(QEventLoop.ProcessEventsFlag.AllEvents)
        worker = geo_resolve._preload_thread
        if worker is not None:
            worker.join(timeout=30)
