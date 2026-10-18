"""`--selfcheck-deps`: packaged search-stack self-check and its CI gate (offline)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_selfcheck_reports_versions_native_and_absent_legacy_transport():
    from core.security.jobspy_runtime import selfcheck_search_dependencies
    result = selfcheck_search_dependencies()
    assert result['ok'] is True
    assert result['jobspy'] == '1.3.0'
    assert result['curl_cffi'] == '0.16.3'
    assert str(result['native']).startswith('libcurl/8.21.0-IMPERSONATE ')
    assert result['scraper_indeed'] == result['scraper_linkedin'] == 'ok'
    assert result['ca_bundle'] == 'ok'
    assert result['tls_client'] == 'absent'


def test_selfcheck_fails_closed_when_frozen_package_contains_tls_client(monkeypatch, tmp_path):
    from importlib import util
    from core.security import jobspy_runtime
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    original = util.find_spec
    monkeypatch.setattr(util, 'find_spec',
                        lambda name, *a: object() if name == 'tls_client' else original(name, *a))
    out = tmp_path / 'r.json'
    assert jobspy_runtime.selfcheck_main([str(out)]) == 1
    payload = json.loads(out.read_text(encoding='utf-8'))
    assert payload['ok'] is False
    assert 'legacy_go_transport_present' in payload['error']


def test_selfcheck_fails_closed_when_native_curl_cannot_load(monkeypatch, tmp_path):
    import curl_cffi
    from core.security import jobspy_runtime

    class Broken:
        def __init__(self, *a, **k):
            raise OSError('libcurl-impersonate: cannot open shared object file')
    monkeypatch.setattr(curl_cffi, 'Curl', Broken)
    out = tmp_path / 'r.json'
    assert jobspy_runtime.selfcheck_main([str(out)]) == 1
    payload = json.loads(out.read_text(encoding='utf-8'))
    assert payload == {'ok': False, 'error_type': 'OSError', 'error': payload['error']}
    assert 'cannot open shared object' in payload['error']


def test_selfcheck_sends_no_request(monkeypatch):
    import socket
    from curl_cffi import Curl
    from core.security.jobspy_runtime import selfcheck_search_dependencies

    def deny(*a, **k):
        raise AssertionError('network used by self-check')
    for name in ('create_connection', 'getaddrinfo'):
        monkeypatch.setattr(socket, name, deny)
    monkeypatch.setattr(socket.socket, 'connect', deny)
    monkeypatch.setattr(Curl, 'perform', deny)
    assert selfcheck_search_dependencies()['ok'] is True


def test_desktop_entry_dispatches_selfcheck_before_qt():
    text = (ROOT / 'desktop' / 'app.py').read_text(encoding='utf-8')
    flag = text.index('"--selfcheck-deps"')
    assert flag < text.index('from PySide6')
    assert 'selfcheck_main' in text[flag:flag + 300]


@pytest.mark.parametrize('payload,problem', [
    ({'tls_client': 'present'}, 'tls_client'),
    ({'jobspy': '1.1.82'}, 'jobspy'),
    ({'native': 'libcurl/8.5.0 OpenSSL/3'}, 'native'),
    ({'frozen': False}, 'frozen'),
    ({'ok': False}, 'ok'),
])
def test_ci_gate_rejects_wrong_package(payload, problem):
    from scripts.ci_frozen_search_deps_check import EXPECTED, validate
    good = dict(EXPECTED, native='libcurl/8.21.0-IMPERSONATE BoringSSL zlib/1.3.1')
    assert validate(good) == []
    bad = dict(good, **payload)
    assert any(p.startswith(problem) for p in validate(bad))


def test_frozen_selfcheck_runs_in_every_native_smoke_workflow():
    platforms = (ROOT / '.github/workflows/desktop-platforms.yml').read_text(encoding='utf-8')
    windows = (ROOT / '.github/workflows/windows-smoke.yml').read_text(encoding='utf-8')
    assert 'scripts/ci_frozen_search_deps_check.py --exe ${{ matrix.exe }}' in platforms
    assert 'scripts/ci_frozen_search_deps_check.py --exe dist/Karrierekrake.exe' in windows
    assert 'artifacts/search-deps.json' in windows


def test_selfcheck_tolerates_missing_dist_info_for_informational_versions(monkeypatch):
    """Frozen bundles may lack dist-info for requests & co. (seen in a local Linux build)."""
    from importlib import metadata
    from core.security.jobspy_runtime import selfcheck_search_dependencies
    original = metadata.version

    def version(name):
        if name in {'python-jobspy', 'curl_cffi'}:
            return original(name)
        raise metadata.PackageNotFoundError(name)
    monkeypatch.setattr(metadata, 'version', version)
    result = selfcheck_search_dependencies()
    assert result['ok'] is True
    assert result['version_requests'] not in ('', 'unknown')
