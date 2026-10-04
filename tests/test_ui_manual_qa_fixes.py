"""Manual UI QA: wizard once, one job action, chip width, licence classes, import cards."""

from __future__ import annotations

import hashlib
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
    assert driving_classes_for_display(["E", "B"]) == ["B"]
    assert "E" not in driving_classes_for_display(["E", "B"])
    assert driving_classes_for_display(["E"]) == []
    assert driving_classes_for_display("E") == []
    assert driving_classes_for_display(["A", "E"]) == ["A"]
    assert driving_classes_for_display(["C1", "C1E"]) == ["C1", "C1E"]
    # Digit leftovers are not classes. A bare C beside them is uncertain.
    assert driving_classes_for_display(["C", "E", "9", "5"]) == []
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
    assert parsed_to_qualifications({"driving_license": ["E"]}).driving_values() == []
    assert parsed_to_qualifications({"driving_license": ["E", "B"]}).driving_values() == ["B"]
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
        (["E", "B"], "languages", ["B"]),
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


def _stub_resource_if_missing() -> bool:
    """Eval-Skripte importieren ``resource`` nur für den Peak-RSS.

    Windows hat das Modul nicht. Der Stub lässt die Führerschein-Helfer
    importieren. Unter Linux bleibt das echte Modul.
    """
    import sys
    import types

    try:
        import resource  # noqa: F401
    except ModuleNotFoundError:
        stub = types.ModuleType("resource")
        stub.RUSAGE_SELF = 0

        def getrusage(_who: int = 0):
            return types.SimpleNamespace(ru_maxrss=0.0)

        stub.getrusage = getrusage
        sys.modules["resource"] = stub
        return True
    return False


def _load_script(name: str):
    import importlib.util
    import sys

    module_name = f"kk_{name}"
    path = Path(__file__).resolve().parents[1] / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[module_name] = module
    stubbed = _stub_resource_if_missing()
    try:
        spec.loader.exec_module(module)
    finally:
        if stubbed:
            sys.modules.pop("resource", None)
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
    loaded = Path(corpus.__file__).resolve()
    assert loaded == Path(__file__).resolve().parents[1] / "scripts" / "run_cv_corpus.py"
    assert loaded.is_file()
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
    assert driving_classes_for_display(quals.driving_license) == []
    assert profile_path.read_bytes() == before

    app = ApplicationProfile()
    sync_application_summaries(app, quals, fill_empty=True)
    assert app.driving_license == ""
    assert "9" not in app.driving_license and "5" not in app.driving_license

    reset_profile_licence_cache()
    matched = profile_licence_codes(quals)
    assert matched == frozenset()
    assert "C" not in matched and "CE" not in matched

    evidence = confirmed_profile_text(loaded)
    assert "C" not in evidence and "CE" not in evidence
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


def _licence_points(
    stored: list[str],
    description: str = "Führerschein Klasse B erforderlich",
) -> int:
    from core.config import AppConfig, QualificationsConfig
    from core.matcher import score_job
    from core.models import Job

    job = Job(
        title="Fahrer",
        company="Logistik",
        remote_type="onsite",
        distance_km=5,
        description=description,
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


def _with_matching_station(cfg, *, title: str, company: str, task: str | list[str]):
    """A professional station whose tasks are also in the job ad."""
    from core.config import ExperienceEntry

    responsibilities = [task] if isinstance(task, str) else list(task)
    cfg.profile.qualifications.work_experience = [
        ExperienceEntry(
            title=title,
            company=company,
            responsibilities=responsibilities,
            source="manual",
        )
    ]
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
            "Wir suchen Unterstützung in der Verwaltung mit Excel, Rechnungsprüfung und Mahnwesen. "
            "Führerschein Klasse B ist von Vorteil."
        ),
    )
    paired = []
    letters = []
    for stored in (["B", "BE"], ["B", "E"]):
        cfg = _with_matching_station(
            _letter_profile(stored),
            title="Sachbearbeiterin",
            company="Nordlicht GmbH",
            task=["Rechnungsprüfung", "Mahnwesen"],
        )
        evidence = confirmed_profile_text(cfg)
        letter = compose_cover_letter(job, cfg)
        assert letter.ok
        assert "Sachbearbeiterin" in letter.text
        assert "Nordlicht GmbH" in letter.text
        assert "Excel" in letter.text
        paired.append(evidence)
        letters.append(letter.text)
        _assert_no_list_repr_or_lone_e(evidence)
        _assert_no_list_repr_or_lone_e(letter.text)
        assert "B" in evidence.splitlines()
    assert "BE" in paired[0].splitlines()
    assert "BE" not in paired[1].splitlines()
    assert "BE" not in letters[0] and "BE" not in letters[1]

    absent = confirmed_profile_text(_letter_profile(["B", "BE"]))
    for phrase in ("B96", "CE 95", "Klasse 3"):
        assert phrase not in absent
    present = confirmed_profile_text(_letter_profile(["B96", "CE 95", "Klasse 3"]))
    for phrase in ("B96", "CE 95", "Klasse 3"):
        assert phrase in present
    _assert_no_list_repr_or_lone_e(present)


def test_old_character_split_is_recovered_without_uncertain_classes():
    from core.cv_parser import read_driving_classes

    broken = read_driving_classes(["B", "C", "1", "D"])
    assert broken.display == ["B", "C1"]
    assert "D" not in broken.display
    assert broken.uncertain == ["D"]
    assert broken.recovered
    assert broken.evidence == ["B"]

    rebuilt = read_driving_classes(["C", "1", "E"])
    assert rebuilt.display == ["C1E"]
    assert rebuilt.evidence == []
    assert rebuilt.recovered

    mixed = read_driving_classes(["B", "E", "C"])
    assert mixed.display == ["B", "BE", "C"]
    assert "CE" not in mixed.display
    assert mixed.evidence == ["B", "C"]
    assert mixed.recovered

    legacy = read_driving_classes(["B", "E"])
    assert legacy.display == ["B", "BE"]
    assert legacy.evidence == ["B"]
    assert legacy.recovered
    assert read_driving_classes(["B", "BE"]).recovered is False
    assert read_driving_classes(["B", "BE"]).evidence == ["B", "BE"]
    assert _licence_points(["C", "9"]) == 3
    assert _licence_points(["B", "C", "1", "D"]) == 5


def test_recovered_be_is_not_a_letter_until_the_drawer_saves_it():
    from core.config import ExtractReview
    from core.cover_guard import confirmed_licence_codes, confirmed_profile_text, screen_cover_letter
    from core.cover_letter import compose_cover_letter
    from core.models import Job

    job = Job(
        title="Fahrer",
        company="Nord GmbH",
        remote_type="remote",
        description=(
            "Wir suchen eine Fahrerin mit Excel, Tourenplanung und Ladungssicherung. "
            "Führerschein Klasse BE ist erforderlich."
        ),
    )
    cfg = _with_matching_station(
        _letter_profile(["B", "E"]),
        title="Fahrerin",
        company="Holm Logistik",
        task=["Tourenplanung", "Ladungssicherung"],
    )
    cfg.profile.extract_review = ExtractReview(source="cv", confirmed=True)
    evidence = confirmed_profile_text(cfg)
    assert "B" in evidence.splitlines()
    assert "BE" not in evidence.splitlines()
    letter = compose_cover_letter(job, cfg)
    assert letter.ok
    assert "Fahrerin" in letter.text
    assert "Holm Logistik" in letter.text
    assert "Excel" in letter.text
    assert "BE" not in letter.text
    claim = "Ich habe den Führerschein BE."
    blocked = screen_cover_letter(
        claim,
        confirmed_text=evidence,
        confirmed_licences=confirmed_licence_codes(cfg),
        job_text="Lager",
    )
    assert not blocked.ok

    saved = _letter_profile(["B", "BE"])
    saved.profile.extract_review = ExtractReview(source="cv", confirmed=True)
    evidence_saved = confirmed_profile_text(saved)
    assert "BE" in evidence_saved.splitlines()
    allowed = screen_cover_letter(
        claim,
        confirmed_text=evidence_saved,
        confirmed_licences=confirmed_licence_codes(saved),
        job_text="Lager",
    )
    assert allowed.ok


def test_recovered_licence_hint_and_drawer_save(qapp, config_service, monkeypatch):
    """A recovered list shows a warning. Saving the drawer writes the clean list once."""
    from PySide6.QtCore import QTimer

    from desktop.theme import apply_theme

    i18n.set_language("de")
    apply_theme(qapp, "light")
    messages: list[str] = []

    def information(_parent, _title, text, *_args, **_kwargs):
        messages.append(str(text))
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(QMessageBox, "information", information)
    monkeypatch.setattr(QMessageBox, "warning", lambda *_a, **_k: QMessageBox.StandardButton.Ok)

    def prepare(codes: list[str]):
        cfg = config_service.load()
        cfg.profile.qualifications.driving_license = _sourced_codes(codes)
        cfg.profile.qualifications.skills = []
        config_service.save(cfg)
        page = ProfilePage(config_service)
        page.resize(1100, 800)
        page.show()
        page.load_from_config()
        qapp.processEvents()
        return page

    uncertain = prepare(["B", "C", "1", "D"])
    assert uncertain._licence_notice.isVisible()
    assert uncertain._licence_review_btn.isVisible()
    assert uncertain._licence_review_btn.text() == "Prüfen"
    assert uncertain._licence_notice.objectName() == "WarningLabel"
    assert "Aus einem älteren Import wiederhergestellt" in uncertain._licence_notice.text()
    assert "Nicht sicher erkannt: D." in uncertain._licence_notice.text()
    assert uncertain._licence_line.text() == "Führerschein: B, C1"
    assert "D" not in [part.strip() for part in uncertain._licence_line.text().split(":")[-1].split(",")]
    assert uncertain.qualifications.driving.get_items() == ["B", "C1", "D"]
    assert "Aus einem älteren Import wiederhergestellt" in uncertain.qualifications.licence_notice.text()
    assert "Nicht sicher erkannt" not in uncertain.qualifications.licence_notice.text()
    uncertain.card_skills.grab().save("/opt/cursor/artifacts/licence-card-b-c1-d.png")

    page = prepare(["B", "E"])
    assert "Aus einem älteren Import wiederhergestellt" in page._licence_notice.text()
    assert "Nicht sicher erkannt" not in page._licence_notice.text()
    assert page._licence_line.text() == "Führerschein: B, BE"
    assert page.qualifications.driving.get_items() == ["B", "BE"]
    page.card_skills.grab().save("/opt/cursor/artifacts/licence-card-b-e.png")
    profile_path = Path(config_service.profile_path)
    before_save = profile_path.read_bytes()
    writes = {"n": 0}
    original_write = config_service._write_config_files

    def counting_write(config):
        writes["n"] += 1
        return original_write(config)

    monkeypatch.setattr(config_service, "_write_config_files", counting_write)

    def accept_drawer() -> None:
        def verify() -> None:
            try:
                assert qapp.focusWidget() is page.qualifications.driving.list
                viewport = page._drawer._scroll.viewport()
                point = page.qualifications.driving.mapTo(
                    viewport, page.qualifications.driving.rect().center()
                )
                assert viewport.rect().contains(point)
                assert page.qualifications.licence_notice.isVisible()
                assert "Aus einem älteren Import wiederhergestellt" in page.qualifications.licence_notice.text()
            finally:
                page._drawer.accept()

        QTimer.singleShot(0, verify)

    QTimer.singleShot(0, accept_drawer)
    page._licence_review_btn.click()
    qapp.processEvents()
    reloaded = config_service.load()
    assert reloaded.profile.qualifications.driving_values() == ["B", "BE"]
    assert profile_path.read_bytes() != before_save
    assert messages[-1] == "Gespeichert."
    page.load_from_config()
    qapp.processEvents()
    assert not page._licence_notice.isVisible()
    assert not page._licence_review_btn.isVisible()

    stored = profile_path.read_bytes()
    stored_stat = (profile_path.stat().st_mtime_ns, hashlib.sha256(stored).hexdigest())

    def accept_again() -> None:
        page._drawer.accept()

    QTimer.singleShot(0, accept_again)
    page._edit_section("skills")
    qapp.processEvents()
    assert profile_path.read_bytes() == stored
    assert (profile_path.stat().st_mtime_ns, hashlib.sha256(profile_path.read_bytes()).hexdigest()) == stored_stat
    assert config_service.load().profile.qualifications.driving_values() == ["B", "BE"]
    assert messages[-1] == "Keine Änderungen."
    assert writes["n"] == 1

    salad = prepare(["C", "E", "9", "5"])
    assert salad._licence_line.text() == "Führerschein: —"
    assert "Nicht sicher erkannt: C." in salad._licence_notice.text()
    assert salad.qualifications.driving.get_items() == ["C", "E"]
    assert salad.qualifications.licence_unknown.text() == (
        "Nicht sicher erkannt: 9, 5. Diese Einträge bleiben unverändert gespeichert."
    )
    assert "Nicht sicher erkannt" not in salad.qualifications.licence_notice.text()
    salad.card_skills.grab().save("/opt/cursor/artifacts/licence-card-c-e-9-5.png")

    am = prepare(["A", "M"])
    assert am._licence_line.text() == "Führerschein: AM"
    assert "Aus einem älteren Import wiederhergestellt" in am._licence_notice.text()
    assert "Nicht sicher erkannt" not in am._licence_notice.text()
    assert am.qualifications.driving.get_items() == ["AM"]
    am.card_skills.grab().save("/opt/cursor/artifacts/licence-card-a-m.png")


def test_unknown_licence_line_equals_the_utf8_literal(qapp):
    """The grey drawer line is this UTF-8 sentence, including the comma and the period."""
    i18n.set_language("de")
    section = QualificationsSection()
    section.load(
        QualificationsConfig(driving_license=_sourced_codes(["C", "E", "9", "5"]))
    )
    assert section.licence_unknown.text() == (
        "Nicht sicher erkannt: 9, 5. Diese Einträge bleiben unverändert gespeichert."
    )


def test_uncertain_digits_stay_in_the_file_when_review_saves_nothing(qapp, config_service, monkeypatch):
    """Prüfen on [C, E, 9, 5] shows C and E. Saving without input keeps the file."""
    from PySide6.QtCore import QTimer

    i18n.set_language("de")
    messages: list[str] = []

    def information(_parent, _title, text, *_args, **_kwargs):
        messages.append(str(text))
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(QMessageBox, "information", information)
    monkeypatch.setattr(QMessageBox, "warning", lambda *_a, **_k: QMessageBox.StandardButton.Ok)
    cfg = config_service.load()
    cfg.profile.qualifications.driving_license = _sourced_codes(["C", "E", "9", "5"])
    cfg.profile.qualifications.skills = []
    config_service.save(cfg)
    page = ProfilePage(config_service)
    page.resize(1100, 800)
    page.show()
    page.load_from_config()
    qapp.processEvents()
    # The applicant form marks blank fields as manual. Persist that once so the
    # measured save is only about the licence list.
    settled = config_service.load()
    page.applicant.save_into(settled.application)
    config_service.save(settled)
    page.load_from_config()
    qapp.processEvents()
    profile_path = Path(config_service.profile_path)
    before = profile_path.read_bytes()
    assert page._licence_review_btn.isVisible()
    assert page.qualifications.driving.get_items() == ["C", "E"]
    assert page.qualifications.licence_unknown.text() == (
        "Nicht sicher erkannt: 9, 5. Diese Einträge bleiben unverändert gespeichert."
    )
    assert page._licence_notice.isVisible()
    page.qualifications.skills.setMinimumHeight(900)
    results: list[bool] = []
    original = page.save

    def wrapped() -> bool:
        value = original()
        results.append(value)
        return value

    page.save = wrapped

    def accept_empty() -> None:
        def verify() -> None:
            try:
                assert page.qualifications.driving.get_items() == ["C", "E"]
                assert qapp.focusWidget() is page.qualifications.driving.list
                viewport = page._drawer._scroll.viewport()
                point = page.qualifications.driving.mapTo(
                    viewport, page.qualifications.driving.rect().center()
                )
                assert viewport.rect().contains(point)
            finally:
                page._drawer.accept()

        QTimer.singleShot(0, verify)

    QTimer.singleShot(0, accept_empty)
    page._licence_review_btn.click()
    qapp.processEvents()
    assert results == [False]
    assert messages[-1] == "Keine Änderungen."
    assert profile_path.read_bytes() == before
    assert config_service.load().profile.qualifications.driving_values() == ["C", "E", "9", "5"]
    assert page._licence_notice.isVisible()
    assert "Aus einem älteren Import wiederhergestellt" in page._licence_notice.text()


def test_unchecking_e_drops_it_and_keeps_unknown_digits(qapp, config_service, monkeypatch):
    """Removing E from [C, E, 9, 5] leaves C, 9 and 5, and does not hide E."""
    from PySide6.QtCore import Qt, QTimer

    i18n.set_language("de")
    messages: list[str] = []

    def information(_parent, _title, text, *_args, **_kwargs):
        messages.append(str(text))
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(QMessageBox, "information", information)
    monkeypatch.setattr(QMessageBox, "warning", lambda *_a, **_k: QMessageBox.StandardButton.Ok)
    cfg = config_service.load()
    cfg.profile.qualifications.driving_license = _sourced_codes(["C", "E", "9", "5"])
    cfg.profile.qualifications.skills = []
    config_service.save(cfg)
    page = ProfilePage(config_service)
    page.resize(1100, 800)
    page.show()
    page.load_from_config()
    qapp.processEvents()
    settled = config_service.load()
    page.applicant.save_into(settled.application)
    config_service.save(settled)
    page.load_from_config()
    qapp.processEvents()
    assert page.qualifications.driving.get_items() == ["C", "E"]

    def drop_e() -> None:
        def verify() -> None:
            try:
                driving = page.qualifications.driving
                match = driving.list.findItems("E", Qt.MatchFlag.MatchExactly)
                assert len(match) == 1
                match[0].setSelected(True)
                driving.remove_btn.click()
                assert driving.get_items() == ["C"]
            finally:
                page._drawer.accept()

        QTimer.singleShot(0, verify)

    QTimer.singleShot(0, drop_e)
    page._licence_review_btn.click()
    qapp.processEvents()
    assert messages[-1] == "Gespeichert."
    values = config_service.load().profile.qualifications.driving_values()
    assert values == ["C", "9", "5"]
    assert "E" not in values


def test_unchanged_c_with_two_digit_suffix_stays_byte_identical(qapp, config_service, monkeypatch):
    """[C, 95] shows C and the unknown line. Saving without input keeps the file."""
    from PySide6.QtCore import QTimer

    i18n.set_language("de")
    messages: list[str] = []

    def information(_parent, _title, text, *_args, **_kwargs):
        messages.append(str(text))
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(QMessageBox, "information", information)
    monkeypatch.setattr(QMessageBox, "warning", lambda *_a, **_k: QMessageBox.StandardButton.Ok)
    cfg = config_service.load()
    cfg.profile.qualifications.driving_license = _sourced_codes(["C", "95"])
    cfg.profile.qualifications.skills = []
    config_service.save(cfg)
    page = ProfilePage(config_service)
    page.resize(1100, 800)
    page.show()
    page.load_from_config()
    qapp.processEvents()
    settled = config_service.load()
    page.applicant.save_into(settled.application)
    config_service.save(settled)
    page.load_from_config()
    qapp.processEvents()
    profile_path = Path(config_service.profile_path)
    before = profile_path.read_bytes()
    assert page.qualifications.driving.get_items() == ["C"]
    assert page.qualifications.licence_unknown.text() == (
        "Nicht sicher erkannt: 95. Diese Einträge bleiben unverändert gespeichert."
    )
    from PySide6.QtCore import Qt

    assert (
        page.qualifications.licence_unknown.textInteractionFlags()
        == Qt.TextInteractionFlag.NoTextInteraction
    )
    results: list[bool] = []
    original = page.save

    def wrapped() -> bool:
        value = original()
        results.append(value)
        return value

    page.save = wrapped

    def accept_unchanged() -> None:
        try:
            assert page.qualifications.driving.get_items() == ["C"]
        finally:
            page._drawer.accept()

    QTimer.singleShot(0, accept_unchanged)
    page._edit_section("skills")
    qapp.processEvents()
    assert results == [False]
    assert messages[-1] == "Keine Änderungen."
    assert profile_path.read_bytes() == before
    assert config_service.load().profile.qualifications.driving_values() == ["C", "95"]


def _profile_for_licence(qapp, config_service, monkeypatch, codes: list[str]):
    """Load a profile whose only licence data is ``codes``, with origins settled."""
    messages: list[str] = []

    def information(_parent, _title, text, *_args, **_kwargs):
        messages.append(str(text))
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(QMessageBox, "information", information)
    monkeypatch.setattr(QMessageBox, "warning", lambda *_a, **_k: QMessageBox.StandardButton.Ok)
    cfg = config_service.load()
    cfg.profile.qualifications.driving_license = _sourced_codes(codes)
    cfg.profile.qualifications.skills = []
    config_service.save(cfg)
    page = ProfilePage(config_service)
    page.resize(1100, 800)
    page.show()
    page.load_from_config()
    qapp.processEvents()
    settled = config_service.load()
    page.applicant.save_into(settled.application)
    config_service.save(settled)
    page.load_from_config()
    qapp.processEvents()
    return page, messages


def _save_drawer_without_edit(page, qapp) -> list[bool]:
    from PySide6.QtCore import QTimer

    results: list[bool] = []
    original = page.save

    def wrapped() -> bool:
        value = original()
        results.append(value)
        return value

    page.save = wrapped

    def accept_unchanged() -> None:
        page._drawer.accept()

    QTimer.singleShot(0, accept_unchanged)
    page._edit_section("skills")
    qapp.processEvents()
    return results


def test_b_with_digits_keeps_the_grey_line_and_the_file(qapp, config_service, monkeypatch):
    """[B, 9, 5] shows B and the grey line. Saving without input keeps the file."""
    i18n.set_language("de")
    page, messages = _profile_for_licence(qapp, config_service, monkeypatch, ["B", "9", "5"])
    profile_path = Path(config_service.profile_path)
    before = profile_path.read_bytes()
    assert page.qualifications.driving.get_items() == ["B"]
    assert page.qualifications.licence_unknown.text() == (
        "Nicht sicher erkannt: 9, 5. Diese Einträge bleiben unverändert gespeichert."
    )
    results = _save_drawer_without_edit(page, qapp)
    assert results == [False]
    assert messages[-1] == "Keine Änderungen."
    assert profile_path.read_bytes() == before
    assert config_service.load().profile.qualifications.driving_values() == ["B", "9", "5"]


def test_ce_with_digits_stays_byte_identical(qapp, config_service, monkeypatch):
    """[CE, 9, 5] shows CE and the same grey line. Saving without input keeps the file."""
    i18n.set_language("de")
    page, messages = _profile_for_licence(qapp, config_service, monkeypatch, ["CE", "9", "5"])
    profile_path = Path(config_service.profile_path)
    before = profile_path.read_bytes()
    assert page.qualifications.driving.get_items() == ["CE"]
    assert page.qualifications.licence_unknown.text() == (
        "Nicht sicher erkannt: 9, 5. Diese Einträge bleiben unverändert gespeichert."
    )
    results = _save_drawer_without_edit(page, qapp)
    assert results == [False]
    assert messages[-1] == "Keine Änderungen."
    assert profile_path.read_bytes() == before
    assert config_service.load().profile.qualifications.driving_values() == ["CE", "9", "5"]


def test_b_and_m_keeps_m_as_a_row(qapp, config_service, monkeypatch):
    """[B, M] shows M as its own row. Saving without input keeps both entries."""
    i18n.set_language("de")
    page, messages = _profile_for_licence(qapp, config_service, monkeypatch, ["B", "M"])
    profile_path = Path(config_service.profile_path)
    before = profile_path.read_bytes()
    assert page.qualifications.driving.get_items() == ["B", "M"]
    assert not page.qualifications.licence_unknown.isVisible()
    assert page.qualifications.licence_unknown.text() == ""
    results = _save_drawer_without_edit(page, qapp)
    assert results == [False]
    assert messages[-1] == "Keine Änderungen."
    assert profile_path.read_bytes() == before
    assert config_service.load().profile.qualifications.driving_values() == ["B", "M"]


def test_b_c_e_with_digits_keeps_e_and_the_digits(qapp, config_service, monkeypatch):
    """[B, C, E, 9, 5] shows B, C and E. The grey line names only 9 and 5."""
    i18n.set_language("de")
    page, messages = _profile_for_licence(
        qapp, config_service, monkeypatch, ["B", "C", "E", "9", "5"]
    )
    profile_path = Path(config_service.profile_path)
    before = profile_path.read_bytes()
    assert page.qualifications.driving.get_items() == ["B", "C", "E"]
    assert page.qualifications.licence_unknown.text() == (
        "Nicht sicher erkannt: 9, 5. Diese Einträge bleiben unverändert gespeichert."
    )
    results = _save_drawer_without_edit(page, qapp)
    assert results == [False]
    assert messages[-1] == "Keine Änderungen."
    assert profile_path.read_bytes() == before
    assert config_service.load().profile.qualifications.driving_values() == ["B", "C", "E", "9", "5"]


def _yaml_block(text: str, key: str) -> str:
    lines = text.splitlines()
    start = None
    indent = 0
    for index, line in enumerate(lines):
        stripped = line.lstrip(" ")
        if stripped.startswith(f"{key}:"):
            start = index
            indent = len(line) - len(stripped)
            break
    assert start is not None
    end = start + 1
    while end < len(lines):
        line = lines[end]
        if not line.strip():
            end += 1
            continue
        current = len(line) - len(line.lstrip(" "))
        if current > indent or (current == indent and line.lstrip(" ").startswith("- ")):
            end += 1
            continue
        break
    return "\n".join(lines[start:end])


def test_language_save_keeps_digits_beside_class_b(qapp, config_service, monkeypatch):
    """Changing only languages through ProfilePage.save leaves 9 and 5 verbatim."""
    i18n.set_language("de")
    page, messages = _profile_for_licence(qapp, config_service, monkeypatch, ["B", "9", "5"])
    profile_path = Path(config_service.profile_path)
    before = profile_path.read_text(encoding="utf-8")
    licence_before = _yaml_block(before, "driving_license")
    assert page.qualifications.driving.get_items() == ["B"]
    assert page.qualifications.licence_unknown.text() == (
        "Nicht sicher erkannt: 9, 5. Diese Einträge bleiben unverändert gespeichert."
    )
    page.languages.languages.set_items(
        [LanguageEntry(language="Englisch", level="C1", source="manual")]
    )
    assert page.save() is True
    qapp.processEvents()
    after = profile_path.read_text(encoding="utf-8")
    assert messages[-1] == "Gespeichert."
    assert _yaml_block(after, "driving_license") == licence_before
    assert "9" in licence_before and "5" in licence_before
    saved = config_service.load()
    assert saved.profile.qualifications.driving_values() == ["B", "9", "5"]
    assert saved.profile.qualifications.languages[0].language == "Englisch"
    assert saved.profile.qualifications.languages[0].level == "C1"


def test_two_digit_suffix_stays_when_the_drawer_saves_nothing(qapp, config_service, monkeypatch):
    """Opening [C, CE, 95] and saving without input keeps 95 and reports no change."""
    from PySide6.QtCore import QTimer

    i18n.set_language("de")
    messages: list[str] = []

    def information(_parent, _title, text, *_args, **_kwargs):
        messages.append(str(text))
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(QMessageBox, "information", information)
    monkeypatch.setattr(QMessageBox, "warning", lambda *_a, **_k: QMessageBox.StandardButton.Ok)
    cfg = config_service.load()
    cfg.profile.qualifications.driving_license = _sourced_codes(["C", "CE", "95"])
    cfg.profile.qualifications.skills = []
    config_service.save(cfg)
    page = ProfilePage(config_service)
    page.resize(1100, 800)
    page.show()
    page.load_from_config()
    qapp.processEvents()
    settled = config_service.load()
    page.applicant.save_into(settled.application)
    config_service.save(settled)
    page.load_from_config()
    qapp.processEvents()
    profile_path = Path(config_service.profile_path)
    before = profile_path.read_bytes()
    assert not page._licence_review_btn.isVisible()
    assert page.qualifications.driving.get_items() == ["C", "CE"]
    results: list[bool] = []
    original = page.save

    def wrapped() -> bool:
        value = original()
        results.append(value)
        return value

    page.save = wrapped

    def accept_unchanged() -> None:
        try:
            assert page.qualifications.driving.get_items() == ["C", "CE"]
        finally:
            page._drawer.accept()

    QTimer.singleShot(0, accept_unchanged)
    page._edit_section("skills")
    qapp.processEvents()
    assert results == [False]
    assert messages[-1] == "Keine Änderungen."
    assert profile_path.read_bytes() == before
    assert config_service.load().profile.qualifications.driving_values() == ["C", "CE", "95"]
    assert "95" in profile_path.read_text(encoding="utf-8")


def test_leading_class_is_shared_by_matcher_and_guard():
    """A verbatim entry keeps its text. The class at its start still counts."""
    from core.config import AppConfig, ExtractReview, QualificationsConfig
    from core.cover_guard import confirmed_licence_codes, confirmed_profile_text, screen_cover_letter
    from core.cv_parser import leading_driving_class, read_driving_classes
    from core.matcher import profile_licence_codes, reset_profile_licence_cache

    assert leading_driving_class("Klasse B") == "B"
    assert leading_driving_class("Führerschein Klasse B") == "B"
    assert leading_driving_class("Fahrerlaubnis Klasse B") == "B"
    assert leading_driving_class("Führerscheinklasse B") == "B"
    assert leading_driving_class("Fahrerlaubnisklasse B") == "B"
    assert leading_driving_class("Führerschein: B") == "B"
    assert leading_driving_class("Klasse: B") == "B"
    assert leading_driving_class("CE 95") == "CE"
    assert leading_driving_class("Klasse 3") == ""
    assert leading_driving_class("Klasse B.") == "B"
    assert leading_driving_class("B-Führerschein") == "B"
    assert leading_driving_class("CE-Führerschein") == "CE"
    assert leading_driving_class("C1-Fahrerlaubnis") == "C1"
    for not_a_class in (
        "C++",
        "C#",
        "B.Sc. Informatik",
        "B.A. BWL",
        "T-Systems",
        "A-Levels",
        "D.I.Y. Markt",
    ):
        assert leading_driving_class(not_a_class) == ""
    assert driving_classes_for_display(["Klasse B"]) == ["Klasse B"]
    assert driving_classes_for_display(["Führerschein Klasse B"]) == ["Führerschein Klasse B"]
    assert driving_classes_for_display(["CE 95"]) == ["CE 95"]
    assert driving_classes_for_display(["Klasse 3"]) == ["Klasse 3"]
    assert _licence_points(["Klasse B"]) == 5
    assert _licence_points(["Führerschein Klasse B"]) == 5
    for phrase in (
        "Führerscheinklasse B",
        "Fahrerlaubnisklasse B",
        "Führerschein: B",
        "Klasse: B",
    ):
        assert leading_driving_class(phrase) == "B"
        assert _licence_points([phrase]) == 5
    assert _licence_points(["B-Führerschein"]) == 5
    assert _licence_points(["CE-Führerschein"], "Führerschein Klasse CE erforderlich") == 5
    assert _licence_points(["Klasse 3"]) == 3

    reset_profile_licence_cache()
    ce = QualificationsConfig(driving_license=_sourced_codes(["CE 95"]))
    assert profile_licence_codes(ce) == frozenset({"CE"})
    assert _licence_points(["CE 95"]) == 3

    cfg = _letter_profile(["CE 95"])
    cfg.profile.extract_review = ExtractReview(source="cv", confirmed=True)
    evidence = confirmed_profile_text(cfg)
    assert "CE 95" in evidence
    allowed = screen_cover_letter(
        "Ich besitze den Führerschein CE 95.",
        confirmed_text=evidence,
        confirmed_licences=confirmed_licence_codes(cfg),
        job_text="Lager",
    )
    assert allowed.ok
    plain = AppConfig()
    plain.profile.extract_review = ExtractReview(source="cv", confirmed=True)
    blocked = screen_cover_letter(
        "Ich besitze den Führerschein CE 95.",
        confirmed_text=confirmed_profile_text(plain),
        confirmed_licences=confirmed_licence_codes(plain),
        job_text="Lager",
    )
    assert not blocked.ok
    klasse3 = read_driving_classes(["Klasse 3"])
    assert klasse3.display == ["Klasse 3"]
    assert "B" not in klasse3.evidence


def test_two_digit_suffix_is_not_a_remnant(qapp):
    from core.cover_guard import confirmed_profile_text
    from core.cv_parser import read_driving_classes
    from core.matcher import profile_licence_codes, reset_profile_licence_cache

    reading = read_driving_classes(["C", "CE", "95"])
    assert reading.display == ["C", "CE"]
    assert reading.uncertain == []
    assert reading.recovered is False
    assert reading.evidence == ["C", "CE"]
    assert "95" not in reading.display

    section = QualificationsSection()
    section.load(
        QualificationsConfig(driving_license=_sourced_codes(["C", "CE", "95"]))
    )
    assert section.driving.get_items() == ["C", "CE"]
    assert section.licence_notice.text() == ""

    reset_profile_licence_cache()
    quals = QualificationsConfig(driving_license=_sourced_codes(["C", "CE", "95"]))
    assert profile_licence_codes(quals) == frozenset({"C", "CE"})
    cfg = _letter_profile(["C", "CE", "95"])
    evidence = confirmed_profile_text(cfg)
    assert "C" in evidence.splitlines()
    assert "CE" in evidence.splitlines()


def test_a_classes_are_recovered_without_becoming_evidence():
    from core.config import ExtractReview
    from core.cover_guard import confirmed_licence_codes, confirmed_profile_text, screen_cover_letter
    from core.cv_parser import read_driving_classes

    rebuilt = read_driving_classes(["A", "1"])
    assert rebuilt.display == ["A1"]
    assert rebuilt.uncertain == []
    assert rebuilt.evidence == []
    assert "A" not in rebuilt.display
    assert rebuilt.recovered

    am = read_driving_classes(["A", "M"])
    assert am.display == ["AM"]
    assert am.evidence == []
    assert am.recovered
    assert am.uncertain == []

    mixed = read_driving_classes(["B", "A", "2"])
    assert mixed.display == ["A2", "B"]
    assert mixed.evidence == ["B"]
    assert "A" not in mixed.display
    assert mixed.recovered

    cfg = _letter_profile(["A", "M"])
    cfg.profile.extract_review = ExtractReview(source="cv", confirmed=True)
    evidence = confirmed_profile_text(cfg)
    assert "AM" not in evidence.splitlines()
    assert "A" not in evidence.splitlines()
    blocked = screen_cover_letter(
        "Ich habe den Führerschein AM.",
        confirmed_text=evidence,
        confirmed_licences=confirmed_licence_codes(cfg),
        job_text="Lager",
    )
    assert not blocked.ok

    bare = read_driving_classes(["A", "9"])
    assert bare.uncertain == ["A"]
    assert "A" not in bare.display
    assert bare.evidence == []


def test_uncertain_entries_are_a_licence_and_not_a_hard_exclusion():
    from core.config import AppConfig, ExtractReview, QualificationsConfig
    from core.match_contract import cv_field_status_map, hard_ko_allowed
    from core.matcher import score_job
    from core.models import Job

    stored = ["C", "E", "9", "5"]
    cfg = AppConfig()
    cfg.settings.exclude_on_missing_mandatory = True
    cfg.profile.extract_review = ExtractReview(
        source="cv",
        confirmed=True,
        field_status={"driving_license": "absent"},
    )
    cfg.profile.qualifications = QualificationsConfig(driving_license=_sourced_codes(stored))
    status = cv_field_status_map(cfg.profile.qualifications, cfg.profile.extract_review)
    assert hard_ko_allowed(
        evidenced=True,
        field_name="driving_license",
        field_status=status,
        review=cfg.profile.extract_review,
    )
    asked = Job(
        title="Lager",
        company="Nord",
        remote_type="onsite",
        distance_km=5,
        description="Führerschein erforderlich",
        employment_type="Vollzeit",
    )
    plain = Job(
        title="Lager",
        company="Nord",
        remote_type="onsite",
        distance_km=5,
        description="Teamarbeit im Lager",
        employment_type="Vollzeit",
    )
    result = score_job(asked, cfg)
    assert not result.excluded
    assert result.score - score_job(plain, cfg).score == 3
    assert "Direkt: Führerschein vorhanden" in result.match_reasons
    assert "Direkt: Führerschein Klasse B" not in result.match_reasons

    empty = AppConfig()
    empty.settings.exclude_on_missing_mandatory = True
    empty.profile.extract_review = ExtractReview(
        source="cv",
        confirmed=True,
        field_status={"driving_license": "absent"},
    )
    missing = score_job(asked, empty)
    assert missing.excluded
    assert missing.score == 0


def test_licence_requirement_follows_a_replaced_description():
    from core.config import AppConfig, QualificationsConfig
    from core.matcher import score_job
    from core.models import Job

    job = Job(
        title="Fahrer",
        company="Logistik",
        remote_type="onsite",
        distance_km=5,
        description="",
        employment_type="Vollzeit",
    )
    assert getattr(job, "_licence_requirement", None) is None
    cfg = AppConfig()
    cfg.profile.qualifications = QualificationsConfig(driving_license=_sourced_codes(["B"]))
    first = score_job(job, cfg)
    assert not any("Führerschein" in row for row in first.match_reasons)
    job.description = "Führerschein Klasse B erforderlich"
    second = score_job(job, cfg)
    assert second.score - first.score == 5
    assert "Direkt: Führerschein Klasse B" in second.match_reasons
    assert job._licence_requirement[0] is job.description
    assert job._licence_requirement[1] is job.title
    assert job._licence_requirement[2] == "class_b"


def test_language_levels_are_not_licence_classes():
    from core.config import ExtractReview, LanguageEntry
    from core.cover_guard import confirmed_licence_codes, confirmed_profile_text, screen_cover_letter

    cfg = _letter_profile([])
    cfg.profile.qualifications.languages = [
        LanguageEntry(language="Englisch", level="C1", source="manual")
    ]
    cfg.profile.extract_review = ExtractReview(source="manual", confirmed=True)
    evidence = confirmed_profile_text(cfg)
    level = screen_cover_letter(
        "Meine Englischkenntnisse liegen auf C1-Niveau.",
        confirmed_text=evidence,
        confirmed_licences=confirmed_licence_codes(cfg),
        job_text="Lager",
    )
    assert level.ok
    pair = screen_cover_letter(
        "Ich spreche Englisch (B1) und Spanisch (A2).",
        confirmed_text=evidence,
        confirmed_licences=confirmed_licence_codes(cfg),
        job_text="Lager",
    )
    assert pair.ok
    claim = screen_cover_letter(
        "Ich habe den Führerschein C1.",
        confirmed_text=evidence,
        confirmed_licences=confirmed_licence_codes(cfg),
        job_text="Lager",
    )
    assert not claim.ok


def test_profile_licence_cache_is_one_tuple():
    from core.config import QualificationsConfig
    import core.matcher as matcher
    from core.matcher import profile_licence_codes, reset_profile_licence_cache

    reset_profile_licence_cache()
    quals = QualificationsConfig(driving_license=_sourced_codes(["B", "E"]))
    assert profile_licence_codes(quals) == frozenset({"B", "BE"})
    cached = matcher._profile_licence_cache
    assert isinstance(cached, tuple) and len(cached) == 2
    assert cached[1] == frozenset({"B", "BE"})
    assert not hasattr(matcher, "_profile_licence_key")
    assert not hasattr(matcher, "_profile_licence_codes")


def _decoy_profile(codes: list[str]):
    """Name, skills and history that must not become licence classes."""
    from core.config import AppConfig, EducationEntry, ExperienceEntry, ExtractReview, QualificationsConfig

    cfg = AppConfig()
    cfg.application.first_name = "Mara"
    cfg.application.last_name = "König"
    cfg.profile.extract_review = ExtractReview(source="cv", confirmed=True)
    cfg.profile.qualifications = QualificationsConfig(
        skills=[
            SourcedText(value="C++", source="cv"),
            SourcedText(value="C#", source="cv"),
        ],
        education=[
            EducationEntry(qualification="B.Sc. Informatik", institution="TU Berlin", source="cv"),
            EducationEntry(qualification="A-Levels", source="cv"),
        ],
        work_experience=[
            ExperienceEntry(title="Beraterin", company="T-Systems", source="cv"),
        ],
        driving_license=_sourced_codes(codes),
    )
    return cfg


def test_guard_reads_licence_evidence_not_the_profile_text():
    """C++, degrees and employers are not driving classes."""
    from core.config import ExtractReview
    from core.cover_guard import confirmed_licence_codes, confirmed_profile_text, screen_cover_letter

    bare = _decoy_profile([])
    text = confirmed_profile_text(bare)
    for snippet in ("Mara König", "C++", "C#", "B.Sc. Informatik", "TU Berlin", "T-Systems", "A-Levels"):
        assert snippet in text
    assert confirmed_licence_codes(bare) == set()
    for sentence in (
        "Ich habe die Fahrerlaubnis C und B.",
        "Ich habe die Fahrerlaubnis T.",
        "Ich habe die Fahrerlaubnis A.",
    ):
        screened = screen_cover_letter(
            sentence,
            confirmed_text=text,
            confirmed_licences=confirmed_licence_codes(bare),
            job_text="Lager",
        )
        assert not screened.ok
        assert sentence in screened.violations

    held = _decoy_profile(["B"])
    held_text = confirmed_profile_text(held)
    assert "C++" in held_text
    assert confirmed_licence_codes(held) == {"B"}
    passed = screen_cover_letter(
        "Ich habe die Fahrerlaubnis B.",
        confirmed_text=held_text,
        confirmed_licences=confirmed_licence_codes(held),
        job_text="Lager",
    )
    assert passed.ok
    flagged = screen_cover_letter(
        "Ich habe die Fahrerlaubnis C.",
        confirmed_text=held_text,
        confirmed_licences=confirmed_licence_codes(held),
        job_text="Lager",
    )
    assert not flagged.ok

    unconfirmed = _decoy_profile(["B"])
    unconfirmed.profile.extract_review = ExtractReview(source="cv", confirmed=False)
    assert confirmed_licence_codes(unconfirmed) == set()
    hidden = screen_cover_letter(
        "Ich habe die Fahrerlaubnis B.",
        confirmed_text=confirmed_profile_text(unconfirmed),
        confirmed_licences=confirmed_licence_codes(unconfirmed),
        job_text="Lager",
    )
    assert not hidden.ok


def test_blank_or_fragment_is_a_missing_licence():
    """An empty entry or a lone E is not a licence. Uncertain C still is."""
    from core.config import AppConfig, ExtractReview, QualificationsConfig
    from core.matcher import score_job
    from core.models import Job

    asked = Job(
        title="Lager",
        company="Nord",
        remote_type="onsite",
        distance_km=5,
        description="Führerschein erforderlich",
        employment_type="Vollzeit",
    )
    plain = Job(
        title="Lager",
        company="Nord",
        remote_type="onsite",
        distance_km=5,
        description="Teamarbeit im Lager",
        employment_type="Vollzeit",
    )

    def configured(codes: list[str]) -> AppConfig:
        cfg = AppConfig()
        cfg.settings.exclude_on_missing_mandatory = True
        cfg.profile.extract_review = ExtractReview(
            source="cv",
            confirmed=True,
            field_status={"driving_license": "absent"},
        )
        cfg.profile.qualifications = QualificationsConfig(driving_license=_sourced_codes(codes))
        return cfg

    for stored in ([""], ["E"]):
        assert _licence_points(stored) == 0
        result = score_job(asked, configured(stored))
        assert result.excluded
        assert result.score == 0
        assert "Direkt: Führerschein vorhanden" not in result.match_reasons

    uncertain = score_job(asked, configured(["C", "E", "9", "5"]))
    assert not uncertain.excluded
    assert uncertain.score - score_job(plain, configured(["C", "E", "9", "5"])).score == 3
    assert "Direkt: Führerschein vorhanden" in uncertain.match_reasons
    assert _licence_points(["C", "E", "9", "5"]) == 3


def test_cover_guard_and_matcher_share_class_punctuation():
    """Hyphen, dot and plus mean the same thing in a profile entry and a letter."""
    from core.config import EducationEntry, ExperienceEntry, ExtractReview
    from core.cover_guard import confirmed_licence_codes, confirmed_profile_text, screen_cover_letter
    from core.cv_parser import licence_class_tokens

    assert licence_class_tokens("C++") == []
    assert licence_class_tokens("C#") == []
    assert licence_class_tokens("B.Sc. Informatik") == []
    assert licence_class_tokens("D.I.Y. Markt") == []
    assert licence_class_tokens("T-Systems") == []
    assert licence_class_tokens("Klasse B.") == ["B"]
    assert licence_class_tokens("Ich habe den B-Führerschein.") == ["B"]
    assert licence_class_tokens("Ich habe einen C-Führerschein.") == ["C"]
    assert licence_class_tokens("CE-Führerschein") == ["CE"]
    assert licence_class_tokens("C1-Fahrerlaubnis") == ["C1"]

    held = _letter_profile(["B"])
    held.profile.extract_review = ExtractReview(source="cv", confirmed=True)
    held.profile.qualifications.skills = [SourcedText(value="C++", source="manual")]
    held_text = confirmed_profile_text(held)
    held_codes = confirmed_licence_codes(held)
    assert held_codes == {"B"}
    assert "C++" in held_text
    for sentence in (
        "Ich habe den Führerschein Klasse B und arbeite täglich mit C++.",
        "Ich habe den Führerschein Klasse B, dazu einen B.Sc. Informatik.",
    ):
        screened = screen_cover_letter(
            sentence,
            confirmed_text=held_text,
            confirmed_licences=held_codes,
            job_text="Lager",
        )
        assert screened.ok

    for phrase in ("Führerscheinklasse B", "Führerschein: B"):
        cfg = _letter_profile([phrase])
        cfg.profile.extract_review = ExtractReview(source="cv", confirmed=True)
        assert confirmed_licence_codes(cfg) == {"B"}
        allowed = screen_cover_letter(
            "Ich besitze den Führerschein Klasse B.",
            confirmed_text=confirmed_profile_text(cfg),
            confirmed_licences=confirmed_licence_codes(cfg),
            job_text="Lager",
        )
        assert allowed.ok

    blocked = screen_cover_letter(
        "Ich habe einen C-Führerschein.",
        confirmed_text=held_text,
        confirmed_licences=held_codes,
        job_text="Lager",
    )
    assert not blocked.ok
    owned = screen_cover_letter(
        "Ich habe den B-Führerschein.",
        confirmed_text=held_text,
        confirmed_licences=held_codes,
        job_text="Lager",
    )
    assert owned.ok

    bare = _letter_profile([])
    bare.profile.extract_review = ExtractReview(source="cv", confirmed=True)
    bare.profile.qualifications.skills = [SourcedText(value="C++", source="cv")]
    bare.profile.qualifications.education = [
        EducationEntry(qualification="B.Sc. Informatik", source="cv")
    ]
    bare.profile.qualifications.work_experience = [
        ExperienceEntry(title="Beraterin", company="T-Systems", source="cv")
    ]
    bare_text = confirmed_profile_text(bare)
    assert "C++" in bare_text
    assert "B.Sc. Informatik" in bare_text
    assert "T-Systems" in bare_text
    assert confirmed_licence_codes(bare) == set()
    for sentence in (
        "Ich habe die Fahrerlaubnis C und B.",
        "Ich habe die Fahrerlaubnis T.",
        "Ich habe die Fahrerlaubnis A.",
        "Ich habe den Führerschein Klasse B.",
        "Ich habe den B-Führerschein.",
        "Ich habe einen C-Führerschein.",
    ):
        screened = screen_cover_letter(
            sentence,
            confirmed_text=bare_text,
            confirmed_licences=confirmed_licence_codes(bare),
            job_text="Lager",
        )
        assert not screened.ok


def test_english_licence_sentences_share_the_class_rule():
    """English licence wording uses the same class scan as German."""
    from core.config import ExtractReview
    from core.cover_guard import confirmed_licence_codes, confirmed_profile_text, screen_cover_letter
    from core.cv_parser import leading_driving_class

    assert leading_driving_class("Driving licence: B") == "B"
    assert leading_driving_class("Driving license: B") == "B"
    assert leading_driving_class("Category B") == "B"
    assert leading_driving_class("B-licence") == "B"
    assert leading_driving_class("B-license") == "B"
    assert _licence_points(["Driving licence: B"]) == 5
    assert _licence_points(["Category B"]) == 5

    held = _letter_profile(["B"])
    held.profile.extract_review = ExtractReview(source="cv", confirmed=True)
    text = confirmed_profile_text(held)
    codes = confirmed_licence_codes(held)
    assert codes == {"B"}

    def screen(sentence: str, *, profile_codes=codes, profile_text=text):
        return screen_cover_letter(
            sentence,
            confirmed_text=profile_text,
            confirmed_licences=profile_codes,
            job_text="Lager",
        )

    assert not screen("I hold a category C driving licence.").ok
    assert screen("I hold a class B driver's license.").ok
    assert screen("I hold a class B-licence.").ok
    assert not screen("I hold a category C-license.").ok
    assert screen("I hold a class B driver\u2019s license.").ok
    assert screen("I have experience with C# and C++.").ok
    assert screen("I taught a class of C1 learners.").ok

    german = _letter_profile(["Klasse B"])
    german.profile.extract_review = ExtractReview(source="cv", confirmed=True)
    german_codes = confirmed_licence_codes(german)
    assert german_codes == {"B"}
    german_text = confirmed_profile_text(german)
    assert screen(
        "I hold a category B driving licence.",
        profile_codes=german_codes,
        profile_text=german_text,
    ).ok
    assert not screen(
        "I hold a category C driving licence.",
        profile_codes=german_codes,
        profile_text=german_text,
    ).ok


@pytest.mark.parametrize(
    "sentence",
    (
        "Ich habe einen Lkw-Führerschein.",
        "Ich habe einen Busführerschein.",
        "Ich habe einen Motorradführerschein.",
    ),
)
def test_vehicle_word_without_class_letter_is_flagged(sentence):
    """A vehicle claim needs a matching confirmed driving class."""
    from core.config import ExtractReview
    from core.cover_guard import confirmed_licence_codes, confirmed_profile_text, screen_cover_letter

    cfg = _letter_profile(["B"])
    cfg.profile.extract_review = ExtractReview(source="cv", confirmed=True)
    screened = screen_cover_letter(
        sentence,
        confirmed_text=confirmed_profile_text(cfg),
        confirmed_licences=confirmed_licence_codes(cfg),
        job_text="Lager",
    )
    assert not screened.ok


@pytest.mark.parametrize(
    ("sentence", "licence", "expected"),
    (
        ("Ich habe einen Lkw-Führerschein.", "C1", True),
        ("Ich habe einen Busführerschein.", "D", True),
        ("Ich habe einen Motorradführerschein.", "A2", True),
        ("I hold a truck driving licence.", "B", False),
        ("I hold a truck driving licence.", "CE", True),
        ("I have a bus driver's license.", "B", False),
        ("I have a bus driver's license.", "D1", True),
        ("Für die Stelle ist ein Lkw-Führerschein nötig.", "B", True),
    ),
)
def test_vehicle_claims_respect_confirmed_class_and_person(sentence, licence, expected):
    from core.config import ExtractReview
    from core.cover_guard import confirmed_licence_codes, confirmed_profile_text, screen_cover_letter

    cfg = _letter_profile([licence])
    cfg.profile.extract_review = ExtractReview(source="cv", confirmed=True)
    screened = screen_cover_letter(
        sentence,
        confirmed_text=confirmed_profile_text(cfg),
        confirmed_licences=confirmed_licence_codes(cfg),
        job_text="Lager",
    )
    assert screened.ok is expected


def test_cover_guard_keeps_abbreviations_inside_the_claim():
    """A period in a date or an abbreviation does not hide the class that follows."""
    from core.config import ExtractReview
    from core.cover_guard import confirmed_licence_codes, confirmed_profile_text, screen_cover_letter

    cfg = _letter_profile(["B"])
    cfg.profile.extract_review = ExtractReview(source="cv", confirmed=True)
    text = confirmed_profile_text(cfg)
    codes = confirmed_licence_codes(cfg)

    def screen(sentence: str):
        return screen_cover_letter(
            sentence,
            confirmed_text=text,
            confirmed_licences=codes,
            job_text="Lager",
        )

    for sentence in (
        "Ich habe am 1. März 2015 den Führerschein Klasse C erworben.",
        "Ich habe u. a. den Führerschein Klasse CE.",
        "Ich besitze seit Jan. 2012 die Fahrerlaubnis Klasse CE.",
    ):
        assert not screen(sentence).ok

    two = screen(
        "Ich arbeite in Hamburg. Der Führerschein Klasse C ist in der Anzeige gefordert."
    )
    assert two.ok
    assert two.violations == []


def test_sentence_break_covers_every_guard_check():
    """Abbreviations stay inside employer, degree, number and licence checks."""
    from core.config import ExtractReview
    from core.cover_guard import confirmed_licence_codes, confirmed_profile_text, screen_cover_letter

    bare = _letter_profile(["B"])
    bare.profile.extract_review = ExtractReview(source="cv", confirmed=True)
    text = confirmed_profile_text(bare)
    codes = confirmed_licence_codes(bare)
    assert "Siemens" not in text
    assert "Master" not in text

    def screen(sentence: str, *, profile_text=text, profile_codes=codes, job_text="Lager"):
        return screen_cover_letter(
            sentence,
            confirmed_text=profile_text,
            confirmed_licences=profile_codes,
            job_text=job_text,
        )

    for sentence in (
        "Ich war u. a. bei Siemens als Teamleiter tätig.",
        "Ich habe am 3. Mai 2018 den Master in BWL abgeschlossen.",
        "Ich habe u. a. 12 Jahre in der Disposition gearbeitet.",
        "Ich habe u. a. den Führerschein Klasse CE.",
    ):
        assert not screen(sentence).ok

    station = _with_matching_station(
        _letter_profile(["B"]),
        title="Fahrerin",
        company="Holm Logistik",
        task="Tourenplanung, z. B. für Kühltransporte",
    )
    station.profile.extract_review = ExtractReview(source="cv", confirmed=True)
    station_text = confirmed_profile_text(station)
    assert "Tourenplanung, z. B. für Kühltransporte" in station_text
    kept = screen(
        "In meiner Tätigkeit als Fahrerin bei Holm Logistik habe ich die "
        "Tourenplanung, z. B. für Kühltransporte übernommen.",
        profile_text=station_text,
        profile_codes=confirmed_licence_codes(station),
        job_text="Tourenplanung für Kühltransporte",
    )
    assert kept.ok
    assert kept.violations == []


def _screen_profile_b():
    from core.config import ExtractReview
    from core.cover_guard import confirmed_licence_codes, confirmed_profile_text

    cfg = _letter_profile(["B"])
    cfg.profile.extract_review = ExtractReview(source="cv", confirmed=True)
    return confirmed_profile_text(cfg), confirmed_licence_codes(cfg)


def test_class_at_sentence_end_does_not_hide_behind_the_next_sentence():
    """A class before a new sentence stays a claim. Profile holds only B."""
    from core.cover_guard import screen_cover_letter

    text, codes = _screen_profile_b()
    assert codes == {"B"}

    def screen(sentence: str):
        return screen_cover_letter(
            sentence,
            confirmed_text=text,
            confirmed_licences=codes,
            job_text="Lager",
        )

    for sentence in (
        "Ich besitze den Führerschein Klasse C. Hiermit bewerbe ich mich als Disponent.",
        "Ich besitze den Führerschein Klasse C.\nMit freundlichen Grüßen",
        "Ich besitze den Führerschein Klasse C, gültig bis 2031. Gerne bewerbe ich mich bei Ihnen.",
    ):
        assert not screen(sentence).ok

    from core.cover_guard import _split_claim_sentences

    ordinal = "Ich habe die 3. größten Aufträge und den Führerschein Klasse C."
    assert _split_claim_sentences(ordinal) == [ordinal]


def test_compound_phrases_yield_the_same_classes_in_every_reader():
    """Parser, guard and read_driving_classes share one licence-word list."""
    from core.cover_guard import _licence_codes_in_sentence
    from core.cv_parser import licence_class_tokens, read_driving_classes

    for phrase, expected in (
        ("Führerscheinklasse C", ["C"]),
        ("Klassen B und C", ["B", "C"]),
    ):
        reading = read_driving_classes(phrase)
        assert licence_class_tokens(phrase) == expected
        assert _licence_codes_in_sentence(phrase) == expected
        assert reading.evidence == expected


def test_compound_licence_words_flag_an_unconfirmed_class():
    """Führerscheinklasse, Führerscheinklassen and Klassen name a class."""
    from core.cover_guard import screen_cover_letter

    text, codes = _screen_profile_b()
    assert codes == {"B"}
    for sentence in (
        "Ich besitze die Führerscheinklasse C.",
        "Ich besitze die Führerscheinklassen B und C.",
        "Ich besitze die Klassen B und C.",
    ):
        screened = screen_cover_letter(
            sentence,
            confirmed_text=text,
            confirmed_licences=codes,
            job_text="Lager",
        )
        assert not screened.ok


_FULL_LETTER_TEMPLATE = """{salutation},

hiermit bewerbe ich mich um die {position_phrase} bei {company_bei}.

{experience_sentence}

{skills}

Über die Möglichkeit eines persönlichen Gesprächs freue ich mich.

Mit freundlichen Grüßen
{full_name}
"""


def _compose_class_letter(tmp_path, codes: list[str]):
    """Full letter: salutation, paragraphs and greeting, like the template."""
    from core.config import ExperienceEntry, ExtractReview
    from core.cover_letter import compose_cover_letter, save_cover_letter
    from core.models import Job

    template = tmp_path / "cover_letter.txt"
    template.write_text(_FULL_LETTER_TEMPLATE, encoding="utf-8")
    cfg = _letter_profile(codes)
    cfg.root = tmp_path
    cfg.settings.cover_letter_template = str(template)
    cfg.profile.extract_review = ExtractReview(source="cv", confirmed=True)
    cfg.profile.qualifications.skills = [
        SourcedText(value="Führerschein Klasse C", source="manual")
    ]
    cfg.profile.qualifications.work_experience = [
        ExperienceEntry(
            title="Disponent",
            company="Alpha",
            responsibilities=["Tourenplanung", "Excel"],
            source="manual",
        ),
        ExperienceEntry(
            title="Disponent",
            company="Beta",
            responsibilities=["Disposition", "Excel"],
            source="manual",
        ),
    ]
    job = Job(
        id="brief-klasse-c",
        title="Disponent",
        company="Nordlicht GmbH",
        remote_type="remote",
        description=(
            "Excel, Tourenplanung und Disposition. "
            "Führerschein Klasse C ist erforderlich."
        ),
    )
    letter = compose_cover_letter(job, cfg)
    return cfg, job, letter, save_cover_letter


def test_full_letter_flags_unconfirmed_c_and_saves_nothing(tmp_path):
    """A blank line must not glue the class sentence to the closing sentence."""
    from core.cover_guard import confirmed_licence_codes, confirmed_profile_text, screen_cover_letter

    cfg, job, letter, _save = _compose_class_letter(tmp_path, ["B"])
    assert letter.ok
    assert "Sehr geehrte Damen und Herren" in letter.text
    assert "Mit freundlichen Grüßen" in letter.text
    assert (
        "Praktische Erfahrung habe ich mit Führerschein Klasse C.\n\n"
        "Über die Möglichkeit eines persönlichen Gesprächs freue ich mich."
    ) in letter.text
    screened = screen_cover_letter(
        letter.text,
        confirmed_text=confirmed_profile_text(cfg),
        confirmed_licences=confirmed_licence_codes(cfg),
        job_text=f"{job.title} {job.description}",
        allowed_context=f"{job.title} {job.company}",
    )
    assert not screened.ok
    assert screened.violations == [
        "Praktische Erfahrung habe ich mit Führerschein Klasse C."
    ]
    saved = tmp_path / "cover_letters" / f"{job.id}.txt"
    assert not saved.exists()


def test_full_letter_saves_when_class_c_is_confirmed(tmp_path):
    """Confirmed C passes the same full letter and is written to disk."""
    from core.cover_guard import confirmed_licence_codes, confirmed_profile_text, screen_cover_letter

    cfg, job, letter, save_cover_letter = _compose_class_letter(tmp_path, ["C"])
    assert letter.ok
    screened = screen_cover_letter(
        letter.text,
        confirmed_text=confirmed_profile_text(cfg),
        confirmed_licences=confirmed_licence_codes(cfg),
        job_text=f"{job.title} {job.description}",
        allowed_context=f"{job.title} {job.company}",
    )
    assert screened.ok
    assert screened.violations == []
    path = save_cover_letter(letter.text, tmp_path / "cover_letters" / f"{job.id}.txt")
    assert path.is_file()
    assert path.read_text(encoding="utf-8") == letter.text


def _compose_shipped_letter(tmp_path, codes: list[str], skills: list[str], description: str):
    """Letter from the shipped template file, not from a string built in the test."""
    from core.config import ExperienceEntry, ExtractReview
    from core.cover_letter import (
        DEFAULT_TEMPLATE,
        compose_cover_letter,
        resolve_cover_letter_template,
        save_cover_letter,
    )
    from core.models import Job

    cfg = _letter_profile(codes)
    cfg.root = tmp_path
    cfg.profile.extract_review = ExtractReview(source="cv", confirmed=True)
    cfg.profile.qualifications.skills = [
        SourcedText(value=skill, source="manual") for skill in skills
    ]
    cfg.profile.qualifications.work_experience = [
        ExperienceEntry(
            title="Disponent",
            company="Alpha",
            responsibilities=["Tourenplanung", "Excel"],
            source="manual",
        ),
        ExperienceEntry(
            title="Disponent",
            company="Beta",
            responsibilities=["Disposition", "Excel"],
            source="manual",
        ),
    ]
    shipped = resolve_cover_letter_template(cfg)
    assert shipped is not None
    assert shipped.name == "cover_letter.txt"
    body = shipped.read_text(encoding="utf-8")
    assert "{skills}" in body
    assert "{skills}" in DEFAULT_TEMPLATE
    assert "Gerne erläutere ich Ihnen in einem persönlichen Gespräch, wie ich Ihre Aufgaben mit meiner Erfahrung unterstützen kann." in body
    assert "Gerne erläutere ich Ihnen in einem persönlichen Gespräch, wie ich Ihre Aufgaben mit meiner Erfahrung unterstützen kann." in DEFAULT_TEMPLATE
    job = Job(
        id="brief-vorlage",
        title="Disponent",
        company="Nordlicht GmbH",
        remote_type="remote",
        description=description,
    )
    letter = compose_cover_letter(job, cfg)
    return cfg, job, letter, save_cover_letter


def test_shipped_template_flags_class_c_at_the_end_of_the_skills_line(tmp_path):
    """The delivered template keeps class C as its own skills sentence before the close."""
    from core.cover_guard import confirmed_licence_codes, confirmed_profile_text, screen_cover_letter

    cfg, job, letter, _save = _compose_shipped_letter(
        tmp_path,
        ["B"],
        ["Excel", "Führerschein Klasse C"],
        "Excel, Tourenplanung und Disposition. Führerschein Klasse C ist erforderlich.",
    )
    assert letter.ok
    sentence = "Praktische Erfahrung habe ich mit Führerschein Klasse C."
    closing = "Gerne erläutere ich Ihnen in einem persönlichen Gespräch, wie ich Ihre Aufgaben mit meiner Erfahrung unterstützen kann."
    assert f"{sentence}\n\n{closing}" in letter.text
    screened = screen_cover_letter(
        letter.text,
        confirmed_text=confirmed_profile_text(cfg),
        confirmed_licences=confirmed_licence_codes(cfg),
        job_text=f"{job.title} {job.description}",
        allowed_context=f"{job.title} {job.company}",
    )
    assert not screened.ok
    assert screened.violations == [sentence]
    assert closing not in screened.violations[0]
    saved = tmp_path / "cover_letters" / f"{job.id}.txt"
    assert not saved.exists()


def test_shipped_template_flags_class_c_between_other_skills(tmp_path):
    """Class C stays a flagged skills sentence among Excel and SAP."""
    from core.cover_guard import confirmed_licence_codes, confirmed_profile_text, screen_cover_letter

    cfg, job, letter, _save = _compose_shipped_letter(
        tmp_path,
        ["B"],
        ["Excel", "Führerschein Klasse C", "SAP"],
        "Excel, Tourenplanung, Disposition, Führerschein Klasse C und SAP sind erforderlich.",
    )
    assert letter.ok
    sentence = "Praktische Erfahrung habe ich mit Führerschein Klasse C."
    assert sentence in letter.text
    assert "Praktische Erfahrung habe ich außerdem mit SAP." in letter.text
    screened = screen_cover_letter(
        letter.text,
        confirmed_text=confirmed_profile_text(cfg),
        confirmed_licences=confirmed_licence_codes(cfg),
        job_text=f"{job.title} {job.description}",
        allowed_context=f"{job.title} {job.company}",
    )
    assert not screened.ok
    assert sentence in screened.violations
    assert all("persönlichen Gespräch" not in item for item in screened.violations)


def test_shipped_template_saves_when_class_c_is_confirmed(tmp_path):
    """Confirmed C passes the delivered template and is written to disk."""
    from core.cover_guard import confirmed_licence_codes, confirmed_profile_text, screen_cover_letter

    cfg, job, letter, save_cover_letter = _compose_shipped_letter(
        tmp_path,
        ["C"],
        ["Excel", "Führerschein Klasse C"],
        "Excel, Tourenplanung und Disposition. Führerschein Klasse C ist erforderlich.",
    )
    assert letter.ok
    screened = screen_cover_letter(
        letter.text,
        confirmed_text=confirmed_profile_text(cfg),
        confirmed_licences=confirmed_licence_codes(cfg),
        job_text=f"{job.title} {job.description}",
        allowed_context=f"{job.title} {job.company}",
    )
    assert screened.ok
    assert screened.violations == []
    path = save_cover_letter(letter.text, tmp_path / "cover_letters" / f"{job.id}.txt")
    assert path.is_file()
    assert path.read_text(encoding="utf-8") == letter.text


def test_guard_scans_a_long_abbreviation_letter_quickly():
    """5000 characters of abbreviations must not backtrack in the guard."""
    import time

    from core.cover_guard import screen_cover_letter

    text, codes = _screen_profile_b()
    chunk = "u. a. 1. Kl. a.b.c."
    letter = (chunk * (5000 // len(chunk) + 1))[:5000]
    assert len(letter) == 5000
    assert "u. a." in letter and "1." in letter and "Kl." in letter and "a.b.c." in letter
    start = time.perf_counter()
    screened = screen_cover_letter(
        letter,
        confirmed_text=text,
        confirmed_licences=codes,
        job_text="Lager",
    )
    elapsed = time.perf_counter() - start
    assert isinstance(screened.ok, bool)
    assert elapsed < 0.05


def test_lowercase_licence_code_counts_only_after_a_licence_word():
    """Uppercase codes count anywhere. Lowercase codes count only after a licence word."""
    from core.config import ExtractReview
    from core.cover_guard import confirmed_licence_codes, confirmed_profile_text, screen_cover_letter

    cfg = _letter_profile(["B"])
    cfg.profile.extract_review = ExtractReview(source="cv", confirmed=True)
    screened = screen_cover_letter(
        "Den Führerschein Klasse B besitze ich, am Steuer eines Transporters bin ich täglich.",
        confirmed_text=confirmed_profile_text(cfg),
        confirmed_licences=confirmed_licence_codes(cfg),
        job_text="Lager",
    )
    assert screened.ok
    flagged = screen_cover_letter(
        "Ich habe den Führerschein Klasse c.",
        confirmed_text=confirmed_profile_text(cfg),
        confirmed_licences=confirmed_licence_codes(cfg),
        job_text="Lager",
    )
    assert not flagged.ok


def test_leading_class_allows_article_plural_and_abbreviation():
    """der/die, plurals and Kl. sit in front of the same leading class."""
    from core.config import ExtractReview
    from core.cover_guard import confirmed_licence_codes, confirmed_profile_text, screen_cover_letter
    from core.cv_parser import leading_driving_class, read_driving_classes

    assert leading_driving_class("Führerschein der Klasse B") == "B"
    assert leading_driving_class("Führerschein die Klasse B") == "B"
    assert _licence_points(["Führerschein der Klasse B"]) == 5
    assert leading_driving_class("Fahrerlaubnis der Klasse CE") == "CE"
    assert _licence_points(
        ["Fahrerlaubnis der Klasse CE"],
        "Führerschein Klasse CE erforderlich",
    ) == 5
    assert leading_driving_class("Klassen B") == "B"
    assert _licence_points(["Klassen B"]) == 5
    assert leading_driving_class("Führerscheinklassen B") == "B"
    assert _licence_points(["Führerscheinklassen B"]) == 5
    assert leading_driving_class("Kl. B") == "B"
    assert _licence_points(["Kl. B"]) == 5
    assert leading_driving_class("Klasse 3") == ""

    # The comma split already separates BE. The helper itself still returns the first class.
    assert leading_driving_class("Klassen B, BE") == "B"
    reading = read_driving_classes("Klassen B, BE")
    assert {leading_driving_class(item) for item in reading.evidence} == {"B", "BE"}
    assert _licence_points(["Klassen B, BE"]) == 5

    cfg = _letter_profile(["Führerschein der Klasse B"])
    cfg.profile.extract_review = ExtractReview(source="cv", confirmed=True)
    assert confirmed_licence_codes(cfg) == {"B"}
    allowed = screen_cover_letter(
        "Ich besitze den Führerschein Klasse B.",
        confirmed_text=confirmed_profile_text(cfg),
        confirmed_licences=confirmed_licence_codes(cfg),
        job_text="Lager",
    )
    assert allowed.ok
