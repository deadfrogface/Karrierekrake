"""Free Outlook IMAP uses OAuth, not Graph or SMTP permissions."""
import time
import httpx
from integrations.providers.enums import ProviderError

IMAP_SCOPE = 'https://outlook.office.com/IMAP.AccessAsUser.All'


def login_outlook(secret):
    from integrations.mail.microsoft.oauth_pkce import run_local_pkce_login
    tokens = run_local_pkce_login(client_id=secret['client_id'],
        scopes=[IMAP_SCOPE, 'offline_access'], redirect_host='localhost',
        redirect_port=8765, redirect_path='/oauth/callback', open_browser=True)
    secret.update(tokens)
    secret['expires_at'] = time.time() + int(tokens.get('expires_in', 3600))
    return secret


def refresh_outlook(secret, *, token_dir):
    if not secret.get('oauth2') or not secret.get('client_id'):
        return secret
    if secret.get('access_token') and float(secret.get('expires_at', 0)) > time.time() + 60:
        return secret
    try:
        response = httpx.post('https://login.microsoftonline.com/common/oauth2/v2.0/token',
            data={'client_id': secret['client_id'], 'grant_type': 'refresh_token',
                  'refresh_token': secret['refresh_token'], 'scope': IMAP_SCOPE + ' offline_access'}, timeout=20)
        response.raise_for_status()
        tokens = response.json()
        if not tokens.get('access_token'):
            raise ValueError('no_token')
        secret = dict(secret, **tokens)
        secret['expires_at'] = time.time() + int(tokens.get('expires_in', 3600))
        from integrations.mail.imap.adapter import store_imap_secret
        store_imap_secret(secret, token_dir=token_dir)
        return secret
    except Exception:
        raise ProviderError('generic_imap', 'outlook_reconnect_required') from None
