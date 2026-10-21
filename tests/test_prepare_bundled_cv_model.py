"""Unit tests for bundled CV model prepare (no multi-GB download)."""

from __future__ import annotations

import urllib.error
from pathlib import Path

import pytest

from core.cv_llm_runtime import CV_MODEL_FILENAME, CV_MODEL_SHA256
from scripts import prepare_bundled_cv_model as prep


def test_download_urls_prefer_public_unsloth_mirror():
    assert prep.DOWNLOAD_URLS[0].startswith(
        "https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/resolve/main/"
    )
    assert any("Qwen/Qwen3.5-4B-GGUF" in u for u in prep.DOWNLOAD_URLS)
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

    monkeypatch.setattr(prep, "_download_one", fake_download_one)
    prep._download(dest)
    assert dest.read_bytes() == b"GGUF-ok"
    assert not part.exists()
    assert len(calls) == 2
    assert "unsloth/Qwen3.5-4B-GGUF" in calls[0]
    assert "Qwen/Qwen3.5-4B-GGUF" in calls[1]


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
    side = also / "models" / "qwen3.5-4b" / CV_MODEL_FILENAME
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
    side = also / "models" / "qwen3.5-4b" / CV_MODEL_FILENAME
    assert side.is_file()
    assert side.read_bytes() == b"staged-gguf"


def test_disk_full_does_not_repeat_download_from_other_mirror(tmp_path, monkeypatch):
    import errno
    calls = []
    def full(url, part):
        calls.append(url)
        part.write_bytes(b'partial')
        raise OSError(errno.ENOSPC, 'synthetic full disk')
    monkeypatch.setattr(prep, '_download_one', full)
    target = tmp_path / 'model.gguf'
    with pytest.raises(SystemExit, match='model_download_insufficient_space'):
        prep._download(target)
    assert len(calls) == 1
    assert not target.exists()
    assert not target.with_suffix('.gguf.part').exists()


def test_known_download_size_is_checked_before_body_or_file_write(tmp_path, monkeypatch):
    import io
    from types import SimpleNamespace
    class Response(io.BytesIO):
        headers = {'Content-Length':'1024'}
        def read(self, *args):
            pytest.fail('body must not be downloaded when disk is already insufficient')
    monkeypatch.setattr(prep.urllib.request, 'urlopen', lambda *a, **k: Response())
    monkeypatch.setattr(prep.shutil, 'disk_usage', lambda _: SimpleNamespace(free=100))
    target = tmp_path / 'model.part'
    with pytest.raises(OSError, match='model_download_insufficient_space'):
        prep._download_one('https://example.org/model', target)
    assert not target.exists()
