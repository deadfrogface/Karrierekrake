"""Acceptance check for the pinned cryptography wheel and its embedded OpenSSL.

The wheel's OpenSSL is separate from Python's ssl and the OS OpenSSL. Do not
infer its security patch level from either of those runtimes.
"""
from __future__ import annotations


def verify_crypto_runtime() -> dict[str, str]:
    import cryptography
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.backends.openssl import backend
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    if (cryptography.__version__ != '50.0.2'
            or backend.openssl_version_number() != 0x40000030):
        raise RuntimeError('cryptography_runtime_policy_mismatch')
    # Exercise the actual signing/verification primitive used by offline
    # entitlements; a version string alone cannot demonstrate it works.
    key = Ed25519PrivateKey.generate()
    message = b'Karrierekrake native crypto acceptance'
    signature = key.sign(message)
    key.public_key().verify(signature, message)
    try:
        key.public_key().verify(signature, message + b'!')
    except InvalidSignature:
        pass
    else:
        raise RuntimeError('cryptography_signature_verification_failed')
    return {'cryptography': cryptography.__version__,
            'openssl': backend.openssl_version_text(), 'ed25519': 'ok'}
