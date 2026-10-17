"""Safe early diagnostics before logging/redaction handlers are available."""
from __future__ import annotations

MODES = ('--cv-import-child', '--model-probe', '--native-update-swap', '--local-backup',
         '--smoke-test', '--report-physical-cores', '--report-llm-load',
         '--smoke-brouter', '--smoke-browser', '--smoke-cv-corpus', '--once')


def boot_summary(argv) -> str:
    mode = next((flag for flag in MODES if flag in argv[1:]), 'gui')
    return f'boot frozen=1 mode={mode} argument_count={max(0, len(argv) - 1)}\n'
