"""Exercise the real HTTPS transport, including a bundled-only trust root."""
import functools
import hashlib
import http.server
import shutil
import ssl
import subprocess
import threading
import urllib.error

import pytest

from guenther import model_manager as models


def test_bundled_ca_downloads_and_verifies_model(tmp_path, monkeypatch):
    if not shutil.which('openssl'):
        pytest.skip('openssl needed for local HTTPS fixture')
    cert, key = tmp_path / 'ca.pem', tmp_path / 'key.pem'
    subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                    '-keyout', str(key), '-out', str(cert), '-days', '1',
                    '-subj', '/CN=localhost', '-addext', 'subjectAltName=DNS:localhost'],
                   check=True, capture_output=True)
    payload = b'GGUF' + b'verified model fixture' * 100
    (tmp_path / 'model.gguf').write_bytes(payload)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(tmp_path))
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        # Simulate a packaged installation without usable system roots.
        monkeypatch.setattr(models.ssl, 'create_default_context',
                            lambda: ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT))
        monkeypatch.setattr(models.certifi, 'where', lambda: str(cert))
        ctx = models.download_ssl_context()
        assert ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname
        mid = models.PRODUCTION_MODEL_ID
        manager = models.ModelManager(tmp_path / 'installed', {mid: {
            'url': f'https://localhost:{server.server_port}/model.gguf',
            'filename': 'model.gguf', 'approx_bytes': len(payload),
            'sha256': hashlib.sha256(payload).hexdigest()}})
        result = manager.install(mid, allow_download=True)
        assert result.status == 'done'
        assert manager.model_path(mid).read_bytes() == payload
        # Untrusted server must still fail, never silently disable validation.
        with pytest.raises(urllib.error.URLError):
            models.urllib.request.urlopen(manager.catalog[mid]['url'],
                                          context=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT))
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_tls_diagnostic_keeps_verification_code_without_secrets():
    exc = ssl.SSLCertVerificationError('secret path and signed URL')
    exc.verify_code = 20
    exc.reason = 'CERTIFICATE_VERIFY_FAILED'
    result = models.download_diagnostic(urllib.error.URLError(exc),
                                       'https://example.org/file?token=secret')
    assert 'verify_code=20' in result
    assert 'reason=CERTIFICATE_VERIFY_FAILED' in result
    assert 'host=example.org' in result
    assert 'secret' not in result
