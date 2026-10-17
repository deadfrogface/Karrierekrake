"""Exercise backup/verify/restore through the actual installed executable."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import time


def native_image(path):
    with Path(path).open('rb') as stream:
        header = stream.read(4)
    return header.startswith((b'\x7fELF', b'MZ')) or header in {
        b'\xfe\xed\xfa\xce', b'\xce\xfa\xed\xfe', b'\xfe\xed\xfa\xcf',
        b'\xcf\xfa\xed\xfe', b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca'}


def verify(exe: Path, output: Path):
    exe = exe.resolve(strict=True)
    report = {'native_image': native_image(exe), 'steps': {}, 'ok': False}
    with exe.open('rb') as image:
        report['executable_sha256'] = hashlib.file_digest(image, 'sha256').hexdigest()
    with tempfile.TemporaryDirectory(prefix='kk-native-restore-') as temporary:
        root = Path(temporary)
        source, restored, archive = root / 'source', root / 'restored', root / 'backup.zip'
        env = dict(os.environ)
        env.pop('LOCALAPPDATA', None)
        env.update(QT_QPA_PLATFORM='offscreen', KARRIEREKRAKE_DATA_DIR=str(source))
        def run(step, *arguments):
            result = subprocess.run([str(exe), *map(str, arguments)], env=env,
                                    capture_output=True, text=True, timeout=120)
            report['steps'][step] = {'exit_code': result.returncode}
            if result.returncode:
                raise RuntimeError('native_backup_step_failed:' + step + ':' + str(result.returncode))
        def await_proof(path, predicate):
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                try:
                    text = path.read_text(encoding='utf-8')
                    if predicate(text):
                        return text
                except (OSError, ValueError):
                    pass
                time.sleep(0.1)
            raise RuntimeError('native_backup_completion_receipt_missing')
        def backup(step, *arguments):
            receipt = root / (step + '-result.json')
            run(step, '--local-backup', '--result-json', receipt, *arguments)
            await_proof(receipt, lambda text: json.loads(text).get('status') == 'ok')
        try:
            run('initial_smoke', '--smoke-test')
            await_proof(source / 'smoke_test_result.txt', lambda text: 'SMOKE_TEST_OK' in text)
            with sqlite3.connect(source / 'data/jobs.db') as connection:
                connection.execute('CREATE TABLE pr144_restore_proof (value TEXT NOT NULL)')
                connection.execute('INSERT INTO pr144_restore_proof VALUES (?)', ('synthetic-restore-proof',))
            backup('create', 'create', source, archive)
            backup('verify', 'verify', archive)
            backup('restore', 'restore', archive, restored)
            # A pre-existing smoke marker from the backup cannot satisfy the
            # restart check: require a fresh one from this invocation.
            (restored / 'smoke_test_result.txt').unlink()
            env['KARRIEREKRAKE_DATA_DIR'] = str(restored)
            run('restored_smoke', '--smoke-test')
            marker = await_proof(restored / 'smoke_test_result.txt', lambda text: 'SMOKE_TEST_OK' in text)
            if 'SMOKE_TEST_OK' not in marker or 'db=' + str(restored / 'data/jobs.db') not in marker:
                raise RuntimeError('native_restore_used_wrong_database')
            with sqlite3.connect(restored / 'data/jobs.db') as connection:
                if connection.execute('SELECT value FROM pr144_restore_proof').fetchall() != [('synthetic-restore-proof',)]:
                    raise RuntimeError('native_restore_marker_not_preserved')
            report.update(ok=True, restored_database_path_confirmed=True, synthetic_marker_preserved=True)
        finally:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if not native_image(args.exe):
        raise ValueError('native_executable_required')
    verify(args.exe, args.out)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
