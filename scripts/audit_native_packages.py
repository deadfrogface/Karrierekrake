"""Audit explicitly attributed Ubuntu native source packages against OSV.

Scope is the supplied build SBOM, not the running host. Unmapped native files,
missing source versions, unsupported ecosystems and query failures remain
unverified. No SONAME or binary-package name is guessed to be a source package.
API contract: https://google.github.io/osv.dev/post-v1-query/
Ubuntu source identity: https://google.github.io/osv.dev/post-v1-ubuntu-binary-to-source/
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen


def query_osv(payload):
    request = Request('https://api.osv.dev/v1/query', data=json.dumps(payload).encode(),
                      headers={'Content-Type': 'application/json'}, method='POST')
    with urlopen(request, timeout=60) as response:
        return json.load(response)


def package_query(component):
    properties = {p['name']: p['value'] for p in component.get('properties', [])}
    source, version = properties.get('kk:source-package'), properties.get('kk:source-version')
    if not source or not version:
        raise ValueError('missing_source_package_identity')
    purl = component.get('purl', '')
    if not purl.startswith('pkg:deb/ubuntu/'):
        raise ValueError('unsupported_native_ecosystem')
    distro = parse_qs(urlsplit(purl).query).get('distro', [''])[0]
    match = re.fullmatch(r'ubuntu-(\d{2}\.04)', distro)
    if not match or int(match[1][:2]) % 2:
        raise ValueError('unsupported_ubuntu_release')
    return {'package': {'name': source, 'ecosystem': 'Ubuntu:' + match[1] + ':LTS'},
            'version': version}


def query_all(payload, query):
    findings, tokens = {}, set()
    current = dict(payload)
    while True:
        response = query(current)
        if not isinstance(response, dict) or set(response) - {'vulns', 'next_page_token'}:
            raise ValueError('invalid_osv_response')
        vulns = response.get('vulns', [])
        if not isinstance(vulns, list):
            raise ValueError('invalid_osv_vulns')
        for vuln in vulns:
            if not isinstance(vuln, dict) or not isinstance(vuln.get('id'), str) or not vuln['id']:
                raise ValueError('invalid_osv_vulnerability')
            findings[vuln['id']] = vuln
        token = response.get('next_page_token', '')
        if not isinstance(token, str) or token in tokens:
            raise ValueError('invalid_osv_pagination')
        if not token:
            break
        tokens.add(token)
        current = {**payload, 'page_token': token}
    return [findings[key] for key in sorted(findings)]


def audit(bom, *, query=query_osv):
    components = bom.get('components')
    if not isinstance(components, list):
        raise ValueError('invalid_native_sbom')
    results, unverified, checked, memo = [], [], set(), {}
    for component in components:
        reference = component.get('bom-ref', '')
        if not reference.startswith('os-package:'):
            continue
        try:
            payload = package_query(component)
            key = json.dumps(payload, sort_keys=True)
            if key not in memo:
                memo[key] = query_all(payload, query)
            results.append({'component': reference, 'query': payload, 'vulnerabilities': memo[key]})
            checked.add(reference)
        except Exception as exc:
            # Continue independent packages; never convert an unavailable query
            # to a successful zero-findings result. Avoid URLs/paths in errors.
            unverified.append({'component': reference, 'reason': type(exc).__name__ + ':' +
                               (str(exc) if isinstance(exc, ValueError) else 'query_failed')})
    native_files = 0
    for component in components:
        reference = component.get('bom-ref', '')
        if reference.startswith('native:'):
            native_files += 1
            owners = {p.get('value') for p in component.get('properties', [])
                      if p.get('name') == 'kk:os-package'}
            if not owners.intersection(checked):
                unverified.append({'component': reference, 'reason': 'no_verified_source_package'})
    if not native_files:
        unverified.append({'component': 'inventory', 'reason': 'no_native_files'})
    if not results:
        unverified.append({'component': 'inventory', 'reason': 'no_native_packages_queried'})
    findings = sorted({v['id'] for row in results for v in row['vulnerabilities']})
    return {'schema': 'karrierekrake.native-osv-audit.v1',
            'queried_at': datetime.now(timezone.utc).isoformat(),
            'scope': 'Attributed Ubuntu source packages in the supplied build inventory; no host or whole-product clearance.',
            'status': 'OFFEN' if findings or unverified else 'IMPLEMENTIERT – PRÜFUNG OFFEN',
            'native_files': native_files, 'queries': results, 'finding_ids': findings,
            'unverified': unverified}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sbom', type=Path)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    report = audit(json.loads(args.sbom.read_text(encoding='utf-8')))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': report['status'], 'queries': len(report['queries']),
                      'findings': len(report['finding_ids']), 'unverified': len(report['unverified'])}))
    return 1 if report['finding_ids'] else (2 if report['unverified'] else 0)


if __name__ == '__main__':
    raise SystemExit(main())
