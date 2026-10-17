import tarfile

import pytest
from scripts.prepare_ci_python import runtime_target, validate_members


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
