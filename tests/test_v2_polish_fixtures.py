"""Visual QA fixture + contextual inbox action smoke tests."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication

from desktop.dev.visual_qa_fixtures import seed_visual_qa_db
from desktop.i18n import i18n, tr
from desktop.pages.applications import ApplicationsPage
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


def test_seed_apps_many(tmp_path):
    db = seed_visual_qa_db(tmp_path / "qa.db", scenario="apps_many")
    assert len(db.list_applications(limit=50)) >= 5


def test_apps_empty_state_panel(qapp, config_service):
    i18n.set_language("de")
    page = ApplicationsPage(config_service)
    page.refresh()
    assert page.empty.isVisible() or not page.empty.isHidden()
    assert page.empty.title.text() == tr("apps.empty_title")
    assert page.review_btn.isHidden()


def test_inbox_interview_actions_contextual(qapp, config_service, tmp_path, monkeypatch):
    i18n.set_language("de")
    cfg = config_service.load()
    seed_visual_qa_db(cfg.db_path, scenario="inbox_mix")
    page = InboxPage(config_service)
    page.refresh()
    # Find interview mail
    interview = next(
        (e for e in page._emails if (e.get("category") or "") == "interview_invite"),
        None,
    )
    assert interview is not None
    page._bind_detail(interview)
    labels = [label for label, _ in page._contextual_actions(interview)]
    assert any("Interview" in t for t in labels)

    rejection = next(
        (e for e in page._emails if (e.get("category") or "") == "rejection"),
        None,
    )
    assert rejection is not None
    labels = [label for label, _ in page._contextual_actions(rejection)]
    joined = " ".join(labels)
    assert "Interview" not in joined
