"""Attach already-tested native artifacts to the matching Windows release."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.app_updates import REPOSITORY, digest
from core.native_updates import ASSETS, METADATA
from core.release_identity import VERSION


def manifests(artifacts: Path, tag: str, commit: str, *, targets: tuple[str, ...] | None = None, model: dict | None = None) -> list[Path]:
    if not re.fullmatch(r'update-[0-9]+-[a-f0-9]{12}', tag):
        raise ValueError('invalid_release_tag')
    outputs = []
    for target in targets or tuple(ASSETS):
        filename = ASSETS[target]
        folder = artifacts / f'Karrierekrake-{target}'
        archive = folder / filename
        current = json.loads((folder / METADATA).read_text(encoding='utf-8'))
        acceptance = json.loads((folder / 'acceptance.json').read_text(encoding='utf-8'))
        if (current.get('target') != target or current.get('commit') != commit
                or current.get('version') != VERSION
                or type(current.get('sequence')) is not int or current['sequence'] <= 0
                or acceptance.get('ok') is not True or not archive.is_file()):
            raise ValueError('native_release_gate_failed')
        try:
            backup = json.loads((folder / 'backup-restore.json').read_text(encoding='utf-8'))
            gui = json.loads((folder / 'gui-startup.json').read_text(encoding='utf-8'))
            upgrade = json.loads((folder / 'upgrade.json').read_text(encoding='utf-8'))
        except (OSError, ValueError) as exc:
            raise ValueError('native_recovery_acceptance_missing') from exc
        if not isinstance(backup, dict) or not isinstance(gui, dict):
            raise ValueError('native_recovery_acceptance_failed')
        steps = backup.get('steps')
        identity = gui.get('identity')
        image_hash = backup.get('executable_sha256', '')
        if (backup.get('ok') is not True or backup.get('native_image') is not True
                or backup.get('restored_database_path_confirmed') is not True
                or backup.get('synthetic_marker_preserved') is not True
                or not isinstance(steps, dict)
                or not all(isinstance(steps.get(key), dict)
                           and type(steps[key].get('exit_code')) is int and steps[key]['exit_code'] == 0
                           for key in ('initial_smoke', 'create', 'verify', 'restore', 'restored_smoke'))
                or gui.get('ok') is not True or gui.get('startup_acknowledged') is not True
                or not isinstance(identity, dict)
                or any(identity.get(key) != current.get(key) for key in ('target', 'commit', 'sequence', 'version'))
                or not isinstance(image_hash, str) or not re.fullmatch(r'[a-f0-9]{64}', image_hash)
                or image_hash != gui.get('executable_sha256')):
            raise ValueError('native_recovery_acceptance_failed')
        if (not isinstance(upgrade, dict) or upgrade.get('ok') is not True
                or upgrade.get('result') != 'success'
                or upgrade.get('startup_acknowledged') is not True
                or upgrade.get('candidate_installed') is not True
                or upgrade.get('synthetic_marker_preserved') is not True
                or not isinstance(upgrade.get('candidate'), dict)
                or any(upgrade['candidate'].get(key) != current.get(key)
                       for key in ('target', 'commit', 'sequence', 'version'))
                or not isinstance(upgrade.get('baseline'), dict)
                or upgrade['baseline'].get('target') != target
                or upgrade['baseline'].get('commit') == commit
                or type(upgrade['baseline'].get('sequence')) is not int
                or not 0 < upgrade['baseline']['sequence'] < current['sequence']
                or upgrade.get('executable_sha256') != image_hash):
            raise ValueError('native_upgrade_acceptance_failed')
        manifest = dict(current, protocol=1, tag=tag, size=archive.stat().st_size,
                        sha256=digest(archive),
                        url=f'https://github.com/{REPOSITORY}/releases/download/{tag}/{filename}')
        if model is not None:
            manifest['model'] = model
        path = artifacts / f'native-manifest-{target}.json'
        path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        outputs.extend([archive, path])
        proof = artifacts / f'native-acceptance-{target}.json'
        proof.write_text(json.dumps({'identity': current, 'acceptance': acceptance,
                                    'backup_restore': backup, 'gui_startup': gui, 'upgrade': upgrade}, indent=2) + '\n', encoding='utf-8')
        outputs.append(proof)
        for name in ('release-sbom.json', 'THIRD_PARTY_NOTICES.txt', 'license-review.json'):
            compliance = folder / (target + '-' + name)
            if not compliance.is_file():
                raise ValueError('native_compliance_inventory_missing')
            outputs.append(compliance)
    return outputs


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--artifacts', type=Path, required=True)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--commit', required=True)
    args = parser.parse_args()
    paths = manifests(args.artifacts, args.tag, args.commit)
    # All three acceptance results must pass before any assets are attached.
    subprocess.run(['gh', 'release', 'upload', args.tag, '--repo', REPOSITORY,
                    *map(str, paths), '--clobber'], check=True)
