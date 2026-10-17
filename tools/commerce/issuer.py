"""Sign only freshly reconciled provider state. No unsigned local payment flags."""
from __future__ import annotations
import base64
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from core.commercial.license_file import canonical, MAX_OFFLINE_SECONDS
from core.commercial.release_policy import PAID_FEATURES
from tools.commerce.paddle import paddle_id


def paid_until(transaction, subscription, *, now, accepted_prices):
    paddle_id(transaction['id'], 'txn')
    paddle_id(subscription['id'], 'sub')
    paddle_id(transaction.get('customer_id'), 'ctm')
    paddle_id(subscription.get('customer_id'), 'ctm')
    if transaction.get('subscription_id') != subscription['id'] or transaction.get('customer_id') != subscription.get('customer_id'):
        raise ValueError('payment_subscription_mismatch')
    if transaction.get('status') != 'completed' or subscription.get('status') != 'active':
        return now  # revoked/paused/past_due never produce a grant
    prices = {item.get('price', {}).get('id') for item in transaction.get('items', [])}
    if not prices.intersection(accepted_prices):
        raise ValueError('payment_product_not_configured')
    adjustments = transaction.get('adjustments')
    if not isinstance(adjustments, list):
        raise ValueError('payment_adjustments_missing')
    if any(item.get('action') in ('refund', 'chargeback', 'chargeback_warning')
           and item.get('status') in ('approved', 'pending_approval') for item in adjustments):
        return now
    def timestamp(value):
        date = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if date.tzinfo is None:
            raise ValueError('payment_date_missing_timezone')
        return int(date.timestamp())
    period = subscription.get('current_billing_period') or {}
    paid_period = transaction.get('billing_period') or {}
    # An old completed transaction is not proof that the current renewal was paid.
    end = min(timestamp(period['ends_at']), timestamp(paid_period['ends_at']), now + MAX_OFFLINE_SECONDS)
    change = subscription.get('scheduled_change') or {}
    if change.get('action') in ('cancel', 'pause'):
        end = min(end, timestamp(change['effective_at']))
    return max(now, end)


def issue(client, transaction_id, *, private_key, key_id, features, accepted_prices, journal, output):
    if not features or any(feature not in PAID_FEATURES for feature in features) or not accepted_prices:
        raise ValueError('configure_features_and_prices')
    transaction = client.transaction(transaction_id)
    subscription = client.subscription(paddle_id(transaction.get('subscription_id'), 'sub'))
    now = int(time.time())
    expires = paid_until(transaction, subscription, now=now, accepted_prices=set(accepted_prices))
    license_id = hashlib.sha256((client.environment + ':' + subscription['id']).encode()).hexdigest()
    key = load_pem_private_key(Path(private_key).read_bytes(), password=None)
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError('ed25519_key_required')
    journal, output = Path(journal), Path(output)
    journal.parent.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(journal)
    try:
        with conn:
            conn.execute('CREATE TABLE IF NOT EXISTS revisions (license_id TEXT PRIMARY KEY, revision INTEGER NOT NULL)')
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute('SELECT revision FROM revisions WHERE license_id=?', (license_id,)).fetchone()
            revision = (row[0] if row else 0) + 1
            payload = {'schema': 1, 'product': 'karrierekrake', 'environment': client.environment,
                       'license_id': license_id, 'revision': revision, 'issued_at': now,
                       'expires_at': expires if expires > now else now + MAX_OFFLINE_SECONDS,
                       'features': sorted(set(features)) if expires > now else []}
            envelope = {'key_id': key_id, 'payload': payload,
                        'signature': base64.b64encode(key.sign(canonical(payload))).decode()}
            fd, temp = tempfile.mkstemp(prefix='.signed-license-', dir=output.parent)
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as handle:
                    json.dump(envelope, handle, indent=2)
                    handle.flush()
                    os.fsync(handle.fileno())
                conn.execute('INSERT OR REPLACE INTO revisions VALUES (?, ?)', (license_id, revision))
                # Persist revision before output; a crash may skip a number, never reuse it.
                conn.commit()
                os.replace(temp, output)
            finally:
                Path(temp).unlink(missing_ok=True)
        return {'license_id': license_id, 'revision': revision, 'granted': bool(payload['features'])}
    finally:
        conn.close()
