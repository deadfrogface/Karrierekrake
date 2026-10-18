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


def run(exe: Path, out: Path, timeout_s: int = 180) -> dict:
    with tempfile.TemporaryDirectory(prefix='kk-selfcheck-') as tmp:
        result = Path(tmp) / 'selfcheck.json'
        env = dict(os.environ, KARRIEREKRAKE_DATA_DIR=str(Path(tmp) / 'data'),
                   QT_QPA_PLATFORM='offscreen', HTTP_PROXY='http://127.0.0.1:1',
                   HTTPS_PROXY='http://127.0.0.1:1', ALL_PROXY='http://127.0.0.1:1',
                   NO_PROXY='localhost,127.0.0.1')
        proc = subprocess.run([str(exe), '--selfcheck-deps', str(result)], env=env,
                              timeout=timeout_s, capture_output=True, text=True)
        deadline = time.monotonic() + 60  # windowed onefile parents may exit early
        while not result.is_file() and time.monotonic() < deadline:
            time.sleep(1)
        if not result.is_file():
            raise RuntimeError(f'selfcheck_result_missing exit={proc.returncode}')
        payload = json.loads(result.read_text(encoding='utf-8'))
    payload['_exit_code'] = proc.returncode
    payload['_platform'] = sys.platform
    problems = validate(payload)
    if proc.returncode not in (0,) and sys.platform != 'win32':
        problems.append(f'exit_code={proc.returncode}')
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
