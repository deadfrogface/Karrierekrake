"""Manual UI QA: wizard once, one job action, chip width, licence classes, import cards."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QPushButton

from core.config import LanguageEntry, QualificationsConfig, SourcedText
from core.cv_parser import driving_classes_for_display, parsed_to_qualifications
from desktop.i18n import i18n, tr
from desktop.pages.jobs import JobsPage
from desktop.pages.profile import ProfilePage
from desktop.pages.profile_sections import QualificationsSection


@pytest.fixture
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
    monkeypatch.setattr(
        "desktop.services.schedule_service.ScheduleService.sync_from_config",
        lambda self: (True, "ok"),
    )
    from desktop.services import ConfigService

    return ConfigService()


def _visible_button_texts(page) -> list[str]:
    texts: list[str] = []
    for button in page.findChildren(QPushButton):
        if button.isVisible() and button.text():
            texts.append(button.text())
    return texts


def test_driving_classes_deduped_for_display_without_mutating_storage():
    stored = ["B", "B", "E"]
    assert driving_classes_for_display(stored) == ["B", "BE"]
    assert stored == ["B", "B", "E"]
    assert driving_classes_for_display("B BE") == ["B", "BE"]
    assert driving_classes_for_display("B, BE") == ["B", "BE"]
    assert driving_classes_for_display(["B", ",", "B", "E"]) == ["B", "BE"]
    assert driving_classes_for_display(["BE", "B", "B"]) == ["B", "BE"]
    assert ", ".join(driving_classes_for_display(["B", "B", "E"])) == "B, BE"
    # A class the parser already stored must survive display (C1 overlaps CEFR).
    assert driving_classes_for_display([{"value": "C1"}]) == ["C1"]
    assert driving_classes_for_display(["C1", "B", "B"]) == ["B", "C1"]


def test_parsed_string_license_is_not_split_into_characters():
    quals = parsed_to_qualifications({"driving_license": "B BE"})
    assert quals.driving_values() == ["B", "BE"]
    comma = parsed_to_qualifications({"driving_license": "B, BE"})
    assert comma.driving_values() == ["B", "BE"]
    already = parsed_to_qualifications(
        {"driving_license": [{"value": "B"}, {"value": "BE"}]}
    )
    assert already.driving_values() == ["B", "BE"]


def test_license_editor_shows_deduped_classes(qapp):
    section = QualificationsSection()
    quals = QualificationsConfig(
        driving_license=[
            SourcedText(value="B", source="cv"),
            SourcedText(value="B", source="cv"),
            SourcedText(value="E", source="cv"),
        ]
    )
    before = [item.value for item in quals.driving_license]
    section.load(quals)
    assert section.driving.get_items() == ["B", "BE"]
    assert [item.value for item in quals.driving_license] == before


def test_wizard_completed_or_skipped_stays_done(qapp, config_service):
    from desktop.services import ConfigService
    from desktop.wizard import FirstRunWizard

    assert config_service.is_first_run()
    finished = FirstRunWizard(config_service)
    finished.accept()
    assert not config_service.is_first_run()
    again = ConfigService()
    assert not again.is_first_run()

    # A fresh tree: skipping must persist the same way.
    root = Path(config_service.meta_path).parent
    meta = root / "meta.json"
    meta.write_text('{"first_run_completed": false}\n', encoding="utf-8")
    skipped_svc = ConfigService()
    assert skipped_svc.is_first_run()
    skipped = FirstRunWizard(skipped_svc)
    skipped.reject()
    assert not skipped_svc.is_first_run()
    assert not ConfigService().is_first_run()


def test_wizard_not_shown_on_second_start(qapp, config_service, monkeypatch):
    monkeypatch.setattr("desktop.tray.AppTray.show", lambda self: None)
    monkeypatch.setattr("desktop.tray.AppTray.showMessage", lambda *a, **k: None)
    from desktop.main_window import MainWindow
    from desktop.wizard import FirstRunWizard

    calls = {"n": 0}

    def _finish(self):
        calls["n"] += 1
        self.accept()
        return 1

    monkeypatch.setattr(FirstRunWizard, "exec", _finish)
    first = MainWindow(config_service)
    first.maybe_run_wizard()
    assert calls["n"] == 1
    assert not config_service.is_first_run()

    second = MainWindow(config_service)
    second.maybe_run_wizard()
    assert calls["n"] == 1


@pytest.mark.parametrize("scale", [1.0, 1.25])
def test_mode_chip_size_hint_fits_full_text(qapp, scale):
    from desktop.design_system.v2_chrome import TagChip

    label = "Nur Suche – nie bewerben"
    chip = TagChip(label, kind="neutral")
    font = chip.font()
    base = font.pointSizeF() if font.pointSizeF() > 0 else 11.0
    font.setPointSizeF(base * scale)
    chip.setFont(font)
    chip.ensurePolished()
    advance = chip.fontMetrics().horizontalAdvance(chip.text())
    assert chip.text() == label
    assert chip.sizeHint().width() >= advance
    assert chip.minimumSizeHint().width() >= advance
    chip.adjustSize()
    chip.show()
    qapp.processEvents()
    assert chip.width() >= advance
    assert "…" not in chip.text()


def test_job_open_and_prepare_appear_once(qapp, config_service):
    i18n.set_language("de")
    page = JobsPage(config_service)
    page.resize(1100, 720)
    page.show()
    qapp.processEvents()
    open_label = tr("btn.open_job")
    prepare_label = tr("btn.prepare_application")
    visible = _visible_button_texts(page)
    assert visible.count(open_label) == 1
    assert visible.count(prepare_label) == 1
    detail_texts = _visible_button_texts(page.detail)
    assert detail_texts.count(open_label) == 1
    assert detail_texts.count(prepare_label) == 1


def test_import_shows_skill_and_language_cards(qapp, config_service, tmp_path, monkeypatch):
    i18n.set_language("de")
    cv_file = tmp_path / "lebenslauf.pdf"
    cv_file.write_bytes(b"%PDF-1.4\n")
    cfg = config_service.load()
    cfg.application.cv_path = str(cv_file)
    config_service.save(cfg)

    imported = QualificationsConfig(
        skills=[SourcedText(value="SAP", source="cv"), SourcedText(value="Excel", source="cv")],
        languages=[
            LanguageEntry(language="Deutsch", level="C2", source="cv"),
            LanguageEntry(language="Englisch", level="B2", source="cv"),
        ],
    )

    class _AcceptedImport:
        DialogCode = QDialog.DialogCode

        def __init__(self, cv_path, *_args, **_kwargs) -> None:
            self.cv_path = Path(cv_path)
            self.result_quals = imported
            self.result_application = None

        def exec(self) -> QDialog.DialogCode:
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr("desktop.pages.profile.CvImportDialog", _AcceptedImport)
    monkeypatch.setattr(QMessageBox, "information", lambda *_a, **_k: QMessageBox.StandardButton.Ok)

    page = ProfilePage(config_service)
    page.resize(1200, 900)
    page.show()
    qapp.processEvents()
    page.import_from_cv()
    qapp.processEvents()

    def _chip_texts(layout) -> list[str]:
        found: list[str] = []
        for index in range(layout.count()):
            widget = layout.itemAt(index).widget()
            if widget is None:
                continue
            found.append(widget.text())
            assert widget.isVisible()
            assert widget.width() > 0
            assert widget.height() > 0
        return found

    skills = _chip_texts(page._skills_row)
    languages = _chip_texts(page._lang_row)
    assert "SAP" in skills
    assert "Excel" in skills
    assert "Deutsch (C2)" in languages
    assert "Englisch (B2)" in languages
    reloaded = config_service.load()
    assert "SAP" in reloaded.profile.qualifications.skill_values()
    assert any(lang.language == "Deutsch" for lang in reloaded.profile.qualifications.languages)
