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
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QMessageBox

from core.config import (
    EducationEntry,
    ExperienceEntry,
    LanguageEntry,
    QualificationsConfig,
    SourcedText,
)
from desktop.i18n import i18n, tr, tr_show_more_entries
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


def _layout_texts(layout, *, object_prefix: str) -> list[str]:
    texts: list[str] = []
    for index in range(layout.count()):
        widget = layout.itemAt(index).widget()
        if not isinstance(widget, QLabel):
            if widget is None:
                continue
            for label in widget.findChildren(QLabel):
                if label.objectName().startswith(object_prefix):
                    texts.append(label.text())
            continue
        if widget.objectName().startswith(object_prefix):
            texts.append(widget.text())
    return texts


def _three_jobs() -> list[ExperienceEntry]:
    return [
        ExperienceEntry(title="Buchhalter", company="Nordlicht GmbH"),
        ExperienceEntry(title="Teamleitung", company="Contoso Süd"),
        ExperienceEntry(title="Sachbearbeitung", company="Fabrikam"),
    ]


def _arm_deleted_more_button(page: ProfilePage) -> None:
    """Place _exp_more, queue deleteLater, then run DeferredDelete.

    The following refresh_cards() is the one that used to call setText on the
    dead button and return before education, skills and languages were rebuilt.
    """
    page.refresh_cards()
    page.refresh_cards()
    _flush_deferred_deletes()


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
    assert tr_show_more_entries(1) == "+ 1 weiteren Eintrag anzeigen"
    assert tr_show_more_entries(2) == "+ 2 weitere Einträge anzeigen"
    assert page._exp_more.text() == "+ 1 weiteren Eintrag anzeigen"
    assert _more_button_in_body(page)
    assert _experience_titles(page) == ["Buchhalter", "Teamleitung"]

    page.refresh_cards()
    _flush_deferred_deletes()
    page.refresh_cards()

    assert page._exp_more.text() == "+ 1 weiteren Eintrag anzeigen"
    assert not page._exp_more.isHidden()
    assert _more_button_in_body(page)
    assert _experience_titles(page) == ["Buchhalter", "Teamleitung"]

    cfg = config_service.load()
    cfg.profile.qualifications.work_experience.append(
        ExperienceEntry(title="Buchhaltung", company="Litware")
    )
    config_service.save(cfg)
    page.refresh_cards()
    _flush_deferred_deletes()
    page.refresh_cards()
    assert page._exp_more.text() == "+ 2 weitere Einträge anzeigen"
    i18n.set_language("en")
    page.refresh_cards()
    assert page._exp_more.text() == "+ show 2 more entries"
    assert tr_show_more_entries(1) == "+ show 1 more entry"
    i18n.set_language("de")
    page.refresh_cards()

    page._exp_more.click()
    assert page._exp_limit == 50
    assert _experience_titles(page) == [
        "Buchhalter",
        "Teamleitung",
        "Sachbearbeitung",
        "Buchhaltung",
    ]
    assert not _more_button_in_body(page)
    assert page._exp_more.isHidden()


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


def test_more_button_not_visible_when_experience_cleared(qapp, config_service):
    """An empty work_experience list (profile reset) must hide the more-button.

    Same orphan as the two-position case: takeAt() without hide() leaves the
    button visible on the shown card. Unpatched main fails isVisible().
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
    qapp.processEvents()
    _flush_deferred_deletes()
    assert page._exp_more.isVisible()
    assert _more_button_in_body(page)

    cfg = config_service.load()
    cfg.profile.qualifications.work_experience = []
    config_service.save(cfg)
    page.refresh_cards()

    assert _experience_titles(page) == []
    assert not _more_button_in_body(page)
    assert not page._exp_more.isVisible()
    assert page._exp_more.isHidden()


def test_second_refresh_rebuilds_education_skills_and_languages(qapp, config_service):
    """Data saved between two refresh_cards() calls must show up on the second.

    load_from_config() puts the more-button in the layout. The first
    refresh_cards() queues deleteLater. DeferredDelete runs before the second
    refresh_cards(), which on main dies in setText after clearing experience
    and before education, skills and languages are rebuilt.
    """
    i18n.set_language("de")
    cfg = config_service.load()
    quals = cfg.profile.qualifications
    quals.work_experience = _three_jobs()
    quals.education = [EducationEntry(qualification="Alte Ausbildung", institution="Alte Schule")]
    quals.skills = [SourcedText(value="Excel", source="manual")]
    quals.languages = [LanguageEntry(language="Deutsch", level="C2")]
    config_service.save(cfg)

    page = ProfilePage(config_service)
    page.load_from_config()
    assert _layout_texts(page._edu_body, object_prefix="NextActionTitle") == ["Alte Ausbildung"]
    assert "Excel" in _layout_texts(page._skills_row, object_prefix="Badge")
    assert "Deutsch (C2)" in _layout_texts(page._lang_body, object_prefix="Badge")

    # Button is already in the layout. This refresh queues deleteLater on it.
    page.refresh_cards()
    cfg = config_service.load()
    quals = cfg.profile.qualifications
    quals.education = [EducationEntry(qualification="Neue Ausbildung", institution="Neue Hochschule")]
    quals.skills = [SourcedText(value="DATEV", source="cv")]
    quals.languages = [LanguageEntry(language="Englisch", level="B2")]
    config_service.save(cfg)
    _flush_deferred_deletes()
    page.refresh_cards()

    education = _layout_texts(page._edu_body, object_prefix="NextActionTitle")
    skills = _layout_texts(page._skills_row, object_prefix="Badge")
    languages = _layout_texts(page._lang_body, object_prefix="Badge")
    assert education == ["Neue Ausbildung"]
    assert "Alte Ausbildung" not in education
    assert "DATEV" in skills
    assert "Excel" not in skills
    assert "Englisch (B2)" in languages
    assert "Deutsch (C2)" not in languages


def test_import_from_cv_shows_updated_message_after_reload(qapp, config_service, tmp_path, monkeypatch):
    """Übernehmen must reach the success dialog after load_from_config().

    The dialog is replaced so the test does not parse a CV. The saved profile
    already has 3 positions, so the reload hits the deleted more-button on
    unpatched main and never calls QMessageBox.information.
    """
    i18n.set_language("de")
    cv_file = tmp_path / "lebenslauf.pdf"
    cv_file.write_bytes(b"%PDF-1.4\n")
    cfg = config_service.load()
    cfg.application.cv_path = str(cv_file)
    quals = cfg.profile.qualifications
    quals.work_experience = _three_jobs()
    quals.education = [EducationEntry(qualification="Alte Ausbildung", institution="Alte Schule")]
    quals.skills = [SourcedText(value="Excel", source="manual")]
    quals.languages = [LanguageEntry(language="Deutsch", level="C2")]
    config_service.save(cfg)

    imported = QualificationsConfig(
        work_experience=_three_jobs(),
        education=[EducationEntry(qualification="Importierte Ausbildung", institution="IHK")],
        skills=[SourcedText(value="SAP", source="cv")],
        languages=[LanguageEntry(language="Französisch", level="A2")],
    )

    class _AcceptedImport:
        DialogCode = QDialog.DialogCode

        def __init__(self, *_args, **_kwargs) -> None:
            self.result_quals = imported
            self.result_application = None

        def exec(self) -> QDialog.DialogCode:
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr("desktop.pages.profile.CvImportDialog", _AcceptedImport)
    shown: list[tuple[str, str]] = []

    def _information(_parent, title, text, *_args, **_kwargs):
        shown.append((str(title), str(text)))
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(QMessageBox, "information", _information)

    page = ProfilePage(config_service)
    page.load_from_config()
    _arm_deleted_more_button(page)
    page.import_from_cv()

    assert shown == [(tr("profile.cv"), tr("profile.cv_updated"))]
    assert tr("profile.cv_updated") == "Profil aktualisiert."
    education = _layout_texts(page._edu_body, object_prefix="NextActionTitle")
    skills = _layout_texts(page._skills_row, object_prefix="Badge")
    languages = _layout_texts(page._lang_body, object_prefix="Badge")
    assert education == ["Importierte Ausbildung"]
    assert "SAP" in skills
    assert "Excel" not in skills
    assert "Französisch (A2)" in languages
    assert "Deutsch (C2)" not in languages
