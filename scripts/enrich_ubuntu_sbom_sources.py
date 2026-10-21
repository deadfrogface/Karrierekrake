"""Recover exact source-package provenance for older Ubuntu build inventories.

Read-only Launchpad queries; never infer a source version from a binary version.
The original SBOM is not overwritten. Unknown/ambiguous records stay unverified.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import copy
import json
from pathlib import Path
import re
from urllib.parse import parse_qs, unquote, urlencode, urlsplit
from urllib.request import urlopen

API = 'https://api.launchpad.net/1.0/'
SERIES = {'ubuntu-22.04': 'jammy', 'ubuntu-24.04': 'noble'}


def get_json(url):
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or parsed.netloc != 'api.launchpad.net' or not parsed.path.startswith('/1.0/'):
        raise ValueError('unexpected_provenance_origin')
    with urlopen(url, timeout=60) as response:
        data = response.read(8 * 1024**2 + 1)
    if len(data) > 8 * 1024**2:
        raise ValueError('provenance_response_too_large')
    return json.loads(data)


def source_identity(component, *, fetch=get_json):
    purl = component.get('purl', '')
    match = re.fullmatch(r'pkg:deb/ubuntu/([^@?]+)@([^?]+)\?(.+)', purl)
    if not match:
        raise ValueError('unsupported_package_url')
    name, version = unquote(match[1]), unquote(match[2])
    qualifiers = parse_qs(match[3])
    distro = qualifiers.get('distro', [''])[0]
    arch = qualifiers.get('arch', [''])[0]
    if distro not in SERIES or not re.fullmatch(r'[a-z0-9]+', arch):
        raise ValueError('unsupported_ubuntu_target')
    if version != component.get('version') or name != component['name'].split(':', 1)[0]:
        raise ValueError('inconsistent_binary_identity')
    target = API + 'ubuntu/' + SERIES[distro] + '/' + arch
    url = API + 'ubuntu/+archive/primary?' + urlencode({
        'ws.op': 'getPublishedBinaries', 'binary_name': name, 'version': version,
        'exact_match': 'true', 'distro_arch_series': target})
    seen, builds = set(), set()
    while url:
        if url in seen or len(seen) >= 100:
            raise ValueError('invalid_provenance_pagination')
        seen.add(url)
        page = fetch(url)
        if not isinstance(page, dict) or not isinstance(page.get('entries'), list):
            raise ValueError('invalid_binary_publications')
        for row in page['entries']:
            if (row.get('binary_package_name') != name or row.get('binary_package_version') != version
                    or row.get('distro_arch_series_link') != target):
                raise ValueError('binary_publication_identity_mismatch')
            link = row.get('build_link')
            if not isinstance(link, str) or not link.startswith(API) or not re.search(r'/\+build/\d+$', link):
                raise ValueError('missing_source_build')
            builds.add(link)
        url = page.get('next_collection_link')
        if url is not None and not isinstance(url, str):
            raise ValueError('invalid_provenance_pagination')
    identities = set()
    for link in sorted(builds):
        build = fetch(link)
        source, source_version = build.get('source_package_name'), build.get('source_package_version')
        if not isinstance(source, str) or not source or not isinstance(source_version, str) or not source_version:
            raise ValueError('missing_source_identity')
        identities.add((source, source_version))
    if len(identities) != 1:
        raise ValueError('missing_or_ambiguous_source_identity')
    source, source_version = identities.pop()
    return source, source_version, sorted(builds)


def enrich(bom, *, fetch=get_json, workers=4):
    result = copy.deepcopy(bom)
    candidates = [c for c in result['components'] if c.get('bom-ref', '').startswith('os-package:')]
    def resolve(component):
        try:
            source, version, links = source_identity(component, fetch=fetch)
            properties = [p for p in component.get('properties', [])
                          if p.get('name') not in {'kk:source-package', 'kk:source-version'}]
            component['properties'] = [*properties, {'name': 'kk:source-package', 'value': source},
                                       {'name': 'kk:source-version', 'value': version},
                                       *({'name': 'kk:source-build', 'value': link} for link in links)]
            return None
        except Exception as exc:
            return {'component': component['bom-ref'], 'reason': type(exc).__name__ + ':' +
                    (str(exc) if isinstance(exc, ValueError) else 'provenance_query_failed')}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        failures = [failure for failure in pool.map(resolve, candidates) if failure]
    return result, failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sbom', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.sbom.resolve() == args.out.resolve():
        raise ValueError('source_inventory_must_not_be_overwritten')
    result, failures = enrich(json.loads(args.sbom.read_text(encoding='utf-8')))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'unverified': failures}))
    return 2 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
