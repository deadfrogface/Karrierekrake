"""Require a real native GUI event-loop acknowledgment without a system tray."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.ci_native_backup_restore import native_image


def verify(exe, output, platform='offscreen'):
    exe, output = Path(exe).resolve(strict=True), Path(output)
    if sys.platform not in {'linux', 'darwin'} or not native_image(exe):
        raise ValueError('native_posix_executable_required')
    root = exe.parents[2] if sys.platform == 'darwin' else exe.parent
    candidates = [root / '_internal/native-current.json', root / 'Contents/Resources/native-current.json',
                  root / 'Contents/Frameworks/native-current.json']
    identity = next(json.loads(path.read_text()) for path in candidates if path.is_file())
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {'ok': False, 'identity': identity, 'headless_no_tray': True, 'qt_platform': platform}
    with exe.open('rb') as image:
        report['executable_sha256'] = hashlib.file_digest(image, 'sha256').hexdigest()
    log = output.with_suffix('.log')
    with tempfile.TemporaryDirectory(prefix='.kk-native-update-gui-', dir=root.parent) as transaction, \
         tempfile.TemporaryDirectory(prefix='kk-gui-profile-') as profile:
        marker = Path(transaction) / 'healthy'
        env = {key: value for key, value in os.environ.items() if not key.startswith('KARRIEREKRAKE_CV_')}
        env.pop('LOCALAPPDATA', None)
        env.pop('KARRIEREKRAKE_SMOKE_TEST', None)
        env.update(QT_QPA_PLATFORM=platform, KARRIEREKRAKE_DATA_DIR=profile,
                   KARRIEREKRAKE_MODELS_DIR=str(Path(profile) / 'models'),
                   KK_NATIVE_UPDATE_MARKER=str(marker), KK_NATIVE_UPDATE_COMMIT=identity['commit'],
                   PYINSTALLER_RESET_ENVIRONMENT='1', HTTP_PROXY='http://127.0.0.1:1',
                   HTTPS_PROXY='http://127.0.0.1:1', NO_PROXY='localhost,127.0.0.1')
        started = time.monotonic()
        with log.open('wb') as transcript:
            process = subprocess.Popen([str(exe)], env=env, stdin=subprocess.DEVNULL,
                                       stdout=transcript, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                deadline = time.monotonic() + 45
                while time.monotonic() < deadline and process.poll() is None:
                    if marker.is_file() and marker.read_text() == identity['commit']:
                        report.update(ok=True, startup_acknowledged=True,
                                      wall_s=round(time.monotonic() - started, 3))
                        break
                    time.sleep(0.1)
                if not report['ok']:
                    raise RuntimeError('native_gui_startup_ack_missing')
            finally:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                report['wall_s'] = round(time.monotonic() - started, 3)
                output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
                if not report['ok']:
                    print(log.read_text(encoding='utf-8', errors='replace'), flush=True)
    print('native_gui_startup_ack=ok', flush=True)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    # xcb (under Xvfb) proves the X11 path with host libraries instead of bundled GTK/libXi/libexpat.
    parser.add_argument('--platform', choices=('offscreen', 'xcb'), default='offscreen')
    arguments = parser.parse_args()
    verify(arguments.exe, arguments.out, arguments.platform)
