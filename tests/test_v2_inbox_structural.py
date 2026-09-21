"""Postfach structural rebuild tests."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication

from core.database import Database
from desktop.i18n import i18n, tr
from desktop.pages.inbox import InboxPage
from desktop.services import ConfigService


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


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
        for p in dirs.values():
            p.mkdir(parents=True, exist_ok=True)
        return dirs

    monkeypatch.setattr(paths_mod, "ensure_app_dirs", fake_dirs)
    monkeypatch.setattr("desktop.services.ensure_app_dirs", fake_dirs)
    return ConfigService()


def test_inbox_has_refresh_icon_and_split(qapp, config_service):
    i18n.set_language("de")
    page = InboxPage(config_service)
    assert page.refresh_btn.toolTip() == tr("inbox.refresh_tooltip")
    assert page.refresh_btn.accessibleName() == tr("inbox.refresh_tooltip")
    assert page.list is not None
    assert page.primary_action is not None
    assert page.more_btn.menu() is not None
    # Lifecycle chrome hidden; capabilities retained via methods
    assert page.lifecycle.isHidden()
    assert hasattr(page.lifecycle, "prepare_followup_draft")


def test_inbox_lists_emails_and_refresh_guard(qapp, config_service):
    cfg = config_service.load()
    db = Database(cfg.db_path)
    db.save_email_message(
        {
            "id": "e1",
            "gmail_id": "g1",
            "subject": "Einladung",
            "sender": "hr@example.com",
            "body_text": "Hallo",
            "association_status": "ambiguous",
            "received_at": "2026-09-20T10:00:00",
        }
    )
    page = InboxPage(config_service)
    page.refresh()
    assert page.list.count() >= 1
    page._refreshing = True
    page._on_refresh()  # should no-op while refreshing
    assert page._refreshing is True
