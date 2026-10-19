"""T07.10: BRouter release ZIP must be hash-checked before extraction/execution."""

from __future__ import annotations

import hashlib
import io
import zipfile
from pathlib import Path

import pytest

import core.road_route_brouter as rb


def _zip_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("brouter-1.7.10/brouter-1.7.10-all.jar", b"J" * 200_000)
        zf.writestr("brouter-1.7.10/profiles2/car-fast.brf", b"profile")
    return buf.getvalue()


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _patch_download(monkeypatch, payload: bytes) -> None:
    monkeypatch.setattr(rb.urllib.request, "urlopen", lambda *a, **k: _Resp(payload))


def test_pinned_sha256_is_well_formed() -> None:
    assert len(rb.BROUTER_ZIP_SHA256) == 64
    int(rb.BROUTER_ZIP_SHA256, 16)
    assert "v1.7.10" in rb.BROUTER_JAR_URL


def test_tampered_zip_is_rejected_before_extraction(monkeypatch, tmp_path: Path) -> None:
    _patch_download(monkeypatch, _zip_bytes())
    jar = tmp_path / "brouter-all.jar"
    with pytest.raises(rb.BRouterIntegrityError):
        rb._download_brouter_distribution(tmp_path, jar, timeout_s=1.0)
    assert not jar.exists()
    assert not (tmp_path / "profiles2").exists()


def test_matching_zip_is_extracted(monkeypatch, tmp_path: Path) -> None:
    payload = _zip_bytes()
    monkeypatch.setattr(rb, "BROUTER_ZIP_SHA256", hashlib.sha256(payload).hexdigest())
    _patch_download(monkeypatch, payload)
    jar = tmp_path / "brouter-all.jar"
    rb._download_brouter_distribution(tmp_path, jar, timeout_s=1.0)
    assert jar.stat().st_size == 200_000
    assert (tmp_path / "profiles2" / "car-fast.brf").read_bytes() == b"profile"


def test_hash_check_is_case_insensitive(monkeypatch, tmp_path: Path) -> None:
    payload = _zip_bytes()
    monkeypatch.setattr(rb, "BROUTER_ZIP_SHA256", hashlib.sha256(payload).hexdigest().upper())
    _patch_download(monkeypatch, payload)
    rb._download_brouter_distribution(tmp_path, tmp_path / "j.jar", timeout_s=1.0)
