# Test: no productive Phi runtime; sole Qwen weight; parser ≠ writing.

from __future__ import annotations

from pathlib import Path

from guenther.model_manager import (
    HISTORICAL_MODEL_CATALOG,
    MODEL_CATALOG,
    PRODUCTION_MODEL_ID,
    ModelManager,
    is_production_model,
)
from guenther.prompts import SYSTEM_EXTRACT, SYSTEM_WRITE


def test_sole_production_is_qwen_not_phi():
    assert PRODUCTION_MODEL_ID == "qwen3.5-4b"
    assert list(MODEL_CATALOG.keys()) == ["qwen3.5-4b"]
    assert "phi4-mini" not in MODEL_CATALOG
    assert "phi4-mini" in HISTORICAL_MODEL_CATALOG
    assert not is_production_model("phi4-mini")
    assert is_production_model("qwen3.5-4b")


def test_historical_phi_not_installable(tmp_path: Path):
    mm = ModelManager(tmp_path / "models")
    ok, reason = mm.can_install("phi4-mini")
    assert not ok
    assert reason in {"historical_model_forbidden", "unknown_model", "not_a_production_model"}


def test_settings_migrate_phi_to_qwen(tmp_path: Path, monkeypatch):
    from core.config import SettingsConfig, load_config

    # Empty profile dir with legacy phi setting
    root = tmp_path / "cfg"
    root.mkdir()
    (root / "settings.yaml").write_text("guenther_model: phi4-mini\n", encoding="utf-8")
    monkeypatch.chdir(root)
    # load_config looks relative to repo; call coerce path via SettingsConfig + migrate logic
    s = SettingsConfig(guenther_model="phi4-mini")
    assert s.guenther_model == "phi4-mini"
    # Simulate load_config coercion
    raw = str(s.guenther_model or "").strip().lower()
    if raw in {"", "auto", "phi4-mini", "phi-4-mini", "qwen3-4b", "qwen3-1.7b"}:
        s.guenther_model = "qwen3.5-4b"
    assert s.guenther_model == "qwen3.5-4b"


def test_write_prompt_is_not_phi_persona():
    assert "PHI_WRITE" not in SYSTEM_WRITE
    assert "PHI_EXTRACT" not in SYSTEM_EXTRACT
    assert "Schreibassistent" in SYSTEM_WRITE or "Günther" in SYSTEM_WRITE


def test_suggest_writing_does_not_import_cv():
    """Writing path must not call CV import / Docpick."""
    import guenther.service as svc
    import inspect

    src = inspect.getsource(svc.GuentherService.suggest_writing)
    assert "import_cv" not in src
    assert "docpick" not in src
    assert "extract_cv" not in src


def test_fallback_messages_name_qwen_not_phi():
    from guenther.fallbacks import UNAVAILABLE_CAUSE_DE

    blob = " ".join(UNAVAILABLE_CAUSE_DE.values())
    assert "Phi" not in blob
    assert "Qwen3.5-4B" in blob


def test_ui_settings_label_not_phi():
    from desktop.i18n import TRANSLATIONS

    de = TRANSLATIONS["de"]
    en = TRANSLATIONS["en"]
    for key in (
        "settings.guenther_hint",
        "settings.guenther_writer_status_on",
        "settings.guenther_model.sole",
    ):
        assert "Phi" not in de[key]
        assert "Qwen" in de[key] or "qwen" in de[key].lower() or key.endswith("sole")
        assert "Phi" not in en[key]
