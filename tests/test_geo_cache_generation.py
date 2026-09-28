"""Index-Generation liegt im Cache-Wert, nicht im Schlüssel."""

from __future__ import annotations

import os
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QMessageBox, QPushButton

from core.config import LocationConfig
from core.database import Database
from core.geo_dataset import get_geo_dataset_manager, reset_geo_dataset_manager_for_tests
from core.geo_normalize import normalize_place_fields
from core.geo_resolve import (
    bind_ui_thread,
    hold_geo_preload_for_tests,
    preload_geo_index_async,
    reset_pgeocode_index_for_tests,
    resolve_place,
)
from core.location import home_location_notice
from core.models import Job, RemoteType
from desktop.i18n import home_country_label, i18n, tr
from desktop.pages.dashboard import DashboardPage, bind_home_notice_label
from desktop.services import ConfigService

import core.geo_resolve as geo


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


def _silence(monkeypatch) -> None:
    monkeypatch.setattr("desktop.tray.AppTray.show", lambda self: None)
    monkeypatch.setattr(
        "desktop.pages.profile.QMessageBox.information",
        lambda *args, **kwargs: QMessageBox.StandardButton.Ok,
    )
    monkeypatch.setattr(
        "desktop.pages.profile.QMessageBox.warning",
        lambda *args, **kwargs: QMessageBox.StandardButton.Ok,
    )


def _wait_thread(thread: threading.Thread | None) -> None:
    if thread is not None:
        thread.join(timeout=30)
        assert not thread.is_alive()


def _pump(qapp, predicate, timeout_s: float = 20.0) -> None:
    deadline = time.monotonic() + timeout_s
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError("timeout")
        qapp.processEvents()


class _NoIter(dict):
    """Raises when the cache is walked. Construction itself may iterate."""

    def __init__(self, *args, **kwargs):
        self._guard = False
        super().__init__(*args, **kwargs)
        self._guard = True

    def _boom(self, name: str):
        if self._guard:
            raise AssertionError(f"cache iterated via {name}")

    def __iter__(self):
        self._boom("__iter__")
        return super().__iter__()

    def keys(self):
        self._boom("keys")
        return super().keys()

    def values(self):
        self._boom("values")
        return super().values()

    def items(self):
        self._boom("items")
        return super().items()


def test_bump_does_not_iterate_and_cache_length_stays(geo_ready):
    """Drei Bumps ändern die Länge nicht und laufen nicht über den Cache."""
    import core.location as location

    _wait_thread(preload_geo_index_async())
    berlin = normalize_place_fields(postal_code="10115", city="Berlin", country_code="DE")
    missing = normalize_place_fields(postal_code="00000", city="", country_code="DE")
    assert resolve_place(berlin).ok
    assert not resolve_place(missing).ok
    before_places = len(geo._resolution_cache)
    before_home = len(location._HOME_RESOLUTION_CACHE)
    geo._resolution_cache = _NoIter(geo._resolution_cache)
    location._HOME_RESOLUTION_CACHE = _NoIter(location._HOME_RESOLUTION_CACHE)
    try:
        for _ in range(3):
            geo._bump_geo_index_generation()
            geo._notify_geo_index_generation()
        assert len(geo._resolution_cache) == before_places
        assert len(location._HOME_RESOLUTION_CACHE) == before_home
        again = resolve_place(berlin)
        assert again.ok
        assert len(geo._resolution_cache) == before_places
        retried = resolve_place(missing)
        assert not retried.ok
        assert len(geo._resolution_cache) == before_places
    finally:
        geo._resolution_cache._guard = False
        location._HOME_RESOLUTION_CACHE._guard = False


def test_refresh_all_after_bump_retries_only_the_failed_place(
    qapp, config_service, geo_ready, monkeypatch
):
    """Zweiter refresh_all über 5000 Jobs: 0 neue Treffer, genau 1 Fehlschlag."""
    from desktop.main_window import MainWindow

    _silence(monkeypatch)
    i18n.set_language("de")
    _wait_thread(preload_geo_index_async())
    cfg = config_service.load()
    cfg.profile.location.home_address = "Alexanderplatz 1, 10115 Berlin, DE"
    cfg.profile.location.postal_code = "10115"
    cfg.profile.location.city = "Berlin"
    cfg.profile.location.country = "DE"
    cfg.profile.location.max_distance_km = 500
    cfg.profile.location.home_latitude = 52.52
    cfg.profile.location.home_longitude = 13.405
    cfg.profile.location.home_geocoded_address = ""
    config_service.save(cfg)

    hamburg = normalize_place_fields(postal_code="20095", city="Hamburg", country_code="DE")
    failed_place = normalize_place_fields(postal_code="00000", city="Nirgendwo", country_code="DE")
    assert resolve_place(hamburg).ok
    assert not resolve_place(failed_place).ok

    db = Database(cfg.db_path, recover=False)
    jobs = [
        Job(
            id=f"ok-{i}",
            source="indeed",
            title="Disponent",
            company=f"Firma {i}",
            city="Berlin",
            postal_code="10115",
            country_code="DE",
            remote_type=RemoteType.ONSITE.value,
            distance_km=float(5 + (i % 20)),
            distance_source="brouter_v1",
            match_score=80,
            status="new",
        )
        for i in range(4990)
    ]
    jobs.extend(
        Job(
            id=f"hh-{i}",
            source="indeed",
            title="Kaufmann",
            company=f"Hafen {i}",
            city="Hamburg",
            postal_code="20095",
            country_code="DE",
            remote_type=RemoteType.ONSITE.value,
            match_score=90,
            status="new",
        )
        for i in range(9)
    )
    jobs.append(
        Job(
            id="failed-place",
            source="indeed",
            title="Unbekannt",
            company="Niemand",
            city="Nirgendwo",
            postal_code="00000",
            country_code="DE",
            remote_type=RemoteType.ONSITE.value,
            match_score=100,
            status="new",
        )
    )
    db.upsert_jobs(jobs)

    win = MainWindow(config_service)
    win.show()
    qapp.processEvents()
    try:
        before = len(geo._resolution_cache)
        for _ in range(3):
            geo._bump_geo_index_generation()
            geo._notify_geo_index_generation()
            qapp.processEvents()
        assert len(geo._resolution_cache) == before
        calls = {"ok": 0, "failed": 0}
        real = geo._resolve_place_uncached

        def _wrapped(place, **kwargs):
            result = real(place, **kwargs)
            if result.ok:
                calls["ok"] += 1
            else:
                calls["failed"] += 1
            return result

        monkeypatch.setattr(geo, "_resolve_place_uncached", _wrapped)
        win.refresh_all()
        qapp.processEvents()
        assert calls["ok"] == 0
        assert calls["failed"] == 1
        assert len(geo._resolution_cache) == before
    finally:
        win._shutting_down = True
        win.close()
        qapp.processEvents()


def test_missing_at_after_preload_is_unavailable_on_the_ui_thread(
    qapp, config_service, geo_ready, monkeypatch
):
    """Fehlende AT.txt nach Preload: nicht loading, Hinweis ohne Button."""
    i18n.set_language("de")
    real_build = geo._build_nominatim

    def _build(country_code: str):
        if country_code == "AT":
            return None
        return real_build(country_code)

    monkeypatch.setattr(geo, "_build_nominatim", _build)
    bind_ui_thread()
    _wait_thread(preload_geo_index_async())
    assert geo._preload_done.is_set()
    assert "AT" not in geo._pgeocode_index

    vienna = normalize_place_fields(postal_code="1010", city="Wien", country_code="AT")
    calls = {"n": 0}
    real = geo._resolve_place_uncached

    def _wrapped(place, **kwargs):
        calls["n"] += 1
        return real(place, **kwargs)

    monkeypatch.setattr(geo, "_resolve_place_uncached", _wrapped)
    result = resolve_place(vienna, home_country="AT")
    assert result.reason == "geo_index_unavailable"
    assert result.reason != "geo_index_loading"
    assert calls["n"] == 1
    again = resolve_place(vienna, home_country="AT")
    assert again.reason == "geo_index_unavailable"
    assert calls["n"] == 1

    loc = LocationConfig(
        home_address="Stephansplatz 1, 1010 Wien, AT",
        postal_code="1010",
        city="Wien",
        country="AT",
    )
    notice = home_location_notice(loc)
    assert notice.status == "unavailable"
    assert notice.offer_change_place is False
    text = tr(
        notice.notice_key,
        place=notice.place_label,
        country=home_country_label(notice.country_code),
    )
    assert text == (
        "Für Österreich fehlen die Standortdaten. "
        "Die Suche läuft deshalb ohne Entfernungsfilter."
    )
    assert "geo_index" not in text
    assert "AT" not in text.split()
    label = QLabel()
    button = QPushButton()
    bind_home_notice_label(label, notice, button)
    assert label.text() == text
    assert label.objectName() == "WarningLabel"
    assert button.isHidden()

    cfg = config_service.load()
    cfg.profile.location = loc
    config_service.save(cfg)
    page = DashboardPage(config_service)
    page.refresh()
    assert page.home_warning_label.text() == text
    assert page.change_place_btn.isHidden()

    cached_len = len(geo._resolution_cache)
    calls["n"] = 0
    geo._bump_geo_index_generation()
    retried = resolve_place(vienna, home_country="AT")
    assert retried.reason == "geo_index_unavailable"
    assert calls["n"] == 1
    assert len(geo._resolution_cache) == cached_len
    monkeypatch.setattr(geo, "_build_nominatim", real_build)

    def _load_at() -> None:
        geo._pgeocode_nominatim("AT")

    worker = threading.Thread(target=_load_at)
    worker.start()
    _wait_thread(worker)
    assert "AT" in geo._pgeocode_index
    calls["n"] = 0
    done = resolve_place(vienna, home_country="AT")
    assert done.ok
    assert calls["n"] == 1
    assert len(geo._resolution_cache) == cached_len


def test_notice_states_and_cold_start_never_says_not_found(
    qapp, config_service, geo_ready, monkeypatch
):
    """Kaltstart Wien: erst 'wird noch geprüft', dann 'aufgelöst', nie 'nicht gefunden'."""
    from desktop.main_window import MainWindow

    _silence(monkeypatch)
    i18n.set_language("de")
    hold = threading.Event()
    hold_geo_preload_for_tests(hold)
    cfg = config_service.load()
    cfg.profile.location.home_address = "Stephansplatz 1, 1010 Wien, AT"
    cfg.profile.location.postal_code = "1010"
    cfg.profile.location.city = "Wien"
    cfg.profile.location.country = "AT"
    cfg.profile.location.home_latitude = None
    cfg.profile.location.home_longitude = None
    cfg.profile.location.home_geocoded_address = ""
    config_service.save(cfg)

    seen: list[str] = []
    win = MainWindow(config_service)
    win.show()
    qapp.processEvents()
    try:
        def _snap() -> str:
            text = win.profile.home_status.text()
            if not seen or seen[-1] != text:
                seen.append(text)
            return text

        _pump(qapp, lambda: "wird noch geprüft" in _snap(), timeout_s=5)
        assert "nicht gefunden" not in _snap()
        assert win.profile.home_status.objectName() == "HomeStatusPending"
        assert win.profile.change_place_btn.isHidden()
        assert win.dashboard.home_warning_label.text() == win.profile.home_status.text()
        hold.set()
        _wait_thread(geo._preload_thread)
        _pump(qapp, lambda: "aufgelöst" in _snap())
        assert all("nicht gefunden" not in text for text in seen)
        assert "wird noch geprüft" in seen[0] or any("wird noch geprüft" in text for text in seen)
        assert any("aufgelöst" in text for text in seen)
    finally:
        hold.set()
        win._shutting_down = True
        win.close()
        qapp.processEvents()
        _wait_thread(geo._preload_thread)


def test_unknown_place_offers_the_change_button(geo_ready):
    i18n.set_language("de")
    _wait_thread(preload_geo_index_async())
    loc = LocationConfig(home_address="Xyzzyplugh", city="Xyzzyplugh", country="DE")
    notice = home_location_notice(loc)
    assert notice.status == "unknown"
    assert notice.offer_change_place is True
    text = tr(notice.notice_key, place=notice.place_label, country="")
    assert text == "„Xyzzyplugh“ wurde nicht gefunden. Die Suche läuft ohne Entfernungsfilter."
    label = QLabel()
    button = QPushButton()
    bind_home_notice_label(label, notice, button)
    assert label.objectName() == "WarningLabel"
    assert button.text() == "Anderen Ort eintragen"
    assert not button.isHidden()


def _count_passes(monkeypatch):
    from desktop.main_window import MainWindow
    from desktop.pages.jobs import JobsPage

    counts = {"filter": 0, "refresh": 0}
    real_filter = JobsPage.apply_filter_pass
    real_refresh = MainWindow.refresh_all

    def _filter(self, *args, **kwargs):
        counts["filter"] += 1
        return real_filter(self, *args, **kwargs)

    def _refresh(self, *args, **kwargs):
        counts["refresh"] += 1
        return real_refresh(self, *args, **kwargs)

    monkeypatch.setattr(JobsPage, "apply_filter_pass", _filter)
    monkeypatch.setattr(MainWindow, "refresh_all", _refresh)
    return counts


def test_bump_with_resolved_home_does_not_filter(
    qapp, config_service, geo_ready, monkeypatch
):
    from desktop.main_window import MainWindow

    _silence(monkeypatch)
    i18n.set_language("de")
    _wait_thread(preload_geo_index_async())
    cfg = config_service.load()
    cfg.profile.location.home_address = "Alexanderplatz 1, 10115 Berlin, DE"
    cfg.profile.location.postal_code = "10115"
    cfg.profile.location.city = "Berlin"
    cfg.profile.location.country = "DE"
    cfg.profile.location.home_latitude = 52.52
    cfg.profile.location.home_longitude = 13.405
    config_service.save(cfg)
    db = Database(cfg.db_path, recover=False)
    db.upsert_job(
        Job(
            id="berlin-1",
            source="indeed",
            title="Disponent",
            company="Firma",
            city="Berlin",
            postal_code="10115",
            country_code="DE",
            remote_type=RemoteType.ONSITE.value,
            distance_km=8.0,
            distance_source="brouter_v1",
            match_score=90,
            status="new",
        )
    )
    counts = _count_passes(monkeypatch)
    win = MainWindow(config_service)
    win.show()
    qapp.processEvents()
    try:
        assert win._home_notice_status == "resolved"
        assert win.jobs._last_pass_saw_loading is False
        counts["filter"] = 0
        counts["refresh"] = 0
        geo._bump_geo_index_generation()
        geo._notify_geo_index_generation()
        qapp.processEvents()
        assert counts["refresh"] == 0
        assert counts["filter"] == 0
    finally:
        win._shutting_down = True
        win.close()
        qapp.processEvents()


def test_bump_that_resolves_home_filters_once(
    qapp, config_service, geo_ready, monkeypatch
):
    from desktop.main_window import MainWindow

    _silence(monkeypatch)
    i18n.set_language("de")
    hold = threading.Event()
    hold_geo_preload_for_tests(hold)
    cfg = config_service.load()
    cfg.profile.location.home_address = "Stephansplatz 1, 1010 Wien, AT"
    cfg.profile.location.postal_code = "1010"
    cfg.profile.location.city = "Wien"
    cfg.profile.location.country = "AT"
    cfg.profile.location.home_latitude = None
    cfg.profile.location.home_longitude = None
    config_service.save(cfg)
    counts = _count_passes(monkeypatch)
    win = MainWindow(config_service)
    win.show()
    qapp.processEvents()
    try:
        _pump(qapp, lambda: "wird noch geprüft" in win.profile.home_status.text(), timeout_s=5)
        counts["filter"] = 0
        counts["refresh"] = 0
        hold.set()
        _wait_thread(geo._preload_thread)
        _pump(qapp, lambda: "aufgelöst" in win.profile.home_status.text())
        assert counts["refresh"] == 0
        assert counts["filter"] == 1
    finally:
        hold.set()
        win._shutting_down = True
        win.close()
        qapp.processEvents()
        _wait_thread(geo._preload_thread)


def test_bump_filters_once_when_jobs_were_loading(
    qapp, config_service, geo_ready, monkeypatch
):
    from desktop.main_window import MainWindow

    _silence(monkeypatch)
    i18n.set_language("de")
    hold = threading.Event()
    hold_geo_preload_for_tests(hold)
    cfg = config_service.load()
    cfg.profile.location.home_address = "Stephansplatz 1, 1010 Wien, AT"
    cfg.profile.location.postal_code = "1010"
    cfg.profile.location.city = "Wien"
    cfg.profile.location.country = "AT"
    cfg.profile.location.max_distance_km = 80
    cfg.profile.location.home_latitude = 48.208
    cfg.profile.location.home_longitude = 16.373
    cfg.profile.location.home_geocoded_address = ""
    config_service.save(cfg)
    db = Database(cfg.db_path, recover=False)
    db.upsert_job(
        Job(
            id="wien-1",
            source="indeed",
            title="Kaufmann",
            company="Donau",
            city="Wien",
            postal_code="1010",
            country_code="AT",
            remote_type=RemoteType.ONSITE.value,
            match_score=95,
            status="new",
        )
    )
    counts = _count_passes(monkeypatch)
    win = MainWindow(config_service)
    win.show()
    qapp.processEvents()
    try:
        assert win._home_notice_status == "resolved"
        assert win.jobs._last_pass_saw_loading is True
        counts["filter"] = 0
        counts["refresh"] = 0
        hold.set()
        _wait_thread(geo._preload_thread)
        _pump(qapp, lambda: counts["filter"] >= 1)
        assert counts["refresh"] == 0
        assert counts["filter"] == 1
        assert win.jobs._jobs
        assert all(job.airline_km is not None and job.airline_km >= 0 for job in win.jobs._jobs)
    finally:
        hold.set()
        win._shutting_down = True
        win.close()
        qapp.processEvents()
        _wait_thread(geo._preload_thread)


def test_filter_pass_keeps_scroll_and_selection(qapp, config_service, geo_ready, monkeypatch):
    """Qt-offscreen: der automatische Filterpass behält Scrollposition und Auswahl."""
    from desktop.pages.jobs import JobsPage

    _silence(monkeypatch)
    i18n.set_language("de")
    _wait_thread(preload_geo_index_async())
    cfg = config_service.load()
    cfg.profile.location.home_address = ""
    cfg.profile.location.postal_code = ""
    cfg.profile.location.city = ""
    cfg.profile.location.home_latitude = None
    cfg.profile.location.home_longitude = None
    config_service.save(cfg)
    db = Database(cfg.db_path, recover=False)
    db.upsert_jobs(
        [
            Job(
                id=f"row-{i}",
                source="indeed",
                title=f"Stelle {i}",
                company=f"Firma {i}",
                city="Berlin",
                postal_code="10115",
                country_code="DE",
                remote_type=RemoteType.ONSITE.value,
                distance_km=10.0,
                distance_source="brouter_v1",
                match_score=50 + (i % 40),
                status="new",
            )
            for i in range(40)
        ]
    )
    page = JobsPage(config_service)
    page.resize(480, 320)
    page.job_list.setFixedHeight(90)
    page.show()
    qapp.processEvents()
    page.apply_filter_pass(preserve_view=False)
    qapp.processEvents()
    assert page.job_list.count() >= 10
    page.job_list.setCurrentRow(8)
    qapp.processEvents()
    selected = page.job_list.currentItem().data(Qt.ItemDataRole.UserRole)
    bar = page.job_list.verticalScrollBar()
    if bar.maximum() == 0:
        bar.setRange(0, 40)
    target = max(1, bar.maximum() // 2)
    bar.setValue(target)
    page.apply_filter_pass(preserve_view=True)
    qapp.processEvents()
    current = page.job_list.currentItem()
    assert current is not None
    assert current.data(Qt.ItemDataRole.UserRole) == selected
    assert page.job_list.verticalScrollBar().value() == target
