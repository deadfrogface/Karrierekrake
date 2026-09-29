"""Andere Profil-Dialoge dürfen den Such-Wohnort nicht aus dem Lebenslauf füllen.

Auf ``main`` ruft jeder Drawer ``ProfilePage.save()`` auf, und ``save()`` kopiert
``application.street/postal_code/city`` bedingungslos nach ``profile.location``.
Ein leerer Wohnort wird dadurch zur Kontaktadresse des importierten Lebenslaufs,
und der Distanzfilter wirft danach weiter entfernte Stellen (Nordmole) aus.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication, QMessageBox, QVBoxLayout, QWidget

from core import geo_resolve
from core.config import (
    EducationEntry,
    ExperienceEntry,
    LanguageEntry,
    LocationConfig,
)
from core.database import Database
from core.geo_dataset import (
    get_geo_dataset_manager,
    reset_geo_dataset_manager_for_tests,
)
from core.geo_resolve import reset_pgeocode_index_for_tests
from core.location import home_location_notice
from core.models import Job, RemoteType
from desktop.design_system.v2_chrome import SectionEditDrawer
from desktop.i18n import i18n
from desktop.pages.jobs import JobsPage
from desktop.pages.profile import (
    _HOME_ADOPT_SCOPES,
    _SECTION_SCOPES_WITHOUT_HOME,
    PROFILE_DRAWER_KEYS,
    ProfilePage,
)
from desktop.services import ConfigService

CV_STREET = "Rosenfelder Straße 103c"
CV_POSTAL = "22765"
CV_CITY = "Hamburg"
RESOLVABLE_STREET = "Alexanderplatz 1"
RESOLVABLE_POSTAL = "10115"
RESOLVABLE_CITY = "Berlin"


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
    """Wie das Hauptfenster: ``refresh_all`` lädt die Profilseite einmal neu."""

    def __init__(self, page: ProfilePage) -> None:
        super().__init__()
        self.profile = page
        layout = QVBoxLayout(self)
        layout.addWidget(page)

    def refresh_all(self) -> None:
        self.profile.load_from_config()


def _silence_dialogs(monkeypatch) -> None:
    monkeypatch.setattr(
        "desktop.pages.profile.QMessageBox.information",
        lambda *args, **kwargs: QMessageBox.StandardButton.Ok,
    )
    monkeypatch.setattr(
        "desktop.pages.profile.QMessageBox.warning",
        lambda *args, **kwargs: pytest.fail(f"warning: {args!r}"),
    )


def _location_block(text: str) -> str:
    lines = text.splitlines(keepends=True)
    start = next(i for i, line in enumerate(lines) if line.startswith("location:"))
    end = next(
        (
            i
            for i in range(start + 1, len(lines))
            if lines[i][:1] not in {" ", "\t", "\n", "\r"}
        ),
        len(lines),
    )
    return "".join(lines[start:end])


def _seed_cv_contact(config_service: ConfigService, *, postal: str, city: str, street: str) -> None:
    cfg = config_service.load()
    cfg.application.street = street
    cfg.application.postal_code = postal
    cfg.application.city = city
    cfg.application.country = "DE"
    cfg.application.field_origins = {
        "street": "cv",
        "postal_code": "cv",
        "city": "cv",
        "country": "cv",
    }
    cfg.profile.location.home_address = ""
    cfg.profile.location.postal_code = ""
    cfg.profile.location.city = ""
    cfg.profile.location.home_latitude = None
    cfg.profile.location.home_longitude = None
    cfg.profile.location.home_geocoded_address = ""
    cfg.profile.location.max_distance_km = 20
    config_service.save(cfg)


def _open_page(qapp, config_service) -> tuple[ProfilePage, _Host]:
    i18n.set_language("de")
    page = ProfilePage(config_service)
    host = _Host(page)
    host.show()
    qapp.processEvents()
    page.load_from_config()
    qapp.processEvents()
    return page, host


def _accept_drawer(page: ProfilePage) -> None:
    page._drawer.present = lambda _content, focus=None: SectionEditDrawer.DialogCode.Accepted  # type: ignore[method-assign]


def _save_section(page: ProfilePage, key: str) -> None:
    _accept_drawer(page)
    page._edit_section(key)


def test_cancel_personal_edit_cannot_leak_into_later_skill_save(
    qapp, config_service, monkeypatch
) -> None:
    _silence_dialogs(monkeypatch)
    page, _host = _open_page(qapp, config_service)
    original = config_service.profile_path.read_bytes()

    def reject_with_edit(_content, focus=None):
        page.applicant.first_name.setText("Nicht speichern")
        return SectionEditDrawer.DialogCode.Rejected

    page._drawer.present = reject_with_edit
    page._edit_section("personal")
    assert page.applicant.first_name.text() == ""
    assert config_service.profile_path.read_bytes() == original

    page.qualifications.skills.set_items(["SAP"])
    _save_section(page, "skills")
    cfg = config_service.load()
    assert cfg.application.first_name == ""
    assert cfg.profile.qualifications.skill_values() == ["SAP"]


def test_cancel_search_home_restores_unsaved_widget(qapp, config_service) -> None:
    page, _host = _open_page(qapp, config_service)
    original = config_service.profile_path.read_bytes()

    def reject_with_edit(_content, focus=None):
        page.location_work.home_address.setText("Falscher Suchort 1")
        return SectionEditDrawer.DialogCode.Rejected

    page._drawer.present = reject_with_edit
    page.edit_search_home()
    assert page.location_work.home_address.text() == ""
    assert config_service.profile_path.read_bytes() == original


def _count_geo(monkeypatch) -> dict[str, int]:
    calls = {"geo": 0}
    original_postal = geo_resolve.resolve_postal_pgeocode
    original_city = geo_resolve.resolve_city_pgeocode

    def _postal(*args, **kwargs):
        calls["geo"] += 1
        return original_postal(*args, **kwargs)

    def _city(*args, **kwargs):
        calls["geo"] += 1
        return original_city(*args, **kwargs)

    monkeypatch.setattr(geo_resolve, "resolve_postal_pgeocode", _postal)
    monkeypatch.setattr(geo_resolve, "resolve_city_pgeocode", _city)
    return calls


def _home_tuple(config_service: ConfigService) -> tuple:
    loc = config_service.load().profile.location
    return (
        loc.home_address,
        loc.postal_code,
        loc.city,
        loc.country,
        loc.max_distance_km,
        loc.allow_remote_germany,
        loc.allow_hybrid,
        loc.cross_border_dach,
        loc.home_latitude,
        loc.home_longitude,
        loc.home_geocoded_address,
    )


def _mutate(page: ProfilePage, key: str) -> None:
    if key == "skills":
        page.qualifications.skills.set_items(["SAP"])
    elif key == "experience":
        page.experience.experience.set_items(
            [ExperienceEntry(title="Disponent", company="Nordmole", source="manual")]
        )
    elif key == "education":
        page.education.education.set_items(
            [EducationEntry(qualification="Fachwirt", institution="IHK", source="manual")]
        )
    elif key == "languages":
        page.languages.languages.set_items(
            [LanguageEntry(language="Spanisch", level="B2", source="manual")]
        )
    elif key == "career":
        page.career.desired_titles.set_items(["Disponent"])
    elif key == "application":
        page.applicant.notice.setText("4 Wochen")
    elif key in {"docs", "personal"}:
        return
    else:
        raise AssertionError(key)


def _assert_section_persisted(config_service: ConfigService, key: str) -> None:
    cfg = config_service.load()
    if key == "skills":
        assert cfg.profile.qualifications.skill_values() == ["SAP"]
    elif key == "experience":
        titles = [e.title for e in cfg.profile.qualifications.work_experience]
        assert titles == ["Disponent"]
    elif key == "education":
        quals = [e.qualification for e in cfg.profile.qualifications.education]
        assert quals == ["Fachwirt"]
    elif key == "languages":
        labels = [lang.label() for lang in cfg.profile.qualifications.languages]
        assert "Spanisch" in " ".join(labels)
    elif key == "career":
        assert cfg.profile.jobs.desired_titles == ["Disponent"]
    elif key == "application":
        assert cfg.application.notice_period == "4 Wochen"
    elif key in {"docs", "personal"}:
        return


_OTHER_SECTIONS = (
    "skills",
    "experience",
    "education",
    "languages",
    "career",
    "application",
    "docs",
    "personal",
)


@pytest.mark.parametrize("key", _OTHER_SECTIONS)
def test_empty_home_stays_empty_when_other_section_saves(
    qapp, config_service, geo_ready, monkeypatch, key
):
    _silence_dialogs(monkeypatch)
    _seed_cv_contact(
        config_service, street=CV_STREET, postal=CV_POSTAL, city=CV_CITY
    )
    page, _host = _open_page(qapp, config_service)
    before = _location_block(config_service.profile_path.read_text(encoding="utf-8"))
    _mutate(page, key)
    _save_section(page, key)
    after = _location_block(config_service.profile_path.read_text(encoding="utf-8"))
    assert after == before
    loc = config_service.load().profile.location
    assert loc.home_address == ""
    assert loc.postal_code == ""
    assert loc.city == ""
    app = config_service.load().application
    assert app.street == CV_STREET
    assert app.postal_code == CV_POSTAL
    assert app.city == CV_CITY
    _assert_section_persisted(config_service, key)


@pytest.mark.parametrize("key", ("skills", "experience", "education", "languages", "career", "docs"))
def test_set_home_is_byte_identical_after_other_section_save(
    qapp, config_service, geo_ready, monkeypatch, key
):
    _silence_dialogs(monkeypatch)
    cfg = config_service.load()
    cfg.application.street = "Quendelstieg 4"
    cfg.application.postal_code = "00000"
    cfg.application.city = "Musterhafen"
    cfg.application.country = "DE"
    cfg.application.field_origins = {"street": "cv", "postal_code": "cv", "city": "cv"}
    cfg.profile.location.home_address = "Quendelstieg 4, 00000 Musterhafen, DE"
    cfg.profile.location.postal_code = "00000"
    cfg.profile.location.city = "Musterhafen"
    cfg.profile.location.country = "DE"
    cfg.profile.location.home_latitude = 53.551
    cfg.profile.location.home_longitude = 9.993
    cfg.profile.location.home_geocoded_address = "Quendelstieg 4, 00000 Musterhafen, DE"
    cfg.profile.location.max_distance_km = 35
    cfg.profile.location.allow_remote_germany = False
    cfg.profile.location.allow_hybrid = True
    config_service.save(cfg)
    from core.home_coord_cache import write_home_coordinates

    write_home_coordinates(
        config_service.dirs["cache"], cfg.profile.location, 53.551, 9.993
    )
    page, _host = _open_page(qapp, config_service)
    before = _location_block(config_service.profile_path.read_text(encoding="utf-8"))
    frozen = _home_tuple(config_service)
    calls = _count_geo(monkeypatch)
    reset_pgeocode_index_for_tests()
    _mutate(page, key)
    _save_section(page, key)
    after = _location_block(config_service.profile_path.read_text(encoding="utf-8"))
    assert after == before
    assert _home_tuple(config_service) == frozen
    assert calls["geo"] == 0
    _assert_section_persisted(config_service, key)


def test_explicit_contact_edit_still_updates_search_home(
    qapp, config_service, geo_ready, monkeypatch
):
    """Umgedreht: eine geänderte Kontaktadresse allein übernimmt den Wohnort nicht."""
    _silence_dialogs(monkeypatch)
    _seed_cv_contact(
        config_service, street=CV_STREET, postal=CV_POSTAL, city=CV_CITY
    )
    page, _host = _open_page(qapp, config_service)
    assert page.applicant.sync_home_from_address.isChecked() is False
    before = _location_block(config_service.profile_path.read_text(encoding="utf-8"))
    page.applicant.street.setText("Neuer Weg 1")
    page.applicant.postal_code.setText(RESOLVABLE_POSTAL)
    page.applicant.city.setText(RESOLVABLE_CITY)
    page.applicant.app_country.setText("DE")
    _save_section(page, "personal")
    after = _location_block(config_service.profile_path.read_text(encoding="utf-8"))
    assert after == before
    loc = config_service.load().profile.location
    assert loc.home_address == ""
    assert loc.postal_code == ""
    assert loc.city == ""
    app = config_service.load().application
    assert app.street == "Neuer Weg 1"
    assert app.postal_code == RESOLVABLE_POSTAL
    assert app.city == RESOLVABLE_CITY


@pytest.mark.parametrize("key", ("personal", "application"))
def test_street_edit_without_checkbox_keeps_different_home(
    qapp, config_service, geo_ready, monkeypatch, key
):
    """Gold (a): gesetzter, anderer Wohnort, Haken aus, nur die Straße ändern."""
    _silence_dialogs(monkeypatch)
    cfg = config_service.load()
    cfg.application.street = CV_STREET
    cfg.application.postal_code = CV_POSTAL
    cfg.application.city = CV_CITY
    cfg.application.country = "DE"
    cfg.profile.location.home_address = "Speicherstraße 2, 20095 Hamburg, DE"
    cfg.profile.location.postal_code = "20095"
    cfg.profile.location.city = "Hamburg"
    cfg.profile.location.country = "DE"
    cfg.profile.location.home_latitude = 53.551
    cfg.profile.location.home_longitude = 9.993
    cfg.profile.location.home_geocoded_address = "Speicherstraße 2, 20095 Hamburg, DE"
    config_service.save(cfg)
    config_service.set_sync_address_to_search(False)
    page, _host = _open_page(qapp, config_service)
    assert page.applicant.sync_home_from_address.isChecked() is False
    before = _location_block(config_service.profile_path.read_text(encoding="utf-8"))
    page.applicant.street.setText("Nur die Straße 9")
    _save_section(page, key)
    after = _location_block(config_service.profile_path.read_text(encoding="utf-8"))
    assert after == before
    app = config_service.load().application
    assert app.street == "Nur die Straße 9"
    assert app.postal_code == CV_POSTAL
    assert app.city == CV_CITY


def test_street_edit_without_checkbox_leaves_empty_home_empty(
    qapp, config_service, geo_ready, monkeypatch
):
    """Gold (b): leerer Wohnort, Haken aus, nur die Straße ändern."""
    _silence_dialogs(monkeypatch)
    _seed_cv_contact(
        config_service, street=CV_STREET, postal=CV_POSTAL, city=CV_CITY
    )
    page, _host = _open_page(qapp, config_service)
    assert page.applicant.sync_home_from_address.isChecked() is False
    page.applicant.street.setText("Nur die Straße 9")
    _save_section(page, "personal")
    loc = config_service.load().profile.location
    assert loc.home_address == ""
    assert loc.postal_code == ""
    assert loc.city == ""
    assert loc.home_latitude is None and loc.home_longitude is None
    assert config_service.load().application.street == "Nur die Straße 9"


def test_sync_checkbox_adopts_unchanged_cv_address(
    qapp, config_service, geo_ready, monkeypatch
):
    """Gold (c): gesetzter Haken übernimmt die Kontaktadresse in den Such-Wohnort."""
    _silence_dialogs(monkeypatch)
    _seed_cv_contact(
        config_service, street=CV_STREET, postal=CV_POSTAL, city=CV_CITY
    )
    page, _host = _open_page(qapp, config_service)
    assert page.applicant.sync_home_from_address.isChecked() is False
    page.applicant.sync_home_from_address.setChecked(True)
    _save_section(page, "personal")
    loc = config_service.load().profile.location
    assert loc.postal_code == CV_POSTAL
    assert loc.city == CV_CITY
    assert CV_STREET in (loc.home_address or "")
    assert config_service.get_sync_address_to_search() is True


def test_location_editor_input_is_saved_without_cv_overwrite(
    qapp, config_service, geo_ready, monkeypatch
):
    _silence_dialogs(monkeypatch)
    _seed_cv_contact(
        config_service, street=CV_STREET, postal=CV_POSTAL, city=CV_CITY
    )
    page, _host = _open_page(qapp, config_service)
    page.location_work.home_address.setText("Speicherstraße 2")
    page.location_work.postal_code.setText("20095")
    page.save()
    loc = config_service.load().profile.location
    assert loc.home_address == "Speicherstraße 2"
    assert loc.postal_code == "20095"
    assert loc.city == ""
    assert CV_STREET not in (loc.home_address or "")
    app = config_service.load().application
    assert app.street == CV_STREET
    assert app.postal_code == CV_POSTAL
    assert app.city == CV_CITY


def test_skill_save_does_not_add_a_geo_resolve_or_second_card_build(
    qapp, config_service, geo_ready, monkeypatch
):
    _silence_dialogs(monkeypatch)
    _seed_cv_contact(
        config_service,
        street=RESOLVABLE_STREET,
        postal=RESOLVABLE_POSTAL,
        city=RESOLVABLE_CITY,
    )
    page, _host = _open_page(qapp, config_service)
    calls = {"geo": 0, "cards": 0}
    original_postal = geo_resolve.resolve_postal_pgeocode
    original_city = geo_resolve.resolve_city_pgeocode
    original_cards = page.refresh_cards

    def _postal(*args, **kwargs):
        calls["geo"] += 1
        return original_postal(*args, **kwargs)

    def _city(*args, **kwargs):
        calls["geo"] += 1
        return original_city(*args, **kwargs)

    def _cards() -> None:
        calls["cards"] += 1
        original_cards()

    monkeypatch.setattr(geo_resolve, "resolve_postal_pgeocode", _postal)
    monkeypatch.setattr(geo_resolve, "resolve_city_pgeocode", _city)
    page.refresh_cards = _cards  # type: ignore[method-assign]
    reset_pgeocode_index_for_tests()
    page.qualifications.skills.set_items(["SAP"])
    _save_section(page, "skills")
    qapp.processEvents()
    assert calls["cards"] == 1
    assert calls["geo"] == 0
    loc = config_service.load().profile.location
    assert loc.home_address == ""
    assert loc.postal_code == ""
    assert loc.city == ""


def test_skill_save_keeps_existing_home_at_one_geo_resolve(
    qapp, config_service, geo_ready, monkeypatch
):
    _silence_dialogs(monkeypatch)
    cfg = config_service.load()
    cfg.application.street = CV_STREET
    cfg.application.postal_code = CV_POSTAL
    cfg.application.city = CV_CITY
    cfg.application.country = "DE"
    cfg.profile.location.home_address = "Alexanderplatz 1, 10115 Berlin, DE"
    cfg.profile.location.postal_code = RESOLVABLE_POSTAL
    cfg.profile.location.city = RESOLVABLE_CITY
    cfg.profile.location.country = "DE"
    cfg.profile.location.home_latitude = None
    cfg.profile.location.home_longitude = None
    cfg.profile.location.home_geocoded_address = ""
    config_service.save(cfg)
    page, _host = _open_page(qapp, config_service)
    calls = {"geo": 0, "cards": 0}
    original_postal = geo_resolve.resolve_postal_pgeocode
    original_city = geo_resolve.resolve_city_pgeocode
    original_cards = page.refresh_cards

    def _postal(*args, **kwargs):
        calls["geo"] += 1
        return original_postal(*args, **kwargs)

    def _city(*args, **kwargs):
        calls["geo"] += 1
        return original_city(*args, **kwargs)

    def _cards() -> None:
        calls["cards"] += 1
        original_cards()

    monkeypatch.setattr(geo_resolve, "resolve_postal_pgeocode", _postal)
    monkeypatch.setattr(geo_resolve, "resolve_city_pgeocode", _city)
    page.refresh_cards = _cards  # type: ignore[method-assign]
    reset_pgeocode_index_for_tests()
    page.qualifications.skills.set_items(["SAP"])
    _save_section(page, "skills")
    qapp.processEvents()
    assert calls["cards"] == 1
    assert calls["geo"] <= 1
    loc = config_service.load().profile.location
    assert loc.postal_code == RESOLVABLE_POSTAL
    assert RESOLVABLE_CITY in (loc.city or loc.home_address)
    assert CV_POSTAL not in (loc.postal_code or "")
    assert CV_CITY not in (loc.city or "")


def test_second_skill_save_does_not_resolve_geo_again(
    qapp, config_service, geo_ready, monkeypatch
):
    """Skill-Saves lösen denselben Wohnort nicht erneut auf und schreiben keine Koordinaten."""
    _silence_dialogs(monkeypatch)
    cfg = config_service.load()
    cfg.application.street = CV_STREET
    cfg.application.postal_code = CV_POSTAL
    cfg.application.city = CV_CITY
    cfg.application.country = "DE"
    cfg.profile.location.home_address = "Alexanderplatz 1, 10115 Berlin, DE"
    cfg.profile.location.postal_code = RESOLVABLE_POSTAL
    cfg.profile.location.city = RESOLVABLE_CITY
    cfg.profile.location.country = "DE"
    cfg.profile.location.home_latitude = None
    cfg.profile.location.home_longitude = None
    cfg.profile.location.home_geocoded_address = ""
    config_service.save(cfg)
    page, _host = _open_page(qapp, config_service)
    calls = _count_geo(monkeypatch)
    reset_pgeocode_index_for_tests()
    page.qualifications.skills.set_items(["SAP"])
    _save_section(page, "skills")
    assert calls["geo"] <= 1
    loc = config_service.load().profile.location
    assert loc.home_address == "Alexanderplatz 1, 10115 Berlin, DE"
    assert loc.postal_code == RESOLVABLE_POSTAL
    assert loc.city == RESOLVABLE_CITY
    assert loc.home_latitude is None and loc.home_longitude is None
    calls["geo"] = 0
    page.qualifications.skills.set_items(["SAP", "Excel"])
    _save_section(page, "skills")
    assert calls["geo"] == 0
    again = config_service.load().profile.location
    assert again.home_latitude is None and again.home_longitude is None
    assert config_service.load().profile.qualifications.skill_values() == ["SAP", "Excel"]


def test_checkbox_on_skill_save_does_not_adopt_contact(
    qapp, config_service, geo_ready, monkeypatch
):
    _silence_dialogs(monkeypatch)
    _seed_cv_contact(
        config_service, street=CV_STREET, postal=CV_POSTAL, city=CV_CITY
    )
    page, _host = _open_page(qapp, config_service)
    page.applicant.sync_home_from_address.setChecked(True)
    page.qualifications.skills.set_items(["SAP"])
    _save_section(page, "skills")
    loc = config_service.load().profile.location
    assert loc.home_address == ""
    assert loc.postal_code == ""
    assert loc.city == ""


def test_edit_section_loads_config_only_inside_save(
    qapp, config_service, geo_ready, monkeypatch
):
    import inspect

    from desktop.services import ConfigService

    _silence_dialogs(monkeypatch)
    _seed_cv_contact(
        config_service, street=CV_STREET, postal=CV_POSTAL, city=CV_CITY
    )
    callers: list[str] = []
    original = ConfigService.load

    def _load(self):
        callers.append(inspect.stack()[1].function)
        return original(self)

    monkeypatch.setattr(ConfigService, "load", _load)
    page, _host = _open_page(qapp, config_service)
    callers.clear()
    page.qualifications.skills.set_items(["SAP"])
    _save_section(page, "skills")
    assert "_edit_section" not in callers
    assert callers.count("save") == 1


def _seed_resolvable_home_without_coords(config_service: ConfigService) -> None:
    cfg = config_service.load()
    cfg.application.street = CV_STREET
    cfg.application.postal_code = CV_POSTAL
    cfg.application.city = CV_CITY
    cfg.application.country = "DE"
    cfg.profile.location.home_address = "Alexanderplatz 1, 10115 Berlin, DE"
    cfg.profile.location.postal_code = RESOLVABLE_POSTAL
    cfg.profile.location.city = RESOLVABLE_CITY
    cfg.profile.location.country = "DE"
    cfg.profile.location.home_latitude = None
    cfg.profile.location.home_longitude = None
    cfg.profile.location.home_geocoded_address = ""
    config_service.save(cfg)


def _open_main_window(qapp, config_service, monkeypatch):
    monkeypatch.setattr("desktop.tray.AppTray.show", lambda self: None)
    from desktop.main_window import MainWindow

    win = MainWindow(config_service)
    win.show()
    qapp.processEvents()
    return win


def _pump_until_resolved(qapp, label, timeout_s: float = 20.0) -> str:
    import time

    deadline = time.monotonic() + timeout_s
    while "aufgelöst" not in label.text():
        if time.monotonic() >= deadline:
            raise AssertionError(label.text())
        qapp.processEvents()
    return label.text()


def test_startup_does_not_write_profile_yaml(
    qapp, config_service, geo_ready, monkeypatch
):
    """K: der Geo-Ready-Slot schreibt profile.yaml nicht."""
    _silence_dialogs(monkeypatch)
    _seed_resolvable_home_without_coords(config_service)
    path = config_service.profile_path
    before = path.read_bytes()
    mtime = path.stat().st_mtime_ns
    win = _open_main_window(qapp, config_service, monkeypatch)
    try:
        _pump_until_resolved(qapp, win.profile.home_status)
        assert path.read_bytes() == before
        assert path.stat().st_mtime_ns == mtime
        loc = config_service.load().profile.location
        assert loc.home_latitude is None and loc.home_longitude is None
    finally:
        win._shutting_down = True
        win.close()
        qapp.processEvents()


def test_home_resolves_once_until_the_user_changes_it(
    qapp, config_service, geo_ready, monkeypatch
):
    """M: 1 Auflösung beim Start, danach 0, nach Wohnort-Änderung genau 1."""
    import core.location as location

    _silence_dialogs(monkeypatch)
    _seed_resolvable_home_without_coords(config_service)
    calls = {"n": 0}
    original = location.resolve_place

    def _wrapped(*args, **kwargs):
        result = original(*args, **kwargs)
        if getattr(result, "reason", "") != "geo_index_loading":
            calls["n"] += 1
        return result

    monkeypatch.setattr(location, "resolve_place", _wrapped)
    reset_pgeocode_index_for_tests()
    win = _open_main_window(qapp, config_service, monkeypatch)
    try:
        _pump_until_resolved(qapp, win.profile.home_status)
        assert calls["n"] == 1
        calls["n"] = 0
        win.refresh_all()
        qapp.processEvents()
        assert calls["n"] == 0
        win.refresh_all()
        assert calls["n"] == 0
        win.profile._drawer.present = (  # type: ignore[method-assign]
            lambda _content, focus=None: SectionEditDrawer.DialogCode.Accepted
        )
        win.profile.qualifications.skills.set_items(["SAP"])
        win.profile._edit_section("skills")
        assert calls["n"] == 0
        win.profile.qualifications.skills.set_items(["SAP", "Excel"])
        win.profile._edit_section("skills")
        assert calls["n"] == 0
        loc = config_service.load().profile.location
        assert loc.home_latitude is None and loc.home_longitude is None
        win.profile.location_work.home_address.setText("Speicherstraße 2")
        win.profile.location_work.postal_code.setText("20095")
        win.profile.save()
        assert calls["n"] == 1
        changed = config_service.load().profile.location
        assert changed.postal_code == "20095"
        assert changed.home_address == "Speicherstraße 2"
        from core.home_coord_cache import read_home_coordinates

        assert read_home_coordinates(config_service.dirs["cache"], changed) is not None
        assert "home_latitude" not in config_service.profile_path.read_text(encoding="utf-8")
        calls["n"] = 0
        toggled = config_service.load()
        toggled.profile.location.cross_border_dach = False
        toggled.settings.cross_border_dach_enabled = False
        config_service.save(toggled)
        win.refresh_all()
        qapp.processEvents()
        # The file key includes cross_border, so the toggle is a new lookup.
        assert calls["n"] == 1
    finally:
        win._shutting_down = True
        win.close()
        qapp.processEvents()


def _home_for(config_service: ConfigService, **fields):
    from core.location import reset_home_resolution_cache_for_tests

    cfg = config_service.load()
    loc = cfg.profile.location
    loc.home_latitude = None
    loc.home_longitude = None
    loc.home_geocoded_address = ""
    for name, value in fields.items():
        setattr(loc, name, value)
    cfg.settings.cross_border_dach_enabled = bool(loc.cross_border_dach)
    reset_home_resolution_cache_for_tests()
    return cfg, loc


def _hint_and_resolve_home_agree(
    config_service, cross_border, place, resolved
):
    """Hinweis und resolve_home sehen Status und Koordinaten derselben Auflösung."""
    from desktop.i18n import tr

    from core.location import LocationService

    i18n.set_language("de")
    cfg, loc = _home_for(
        config_service,
        cross_border_dach=cross_border,
        **place,
    )
    notice = home_location_notice(loc, cfg)
    home = LocationService(Database(cfg.db_path, recover=False), cfg).resolve_home()
    assert (notice.status == "resolved") is home.resolved is resolved
    if home.coords is None:
        assert notice.latitude is None and notice.longitude is None
        text = tr(notice.notice_key, place=notice.place_label or "")
        assert "Distanzfilter aktiv" not in text
    else:
        assert notice.latitude == pytest.approx(home.coords[0])
        assert notice.longitude == pytest.approx(home.coords[1])
        assert "Distanzfilter aktiv" in tr(notice.notice_key, place=notice.place_label or "")


@pytest.mark.parametrize("cross_border", [False, True])
@pytest.mark.parametrize(
    ("place", "resolved"),
    [
        (
            {
                "home_address": "Alexanderplatz 1, 10115 Berlin, DE",
                "postal_code": "10115",
                "city": "Berlin",
                "country": "DE",
            },
            True,
        ),
        (
            {
                "home_address": "Stephansplatz 1, 1010 Wien, AT",
                "postal_code": "1010",
                "city": "Wien",
                "country": "AT",
            },
            True,
        ),
        (
            {
                "home_address": "Frankfurt",
                "postal_code": "",
                "city": "Frankfurt",
                "country": "DE",
            },
            False,
        ),
    ],
)
def test_hint_matches_resolve_home_for_border_and_country(
    config_service, geo_ready, cross_border, place, resolved
):
    _hint_and_resolve_home_agree(config_service, cross_border, place, resolved)


def test_index_generation_retries_a_cached_miss(config_service, geo_ready, monkeypatch):
    """Ein Fehlschlag bleibt nur bis zur nächsten Index-Generation im Cache."""
    import core.geo_resolve as geo
    import core.location as location

    cfg, loc = _home_for(
        config_service,
        home_address="Stephansplatz 1, 1010 Wien, AT",
        postal_code="1010",
        city="Wien",
        country="AT",
        cross_border_dach=True,
    )
    # First LocationService may seed the dataset and bump the index epoch.
    LocationService = location.LocationService
    LocationService(Database(cfg.db_path, recover=False), cfg)
    calls = {"n": 0}
    original = location.resolve_place

    def _wrapped(*args, **kwargs):
        result = original(*args, **kwargs)
        if getattr(result, "reason", "") != "geo_index_loading":
            calls["n"] += 1
        return result

    monkeypatch.setattr(location, "resolve_place", _wrapped)
    real_postal = geo.resolve_postal_pgeocode

    def _miss(postal_code, country_code):
        from core.geo_resolve import PlaceResolution

        return PlaceResolution(
            status="UNKNOWN",
            reason="plz_not_found",
            country_code=country_code,
        )

    monkeypatch.setattr(geo, "resolve_postal_pgeocode", _miss)
    failed = home_location_notice(loc, cfg)
    assert failed.status != "resolved"
    assert calls["n"] == 1
    monkeypatch.setattr(geo, "resolve_postal_pgeocode", real_postal)
    calls["n"] = 0
    before = geo.geo_index_generation()
    geo._bump_geo_index_generation()
    assert geo.geo_index_generation() == before + 1
    resolved = home_location_notice(loc, cfg)
    assert calls["n"] == 1
    assert resolved.status == "resolved"
    assert resolved.latitude is not None and resolved.longitude is not None
    home = location.LocationService(Database(cfg.db_path, recover=False), cfg).resolve_home()
    assert home.resolved is True
    assert calls["n"] == 1
    assert home.coords is not None
    assert resolved.latitude == pytest.approx(home.coords[0])
    assert resolved.longitude == pytest.approx(home.coords[1])


@pytest.mark.parametrize("key", PROFILE_DRAWER_KEYS)
def test_drawer_key_is_in_exactly_one_home_set(key):
    adopt = key in _HOME_ADOPT_SCOPES
    deny = key in _SECTION_SCOPES_WITHOUT_HOME
    assert adopt != deny


def test_drawer_mapping_matches_the_home_partition(qapp, config_service):
    page = ProfilePage(config_service)
    live = set(page._drawer_mapping())
    adopt = set(_HOME_ADOPT_SCOPES) - {None}
    deny = set(_SECTION_SCOPES_WITHOUT_HOME)
    assert adopt.isdisjoint(deny)
    assert live == set(PROFILE_DRAWER_KEYS) == adopt | deny
    assert None in _HOME_ADOPT_SCOPES
    assert None not in deny


def test_skill_save_keeps_nordmole_in_the_job_list(
    qapp, config_service, geo_ready, monkeypatch
):
    """Leerer Wohnort: 5 Treffer. Übernähme der Skill-Save 10115, fiele Nordmole weg."""
    _silence_dialogs(monkeypatch)
    _seed_cv_contact(
        config_service,
        street=RESOLVABLE_STREET,
        postal=RESOLVABLE_POSTAL,
        city=RESOLVABLE_CITY,
    )
    adopted = LocationConfig(
        home_address="Alexanderplatz 1, 10115 Berlin, DE",
        postal_code=RESOLVABLE_POSTAL,
        city=RESOLVABLE_CITY,
        country="DE",
    )
    assert home_location_notice(adopted).status == "resolved"

    cfg = config_service.load()
    db = Database(cfg.db_path, recover=False)
    specs = [
        ("nordmole", "Nordmole Musterlogistik", 80.0),
        ("nah-1", "Hafenkontor", 3.0),
        ("nah-2", "Speicherstadt Büro", 6.0),
        ("nah-3", "Elbpark Service", 9.0),
        ("nah-4", "Alster Dialog", 12.0),
    ]
    for job_id, company, km in specs:
        db.upsert_job(
            Job(
                id=job_id,
                source="indeed",
                title="Disponent",
                company=company,
                city="Hamburg" if job_id == "nordmole" else "Berlin",
                country_code="DE",
                remote_type=RemoteType.ONSITE.value,
                distance_km=km,
                distance_source="brouter_v1",
                match_score=90,
                status="new",
            )
        )
    visible = {"min_match": 60, "hide_applied": True, "hide_duplicates": True}
    assert len(db.list_jobs(**visible)) == 5
    assert len(db.list_jobs(max_distance=20, **visible)) == 4

    page, _host = _open_page(qapp, config_service)
    jobs = JobsPage(config_service)
    jobs.refresh()
    before = [job.company for job in jobs._jobs]
    assert len(before) == 5
    assert any("Nordmole" in name for name in before)

    page.qualifications.skills.set_items(["SAP"])
    _save_section(page, "skills")
    jobs.refresh()
    after = [job.company for job in jobs._jobs]
    assert len(after) == 5
    assert any("Nordmole" in name for name in after)
    loc = config_service.load().profile.location
    assert loc.home_address == ""
    assert loc.postal_code == ""
    assert loc.city == ""
