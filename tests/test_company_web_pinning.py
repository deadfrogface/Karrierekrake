"""F10: the public-address check must bind to the TCP connection actually made (no DNS rebinding)."""
import datetime
import http.server
import socket
import ssl
import threading

import httpcore
import httpx
import pytest

from search import company_web as web

PUBLIC = '93.184.216.34'
BLOCKED = ['127.0.0.1', '10.0.0.5', '172.16.0.1', '192.168.1.5', '100.64.0.1', '0.0.0.0',
           '169.254.169.254', '::1', '::', 'fd00::1', 'fd00:ec2::254', 'fe80::1%3', 'ff0e::1',
           '::ffff:127.0.0.1', '::ffff:169.254.169.254', '64:ff9b::a9fe:a9fe', '2002:7f00:1::']


def fake_dns(monkeypatch, table):
    """table: host -> list of answers; each lookup pops the next answer (last one sticks)."""
    lookups = []
    real = socket.getaddrinfo

    def getaddrinfo(host, port, *args, **kwargs):
        if host not in table and host == '127.0.0.1':
            return real(host, port, *args, **kwargs)  # the local test server behind the fake connect
        lookups.append(host)
        answers = table[host]
        ip = answers.pop(0) if len(answers) > 1 else answers[0]
        family = socket.AF_INET6 if ':' in ip else socket.AF_INET
        return [(family, socket.SOCK_STREAM, 6, '', (ip, port))]
    monkeypatch.setattr(socket, 'getaddrinfo', getaddrinfo)
    return lookups


@pytest.fixture
def connects(monkeypatch):
    """Record every real TCP target; route it to a local server (or fail) instead of the internet."""
    state = {'targets': [], 'server': None}
    real = httpcore.SyncBackend.connect_tcp

    def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        state['targets'].append(host)
        if state['server'] is None:
            raise httpcore.ConnectError('offline test')
        return real(self, '127.0.0.1', state['server'], timeout=timeout)
    monkeypatch.setattr(httpcore.SyncBackend, 'connect_tcp', connect_tcp)
    return state


def serve(handler_cls, tls_context=None):
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler_cls)
    if tls_context is not None:
        server.socket = tls_context.wrap_socket(server.socket, server_side=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


class Redirect(http.server.BaseHTTPRequestHandler):
    location = 'http://intern.example/'

    def do_GET(self):
        Redirect.hosts.append(self.headers['Host'])
        if self.headers['Host'] == 'firma.example':
            self.send_response(302)
            self.send_header('Location', self.location)
            self.send_header('Content-Length', '0')
            self.end_headers()
        else:
            self.send_response(200)
            self.send_header('Content-Length', '2')
            self.end_headers()
            self.wfile.write(b'ok')

    def log_message(self, *args):
        pass


@pytest.mark.parametrize('ip', BLOCKED)
def test_is_public_ip_rejects_internal_ranges(ip):
    assert not web.is_public_ip(ip)


@pytest.mark.parametrize('ip', [PUBLIC, '2606:2800:220:1:248:1893:25c8:1946', '::ffff:93.184.216.34'])
def test_is_public_ip_accepts_global_unicast(ip):
    assert web.is_public_ip(ip)


@pytest.mark.parametrize('rebound', BLOCKED)
def test_dns_rebinding_never_reaches_internal_address(monkeypatch, connects, rebound):
    # First lookup (public_url pre-check) is public, the connection-time lookup rebinds.
    fake_dns(monkeypatch, {'firma.example': [PUBLIC, rebound]})
    pages = web.PublicPages()
    try:
        with pytest.raises(ValueError, match='non_public'):
            pages._read('https://firma.example/karriere', check_robots=False)
    finally:
        pages.close()
    assert connects['targets'] == []


def test_mixed_answer_with_one_private_address_is_refused(monkeypatch, connects):
    monkeypatch.setattr(socket, 'getaddrinfo', lambda h, p, *a, **k: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, '', (PUBLIC, p)),
        (socket.AF_INET6, socket.SOCK_STREAM, 6, '', ('fd00::1', p, 0, 0))])
    with web.public_client() as client, pytest.raises(ValueError, match='non_public'):
        client.get('https://firma.example/')
    assert connects['targets'] == []


@pytest.mark.parametrize('location, host, ip', [
    ('http://intern.example/admin', 'intern.example', '10.0.0.5'),
    ('http://metadata.example/latest/meta-data/', 'metadata.example', '169.254.169.254'),
    ('http://v6.example/', 'v6.example', 'fd00::1'),
    ('http://169.254.169.254/latest/meta-data/', '169.254.169.254', '169.254.169.254'),
])
def test_redirect_to_private_address_is_blocked(monkeypatch, connects, location, host, ip):
    Redirect.hosts, Redirect.location = [], location
    server = serve(Redirect)
    connects['server'] = server.server_address[1]
    fake_dns(monkeypatch, {'firma.example': [PUBLIC], host: [ip]})
    pages = web.PublicPages()
    try:
        with pytest.raises(ValueError, match='non_public'):
            pages._read('http://firma.example/', check_robots=False)
    finally:
        pages.close()
        server.shutdown()
    assert connects['targets'] == [PUBLIC] and Redirect.hosts == ['firma.example']


def test_redirect_to_public_host_is_followed_on_pinned_ip(monkeypatch, connects):
    Redirect.hosts, Redirect.location = [], 'http://jobs.example/'
    server = serve(Redirect)
    connects['server'] = server.server_address[1]
    fake_dns(monkeypatch, {'firma.example': [PUBLIC], 'jobs.example': ['2606:2800:220:1:248:1893:25c8:1946']})
    pages = web.PublicPages()
    try:
        assert pages._read('http://firma.example/', check_robots=False) == ('ok', 'http://jobs.example/')
    finally:
        pages.close()
        server.shutdown()
    assert connects['targets'] == [PUBLIC, '2606:2800:220:1:248:1893:25c8:1946']
    assert Redirect.hosts == ['firma.example', 'jobs.example']


def test_environment_proxy_is_ignored(monkeypatch, connects):
    for name in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy'):
        monkeypatch.setenv(name, 'http://proxy.example:8080')
    fake_dns(monkeypatch, {'firma.example': [PUBLIC], 'proxy.example': ['10.0.0.9']})
    with web.public_client() as client:
        assert not client._mounts
        with pytest.raises(httpx.ConnectError):
            client.get('https://firma.example/')
    assert connects['targets'] == [PUBLIC]


def _tls_material(tmp_path, hostname):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    now = datetime.datetime.now(datetime.UTC)
    ca_key, key = ec.generate_private_key(ec.SECP256R1()), ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Karrierekrake Test CA')])
    ca = (x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name)
          .public_key(ca_key.public_key()).serial_number(1)
          .not_valid_before(now - datetime.timedelta(days=1)).not_valid_after(now + datetime.timedelta(days=1))
          .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
          .sign(ca_key, hashes.SHA256()))
    leaf = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hostname)]))
            .issuer_name(ca_name).public_key(key.public_key()).serial_number(2)
            .not_valid_before(now - datetime.timedelta(days=1)).not_valid_after(now + datetime.timedelta(days=1))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(hostname)]), critical=False)
            .sign(ca_key, hashes.SHA256()))
    cert, keyfile = tmp_path / 'leaf.pem', tmp_path / 'leaf.key'
    cert.write_bytes(leaf.public_bytes(serialization.Encoding.PEM))
    keyfile.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                          serialization.NoEncryption()))
    server_ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    server_ctx.load_cert_chain(cert, keyfile)
    client_ctx = ssl.create_default_context(cadata=ca.public_bytes(serialization.Encoding.PEM).decode())
    return server_ctx, client_ctx


def test_https_on_pinned_ip_still_verifies_certificate_against_hostname(monkeypatch, connects, tmp_path):
    server_ctx, client_ctx = _tls_material(tmp_path, 'firma.example')
    sni = []
    server_ctx.sni_callback = lambda sock, name, ctx: sni.append(name)
    Redirect.hosts = []
    server = serve(Redirect, server_ctx)
    connects['server'] = server.server_address[1]
    fake_dns(monkeypatch, {'firma.example': [PUBLIC], 'andere.example': [PUBLIC]})
    try:
        with web.public_client(ssl_context=client_ctx) as client:
            response = client.get('https://firma.example/')
            assert response.status_code == 302 and Redirect.hosts == ['firma.example']
            # Same pinned IP and server, but the certificate does not cover this hostname.
            with pytest.raises(httpx.ConnectError, match='(?i)certificate|hostname'):
                client.get('https://andere.example/')
    finally:
        server.shutdown()
    assert set(connects['targets']) == {PUBLIC}
    assert 'firma.example' in sni and 'andere.example' in sni
