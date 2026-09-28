"""Such-Wohnort-Koordinaten liegen im Cache, nicht in profile.yaml."""

from __future__ import annotations

import hashlib
import os
import threading

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication, QMessageBox, QVBoxLayout, QWidget

from core.database import Database
from core.geo_dataset import get_geo_dataset_manager, reset_geo_dataset_manager_for_tests
from core.geo_resolve import (
    bind_ui_thread,
    hold_geo_preload_for_tests,
    reset_pgeocode_index_for_tests,
)
from core.home_coord_cache import read_home_coordinates, write_home_coordinates
from core.location import (
    LocationService,
    reset_home_resolution_cache_for_tests,
    store_user_home_coordinates,
)
from desktop.design_system.v2_chrome import SectionEditDrawer
from desktop.i18n import i18n
from desktop.pages.profile import ProfilePage
from desktop.services import ConfigService

HINT = "Eigener Suchort gespeichert. Die Kontaktadresse wird nicht mehr übernommen."
AT_COORDS = (48.2085, 16.3721)
CH_COORDS = (46.5377, 6.6553)


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
    def __init__(self, page: ProfilePage) -> None:
        super().__init__()
        self.profile = page
        layout = QVBoxLayout(self)
        layout.addWidget(page)

    def refresh_all(self) -> None:
        self.profile.load_from_config()


def _silence(monkeypatch) -> None:
    monkeypatch.setattr(
        "desktop.pages.profile.QMessageBox.information",
        lambda *args, **kwargs: QMessageBox.StandardButton.Ok,
    )
    monkeypatch.setattr(
        "desktop.pages.profile.QMessageBox.warning",
        lambda *args, **kwargs: pytest.fail(f"warning: {args!r}"),
    )
    monkeypatch.setattr("desktop.tray.AppTray.show", lambda self: None)


def _sha256(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _yaml_hashes(config_service: ConfigService) -> tuple[str, str, str]:
    return (
        _sha256(config_service.profile_path),
        _sha256(config_service.application_path),
        _sha256(config_service.settings_path),
    )


def _seed_berlin(config_service: ConfigService) -> None:
    cfg = config_service.load()
    cfg.profile.location.home_address = "Alexanderplatz 1, 10115 Berlin, DE"
    cfg.profile.location.postal_code = "10115"
    cfg.profile.location.city = "Berlin"
    cfg.profile.location.country = "DE"
    cfg.profile.location.home_latitude = None
    cfg.profile.location.home_longitude = None
    cfg.profile.location.home_geocoded_address = ""
    config_service.save(cfg)


def _open_main(qapp, config_service):
    from desktop.main_window import MainWindow

    win = MainWindow(config_service)
    win.show()
    qapp.processEvents()
    return win


def _pump_resolved(qapp, label, timeout_s: float = 20.0) -> None:
    import time

    deadline = time.monotonic() + timeout_s
    while "aufgelöst" not in label.text():
        if time.monotonic() >= deadline:
            raise AssertionError(label.text())
        qapp.processEvents()


def _close(win, qapp) -> None:
    win._shutting_down = True
    win.close()
    qapp.processEvents()


def test_first_and_second_start_leave_yaml_sha256_equal(
    qapp, config_service, geo_ready, monkeypatch
):
    """(a) Erster und zweiter Start lassen die drei YAML-Dateien byte-gleich."""
    import core.location as location

    _silence(monkeypatch)
    i18n.set_language("de")
    _seed_berlin(config_service)
    before = _yaml_hashes(config_service)
    win = _open_main(qapp, config_service)
    try:
        _pump_resolved(qapp, win.profile.home_status)
        assert _yaml_hashes(config_service) == before
    finally:
        _close(win, qapp)
    assert _yaml_hashes(config_service) == before

    reset_home_resolution_cache_for_tests()
    calls = {"n": 0}
    original = location.resolve_place

    def _wrapped(*args, **kwargs):
        calls["n"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(location, "resolve_place", _wrapped)
    win2 = _open_main(qapp, config_service)
    try:
        _pump_resolved(qapp, win2.profile.home_status)
        assert calls["n"] == 0
        assert _yaml_hashes(config_service) == before
    finally:
        _close(win2, qapp)


def test_second_start_with_cache_does_not_resolve(
    qapp, config_service, geo_ready, monkeypatch
):
    """(b) Zweiter Start mit Cache ruft die Auflösung 0-mal auf."""
    import core.location as location

    _silence(monkeypatch)
    i18n.set_language("de")
    _seed_berlin(config_service)
    win = _open_main(qapp, config_service)
    try:
        _pump_resolved(qapp, win.profile.home_status)
    finally:
        _close(win, qapp)
    loaded = config_service.load().profile.location
    assert read_home_coordinates(config_service.dirs["cache"], loaded) is not None

    reset_home_resolution_cache_for_tests()
    calls = {"n": 0}
    original = location.resolve_place

    def _wrapped(*args, **kwargs):
        calls["n"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(location, "resolve_place", _wrapped)
    win2 = _open_main(qapp, config_service)
    try:
        _pump_resolved(qapp, win2.profile.home_status)
        assert calls["n"] == 0
    finally:
        _close(win2, qapp)


def test_start_resolves_once_without_cache_and_never_with_cache(
    qapp, config_service, geo_ready, monkeypatch
):
    """Ohne Cache genau ein resolve_place pro Start, mit Cache keins.

    Der Lade-Sentinel vor dem Index zählt nicht: Hinweis und Distanzfilter
    teilen die eine Auflösung nach dem Preload.
    """
    import core.location as location

    _silence(monkeypatch)
    i18n.set_language("de")
    _seed_berlin(config_service)
    reset_home_resolution_cache_for_tests()
    calls = {"n": 0}
    original = location.resolve_place

    def _wrapped(*args, **kwargs):
        calls["n"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(location, "resolve_place", _wrapped)
    win = _open_main(qapp, config_service)
    try:
        _pump_resolved(qapp, win.profile.home_status)
        assert calls["n"] == 1
    finally:
        _close(win, qapp)
    loaded = config_service.load().profile.location
    assert read_home_coordinates(config_service.dirs["cache"], loaded) is not None

    reset_home_resolution_cache_for_tests()
    calls["n"] = 0
    win2 = _open_main(qapp, config_service)
    try:
        _pump_resolved(qapp, win2.profile.home_status)
        assert calls["n"] == 0
    finally:
        _close(win2, qapp)


def test_country_change_at_to_ch_same_plz_is_cache_miss(
    config_service, geo_ready
):
    """(c) Gleiche vierstellige PLZ, Land AT → CH: keine AT-Koordinaten."""
    cfg = config_service.load()
    loc = cfg.profile.location
    loc.home_address = "Stephansplatz 1"
    loc.postal_code = "1010"
    loc.city = "Wien"
    loc.country = "AT"
    write_home_coordinates(config_service.dirs["cache"], loc, *AT_COORDS)
    assert read_home_coordinates(config_service.dirs["cache"], loc) == AT_COORDS

    loc.country = "CH"
    loc.city = "Lausanne"
    assert read_home_coordinates(config_service.dirs["cache"], loc) is None
    reset_home_resolution_cache_for_tests()
    home = LocationService(Database(cfg.db_path, recover=False), cfg).resolve_home()
    assert home.coords is not None
    assert abs(home.coords[0] - AT_COORDS[0]) > 0.5
    assert abs(home.coords[0] - CH_COORDS[0]) < 0.05
    assert abs(home.coords[1] - CH_COORDS[1]) < 0.05


def test_ui_save_writes_no_coordinates_into_profile_yaml(
    qapp, config_service, geo_ready, monkeypatch
):
    """(d) UI-Speichern schreibt keine Koordinaten nach profile.yaml."""
    _silence(monkeypatch)
    i18n.set_language("de")
    _seed_berlin(config_service)
    page = ProfilePage(config_service)
    host = _Host(page)
    host.show()
    qapp.processEvents()
    page.load_from_config()
    page.location_work.home_address.setText("Speicherstraße 2, 20095 Hamburg, DE")
    page.location_work.postal_code.setText("20095")
    page.location_work.country.setText("DE")
    page._save_scope = "search_home"
    page.save()
    qapp.processEvents()
    text = config_service.profile_path.read_text(encoding="utf-8")
    assert "home_latitude" not in text
    assert "home_longitude" not in text
    assert "home_geocoded_address" not in text
    loc = config_service.load().profile.location
    cached = read_home_coordinates(config_service.dirs["cache"], loc)
    assert cached is not None
    assert loc.postal_code == "20095"


def test_legacy_profile_yaml_coordinates_are_not_a_distance_source(
    config_service, geo_ready
):
    """(e) Alte profile.yaml mit Koordinaten wird geladen und nicht benutzt."""
    _seed_berlin(config_service)
    path = config_service.profile_path
    text = path.read_text(encoding="utf-8")
    needle = "country: DE\n"
    assert needle in text
    path.write_text(
        text.replace(
            needle,
            "country: DE\n  home_latitude: 1.5\n  home_longitude: 2.5\n"
            "  home_geocoded_address: fake\n",
            1,
        ),
        encoding="utf-8",
    )
    before = path.read_bytes()
    loaded = config_service.load()
    assert loaded.profile.location.home_latitude == pytest.approx(1.5)
    assert loaded.profile.location.home_longitude == pytest.approx(2.5)
    assert path.read_bytes() == before
    home = LocationService(Database(loaded.db_path, recover=False), loaded).resolve_home()
    assert home.resolved
    assert home.coords is not None
    assert abs(home.coords[0] - 1.5) > 1
    assert path.read_bytes() == before
    config_service.save(loaded)
    assert "home_latitude" not in path.read_text(encoding="utf-8")


def test_country_change_while_index_loads_drops_at_distance(
    config_service, geo_ready
):
    """Landwechsel während der Index lädt: keine AT-Entfernung, danach CH."""
    cfg = config_service.load()
    loc = cfg.profile.location
    loc.home_address = "Stephansplatz 1"
    loc.postal_code = "1010"
    loc.city = "Wien"
    loc.country = "AT"
    loc.home_latitude = AT_COORDS[0]
    loc.home_longitude = AT_COORDS[1]
    loc.home_geocoded_address = "1010|Wien|AT"
    write_home_coordinates(config_service.dirs["cache"], loc, *AT_COORDS)

    hold = threading.Event()
    hold_geo_preload_for_tests(hold)
    bind_ui_thread()
    reset_home_resolution_cache_for_tests()
    loc.country = "CH"
    loc.city = "Lausanne"
    try:
        outcome = store_user_home_coordinates(loc, cache_dir=config_service.dirs["cache"])
        assert outcome == "pending"
        assert loc.home_latitude is None and loc.home_longitude is None
        assert read_home_coordinates(config_service.dirs["cache"], loc) is None
        pending = LocationService(Database(cfg.db_path, recover=False), cfg).resolve_home()
        assert pending.coords is None
        assert pending.coords != AT_COORDS
    finally:
        hold.set()
        reset_pgeocode_index_for_tests()
        reset_home_resolution_cache_for_tests()

    done = LocationService(Database(cfg.db_path, recover=False), cfg).resolve_home()
    assert done.coords is not None
    assert abs(done.coords[0] - AT_COORDS[0]) > 0.5
    assert abs(done.coords[0] - CH_COORDS[0]) < 0.05
    assert abs(done.coords[1] - CH_COORDS[1]) < 0.05


def _open_profile(qapp, config_service) -> tuple[ProfilePage, _Host]:
    i18n.set_language("de")
    page = ProfilePage(config_service)
    host = _Host(page)
    host.show()
    qapp.processEvents()
    page.load_from_config()
    qapp.processEvents()
    return page, host


def _seed_contact(config_service: ConfigService) -> None:
    cfg = config_service.load()
    cfg.application.street = "Speicherstraße 2"
    cfg.application.postal_code = "20095"
    cfg.application.city = "Hamburg"
    cfg.application.country = "DE"
    cfg.profile.location.home_address = "Speicherstraße 2, 20095 Hamburg, DE"
    cfg.profile.location.postal_code = "20095"
    cfg.profile.location.city = "Hamburg"
    cfg.profile.location.country = "DE"
    config_service.save(cfg)
    config_service.set_sync_address_to_search(True)


def test_search_home_divergent_place_clears_checkbox_and_shows_hint(
    qapp, config_service, geo_ready, monkeypatch
):
    """2a Abweichender Ort bei gesetztem Haken: Eingabe bleibt, Haken aus, Hinweis."""
    _silence(monkeypatch)
    _seed_contact(config_service)
    page, _host = _open_profile(qapp, config_service)
    assert page.applicant.sync_home_from_address.isChecked()
    assert page.location_work.home_address.isEnabled()
    page.location_work.home_address.setText("Alexanderplatz 1")
    page.location_work.postal_code.setText("10115")
    page.location_work.country.setText("DE")
    page._drawer.present = lambda _content, focus=None: SectionEditDrawer.DialogCode.Accepted  # type: ignore[method-assign]
    page.edit_search_home()
    qapp.processEvents()
    loc = config_service.load().profile.location
    assert loc.home_address == "Alexanderplatz 1"
    assert loc.postal_code == "10115"
    assert page.location_work.home_address.text() == "Alexanderplatz 1"
    assert page.location_work.postal_code.text() == "10115"
    assert page.applicant.sync_home_from_address.isChecked() is False
    assert config_service.get_sync_address_to_search() is False
    assert page.applicant.custom_home_hint.isVisibleTo(page.applicant)
    assert page.applicant.custom_home_hint.text() == HINT
    assert page.location_work.home_address.isEnabled()


def test_search_home_exact_contact_keeps_checkbox_without_hint(
    qapp, config_service, geo_ready, monkeypatch
):
    """2b Exakt die Kontaktadresse: Haken bleibt, kein Hinweis."""
    _silence(monkeypatch)
    _seed_contact(config_service)
    page, _host = _open_profile(qapp, config_service)
    page.location_work.home_address.setText("Speicherstraße 2, 20095 Hamburg, DE")
    page.location_work.postal_code.setText("20095")
    page.location_work.country.setText("DE")
    page._drawer.present = lambda _content, focus=None: SectionEditDrawer.DialogCode.Accepted  # type: ignore[method-assign]
    page.edit_search_home()
    qapp.processEvents()
    assert page.applicant.sync_home_from_address.isChecked() is True
    assert config_service.get_sync_address_to_search() is True
    assert page.applicant.custom_home_hint.isVisibleTo(page.applicant) is False


def test_search_home_checkbox_again_restores_contact_without_restart(
    qapp, config_service, geo_ready, monkeypatch
):
    """2c Haken wieder setzen: Kontaktadresse, Hinweis weg, Entfernung ohne Neustart."""
    _silence(monkeypatch)
    _seed_contact(config_service)
    page, _host = _open_profile(qapp, config_service)
    page.location_work.home_address.setText("Alexanderplatz 1, 10115 Berlin, DE")
    page.location_work.postal_code.setText("10115")
    page.location_work.country.setText("DE")
    page._drawer.present = lambda _content, focus=None: SectionEditDrawer.DialogCode.Accepted  # type: ignore[method-assign]
    page.edit_search_home()
    qapp.processEvents()
    assert page.applicant.custom_home_hint.text() == HINT
    berlin = read_home_coordinates(
        config_service.dirs["cache"], config_service.load().profile.location
    )
    assert berlin is not None

    page.applicant.sync_home_from_address.setChecked(True)
    page._drawer.present = lambda _content, focus=None: SectionEditDrawer.DialogCode.Accepted  # type: ignore[method-assign]
    page._edit_section("personal")
    qapp.processEvents()
    loc = config_service.load().profile.location
    assert "Speicherstraße 2" in (loc.home_address or "")
    assert loc.postal_code == "20095"
    assert page.applicant.sync_home_from_address.isChecked() is True
    assert page.applicant.custom_home_hint.isVisibleTo(page.applicant) is False
    reset_home_resolution_cache_for_tests()
    home = LocationService(
        Database(config_service.load().db_path, recover=False),
        config_service.load(),
    ).resolve_home()
    assert home.coords is not None
    assert abs(home.coords[0] - berlin[0]) > 0.4
    assert home.coords[0] > 53.0
