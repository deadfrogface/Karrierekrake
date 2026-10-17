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
