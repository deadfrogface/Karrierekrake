from pathlib import Path
import zipfile

import pytest
from scripts import package_windows_release as package


def inputs(tmp_path, monkeypatch):
    dist = tmp_path / 'dist'
    (dist / 'Karrierekrake' / '_internal').mkdir(parents=True)
    (dist / 'Karrierekrake' / 'Karrierekrake.exe').write_bytes(b'MZsynthetic')
    (dist / 'Karrierekrake' / '_internal' / 'lib.dll').write_bytes(b'lib')
    compliance = tmp_path / 'compliance'
    compliance.mkdir()
    for name in ('release-sbom.json', 'license-review.json', 'THIRD_PARTY_NOTICES.txt'):
        (compliance / name).write_text('synthetic ' + name)
    monkeypatch.setattr(package, 'require_release_layout', lambda _: dist / 'Karrierekrake' / 'Karrierekrake.exe')
    return dist, compliance


def test_windows_zip_preserves_actual_build_inventory_and_full_license_texts(tmp_path, monkeypatch):
    dist, compliance = inputs(tmp_path, monkeypatch)
    (compliance / 'private-build-log.txt').write_text('must not ship')
    target = tmp_path / 'release.zip'
    package.build_zip(dist, target, compliance_dir=compliance)
    with zipfile.ZipFile(target) as archive:
        for path, name in package.compliance_members(compliance):
            assert archive.read(name) == path.read_bytes()
        assert 'private-build-log.txt' not in archive.namelist()
        assert archive.read('Karrierekrake.exe') == b'MZsynthetic'
        assert archive.read('_internal/lib.dll') == b'lib'
        assert not any(name.startswith('models/') for name in archive.namelist())


@pytest.mark.parametrize('name', ['release-sbom.json', 'THIRD_PARTY_NOTICES.txt', 'license-review.json'])
def test_missing_build_notices_or_inventory_refuse_release_without_replacing_previous_zip(tmp_path, monkeypatch, name):
    dist, compliance = inputs(tmp_path, monkeypatch)
    (compliance / name).unlink()
    target = tmp_path / 'release.zip'
    target.write_bytes(b'previous valid archive')
    with pytest.raises(ValueError, match='compliance_inventory_missing'):
        package.build_zip(dist, target, compliance_dir=compliance)
    assert target.read_bytes() == b'previous valid archive'
