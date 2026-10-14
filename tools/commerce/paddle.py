"""Paddle Billing operator client. No merchant credentials in desktop releases."""
from __future__ import annotations
import hashlib
import hmac
import json
import re
import time
import httpx


def paddle_id(value, prefix):
    if not isinstance(value, str) or not re.fullmatch(prefix + r'_[a-z0-9]{26}', value):
        raise ValueError('invalid_paddle_id')
    return value


class PaddleError(RuntimeError):
    pass


class PaddleClient:
    def __init__(self, api_key, *, environment='sandbox', transport=None):
        if environment not in ('sandbox', 'production') or not isinstance(api_key, str) or not api_key.strip():
            raise ValueError('paddle_credentials_required')
        self.environment = environment
        self.base = 'https://sandbox-api.paddle.com' if environment == 'sandbox' else 'https://api.paddle.com'
        self.client = httpx.Client(headers={'Authorization': 'Bearer ' + api_key, 'Paddle-Version': '1'},
                                   timeout=30, follow_redirects=False, trust_env=False, transport=transport)

    def close(self):
        self.client.close()

    def request(self, method, path, payload=None, params=None):
        try:
            with self.client.stream(method, self.base + path, json=payload, params=params) as response:
                if response.status_code >= 300:
                    raise PaddleError('paddle_http_' + str(response.status_code))
                raw = bytearray()
                for block in response.iter_bytes():
                    raw.extend(block)
                    if len(raw) > 2 * 1024**2:
                        raise PaddleError('paddle_response_too_large')
            value = json.loads(raw)
            if not isinstance(value, dict) or 'data' not in value:
                raise PaddleError('paddle_invalid_response')
            return value['data']
        except (httpx.HTTPError, ValueError):
            # Do not leak headers, URLs or customer response bodies in errors.
            raise PaddleError('paddle_connection_or_response_failed') from None

    def transaction(self, transaction_id):
        return self.request('GET', '/transactions/' + paddle_id(transaction_id, 'txn'), params={'include': 'adjustments'})

    def subscription(self, subscription_id):
        return self.request('GET', '/subscriptions/' + paddle_id(subscription_id, 'sub'))

    def checkout(self, price_id):
        return self.request('POST', '/transactions', {'items': [{'price_id': paddle_id(price_id, 'pri'), 'quantity': 1}],
                                                       'collection_mode': 'automatic'})

    def cancel(self, subscription_id, *, immediate=False):
        return self.request('POST', '/subscriptions/' + paddle_id(subscription_id, 'sub') + '/cancel',
                            {'effective_from': 'immediately' if immediate else 'next_billing_period'})

    def refund(self, transaction_id, reason):
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 512:
            raise ValueError('refund_reason_required')
        return self.request('POST', '/adjustments', {'action': 'refund', 'type': 'full',
                            'transaction_id': paddle_id(transaction_id, 'txn'), 'reason': reason})

    def portal(self, customer_id, subscription_id):
        return self.request('POST', '/customers/' + paddle_id(customer_id, 'ctm') + '/portal-sessions',
                            {'subscription_ids': [paddle_id(subscription_id, 'sub')]})


def verify_webhook(raw, signature_header, secret, *, now=None, tolerance=300):
    """Authenticate exact incoming bytes, never parsed/reformatted JSON."""
    if (not isinstance(raw, bytes) or len(raw) > 2 * 1024**2 or not isinstance(secret, str) or not secret
            or not isinstance(signature_header, str) or len(signature_header) > 8192):
        raise ValueError('invalid_webhook')
    parts = [part.strip().split('=', 1) for part in signature_header.split(';')]
    if any(len(part) != 2 for part in parts):
        raise ValueError('invalid_webhook_signature')
    timestamps = [value for key, value in parts if key == 'ts']
    signatures = [value for key, value in parts if key == 'h1' and re.fullmatch(r'[0-9a-f]{64}', value)]
    if len(timestamps) != 1 or not timestamps[0].isdigit():
        raise ValueError('invalid_webhook_signature')
    timestamp = int(timestamps[0])
    now = int(time.time()) if now is None else now
    if abs(now - timestamp) > tolerance:
        raise ValueError('expired_webhook_signature')
    expected = hmac.new(secret.encode(), timestamps[0].encode() + b':' + raw, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, value) for value in signatures):
        raise ValueError('invalid_webhook_signature')
    event = json.loads(raw)
    if not isinstance(event, dict) or not event.get('event_id') or not event.get('occurred_at'):
        raise ValueError('invalid_webhook_event')
    return event
