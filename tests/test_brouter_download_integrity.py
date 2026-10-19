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


# --- T07.10 Kritiker follow-up: existing JAR, atomic activation, zip-slip ---


def _install_ok(monkeypatch, tmp_path: Path) -> tuple[Path, bytes]:
    payload = _zip_bytes()
    monkeypatch.setattr(rb, "BROUTER_ZIP_SHA256", hashlib.sha256(payload).hexdigest())
    _patch_download(monkeypatch, payload)
    jar = tmp_path / "brouter-all.jar"
    rb._download_brouter_distribution(tmp_path, jar, timeout_s=1.0)
    return jar, payload


def test_install_writes_verified_marker_with_jar_sha256(monkeypatch, tmp_path: Path) -> None:
    jar, _ = _install_ok(monkeypatch, tmp_path)
    assert rb.jar_install_verified(jar)
    assert not list(tmp_path.glob("*.partial"))


def test_existing_jar_without_marker_is_not_trusted(tmp_path: Path) -> None:
    jar = tmp_path / "brouter-all.jar"
    jar.write_bytes(b"J" * 200_000)  # >100KB but never verified
    assert not rb.jar_install_verified(jar)


def test_tampered_existing_jar_is_not_trusted(monkeypatch, tmp_path: Path) -> None:
    jar, _ = _install_ok(monkeypatch, tmp_path)
    jar.write_bytes(b"X" * 200_000)
    assert not rb.jar_install_verified(jar)


def test_truncated_jar_over_100kb_is_not_installed(monkeypatch, tmp_path: Path) -> None:
    jar, _ = _install_ok(monkeypatch, tmp_path)
    jar.write_bytes(b"J" * 150_000)  # interrupted write, still >100KB
    assert not rb.jar_install_verified(jar)
    rt = rb.BRouterRuntime()
    rt._dirs = rb.default_runtime_dirs(tmp_path)
    assert not rt.is_installed()


def test_ensure_install_redownloads_unverified_existing_jar(monkeypatch, tmp_path: Path) -> None:
    dirs = rb.default_runtime_dirs(tmp_path)
    dirs["root"].mkdir(parents=True, exist_ok=True)
    dirs["jar"].write_bytes(b"EVIL" * 50_000)
    dirs["profiles"].mkdir(parents=True, exist_ok=True)
    (dirs["profiles"] / "car-fast.brf").write_bytes(b"p")
    calls: list[Path] = []
    monkeypatch.setattr(
        rb, "_download_brouter_distribution", lambda root, jar, **k: calls.append(jar)
    )
    monkeypatch.setattr(rb, "ensure_segments", lambda *a, **k: None)
    rb.ensure_brouter_install(root=tmp_path, segment_names=())
    assert calls == [dirs["jar"]]


def test_failed_jar_write_leaves_no_active_jar(monkeypatch, tmp_path: Path) -> None:
    payload = _zip_bytes()
    monkeypatch.setattr(rb, "BROUTER_ZIP_SHA256", hashlib.sha256(payload).hexdigest())
    _patch_download(monkeypatch, payload)
    jar = tmp_path / "brouter-all.jar"

    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(rb.os, "replace", boom)
    with pytest.raises(OSError):
        rb._download_brouter_distribution(tmp_path, jar, timeout_s=1.0)
    assert not jar.exists()
    assert not rb.jar_install_verified(jar)


def _slip_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("brouter-1.7.10/brouter-1.7.10-all.jar", b"J" * 200_000)
        zf.writestr("brouter-1.7.10/profiles2/../../../evil.txt", b"pwn")
        zf.writestr("brouter-1.7.10/profiles2/car-fast.brf", b"profile")
    return buf.getvalue()


def test_zip_slip_member_is_rejected(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "rt"
    root.mkdir()
    payload = _slip_zip()
    monkeypatch.setattr(rb, "BROUTER_ZIP_SHA256", hashlib.sha256(payload).hexdigest())
    _patch_download(monkeypatch, payload)
    with pytest.raises(rb.BRouterIntegrityError):
        rb._download_brouter_distribution(root, root / "brouter-all.jar", timeout_s=1.0)
    assert not (tmp_path / "evil.txt").exists()
    assert not (root / "evil.txt").exists()
