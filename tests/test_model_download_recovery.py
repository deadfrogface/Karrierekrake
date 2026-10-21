"""Range recovery cannot append a full response to a previous partial file."""
import hashlib
import io
import errno
import ssl
import urllib.error
from types import SimpleNamespace

import pytest
import requests

from core import app_updates
from guenther import model_manager as models


@pytest.fixture(autouse=True)
def fast_retry(monkeypatch):
    monkeypatch.setattr(models, 'DOWNLOAD_RETRY_DELAY', 0)


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
    # The unusable Range answer triggered the restart from zero, which empties the
    # stale .part at once; the misplaced 206 body is never appended to it.
    assert partial.read_bytes() == b''


def test_timeout_after_received_bytes_resumes_automatically(tmp_path, monkeypatch):
    manager, mid, payload, dest, partial = setup_manager(tmp_path)
    calls = []
    class Interrupted(Response):
        def read(self, size=-1):
            if self.tell():
                raise TimeoutError('private signed URL')
            return super().read(5)
    def open_url(req, **kwargs):
        calls.append(req.get_header('Range'))
        assert kwargs['timeout'] == 60
        if len(calls) == 1:
            return Interrupted(payload[5:10], 206,
                               **{'Content-Range': f'bytes 5-{len(payload)-1}/{len(payload)}'})
        assert partial.read_bytes() == payload[:10]
        return Response(payload[10:], 206,
                        **{'Content-Range': f'bytes 10-{len(payload)-1}/{len(payload)}'})
    monkeypatch.setattr(models.urllib.request, 'urlopen', open_url)
    stages = []
    result = manager.install(mid, allow_download=True, progress_cb=lambda p: stages.append(p.status))
    assert result.status == 'done'
    assert dest.read_bytes() == payload
    assert calls == ['bytes=5-', 'bytes=10-']
    assert 'retrying' in stages


@pytest.mark.parametrize('failure,code,retries', [
    (TimeoutError('private path'), 'connection_timeout', 3),
    (urllib.error.URLError(TimeoutError('private URL')), 'connection_timeout', 3),
    (ssl.SSLCertVerificationError('private certificate'), 'tls_failed', 1),
    (PermissionError('private directory'), 'write_permission_denied', 1),
    (OSError(errno.ENOSPC, 'private drive'), 'insufficient_disk', 1),
    (urllib.error.HTTPError('https://private.test', 403, 'blocked', {}, None), 'http_403', 1),
    (urllib.error.HTTPError('https://private.test', 503, 'busy', {}, None), 'http_503', 3),
])
def test_failure_is_specific_and_retries_are_bounded(tmp_path, monkeypatch, failure, code, retries):
    manager, mid, _, dest, partial = setup_manager(tmp_path)
    calls = []
    def open_url(*args, **kwargs):
        calls.append(True)
        raise failure
    monkeypatch.setattr(models.urllib.request, 'urlopen', open_url)
    result = manager.install(mid, allow_download=True)
    assert (result.status, result.message) == ('error', code)
    assert len(calls) == retries
    assert not dest.exists() and partial.exists()


def test_cancel_during_retry_never_activates_or_retries(tmp_path, monkeypatch):
    manager, mid, _, dest, partial = setup_manager(tmp_path)
    cancelled = []
    calls = []
    def open_url(*args, **kwargs):
        calls.append(True)
        raise TimeoutError()
    def progress(p):
        if p.status == 'retrying':
            cancelled.append(True)
    monkeypatch.setattr(models.urllib.request, 'urlopen', open_url)
    result = manager.install(mid, allow_download=True, progress_cb=progress,
                             cancel_check=lambda: bool(cancelled))
    assert result.status == 'cancelled' and len(calls) == 1
    assert partial.exists() and not dest.exists()


@pytest.mark.parametrize('failure,expected', [
    ('connection_timeout', 'connection_timeout'),
    ('insufficient_disk', 'insufficient_disk'),
    ('checksum_mismatch', 'checksum_mismatch'),
    ('http_403', 'http_403'),
])
def test_setup_reports_specific_failure_without_private_details(failure, expected):
    from desktop.widgets.model_setup_panel import model_failure_text
    assert expected in model_failure_text(RuntimeError(failure))
    assert 'private-user-path' not in model_failure_text(RuntimeError('private-user-path'))


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


@pytest.mark.parametrize("link_kind", ["partial", "final", "directory"])
def test_model_download_rejects_symlink_destinations(tmp_path, monkeypatch, link_kind):
    manager, mid, payload, dest, partial = setup_manager(tmp_path)
    partial.unlink()
    external = tmp_path / "external"
    external.mkdir()
    external_file = external / "external.gguf"
    external_file.write_bytes(b"do not overwrite")
    if link_kind == "partial":
        link = partial
        target = external_file
    elif link_kind == "final":
        link = dest
        target = external_file
    else:
        dest.parent.rmdir()
        link = dest.parent
        target = external
    try:
        link.symlink_to(target, target_is_directory=link_kind == "directory")
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks unavailable")
    monkeypatch.setattr(models.urllib.request, "urlopen",
                        lambda *a, **k: pytest.fail("No network request expected"))
    result = manager.install(mid, allow_download=True)
    assert result.status == "error"
    assert external_file.read_bytes() == b"do not overwrite"
