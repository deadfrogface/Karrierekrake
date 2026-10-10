"""Unit tests for bundled CV model prepare (no multi-GB download)."""

from __future__ import annotations

import urllib.error
from pathlib import Path

import pytest

from core.cv_llm_runtime import CV_MODEL_FILENAME, CV_MODEL_SHA256
from scripts import prepare_bundled_cv_model as prep


def test_download_url_pins_public_daslab_artifact():
    assert prep.DOWNLOAD_URLS[0].startswith(
        "https://huggingface.co/ISTA-DASLab/Qwen3.8-27B-GSQ-RCO-GGUF/resolve/d562806dbafae37109975e970aae91b43e73b440/"
    )
    assert len(prep.DOWNLOAD_URLS) == 1
    assert all(CV_MODEL_FILENAME in u for u in prep.DOWNLOAD_URLS)


def test_download_falls_back_after_http_401(tmp_path: Path, monkeypatch):
    dest = tmp_path / "model.gguf"
    part = dest.with_suffix(dest.suffix + ".part")
    calls: list[str] = []

    def fake_download_one(url: str, part_path: Path) -> None:
        calls.append(url)
        if "unsloth/" in url:
            raise urllib.error.HTTPError(url, 401, "Unauthorized", hdrs=None, fp=None)
        # Write a tiny placeholder; SHA check is outside _download.
        part_path.write_bytes(b"GGUF-ok")

    monkeypatch.setattr(prep, "DOWNLOAD_URLS", ("https://test/unsloth/first", "https://test/fallback"))
    monkeypatch.setattr(prep, "_download_one", fake_download_one)
    prep._download(dest)
    assert dest.read_bytes() == b"GGUF-ok"
    assert not part.exists()
    assert len(calls) == 2
    assert calls[0] == "https://test/unsloth/first"
    assert calls[1] == "https://test/fallback"


def test_prepare_uses_local_src_without_network(tmp_path: Path, monkeypatch):
    src = tmp_path / "src.gguf"
    # Minimal file with correct SHA mocked.
    src.write_bytes(b"local-gguf")
    monkeypatch.setattr(prep, "_sha256", lambda path: CV_MODEL_SHA256)
    monkeypatch.setattr(prep, "_ROOT", tmp_path / "repo")
    also = tmp_path / "dist"
    out = prep.prepare(src=src, allow_download=False, also_sidecar=also)
    assert out.is_file()
    assert out.read_bytes() == b"local-gguf"
    side = also / "models" / "qwen3.8-27b-gsq-rco" / CV_MODEL_FILENAME
    assert side.is_file()
    assert side.read_bytes() == b"local-gguf"


def test_prepare_refuses_missing_without_download(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(prep, "_ROOT", tmp_path / "repo")
    monkeypatch.delenv("KARRIEREKRAKE_CV_LLM_MODEL", raising=False)
    monkeypatch.delenv("KARRIEREKRAKE_MODELS_DIR", raising=False)
    monkeypatch.setattr(prep, "_candidate_sources", lambda explicit: [])
    with pytest.raises(SystemExit, match="GGUF source missing"):
        prep.prepare(src=None, allow_download=False, also_sidecar=None)


def test_also_sidecar_reuses_staged_vendor(tmp_path: Path, monkeypatch):
    """Second prepare(--also-sidecar) must find vendor GGUF without re-download."""
    root = tmp_path / "repo"
    vendor = root / prep.VENDOR_REL
    vendor.parent.mkdir(parents=True, exist_ok=True)
    vendor.write_bytes(b"staged-gguf")
    monkeypatch.setattr(prep, "_ROOT", root)
    monkeypatch.setattr(prep, "_sha256", lambda path: CV_MODEL_SHA256)
    monkeypatch.delenv("KARRIEREKRAKE_CV_LLM_MODEL", raising=False)
    monkeypatch.delenv("KARRIEREKRAKE_MODELS_DIR", raising=False)
    also = tmp_path / "dist"
    out = prep.prepare(src=None, allow_download=False, also_sidecar=also)
    assert out.resolve() == vendor.resolve()
    side = also / "models" / "qwen3.8-27b-gsq-rco" / CV_MODEL_FILENAME
    assert side.is_file()
    assert side.read_bytes() == b"staged-gguf"
