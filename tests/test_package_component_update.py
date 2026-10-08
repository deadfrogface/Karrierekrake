import json
import zipfile
import pytest
from core import app_updates as u
from scripts import package_component_update as p


def test_package_keeps_model_out_of_exe_download_and_bootstrap_zip(tmp_path, monkeypatch):
    exe, model = tmp_path / 'app.exe', tmp_path / 'model.gguf'
    exe.write_bytes(b'program')
    model.write_bytes(b'verified-model')
    monkeypatch.setattr(p, 'CV_MODEL_SHA256', u.digest(model))
    out = tmp_path / 'release'
    manifest = p.build(exe, model, out, sequence=3, commit='abcdef123456' + '0' * 28)
    assert u.validate_manifest(manifest, manifest['tag']) == manifest
    assert (out / 'model-001.bin').read_bytes() == b'verified-model'
    assert (out / 'app-001.bin').read_bytes() == b'program'
    assert (out / 'install' / u.MODEL_PATH).is_file()
    with zipfile.ZipFile(out / p.WINDOWS_ASSET) as archive:
        assert u.MODEL_PATH not in archive.namelist()
        assert json.loads(archive.read(u.CURRENT)) == manifest
        assert 'KI-Modell' in archive.read('INSTALL.txt').decode('utf-8')


def test_package_rejects_wrong_model_before_producing_manifest(tmp_path, monkeypatch):
    exe, model = tmp_path / 'app.exe', tmp_path / 'model.gguf'
    exe.write_bytes(b'program')
    model.write_bytes(b'wrong model')
    monkeypatch.setattr(p, 'CV_MODEL_SHA256', '0' * 64)
    with pytest.raises(ValueError, match='bundled_model_hash_mismatch'):
        p.build(exe, model, tmp_path / 'release', sequence=3, commit='abcdef123456')
    assert not (tmp_path / 'release' / 'update-manifest.json').exists()
