"""Do not attach incomplete/mismatched native build artifacts to a release."""
import json

import pytest

from core.release_identity import VERSION
from scripts.publish_native_assets import ASSETS, METADATA, manifests


def artifacts(root, commit):
    for target, filename in ASSETS.items():
        folder = root / f'Karrierekrake-{target}'
        folder.mkdir()
        (folder / filename).write_bytes(b'tested native archive')
        (folder / METADATA).write_text(json.dumps({'target': target, 'commit': commit, 'sequence': 123, 'version': VERSION}))
        (folder / 'acceptance.json').write_text(json.dumps({'ok': True}))


def test_all_targets_receive_exact_release_urls_and_hashes(tmp_path):
    commit = 'a' * 40
    tag = 'update-456-' + 'a' * 12
    artifacts(tmp_path, commit)
    paths = manifests(tmp_path, tag, commit)
    assert len(paths) == 6
    for target, filename in ASSETS.items():
        value = json.loads((tmp_path / f'native-manifest-{target}.json').read_text())
        assert value['commit'] == commit and value['sequence'] == 123
        assert value['url'].endswith(f'/{tag}/{filename}')
        assert len(value['sha256']) == 64


@pytest.mark.parametrize('failure', ['wrong_commit', 'failed_acceptance', 'missing_archive'])
def test_failed_or_stale_build_cannot_publish(tmp_path, failure):
    commit = 'a' * 40
    artifacts(tmp_path, commit)
    folder = tmp_path / 'Karrierekrake-macos-arm64'
    if failure == 'wrong_commit':
        (folder / METADATA).write_text(json.dumps({'target': 'macos-arm64', 'commit': 'b' * 40, 'sequence': 123, 'version': VERSION}))
    elif failure == 'failed_acceptance':
        (folder / 'acceptance.json').write_text(json.dumps({'ok': False}))
    else:
        (folder / ASSETS['macos-arm64']).unlink()
    with pytest.raises(ValueError):
        manifests(tmp_path, 'update-456-' + 'a' * 12, commit)
