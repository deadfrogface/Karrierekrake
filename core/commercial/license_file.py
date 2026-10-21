"""Ed25519-signed, expiring offline entitlements. No secret key in the app.

Local administrator tampering/clock resets cannot be made server-proof offline.
A short expiry bounds delayed revocation; it does not provide instant revocation.
"""
from __future__ import annotations
import base64
import json
import os
from pathlib import Path
import re
import tempfile
import time
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from core.commercial.release_policy import FREE_FEATURES, PAID_FEATURES, load_policy
from core.platform_paths import user_data_dir

MAX_LICENSE_BYTES = 32768
MAX_OFFLINE_SECONDS = 31 * 86400


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')


def verify_license(raw: bytes, *, policy=None, now=None):
    if len(raw) > MAX_LICENSE_BYTES:
        raise ValueError('license_too_large')
    policy = load_policy() if policy is None else policy
    now = int(time.time()) if now is None else now
    try:
        envelope = json.loads(raw)
        payload = envelope['payload']
        key_id = envelope['key_id']
        key = base64.b64decode(policy['public_keys'][key_id], validate=True)
        signature = base64.b64decode(envelope['signature'], validate=True)
        Ed25519PublicKey.from_public_bytes(key).verify(signature, canonical(payload))
    except (ValueError, KeyError, TypeError, InvalidSignature):
        raise ValueError('license_signature_invalid') from None
    if (not isinstance(payload, dict) or payload.get('schema') != 1
            or payload.get('product') != 'karrierekrake'
            or payload.get('environment') != policy['environment']
            or not re.fullmatch(r'[a-zA-Z0-9_-]{8,128}', str(payload.get('license_id', '')))
            or type(payload.get('revision')) is not int or payload['revision'] < 1
            or type(payload.get('issued_at')) is not int or type(payload.get('expires_at')) is not int
            or not payload['issued_at'] - 300 <= now < payload['expires_at']
            or not 0 < payload['expires_at'] - payload['issued_at'] <= MAX_OFFLINE_SECONDS
            or not isinstance(payload.get('features'), list)
            or any(feature not in PAID_FEATURES for feature in payload['features'])):
        raise ValueError('license_invalid_or_expired')
    return payload


def license_path():
    return user_data_dir() / 'commerce/license.json'


def import_license(path: Path, *, policy=None, destination=None, now=None):
    path = Path(path)
    if path.stat().st_size > MAX_LICENSE_BYTES:
        raise ValueError('license_too_large')
    raw = path.read_bytes()
    policy = load_policy() if policy is None else policy
    payload = verify_license(raw, policy=policy, now=now)
    destination = Path(destination) if destination else license_path()
    if destination.exists():
        # Expiry must not allow an older signed grant to replace a newer revoke.
        try:
            previous_raw = destination.read_bytes()
            previous = json.loads(previous_raw)['payload']
            verify_license(previous_raw, policy=policy, now=previous['issued_at'])
        except (ValueError, KeyError, TypeError):
            raise ValueError('existing_license_unreadable') from None
        if (previous['license_id'] != payload['license_id']
                or payload['revision'] < previous['revision']
                or (payload['revision'] == previous['revision'] and canonical(payload) != canonical(previous))):
            raise ValueError('license_revision_conflict')
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.license-', dir=destination.parent)
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return payload


def current_license(*, policy=None):
    try:
        path = license_path()
        if path.stat().st_size > MAX_LICENSE_BYTES:
            return None
        return verify_license(path.read_bytes(), policy=policy)
    except (OSError, ValueError, KeyError, TypeError):
        return None


def feature_allowed(feature):
    if feature in FREE_FEATURES:
        return True
    try:
        policy = load_policy()
        payload = current_license(policy=policy)
        # Sandbox entitlements are visible in Settings but never unlock production.
        return bool(policy['environment'] == 'production' and feature in policy['enabled_features']
                    and payload and feature in payload['features'])
    except (OSError, ValueError, KeyError, TypeError):
        return False
