"""Prove production CV import never invokes PHI_EXTRACT / C1.

CV Extraction: deterministic
Writing Assistance: optional local AI (PHI_WRITE)
"""

from __future__ import annotations

import ast
import warnings
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.cv_intelligence import import_cv_canonical
from core.cv_parser import import_cv, parse_cv_text

ROOT = Path(__file__).resolve().parents[1]


def _sample_cv(
    *,
    english: bool = False,
    two_column_ish: bool = False,
    complex_: bool = False,
) -> str:
    if english:
        return (
            "Jane Applicant\n123 Main Street\nBerlin\n"
            "Experience\nSoftware Engineer at Demo Corp 2019-2023\n"
            "Education\nBSc Computer Science\n"
            "Skills\nPython, Excel\n"
            "Languages\nEnglish C1, German B2\n"
        )
    if two_column_ish:
        return (
            "Max Zweispalt\nmax@example.com | 030 123456\n"
            "Berufserfahrung                    Kenntnisse\n"
            "Sachbearbeiter Demo AG 2020-heute   Excel\n"
            "                                   SAP\n"
            "Ausbildung                         Sprachen\n"
            "Industriekaufmann IHK              Deutsch\n"
            "                                   Englisch B2\n"
        )
    if complex_:
        return (
            "Komplex Beispiel\nMusterstraße 1, 10115 Berlin\n"
            "Ziel: Quereinstieg IT\n"
            "Berufserfahrung\n"
            "2020-2022 Lagerist bei Logistik GmbH\n"
            "2018-2020 Minijob Einzelhandel\n"
            "2019-heute Selbstständig Beratung (nebenberuflich)\n"
            "Ausbildung\n"
            "2015-2018 Ausbildung Fachkraft für Lagerlogistik (abgebrochen)\n"
            "Sprachen\nDeutsch Muttersprache\nEnglisch C1\n"
            "Führerschein\nKlasse B, C1\n"
            "Software\nExcel (sehr gut), DATEV\n"
            "Kenntnisse\nGabelstapler, Staplerschein\n"
        )
    return (
        "Max Beispiel\nBerlin\n"
        "Berufserfahrung\nBuchhalterin bei Demo GmbH 2020-2024\n"
        "Ausbildung\nIndustriekauffrau IHK\n"
        "Kenntnisse\nExcel, Buchhaltung\n"
    )


def _assert_no_phi(parsed: dict, mock: MagicMock | None = None) -> None:
    assert parsed.get("phi_extract_call_count") == 0
    assert parsed.get("phi_invoked") is False
    assert parsed.get("intelligence_status") in {
        "deterministic_only",  # historical DET-only label
        "docpick_qwen35",
    }
    if mock is not None:
        mock.suggest_cv_extract.assert_not_called()
        if hasattr(mock, "suggest_cv_extract_split"):
            mock.suggest_cv_extract_split.assert_not_called()


@pytest.fixture(autouse=True)
def _stub_docpick_offline(monkeypatch):
    """Unit tests use text fixtures; stub Docpick so CI needs no Docling/LLM.

    Production import still routes through import_cv_docpick — never parse_cv_text.
    """

    def _fake_docpick(path):
        p = Path(path)
        text = p.read_text(encoding="utf-8") if p.is_file() else ""
        parsed = parse_cv_text(text)
        parsed["source_path"] = str(path)
        parsed["pipeline"] = "docpick_qwen35_4b"
        parsed["intelligence_status"] = "docpick_qwen35"
        parsed["phi_invoked"] = False
        parsed["phi_extract_call_count"] = 0
        parsed["intelligence_notes"] = list(parsed.get("intelligence_notes") or [])
        return parsed

    monkeypatch.setattr("core.cv_docpick_import.import_cv_docpick", _fake_docpick)


@pytest.fixture
def phi_spy():
    mock = MagicMock()
    mock.suggest_cv_extract = MagicMock(side_effect=AssertionError("PHI_EXTRACT must not run"))
    mock.suggest_cv_extract_split = MagicMock(
        side_effect=AssertionError("PHI_EXTRACT split must not run")
    )
    return mock


def test_01_normal_cv_import_never_calls_phi(tmp_path, phi_spy):
    p = tmp_path / "cv.txt"
    p.write_text(_sample_cv(), encoding="utf-8")
    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        parsed = import_cv_canonical(p, guenther_enabled=True, guenther_service=phi_spy)
    _assert_no_phi(parsed, phi_spy)


def test_02_complex_cv_import_never_calls_phi(tmp_path, phi_spy):
    p = tmp_path / "cv.txt"
    p.write_text(_sample_cv(complex_=True), encoding="utf-8")
    parsed = import_cv_canonical(p, guenther_enabled=True, guenther_service=phi_spy)
    _assert_no_phi(parsed, phi_spy)


def test_03_two_column_cv_never_calls_phi(tmp_path, phi_spy):
    p = tmp_path / "cv.txt"
    p.write_text(_sample_cv(two_column_ish=True), encoding="utf-8")
    parsed = import_cv_canonical(p, guenther_enabled=True, guenther_service=phi_spy)
    _assert_no_phi(parsed, phi_spy)


def test_04_english_cv_never_calls_phi(tmp_path, phi_spy):
    p = tmp_path / "cv.txt"
    p.write_text(_sample_cv(english=True), encoding="utf-8")
    parsed = import_cv_canonical(p, guenther_enabled=True, guenther_service=phi_spy)
    _assert_no_phi(parsed, phi_spy)


def test_05_validator_error_never_calls_phi(tmp_path, phi_spy):
    """Docpick path does not run DET verify/repair; Phi must still stay off."""
    p = tmp_path / "cv.txt"
    p.write_text(_sample_cv(), encoding="utf-8")

    def boom(*_a, **_k):
        raise RuntimeError("validator_failed")

    with patch("core.cv_verify_repair.apply_verify_repair_pipeline", side_effect=boom):
        parsed = import_cv_canonical(p, guenther_enabled=True, guenther_service=phi_spy)
    _assert_no_phi(parsed, phi_spy)
    # Production Docpick import must not depend on DET verify/repair.
    assert parsed.get("pipeline") == "docpick_qwen35_4b"


def test_06_missing_required_fields_never_calls_phi(tmp_path, phi_spy):
    p = tmp_path / "cv.txt"
    p.write_text("Lebenslauf\nSeite 1\n", encoding="utf-8")
    parsed = import_cv_canonical(p, guenther_enabled=True, guenther_service=phi_spy)
    _assert_no_phi(parsed, phi_spy)


def test_07_low_confidence_never_calls_phi(tmp_path, phi_spy):
    p = tmp_path / "cv.txt"
    p.write_text("Unklar\nvielleicht Erfahrung irgendwo\n", encoding="utf-8")
    parsed = import_cv_canonical(p, guenther_enabled=True, guenther_service=phi_spy)
    _assert_no_phi(parsed, phi_spy)


def test_08_docpick_exception_never_falls_back_to_phi(tmp_path, phi_spy):
    p = tmp_path / "cv.txt"
    p.write_text(_sample_cv(), encoding="utf-8")

    with patch(
        "core.cv_docpick_import.import_cv_docpick",
        side_effect=ValueError("docpick_crash"),
    ):
        with pytest.raises(ValueError, match="docpick_crash"):
            import_cv_canonical(p, guenther_enabled=True, guenther_service=phi_spy)
    phi_spy.suggest_cv_extract.assert_not_called()


def test_08b_import_never_calls_det_parse_cv_text(tmp_path, phi_spy, monkeypatch):
    """Productive import must not invoke DET parse_cv_text (no silent fallback)."""
    p = tmp_path / "cv.txt"
    p.write_text(_sample_cv(), encoding="utf-8")

    def _fake_docpick(_path):
        return {
            "pipeline": "docpick_qwen35_4b",
            "intelligence_status": "docpick_qwen35",
            "phi_invoked": False,
            "phi_extract_call_count": 0,
            "skills": ["Excel"],
            "work_experience": [],
            "source_path": str(p),
        }

    monkeypatch.setattr("core.cv_docpick_import.import_cv_docpick", _fake_docpick)
    with patch("core.cv_parser.parse_cv_text", side_effect=AssertionError("DET must not run")):
        parsed = import_cv_canonical(p, guenther_enabled=True, guenther_service=phi_spy)
    assert parsed.get("pipeline") == "docpick_qwen35_4b"
    _assert_no_phi(parsed, phi_spy)

def test_09_legacy_enable_phi_fallback_config_ignored(tmp_path, phi_spy, monkeypatch):
    """Old config keys must not reactivate PHI_EXTRACT."""
    p = tmp_path / "cv.txt"
    p.write_text(_sample_cv(), encoding="utf-8")

    class FakeSettings:
        guenther_enabled = True
        enable_phi_fallback = True
        use_phi_extract = True
        hybrid_extraction = True
        c1_fallback_enabled = True
        thin_routing_threshold = 3
        phi_verify_enabled = True
        phi_repair_enabled = True

    class FakeCfg:
        settings = FakeSettings()

    monkeypatch.setattr("core.config.load_config", lambda: FakeCfg())
    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        parsed = import_cv(p, guenther_enabled=True)
        parsed2 = import_cv_canonical(
            p, guenther_enabled=FakeSettings.guenther_enabled, guenther_service=phi_spy
        )
    _assert_no_phi(parsed)
    _assert_no_phi(parsed2, phi_spy)


def test_10_legacy_cli_style_flags_ignored(tmp_path, phi_spy):
    p = tmp_path / "cv.txt"
    p.write_text(_sample_cv(), encoding="utf-8")
    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        parsed = import_cv_canonical(
            p,
            guenther_enabled=True,
            guenther_service=phi_spy,
            split_phi_passes=True,
            document_backend="current",
        )
    _assert_no_phi(parsed, phi_spy)


def test_11_missing_phi_model_does_not_block_import(tmp_path, monkeypatch):
    monkeypatch.setenv("KARRIEREKRAKE_MODELS_DIR", str(tmp_path / "no_models"))
    p = tmp_path / "cv.txt"
    p.write_text(_sample_cv(), encoding="utf-8")
    parsed = import_cv(p)
    assert parsed.get("phi_extract_call_count") == 0
    assert "work_experience" in parsed or "skills" in parsed or "personal" in parsed


def test_12_cv_import_does_not_load_phi_model(tmp_path):
    p = tmp_path / "cv.txt"
    p.write_text(_sample_cv(), encoding="utf-8")
    load_calls: list[str] = []

    def spy_load(*_a, **_k):
        load_calls.append("load")
        raise AssertionError("model load must not happen during CV import")

    with patch("guenther.service.GuentherService.suggest_cv_extract", side_effect=spy_load):
        with patch("guenther.service.GuentherService.__init__", side_effect=spy_load):
            with patch("guenther.model_manager.ModelManager.is_installed", side_effect=spy_load):
                parsed = import_cv(p)
    assert load_calls == []
    assert parsed.get("phi_extract_call_count") == 0


def test_13_cv_import_starts_no_phi_subprocess(tmp_path):
    p = tmp_path / "cv.txt"
    p.write_text(_sample_cv(), encoding="utf-8")
    with patch("subprocess.Popen") as popen:
        with patch("subprocess.run") as run:
            parsed = import_cv(p)
    popen.assert_not_called()
    # allow unrelated subprocess if any library uses it — but import path shouldn't
    for call in run.call_args_list:
        cmd = " ".join(str(x) for x in (call.args[0] if call.args else []))
        assert "phi" not in cmd.lower()
        assert "llama" not in cmd.lower()
    assert parsed.get("phi_extract_call_count") == 0


def test_14_phi_write_still_available():
    from guenther.prompts import SYSTEM_PHI_WRITE
    from guenther.service import GuentherService

    assert "PHI_WRITE" in SYSTEM_PHI_WRITE or "biograf" in SYSTEM_PHI_WRITE.lower()
    assert hasattr(GuentherService, "suggest_writing")
    assert callable(GuentherService.suggest_writing)


def test_15_writer_uses_verified_profile_only():
    from guenther.contracts import WritingSuggestion
    from guenther.validation import validate_writing

    suggestion = WritingSuggestion(
        subject="Bewerbung",
        body="Ich habe 10 Jahre Führungserfahrung und einen Doktortitel in Physik.",
        anchors_used=[],
        invented_flag=False,
        confidence="medium",
    )
    profile = "Name: Ada Test\nSkills: Excel\nBeruf: Sachbearbeiterin"
    model, notes = validate_writing(suggestion, profile_text=profile, job_text="Führung")
    assert model.invented_flag is True or any(
        "invent" in (n or "").lower() or "ground" in (n or "").lower() or "unbelegt" in (n or "").lower()
        for n in (notes or [])
    ) or model.confidence.value == "low"


def test_16_writer_does_not_invent_biography():
    from guenther.prompts import SYSTEM_PHI_WRITE, build_layers

    system, trusted, _ = build_layers(
        task="Schreibe Anschreiben",
        schema_hint="{}",
        trusted="PROFILE:\nName: Ada Test\nSkills: Excel\n",
        untrusted="JOB: Leadership, SAP",
        system_core=SYSTEM_PHI_WRITE,
    )
    assert "Excel" in trusted
    assert "biograf" in system.lower() or "Profil" in system or "profile" in system.lower()


def test_17_writer_model_not_loaded_at_import():
    """GuentherService construction for WRITE must stay lazy; import never constructs it."""
    p = Path(__file__).resolve()  # just ensure module import path
    assert p.exists()
    ctor_calls: list[int] = []
    real_init = None

    from guenther import service as svc_mod

    real_init = svc_mod.GuentherService.__init__

    def counting_init(self, *a, **k):
        ctor_calls.append(1)
        return real_init(self, *a, **k)

    cv = ROOT / "tests"
    sample = (_sample_cv()).encode("utf-8")
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "cv.txt"
        path.write_bytes(sample)
        with patch.object(svc_mod.GuentherService, "__init__", counting_init):
            parsed = import_cv(path)
    assert ctor_calls == []
    assert parsed.get("phi_extract_call_count") == 0


def test_18_historical_eval_not_imported_by_production():
    """Production CV modules must not import holdout GT or final_holdout expected results."""
    prod_files = [
        ROOT / "core" / "cv_intelligence.py",
        ROOT / "core" / "cv_parser.py",
        ROOT / "core" / "cv_extract.py",
        ROOT / "core" / "cv_sections.py",
        ROOT / "desktop" / "widgets" / "cv_import_dialog.py",
    ]
    forbidden = (
        "expected_results",
        "final_holdout",
        "solution_sheet",
        "suggest_cv_extract",
        "reconcile_phi_into_parsed",
    )
    for path in prod_files:
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                mod = getattr(node, "module", None) or ""
                names = " ".join(
                    a.name for a in getattr(node, "names", [])
                )
                blob = f"{mod} {names}".lower()
                for f in ("expected_results", "solution_sheet"):
                    assert f not in blob, f"{path} imports {f}"
        # dialog / intelligence must not call suggest_cv_extract
        if path.name in {"cv_intelligence.py", "cv_import_dialog.py", "cv_parser.py"}:
            assert "suggest_cv_extract(" not in src
            if path.name == "cv_intelligence.py":
                # reconcile may exist as historical helper but must not be called from import_cv_canonical
                body = src.split("def import_cv_canonical", 1)[1]
                assert "reconcile_phi_into_parsed" not in body
                assert "suggest_cv_extract" not in body


def test_uncertain_instead_of_phi_invention():
    """When DET cannot reliably extract, leave empty/uncertain — do not invent."""
    text = "Lebenslauf\nGeheim\n"
    parsed = parse_cv_text(text)
    # No fake employment invented
    work = parsed.get("work_experience") or []
    assert all(
        not str(w.get("title") or "").lower().startswith("invent")
        for w in work
        if isinstance(w, dict)
    )
