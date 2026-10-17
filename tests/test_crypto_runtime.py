import pytest

from core.security.crypto_runtime import verify_crypto_runtime


def test_actual_pinned_crypto_runtime_and_signature_verification():
    result = verify_crypto_runtime()
    assert result['cryptography'] == '50.0.2'
    assert result['openssl'].startswith('OpenSSL 4.0.3 ')
    assert result['ed25519'] == 'ok'


@pytest.mark.parametrize(('version', 'openssl'), [
    ('50.0.1', 0x40000020),
    ('50.0.2', 0x40000020),  # New distribution metadata cannot hide an old binary.
    ('50.0.1', 0x40000030),
])
def test_mixed_or_stale_embedded_crypto_runtime_is_rejected(monkeypatch, version, openssl):
    import cryptography
    from cryptography.hazmat.backends.openssl import backend
    monkeypatch.setattr(cryptography, '__version__', version)
    monkeypatch.setattr(backend, 'openssl_version_number', lambda: openssl)
    with pytest.raises(RuntimeError, match='runtime_policy_mismatch'):
        verify_crypto_runtime()


@pytest.mark.parametrize(('python_version', 'openssl'), [((3, 12, 10), (3, 5, 9)),
                                                        ((3, 12, 15), (3, 6, 3))])
def test_packaged_interpreter_and_its_separate_ssl_must_meet_security_policy(monkeypatch, python_version, openssl):
    import sys
    import ssl
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, 'version_info', python_version)
    monkeypatch.setattr(sys, 'platform', 'win32')
    monkeypatch.setattr(ssl, 'OPENSSL_VERSION_INFO', openssl)
    with pytest.raises(RuntimeError, match='packaged_python_runtime_policy_mismatch'):
        verify_crypto_runtime()
