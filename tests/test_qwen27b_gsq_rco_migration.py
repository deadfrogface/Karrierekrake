"""Migration and release boundaries; no model weights required."""
import pytest

from core import app_updates, native_model_download
from core.cv_llm_runtime import CV_MODEL_DIRNAME, CV_MODEL_FILENAME, CV_MODEL_SHA256
from guenther.hardware import HardwareTier, can_run_production_model
from guenther.model_manager import MODEL_CATALOG, PRODUCTION_MODEL_ID
from scripts.prepare_bundled_cv_model import DOWNLOAD_URLS


@pytest.mark.parametrize("legacy", ["qwen3.5-4b", "qwen35-9b", "auto", "phi4-mini"])
def test_real_config_upgrade_keeps_user_profile(tmp_path, legacy):
    from core.config import load_config
    (tmp_path / "profile.yaml").write_text("location:\n  max_distance_km: 20\n", encoding="utf-8")
    (tmp_path / "application.yaml").write_text("first_name: Nora\nlast_name: Test\n", encoding="utf-8")
    (tmp_path / "settings.yaml").write_text(f"guenther_model: {legacy}\n", encoding="utf-8")
    config = load_config(root=tmp_path, profile_path=tmp_path / "profile.yaml",
                         application_path=tmp_path / "application.yaml",
                         settings_path=tmp_path / "settings.yaml")
    assert config.settings.guenther_model == PRODUCTION_MODEL_ID
    assert config.application.first_name == "Nora"
    # Merely reading config must not delete the old profile or model files.
    assert "Nora" in (tmp_path / "application.yaml").read_text()
    assert config.profile.location.max_distance_km == 20


def test_every_delivery_path_targets_same_verified_artifact():
    meta = MODEL_CATALOG[PRODUCTION_MODEL_ID]
    assert meta["compression"] == "GSQ-RCO"
    assert meta["quant"] == "IQ2_XS"
    assert meta["approx_bytes"] == 8_422_841_472
    assert meta["filename"] == CV_MODEL_FILENAME
    assert meta["sha256"] == CV_MODEL_SHA256
    assert CV_MODEL_DIRNAME == PRODUCTION_MODEL_ID
    assert DOWNLOAD_URLS == (meta["url"],)
    assert f"/resolve/{meta['revision']}/" in meta["url"]
    assert app_updates.MODEL_PATH == f"models/{PRODUCTION_MODEL_ID}/{CV_MODEL_FILENAME}"


def nine_part_model():
    meta = MODEL_CATALOG[PRODUCTION_MODEL_ID]
    tag = "update-42-abcdef123456"
    parts = []
    left = meta["approx_bytes"]
    for index in range(1, 10):
        size = min(left, 1_000_000_000)
        left -= size
        parts.append({"size": size, "sha256": "a" * 64,
                      "url": f"https://github.com/{app_updates.REPOSITORY}/releases/download/{tag}/model-{index:03d}.bin"})
    return tag, {"path": app_updates.MODEL_PATH, "size": meta["approx_bytes"],
                 "sha256": meta["sha256"], "parts": parts}


def test_842gb_nine_part_release_accepted_by_both_downloaders():
    tag, model = nine_part_model()
    assert native_model_download.validate({"tag": tag, "model": model}) == model
    app = {"path": "Karrierekrake.exe", "size": 1, "sha256": "b" * 64,
           "parts": [{"size": 1, "sha256": "b" * 64,
                      "url": f"https://github.com/{app_updates.REPOSITORY}/releases/download/{tag}/app-001.bin"}]}
    manifest = {"tag": tag, "protocol": 1, "sequence": 42,
                "components": {"app": app, "model": model}}
    assert app_updates.validate_manifest(manifest, tag) == manifest
    model["parts"][8]["url"] = "https://example.com/model-009.bin"
    with pytest.raises(ValueError):
        native_model_download.validate({"tag": tag, "model": model})
    with pytest.raises(ValueError):
        app_updates.validate_manifest(manifest, tag)


@pytest.mark.parametrize("ram,expected", [(8, False), (12, False), (15.5, True), (24, True)])
def test_hardware_target_is_16gb_installed_ram(ram, expected):
    assert can_run_production_model(HardwareTier.STANDARD, ram_gb=ram) is expected


def test_non_thinking_switch_matches_cv_prefill_template():
    pytest.importorskip("llama_cpp")
    from types import SimpleNamespace
    from core.local_chat_template import configure_non_thinking_chat
    from core.cv_llm_runtime import _gguf_chat_prompt_token_ids
    llm = SimpleNamespace(
        metadata={"tokenizer.chat_template": "{% if enable_thinking is not defined or enable_thinking %}THINK{% else %}ANSWER{% endif %}"},
        token_eos=lambda: 1, token_bos=lambda: 2,
        _model=SimpleNamespace(token_get_text=lambda token: "<eos>" if token == 1 else "<bos>"),
        tokenize=lambda text, **kwargs: list(text),
    )
    assert configure_non_thinking_chat(llm)
    assert callable(llm.chat_handler)
    assert bytes(_gguf_chat_prompt_token_ids(llm, [{"role": "user", "content": "hello"}])) == b"ANSWER"


def test_windows_zip_contains_verified_sidecar(tmp_path, monkeypatch):
    import hashlib
    import zipfile
    from scripts import package_windows_release as package
    dist = tmp_path / "dist"
    model = dist / package.CV_MODEL_REL
    model.parent.mkdir(parents=True)
    model.write_bytes(b"GGUF fixture")
    (dist / "Karrierekrake.exe").write_bytes(b"MZ fixture")
    monkeypatch.setattr(package, "CV_MODEL_SHA256", hashlib.sha256(model.read_bytes()).hexdigest())
    output = tmp_path / "release.zip"
    meta = package.build_zip(dist, output)
    assert meta["model_sidecar"] is True and meta["model_embedded"] is False
    with zipfile.ZipFile(output) as archive:
        assert archive.read(package.CV_MODEL_REL.as_posix()) == b"GGUF fixture"
        assert archive.getinfo(package.CV_MODEL_REL.as_posix()).compress_type == zipfile.ZIP_STORED
    model.write_bytes(b"tampered")
    with pytest.raises(SystemExit, match="Release model gate failed"):
        package.require_release_layout(dist)
