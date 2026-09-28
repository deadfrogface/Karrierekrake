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
    # Unknown tokens stay. A lone E extends the class directly before it.
    assert driving_classes_for_display(["B", "B96"]) == ["B", "B96"]
    assert driving_classes_for_display(["B", "E", "C1"]) == ["B", "BE", "C1"]
    assert driving_classes_for_display("Klasse 3") == ["Klasse 3"]
    assert driving_classes_for_display("CE 95") == ["CE 95"]
    assert driving_classes_for_display(["B", "E"]) == ["B", "BE"]
    assert driving_classes_for_display(["C", "E"]) == ["C", "CE"]
    assert driving_classes_for_display(["C1", "E"]) == ["C1", "C1E"]
    assert driving_classes_for_display(["D", "E"]) == ["D", "DE"]
    assert driving_classes_for_display(["D1", "E"]) == ["D1", "D1E"]
    assert driving_classes_for_display(["E"]) == ["E"]
    assert driving_classes_for_display("E") == ["E"]
    assert driving_classes_for_display(["A", "E"]) == ["A", "E"]
    assert driving_classes_for_display(["C1", "C1E"]) == ["C1", "C1E"]
    # Digit leftovers from the old character split are not classes.
    assert driving_classes_for_display(["C", "E", "9", "5"]) == ["C", "CE"]
    assert "9" not in driving_classes_for_display(["C", "E", "9", "5"])
    assert "5" not in driving_classes_for_display(["C", "E", "9", "5"])


def test_import_license_strings_are_tokens_not_characters():
    """A licence string is split into classes, never into characters."""
    from core.cv_parser import _as_sequence

    assert _as_sequence("B, BE") == ["B", "BE"]
    assert _as_sequence("B BE") == ["B", "BE"]
    assert _as_sequence("BE") == ["BE"]
    assert _as_sequence("B und BE") == ["B", "BE"]
    assert _as_sequence("B and BE") == ["B", "BE"]
    assert _as_sequence("B/BE") == ["B", "BE"]
    assert _as_sequence("Klasse 3") == ["Klasse 3"]
    assert _as_sequence("CE 95") == ["CE 95"]
    assert _as_sequence("B96 (Anhänger)") == ["B96 (Anhänger)"]
    assert _as_sequence("B, CE 95") == ["B", "CE 95"]
    assert list("BE") == ["B", "E"]
    assert _as_sequence("BE") != ["B", "E"]
    cases = {
        "B, BE": ["B", "BE"],
        "BE": ["BE"],
        "B BE": ["B", "BE"],
        "Klasse 3": ["Klasse 3"],
        "B, CE 95": ["B", "CE 95"],
        "CE 95": ["CE 95"],
        "B96 (Anhänger)": ["B96 (Anhänger)"],
    }
    for raw, expected in cases.items():
        got = parsed_to_qualifications({"driving_license": raw}).driving_values()
        assert got == expected
        assert got != ["B", "E"]


def test_suggestion_to_parsed_passes_licence_list():
    """Docpick keeps the class list. It does not join codes into one string."""
    from core.cv_docpick_import import suggestion_to_parsed

    parsed = suggestion_to_parsed(
        {
            "name": {"first_name": "A", "last_name": "B"},
            "email": "a@example.com",
            "licenses": ["B", "BE"],
            "employment": [],
            "education": [],
            "skills": [],
            "software": [],
            "certificates": [],
            "languages": [],
        }
    )
    assert isinstance(parsed["driving_license"], list)
    assert parsed["driving_license"] == ["B", "BE"]
    assert parsed_to_qualifications(parsed).driving_values() == ["B", "BE"]


def test_parsed_string_license_is_not_split_into_characters():
    quals = parsed_to_qualifications({"driving_license": "B BE"})
    assert quals.driving_values() == ["B", "BE"]
    comma = parsed_to_qualifications({"driving_license": "B, BE"})
    assert comma.driving_values() == ["B", "BE"]
    already = parsed_to_qualifications(
        {"driving_license": [{"value": "B"}, {"value": "BE"}]}
    )
    assert already.driving_values() == ["B", "BE"]
    # Import stores the same normalisation. The base class stays beside the E variant.
    assert parsed_to_qualifications({"driving_license": "BE"}).driving_values() == ["BE"]
    assert parsed_to_qualifications({"driving_license": ["B", "E"]}).driving_values() == ["B", "BE"]
    assert parsed_to_qualifications({"driving_license": ["C", "E"]}).driving_values() == ["C", "CE"]
    assert parsed_to_qualifications({"driving_license": ["C1", "E"]}).driving_values() == ["C1", "C1E"]
    assert parsed_to_qualifications({"driving_license": ["E"]}).driving_values() == ["E"]
    imported = parsed_to_qualifications(
        {"driving_license": [{"value": "C1"}, {"value": "C1E"}, {"value": "B96"}]}
    )
    assert imported.driving_values() == ["C1", "C1E", "B96"]


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


@pytest.mark.parametrize(
    ("stored", "drawer", "expected"),
    [
        (["B", "B96"], "languages", ["B", "B96"]),
        (["B", "E", "C1"], "experience", ["B", "BE", "C1"]),
        (["Klasse 3"], "education", ["Klasse 3"]),
        (["CE 95"], "career", ["CE 95"]),
        (["C1", "C1E"], "docs", ["C1", "C1E"]),
        (["B", "E"], "personal", ["B", "BE"]),
        (["C", "E"], "experience", ["C", "CE"]),
        (["C1", "E"], "education", ["C1", "C1E"]),
        (["E"], "languages", ["E"]),
    ],
)
def test_other_drawer_save_keeps_license_in_file(
    qapp, config_service, monkeypatch, stored, drawer, expected
):
    """Loading fills every editor. Saving a different drawer must not drop classes."""
    from desktop.services.profile_merge import SOURCE_CV

    cfg = config_service.load()
    cfg.profile.qualifications.driving_license = [
        SourcedText(value=value, source="cv") for value in stored
    ]
    cfg.application.driving_license = "vorher"
    cfg.application.field_origins["driving_license"] = SOURCE_CV
    config_service.save(cfg)

    page = ProfilePage(config_service)
    page.load_from_config()
    monkeypatch.setattr(QMessageBox, "information", lambda *_a, **_k: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "warning", lambda *_a, **_k: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(
        page._drawer,
        "present",
        lambda *_args, **_kwargs: page._drawer.DialogCode.Accepted,
    )
    page._edit_section(drawer)

    profile_text = Path(config_service.profile_path).read_text(encoding="utf-8")
    application_text = Path(config_service.application_path).read_text(encoding="utf-8")
    reloaded = config_service.load()
    assert reloaded.profile.qualifications.driving_values() == expected
    for token in expected:
        assert token in profile_text
    assert reloaded.application.driving_license == ", ".join(expected)
    assert ", ".join(expected) in application_text


def test_next_drawer_opens_at_top_with_first_input_focused(qapp, config_service):
    from PySide6.QtCore import QTimer

    i18n.set_language("de")
    page = ProfilePage(config_service)
    page.resize(1000, 700)
    page.show()
    page.load_from_config()
    page.applicant.setMinimumHeight(1400)
    page.qualifications.setMinimumHeight(1400)
    qapp.processEvents()

    def scroll_contact_down() -> None:
        def apply() -> None:
            bar = page._drawer._scroll.verticalScrollBar()
            assert bar.maximum() > 0
            bar.setValue(bar.maximum())
            assert bar.value() > 0
            page._drawer.reject()

        QTimer.singleShot(0, apply)

    def check_skills() -> None:
        def verify() -> None:
            bar = page._drawer._scroll.verticalScrollBar()
            assert bar.maximum() > 0
            assert bar.value() == 0
            focus = qapp.focusWidget()
            assert focus is page.qualifications.skills.list
            page._drawer.reject()

        QTimer.singleShot(0, verify)

    QTimer.singleShot(0, scroll_contact_down)
    page._edit_section("personal")
    QTimer.singleShot(0, check_skills)
    page._edit_section("skills")


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
    # The floor is the longest word, so the full label does not set the window minimum.
    assert chip.minimumSizeHint().width() < chip.sizeHint().width()
    assert chip.minimumSizeHint().width() >= chip.fontMetrics().horizontalAdvance("bewerben")
    chip.adjustSize()
    chip.show()
    qapp.processEvents()
    assert chip.width() >= advance
    assert "…" not in chip.text()


def test_long_chip_wraps_inside_narrow_host(qapp):
    from PySide6.QtWidgets import QVBoxLayout, QWidget

    from desktop.design_system.v2_chrome import TagChip

    text = "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda"
    host = QWidget()
    layout = QVBoxLayout(host)
    layout.setContentsMargins(0, 0, 0, 0)
    chip = TagChip(text, kind="neutral")
    layout.addWidget(chip)
    host.setFixedWidth(200)
    host.show()
    qapp.processEvents()
    assert chip.sizeHint().width() > 200
    assert chip.minimumSizeHint().width() <= 200
    assert chip.width() <= 200
    assert chip.height() > chip.fontMetrics().lineSpacing()
    assert chip.text() == text
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


def _load_script(name: str):
    import importlib.util
    import sys

    module_name = f"kk_{name}"
    path = Path("/workspace/scripts") / f"{name}.py"
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_LICENSE_SHAPES = (["B", "BE"], "B, BE")


def test_parse_and_profile_readers_accept_list_and_string(tmp_path):
    """One normalisation. A list and a legacy string produce the same classes."""
    import json

    from core.config import (
        AppConfig,
        ApplicationProfile,
        ExtractReview,
        load_config,
        parse_qualifications,
    )
    from core.cover_guard import confirmed_profile_text
    from core.matcher import score_job
    from core.models import Job
    from desktop.services.profile_merge import sync_application_summaries
    from desktop.services.profile_merge import summarize_incoming

    quals = []
    summaries = []
    letters = []
    match_reasons = []
    app_summaries = []
    for raw in _LICENSE_SHAPES:
        parsed = parsed_to_qualifications({"driving_license": raw})
        quals.append(parsed.driving_values())
        summaries.append(summarize_incoming(parsed)["driving_license"])
        cfg = AppConfig()
        cfg.profile.qualifications = parsed
        cfg.profile.extract_review = ExtractReview(source="cv", confirmed=True)
        letters.append(confirmed_profile_text(cfg))
        job = Job(
            title="Fahrer",
            company="Logistik",
            remote_type="onsite",
            distance_km=5,
            description="Führerschein Klasse B erforderlich",
            employment_type="Vollzeit",
        )
        scored = score_job(job, cfg)
        match_reasons.append(
            [reason for reason in scored.match_reasons if "Führerschein" in reason]
        )
        app = ApplicationProfile()
        sync_application_summaries(app, parsed, fill_empty=True)
        app_summaries.append(app.driving_license)
        blob = json.loads(json.dumps({"parsed": {"driving_license": raw}}))
        assert parsed_to_qualifications(blob["parsed"]).driving_values() == ["B", "BE"]

    assert quals[0] == quals[1] == ["B", "BE"]
    assert summaries[0] == summaries[1] == ["B", "BE"]
    assert letters[0] == letters[1]
    assert "B" in letters[0] and "BE" in letters[0]
    assert match_reasons[0] == match_reasons[1]
    assert match_reasons[0]
    assert app_summaries[0] == app_summaries[1] == "B, BE"

    from_list = parse_qualifications(
        {"driving_license": [{"value": "B", "source": "cv"}, {"value": "BE", "source": "cv"}]}
    )
    from_string = parse_qualifications({"driving_license": "B, BE"})
    assert from_list.driving_values() == from_string.driving_values() == ["B", "BE"]

    profile_path = tmp_path / "profile.yaml"
    application_path = tmp_path / "application_profile.yaml"
    settings_path = tmp_path / "settings.yaml"
    profile_path.write_text("qualifications:\n  driving_license: 'B, BE'\n", encoding="utf-8")
    application_path.write_text("driving_license: 'B, BE'\n", encoding="utf-8")
    settings_path.write_text("{}\n", encoding="utf-8")
    before_profile = profile_path.read_bytes()
    before_application = application_path.read_bytes()
    loaded = load_config(profile_path, application_path, settings_path, strip_placeholders=False)
    assert loaded.profile.qualifications.driving_values() == ["B", "BE"]
    assert loaded.application.driving_license == "B, BE"
    assert profile_path.read_bytes() == before_profile
    assert application_path.read_bytes() == before_application


def test_licence_evaluators_accept_list_and_string():
    corpus = _load_script("run_cv_corpus")
    soll = _load_script("run_cv_sollwerte_corpus")
    holdout = _load_script("holdout_scorer_v2")
    evaluate = _load_script("evaluate_holdout_100")
    post = _load_script("run_post_analysis_language_eval")
    phi = _load_script("run_phi_language_only_benchmark")

    corpus_rows = []
    soll_rows = []
    holdout_rows = []
    evaluate_rows = []
    post_rows = []
    phi_rows = []
    for raw in _LICENSE_SHAPES:
        parsed = {"personal": {}, "driving_license": raw, "languages": []}
        corpus_rows.append(corpus.evaluate_doc(parsed, {"licenses": ["B", "BE"]})["licenses"])
        soll_fails = soll.evaluate(
            parsed,
            {"FUEHRERSCHEINE_ANZAHL": "2", "FUEHRERSCHEIN_1": "B", "FUEHRERSCHEIN_2": "BE"},
        )
        soll_rows.append([row for row in soll_fails if str(row["field"]).startswith("FUEHRERSCHEIN")])
        holdout_rows.append(holdout.pred_view(parsed)["licenses"])
        evaluate_rows.append(evaluate.pred_view(parsed)["licenses"])
        stats = post.language_licence_stats(
            {"a.pdf": {"languages": [], "licenses": ["B", "BE"]}},
            {"a.pdf": parsed},
        )
        post_rows.append((stats["licence_precision"], stats["licence_recall"]))
        phi_rows.append(phi.licence_codes(raw))

    assert corpus_rows[0] == corpus_rows[1] == (True, "ok")
    assert soll_rows[0] == soll_rows[1] == []
    assert holdout_rows[0] == holdout_rows[1] == "B BE"
    assert evaluate_rows[0] == evaluate_rows[1] == "B BE"
    assert post_rows[0] == post_rows[1] == (1.0, 1.0)
    assert phi_rows[0] == phi_rows[1] == {"B", "BE"}


def _sourced_codes(codes: list[str]) -> list[SourcedText]:
    return [SourcedText(value=code, source="cv") for code in codes]


def _profile_yaml(codes: list[str]) -> str:
    lines = ["qualifications:", "  driving_license:"]
    for code in codes:
        lines.append(f"    - value: {code!r}")
        lines.append("      source: cv")
    lines.append("")
    return "\n".join(lines)


@pytest.mark.parametrize("codes", (["B", "E"], ["B", "B", "E"]))
def test_existing_profile_reads_be_without_rewriting_file(codes, tmp_path):
    """Imported lists stay on disk. Reading them yields the normalised display."""
    from core.config import load_config

    profile_path = tmp_path / "profile.yaml"
    application_path = tmp_path / "application_profile.yaml"
    settings_path = tmp_path / "settings.yaml"
    profile_path.write_text(_profile_yaml(codes), encoding="utf-8")
    application_path.write_text("driving_license: ''\n", encoding="utf-8")
    settings_path.write_text("{}\n", encoding="utf-8")
    before = profile_path.read_bytes()

    loaded = load_config(profile_path, application_path, settings_path, strip_placeholders=False)
    assert loaded.profile.qualifications.driving_values() == codes
    assert ", ".join(driving_classes_for_display(loaded.profile.qualifications.driving_license)) == "B, BE"
    assert profile_path.read_bytes() == before

    # Startup with the shutdown migration already applied does not rewrite the file.
    from desktop.services import ConfigService

    root = tmp_path / "Karrierekrake"
    (root / "config").mkdir(parents=True)
    for name in ("data", "logs", "browser_profile", "browsers", "cvs", "cache", "cover_letters"):
        (root / name).mkdir()
    disk_profile = root / "config" / "profile.yaml"
    disk_profile.write_bytes(before)
    (root / "config" / "application_profile.yaml").write_text("driving_license: ''\n", encoding="utf-8")
    (root / "config" / "settings.yaml").write_text("{}\n", encoding="utf-8")
    (root / "meta.json").write_text(
        '{"shutdown_fix_v1": true, "first_run_completed": true}\n',
        encoding="utf-8",
    )

    class _Started(ConfigService):
        def __init__(self) -> None:
            self.dirs = {
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
            self.meta_path = root / "meta.json"
            self._config = None

    service = _Started()
    shown = service.load()
    assert ", ".join(driving_classes_for_display(shown.profile.qualifications.driving_license)) == "B, BE"
    assert disk_profile.read_bytes() == before


def test_digit_remnants_never_become_classes(tmp_path):
    """9 and 5 from the old split are dropped everywhere. The file stays as stored."""
    from core.config import ApplicationProfile, load_config
    from core.cover_guard import confirmed_profile_text
    from core.matcher import profile_licence_codes, reset_profile_licence_cache
    from desktop.services.profile_merge import sync_application_summaries

    codes = ["C", "E", "9", "5"]
    profile_path = tmp_path / "profile.yaml"
    application_path = tmp_path / "application_profile.yaml"
    settings_path = tmp_path / "settings.yaml"
    profile_path.write_text(_profile_yaml(codes), encoding="utf-8")
    application_path.write_text("{}\n", encoding="utf-8")
    settings_path.write_text("{}\n", encoding="utf-8")
    before = profile_path.read_bytes()
    loaded = load_config(profile_path, application_path, settings_path, strip_placeholders=False)
    quals = loaded.profile.qualifications
    assert quals.driving_values() == codes
    assert ", ".join(driving_classes_for_display(quals.driving_license)) == "C, CE"
    assert profile_path.read_bytes() == before

    app = ApplicationProfile()
    sync_application_summaries(app, quals, fill_empty=True)
    assert app.driving_license == "C, CE"
    assert "9" not in app.driving_license and "5" not in app.driving_license

    reset_profile_licence_cache()
    matched = profile_licence_codes(quals)
    assert matched == frozenset({"C", "CE"})
    assert "9" not in matched and "5" not in matched and "E" not in matched

    evidence = confirmed_profile_text(loaded)
    assert "C" in evidence and "CE" in evidence
    assert "9" not in evidence and "5" not in evidence
    _assert_no_list_repr_or_lone_e(evidence)


def test_sync_summary_is_every_normalised_class():
    from core.config import ApplicationProfile, QualificationsConfig
    from desktop.services.profile_merge import sync_application_summaries

    for stored in (["B", "BE"], ["B", "E"]):
        app = ApplicationProfile()
        quals = QualificationsConfig(driving_license=_sourced_codes(stored))
        before = [item.value for item in quals.driving_license]
        sync_application_summaries(app, quals, fill_empty=True)
        assert app.driving_license == "B, BE"
        assert [item.value for item in quals.driving_license] == before


def _licence_points(stored: list[str]) -> int:
    from core.config import AppConfig, QualificationsConfig
    from core.matcher import score_job
    from core.models import Job

    job = Job(
        title="Fahrer",
        company="Logistik",
        remote_type="onsite",
        distance_km=5,
        description="Führerschein Klasse B erforderlich",
        employment_type="Vollzeit",
    )

    def scored(codes: list[str]) -> int:
        cfg = AppConfig()
        cfg.profile.qualifications = QualificationsConfig(driving_license=_sourced_codes(codes))
        return score_job(job, cfg).score

    return scored(stored) - scored([])


def test_matching_class_b_is_set_membership():
    from core.config import AppConfig, QualificationsConfig
    from core.matcher import score_job
    from core.models import Job

    job = Job(
        title="Fahrer",
        company="Logistik",
        remote_type="onsite",
        distance_km=5,
        description="Führerschein Klasse B erforderlich",
        employment_type="Vollzeit",
    )
    assert _licence_points(["B"]) == 5
    assert _licence_points(["BE"]) == 5
    assert _licence_points(["C", "CE"]) == 3

    def reasons(codes: list[str]) -> list[str]:
        cfg = AppConfig()
        cfg.profile.qualifications = QualificationsConfig(driving_license=_sourced_codes(codes))
        return [row for row in score_job(job, cfg).match_reasons if "Führerschein" in row]

    assert reasons(["B"]) == ["Direkt: Führerschein Klasse B"]
    assert reasons(["BE"]) == ["Direkt: Führerschein Klasse B"]
    assert reasons(["C", "CE"]) == ["Direkt: Führerschein vorhanden"]


def test_five_thousand_ads_normalize_profile_once():
    """Scoring 5000 ads normalises the profile classes once per profile state."""
    from core.config import AppConfig, QualificationsConfig
    import core.matcher as matcher
    from core.matcher import reset_profile_licence_cache, score_job
    from core.models import Job

    jobs = [
        Job(
            id=str(i),
            title="Fahrer",
            company="Logistik",
            remote_type="onsite",
            distance_km=5,
            description="Führerschein Klasse B erforderlich",
            employment_type="Vollzeit",
        )
        for i in range(5000)
    ]
    counts = {}
    for stored in (["B", "BE"], ["B", "E"]):
        reset_profile_licence_cache()
        cfg = AppConfig()
        cfg.profile.qualifications = QualificationsConfig(driving_license=_sourced_codes(stored))
        for job in jobs:
            score_job(job, cfg)
        counts[tuple(stored)] = matcher.profile_licence_normalizations
        assert matcher.profile_licence_normalizations == 1
        cfg.profile.qualifications.driving_license = _sourced_codes(["C"])
        score_job(jobs[0], cfg)
        assert matcher.profile_licence_normalizations == 2
    assert counts[("B", "BE")] == 1
    assert counts[("B", "E")] == 1


_LONE_CLASS_E = __import__("re").compile(r"(?:^|[\s,\n])E(?:$|[\s,\n])")


def _assert_no_list_repr_or_lone_e(text: str) -> None:
    assert "['" not in text
    assert _LONE_CLASS_E.search(text) is None


def _letter_profile(codes: list[str]):
    from core.config import AppConfig, QualificationsConfig

    cfg = AppConfig()
    cfg.application.first_name = "Ada"
    cfg.application.last_name = "Beispiel"
    cfg.profile.qualifications = QualificationsConfig(
        skills=[SourcedText(value="Excel", source="manual")],
        driving_license=_sourced_codes(codes),
    )
    return cfg


def test_cover_evidence_uses_the_same_normalisation():
    from core.cover_guard import confirmed_profile_text
    from core.cover_letter import compose_cover_letter
    from core.models import Job

    job = Job(
        title="Sachbearbeiter",
        company="Nord GmbH",
        remote_type="remote",
        description=(
            "Wir suchen Unterstützung in der Verwaltung mit Excel. "
            "Führerschein Klasse B ist von Vorteil."
        ),
    )
    paired = []
    letters = []
    for stored in (["B", "BE"], ["B", "E"]):
        cfg = _letter_profile(stored)
        evidence = confirmed_profile_text(cfg)
        letter = compose_cover_letter(job, cfg)
        assert letter.ok
        paired.append(evidence)
        letters.append(letter.text)
        _assert_no_list_repr_or_lone_e(evidence)
        _assert_no_list_repr_or_lone_e(letter.text)
        assert "B" in evidence and "BE" in evidence
    assert paired[0] == paired[1]
    assert letters[0] == letters[1]

    absent = confirmed_profile_text(_letter_profile(["B", "BE"]))
    for phrase in ("B96", "CE 95", "Klasse 3"):
        assert phrase not in absent
    present = confirmed_profile_text(_letter_profile(["B96", "CE 95", "Klasse 3"]))
    for phrase in ("B96", "CE 95", "Klasse 3"):
        assert phrase in present
    _assert_no_list_repr_or_lone_e(present)
