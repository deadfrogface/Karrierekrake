"""Loopback HTTPS CalDAV integration; synthetic server/account, never a user account."""
from datetime import datetime, timedelta, timezone
import ipaddress
import socket
import subprocess
import sys
import time

import pytest


@pytest.fixture
def caldav_server(tmp_path, monkeypatch):
    pytest.importorskip("radicale")
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(days=1))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), False)
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), True)
            .sign(key, hashes.SHA256()))
    certfile, keyfile = tmp_path / "test-cert.pem", tmp_path / "test-key.pem"
    certfile.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    keyfile.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    config = tmp_path / "radicale.ini"
    config.write_text(f"[server]\nhosts = 127.0.0.1:{port}\nssl = true\ncertificate = {certfile.as_posix()}\nkey = {keyfile.as_posix()}\n[auth]\ntype = none\n[storage]\nfilesystem_folder = {(tmp_path / 'store').as_posix()}\n[logging]\nlevel = warning\n")
    monkeypatch.setenv("REQUESTS_CA_BUNDLE", str(certfile))
    with (tmp_path / "server.log").open("wb") as log:
        proc = subprocess.Popen([sys.executable, "-m", "radicale", "--config", str(config)], stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + 15
            while True:
                if proc.poll() is not None:
                    pytest.fail("local CalDAV server exited")
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=.2):
                        break
                except OSError:
                    if time.monotonic() > deadline:
                        pytest.fail("local CalDAV startup timed out")
                    time.sleep(.05)
            yield f"https://localhost:{port}/"
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)


def test_discover_recurrence_exception_create_and_retry(caldav_server):
    from caldav import DAVClient
    from integrations.calendar.caldav.client import LiveCaldavClient
    secret = {"base_url": caldav_server, "username": "synthetic", "password": "test-only"}
    with DAVClient(url=caldav_server, username="synthetic", password="test-only") as setup:
        calendar = setup.principal().make_calendar(name="Synthetic interviews")
        calendar.save_event("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:series\r\nDTSTAMP:20261001T120000Z\r\nDTSTART:20261005T100000Z\r\nDTEND:20261005T110000Z\r\nRRULE:FREQ=DAILY;COUNT=3\r\nEXDATE:20261006T100000Z\r\nSUMMARY:Synthetic private title\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n")
        secret["calendar_path"] = str(calendar.url)
    client = LiveCaldavClient(secret)
    assert client.discover_calendars() == [secret["calendar_path"]]
    busy = client.list_busy(time_min=datetime(2026,10,5,tzinfo=timezone.utc), time_max=datetime(2026,10,8,tzinfo=timezone.utc))
    assert busy == [{"start":"2026-10-05T10:00:00+00:00", "end":"2026-10-05T11:00:00+00:00"},
                    {"start":"2026-10-07T10:00:00+00:00", "end":"2026-10-07T11:00:00+00:00"}]
    event = "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:new\r\nDTSTAMP:20261001T120000Z\r\nDTSTART:20261005T120000Z\r\nDTEND:20261005T130000Z\r\nSUMMARY:Synthetic interview\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
    first = client.put_event(href="new.ics", ics=event)
    second = client.put_event(href="new.ics", ics=event)
    assert first == second
