"""Smoke and offline DE/EN CV acceptance for the actual native executable."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.ci_cv_import_exe_offline_e2e import (
    _preview_has_identity,
    _preview_qualification_counts,
)


def verify(exe: Path, output: Path) -> None:
    report = {'smoke': False, 'imports': {}}
    with tempfile.TemporaryDirectory(prefix='kk-native-') as isolated:
        root = Path(isolated)
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(('KARRIEREKRAKE_CV_', 'KARRIEREKRAKE_LLM_'))}
        env.pop('LOCALAPPDATA', None)
        env.pop('KARRIEREKRAKE_MODELS_DIR', None)
        env.update(KARRIEREKRAKE_DATA_DIR=str(root / 'data'), QT_QPA_PLATFORM='offscreen',
                   KARRIEREKRAKE_CV_LLM_BASE='http://127.0.0.1:1/v1',
                   HTTP_PROXY='http://127.0.0.1:1', HTTPS_PROXY='http://127.0.0.1:1',
                   NO_PROXY='localhost,127.0.0.1')
        subprocess.run([str(exe), '--smoke-test'], env=env, check=True, timeout=120)
        marker = root / 'data' / 'smoke_test_result.txt'
        if not marker.is_file() or 'SMOKE_TEST_OK' not in marker.read_text():
            raise RuntimeError('native_smoke_marker_missing')
        report['smoke'] = True
        for name in ['DE_01_Klassisch.pdf', 'EN_01_Classic_Resume.pdf']:
            result = root / f'{name}.json'
            subprocess.run([str(exe), '--cv-import-child', '--cv',
                            str(ROOT / 'tests' / 'fixtures' / 'cv_corpus' / name), '--out', str(result)],
                           env=env, check=True, timeout=900)
            payload = json.loads(result.read_text(encoding='utf-8'))
            counts = _preview_qualification_counts(payload)
            if not _preview_has_identity(payload) or not counts['languages'] or not (counts['skills'] + counts['software']):
                raise RuntimeError(f'native_cv_import_failed: {name}')
            report['imports'][name] = {'ok': True, 'counts': counts}
        report['ok'] = True
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2), encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--exe', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    verify(args.exe.resolve(), args.out)
