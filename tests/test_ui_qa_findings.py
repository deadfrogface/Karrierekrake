"""Regressions from manual UI QA (dark theme, labeled confirms, copy, status, counters)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QPalette  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialogButtonBox, QMessageBox  # noqa: E402

from desktop.branding import COLOR_DARK_BG  # noqa: E402
from desktop.i18n import TRANSLATIONS, i18n, tr, tr_n  # noqa: E402
from desktop.theme import apply_theme  # noqa: E402

_DESKTOP = Path(__file__).resolve().parent.parent / "desktop"


@pytest.fixture
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app
    apply_theme(app, "light")
    i18n.set_language("de")


@pytest.fixture
def config_service(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    from desktop import paths as paths_mod

    def fake_dirs():
        root = tmp_path / "Karrierekrake"
        dirs = {
            name: root / name
            for name in ("config", "data", "logs", "browser_profile", "browsers", "cvs", "cache", "cover_letters")
        }
        dirs["root"] = root
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


# --- Confirm dialogs: text labels, never bare icons / Qt-translated Yes/No ---


@pytest.mark.parametrize(
    ("lang", "confirm", "cancel"),
    [("de", "Exportieren", "Abbrechen"), ("en", "Export", "Cancel")],
)
def test_confirm_box_buttons_carry_i18n_labels(qapp, lang, confirm, cancel):
    from desktop.widgets.confirm_dialog import build_confirm_box

    i18n.set_language(lang)
    box, confirm_btn, cancel_btn = build_confirm_box(
        None,
        tr("privacy.tab"),
        tr("privacy.export_confirm"),
        confirm_text=tr("privacy.export_confirm_btn"),
    )
    assert confirm_btn.text() == confirm
    assert cancel_btn.text() == cancel
    assert box.standardButtons() == QMessageBox.StandardButton.NoButton
    assert box.defaultButton() is confirm_btn
    box.deleteLater()


def test_destructive_confirm_defaults_to_cancel(qapp):
    from desktop.widgets.confirm_dialog import build_confirm_box

    i18n.set_language("de")
    box, confirm_btn, cancel_btn = build_confirm_box(
        None, "t", "Wirklich löschen?", confirm_text="Löschen", destructive=True
    )
    assert box.defaultButton() is cancel_btn
    assert box.escapeButton() is cancel_btn
    assert confirm_btn.text() == "Löschen"
    box.deleteLater()


def test_label_button_box_localizes_standard_buttons(qapp):
    from desktop.widgets.confirm_dialog import label_button_box

    i18n.set_language("de")
    buttons = label_button_box(
        QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    )
    assert buttons.button(QDialogButtonBox.StandardButton.Cancel).text() == "Abbrechen"
    assert buttons.button(QDialogButtonBox.StandardButton.Ok).text() == "OK"


def test_no_unlabeled_question_boxes_in_desktop_sources():
    offenders = [
        str(p.relative_to(_DESKTOP))
        for p in _DESKTOP.rglob("*.py")
        if "QMessageBox.question(" in p.read_text(encoding="utf-8")
        or "addButton(QMessageBox.StandardButton" in p.read_text(encoding="utf-8")
    ]
    assert offenders == []


def test_privacy_export_confirm_uses_labeled_dialog(qapp, config_service, monkeypatch):
    from desktop.pages import settings as settings_mod

    seen: dict = {}

    def fake_confirm(parent, title, text, **kwargs):
        seen.update(kwargs, text=text)
        return False

    monkeypatch.setattr(settings_mod, "confirm_action", fake_confirm)
    i18n.set_language("de")
    page = settings_mod.SettingsPage(config_service)
    page._privacy_export()
    assert seen["text"] == tr("privacy.export_confirm")
    assert seen["confirm_text"] == "Exportieren"


# --- Dark theme ---


def test_apply_theme_dark_sets_matching_palette(qapp):
    apply_theme(qapp, "dark")
    pal = qapp.palette()
    assert pal.color(QPalette.ColorRole.Window).name().lower() == COLOR_DARK_BG.lower()
    assert pal.color(QPalette.ColorRole.ButtonText).lightness() > 180
    css = qapp.styleSheet()
    assert "QToolButton#SecondaryButton" in css
    assert "QScrollArea > QWidget > QWidget" in css
    apply_theme(qapp, "light")
    assert qapp.palette().color(QPalette.ColorRole.Window).name().lower() != COLOR_DARK_BG.lower()


def test_dark_settings_body_is_not_light(qapp, config_service):
    from desktop.pages.settings import SettingsPage

    i18n.set_language("de")
    apply_theme(qapp, "dark")
    page = SettingsPage(config_service)
    page.resize(1000, 700)
    page.show()
    page.nav.setCurrentRow(0)
    QTest.qWait(20)
    img = page.stack.grab().toImage()
    # Empty area below the "Allgemein" group box.
    sample = img.pixelColor(img.width() // 2, img.height() - 20)
    page.close()
    assert sample.lightness() < 80, sample.name()


# --- Copy: plural, privacy, about path, location ---


def test_inbox_title_plural_de_en():
    i18n.set_language("de")
    assert tr_n("dash.next_inbox_title", 1) == "1 Nachricht muss zugeordnet werden"
    assert tr_n("dash.next_inbox_title", 3) == "3 Nachrichten müssen zugeordnet werden"
    i18n.set_language("en")
    assert tr_n("dash.next_inbox_title", 1) == "1 message needs association"
    assert tr_n("dash.next_inbox_title", 2) == "2 messages need association"
    i18n.set_language("de")


def test_dashboard_uses_singular_for_one_ambiguous_reply(qapp, config_service):
    from core.database import Database
    from desktop.pages.dashboard import DashboardPage

    cfg = config_service.load()
    cfg.profile.jobs.desired_titles = ["Office Manager"]
    config_service.save(cfg)
    Database(cfg.db_path).save_email_message(
        {
            "id": "m1",
            "gmail_id": "m1",
            "sender": "HR <hr@acme.example>",
            "subject": "Ihre Bewerbung",
            "body_text": "Hallo",
            "category": "generic",
            "association_status": "ambiguous",
            "case_id": "",
            "received_at": "2026-09-24T08:00:00+00:00",
        }
    )
    i18n.set_language("de")
    page = DashboardPage(config_service)
    page.refresh()
    assert page.next_title.text() == "1 Nachricht muss zugeordnet werden"


def test_no_legal_placeholder_in_user_facing_copy():
    for lang, table in TRANSLATIONS.items():
        for key, value in table.items():
            assert "UNSPECIFIED" not in value, (lang, key)
            assert "LEGAL REVIEW" not in value, (lang, key)


def test_about_dialog_shows_resolved_data_dir(qapp, tmp_path):
    from PySide6.QtWidgets import QLabel

    from desktop.widgets.about_dialog import AboutDialog

    i18n.set_language("de")
    dlg = AboutDialog(None, data_dir=tmp_path / "Karrierekrake")
    texts = [lbl.text() for lbl in dlg.findChildren(QLabel)]
    dlg.deleteLater()
    assert any(str(tmp_path / "Karrierekrake") in t for t in texts)
    assert not any("%LOCALAPPDATA%" in t for t in texts)


def test_dashboard_home_notice_follows_live_resolver(qapp, config_service):
    """Stale run text must not override the live home resolver.

    Frankfurt without a postal code stays on the PLZ hint (no centroid).
    Coordinates stored for that same address show the resolved OK line.
    """
    from core.database import Database
    from desktop.pages.dashboard import DashboardPage

    cfg = config_service.load()
    cfg.profile.location.home_address = "Frankfurt, Deutschland"
    config_service.save(cfg)
    db = Database(cfg.db_path)
    rid = db.start_search_run()
    db.finish_search_run(rid, "ok", {"home_warning": "technical text"})
    i18n.set_language("de")
    page = DashboardPage(config_service)
    page.refresh()
    text = page.home_warning_label.text()
    assert text == tr("dash.home_plz_hint")
    assert "technical text" not in text
    assert "Postleitzahl" in text
    assert "geschätzt" in text
    assert "10115" not in text
    assert "Distanzfilter übersprungen" not in text
    assert page.home_warning_label.objectName() == "WarningLabel"
    assert not page.home_warning_label.isHidden()

    cfg = config_service.load()
    cfg.profile.location.home_latitude = 50.11
    cfg.profile.location.home_longitude = 8.68
    config_service.save(cfg)
    page.refresh()
    resolved = page.home_warning_label.text()
    assert resolved == tr("dash.home_resolved", place="Frankfurt")
    assert "technical text" not in resolved
    assert page.home_warning_label.objectName() == "HomeStatusOk"
    assert not page.home_warning_label.isHidden()


# --- Status after cancel ---


def test_cancelled_status_does_not_lock_idle_search_cta(qapp, config_service):
    from desktop.pages.dashboard import DashboardPage

    i18n.set_language("en")
    page = DashboardPage(config_service)
    page.set_pipeline_running(True)
    page.set_pipeline_running(False)
    page.set_status(tr("status.cancelled"))
    assert page.btn_search.isEnabled()
    assert page.btn_search.text() == tr("btn.search_again")
    i18n.set_language("de")
    page.set_status(tr("btn.cancel_search") + "…")
    assert page.btn_search.isEnabled()


def test_main_window_resets_cancelled_status(qapp, config_service, monkeypatch):
    monkeypatch.setattr("desktop.tray.AppTray.show", lambda self: None)
    from desktop.main_window import MainWindow

    i18n.set_language("de")
    win = MainWindow(config_service)
    try:
        win.progress_label.setText(tr("status.cancelled"))
        win._schedule_status_reset(tr("status.cancelled"), delay_ms=0)
        QTest.qWait(30)
        assert win.progress_label.text() == tr("status.ready")
    finally:
        win._shutting_down = True
        win.close()


# --- KPI cards ---


def test_kpi_cards_are_clickable_and_navigate(qapp, config_service):
    from desktop.pages.dashboard import DashboardPage

    i18n.set_language("de")
    page = DashboardPage(config_service)
    page.resize(1000, 700)
    page.show()
    reviews: list[bool] = []
    page.review_requested.connect(lambda: reviews.append(True))
    card = page.kpi_cards["needs_review"]
    assert card.is_clickable()
    assert card.cursor().shape() == Qt.CursorShape.PointingHandCursor
    QTest.mouseClick(card, Qt.MouseButton.LeftButton)
    assert reviews == [True]
    page.close()


# --- Review counter must not move because a GUI search started / was cancelled ---


def test_pipeline_worker_skips_crash_recovery(monkeypatch, tmp_path):
    from core.config import empty_app_config
    from desktop.workers import PipelineWorker

    seen: dict = {}

    def fake_run(config, mode=None, **kwargs):
        seen.update(kwargs)
        return {"cancelled": True}

    monkeypatch.setattr("app.main.run_pipeline", fake_run)
    worker = PipelineWorker(empty_app_config(root=tmp_path), mode="search_only")
    worker.run()
    assert seen.get("recover_interrupted") is False


def test_cancelled_gui_search_keeps_review_counter(tmp_path):
    from app.main import run_pipeline
    from core.config import empty_app_config
    from core.database import Database
    from core.models import Job, JobStatus

    cfg = empty_app_config(root=tmp_path)
    cfg.settings.database_path = "data/jobs.db"
    cfg.settings.logs_dir = "logs"
    (tmp_path / "data").mkdir()
    (tmp_path / "logs").mkdir()
    cfg.profile.jobs.desired_titles = ["Tester"]
    cfg.profile.location.home_address = "Berlin"
    cfg.settings.enabled_sources = ["company_sites"]
    db = Database(cfg.db_path)
    db.upsert_job(
        Job(id="j1", source="t", title="T", company="C", url="https://x/1", status=JobStatus.NEEDS_REVIEW.value)
    )
    db.upsert_job(
        Job(id="j2", source="t", title="T2", company="C2", url="https://x/2", status=JobStatus.APPLYING.value)
    )
    before = db.dashboard_stats()["needs_review"]
    stats = run_pipeline(
        cfg, mode="search_only", should_stop=lambda: True, recover_interrupted=False
    )
    assert stats.get("cancelled") is True
    assert Database(cfg.db_path).dashboard_stats()["needs_review"] == before
