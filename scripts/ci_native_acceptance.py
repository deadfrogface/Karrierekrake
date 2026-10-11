"""Smoke and offline DE/EN CV acceptance for the actual native executable."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.ci_cv_import_exe_offline_e2e import (
    _preview_has_identity,
    _preview_qualification_counts,
    _terminate_child_tree,
)


def _save_report(output: Path, report: dict) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding='utf-8')


def verify(exe: Path, output: Path, model: Path) -> None:
    report = {'smoke': False, 'imports': {}}
    with tempfile.TemporaryDirectory(prefix='kk-native-') as isolated:
        root = Path(isolated)
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(('KARRIEREKRAKE_CV_', 'KARRIEREKRAKE_LLM_'))}
        from core.app_updates import digest
        from core.cv_llm_runtime import CV_MODEL_REL, CV_MODEL_SHA256
        if digest(model) != CV_MODEL_SHA256:
            raise ValueError('native_acceptance_model_invalid')
        destination = root / 'data' / CV_MODEL_REL
        destination.parent.mkdir(parents=True)
        shutil.copy2(model, destination)
        report['model_provisioning'] = 'verified_user_data_model_after_initial_download'
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
        _save_report(output, report)
        for name in ['DE_01_Klassisch.pdf', 'EN_01_Classic_Resume.pdf']:
            result = root / f'{name}.json'
            command = [str(exe), '--cv-import-child', '--cv',
                            str(ROOT / 'tests' / 'fixtures' / 'cv_corpus' / name), '--out', str(result)]
            # Onefile bootloaders can spawn a second process holding the GGUF.
            child = subprocess.Popen(command, env=env,
                                     start_new_session=sys.platform != 'win32')
            try:
                from core.cv_docpick_import import CV_IMPORT_TIMEOUT_CEILING_S
                child.wait(timeout=CV_IMPORT_TIMEOUT_CEILING_S + 120.0)
            except BaseException:
                report['imports'][name] = {'ok': False, 'kind': 'timeout_or_interruption'}
                _save_report(output, report)
                _terminate_child_tree(child)
                raise
            if not result.is_file():
                raise RuntimeError(f'native_cv_import_result_missing: exit={child.returncode}')
            payload = json.loads(result.read_text(encoding='utf-8'))
            from core.cv_llm_runtime import public_llm_step
            report['imports'][name] = {
                'ok': bool(payload.get('ok')) and child.returncode == 0,
                'kind': payload.get('kind'),
                'llm_step': public_llm_step(payload.get('llm_step')),
            }
            _save_report(output, report)
            if child.returncode or not payload.get('ok'):
                # Print only worker codes/counters, never profile contents or paths.
                detail = payload.get('detail') or {}
                safe = {key: detail[key] for key in ('exception_type', 'reason', 'stage',
                        'counter', 'peak_bytes', 'budget_bytes') if key in detail}
                raise RuntimeError(f"native_cv_import_failed: exit={child.returncode} "
                                   f"kind={payload.get('kind')} detail={safe}")
            counts = _preview_qualification_counts(payload)
            if not _preview_has_identity(payload) or not counts['languages'] or not (counts['skills'] + counts['software']):
                raise RuntimeError(f'native_cv_import_failed: {name}')
            report['imports'][name]['counts'] = counts
        report['ok'] = True
        _save_report(output, report)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--exe', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--model', type=Path, required=True)
    args = parser.parse_args()
    verify(args.exe.resolve(), args.out, args.model.resolve())
