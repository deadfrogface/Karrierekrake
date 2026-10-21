"""T01.10: no network and no outgoing mail for the synthetic account.

Every test in this module runs under ``NetworkGuard``: ``socket.socket.connect``,
``socket.socket.connect_ex``, ``socket.socket.sendto``, ``socket.socket.sendmsg``
(where the platform has it), ``socket.create_connection`` and
``socket.getaddrinfo`` are patched; every IP/DNS attempt (TCP and UDP) is
recorded and turned into ``BlockedNetworkAccess``. The IMAP stand-in used by the T01.10
tests replaces ``imaplib.IMAP4_SSL`` in-process and opens no socket at all,
so loopback is blocked as well and the expected total is 0 attempts
(gold ``defaults.network_attempts``).
"""

from __future__ import annotations

import ast
import ipaddress
import re
import socket
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LOOPBACK_NAMES = {"localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback"}


class BlockedNetworkAccess(RuntimeError):
    """Raised by NetworkGuard for every blocked connect / DNS lookup."""


def _host_of(address) -> str | None:
    if isinstance(address, (tuple, list)) and address:
        return str(address[0])
    return None  # AF_UNIX path or unknown: no IP network


def _is_loopback(host: str) -> bool:
    name = (host or "").strip().strip("[]").lower()
    if name in LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(name.split("%", 1)[0]).is_loopback
    except ValueError:
        return False


class NetworkGuard:
    """Records and blocks network access. Non-loopback is always blocked."""

    def __init__(self, *, allow_loopback: bool = False) -> None:
        self.allow_loopback = allow_loopback
        self.attempts: list[dict] = []

    def _check(self, api: str, host: str | None, port=None) -> None:
        if host is None:
            return  # AF_UNIX / local IPC, not an IP network
        loopback = _is_loopback(host)
        allowed = loopback and self.allow_loopback
        self.attempts.append(
            {"api": api, "host": host, "port": port, "loopback": loopback, "allowed": allowed}
        )
        if not allowed:
            raise BlockedNetworkAccess(f"T01.10 network guard: {api} to {host!r}:{port} blocked")

    def install(self, monkeypatch: pytest.MonkeyPatch) -> NetworkGuard:
        guard = self
        real_connect = socket.socket.connect
        real_connect_ex = socket.socket.connect_ex
        real_create_connection = socket.create_connection
        real_getaddrinfo = socket.getaddrinfo
        real_sendto = socket.socket.sendto
        real_sendmsg = getattr(socket.socket, "sendmsg", None)

        def connect(sock, address):
            guard._check("socket.connect", _host_of(address), (address[1] if _host_of(address) else None))
            return real_connect(sock, address)

        def connect_ex(sock, address):
            guard._check("socket.connect_ex", _host_of(address), (address[1] if _host_of(address) else None))
            return real_connect_ex(sock, address)

        def create_connection(address, *args, **kwargs):
            guard._check("socket.create_connection", _host_of(address), address[1])
            return real_create_connection(address, *args, **kwargs)

        def sendto(sock, data, *args):
            # sendto(data, address) or sendto(data, flags, address)
            address = args[-1] if args else None
            host = _host_of(address)
            guard._check("socket.sendto", host, address[1] if host else None)
            return real_sendto(sock, data, *args)

        def sendmsg(sock, buffers, *args):
            # sendmsg(buffers[, ancdata[, flags[, address]]]); no address = connected socket,
            # whose connect() already went through the guard.
            address = args[2] if len(args) >= 3 else None
            host = _host_of(address)
            guard._check("socket.sendmsg", host, address[1] if host else None)
            return real_sendmsg(sock, buffers, *args)

        def getaddrinfo(host, port, *args, **kwargs):
            guard._check("socket.getaddrinfo", "" if host is None else str(host), port)
            return real_getaddrinfo(host, port, *args, **kwargs)

        monkeypatch.setattr(socket.socket, "connect", connect)
        monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
        monkeypatch.setattr(socket.socket, "sendto", sendto)
        if real_sendmsg is not None:
            monkeypatch.setattr(socket.socket, "sendmsg", sendmsg)
        monkeypatch.setattr(socket, "create_connection", create_connection)
        monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
        return self

    def non_loopback(self) -> list[dict]:
        return [a for a in self.attempts if not a["loopback"]]

    def assert_clean(self) -> None:
        """Gold defaults.network_attempts == 0: any recorded attempt is a failure."""
        assert self.attempts == [], f"network attempts recorded: {self.attempts}"


@pytest.fixture(autouse=True)
def network_guard(monkeypatch):
    guard = NetworkGuard(allow_loopback=False).install(monkeypatch)
    yield guard
    guard.assert_clean()


def _nested_guard():
    """A second guard on top of the autouse one, for deliberate violations.

    The nested guard raises before the outer one is reached, so the outer
    (autouse) guard stays clean while this guard records the violation.
    """
    mp = pytest.MonkeyPatch()
    return mp, NetworkGuard(allow_loopback=False).install(mp)


def test_guard_turns_non_loopback_connect_into_failure():
    mp, guard = _nested_guard()
    try:
        with pytest.raises(BlockedNetworkAccess):
            socket.create_connection(("192.0.2.11", 993), timeout=0.1)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            with pytest.raises(BlockedNetworkAccess):
                sock.connect(("198.51.100.23", 993))
            with pytest.raises(BlockedNetworkAccess):
                sock.connect_ex(("203.0.113.40", 993))
        finally:
            sock.close()
        with pytest.raises(BlockedNetworkAccess):
            socket.getaddrinfo("imap.example.test", 993)
    finally:
        mp.undo()
    assert [a["api"] for a in guard.attempts] == [
        "socket.create_connection",
        "socket.connect",
        "socket.connect_ex",
        "socket.getaddrinfo",
    ]
    assert len(guard.non_loopback()) == 4
    # The guard is red on violation: the teardown check fails.
    with pytest.raises(AssertionError, match="network attempts recorded"):
        guard.assert_clean()


@pytest.mark.parametrize("host", ["127.0.0.1", "192.0.2.53"], ids=["loopback", "non-loopback"])
def test_guard_turns_udp_sendto_and_sendmsg_into_failure(host):
    """UDP is blocked like TCP, loopback included; the guard is red on violation."""
    mp, guard = _nested_guard()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    expected = ["socket.sendto", "socket.sendto"]
    try:
        with pytest.raises(BlockedNetworkAccess):
            sock.sendto(b"t0110", (host, 53))
        with pytest.raises(BlockedNetworkAccess):
            sock.sendto(b"t0110", 0, (host, 53))
        if hasattr(socket.socket, "sendmsg"):
            with pytest.raises(BlockedNetworkAccess):
                sock.sendmsg([b"t0110"], [], 0, (host, 53))
            expected.append("socket.sendmsg")
        with pytest.raises(BlockedNetworkAccess):
            socket.create_connection((host, 53), timeout=0.1)
        expected.append("socket.create_connection")
    finally:
        sock.close()
        mp.undo()
    assert [a["api"] for a in guard.attempts] == expected
    assert all(a["host"] == host and not a["allowed"] for a in guard.attempts)
    assert all(a["loopback"] is (host == "127.0.0.1") for a in guard.attempts)
    with pytest.raises(AssertionError, match="network attempts recorded"):
        guard.assert_clean()


def test_guard_blocks_imaplib_to_fixture_host_without_stand_in():
    """Without the stand-in, the real IMAP client is stopped by the guard."""
    import imaplib

    mp, guard = _nested_guard()
    try:
        with pytest.raises(BlockedNetworkAccess):
            imaplib.IMAP4_SSL("imap.example.test", 993, timeout=0.1)
    finally:
        mp.undo()
    assert guard.non_loopback() and guard.non_loopback()[0]["host"] == "imap.example.test"


def test_loopback_is_blocked_too_and_not_needed():
    mp, guard = _nested_guard()
    try:
        with pytest.raises(BlockedNetworkAccess):
            socket.create_connection(("127.0.0.1", 1143), timeout=0.1)
        with pytest.raises(BlockedNetworkAccess):
            socket.getaddrinfo("localhost", 1143)
    finally:
        mp.undo()
    assert all(a["loopback"] and not a["allowed"] for a in guard.attempts)
    assert len(guard.attempts) == 2


def test_full_t0110_flow_makes_zero_network_attempts(tmp_path, monkeypatch, network_guard):
    """Import twice, IMAP stand-in sync, slots, drafts, ICS, gates: 0 attempts.

    The IMAP stand-in replaces imaplib.IMAP4_SSL in-process, so no socket and
    no loopback connection is used at all.
    """
    from tests import test_t0110_synthetic_mail_calendar as t

    with t.frozen_reference_now():
        t.stub_guenther(monkeypatch)
        summary = t.run_full_offline_flow(tmp_path, monkeypatch)
    assert summary["imap_stand_in_hosts"] == ["imap.example.test"]
    assert summary["imap_stand_in_sessions"] == 2  # two syncs, both in-process stand-ins
    assert summary["send_transport_calls"] == 0
    assert summary["calendar_transport_calls"] == 0
    assert network_guard.attempts == []
    assert t.GOLD["defaults"]["network_attempts"] == len(network_guard.attempts)


_SMTPLIB_TEXT = re.compile(r"\bsmtplib\b")


def test_no_smtplib_import_in_product_code():
    offenders: list[str] = []
    scanned = 0
    for top in ("integrations", "core", "desktop"):
        for path in sorted((ROOT / top).rglob("*.py")):
            scanned += 1
            source = path.read_text(encoding="utf-8")
            rel = path.relative_to(ROOT).as_posix()
            tree = ast.parse(source, filename=rel)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    if any(alias.name.split(".")[0] == "smtplib" for alias in node.names):
                        offenders.append(f"{rel}:{node.lineno} import smtplib")
                elif isinstance(node, ast.ImportFrom):
                    if (node.module or "").split(".")[0] == "smtplib":
                        offenders.append(f"{rel}:{node.lineno} from smtplib import")
            for lineno, line in enumerate(source.splitlines(), start=1):
                if _SMTPLIB_TEXT.search(line):
                    offenders.append(f"{rel}:{lineno} mentions smtplib (dynamic import?)")
    assert scanned > 50
    assert offenders == []
