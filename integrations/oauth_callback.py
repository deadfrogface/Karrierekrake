"""Cancellable Google loopback callback; token/state/PKCE validation stays in OAuthlib."""
from __future__ import annotations

import time
import webbrowser
from wsgiref.simple_server import make_server, WSGIRequestHandler, WSGIServer
from wsgiref.util import request_uri


class OAuthCancelled(Exception):
    pass


class _QuietHandler(WSGIRequestHandler):
    def log_message(self, format, *args):
        # Callback URLs contain authorization codes, never log them.
        pass


def run_google_callback(flow, *, cancelled, port, open_browser=True,
                        timeout_seconds=180, **authorization_kwargs):
    if cancelled():
        raise OAuthCancelled()
    callback = []

    def app(environ, start_response):
        if environ.get('PATH_INFO') != '/':
            start_response('404 Not Found', [('Content-Type', 'text/plain')])
            return [b'Not found']
        callback.append(request_uri(environ))
        start_response('200 OK', [('Content-Type', 'text/plain; charset=utf-8')])
        return ['Karrierekrake: Sie können dieses Fenster schließen.'.encode()]

    class ExclusiveServer(WSGIServer):
        allow_reuse_address = False

        def get_request(self):
            connection, address = super().get_request()
            connection.settimeout(1.0)
            return connection, address

    with make_server('127.0.0.1', port, app, server_class=ExclusiveServer,
                     handler_class=_QuietHandler) as server:
        flow.redirect_uri = f'http://localhost:{server.server_port}/'
        url, _ = flow.authorization_url(**authorization_kwargs)
        if open_browser and not webbrowser.open(url, new=1, autoraise=True):
            raise RuntimeError('oauth_browser_unavailable')
        server.timeout = 0.25
        deadline = time.monotonic() + timeout_seconds
        while not callback:
            if cancelled() or time.monotonic() >= deadline:
                raise OAuthCancelled()
            server.handle_request()
        if cancelled():
            raise OAuthCancelled()
        # Only rewrite the loopback scheme, never other occurrences in query data.
        response = callback[0].replace('http://', 'https://', 1)
        flow.fetch_token(authorization_response=response, timeout=30)
        if cancelled():
            raise OAuthCancelled()
        return flow.credentials
