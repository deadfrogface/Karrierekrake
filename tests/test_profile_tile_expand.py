"""Profile section cards: expand/collapse, pill wrap, action isolation."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel

from core.config import CertificateEntry, ExperienceEntry, SourcedText
from desktop.design_system.flow_layout import FlowLayout
from desktop.design_system.v2_chrome import ProfileSectionCard, TagChip
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


def _chip_texts(layout) -> list[str]:
    texts: list[str] = []
    for index in range(layout.count()):
        widget = layout.itemAt(index).widget()
        if isinstance(widget, QLabel):
            texts.append(widget.text())
    return texts


def test_profile_section_card_toggles_on_keyboard(qapp):
    i18n.set_language("de")
    card = ProfileSectionCard("Berufsziel", action_text="Bearbeiten")
    assert card.is_expanded() is False
    assert card.focusPolicy() == Qt.FocusPolicy.StrongFocus
    card.setFocus()
    QTest.keyClick(card, Qt.Key.Key_Space)
    assert card.is_expanded() is True
    QTest.keyClick(card, Qt.Key.Key_Return)
    assert card.is_expanded() is False
    assert tr("profile.expand") in (card.expand_indicator.toolTip() or "")


def test_profile_section_card_action_does_not_toggle(qapp):
    card = ProfileSectionCard("Skills", action_text="Bearbeiten")
    toggles: list[bool] = []
    card.expandedChanged.connect(lambda v: toggles.append(v))
    # Clicking the action button must open edit, not expand.
    QTest.mouseClick(card.action_btn, Qt.MouseButton.LeftButton)
    assert toggles == []
    assert card.is_expanded() is False


def test_profile_section_card_indicator_toggles(qapp):
    card = ProfileSectionCard("Skills", action_text="Bearbeiten")
    QTest.mouseClick(card.expand_indicator, Qt.MouseButton.LeftButton)
    assert card.is_expanded() is True
    QTest.mouseClick(card.expand_indicator, Qt.MouseButton.LeftButton)
    assert card.is_expanded() is False


def test_flow_layout_wraps_long_pills(qapp):
    from desktop.design_system.flow_layout import FlowHost

    host_card = ProfileSectionCard("Berufsziel")
    flow_host = FlowHost(h_spacing=8, v_spacing=8)
    flow = flow_host.flow()
    host_card.body().addWidget(flow_host)
    long = "Fachkraft für Lagerlogistik und Intralogistiksysteme"
    for text in (long, "Python", "Buchhaltung", "Steuerfachangestellte/r", long):
        flow.addWidget(TagChip(text, kind="wanted"))
    host_card.resize(320, 600)
    host_card.show()
    qapp.processEvents()
    # Height for narrow width must exceed a single line of chips.
    h = flow_host.heightForWidth(280)
    assert h > 40
    for index in range(flow.count()):
        chip = flow.itemAt(index).widget()
        assert isinstance(chip, TagChip)
        assert "…" not in chip.text()
        assert chip.wordWrap() is True


def test_profile_expand_shows_all_skill_pills(qapp, config_service):
    i18n.set_language("de")
    cfg = config_service.load()
    skills = [
        "Buchhaltung",
        "Jahresabschluss",
        "DATEV",
        "Lexware",
        "Excel Power Query",
        "Kostenrechnung",
        "Debitorenbuchhaltung",
        "Kreditorenbuchhaltung",
        "Umsatzsteuer-Voranmeldung",
        "Finanzbuchhaltung",
        "Controlling-Reporting",
    ]
    cfg.profile.qualifications.skills = [SourcedText(value=s) for s in skills]
    cfg.profile.jobs.desired_titles = [
        "Buchhalter/in",
        "Finanzbuchhalter/in",
        "Accountant",
        "Steuerfachangestellte/r",
        "Bilanzbuchhalter/in",
        "Sachbearbeiter Finanzen",
        "Teamleitung Buchhaltung",
    ]
    config_service.save(cfg)

    page = ProfilePage(config_service)
    page.load_from_config()
    collapsed = _chip_texts(page._skills_row)
    assert any("+ " in t or "weitere" in t for t in collapsed)
    assert "Controlling-Reporting" not in collapsed

    page.card_skills.set_expanded(True)
    qapp.processEvents()
    expanded = _chip_texts(page._skills_row)
    assert "Controlling-Reporting" in expanded
    assert not any(t.startswith("+ ") for t in expanded)

    page.card_career.set_expanded(True)
    qapp.processEvents()
    career = _chip_texts(page._wanted_row)
    assert "Teamleitung Buchhaltung" in career


def test_profile_experience_expand_shows_all(qapp, config_service):
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
    assert page._exp_more.isVisibleTo(page) or not page._exp_more.isHidden()
    page.card_experience.set_expanded(True)
    qapp.processEvents()
    titles: list[str] = []
    for index in range(page._exp_body.count()):
        widget = page._exp_body.itemAt(index).widget()
        if widget is None or widget is page._exp_more:
            continue
        for label in widget.findChildren(QLabel):
            if label.objectName() == "NextActionTitle":
                titles.append(label.text())
    assert titles == ["Buchhalter", "Teamleitung", "Sachbearbeitung"]
    assert page._exp_more.isHidden()


def test_tag_chip_keeps_long_german_and_english(qapp):
    de = TagChip("Umsatzsteuer-Voranmeldung", kind="neutral")
    en = TagChip("Accounts receivable specialist", kind="wanted")
    assert de.text() == "Umsatzsteuer-Voranmeldung"
    assert en.text() == "Accounts receivable specialist"
    assert de.sizePolicy().horizontalPolicy() == de.sizePolicy().Policy.Minimum
