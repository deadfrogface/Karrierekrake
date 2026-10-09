"""Range recovery cannot append a full response to a previous partial file."""
import hashlib
import io
import urllib.error
from types import SimpleNamespace

import pytest
import requests

from core import app_updates
from guenther import model_manager as models


class Response(io.BytesIO):
    def __init__(self, data, status=200, **headers):
        super().__init__(data)
        self.status = status
        self.headers = {'Content-Length': str(len(data)), **headers}


def setup_manager(tmp_path):
    payload = b'complete verified model'
    mid = models.PRODUCTION_MODEL_ID
    manager = models.ModelManager(tmp_path, catalog={mid: {
        'filename': 'model.gguf', 'url': 'https://example.test/model.gguf',
        'sha256': hashlib.sha256(payload).hexdigest(), 'approx_bytes': len(payload)}})
    dest = manager.model_path(mid)
    dest.parent.mkdir()
    partial = dest.with_suffix('.gguf.part')
    partial.write_bytes(payload[:5])
    return manager, mid, payload, dest, partial


@pytest.mark.parametrize('status', [200, 206, 416])
def test_interrupted_download_recovers_without_corruption(tmp_path, monkeypatch, status):
    manager, mid, payload, dest, partial = setup_manager(tmp_path)
    requests_seen = []
    def open_url(req, **kwargs):
        requests_seen.append(req.get_header('Range'))
        if status == 416 and len(requests_seen) == 1:
            raise urllib.error.HTTPError(req.full_url, 416, 'Range invalid', {}, io.BytesIO())
        if status == 206:
            return Response(payload[5:], 206, **{'Content-Range': f'bytes 5-{len(payload)-1}/{len(payload)}'})
        return Response(payload)
    monkeypatch.setattr(models.urllib.request, 'urlopen', open_url)
    progress = []
    result = manager.install(mid, allow_download=True,
                             progress_cb=lambda p: progress.append((p.bytes_done, p.bytes_total)))
    assert result.status == 'done'
    assert dest.read_bytes() == payload and not partial.exists()
    assert requests_seen == (['bytes=5-', None] if status == 416 else ['bytes=5-'])
    assert progress[-1] == (len(payload), len(payload))


def test_incorrect_range_never_overwrites_installed_model(tmp_path, monkeypatch):
    manager, mid, payload, dest, partial = setup_manager(tmp_path)
    dest.write_bytes(b'old installed model')
    monkeypatch.setattr(models.urllib.request, 'urlopen', lambda *a, **k:
                        Response(payload[5:], 206, **{'Content-Range': f'bytes 0-{len(payload)-6}/{len(payload)}'}))
    result = manager.install(mid, allow_download=True)
    assert result.status == 'error'
    assert dest.read_bytes() == b'old installed model'
    assert partial.read_bytes() == payload[:5]


def test_failure_codes_do_not_expose_exception_paths():
    assert app_updates.failure_code(PermissionError('private-user-folder')) == 'write_permission_denied'
    assert app_updates.failure_code(ValueError('private-user-folder')) == 'update_failed'
    assert app_updates.failure_code(OSError('insufficient_update_space')) == 'insufficient_update_space'
    response = requests.Response()
    response.status_code = 403
    assert app_updates.failure_code(requests.HTTPError(response=response)) == 'http_403'
    assert app_updates.failure_code(requests.Timeout()) == 'connection_timeout'


def test_settings_recognizes_the_shared_model(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QLabel

    from core import cv_llm_runtime
    from desktop.i18n import tr
    from desktop.pages.settings import SettingsPage
    monkeypatch.setattr(cv_llm_runtime, 'resolve_cv_model_path', lambda: tmp_path / 'model.gguf')
    monkeypatch.setattr(cv_llm_runtime, 'llama_cpp_importable', lambda: False)
    page = SimpleNamespace(guenther_writer_status=QLabel())
    SettingsPage._refresh_guenther_status_labels(page)
    assert page.guenther_writer_status.text() == tr('settings.guenther_writer_status_on')
