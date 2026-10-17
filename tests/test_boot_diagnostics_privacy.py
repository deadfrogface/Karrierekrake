import pytest
from core.privacy.boot_diagnostics import boot_summary


@pytest.mark.parametrize('argv,mode', [
    (['/private/SYNTHETIC_USER/app', '--cv-import-child', '--input', '/private/SYNTHETIC_CV.pdf'], '--cv-import-child'),
    (['/private/SYNTHETIC_USER/app', '--unknown=SYNTHETIC_SECRET'], 'gui'),
    (['/private/SYNTHETIC_USER/app', '--local-backup', 'create', '/private/SYNTHETIC_PROFILE'], '--local-backup'),
])
def test_early_boot_summary_excludes_paths_and_argument_values(argv, mode):
    message = boot_summary(argv)
    assert f'mode={mode}' in message
    assert 'SYNTHETIC_' not in message
    assert '/private/' not in message
    assert f'argument_count={len(argv)-1}' in message
