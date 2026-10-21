import tarfile

import pytest
from scripts.prepare_ci_python import runtime_target, validate_members, verify_license


@pytest.mark.parametrize(('system', 'machine', 'target'), [
    ('win32', 'AMD64', 'x86_64-pc-windows-msvc'),
    ('darwin', 'arm64', 'aarch64-apple-darwin'),
    ('darwin', 'x86_64', 'x86_64-apple-darwin')])
def test_exact_native_runtime_target(system, machine, target):
    assert runtime_target(system, machine) == target


def test_unsupported_architecture_does_not_fall_back_to_wrong_binary():
    with pytest.raises(ValueError, match='unsupported'):
        runtime_target('win32', 'ARM64')


@pytest.mark.parametrize(('name', 'kind'), [('/outside', tarfile.REGTYPE),
    ('python/../outside', tarfile.REGTYPE), ('python/link', tarfile.LNKTYPE),
    ('python/device', tarfile.CHRTYPE), ('other/file', tarfile.REGTYPE)])
def test_pinned_runtime_extraction_still_rejects_unsafe_members(name, kind):
    member = tarfile.TarInfo(name)
    member.type = kind
    with pytest.raises(ValueError, match='archive_invalid'):
        validate_members([member])


def test_duplicate_paths_cannot_replace_a_checked_runtime_member():
    with pytest.raises(ValueError, match='archive_invalid'):
        validate_members([tarfile.TarInfo('python/bin/python'), tarfile.TarInfo('python/bin/./python')])


def _runtime_with_license(tmp_path, text):
    import hashlib

    (tmp_path / "python").mkdir()
    (tmp_path / "python" / "LICENSE.txt").write_bytes(text)
    return {"license": {"path": "python/LICENSE.txt", "sha256": hashlib.sha256(text).hexdigest()}}


def test_runtime_license_must_be_present_pinned_and_psf(tmp_path):
    text = b"PYTHON SOFTWARE FOUNDATION LICENSE VERSION 2\n"
    entry = _runtime_with_license(tmp_path, text)
    verify_license(tmp_path, entry)
    (tmp_path / "python" / "LICENSE.txt").write_bytes(text + b"changed")
    with pytest.raises(ValueError, match="ci_python_license_mismatch"):
        verify_license(tmp_path, entry)


def test_runtime_license_other_text_is_refused(tmp_path):
    entry = _runtime_with_license(tmp_path, b"some other license")
    with pytest.raises(ValueError, match="ci_python_license_mismatch"):
        verify_license(tmp_path, entry)


def test_every_pinned_runtime_declares_its_license():
    import json
    from pathlib import Path

    config = json.loads((Path(__file__).resolve().parents[1] / "packaging" / "ci_python_runtimes.json").read_text())
    assert all(len(r["license"]["sha256"]) == 64 and r["license"]["path"].endswith("LICENSE.txt")
               for r in config["runtimes"].values()) and len(config["runtimes"]) == 3
