"""Import collected wheel CycloneDX components without build-path identities."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath


def collected_components(datas):
    components, unresolved, seen = [], [], set()
    for row in datas:
        name, path = str(row[0]), Path(row[1])
        parts = PurePosixPath(name).parts
        if 'sboms' not in parts or not name.endswith('.json'):
            continue
        if name in seen:
            raise ValueError('embedded_sbom_duplicate_input')
        seen.add(name)
        if (PurePosixPath(name).is_absolute() or '..' in parts or '\\' in name
                or path.stat().st_size > 2 * 1024**2):
            raise ValueError('embedded_sbom_invalid_input')
        raw = path.read_bytes()
        document = json.loads(raw)
        if (not isinstance(document, dict) or document.get('bomFormat') != 'CycloneDX'
                or not isinstance(document.get('components'), list)):
            raise ValueError('embedded_sbom_invalid_document')
        source_hash = hashlib.sha256(raw).hexdigest()
        for index, source in enumerate(document['components']):
            if (not isinstance(source, dict) or source.get('type') != 'library'
                    or any(not isinstance(source.get(k), str) or not source[k].strip()
                           for k in ('name', 'version'))):
                raise ValueError('embedded_sbom_invalid_component')
            ref = 'embedded:' + hashlib.sha256((name + ':' + str(index)).encode()).hexdigest()
            component = {'type': 'library', 'name': source['name'], 'version': source['version'],
                         'bom-ref': ref, 'properties': [
                             {'name': 'kk:embedded-sbom', 'value': name},
                             {'name': 'kk:embedded-sbom-sha256', 'value': source_hash}]}
            purl = source.get('purl')
            if isinstance(purl, str) and purl.startswith('pkg:') and 'file:' not in purl:
                component['purl'] = purl
            else:
                unresolved.append('embedded-identity:' + ref)
            for key in ('licenses', 'hashes'):
                if key in source:
                    if not isinstance(source[key], list):
                        raise ValueError('embedded_sbom_invalid_component')
                    component[key] = source[key]
            if not component.get('licenses'):
                unresolved.append('embedded-license:' + ref)
            components.append(component)
    return components, unresolved
