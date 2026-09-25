"""refresh_cards must survive DeferredDelete of widgets it rebuilds.

The experience "Weitere anzeigen" button is created once and reinserted on
every refresh. Clearing the card with deleteLater destroys that C++ object
on the next event-loop pass; the following refresh then calls setText on it.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication, QLabel

from core.config import ExperienceEntry
from desktop.i18n import i18n, tr
from desktop.pages.profile import ProfilePage
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
        for path in dirs.values():
            path.mkdir(parents=True, exist_ok=True)
        return dirs

    monkeypatch.setattr(paths_mod, "ensure_app_dirs", fake_dirs)
    monkeypatch.setattr("desktop.services.ensure_app_dirs", fake_dirs)
    return ConfigService()


def _flush_deferred_deletes() -> None:
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def _experience_titles(page: ProfilePage) -> list[str]:
    titles: list[str] = []
    body = page._exp_body
    for index in range(body.count()):
        widget = body.itemAt(index).widget()
        if widget is None or widget is page._exp_more:
            continue
        for label in widget.findChildren(QLabel):
            if label.objectName() == "NextActionTitle":
                titles.append(label.text())
    return titles


def _more_button_in_body(page: ProfilePage) -> bool:
    body = page._exp_body
    return any(
        body.itemAt(index).widget() is page._exp_more for index in range(body.count())
    )


def test_refresh_cards_keeps_experience_more_button_after_deferred_delete(
    qapp, config_service
):
    """Two refreshes with DeferredDelete processed in between must not crash.

    load_from_config() already places _exp_more in the layout when more than
    two jobs exist. The next refresh_cards() used to deleteLater() that
    button; after the deferred delete, another refresh_cards() called setText
    on the dead QPushButton.
    """
    i18n.set_language("de")
    cfg = config_service.load()
    cfg.profile.qualifications.work_experience = [
        ExperienceEntry(title="Buchhalter", company="Nordlicht GmbH"),
        ExperienceEntry(title="Teamleitung", company="Contoso Süd"),
        ExperienceEntry(title="Sachbearbeitung", company="Fabrikam"),
    ]
    config_service.save(cfg)

    page = ProfilePage(config_service)
    page.load_from_config()
    hidden = len(cfg.profile.qualifications.work_experience) - page._exp_limit
    expected = tr("profile.show_more_entries", n=hidden)
    assert expected == "+ 1 weitere Einträge anzeigen"
    assert page._exp_more.text() == expected
    assert _more_button_in_body(page)
    assert _experience_titles(page) == ["Buchhalter", "Teamleitung"]

    page.refresh_cards()
    _flush_deferred_deletes()
    page.refresh_cards()

    assert page._exp_more.text() == expected
    assert not page._exp_more.isHidden()
    assert _more_button_in_body(page)
    assert _experience_titles(page) == ["Buchhalter", "Teamleitung"]

    page._exp_more.click()
    assert page._exp_limit == 50
    assert _experience_titles(page) == ["Buchhalter", "Teamleitung", "Sachbearbeitung"]
    assert not _more_button_in_body(page)
    assert page._exp_more.isHidden()

    _flush_deferred_deletes()
    page.refresh_cards()
    assert _experience_titles(page) == ["Buchhalter", "Teamleitung", "Sachbearbeitung"]
    assert not _more_button_in_body(page)

    page._exp_limit = 2
    page.refresh_cards()
    _flush_deferred_deletes()
    page.refresh_cards()
    assert page._exp_more.text() == expected
    assert not page._exp_more.isHidden()
    assert _more_button_in_body(page)
    assert _experience_titles(page) == ["Buchhalter", "Teamleitung"]


def test_more_button_not_visible_when_positions_drop_to_two(qapp, config_service):
    """Dropping to two jobs must hide the more-button, not leave it on the card.

    The page is shown so a button removed with takeAt() but not hide() stays
    visible (top-left leftover). Unpatched main fails that visibility check.
    """
    i18n.set_language("de")
    cfg = config_service.load()
    cfg.profile.qualifications.work_experience = [
        ExperienceEntry(title="Buchhalter", company="Nordlicht GmbH"),
        ExperienceEntry(title="Teamleitung", company="Contoso Süd"),
        ExperienceEntry(title="Sachbearbeitung", company="Fabrikam"),
    ]
    config_service.save(cfg)

    page = ProfilePage(config_service)
    page.show()
    page.refresh_cards()
    # Realize the shown card. The first refresh does not deleteLater the button.
    qapp.processEvents()
    _flush_deferred_deletes()
    assert page._exp_more.isVisible()
    assert _more_button_in_body(page)

    cfg = config_service.load()
    cfg.profile.qualifications.work_experience = cfg.profile.qualifications.work_experience[:2]
    config_service.save(cfg)
    page.refresh_cards()

    assert _experience_titles(page) == ["Buchhalter", "Teamleitung"]
    assert not _more_button_in_body(page)
    assert not page._exp_more.isVisible()
    assert page._exp_more.isHidden()
