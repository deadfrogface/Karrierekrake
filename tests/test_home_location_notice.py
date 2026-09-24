"""Home-location notice refresh and distance-skip reliability (PR #67)."""

from __future__ import annotations

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication

from core.config import LocationConfig
from core.database import Database
from core.geo_dataset import get_geo_dataset_manager, reset_geo_dataset_manager_for_tests
from core.geo_resolve import reset_pgeocode_index_for_tests, resolve_city_pgeocode
from core.location import LocationService, enrich_job_locations, home_location_notice
from core.matcher import apply_distance_scoring
from core.models import Job, RemoteType
from desktop.i18n import i18n
from desktop.pages.dashboard import DashboardPage
from desktop.pages.profile_sections import LocationWorkSection
from desktop.pages.settings import SettingsPage
from desktop.services import ConfigService
from desktop.services.schedule_service import ScheduleService


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


def _save_home(config_service: ConfigService, **fields) -> None:
    cfg = config_service.load()
    loc = cfg.profile.location
    for key, value in fields.items():
        setattr(loc, key, value)
    config_service.save(cfg)


def _seed_stale_warning(config_service: ConfigService) -> None:
    cfg = config_service.load()
    db = Database(cfg.db_path)
    run_id = db.start_search_run()
    db.finish_search_run(run_id, "ok", {"home_warning": "Standort nicht prüfbar"})


def test_berlin_resolve_clears_stale_home_warning(qapp, config_service, geo_ready, monkeypatch):
    monkeypatch.setattr(ScheduleService, "sync_from_config", lambda self: (True, "ok"))
    i18n.set_language("de")
    _save_home(
        config_service,
        home_address="Berlin, Deutschland",
        city="Berlin",
        postal_code="",
        country="DE",
        home_latitude=None,
        home_longitude=None,
        home_geocoded_address="",
    )
    _seed_stale_warning(config_service)
    notice = home_location_notice(config_service.load().profile.location)
    assert notice.status == "resolved"
    assert notice.ask_postal is False

    page = DashboardPage(config_service)
    page.refresh()
    assert not page.home_warning_label.isHidden()
    assert "aufgelöst" in page.home_warning_label.text()
    assert "nicht prüfbar" not in page.home_warning_label.text()
    assert "Berlin" in page.home_warning_label.text()

    settings = SettingsPage(config_service)
    settings.load_from_config()
    assert not settings.home_notice.isHidden()
    assert "aufgelöst" in settings.home_notice.text()
    assert "nicht prüfbar" not in settings.home_notice.text()

    section = LocationWorkSection()
    section.home_address.setText("Berlin, Deutschland")
    section.country.setText("DE")
    section.refresh_home_notice()
    assert "aufgelöst" in section.home_notice.text()
    assert "nicht prüfbar" not in section.home_notice.text()
    assert config_service.load().profile.location.home_latitude is None


def test_ambiguous_home_shows_postal_hint_without_guessing(
    qapp, config_service, geo_ready, monkeypatch
):
    monkeypatch.setattr(ScheduleService, "sync_from_config", lambda self: (True, "ok"))
    i18n.set_language("de")
    loc = LocationConfig(home_address="Halle", city="Halle", postal_code="", country="DE")
    notice = home_location_notice(loc)
    assert notice.status == "ambiguous"
    assert notice.ask_postal is True
    assert loc.home_latitude is None and loc.home_longitude is None

    _save_home(
        config_service,
        home_address="Halle",
        city="Halle",
        postal_code="",
        country="DE",
        home_latitude=None,
        home_longitude=None,
        home_geocoded_address="",
    )
    page = DashboardPage(config_service)
    page.refresh()
    assert not page.home_warning_label.isHidden()
    assert "Postleitzahl" in page.home_warning_label.text()
    assert "geschätzt" in page.home_warning_label.text()

    settings = SettingsPage(config_service)
    settings.load_from_config()
    assert not settings.home_notice.isHidden()
    assert "Postleitzahl" in settings.home_notice.text()

    loaded = config_service.load().profile
    section = LocationWorkSection()
    section.load(loaded.location, loaded.employment, loaded.filters)
    assert "Postleitzahl" in section.home_notice.text()
    assert not section.home_notice.isHidden()

    resolved = home_location_notice(
        LocationConfig(home_address="06108 Halle", city="Halle", postal_code="06108", country="DE")
    )
    assert resolved.status == "resolved"
    assert resolved.ask_postal is False


def test_unresolved_distance_skip_does_not_hang(geo_ready, tmp_path, monkeypatch):
    import pgeocode

    def _forbid_query_location(self, *args, **kwargs):
        raise AssertionError("query_location must not run on the skip path")

    monkeypatch.setattr(pgeocode.Nominatim, "query_location", _forbid_query_location)

    frank = resolve_city_pgeocode("Frankfurt", "DE")
    assert frank.status == "AMBIGUOUS"
    assert frank.latitude is None and frank.longitude is None

    from core.config import AppConfig

    cfg = AppConfig()
    cfg.root = tmp_path
    cfg.profile.location = LocationConfig(
        home_address="Halle",
        city="Halle",
        postal_code="",
        country="DE",
        max_distance_km=30,
        allow_remote_germany=True,
        allow_hybrid=True,
    )
    db = Database(tmp_path / "skip.db", recover=False)
    svc = LocationService(db, cfg)
    jobs = [
        Job(
            id=f"j{i}",
            title="Sachbearbeiter",
            company="Beispiel",
            city="(a+)+$" if i % 2 == 0 else "Halle",
            country_code="DE",
            remote_type=RemoteType.ONSITE.value,
            match_score=80,
            status="new",
        )
        for i in range(24)
    ]
    started = time.perf_counter()
    enrich_job_locations(jobs, svc)
    for job in jobs:
        apply_distance_scoring(job, cfg)
    elapsed = time.perf_counter() - started
    assert elapsed < 2.0, elapsed
    assert svc.stats.skipped_distance_no_home is True
    for job in jobs:
        assert job.distance_km is None
        assert job.latitude is None
        assert job.status != "ignored"


def test_resolved_home_skips_ambiguous_jobs_without_regex_scan(geo_ready, tmp_path, monkeypatch):
    import pgeocode

    calls = {"n": 0}

    def _forbid_query_location(self, *args, **kwargs):
        calls["n"] += 1
        raise AssertionError("query_location")

    monkeypatch.setattr(pgeocode.Nominatim, "query_location", _forbid_query_location)

    from core.config import AppConfig

    cfg = AppConfig()
    cfg.root = tmp_path
    cfg.profile.location = LocationConfig(
        home_address="10115 Berlin",
        city="Berlin",
        postal_code="10115",
        country="DE",
        max_distance_km=30,
        allow_remote_germany=True,
        allow_hybrid=True,
    )
    db = Database(tmp_path / "berlin-skip.db", recover=False)
    svc = LocationService(db, cfg)
    job = Job(
        id="bomb",
        title="Sachbearbeiter",
        company="Beispiel",
        city="(a+)+$",
        country_code="DE",
        remote_type=RemoteType.ONSITE.value,
        match_score=70,
        status="new",
    )
    started = time.perf_counter()
    enrich_job_locations([job], svc)
    apply_distance_scoring(job, cfg)
    assert time.perf_counter() - started < 3.0
    assert calls["n"] == 0
    assert job.distance_km is None
    assert job.latitude is None
    assert job.status != "ignored"
    assert svc.home_resolved is True


def test_known_km_is_shown_when_home_resolved_and_hidden_when_ambiguous():
    from desktop.i18n import i18n
    from desktop.pages.jobs import format_commute_label
    from desktop.viewmodels.job_fit import build_job_fit_viewmodel
    from core.config import AppConfig, SearchPreferences
    from core.search_intent import SearchIntent

    i18n.set_language("de")
    job = Job(
        id="row",
        title="DevOps",
        company="Alpen IT",
        city="Berlin",
        remote_type=RemoteType.HYBRID.value,
        distance_km=14,
        distance_source="",
        match_score=80,
        status="new",
    )
    label = format_commute_label(job, home_status="resolved")
    assert "14" in label
    assert "Luftlinie" in label
    assert "nicht prüfbar" not in label
    skipped = format_commute_label(job, home_status="ambiguous")
    assert "PLZ" in skipped
    assert "14" not in skipped

    cfg = AppConfig(
        profile=SearchPreferences(
            location=LocationConfig(home_address="Halle", city="Halle", country="DE"),
            search_intent=SearchIntent(radius_km=20, countries=["DE"]),
        )
    )
    vm = build_job_fit_viewmodel(job, cfg)
    text = " ".join(b.text for b in vm.bullets)
    assert "within radius" not in text.casefold()
    assert "PLZ" in text
    assert "14" not in text


def test_unknown_distance_does_not_claim_within_radius():
    from core.intent_filter import apply_search_intent
    from core.search_intent import SearchIntent

    job = Job(
        title="DevOps",
        company="Alpen IT",
        city="Berlin",
        remote_type=RemoteType.HYBRID.value,
        distance_km=None,
    )
    result = apply_search_intent(job, SearchIntent(radius_km=20, countries=["DE"]))
    blob = " ".join(result.why_shown)
    assert "within radius" not in blob.casefold()
    assert result.included is True
    assert result.excluded is False


def test_profile_save_updates_overview_home_from_visible_address(
    qapp, config_service, geo_ready, monkeypatch
):
    from PySide6.QtWidgets import QMessageBox

    from desktop.pages.profile import ProfilePage

    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)
    i18n.set_language("de")
    page = ProfilePage(config_service)
    page.load_from_config()
    page.applicant.city.setText("Berlin, Deutschland")
    page.applicant.postal_code.setText("")
    page.applicant.app_country.setText("DE")
    page.save()
    loc = config_service.load().profile.location
    assert "Berlin" in (loc.city or loc.home_address)
    assert loc.home_latitude is None
    notice = home_location_notice(loc)
    assert notice.status == "resolved"
    assert "aufgelöst" in page.home_status.text()
    assert "nicht prüfbar" not in page.home_status.text()

    dash = DashboardPage(config_service)
    dash.refresh()
    assert "aufgelöst" in dash.home_warning_label.text()

    page.applicant.city.setText("Halle")
    page.applicant.postal_code.setText("")
    page.save()
    loc = config_service.load().profile.location
    assert home_location_notice(loc).status == "ambiguous"
    assert loc.home_latitude is None and not (loc.postal_code or "").strip()
    assert "Postleitzahl" in page.home_status.text()
    dash.refresh()
    assert "Postleitzahl" in dash.home_warning_label.text()

    page.applicant.city.setText("Halle")
    page.applicant.postal_code.setText("06108")
    page.save()
    loc = config_service.load().profile.location
    assert home_location_notice(loc).status == "resolved"
    assert "aufgelöst" in page.home_status.text()
    dash.refresh()
    assert "aufgelöst" in dash.home_warning_label.text()
    assert "nicht prüfbar" not in dash.home_warning_label.text()
