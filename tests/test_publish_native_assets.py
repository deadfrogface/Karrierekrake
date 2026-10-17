"""Do not attach incomplete/mismatched native build artifacts to a release."""
import json

import pytest

from core.release_identity import VERSION
from scripts.publish_native_assets import ASSETS, METADATA, manifests


def artifacts(root, commit, native_recovery_proofs):
    for target, filename in ASSETS.items():
        folder = root / f'Karrierekrake-{target}'
        folder.mkdir()
        (folder / filename).write_bytes(b'tested native archive')
        identity = {'target': target, 'commit': commit, 'sequence': 123, 'version': VERSION}
        (folder / METADATA).write_text(json.dumps(identity))
        (folder / 'acceptance.json').write_text(json.dumps({'ok': True}))
        native_recovery_proofs(folder, identity)
        for name in ('release-sbom.json', 'THIRD_PARTY_NOTICES.txt', 'license-review.json'):
            (folder / (target + '-' + name)).write_text('{}')


def test_all_targets_receive_exact_release_urls_and_hashes(tmp_path, native_recovery_proofs):
    commit = 'a' * 40
    tag = 'update-456-' + 'a' * 12
    artifacts(tmp_path, commit, native_recovery_proofs)
    paths = manifests(tmp_path, tag, commit)
    assert len(paths) == 18
    for target, filename in ASSETS.items():
        value = json.loads((tmp_path / f'native-manifest-{target}.json').read_text())
        assert value['commit'] == commit and value['sequence'] == 123
        assert value['url'].endswith(f'/{tag}/{filename}')
        assert len(value['sha256']) == 64


@pytest.mark.parametrize('failure', ['missing_gui', 'unacknowledged_gui', 'stale_gui',
                                    'wrong_binary', 'failed_restore', 'source_wrapper'])
def test_recovery_proofs_are_required_for_the_same_actual_binary(tmp_path, failure, native_recovery_proofs):
    commit = 'a' * 40
    artifacts(tmp_path, commit, native_recovery_proofs)
    folder = tmp_path / 'Karrierekrake-linux-x86_64'
    gui = json.loads((folder / 'gui-startup.json').read_text())
    backup = json.loads((folder / 'backup-restore.json').read_text())
    if failure == 'unacknowledged_gui': gui['startup_acknowledged'] = False
    if failure == 'stale_gui': gui['identity']['commit'] = 'b' * 40
    if failure == 'wrong_binary': gui['executable_sha256'] = 'e' * 64
    if failure == 'failed_restore': backup['steps']['restore']['exit_code'] = 1
    if failure == 'source_wrapper': backup['native_image'] = False
    (folder / 'gui-startup.json').write_text(json.dumps(gui))
    (folder / 'backup-restore.json').write_text(json.dumps(backup))
    if failure == 'missing_gui': (folder / 'gui-startup.json').unlink()
    with pytest.raises(ValueError, match='native_recovery_acceptance'):
        manifests(tmp_path, 'update-456-' + 'a' * 12, commit)


@pytest.mark.parametrize('failure', ['wrong_commit', 'failed_acceptance', 'missing_archive'])
def test_failed_or_stale_build_cannot_publish(tmp_path, failure, native_recovery_proofs):
    commit = 'a' * 40
    artifacts(tmp_path, commit, native_recovery_proofs)
    folder = tmp_path / 'Karrierekrake-macos-arm64'
    if failure == 'wrong_commit':
        (folder / METADATA).write_text(json.dumps({'target': 'macos-arm64', 'commit': 'b' * 40, 'sequence': 123, 'version': VERSION}))
    elif failure == 'failed_acceptance':
        (folder / 'acceptance.json').write_text(json.dumps({'ok': False}))
    else:
        (folder / ASSETS['macos-arm64']).unlink()
    with pytest.raises(ValueError):
        manifests(tmp_path, 'update-456-' + 'a' * 12, commit)


@pytest.mark.parametrize('failure', ['missing', 'rollback', 'stale_candidate', 'same_build',
                                    'newer_baseline', 'wrong_binary', 'lost_profile'])
def test_real_upgrade_proof_is_required_before_native_release(tmp_path, failure, native_recovery_proofs):
    commit = 'a' * 40
    artifacts(tmp_path, commit, native_recovery_proofs)
    path = tmp_path / 'Karrierekrake-linux-x86_64/upgrade.json'
    proof = json.loads(path.read_text())
    if failure == 'rollback': proof['result'] = 'rollback'
    if failure == 'stale_candidate': proof['candidate']['commit'] = 'b' * 40
    if failure == 'same_build': proof['baseline']['commit'] = commit
    if failure == 'newer_baseline': proof['baseline']['sequence'] = 999
    if failure == 'wrong_binary': proof['executable_sha256'] = 'e' * 64
    if failure == 'lost_profile': proof['synthetic_marker_preserved'] = False
    path.write_text(json.dumps(proof))
    if failure == 'missing': path.unlink()
    with pytest.raises(ValueError, match='native_(recovery|upgrade)_acceptance'):
        manifests(tmp_path, 'update-456-' + 'a' * 12, commit)
