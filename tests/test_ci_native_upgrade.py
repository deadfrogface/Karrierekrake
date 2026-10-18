"""Keep a symlinked OS temporary root consistent with transaction validation."""
from contextlib import contextmanager
import json
import os
from pathlib import Path

import pytest
from scripts import ci_native_upgrade as upgrade


@pytest.mark.skipif(os.name == 'nt', reason='POSIX temporary directory alias')
def test_upgrade_uses_canonical_temporary_directory_before_staging(tmp_path, monkeypatch):
    real = tmp_path / 'physical'
    real.mkdir()
    alias = tmp_path / 'alias'
    alias.symlink_to(real, target_is_directory=True)
    current = {'target': 'linux-x86_64', 'commit': 'a'*40, 'sequence': 1}
    old, candidate = tmp_path/'old', tmp_path/'candidate'
    for directory in (old, candidate):
        directory.mkdir()
        (directory/'native-current.json').write_text(json.dumps(current))

    @contextmanager
    def temporary(**kwargs):
        yield str(alias)

    @contextmanager
    def unpack(archive, directory):
        assert directory == real / 'install'
        app = directory / 'Karrierekrake'
        (app/'_internal').mkdir(parents=True)
        (app/'_internal/native-current.json').write_text(json.dumps(current))
        yield app

    monkeypatch.setattr(upgrade.tempfile, 'TemporaryDirectory', temporary)
    monkeypatch.setattr(upgrade, 'unpack', unpack)
    monkeypatch.setattr(upgrade, 'native_image', lambda _: False)
    # Stop at the unchanged native-image gate: this fixture never claims an
    # actual bundle transition or creates a forged healthy marker.
    with pytest.raises(ValueError, match='requires_native_baseline'):
        upgrade.verify(old, candidate, tmp_path/'report.json')


def test_transition_log_prints_candidate_and_installed_identity(capsys):
    upgrade.log_transition({'sequence': 39087873965, 'commit': 'b'*40, 'target': 'macos-x86_64'},
                           {'sequence': 39086930936, 'commit': 'a'*40, 'sha256': 'c'*64})
    assert capsys.readouterr().out.splitlines() == [
        'native_upgrade_candidate sequence=39086930936 commit=' + 'a'*40,
        'native_upgrade_installed sequence=39087873965 commit=' + 'b'*40]
