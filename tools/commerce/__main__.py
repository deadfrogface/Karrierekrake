"""Operator CLI: python -m tools.commerce --help. Never run on an end-user device."""
from __future__ import annotations
import argparse
import base64
import json
import os
from pathlib import Path
import sqlite3
import hashlib
from tools.commerce.paddle import PaddleClient
from tools.commerce.issuer import issue


def mutation_once(journal, operation_id, request, operation):
    """A timed-out payment mutation is not retried blindly (no duplicate order)."""
    if not operation_id:
        raise ValueError('operation_id_required')
    journal.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(journal)
    fingerprint = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()
    try:
        with conn:
            conn.execute('CREATE TABLE IF NOT EXISTS mutations (id TEXT PRIMARY KEY, fingerprint TEXT, status TEXT, provider_id TEXT)')
            if conn.execute('SELECT 1 FROM mutations WHERE id=?', (operation_id,)).fetchone():
                raise ValueError('operation_already_attempted_reconcile_in_provider_dashboard')
            conn.execute('INSERT INTO mutations VALUES (?, ?, ?, ?)', (operation_id, fingerprint, 'pending', ''))
        result = operation()
        with conn:
            conn.execute('UPDATE mutations SET status=?, provider_id=? WHERE id=?', ('completed', result.get('id', ''), operation_id))
        return result
    finally:
        conn.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--environment', choices=['sandbox', 'production'], default='sandbox')
    parser.add_argument('--allow-production', action='store_true')
    parser.add_argument('--journal', type=Path, default=Path.home() / '.karrierekrake-operator/commerce.sqlite3')
    parser.add_argument('--operation-id')
    sub = parser.add_subparsers(dest='command', required=True)
    keygen = sub.add_parser('keygen'); keygen.add_argument('--private-key', type=Path, required=True)
    checkout = sub.add_parser('checkout'); checkout.add_argument('--price-id', required=True)
    cancel = sub.add_parser('cancel'); cancel.add_argument('--subscription-id', required=True); cancel.add_argument('--immediate', action='store_true')
    refund = sub.add_parser('refund'); refund.add_argument('--transaction-id', required=True); refund.add_argument('--reason', required=True)
    portal = sub.add_parser('portal'); portal.add_argument('--customer-id', required=True); portal.add_argument('--subscription-id', required=True)
    sign = sub.add_parser('license'); sign.add_argument('--transaction-id', required=True)
    sign.add_argument('--private-key', type=Path, required=True); sign.add_argument('--key-id', required=True)
    sign.add_argument('--feature', action='append', required=True); sign.add_argument('--price-id', action='append', required=True)
    sign.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == 'keygen':
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives import serialization
        if args.private_key.resolve().is_relative_to(Path(__file__).resolve().parents[2]):
            raise ValueError('private_key_must_be_outside_repository')
        key = Ed25519PrivateKey.generate()
        args.private_key.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(args.private_key, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as handle:
            handle.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        print(json.dumps({'public_key': base64.b64encode(key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode()}))
        return 0
    if args.environment == 'production' and not args.allow_production:
        raise ValueError('explicit_production_authorization_required')
    client = PaddleClient(os.environ.get('PADDLE_API_KEY', ''), environment=args.environment)
    try:
        if args.command == 'license':
            result = issue(client, args.transaction_id, private_key=args.private_key, key_id=args.key_id,
                           features=args.feature, accepted_prices=args.price_id, journal=args.journal, output=args.output)
        elif args.command == 'portal':
            result = client.portal(args.customer_id, args.subscription_id)
        else:
            operations = {'checkout': lambda: client.checkout(args.price_id),
                          'cancel': lambda: client.cancel(args.subscription_id, immediate=args.immediate),
                          'refund': lambda: client.refund(args.transaction_id, args.reason)}
            request = {key: str(value) for key, value in vars(args).items() if key not in {'journal', 'operation_id'}}
            result = mutation_once(args.journal, args.operation_id, request, operations[args.command])
            # Output only workflow result fields, never the customer/financial payload.
            result = {key: result[key] for key in ('id', 'status', 'checkout', 'scheduled_change') if key in result}
        print(json.dumps(result))
        return 0
    finally:
        client.close()


if __name__ == '__main__':
    raise SystemExit(main())
