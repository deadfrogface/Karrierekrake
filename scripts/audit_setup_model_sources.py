"""Verify pinned public model metadata; never equate metadata with a load test."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from guenther.setup_models import SETUP_MODEL_CATALOG


def audit(catalog=None, *, opener=urlopen):
    rows = []
    for model_id, entry in (SETUP_MODEL_CATALOG if catalog is None else catalog).items():
        revision = entry['url'].split('/resolve/', 1)[1].split('/', 1)[0]
        source = 'https://huggingface.co/api/models/' + entry['source_repo'] + '/revision/' + revision + '?blobs=true'
        row = {'model_id': model_id, 'revision': revision, 'metadata_source': source, 'ok': False}
        try:
            with opener(source, timeout=30) as response:
                data = json.load(response)
            file = next(f for f in data.get('siblings', []) if f['rfilename'] == entry['filename'])
            lfs = file.get('lfs') or {}
            row.update(resolved_revision=data.get('sha'), license=(data.get('cardData') or {}).get('license'),
                       size=lfs.get('size', file.get('size')), sha256=lfs.get('sha256'))
            row['ok'] = (row['resolved_revision'] == revision
                         and row['license'] == entry['license'].lower()
                         and row['size'] == entry['approx_bytes'] and row['sha256'] == entry['sha256'])
        except (OSError, ValueError, TypeError, AttributeError, KeyError, StopIteration) as exc:
            row['error'] = type(exc).__name__  # no tokens/headers or raw response in report
        rows.append(row)
    return {'checked_at': datetime.now(timezone.utc).isoformat(),
            'scope': 'Pinned source metadata only; runtime, hardware and complete license review are separate gates.',
            'ok': bool(rows) and all(row['ok'] for row in rows), 'models': rows}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    report = audit()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
