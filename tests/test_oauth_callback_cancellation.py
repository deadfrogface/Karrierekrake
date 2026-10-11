from unittest.mock import Mock
import socket
import pytest

from integrations.oauth_callback import OAuthCancelled, run_google_callback
from integrations.mail.microsoft.oauth_pkce import run_local_pkce_login
from integrations.providers.enums import ProviderError


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def assert_released(port):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', port))


def test_google_cancellation_releases_listener_without_token_exchange():
    flow = Mock()
    flow.authorization_url.return_value = ('https://example.org', 'state')
    calls = iter([False, True])
    port = free_port()
    with pytest.raises(OAuthCancelled):
        run_google_callback(flow, cancelled=lambda: next(calls), port=port, open_browser=False)
    assert_released(port)
    flow.fetch_token.assert_not_called()


def test_google_timeout_releases_listener():
    flow = Mock()
    flow.authorization_url.return_value = ('https://example.org', 'state')
    port = free_port()
    with pytest.raises(OAuthCancelled):
        run_google_callback(flow, cancelled=lambda: False, port=port,
                            open_browser=False, timeout_seconds=0)
    assert_released(port)
    flow.fetch_token.assert_not_called()


def test_microsoft_timeout_is_not_state_mismatch():
    port = free_port()
    with pytest.raises(ProviderError, match='oauth_timeout'):
        run_local_pkce_login(client_id='test', scopes=['openid'], redirect_port=port,
                             open_browser=False, timeout_s=0)
    assert_released(port)


def test_microsoft_browser_failure_releases_listener(monkeypatch):
    from integrations.mail.microsoft import oauth_pkce as oauth
    port = free_port()
    monkeypatch.setattr(oauth, 'open_system_browser', Mock(side_effect=RuntimeError('browser failed')))
    with pytest.raises(RuntimeError, match='browser failed'):
        run_local_pkce_login(client_id='test', scopes=['openid'], redirect_port=port)
    assert_released(port)
