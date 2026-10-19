"""Offline regression tests against the urllib3-future/h11 versions the desktop package ships.

The built packages (Linux, Windows, macOS) bundle urllib3-future 2.25.901, which
overwrites ``urllib3/``, and h11 0.16.0 as its only HTTP/1.1 parser
(``urllib3.contrib.hface.protocols.http1._h11``). Python ``brotli``/``brotlicffi``
is not packaged. libcurl's C brotli inside curl_cffi is a separate stack that
these tests do not cover.

* 2xpw / CVE-2025-66471: a decompression bomb must be decoded in bounded steps.
* vxq7 / CVE-2026-97689: an over-long chunk-size line must be rejected at h11's
  incomplete-event limit.

Every check has its own negative-control test. Each control removes the
protection (decoder without ``max_length``, h11 with a raised limit, a permissive
chunk-header regex, ``br`` offered without a module) and shows that the same
check then fires. Only loopback sockets and in-memory data are used.
"""
from __future__ import annotations

import gzip
import io
import socket
import threading
import tracemalloc
import zlib
from importlib import metadata
from pathlib import Path

import h11
import pytest
import urllib3
from urllib3.response import DeflateDecoder, GzipDecoder, HTTPResponse

ROOT = Path(__file__).resolve().parents[1]
BOMB_PLAIN = 64 * 1024 * 1024
PEAK_LIMIT = 256 * 1024
H11_LIMIT = 16 * 1024
LOOPBACK_FLOOD = 4 * 1024 * 1024


# --- exact packaged versions and parser ---------------------------------------------------

def _constraint(name: str) -> str:
    for line in (ROOT / 'constraints-runtime.txt').read_text(encoding='utf-8').splitlines():
        line = line.split('#', 1)[0].strip()
        if line.lower().startswith(name.lower() + '=='):
            return line.split('==', 1)[1].strip()
    raise AssertionError(f'{name} is not pinned in constraints-runtime.txt')


def _pin_problems(version_of) -> list[str]:
    expected = {'urllib3-future': '2.25.901', 'h11': '0.16.0'}
    problems = []
    for dist, packaged in expected.items():
        if not (version_of(dist) == _constraint(dist) == packaged):
            problems.append(f'{dist}: installed {version_of(dist)}, pinned {_constraint(dist)}, packaged {packaged}')
    return problems


def test_tests_run_against_the_pinned_packaged_versions():
    assert _pin_problems(metadata.version) == []
    # urllib3-future owns the urllib3 import name (same as in the built package).
    assert urllib3.__version__ == '2.25.901'


def test_negative_control_pin_check_fires_on_other_versions():
    fake = {'urllib3-future': '2.25.902', 'h11': '0.14.0'}
    assert len(_pin_problems(fake.__getitem__)) == 2


def _http1_impl():
    from urllib3.contrib.hface.protocols.http1 import _h11

    return _h11.HTTP1ProtocolHyperImpl


def _parser_problems(impl) -> list[str]:
    problems = []
    if getattr(impl, 'implementation', None) != 'h11':
        problems.append(f'implementation={getattr(impl, "implementation", None)!r}')
    if not isinstance(impl()._connection, h11.Connection):
        problems.append('connection is not h11.Connection')
    return problems


def test_http1_parser_used_by_urllib3_future_is_h11():
    assert _parser_problems(_http1_impl()) == []


def test_negative_control_parser_check_fires_on_other_parser():
    class OtherParser:
        implementation = 'other'

        def __init__(self):
            self._connection = object()

    assert len(_parser_problems(OtherParser)) == 2


# --- 2xpw / CVE-2025-66471: decompression bomb ------------------------------------------------

def _bomb(encoding: str) -> bytes:
    plain = b'\0' * BOMB_PLAIN
    if encoding == 'gzip':
        return gzip.compress(plain, 9)
    if encoding == 'deflate':
        return zlib.compress(plain, 9)
    import brotli  # only reached when the module is installed

    return brotli.compress(plain, quality=5)


def _response(encoding: str) -> HTTPResponse:
    return HTTPResponse(body=io.BytesIO(_bomb(encoding)), headers={'content-encoding': encoding},
                        status=200, preload_content=False, decode_content=True)


def _peak(callable_):
    tracemalloc.start()
    try:
        result = callable_()
        return result, tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()


def _read_peak(encoding: str) -> tuple[int, int]:
    response = _response(encoding)
    data, peak = _peak(lambda: response.read(1024))
    return len(data), peak


def _stream_peak(encoding: str) -> tuple[int, int]:
    response = _response(encoding)

    def first_chunks():
        sizes = []
        for chunk in response.stream(4096, decode_content=True):
            sizes.append(len(chunk))
            if len(sizes) == 8:
                break
        return max(sizes)

    return _peak(first_chunks)


def _without_max_length(monkeypatch):
    for cls in (GzipDecoder, DeflateDecoder):
        original = cls.decompress
        monkeypatch.setattr(cls, 'decompress',
                            lambda self, data, max_length=-1, _o=original: _o(self, data, -1))


@pytest.mark.parametrize('encoding', ['gzip', 'deflate'])
def test_decompression_bomb_read_amt_is_bounded(encoding):
    size, peak = _read_peak(encoding)
    assert size == 1024
    assert peak < PEAK_LIMIT, f'{encoding}: read(1024) allocated {peak} bytes'


@pytest.mark.parametrize('encoding', ['gzip', 'deflate'])
def test_decompression_bomb_stream_is_bounded(encoding):
    largest, peak = _stream_peak(encoding)
    assert 0 < largest <= 4096
    assert peak < PEAK_LIMIT, f'{encoding}: stream(4096) allocated {peak} bytes'


@pytest.mark.parametrize('encoding', ['gzip', 'deflate'])
def test_negative_control_unbounded_decoder_trips_the_bomb_checks(encoding, monkeypatch):
    _without_max_length(monkeypatch)
    assert _read_peak(encoding)[1] >= PEAK_LIMIT
    assert _stream_peak(encoding)[1] >= PEAK_LIMIT


def _installed_brotli():
    for module, dist in (('brotlicffi', 'brotlicffi'), ('brotli', 'Brotli')):
        try:
            __import__(module)
        except ImportError:
            continue
        return dist
    return None


def _brotli_problems(dist, accept_encoding: str, version_of=metadata.version) -> list[str]:
    offered = 'br' in [p.strip() for p in accept_encoding.split(',')]
    if dist is None:
        return ['br offered without brotli module'] if offered else []
    version = tuple(int(p) for p in version_of(dist).split('.')[:3] if p.isdigit())
    return [] if version >= (1, 2, 0) else [f'{dist} {version}: mf9v fix needs >= 1.2.0']


def test_brotli_is_bounded_or_not_offered():
    from urllib3.util.request import ACCEPT_ENCODING

    dist = _installed_brotli()
    assert _brotli_problems(dist, ACCEPT_ENCODING) == []
    if dist is not None:
        size, peak = _read_peak('br')
        assert size == 1024
        assert peak < PEAK_LIMIT


def test_negative_control_brotli_check_fires():
    assert _brotli_problems(None, 'gzip,deflate,br') == ['br offered without brotli module']
    assert _brotli_problems('Brotli', 'gzip,deflate,br', lambda _d: '1.1.0')
    assert _brotli_problems('brotlicffi', 'gzip,deflate,br', lambda _d: '1.1.0.0')


# --- vxq7 / CVE-2026-97689: over-long chunk-size line ------------------------------------------

def _protocol_after_headers(limit: int | None = None):
    proto = _http1_impl()()
    if limit is not None:
        proto._connection._max_incomplete_event_size = limit
    proto.submit_headers(1, [(b':method', b'GET'), (b':scheme', b'http'),
                             (b':authority', b'example.invalid'), (b':path', b'/')], end_stream=True)
    proto.bytes_to_send()
    proto.bytes_received(b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n')
    return proto


def _terminations(proto, body: bytes):
    from urllib3.contrib.hface.events import ConnectionTerminated

    proto.bytes_received(body)
    events = []
    while (event := proto.next_event()) is not None:
        events.append(event)
    return [e for e in events if isinstance(e, ConnectionTerminated)]


def test_chunk_size_line_rejected_exactly_above_h11_limit():
    assert h11._connection.DEFAULT_MAX_INCOMPLETE_EVENT_SIZE == H11_LIMIT
    assert _terminations(_protocol_after_headers(), b'1' * H11_LIMIT) == []
    terminated = _terminations(_protocol_after_headers(), b'1' * (H11_LIMIT + 1))
    assert len(terminated) == 1
    assert terminated[0].message == 'Receive buffer too long'
    assert terminated[0].error_code == 431


def test_negative_control_raised_h11_limit_accepts_overlong_line():
    assert _terminations(_protocol_after_headers(limit=1 << 30), b'1' * (H11_LIMIT + 1)) == []


def test_chunk_size_with_more_than_20_hex_digits_is_illegal():
    terminated = _terminations(_protocol_after_headers(), b'1' * 21 + b'\r\n')
    assert len(terminated) == 1
    assert 'illegal chunk header' in terminated[0].message


def test_negative_control_permissive_chunk_header_accepts_21_digits(monkeypatch):
    import re

    from h11 import _readers

    monkeypatch.setattr(_readers, 'chunk_header_re',
                        re.compile(rb'(?P<chunk_size>[0-9A-Fa-f]+)(?P<chunk_ext>;.*)?\r\n'))
    assert _terminations(_protocol_after_headers(), b'1' * 21 + b'\r\n') == []


def _loopback_flood() -> tuple[BaseException | None, int]:
    server = socket.socket()
    server.bind(('127.0.0.1', 0))
    server.listen(1)
    port = server.getsockname()[1]
    sent = []

    def serve():
        conn, _ = server.accept()
        with conn:
            conn.recv(65536)
            conn.sendall(b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n')
            try:
                for _ in range(LOOPBACK_FLOOD // 4096):  # hex digits, never a CRLF
                    conn.sendall(b'1' * 4096)
                    sent.append(4096)
            except OSError:
                pass

    worker = threading.Thread(target=serve, daemon=True)
    worker.start()
    pool = urllib3.PoolManager(retries=False, timeout=10)
    error = None
    try:
        response = pool.request('GET', f'http://127.0.0.1:{port}/', preload_content=False)
        response.read()
    except Exception as exc:  # noqa: BLE001 - the caller inspects the exact exception
        error = exc
    finally:
        pool.clear()
        server.close()
        worker.join(timeout=20)
    return error, sum(sent)


def test_overlong_chunk_size_line_from_loopback_server_raises_protocol_error():
    error, sent = _loopback_flood()
    assert isinstance(error, urllib3.exceptions.ProtocolError)
    assert 'Receive buffer too long' in str(error)
    assert sent < LOOPBACK_FLOOD


def test_negative_control_loopback_without_h11_limit_buffers_the_whole_flood(monkeypatch):
    original = h11.Connection.__init__

    def unlimited(self, *args, **kwargs):
        kwargs['max_incomplete_event_size'] = 1 << 30
        original(self, *args, **kwargs)

    monkeypatch.setattr(h11.Connection, '__init__', unlimited)
    error, sent = _loopback_flood()
    assert 'Receive buffer too long' not in str(error)
    assert sent == LOOPBACK_FLOOD
