"""CV import child must surface stage-specific errors; EXE must ship Docpick."""

from __future__ import annotations

import json
import logging
import sys
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
    assert "psutil" in hidden
    assert "psutil._pswindows" in hidden
    assert "llama_cpp" in mod.ALLOWED_COLLECT_ALL_PACKAGES
    assert mod.datas_entry_allowed(
        "vendor/cv_model/qwen3.5-4b/Qwen3.5-4B-Q4_K_M.gguf",
        "models/qwen3.5-4b",
    )


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


def test_resolve_sidecar_skips_appdata_copy_when_frozen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sidecar next to the EXE must not pay for a 2.7 GB AppData copy."""
    from core import cv_llm_runtime as rt

    exe_dir = tmp_path / "dist"
    sidecar = exe_dir / "models" / "qwen3.5-4b" / rt.CV_MODEL_FILENAME
    sidecar.parent.mkdir(parents=True)
    sidecar.write_bytes(b"sidecar-gguf")
    meipass = tmp_path / "_internal"
    meipass.mkdir()
    calls: list[Path] = []

    monkeypatch.delenv("KARRIEREKRAKE_CV_LLM_MODEL", raising=False)
    monkeypatch.setattr(rt, "is_frozen", lambda: True)
    monkeypatch.setattr(rt, "_meipass_dir", lambda: meipass)
    monkeypatch.setattr(rt, "_exe_dir", lambda: exe_dir)
    monkeypatch.setattr(
        rt,
        "bundled_cv_model_candidates",
        lambda: [sidecar],
    )
    monkeypatch.setattr(
        rt,
        "materialize_bundled_model_to_appdata",
        lambda src: calls.append(src) or None,
    )
    assert rt.resolve_cv_model_path() == sidecar
    assert calls == []


def test_resolve_meipass_still_materializes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from core import cv_llm_runtime as rt

    meipass = tmp_path / "_internal"
    embedded = meipass / "models" / "qwen3.5-4b" / rt.CV_MODEL_FILENAME
    embedded.parent.mkdir(parents=True)
    embedded.write_bytes(b"embedded-gguf")
    durable = tmp_path / "AppData" / "models" / "qwen3.5-4b" / rt.CV_MODEL_FILENAME

    monkeypatch.delenv("KARRIEREKRAKE_CV_LLM_MODEL", raising=False)
    monkeypatch.setattr(rt, "is_frozen", lambda: True)
    monkeypatch.setattr(rt, "_meipass_dir", lambda: meipass)
    monkeypatch.setattr(
        rt,
        "bundled_cv_model_candidates",
        lambda: [embedded],
    )
    monkeypatch.setattr(
        rt,
        "materialize_bundled_model_to_appdata",
        lambda _src: durable,
    )
    durable.parent.mkdir(parents=True)
    durable.write_bytes(b"durable-gguf")
    assert rt.resolve_cv_model_path() == durable


def test_resolve_stale_env_falls_through_to_sidecar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stale KARRIEREKRAKE_CV_LLM_MODEL must not force model_missing."""
    from core import cv_llm_runtime as rt

    exe_dir = tmp_path / "install"
    sidecar = exe_dir / "models" / "qwen3.5-4b" / rt.CV_MODEL_FILENAME
    sidecar.parent.mkdir(parents=True)
    sidecar.write_bytes(b"sidecar-gguf")
    monkeypatch.setenv("KARRIEREKRAKE_CV_LLM_MODEL", str(tmp_path / "gone.gguf"))
    monkeypatch.setattr(rt, "is_frozen", lambda: True)
    monkeypatch.setattr(rt, "_meipass_dir", lambda: None)
    monkeypatch.setattr(rt, "_exe_dir", lambda: exe_dir)
    monkeypatch.setattr(rt, "bundled_cv_model_candidates", lambda: [sidecar])
    assert rt.resolve_cv_model_path() == sidecar


def test_package_windows_release_requires_sidecar(tmp_path: Path) -> None:
    from scripts import package_windows_release as pkg

    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "Karrierekrake.exe").write_bytes(b"MZ-fake")
    with pytest.raises(SystemExit, match="sidecar missing"):
        pkg.require_release_layout(dist)


def test_package_windows_release_stages_install(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts import package_windows_release as pkg

    dist = tmp_path / "dist"
    gguf = dist / "models" / "qwen3.5-4b" / "Qwen3.5-4B-Q4_K_M.gguf"
    gguf.parent.mkdir(parents=True)
    # Size gate is 1GB — stub the check for unit speed.
    gguf.write_bytes(b"x" * 64)
    (dist / "Karrierekrake.exe").write_bytes(b"MZ-fake")
    monkeypatch.setattr(pkg, "_sha256", lambda _p: pkg.CV_MODEL_SHA256)
    monkeypatch.setattr(
        pkg,
        "require_release_layout",
        lambda d: d / "models" / "qwen3.5-4b" / "Qwen3.5-4B-Q4_K_M.gguf",
    )
    install = tmp_path / "install"
    exe = pkg.stage_install_dir(dist, install)
    assert exe.is_file()
    assert (install / "models" / "qwen3.5-4b" / "Qwen3.5-4B-Q4_K_M.gguf").is_file()
    assert (install / "INSTALL.txt").is_file()


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


def test_sentinel_stays_out_of_parse_error_and_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """CV text and a username path never enter the result, the log, or the pipe."""
    sentinel = "KK_SENTINEL_7f3a"
    user = "KKSentinelUser"
    cv = tmp_path / "Users" / user / "cv.txt"
    cv.parent.mkdir(parents=True)
    cv.write_text(sentinel, encoding="utf-8")
    phase = tmp_path / "phase.jsonl"
    monkeypatch.setenv("KARRIEREKRAKE_CV_PHASE_EVENTS", str(phase))
    detail_keys = {
        "exception_type",
        "reason",
        "stage",
        "prompt_tokens",
        "tokens_done",
        "max_tokens",
        "n_ctx",
        "elapsed_s",
        "timeout_s",
        "peak_bytes",
        "budget_bytes",
        "counter",
    }

    def _assert_clean(out: Path) -> None:
        text = out.read_text(encoding="utf-8")
        if phase.is_file():
            text += phase.read_text(encoding="utf-8")
        text += caplog.text
        assert sentinel not in text
        assert user not in text
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert set(payload["detail"]) <= detail_keys
        assert "message" in payload

    def parse_fail(*_a, **_k):
        raise CvImportError("llm_extract_failed", f"{sentinel} path={cv}")

    def time_fail(*_a, **_k):
        raise CvImportError("llm_timeout", f"{sentinel} path={cv}")

    out_parse = tmp_path / "parse.json"
    monkeypatch.setattr("core.cv_parser.import_cv", parse_fail)
    with caplog.at_level(logging.DEBUG):
        assert run_child(["--cv", str(cv), "--out", str(out_parse)]) == 1
    _assert_clean(out_parse)
    assert json.loads(out_parse.read_text(encoding="utf-8"))["kind"] == "llm_extract_failed"

    caplog.clear()
    phase.write_text("", encoding="utf-8")
    out_time = tmp_path / "time.json"
    monkeypatch.setattr("core.cv_parser.import_cv", time_fail)
    with caplog.at_level(logging.DEBUG):
        assert run_child(["--cv", str(cv), "--out", str(out_time)]) == 1
    _assert_clean(out_time)
    assert json.loads(out_time.read_text(encoding="utf-8"))["kind"] == "llm_timeout"


def test_peak_detail_carries_bytes_and_drops_free_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sentinel = "KK_SENTINEL_7f3a"
    cv = tmp_path / "cv.txt"
    cv.write_text("x", encoding="utf-8")
    out = tmp_path / "peak.json"

    def boom(*_a, **_k):
        raise CvImportError(
            "peak_rss_exceeded",
            sentinel,
            detail={
                "stage": "after_load",
                "peak_bytes": 4_000_000_000,
                "budget_bytes": 3_132_727_552,
                "counter": "PeakJobMemoryUsed",
                "leak": sentinel,
            },
        )

    monkeypatch.setattr("core.cv_parser.import_cv", boom)
    assert run_child(["--cv", str(cv), "--out", str(out)]) == 3
    text = out.read_text(encoding="utf-8")
    assert sentinel not in text
    payload = json.loads(text)
    assert payload["detail"]["stage"] == "after_load"
    assert payload["detail"]["peak_bytes"] == 4_000_000_000
    assert payload["detail"]["budget_bytes"] == 3_132_727_552
    assert payload["detail"]["counter"] == "PeakJobMemoryUsed"
    assert "leak" not in payload["detail"]


def test_known_token_counts_reach_detail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from core.cv_docpick_import import note_import_progress

    cv = tmp_path / "cv.txt"
    cv.write_text("x", encoding="utf-8")
    out = tmp_path / "time.json"

    def boom(*_a, **_k):
        note_import_progress(
            stage="before_generation",
            prompt_tokens=1763,
            tokens_done=4,
            max_tokens=804,
            n_ctx=4096,
        )
        raise CvImportError("llm_timeout", "llm_timeout")

    monkeypatch.setattr("core.cv_parser.import_cv", boom)
    assert run_child(["--cv", str(cv), "--out", str(out)]) == 1
    detail = json.loads(out.read_text(encoding="utf-8"))["detail"]
    assert detail["stage"] == "before_generation"
    assert detail["prompt_tokens"] == 1763
    assert detail["tokens_done"] == 4
    assert detail["max_tokens"] == 804
    assert detail["n_ctx"] == 4096
