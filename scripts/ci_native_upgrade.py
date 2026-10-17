"""Switch two real POSIX bundles, then verify normal GUI health and profile data.

Only the public release transport is replaced by a verified local CI archive.
The production staging validator, frozen atomic-swap entry point, detached
installer, and normal GUI acknowledgment all run unchanged.
"""
from __future__ import annotations
import argparse
from contextlib import closing, contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from core import native_update_install as updater
from core.native_updates import ASSETS
from scripts.ci_native_backup_restore import native_image


def identity(app):
    for relative in ('_internal/native-current.json', 'Contents/Resources/native-current.json',
                     'Contents/Frameworks/native-current.json'):
        path = app / relative
        if path.is_file():
            return json.loads(path.read_text(encoding='utf-8'))
    raise ValueError('native_upgrade_identity_missing')


@contextmanager
def unpack(archive, directory):
    if sys.platform == 'darwin':
        mount = directory / 'mount'
        mount.mkdir()
        subprocess.run(['hdiutil', 'attach', '-readonly', '-nobrowse', '-mountpoint', str(mount), str(archive)],
                       check=True, capture_output=True, timeout=120)
        try:
            app = directory / 'Karrierekrake.app'
            shutil.copytree(mount / app.name, app, symlinks=True)
        finally:
            subprocess.run(['hdiutil', 'detach', str(mount)], check=True, capture_output=True, timeout=60)
    else:
        with tarfile.open(archive, 'r:gz') as source:
            updater._validate_archive_members(source.getmembers())
            source.extractall(directory, filter='data')
        app = directory / 'Karrierekrake'
    yield app


def launch_helper(stage, root):
    # This controller exits naturally. The production installer waits for its
    # real parent PID; no fake PID or early health marker is used.
    original = subprocess.Popen
    def capture(*args, **kwargs):
        process = original(*args, **kwargs)
        (stage / 'helper-pid').write_text(str(process.pid), encoding='ascii')
        return process
    with patch.object(updater, 'install_location', return_value=root), \
         patch.object(updater.subprocess, 'Popen', side_effect=capture):
        updater.launch_installer(stage)


def verify(old_folder, candidate_folder, output):
    old_folder, candidate_folder = Path(old_folder).resolve(), Path(candidate_folder).resolve()
    output = Path(output)
    candidate = json.loads((candidate_folder / 'native-current.json').read_text())
    archive = candidate_folder / ASSETS[candidate['target']]
    old_archive = old_folder / ASSETS[candidate['target']]
    report = {'ok': False, 'candidate': candidate, 'scope': 'native CI build transition; local archive transport'}
    output.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix='kk-native-upgrade-') as temporary:
        work = Path(temporary)
        installation = work / 'install'
        installation.mkdir()
        stage = None
        with unpack(old_archive, installation) as app:
            old = identity(app)
            if old != json.loads((old_folder / 'native-current.json').read_text()) or old['target'] != candidate['target']:
                raise ValueError('native_upgrade_baseline_identity_mismatch')
            report['baseline'] = old
            relative = 'Contents/MacOS/Karrierekrake' if sys.platform == 'darwin' else 'Karrierekrake'
            exe = app / relative
            if not native_image(exe):
                raise ValueError('native_upgrade_requires_native_baseline')
            profile = work / 'profile'
            env = dict(os.environ)
            for key in ('LOCALAPPDATA', 'KARRIEREKRAKE_SMOKE_TEST', 'KK_NATIVE_UPDATE_MARKER', 'KK_NATIVE_UPDATE_COMMIT'):
                env.pop(key, None)
            env.update(KARRIEREKRAKE_DATA_DIR=str(profile), QT_QPA_PLATFORM='offscreen',
                       HTTP_PROXY='http://127.0.0.1:1', HTTPS_PROXY='http://127.0.0.1:1',
                       NO_PROXY='localhost,127.0.0.1', PYINSTALLER_RESET_ENVIRONMENT='1')
            try:
                subprocess.run([str(exe), '--smoke-test'], env=env, check=True, timeout=120,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                if 'SMOKE_TEST_OK' not in (profile / 'smoke_test_result.txt').read_text():
                    raise RuntimeError('native_upgrade_baseline_smoke_missing')
                database = profile / 'data/jobs.db'
                with closing(sqlite3.connect(database)) as connection, connection:
                    connection.execute('CREATE TABLE pr144_upgrade_proof (value TEXT NOT NULL)')
                    connection.execute('INSERT INTO pr144_upgrade_proof VALUES (?)', ('synthetic-upgrade-proof',))
                with archive.open('rb') as stream:
                    sha = hashlib.file_digest(stream, 'sha256').hexdigest()
                report['archive_sha256'] = sha
                tag = 'update-' + str(candidate['sequence']) + '-' + candidate['commit'][:12]
                manifest = {**candidate, 'protocol': 1, 'tag': tag, 'size': archive.stat().st_size,
                            'sha256': sha, 'url': 'https://github.com/' + updater.REPOSITORY +
                            '/releases/download/' + tag + '/' + archive.name}
                class LocalResponse:
                    def __enter__(self): self.stream = archive.open('rb'); return self
                    def __exit__(self, *args): self.stream.close()
                    def iter_content(self, size):
                        while block := self.stream.read(size): yield block
                with patch.object(updater, 'install_location', return_value=app), \
                     patch.object(updater, 'current', return_value=old), \
                     patch.object(updater, '_get', return_value=LocalResponse()):
                    stage = updater.stage_update(manifest)
                subprocess.run([sys.executable, str(Path(__file__).resolve()), '--launch-helper',
                                str(stage), '--install-root', str(app)], env=env, check=True, timeout=30)
                deadline = time.monotonic() + 115
                while time.monotonic() < deadline and not (stage / 'result').is_file():
                    time.sleep(.2)
                report['result'] = (stage / 'result').read_text().strip() if (stage / 'result').is_file() else 'missing'
                report['startup_acknowledged'] = ((stage / 'healthy').is_file()
                    and (stage / 'healthy').read_text() == candidate['commit'])
                report['candidate_installed'] = identity(app) == candidate
                with closing(sqlite3.connect(database)) as connection:
                    report['synthetic_marker_preserved'] = connection.execute(
                        'SELECT value FROM pr144_upgrade_proof').fetchall() == [('synthetic-upgrade-proof',)]
                with exe.open('rb') as stream:
                    report['executable_sha256'] = hashlib.file_digest(stream, 'sha256').hexdigest()
                if not (report['result'] == 'success' and report['startup_acknowledged']
                        and report['candidate_installed'] and report['synthetic_marker_preserved']):
                    raise RuntimeError('native_upgrade_acceptance_failed')
                report['ok'] = True
            finally:
                if stage is not None and (stage / 'helper-pid').is_file():
                    pid = int((stage / 'helper-pid').read_text())
                    for sig in (signal.SIGTERM, signal.SIGKILL):
                        try: os.killpg(pid, sig)
                        except ProcessLookupError: pass
                        time.sleep(.3)
                report['wall_s'] = round(time.monotonic() - started, 3)
                output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print('native_upgrade=ok', flush=True)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--old', type=Path)
    parser.add_argument('--candidate', type=Path)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--launch-helper', type=Path)
    parser.add_argument('--install-root', type=Path)
    args = parser.parse_args()
    if args.launch_helper:
        launch_helper(args.launch_helper, args.install_root)
    else:
        verify(args.old, args.candidate, args.out)
