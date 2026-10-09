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
        manifest = dict(current, protocol=1, tag=tag, size=archive.stat().st_size,
                        sha256=digest(archive),
                        url=f'https://github.com/{REPOSITORY}/releases/download/{tag}/{filename}')
        if model is not None:
            manifest['model'] = model
        path = artifacts / f'native-manifest-{target}.json'
        path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        outputs.extend([archive, path])
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
