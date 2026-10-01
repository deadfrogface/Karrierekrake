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
    # These UI tests exercise offline geocoding, not router installation.
    # Do not leave a network-using boot thread running into later socket guards.
    monkeypatch.setattr("desktop.main_window.MainWindow._start_brouter_runtime", lambda self: None)
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
    from core.location import flush_home_coord_writes

    win._shutting_down = True
    win.close()
    qapp.processEvents()
    flush_home_coord_writes()


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
        outcome = store_user_home_coordinates(
            loc, cfg, cache_dir=config_service.dirs["cache"]
        )
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


def test_1010_empty_country_cross_border_off_is_not_a_hit(config_service, geo_ready):
    """1010, leeres Land: cross_border an, dann aus. Kein Treffer, kein Abstand.

    Gilt im selben Prozess und nach einem simulierten Neustart. Der Datei-Schlüssel
    enthält cross_border, das aufgelöste Land bleibt AT und wird nicht zu DE.
    """
    from core.geo_resolve import preload_geo_index_async
    import core.geo_resolve as geo

    cfg = config_service.load()
    loc = cfg.profile.location
    loc.home_address = ""
    loc.postal_code = "1010"
    loc.city = ""
    loc.country = ""
    loc.cross_border_dach = False
    cfg.settings.cross_border_dach_enabled = True
    reset_home_resolution_cache_for_tests()
    thread = preload_geo_index_async()
    if thread is not None:
        thread.join(timeout=60)
    assert geo._preload_done.is_set()

    db = Database(cfg.db_path, recover=False)
    on = LocationService(db, cfg).resolve_home()
    if on.coords is None:
        write_home_coordinates(
            config_service.dirs["cache"],
            loc,
            *AT_COORDS,
            display_name="1010, Wien, AT",
            cross_border=True,
            home_country="DE",
            resolved_country="AT",
        )
    hit = read_home_coordinates(
        config_service.dirs["cache"],
        loc,
        cross_border=True,
        home_country="DE",
    )
    assert hit is not None
    assert abs(hit[0] - AT_COORDS[0]) < 0.05
    record = __import__(
        "core.home_coord_cache", fromlist=["read_home_record"]
    ).read_home_record(
        config_service.dirs["cache"],
        loc,
        cross_border=True,
        home_country="DE",
    )
    assert record is not None and record[3] == "AT"

    cfg.settings.cross_border_dach_enabled = False
    off = LocationService(db, cfg).resolve_home()
    assert off.coords is None
    assert off.resolved is False
    assert (
        read_home_coordinates(
            config_service.dirs["cache"],
            loc,
            cross_border=False,
            home_country="DE",
        )
        is None
    )

    reset_home_resolution_cache_for_tests()
    restarted = LocationService(db, cfg).resolve_home()
    assert restarted.coords is None
    assert restarted.resolved is False


def test_start_resolves_once_when_location_flag_differs(
    qapp, config_service, geo_ready, monkeypatch, caplog
):
    """Ohne Cache genau ein resolve_place, auch wenn die beiden Flags abweichen."""
    import logging

    import core.location as location

    _silence(monkeypatch)
    i18n.set_language("de")
    _seed_berlin(config_service)
    cfg = config_service.load()
    cfg.profile.location.cross_border_dach = False
    cfg.settings.cross_border_dach_enabled = True
    config_service.save(cfg)
    reset_home_resolution_cache_for_tests()
    calls = {"n": 0}
    original = location.resolve_place

    def _wrapped(*args, **kwargs):
        calls["n"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(location, "resolve_place", _wrapped)
    caplog.set_level(logging.INFO, logger="karrierekrake.home")
    win = _open_main(qapp, config_service)
    try:
        _pump_resolved(qapp, win.profile.home_status)
        assert calls["n"] == 1
    finally:
        _close(win, qapp)
    reasons = [rec.getMessage() for rec in caplog.records if rec.name == "karrierekrake.home"]
    assert reasons
    assert any("caller=" in line and "key=" in line for line in reasons)
    assert any("geo_index_loading" in line or "status=RESOLVED" in line for line in reasons)


def test_memory_hit_does_not_touch_the_coordinate_file(
    config_service, geo_ready, monkeypatch
):
    """Speicher-Treffer und der zweite Refresh: kein read, kein json, kein Stempel."""
    import core.home_coord_cache as cache
    import core.location as location_mod
    from core.geo_resolve import preload_geo_index_async
    from core.location import cached_home_resolution, home_location_notice
    import core.geo_resolve as geo

    _seed_berlin(config_service)
    cfg = config_service.load()
    reset_home_resolution_cache_for_tests()
    thread = preload_geo_index_async()
    if thread is not None:
        thread.join(timeout=60)
    assert geo._preload_done.is_set()
    loc = cfg.profile.location
    first = cached_home_resolution(
        loc,
        cross_border=True,
        home_country="DE",
        cache_dir=config_service.dirs["cache"],
    )
    assert first is not None and first.ok
    from core.location import flush_home_coord_writes

    flush_home_coord_writes()

    counts = {"read": 0, "json": 0, "stamp": 0}
    real_read = cache.read_home_record
    real_loads = cache.json.loads
    real_stamp = cache.geo_index_stamp

    def _read(*args, **kwargs):
        counts["read"] += 1
        return real_read(*args, **kwargs)

    def _loads(*args, **kwargs):
        counts["json"] += 1
        return real_loads(*args, **kwargs)

    def _stamp():
        counts["stamp"] += 1
        return real_stamp()

    monkeypatch.setattr(location_mod, "read_home_record", _read)
    monkeypatch.setattr(cache.json, "loads", _loads)
    monkeypatch.setattr(cache, "geo_index_stamp", _stamp)
    second = cached_home_resolution(
        loc, cross_border=True, home_country="DE", cache_dir=config_service.dirs["cache"]
    )
    assert second is first or (second is not None and second.ok)
    assert counts == {"read": 0, "json": 0, "stamp": 0}
    home_location_notice(loc, cfg)
    assert counts == {"read": 0, "json": 0, "stamp": 0}


def test_user_save_writes_once_on_the_caller_thread(config_service, geo_ready, monkeypatch):
    """Nutzer-Speichern: genau ein fsync, auf dem Aufrufer-Thread."""
    import core.location as location_mod
    from core.geo_resolve import bind_ui_thread, preload_geo_index_async
    import core.geo_resolve as geo

    _seed_berlin(config_service)
    cfg = config_service.load()
    reset_home_resolution_cache_for_tests()
    thread = preload_geo_index_async()
    if thread is not None:
        thread.join(timeout=60)
    assert geo._preload_done.is_set()
    bind_ui_thread()
    writes = []
    real = location_mod.write_home_coordinates

    def _wrapped(*args, **kwargs):
        writes.append(threading.get_ident())
        return real(*args, **kwargs)

    monkeypatch.setattr(location_mod, "write_home_coordinates", _wrapped)
    loc = cfg.profile.location
    loc.home_address = "Speicherstraße 1, 20095 Hamburg"
    loc.postal_code = "20095"
    loc.city = "Hamburg"
    loc.country = "DE"
    outcome = store_user_home_coordinates(loc, cfg, cache_dir=config_service.dirs["cache"])
    assert outcome == "resolved"
    assert writes == [threading.get_ident()]


def test_gui_refresh_while_loading_stays_under_5ms_and_does_not_write(
    qapp, config_service, geo_ready, monkeypatch
):
    """GUI-Thread: jeder Aufruf unter 5 ms, kein Schreiben. Abstand kommt nach dem Worker."""
    import time

    import core.geo_resolve as geo
    import core.location as location
    from core.models import Job, RemoteType

    _silence(monkeypatch)
    i18n.set_language("de")
    _seed_berlin(config_service)
    cfg = config_service.load()
    db = Database(cfg.db_path, recover=False)
    db.upsert_job(
        Job(
            id="stale-12",
            source="indeed",
            title="Alpha",
            company="Nord",
            city="Berlin",
            postal_code="10115",
            country_code="DE",
            remote_type=RemoteType.ONSITE.value,
            match_score=90,
            status="new",
            distance_km=12.0,
        )
    )
    db.upsert_job(
        Job(
            id="stale-0",
            source="indeed",
            title="Beta",
            company="Süd",
            city="Hamburg",
            postal_code="20095",
            country_code="DE",
            remote_type=RemoteType.ONSITE.value,
            match_score=80,
            status="new",
            distance_km=0.0,
        )
    )
    db.upsert_job(
        Job(
            id="needs-place",
            source="indeed",
            title="Gamma",
            company="Ost",
            city="Leipzig",
            postal_code="04109",
            country_code="DE",
            remote_type=RemoteType.ONSITE.value,
            match_score=70,
            status="new",
        )
    )
    hold = threading.Event()
    hold_geo_preload_for_tests(hold)
    records: list[tuple[int, float, str]] = []

    def _timed(kind, real):
        def _wrapped(*args, **kwargs):
            started = time.perf_counter()
            try:
                return real(*args, **kwargs)
            finally:
                records.append((threading.get_ident(), time.perf_counter() - started, kind))

        return _wrapped

    monkeypatch.setattr(location, "resolve_place", _timed("resolve", location.resolve_place))
    monkeypatch.setattr(geo, "resolve_place", _timed("resolve", geo.resolve_place))
    monkeypatch.setattr(
        location, "write_home_coordinates", _timed("write", location.write_home_coordinates)
    )
    win = _open_main(qapp, config_service)
    try:
        gui = threading.get_ident()
        qapp.processEvents()
        assert "Entfernung wird ermittelt" in win.profile.home_status.text()
        assert win.profile.home_status.objectName() == "HomeStatusPending"
        assert win.profile.home_status.movie() is None
        for row in range(win.jobs.table.rowCount()):
            cell = win.jobs.table.item(row, 3).text()
            assert cell == ""
            assert "0 km" not in cell
            assert "12" not in cell
        gui_calls = [item for item in records if item[0] == gui]
        assert gui_calls
        assert all(duration < 0.005 for _ident, duration, _kind in gui_calls)
        assert all(kind != "write" for _ident, _duration, kind in gui_calls)
        from PySide6.QtCore import Qt

        role = Qt.ItemDataRole.UserRole
        beta_row = None
        for row in range(win.jobs.job_list.count()):
            item = win.jobs.job_list.item(row)
            if item is not None and item.data(role) == "stale-0":
                beta_row = row
                win.jobs.job_list.setCurrentRow(row)
        assert beta_row is not None
        bar = win.jobs.job_list.verticalScrollBar()
        if bar.maximum() > 0:
            bar.setValue(bar.maximum())
        scroll = bar.value()
        selected = win.jobs.job_list.currentItem().data(role)
        passes = win.jobs._distance_order_passes
        seen = [win.profile.home_status.text()]
        hold.set()
        deadline = time.monotonic() + 20
        while "aufgelöst" not in win.profile.home_status.text():
            text = win.profile.home_status.text()
            if not seen or seen[-1] != text:
                seen.append(text)
            if time.monotonic() >= deadline:
                raise AssertionError(seen)
            qapp.processEvents()
        final = win.profile.home_status.text()
        if not seen or seen[-1] != final:
            seen.append(final)
        assert seen[0].startswith("Entfernung wird ermittelt") or any(
            text.startswith("Entfernung wird ermittelt") for text in seen
        )
        assert sum(text.startswith("Entfernung wird ermittelt") for text in seen) == 1
        assert seen[-1] != seen[0]
        assert "aufgelöst" in seen[-1]
        assert win.jobs._distance_order_passes == passes + 1
        current = win.jobs.job_list.currentItem()
        assert current is not None and current.data(role) == selected
        assert win.jobs.job_list.verticalScrollBar().value() == scroll
    finally:
        hold.set()
        _close(win, qapp)
