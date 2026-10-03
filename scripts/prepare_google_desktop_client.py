"""Provision the registered public Desktop OAuth identity from a build secret."""
from __future__ import annotations
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / 'assets/oauth/desktop_client.json'


def validate_client(raw: str) -> dict:
    try:
        data = json.loads(raw)
        if set(data) != {'installed'} or not isinstance(data['installed'], dict):
            raise ValueError
        client = data['installed']
        allowed = {'client_id', 'project_id', 'auth_uri', 'token_uri',
                   'auth_provider_x509_cert_url', 'client_secret', 'redirect_uris'}
        if set(client) - allowed:
            raise ValueError
        if not all(isinstance(client.get(k), str) and client[k].strip()
                   for k in ('client_id', 'client_secret', 'auth_uri', 'token_uri')):
            raise ValueError
        if not client['client_id'].endswith('.apps.googleusercontent.com'):
            raise ValueError
        if client['auth_uri'] not in ('https://accounts.google.com/o/oauth2/auth',
                                      'https://accounts.google.com/o/oauth2/v2/auth'):
            raise ValueError
        if client['token_uri'] != 'https://oauth2.googleapis.com/token':
            raise ValueError
    except (ValueError, TypeError, KeyError):
        raise ValueError('Expected Google Desktop client JSON; web clients, user tokens and service-account keys are rejected') from None
    return data


def main() -> int:
    raw = os.environ.get('GOOGLE_DESKTOP_CLIENT_JSON', '')
    if not raw:
        raise SystemExit('Missing repository Actions secret GOOGLE_DESKTOP_CLIENT_JSON; refusing to build an EXE without Google account setup')
    try:
        data = validate_client(raw)
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
    print('Google Desktop client provisioned for EXE packaging')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
