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
    good = dict(EXPECTED, native=_GOOD_NATIVE)
    assert validate(good) == []
    bad = dict(good, **payload)
    assert any(p.startswith(problem) for p in validate(bad))


# T06.05.07.05.04.04 (Data Engine 19.10.2026): the C stack embedded in curl_cffi 0.16.3
# is pinned component by component as reported by the BUILT packages of Desktop
# Platforms 39194636153 / Windows Smoke 39194636239 (head 695e264e, search-deps.json).
# A changed, missing or additional native component fails the CI gate until it is
# inventoried again. zlib is reported from the process (Linux runner: system zlib
# 1.2.11, box: 1.3.1), so only its presence is required.
_BUILT_NATIVE = {
    'linux': 'libcurl/8.21.0-IMPERSONATE BoringSSL zlib/1.2.11 brotli/1.2.0 zstd/1.5.7 '
             'libidn2/2.3.7 nghttp2/1.63.0 ngtcp2/1.20.0 nghttp3/1.15.0',
    'darwin': 'libcurl/8.21.0-IMPERSONATE BoringSSL zlib/1.3.1 brotli/1.2.0 zstd/1.5.7 '
              'AppleIDN nghttp2/1.63.0 ngtcp2/1.20.0 nghttp3/1.15.0',
    'win32': 'libcurl/8.21.0-IMPERSONATE BoringSSL zlib/1.3.1 brotli/1.2.0 zstd/1.5.7 '
             'WinIDN nghttp2/1.63.0 ngtcp2/1.20.0 nghttp3/1.15.0',
}


_GOOD_NATIVE = _BUILT_NATIVE.get(sys.platform, _BUILT_NATIVE['linux'])


@pytest.mark.parametrize('platform', ['win32', 'linux', 'darwin'])
@pytest.mark.parametrize('returncode', [1, 3, -11, 0xC0000005, None])
def test_ci_gate_rejects_nonzero_exit_even_with_ok_json(monkeypatch, platform, returncode):
    """Review: a crash after writing an ok JSON must fail, on Windows too."""
    from scripts.ci_frozen_search_deps_check import EXPECTED, evaluate
    monkeypatch.setattr(sys, 'platform', platform)
    good = dict(EXPECTED, native=_BUILT_NATIVE[platform])
    assert evaluate(good, 0) == []
    problems = evaluate(good, returncode)
    assert problems == [f'exit_code={returncode!r} expected 0']


def test_ci_gate_reports_exit_code_and_payload_problems_together():
    from scripts.ci_frozen_search_deps_check import EXPECTED, evaluate
    bad = dict(EXPECTED, native=_GOOD_NATIVE, ok=False)
    problems = evaluate(bad, 2)
    assert any(p.startswith('ok=') for p in problems)
    assert 'exit_code=2 expected 0' in problems


@pytest.mark.parametrize('platform', ['win32', 'linux'])
def test_ci_run_fails_when_exe_crashes_after_writing_ok_json(monkeypatch, tmp_path, platform):
    from scripts import ci_frozen_search_deps_check as ci
    monkeypatch.setattr(sys, 'platform', platform)

    def fake_selfcheck(cmd, env, timeout_s):
        Path(cmd[-1]).write_text(json.dumps(dict(ci.EXPECTED, native=_BUILT_NATIVE[platform])), encoding='utf-8')
        return 3, '', 'crash after writing'
    monkeypatch.setattr(ci, '_run_selfcheck', fake_selfcheck)
    out = tmp_path / 'search-deps.json'
    with pytest.raises(SystemExit, match='exit_code=3 expected 0'):
        ci.run(tmp_path / 'Karrierekrake.exe', out)
    recorded = json.loads(out.read_text(encoding='utf-8'))
    assert recorded['_exit_code'] == 3
    assert recorded['_problems'] == ['exit_code=3 expected 0']


def test_ci_run_passes_on_ok_json_and_zero_exit(monkeypatch, tmp_path):
    from scripts import ci_frozen_search_deps_check as ci

    def fake_selfcheck(cmd, env, timeout_s):
        Path(cmd[-1]).write_text(json.dumps(dict(ci.EXPECTED, native=_GOOD_NATIVE)), encoding='utf-8')
        return 0, '', ''
    monkeypatch.setattr(ci, '_run_selfcheck', fake_selfcheck)
    payload = ci.run(tmp_path / 'Karrierekrake.exe', tmp_path / 'search-deps.json')
    assert payload['_problems'] == []


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


def test_selfcheck_result_is_written_atomically_via_tmp_and_replace(monkeypatch, tmp_path):
    """Review round 1 (1): the Windows CI step polls the file; never expose a partial write."""
    import os
    from core.security import jobspy_runtime
    out = tmp_path / 'sub' / 'r.json'
    calls = []
    original = os.replace

    def replace(src, dst):
        src, dst = Path(src), Path(dst)
        assert src == out.with_name('r.json.tmp')
        assert not dst.exists(), 'target must only appear via os.replace'
        json.loads(src.read_text(encoding='utf-8'))  # complete before it becomes visible
        calls.append((src, dst))
        original(src, dst)
    monkeypatch.setattr(os, 'replace', replace)
    monkeypatch.setattr(jobspy_runtime, 'selfcheck_search_dependencies', lambda: {'ok': True})
    assert jobspy_runtime.selfcheck_main([str(out)]) == 0
    assert calls == [(out.with_name('r.json.tmp'), out)]
    assert json.loads(out.read_text(encoding='utf-8')) == {'ok': True}
    assert not out.with_name('r.json.tmp').exists()


def test_selfcheck_atomic_write_leaves_no_tmp_on_failure(monkeypatch, tmp_path):
    import os
    from core.security import jobspy_runtime

    def boom(src, dst):
        raise OSError('replace failed')
    monkeypatch.setattr(os, 'replace', boom)
    out = tmp_path / 'r.json'
    with pytest.raises(OSError):
        jobspy_runtime._write_atomic(out, '{}')
    assert not out.exists() and not out.with_name('r.json.tmp').exists()


class _HangingProc:
    pid = 4242
    returncode = None

    def __init__(self):
        self.killed = False
        self.calls = 0

    def communicate(self, timeout=None):
        import subprocess
        self.calls += 1
        if self.calls == 1:
            raise subprocess.TimeoutExpired('exe', timeout)
        return '', ''

    def kill(self):
        self.killed = True


@pytest.mark.skipif(
    sys.platform == 'win32',
    reason='POSIX-only: asserts os.killpg(pid, signal.SIGKILL); Windows has no signal.SIGKILL/os.killpg '
           '(Windows path: test_ci_timeout_kills_whole_process_tree_on_windows*)',
)
def test_ci_timeout_kills_whole_process_tree_on_posix(monkeypatch):
    """Review round 1 (2): own session + killpg, not only the direct child."""
    import signal
    import subprocess
    from scripts import ci_frozen_search_deps_check as ci
    proc = _HangingProc()
    seen = {}

    def popen(cmd, **kwargs):
        seen.update(kwargs)
        return proc
    killed = []
    monkeypatch.setattr(ci.sys, 'platform', 'linux')
    monkeypatch.setattr(subprocess, 'Popen', popen)
    monkeypatch.setattr(ci.os, 'killpg', lambda pid, sig: killed.append((pid, sig)), raising=False)
    with pytest.raises(RuntimeError, match='process_tree_killed'):
        ci._run_selfcheck(['exe', '--selfcheck-deps', 'x.json'], {}, 5)
    assert seen.get('start_new_session') is True
    assert killed == [(4242, signal.SIGKILL)]
    assert proc.killed


def test_ci_timeout_kills_whole_process_tree_on_windows(monkeypatch):
    """Review round 1 (2): taskkill /T /F so the unpacked onefile child releases _MEI."""
    import subprocess
    from scripts import ci_frozen_search_deps_check as ci
    proc = _HangingProc()
    seen = {}
    runs = []

    def popen(cmd, **kwargs):
        seen.update(kwargs)
        return proc
    monkeypatch.setattr(ci.sys, 'platform', 'win32')
    monkeypatch.setattr(subprocess, 'Popen', popen)
    monkeypatch.setattr(subprocess, 'run', lambda cmd, **k: runs.append(cmd))
    monkeypatch.setattr(ci.os, 'killpg', lambda *a: pytest.fail('killpg on windows'), raising=False)
    with pytest.raises(RuntimeError, match='process_tree_killed'):
        ci._run_selfcheck(['Karrierekrake.exe', '--selfcheck-deps', 'x.json'], {}, 5)
    assert 'start_new_session' not in seen
    assert runs == [['taskkill', '/T', '/F', '/PID', '4242']]
    assert proc.killed


def test_ci_timeout_on_windows_needs_no_posix_signal_and_stays_a_failure(monkeypatch, tmp_path):
    """Windows timeout path never touches signal.SIGKILL/os.killpg (absent on Windows)
    and the gate fails (RuntimeError, no search-deps.json with ok) instead of passing."""
    import signal
    import subprocess
    from scripts import ci_frozen_search_deps_check as ci
    proc = _HangingProc()
    runs = []
    monkeypatch.setattr(ci.sys, 'platform', 'win32')
    monkeypatch.delattr(signal, 'SIGKILL', raising=False)  # as on Windows
    monkeypatch.delattr(ci.os, 'killpg', raising=False)  # as on Windows
    monkeypatch.setattr(subprocess, 'Popen', lambda cmd, **k: proc)
    monkeypatch.setattr(subprocess, 'run', lambda cmd, **k: runs.append(cmd))
    out = tmp_path / 'search-deps.json'
    with pytest.raises(RuntimeError, match='selfcheck_timeout_after_180s_process_tree_killed'):
        ci.run(tmp_path / 'Karrierekrake.exe', out)
    assert runs == [['taskkill', '/T', '/F', '/PID', '4242']]
    assert proc.killed
    assert not out.exists()


def test_ci_returns_exit_code_without_killing_on_normal_exit(monkeypatch):
    import subprocess
    from scripts import ci_frozen_search_deps_check as ci

    class Done:
        pid = 7
        returncode = 0

        def communicate(self, timeout=None):
            return 'out', 'err'
    monkeypatch.setattr(subprocess, 'Popen', lambda cmd, **k: Done())
    monkeypatch.setattr(ci, '_kill_tree', lambda p: pytest.fail('killed a finished process'))
    assert ci._run_selfcheck(['exe'], {}, 5) == (0, 'out', 'err')


def test_informational_version_of_missing_module_is_unavailable_not_fatal(monkeypatch):
    """Review round 1 (3): a missing optional module (e.g. pandas) must not fail the check."""
    import builtins
    import jobspy  # noqa: F401 - keep the real search stack loaded before hiding pandas
    from core.security.jobspy_runtime import selfcheck_search_dependencies
    original = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name in {'pandas', 'pydantic'}:
            raise ImportError(f'No module named {name!r}')
        return original(name, *args, **kwargs)
    for mod in ('pandas', 'pydantic'):
        monkeypatch.delitem(sys.modules, mod, raising=False)
    monkeypatch.setattr(builtins, '__import__', fake_import)
    result = selfcheck_search_dependencies()
    assert result['ok'] is True
    assert result['version_pandas'] == 'unavailable'
    assert result['version_pydantic'] == 'unavailable'
    assert result['version_requests'] not in ('', 'unknown', 'unavailable')


def test_linux_selfcheck_runs_in_netns_without_network_as_runner_user():
    """Review round 1 (Kritiker/Teamlead): hard proof of no network on the Linux runner."""
    platforms = (ROOT / '.github/workflows/desktop-platforms.yml').read_text(encoding='utf-8')
    start = platforms.index('Frozen search dependency self-check in network namespace')
    step = platforms[start:platforms.index('- name:', start)]
    assert "if: runner.os == 'Linux'" in step
    assert 'unshare -rn' not in step[step.index('run: |'):]
    # Review: pre-check and self-check share ONE namespace (single unshare call),
    # entered as the runner user; no separate namespace for the pre-check.
    assert step.count('unshare') == step[:step.index('run: |')].count('unshare') + 1
    entry = 'sudo unshare -n -- sudo -u "$USER" env HOME="$HOME" PATH="$PATH" sh -c \''
    assert step.count(entry) == 1
    script = step[step.index(entry) + len(entry):]
    script = script[:script.index("\n          '")]
    precheck = script.index('links=$(ip -o link show)')
    run = script.index('exec python scripts/ci_frozen_search_deps_check.py --exe ${{ matrix.exe }} '
                       '--out native-release/search-deps.json')
    assert precheck < run
    assert script.lstrip().startswith('set -eu')
    pre = script[precheck:run]
    assert 'netns_precheck_ok: no network in namespace' in pre
    assert 'netns_precheck_failed: non-loopback interface present"; exit 1' in pre
    assert 'netns_precheck_failed: connect to $target succeeded"; exit 1' in pre
    assert 's.connect(' in pre
    # Teamlead 2026-10-18: log output only. Link list and every failed connect
    # attempt (with its error) are printed before netns_precheck_ok; the fail
    # conditions above stay unchanged.
    ok = pre.index('netns_precheck_ok: no network in namespace')
    link_log = pre.index('printf "%s\\n" "$links" | sed "s/^/netns_precheck_link: /"')
    assert link_log < pre.index('netns_precheck_failed: non-loopback interface present') < ok
    connect_log = pre.index('echo "netns_precheck_connect_failed: $target rc=$rc error=')
    assert pre.index('netns_precheck_failed: connect to $target succeeded"; exit 1') < connect_log < ok
    assert '2>&1); then' in pre
    other = platforms[platforms.index('- name: Frozen search dependency self-check (JobSpy'):start]
    assert "if: runner.os != 'Linux'" in other


@pytest.mark.parametrize('platform', sorted(_BUILT_NATIVE))
def test_ci_gate_accepts_native_stack_reported_by_built_package(platform):
    from scripts.ci_frozen_search_deps_check import EXPECTED, validate
    payload = dict(EXPECTED, native=_BUILT_NATIVE[platform], _platform=platform)
    assert validate(payload) == []


@pytest.mark.parametrize('platform,old,new', [
    ('linux', 'nghttp2/1.63.0', 'nghttp2/1.64.0'),
    ('linux', 'ngtcp2/1.20.0', 'ngtcp2/1.19.0'),
    ('darwin', 'nghttp3/1.15.0', 'nghttp3/1.16.0'),
    ('win32', 'brotli/1.2.0', 'brotli/1.1.0'),
    ('win32', 'zstd/1.5.7', 'zstd/1.5.6'),
    ('linux', 'libidn2/2.3.7', 'libidn2/2.3.8'),
    ('linux', 'libidn2/2.3.7', 'WinIDN'),
    ('win32', 'WinIDN', 'libidn2/2.3.7'),
    ('darwin', ' nghttp3/1.15.0', ''),
    ('linux', ' zlib/1.2.11', ''),
    ('win32', 'nghttp3/1.15.0', 'nghttp3/1.15.0 libssh2/1.11.0'),
    ('darwin', 'nghttp2/1.63.0', 'nghttp2/1.63.0 nghttp2/1.63.0'),
])
def test_ci_gate_rejects_changed_missing_or_extra_native_component(platform, old, new):
    from scripts.ci_frozen_search_deps_check import EXPECTED, validate
    native = _BUILT_NATIVE[platform]
    assert old in native
    payload = dict(EXPECTED, native=native.replace(old, new, 1), _platform=platform)
    assert any(p.startswith('native_component') for p in validate(payload)), payload['native']


@pytest.mark.parametrize('zlib', ['zlib/1.2.11', 'zlib/1.3.1'])
def test_ci_gate_only_requires_presence_of_process_zlib(zlib):
    from scripts.ci_frozen_search_deps_check import EXPECTED, validate
    native = _BUILT_NATIVE['linux'].replace('zlib/1.2.11', zlib)
    assert validate(dict(EXPECTED, native=native, _platform='linux')) == []


def test_ci_gate_unknown_platform_fails_closed():
    from scripts.ci_frozen_search_deps_check import EXPECTED, validate
    payload = dict(EXPECTED, native=_BUILT_NATIVE['linux'], _platform='freebsd14')
    assert any(p.startswith('native_component') for p in validate(payload))
