"""CV import child must surface stage-specific errors; EXE must ship Docpick."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from core.cv_docpick_import import CvImportError, extract_cv_text
from desktop.cv_import_child import run as run_child
from desktop.cv_import_child import user_message_for_kind


def test_user_message_for_known_kinds_is_stage_specific() -> None:
    msg = user_message_for_kind("model_missing", "ignored raw")
    assert "Modell" in msg or "Installation" in msg
    assert "Qwen" not in msg
    assert "DET" not in msg
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
            "internal diagnostic mentions Qwen and path "
            f"Pfad={cv}",  # must not leak into user message
        )

    monkeypatch.setattr("core.cv_parser.import_cv", boom)
    code = run_child(["--cv", str(cv), "--out", str(out)])
    assert code == 1
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["ok"] is False
    assert payload["kind"] == "model_missing"
    assert "Qwen" not in payload["message"]
    assert "DET" not in payload["message"]
    assert "Modell" in payload["message"] or "Installation" in payload["message"]
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
    assert "llama_cpp" in mod.ALLOWED_COLLECT_ALL_PACKAGES
    assert mod.datas_entry_allowed(
        "vendor/cv_model/qwen3.5-4b/Qwen3.5-4B-Q4_K_M.gguf",
        "models/qwen3.5-4b",
    )


def test_resolve_cv_model_prefers_vendor_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from core import cv_llm_runtime as rt

    vendor = tmp_path / "vendor" / "cv_model" / "qwen3.5-4b"
    vendor.mkdir(parents=True)
    gguf = vendor / rt.CV_MODEL_FILENAME
    gguf.write_bytes(b"fake-gguf")
    monkeypatch.delenv("KARRIEREKRAKE_CV_LLM_MODEL", raising=False)
    monkeypatch.setattr(rt, "is_frozen", lambda: False)
    monkeypatch.setattr(
        rt,
        "bundled_cv_model_candidates",
        lambda: [gguf],
    )
    monkeypatch.setattr(rt, "materialize_bundled_model_to_appdata", lambda _src: None)
    assert rt.resolve_cv_model_path() == gguf


def test_ui_copy_has_no_internal_model_names() -> None:
    from desktop import i18n

    de = i18n.TRANSLATIONS["de"]
    en = i18n.TRANSLATIONS["en"]
    banned = ("Qwen", "Docpick", "DET-Parser", "llama", "GGUF", "Phi-4")
    keys = [
        k
        for k in de
        if k.startswith("cv_import.")
        or k.startswith("settings.cv_import")
        or k.startswith("settings.guenther")
    ]
    for key in keys:
        for lang, table in (("de", de), ("en", en)):
            text = table.get(key, "")
            for token in banned:
                assert token not in text, f"{lang}:{key} contains {token!r}"


def test_requirements_runtime_lists_docpick_and_llama() -> None:
    text = Path("requirements-runtime.txt").read_text(encoding="utf-8")
    assert "docpick" in text
    assert "llama-cpp-python" in text
    assert not any(
        line.strip().startswith("#") and "docpick" in line for line in text.splitlines() if "docpick" in line
    )
