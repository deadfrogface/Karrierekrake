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
    _run_child_import,
)


def verify(exe: Path, output: Path, model: Path, *, require_avx2: bool = False) -> None:
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
        # Verify the actual bundled backend, not just the build-host Python.
        backend = root / 'backend.txt'
        subprocess.run([str(exe), '--report-llm-load', str(backend)],
                       env=env, check=True, timeout=120)
        backend_text = backend.read_text(encoding='utf-8')
        features = next((line for line in backend_text.splitlines()
                         if line.startswith('llama_cpu_features=')), '')
        print(features, flush=True)
        if require_avx2 and 'AVX2 = 1' not in features:
            raise RuntimeError('native_backend_avx2_missing')
        for name in ['DE_01_Klassisch.pdf', 'EN_01_Classic_Resume.pdf']:
            result = root / f'{name}.json'
            print(f'native_cv_import_start fixture={name}', flush=True)
            payload = _run_child_import(
                exe, ROOT / 'tests' / 'fixtures' / 'cv_corpus' / name, result,
                local_appdata=root / 'data', timeout_s=900, env_override=env)
            if payload['_exit_code'] or not payload.get('ok'):
                # Print only worker codes/counters, never profile contents or paths.
                detail = payload.get('detail') or {}
                safe = {key: detail[key] for key in ('exception_type', 'reason', 'stage',
                        'counter', 'peak_bytes', 'budget_bytes', 'elapsed_s', 'timeout_s',
                        'prompt_tokens', 'tokens_done', 'max_tokens', 'n_ctx') if key in detail}
                raise RuntimeError(f"native_cv_import_failed: exit={payload['_exit_code']} "
                                   f"kind={payload.get('kind')} detail={safe}")
            counts = _preview_qualification_counts(payload)
            if not _preview_has_identity(payload) or not counts['languages'] or not (counts['skills'] + counts['software']):
                raise RuntimeError(f'native_cv_import_failed: {name}')
            report['imports'][name] = {'ok': True, 'counts': counts, 'wall_s': payload['_wall_s']}
            print(f"native_cv_import_ok fixture={name} wall_s={payload['_wall_s']}", flush=True)
        report['ok'] = True
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2), encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--exe', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--require-avx2', action='store_true')
    args = parser.parse_args()
    verify(args.exe.resolve(), args.out, args.model.resolve(), require_avx2=args.require_avx2)
