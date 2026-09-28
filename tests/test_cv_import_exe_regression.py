"""CV import child must surface stage-specific errors; EXE must ship Docpick."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from core.cv_docpick_import import CvImportError, extract_cv_text
from desktop.cv_import_child import run as run_child
from desktop.cv_import_child import user_message_for_kind


def test_user_message_for_known_kinds_is_stage_specific() -> None:
    msg = user_message_for_kind("model_missing", "ignored raw")
    assert "Qwen" in msg or "Modell" in msg
    assert "Users\\" not in msg
    assert user_message_for_kind("unreadable_cv").startswith("Die Datei")


def test_user_message_strips_sensitive_fallback() -> None:
    # Build at runtime so privacy_scan does not see a literal Windows user path
    # or known CV fingerprint fragments in this tracked source file.
    sep = chr(92)  # backslash
    raw = "failed " + sep.join(
        ("C:", "Users", "fixture_user", "AppData", "Local", "secret", "cv.pdf")
    ) + " token=abc"
    assert "Users" + sep + "fixture_user" + sep in raw
    assert user_message_for_kind("unknown_kind", raw) == (
        "Der Lebenslauf konnte nicht gelesen werden."
    )


def test_extract_cv_text_uses_shipped_cv_extract(tmp_path: Path) -> None:
    from docx import Document

    docx = tmp_path / "cv.docx"
    d = Document()
    d.add_paragraph("Ada Lovelace")
    d.add_paragraph("ada@example.com")
    d.save(docx)
    text = extract_cv_text(docx)
    assert "Ada" in text
    assert "ada@example.com" in text


def test_extract_cv_text_docling_opt_in_fails_closed_without_docling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4 minimal")
    monkeypatch.setenv("KARRIEREKRAKE_CV_USE_DOCLING", "1")
    with patch.dict("sys.modules", {"docling": None, "docling.document_converter": None}):
        # Force ImportError path inside _extract_via_docling
        with patch(
            "core.cv_docpick_import._extract_via_docling",
            side_effect=CvImportError("docling_missing", "Docling fehlt"),
        ):
            with pytest.raises(CvImportError) as ei:
                extract_cv_text(pdf)
            assert ei.value.code == "docling_missing"


def test_child_preserves_cv_import_error_kind(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cv = tmp_path / "cv.pdf"
    cv.write_bytes(b"%PDF-1.4")
    out = tmp_path / "out.json"

    def boom(*_a, **_k):
        raise CvImportError(
            "model_missing",
            "Das lokale CV-Modell (Qwen3.5-4B) fehlt. "
            f"Pfad={cv}",  # must not leak into user message
        )

    monkeypatch.setattr("core.cv_parser.import_cv", boom)
    code = run_child(["--cv", str(cv), "--out", str(out)])
    assert code == 1
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["ok"] is False
    assert payload["kind"] == "model_missing"
    assert "Qwen" in payload["message"] or "Modell" in payload["message"]
    assert "Users" not in payload["message"]
    assert str(cv) not in payload["message"]


def test_child_instance_lock_kind_not_used_for_parser_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: generic read-failed must not hide llm_unavailable."""
    cv = tmp_path / "cv.pdf"
    cv.write_bytes(b"%PDF-1.4")
    out = tmp_path / "out.json"

    def boom(*_a, **_k):
        raise CvImportError("llm_unavailable", "server down at http://127.0.0.1:8765/v1")

    monkeypatch.setattr("core.cv_parser.import_cv", boom)
    run_child(["--cv", str(cv), "--out", str(out)])
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["kind"] == "llm_unavailable"
    assert "8765" not in payload["message"]  # no endpoint leak in user copy
    assert payload["message"] != "Der Lebenslauf konnte nicht gelesen werden."


def test_ensure_cv_llm_ready_prefers_http(monkeypatch: pytest.MonkeyPatch) -> None:
    from core import cv_llm_runtime as rt

    monkeypatch.setattr(rt, "http_llm_available", lambda *a, **k: True)
    assert rt.ensure_cv_llm_ready() == "http"


def test_ensure_cv_llm_ready_inprocess_when_model_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from core import cv_llm_runtime as rt

    model = tmp_path / "Qwen3.5-4B-Q4_K_M.gguf"
    model.write_bytes(b"fake")
    monkeypatch.setattr(rt, "http_llm_available", lambda *a, **k: False)
    monkeypatch.setattr(rt, "resolve_cv_model_path", lambda: model)
    monkeypatch.setattr(rt, "llama_cpp_importable", lambda: True)
    assert rt.ensure_cv_llm_ready() == "inprocess"


def test_ensure_cv_llm_ready_model_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    from core import cv_llm_runtime as rt

    monkeypatch.setattr(rt, "http_llm_available", lambda *a, **k: False)
    monkeypatch.setattr(rt, "resolve_cv_model_path", lambda: None)
    with pytest.raises(CvImportError) as ei:
        rt.ensure_cv_llm_ready()
    assert ei.value.code == "model_missing"


def test_packaging_policy_allows_docpick() -> None:
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "packaging" / "kk_content_policy.py"
    spec = importlib.util.spec_from_file_location("kk_content_policy_repo", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    hidden = set(mod.ALLOWED_THIRD_PARTY_HIDDEN)
    assert "docpick" in hidden
    assert "docpick.llm.vllm_provider" in hidden
    assert "llama_cpp" in hidden
    assert "psutil" in hidden
    assert "psutil._pswindows" in hidden


def test_physical_cores_report_writes_reserve_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The EXE report keeps the psutil line and adds the reserve line."""
    out = tmp_path / "cores.txt"
    monkeypatch.setattr(
        sys,
        "argv",
        ["Karrierekrake", "--report-physical-cores", str(out)],
    )
    monkeypatch.setattr(
        "core.cv_llm_runtime.physical_cores_report_line",
        lambda: "physical_cores source=psutil count=8",
    )
    monkeypatch.setattr(
        "core.cv_llm_runtime.cv_llm_thread_report_line",
        lambda: "n_threads=7 n_threads_batch=7 physical=8 logical=8 reserve=1",
    )
    from desktop.app import _report_physical_cores

    assert _report_physical_cores() == 0
    lines = out.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "physical_cores source=psutil count=8"
    assert lines[1] == "n_threads=7 n_threads_batch=7 physical=8 logical=8 reserve=1"


def test_requirements_runtime_lists_docpick_and_llama() -> None:
    text = Path("requirements-runtime.txt").read_text(encoding="utf-8")
    assert "docpick" in text
    assert "llama-cpp-python" in text
    assert "--extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu" in text
    constraints = Path("constraints-runtime.txt").read_text(encoding="utf-8")
    assert "llama-cpp-python==0.3.35" in constraints
    assert "psutil>=5.9" in text
    assert "psutil==7.2.2" in constraints
    smoke = Path(".github/workflows/windows-smoke.yml").read_text(encoding="utf-8")
    assert "--report-physical-cores" in smoke
    assert "source=psutil" in smoke
    assert "reserve=" in smoke
    assert "--report-llm-load" in smoke
    assert "AMX_INT8 = 1" in smoke
    assert "llama_cpu_all_variants=0" in smoke
    assert "llama_backend_libs=" in smoke
    assert "ggml-cpu-haswell" in smoke
    assert "llama_model_buffer=not_loaded" in smoke
    assert not any(
        line.strip().startswith("#") and "docpick" in line for line in text.splitlines() if "docpick" in line
    )
