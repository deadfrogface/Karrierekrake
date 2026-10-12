"""Compare Patchright with the actual repo's Playwright launch flags locally.

No Google searches, private profiles, accounts, proxies or CAPTCHA attempts.
The report measures observable signals and compatibility, not CAPTCHA probability.
"""
from __future__ import annotations

import argparse
import ast
import importlib
import importlib.metadata
import json
import os
import shutil
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def current_options():
    tree = ast.parse((ROOT / 'browser/browser_manager.py').read_text(encoding='utf-8'))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'launch_kwargs'
                                               for t in node.targets):
            if isinstance(node.value, ast.Call):
                return {kw.arg: ast.literal_eval(kw.value) for kw in node.value.keywords
                        if kw.arg in {'viewport', 'args', 'ignore_default_args'}}
    raise RuntimeError('Current browser launch options not found; refusing guessed baseline')


def executable_path(explicit):
    if explicit:
        path = Path(explicit)
        if not path.is_file():
            raise FileNotFoundError('Browser executable not found')
        return path
    if sys.platform == 'win32':
        for base in (os.environ.get('PROGRAMFILES'), os.environ.get('PROGRAMFILES(X86)'),
                     os.environ.get('LOCALAPPDATA')):
            if base:
                for suffix in ('Microsoft/Edge/Application/msedge.exe',
                               'Google/Chrome/Application/chrome.exe'):
                    path = Path(base) / suffix
                    if path.is_file():
                        return path
    elif sys.platform == 'darwin':
        for name in ('Google Chrome', 'Microsoft Edge'):
            path = Path('/Applications') / f'{name}.app/Contents/MacOS/{name}'
            if path.is_file():
                return path
    else:
        for name in ('google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser'):
            path = shutil.which(name)
            if path:
                return Path(path)
    raise RuntimeError('No installed compatible browser; benchmark did not run')


class PageServer(BaseHTTPRequestHandler):
    def do_GET(self):
        content = (b'<!doctype html><meta charset="utf-8"><title>Local browser comparison</title>'
                   b'<input id="input"><button id="button" onclick="this.dataset.clicked=1">Click</button>')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(content)))
        self.end_headers()
        self.wfile.write(content)
    def log_message(self, *args):
        pass


PROBE = """() => {
  let serializationReads = 0;
  const error = new Error('controlled local CDP probe');
  Object.defineProperty(error, 'stack', {get() { serializationReads++; return 'local'; }});
  console.debug(error);
  const canvas = document.createElement('canvas');
  const gl = canvas.getContext('webgl');
  const ext = gl && gl.getExtension('WEBGL_debug_renderer_info');
  return {
    webdriver: navigator.webdriver === true,
    user_agent: navigator.userAgent,
    headless_user_agent: navigator.userAgent.includes('HeadlessChrome'),
    automation_globals: Object.getOwnPropertyNames(window).filter(
      k => /^cdc_|__playwright|__pwInitScripts/.test(k)),
    cdp_serialization_observed: serializationReads > 0,
    language: navigator.language,
    plugins: navigator.plugins.length,
    webgl_renderer: ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : null
  };
}"""


def run_case(engine, options, profile, binary, url):
    started = time.monotonic()
    api = importlib.import_module(engine + '.sync_api')
    with api.sync_playwright() as driver:
        context = driver.chromium.launch_persistent_context(
            str(profile), executable_path=str(binary), **options)
        try:
            page = context.new_page()
            page.goto(url, wait_until='domcontentloaded', timeout=15000)
            result = page.evaluate(PROBE)
            page.locator('#input').fill('Karrierekrake local compatibility test')
            page.locator('#button').click()
            result['form_interaction_ok'] = (
                page.locator('#input').input_value() == 'Karrierekrake local compatibility test'
                and page.locator('#button').get_attribute('data-clicked') == '1')
            context.add_cookies([{'name': 'isolated-test', 'value': 'persisted',
                                 'url': url, 'expires': time.time() + 3600}])
            result['browser_version'] = context.browser.version if context.browser else 'unknown'
        finally:
            context.close()
        reopened = driver.chromium.launch_persistent_context(
            str(profile), executable_path=str(binary), **options)
        try:
            result['profile_persisted'] = any(c['name'] == 'isolated-test' and c['value'] == 'persisted'
                                              for c in reopened.cookies(url))
        finally:
            reopened.close()
    result['elapsed_seconds'] = round(time.monotonic() - started, 3)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--browser', default='')
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--rounds', type=int, default=3)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    versions = {name: importlib.metadata.version(name) for name in ('playwright', 'patchright')}
    if versions['playwright'] != versions['patchright']:
        raise RuntimeError('Driver versions differ; refusing mismatched comparison')
    binary = executable_path(args.browser)
    cases = [
        ('playwright_default', 'playwright', {'headless': True}),
        ('karrierekrake_current', 'playwright', {**current_options(), 'headless': True}),
        ('patchright_same_settings', 'patchright', {**current_options(), 'headless': True}),
        ('patchright_recommended_visible', 'patchright', {'headless': False, 'no_viewport': True}),
    ]
    server = ThreadingHTTPServer(('127.0.0.1', 0), PageServer)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    results = []
    try:
        with tempfile.TemporaryDirectory(prefix='kk-driver-comparison-') as temporary:
            for round_index in range(max(1, min(args.rounds, 5))):
                # Reverse order in alternate rounds to reduce order bias.
                order = cases if round_index % 2 == 0 else list(reversed(cases))
                for name, engine, options in order:
                    row = {'variant': name, 'round': round_index + 1, 'headless': options['headless']}
                    try:
                        row.update(run_case(engine, options, Path(temporary) / f'{name}-{round_index}',
                                            binary, f'http://127.0.0.1:{server.server_port}/'))
                        row['status'] = 'ok'
                    except Exception as exc:
                        row['status'] = 'failed'
                        row['error_type'] = type(exc).__name__
                        print(f'{name}: {type(exc).__name__}: {str(exc)[:350]}', flush=True)
                    results.append(row)
                    print(json.dumps(row, ensure_ascii=False), flush=True)
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    report = {'driver_versions': versions, 'browser_binary': binary.name, 'results': results,
              'limits': 'Local probes only. No CAPTCHA/private-browsing/IP-reputation measurement. '
                        'Visible recommendation differs in headless mode; compare same-settings rows for driver effect.'}
    (args.output_dir / 'comparison.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    lines = ['# Browser driver comparison', '', report['limits'], '',
             '| Variant | Round | Status | webdriver | Headless UA | Automation globals | CDP probe | Form | Session persisted |',
             '|---|---:|---|---|---|---|---|---|---|']
    for r in results:
        lines.append('| ' + ' | '.join(str(r.get(k, '—')) for k in (
            'variant', 'round', 'status', 'webdriver', 'headless_user_agent', 'automation_globals',
            'cdp_serialization_observed', 'form_interaction_ok', 'profile_persisted')) + ' |')
    (args.output_dir / 'comparison.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    required = {'karrierekrake_current', 'patchright_same_settings'}
    if any(r['status'] != 'ok' for r in results if r['variant'] in required):
        raise SystemExit('Required browser compatibility case failed; inspect the report')


if __name__ == '__main__':
    main()
