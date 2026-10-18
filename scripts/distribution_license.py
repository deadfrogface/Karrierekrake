"""Use declared license metadata or reviewed, exact-version license-file hashes."""
from __future__ import annotations

from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re


def normalized_name(value):
    return re.sub(r'[-_.]+', '-', value).casefold()


@lru_cache(maxsize=1)
def pinned_evidence():
    return json.loads((Path(__file__).resolve().parents[1] /
                       'packaging/license_evidence.json').read_text(encoding='utf-8'))['entries']


def distribution_license(dist, *, evidence=None):
    expression = dist.metadata.get('License-Expression')
    if expression:
        return [{'expression': expression}], [{'name': 'kk:license-evidence', 'value': 'metadata:License-Expression'}]
    name = dist.metadata.get('License')
    if name and name != 'UNKNOWN':
        return [{'license': {'name': name[:500]}}], [{'name': 'kk:license-evidence', 'value': 'metadata:License'}]
    get_all = getattr(dist.metadata, 'get_all', None)
    classifiers = get_all('Classifier', []) if callable(get_all) else dist.metadata.get('Classifier', [])
    if isinstance(classifiers, str):
        classifiers = [classifiers]
    declared = [item for item in classifiers if item.startswith('License ::')]
    # A generic BSD classifier cannot distinguish the actual BSD variant.
    # Only this exact unambiguous classifier is translated automatically.
    if declared == ['License :: OSI Approved :: MIT License']:
        return [{'expression': 'MIT'}], [{'name': 'kk:license-evidence', 'value': 'metadata:MIT-classifier'}]
    for entry in pinned_evidence() if evidence is None else evidence:
        if (normalized_name(dist.metadata['Name']) != normalized_name(entry['name'])
                or dist.version != entry['version']):
            continue
        for file in dist.files or ():
            if Path(str(file)).name != entry['filename']:
                continue
            path = Path(dist.locate_file(file))
            try:
                if path.stat().st_size > 2 * 1024**2:
                    continue
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
            except OSError:
                continue
            # Exact digests only: the reference file, or one recorded for a
            # platform wheel with other bytes (e.g. CRLF on win_amd64).
            accepted = {entry['sha256'], *(entry.get('platform_sha256') or {}).values()}
            if digest in accepted:
                return [{'expression': entry['expression']}], [
                    {'name': 'kk:license-evidence', 'value': 'pinned-license-file'},
                    {'name': 'kk:license-file-sha256', 'value': digest},
                    {'name': 'kk:license-source', 'value': entry['source_url']}]
    return None, []
