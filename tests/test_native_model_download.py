"""Native setup downloads only verified common model parts, atomically."""
import hashlib

import pytest

from core import native_model_download as model
from guenther import model_manager


def fixture(tmp_path, monkeypatch):
    blocks = [b'first model bytes', b'second model bytes']
    sha = lambda value: hashlib.sha256(value).hexdigest()
    monkeypatch.setattr(model, 'CV_MODEL_SHA256', sha(b''.join(blocks)))
    monkeypatch.setattr(model_manager, 'default_models_dir', lambda: tmp_path)
    tag = 'update-42-' + 'a' * 12
    manifest = {'tag': tag, 'model': {'path': model.MODEL_PATH,
        'sha256': sha(b''.join(blocks)), 'size': sum(map(len, blocks)), 'parts': [
            {'url': f'https://github.com/{model.REPOSITORY}/releases/download/{tag}/model-{i:03d}.bin',
             'size': len(value), 'sha256': sha(value)} for i, value in enumerate(blocks, 1)]}}
    return blocks, manifest


@pytest.mark.parametrize('failure', [None, 'corrupt', 'cancel'])
def test_download_is_model_only_and_atomic(tmp_path, monkeypatch, failure):
    blocks, manifest = fixture(tmp_path, monkeypatch)
    dest = tmp_path / model.CV_MODEL_DIRNAME / model.CV_MODEL_FILENAME
    dest.parent.mkdir()
    dest.write_bytes(b'previous model')
    profile = tmp_path / 'profile.json'
    profile.write_text('preserved')
    requested = []
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def iter_content(self, size):
            yield b'x' * len(blocks[len(requested) - 1]) if failure == 'corrupt' else blocks[len(requested) - 1]
    def get(url, **kwargs):
        requested.append(url)
        return Response()
    monkeypatch.setattr(model, '_get', get)
    if failure:
        with pytest.raises((ValueError, RuntimeError)):
            model.download(manifest, cancelled=lambda: failure == 'cancel')
        assert dest.read_bytes() == b'previous model'
    else:
        assert model.download(manifest) == dest
        assert dest.read_bytes() == b''.join(blocks)
        assert requested == [part['url'] for part in manifest['model']['parts']]
    assert profile.read_text() == 'preserved'
    assert not list(dest.parent.glob('*.part'))


def test_foreign_program_url_rejected_before_download(tmp_path, monkeypatch):
    _, manifest = fixture(tmp_path, monkeypatch)
    manifest['model']['parts'][0]['url'] = 'https://github.com/evil/releases/app-001.bin'
    monkeypatch.setattr(model, '_get', lambda *a, **k: pytest.fail('invalid model initiated a download'))
    with pytest.raises(ValueError, match='invalid_model_part'):
        model.download(manifest)
