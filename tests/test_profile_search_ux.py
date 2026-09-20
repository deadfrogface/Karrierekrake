"""pytest-qt flows for Profile / SearchIntent UX separation (PR35)."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication, QMessageBox


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def config_service(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.delenv("KARRIEREKRAKE_LEGACY_PROFILE_SEARCH", raising=False)
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
    monkeypatch.setattr(
        "desktop.services.schedule_service.ScheduleService.sync_from_config",
        lambda self: (True, "ok"),
    )
    from desktop.services import ConfigService

    return ConfigService()


def _accept_messageboxes(monkeypatch):
    monkeypatch.setattr(
        QMessageBox,
        "information",
        classmethod(lambda *a, **k: QMessageBox.StandardButton.Ok),
    )
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        classmethod(lambda *a, **k: QMessageBox.StandardButton.Ok),
    )


def _wheel_at(widget, delta: int = -120) -> QWheelEvent:
    center = widget.rect().center()
    global_pos = widget.mapToGlobal(center)
    return QWheelEvent(
        QPointF(center),
        QPointF(global_pos),
        QPoint(0, 0),
        QPoint(0, delta),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.ScrollUpdate,
        False,
    )


# ---------------------------------------------------------------------------
# Profile edit / clear
# ---------------------------------------------------------------------------


def test_profile_edit_and_clear_without_touching_search_intent(qapp, config_service, monkeypatch):
    from core.search_intent import SearchIntent, Strictness
    from desktop.pages.profile import ProfilePage

    _accept_messageboxes(monkeypatch)
    cfg = config_service.load()
    cfg.profile.search_intent = SearchIntent(
        target_roles=["Lohnbuchhalter"],
        mandatory_skills=["SAP"],
        strictness=Strictness.STRICT,
    )
    config_service.save(cfg)

    page = ProfilePage(config_service)
    page.load_from_config()
    assert page.career.isHidden() is True
    assert page.location_work.max_distance.isHidden() is True

    page.applicant.first_name.setText("Julia")
    page.applicant.last_name.setText("Muster")
    page.applicant.city.setText("München")
    page.qualifications.skills.set_items(["Excel", "DATEV"])
    page.save()

    loaded = config_service.load()
    assert loaded.application.first_name == "Julia"
    assert loaded.application.city == "München"
    intent = loaded.profile.search_intent
    assert list(intent.target_roles) == ["Lohnbuchhalter"]
    assert list(intent.mandatory_skills) == ["SAP"]
    assert intent.strictness == Strictness.STRICT

    # Clear applicant city — must stick; intent unchanged.
    page.load_from_config()
    page.applicant.city.setText("")
    page.save()
    loaded = config_service.load()
    assert loaded.application.city == ""
    assert list(loaded.profile.search_intent.target_roles) == ["Lohnbuchhalter"]


def test_legacy_profile_search_flag_restores_career_ui(qapp, config_service, monkeypatch):
    monkeypatch.setenv("KARRIEREKRAKE_LEGACY_PROFILE_SEARCH", "1")
    from desktop.pages.profile import ProfilePage

    page = ProfilePage(config_service)
    page.load_from_config()
    # Parent not shown → isVisible() is False; use isHidden() for flag effect.
    assert page.career.isHidden() is False
    assert page.location_work.max_distance.isHidden() is False


def test_profile_hides_career_by_default(qapp, config_service):
    from desktop.pages.profile import ProfilePage

    page = ProfilePage(config_service)
    page.load_from_config()
    assert page.career.isHidden() is True
    assert page.location_work.max_distance.isHidden() is True


# ---------------------------------------------------------------------------
# SearchIntent save + real cases
# ---------------------------------------------------------------------------


def test_search_intent_payroll_only_save_restart(qapp, config_service, monkeypatch):
    from core.search_intent import Strictness
    from desktop.pages.search import SearchPage

    _accept_messageboxes(monkeypatch)
    page = SearchPage(config_service)
    page.load_from_config()
    page.target_roles.set_items(
        [
            "Lohn- und Gehaltsbuchhaltung",
            "Lohnbuchhalter",
            "Gehaltsbuchhalter",
        ]
    )
    page.mandatory_skills.set_items([])
    page.strictness.setCurrentIndex(page.strictness.findData(Strictness.STRICT.value))
    page.save()

    # Simulate restart: new page + reload from disk.
    page2 = SearchPage(config_service)
    page2.load_from_config()
    roles = page2.target_roles.get_items()
    assert "Lohn- und Gehaltsbuchhaltung" in roles
    assert page2.mandatory_skills.get_items() == []
    loaded = config_service.load()
    assert loaded.profile.search_intent.strictness == Strictness.STRICT
    assert "Lohnbuchhalter" in loaded.profile.jobs.desired_titles  # dual-write


def test_search_intent_sap_only(qapp, config_service, monkeypatch):
    from core.search_intent import Strictness
    from desktop.pages.search import SearchPage

    _accept_messageboxes(monkeypatch)
    page = SearchPage(config_service)
    page.load_from_config()
    page.target_roles.set_items([])
    page.mandatory_skills.set_items(["SAP"])
    page.strictness.setCurrentIndex(page.strictness.findData(Strictness.STRICT.value))
    page.remote_remote.setChecked(True)
    page.country_de.setChecked(True)
    page.country_at.setChecked(False)
    page.country_ch.setChecked(False)
    page.save()

    intent = config_service.load().profile.search_intent
    assert intent.mandatory_skills == ["SAP"]
    assert intent.target_roles == []
    assert intent.strictness == Strictness.STRICT
    assert intent.remote_mode == "remote"
    assert intent.countries == ["DE"]


def test_search_intent_does_not_invent_strictness(qapp, config_service, monkeypatch):
    from desktop.pages.search import SearchPage

    _accept_messageboxes(monkeypatch)
    page = SearchPage(config_service)
    page.load_from_config()
    page.target_roles.set_items(["Controller"])
    # Leave strictness on "unset" (index 0)
    page.strictness.setCurrentIndex(0)
    page.save()
    intent = config_service.load().profile.search_intent
    assert intent.strictness is None
    assert intent.target_roles == ["Controller"]


# ---------------------------------------------------------------------------
# Wheel scroll regression
# ---------------------------------------------------------------------------


def test_radius_wheel_ignored_without_focus(qapp, config_service):
    from desktop.pages.search import SearchPage

    page = SearchPage(config_service)
    page.load_from_config()
    page.radius_km.setValue(25)
    page.radius_km.clearFocus()
    qapp.processEvents()
    assert page.radius_km.hasFocus() is False
    before = page.radius_km.value()
    event = _wheel_at(page.radius_km, delta=-240)
    # Deliver via event filter / widget
    QApplication.sendEvent(page.radius_km, event)
    qapp.processEvents()
    assert page.radius_km.value() == before


def test_radius_wheel_changes_when_focused(qapp, config_service):
    from desktop.pages.search import SearchPage

    page = SearchPage(config_service)
    page.show()
    page.load_from_config()
    page.radius_km.setValue(25)
    page.radius_km.setFocus(Qt.FocusReason.MouseFocusReason)
    qapp.processEvents()
    assert page.radius_km.hasFocus()
    before = page.radius_km.value()
    event = _wheel_at(page.radius_km, delta=-120)
    QApplication.sendEvent(page.radius_km, event)
    qapp.processEvents()
    assert page.radius_km.value() != before


def test_profile_commute_spin_has_wheel_guard(qapp, config_service, monkeypatch):
    monkeypatch.setenv("KARRIEREKRAKE_LEGACY_PROFILE_SEARCH", "1")
    from desktop.pages.profile import ProfilePage

    page = ProfilePage(config_service)
    page.load_from_config()
    spin = page.location_work.max_distance
    assert spin.property("kkWheelGuard") is True
    assert spin.focusPolicy() == Qt.FocusPolicy.StrongFocus
    spin.setValue(40)
    spin.clearFocus()
    before = spin.value()
    QApplication.sendEvent(spin, _wheel_at(spin, delta=-120))
    assert spin.value() == before


# ---------------------------------------------------------------------------
# Tab order / long German / DPI / nav bindings
# ---------------------------------------------------------------------------


def test_search_page_tab_order_and_long_german_labels(qapp, config_service):
    from desktop.i18n import i18n, tr
    from desktop.pages.search import SearchPage

    i18n.set_language("de")
    page = SearchPage(config_service)
    page.retranslate_ui()
    assert "jetzt" in page.page_subtitle.text().lower()
    assert len(tr("search.strictness_strict")) > 20
    assert len(tr("search.strictness_explore")) > 20
    # Tab focus chain starts at list editors / radios — widgets accept focus.
    assert page.target_roles.input.focusPolicy() != Qt.FocusPolicy.NoFocus
    assert page.radius_km.focusPolicy() == Qt.FocusPolicy.StrongFocus
    assert page.salary_min.focusPolicy() == Qt.FocusPolicy.StrongFocus


def test_main_window_nav_order_profile_then_search(qapp, config_service, monkeypatch, tmp_path):
    monkeypatch.setattr("desktop.tray.AppTray.show", lambda self: None)
    monkeypatch.setattr("desktop.tray.AppTray.showMessage", lambda *a, **k: None)
    from desktop.main_window import MainWindow

    win = MainWindow(config_service)
    keys = [k for k, _ in win._nav_defs]
    assert keys[0] == "nav.profile"
    assert keys[1] == "nav.search"
    assert keys[2] == "nav.jobs"
    assert keys[3] == "nav.applications"
    assert keys[4] == "nav.guenther"
    assert keys[5] == "nav.settings"
    assert "nav.search" in win._page_index
    win.navigate_to("nav.search")
    assert win.stack.currentWidget() is win.search
    win.navigate_to("nav.profile")
    assert win.stack.currentWidget() is win.profile
    # DPI: page still lays out without crash at large min size
    win.resize(1400, 900)
    win.search.load_from_config()
    win.close()


def test_i18n_keys_parity_for_search(qapp):
    from desktop.i18n import TRANSLATIONS

    assert set(TRANSLATIONS["de"]) == set(TRANSLATIONS["en"])
    for key in (
        "nav.search",
        "nav.guenther",
        "search.target_roles",
        "search.mandatory_skills",
        "search.radius",
        "btn.save_search",
        "profile.subtitle",
    ):
        assert key in TRANSLATIONS["de"]
        assert key in TRANSLATIONS["en"]
