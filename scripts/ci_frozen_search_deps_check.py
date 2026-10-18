"""Run ``--selfcheck-deps`` in the actual built executable and fail closed.

PR144 Data Engine (T06.05.07.05.04.03): proves inside the frozen package that
JobSpy 1.3.0, curl_cffi 0.16.3 with its native libcurl-impersonate/BoringSSL,
the Indeed/LinkedIn scrapers, requests/urllib3 and the CA bundle are bundled,
and that the retired ``tls_client`` Go transport is absent. Sends no request:
proxies point to a closed local port.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

EXPECTED = {'jobspy': '1.3.0', 'curl_cffi': '0.16.3', 'tls_client': 'absent',
            'scraper_indeed': 'ok', 'scraper_linkedin': 'ok', 'ca_bundle': 'ok',
            'frozen': True, 'ok': True}


def validate(payload: dict) -> list[str]:
    problems = [f'{key}={payload.get(key)!r} expected {value!r}'
                for key, value in EXPECTED.items() if payload.get(key) != value]
    native = str(payload.get('native') or '')
    if not native.startswith('libcurl/8.21.0-IMPERSONATE ') or ' BoringSSL ' not in native:
        problems.append(f'native={native!r} expected libcurl/8.21.0-IMPERSONATE with BoringSSL')
    return problems


def evaluate(payload: dict, returncode: int | None) -> list[str]:
    """All gate problems: payload values plus the self-check exit code.

    A non-zero exit fails on every platform (including Windows), even when the
    JSON was already written with ok=true (e.g. a crash after writing).
    """
    problems = validate(payload)
    if returncode != 0:
        problems.append(f'exit_code={returncode!r} expected 0')
    return problems


def _kill_tree(proc: subprocess.Popen) -> None:
    """Kill the started process and all its descendants.

    A PyInstaller onefile bootloader starts the real app as a child; killing only
    the bootloader leaves the child running and holding ``_MEI*`` open on Windows.
    """
    if sys.platform == 'win32':
        subprocess.run(['taskkill', '/T', '/F', '/PID', str(proc.pid)],
                       capture_output=True, text=True, timeout=60, check=False)
    else:
        try:
            os.killpg(proc.pid, signal.SIGKILL)  # own session/group via start_new_session
        except ProcessLookupError:
            pass
    proc.kill()  # no-op if already gone; ensures the direct child is reaped


def _run_selfcheck(cmd: list[str], env: dict, timeout_s: int) -> tuple[int, str, str]:
    popen_kwargs: dict = {}
    if sys.platform != 'win32':
        popen_kwargs['start_new_session'] = True
    proc = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, **popen_kwargs)
    try:
        stdout, stderr = proc.communicate(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        try:
            proc.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            pass
        raise RuntimeError(f'selfcheck_timeout_after_{timeout_s}s_process_tree_killed') from None
    return proc.returncode, stdout, stderr


def run(exe: Path, out: Path, timeout_s: int = 180) -> dict:
    with tempfile.TemporaryDirectory(prefix='kk-selfcheck-') as tmp:
        result = Path(tmp) / 'selfcheck.json'
        env = dict(os.environ, KARRIEREKRAKE_DATA_DIR=str(Path(tmp) / 'data'),
                   QT_QPA_PLATFORM='offscreen', HTTP_PROXY='http://127.0.0.1:1',
                   HTTPS_PROXY='http://127.0.0.1:1', ALL_PROXY='http://127.0.0.1:1',
                   NO_PROXY='localhost,127.0.0.1')
        returncode, _stdout, _stderr = _run_selfcheck(
            [str(exe), '--selfcheck-deps', str(result)], env, timeout_s)
        deadline = time.monotonic() + 60  # windowed onefile parents may exit early
        while not result.is_file() and time.monotonic() < deadline:
            time.sleep(1)
        if not result.is_file():
            raise RuntimeError(f'selfcheck_result_missing exit={returncode}')
        payload = json.loads(result.read_text(encoding='utf-8'))
    payload['_exit_code'] = returncode
    payload['_platform'] = sys.platform
    problems = evaluate(payload, returncode)
    payload['_problems'] = problems
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding='utf-8')
    print(json.dumps(payload, indent=2, sort_keys=True), flush=True)
    if problems:
        raise SystemExit('frozen_search_deps_check_failed: ' + '; '.join(problems))
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--exe', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args(argv)
    run(args.exe, args.out)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
