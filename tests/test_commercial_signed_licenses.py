"""Offline regression cases; no provider requests or merchant credentials."""
import base64
import json
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from core.commercial.license_file import canonical, verify_license, import_license
from tools.commerce.issuer import paid_until
from tools.commerce.__main__ import mutation_once


@pytest.fixture
def signed():
    key = Ed25519PrivateKey.generate()
    policy = {'environment': 'sandbox', 'public_keys': {'test': base64.b64encode(
        key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()}}
    def envelope(revision=1, **changes):
        payload = {'schema': 1, 'product': 'karrierekrake', 'environment': 'sandbox',
                   'license_id': 'synthetic-license', 'revision': revision, 'issued_at': 1000,
                   'expires_at': 2000, 'features': ['ad_free']}
        payload.update(changes)
        return json.dumps({'key_id': 'test', 'payload': payload,
            'signature': base64.b64encode(key.sign(canonical(payload))).decode()}).encode()
    return policy, envelope


def test_signature_expiry_and_environment(signed):
    policy, envelope = signed
    raw = envelope()
    assert verify_license(raw, policy=policy, now=1500)['revision'] == 1
    with pytest.raises(ValueError):
        verify_license(raw.replace(b'ad_free', b'cloud_models'), policy=policy, now=1500)
    with pytest.raises(ValueError):
        verify_license(raw, policy=policy, now=2000)
    with pytest.raises(ValueError):
        verify_license(raw, policy={**policy, 'environment': 'production'}, now=1500)


def test_revoke_cannot_be_replaced_by_older_grant(signed, tmp_path):
    policy, envelope = signed
    source, installed = tmp_path / 'incoming.json', tmp_path / 'installed.json'
    source.write_bytes(envelope(2, features=[]))
    import_license(source, policy=policy, destination=installed, now=1500)
    before = installed.read_bytes()
    source.write_bytes(envelope(1))
    with pytest.raises(ValueError, match='revision_conflict'):
        import_license(source, policy=policy, destination=installed, now=1500)
    assert installed.read_bytes() == before


def test_ambiguous_provider_result_is_not_retried(tmp_path):
    journal = tmp_path / 'journal.sqlite3'
    calls = []
    def timeout():
        calls.append(1)
        raise TimeoutError('response lost after possible payment mutation')
    with pytest.raises(TimeoutError):
        mutation_once(journal, 'synthetic-order', {'price': 'example'}, timeout)
    with pytest.raises(ValueError, match='already_attempted'):
        mutation_once(journal, 'synthetic-order', {'price': 'example'}, timeout)
    assert calls == [1]


def test_refunded_or_stale_payment_never_grants_new_period():
    subscription = {'id': 'sub_' + 'a'*26, 'customer_id': 'ctm_' + 'b'*26, 'status': 'active',
                    'current_billing_period': {'ends_at': '2026-03-01T00:00:00Z'}}
    transaction = {'id': 'txn_' + 'c'*26, 'subscription_id': subscription['id'],
                   'customer_id': subscription['customer_id'], 'status': 'completed',
                   'items': [{'price': {'id': 'pri_example'}}], 'adjustments': [],
                   'billing_period': {'ends_at': '2026-01-01T00:00:00Z'}}
    now = 1769904000  # 2026-02-01 UTC
    assert paid_until(transaction, subscription, now=now, accepted_prices={'pri_example'}) == now
    transaction['billing_period']['ends_at'] = '2026-03-01T00:00:00Z'
    assert paid_until(transaction, subscription, now=now, accepted_prices={'pri_example'}) > now
    transaction['adjustments'] = [{'action': 'refund', 'status': 'pending_approval'}]
    assert paid_until(transaction, subscription, now=now, accepted_prices={'pri_example'}) == now
