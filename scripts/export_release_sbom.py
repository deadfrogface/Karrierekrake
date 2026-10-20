"""Build-time CycloneDX inventory from PyInstaller's resolved inputs.

No network and no assumed license for unidentified native components.
"""
from __future__ import annotations

import hashlib
from importlib import metadata
import json
from pathlib import Path
import re

from scripts.export_runtime_sbom import build_sbom


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


# OpenSSL 3 libraries per platform (macOS dylib, Windows DLL, Linux SONAME) -> their libcrypto.
_OPENSSL_LIBRARIES = {
    'libcrypto.3.dylib': 'libcrypto.3.dylib', 'libssl.3.dylib': 'libcrypto.3.dylib',
    'libcrypto-3-x64.dll': 'libcrypto-3-x64.dll', 'libssl-3-x64.dll': 'libcrypto-3-x64.dll',
    'libcrypto-3-arm64.dll': 'libcrypto-3-arm64.dll', 'libssl-3-arm64.dll': 'libcrypto-3-arm64.dll',
    'libcrypto-3.dll': 'libcrypto-3.dll', 'libssl-3.dll': 'libcrypto-3.dll',
    'libcrypto.so.3': 'libcrypto.so.3', 'libssl.so.3': 'libcrypto.so.3',
}


def _openssl_crypto_name(file_name: str) -> str:
    """The libcrypto that carries the release string for an OpenSSL 3 library, or ''."""
    return _OPENSSL_LIBRARIES.get(file_name.lower(), '')


def _record_matches(dist, path: Path) -> bool | None:
    """True/False: ``dist``'s RECORD hash for ``path`` matches/differs; None: not recorded."""
    import base64
    target = str(path.resolve())
    for file in dist.files or ():
        if str(Path(dist.locate_file(file)).resolve()) != target:
            continue
        if file.hash is None or file.hash.mode != 'sha256':
            return None
        actual = base64.urlsafe_b64encode(hashlib.sha256(path.read_bytes()).digest()).rstrip(b'=').decode()
        return actual == file.hash.value
    return None


def _collected_owner_names(modules, owners, pure, installed):
    """Distribution names that own the collected pure modules.

    A top-level module claimed by several installed distributions (urllib3 and
    urllib3-future both install ``urllib3/``) belongs to the claimant whose
    RECORD hashes match the collected files: at least one match, no mismatch.
    If no claimant matches, all stay listed and the module is reported as
    ambiguous (license review stays open). Teamlead 19.10.2026: the SBOM
    describes the built package, not the build environment.
    """
    by_name = {d.metadata.get('Name', '').lower().replace('_', '-'): d for d in installed}
    names, ambiguous = set(), set()
    for module in modules:
        claimants = {name.lower().replace('_', '-') for name in owners.get(module, [])}
        if len(claimants) <= 1:
            names |= claimants
            continue
        paths = [Path(row[1]) for row in pure
                 if str(row[0]).split('.')[0] == module and row[1] and Path(row[1]).is_file()]
        matching = set()
        for name in claimants:
            dist = by_name.get(name)
            results = [_record_matches(dist, path) for path in paths] if dist else []
            if True in results and False not in results:
                matching.add(name)
        if matching:
            names |= matching
        else:
            names |= claimants
            ambiguous.add(module)
    return names, ambiguous


def export_release_inventory(root, output, binaries, pure, datas=(), *, require_python_runtime=False):
    root, output = Path(root), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    modules = {str(row[0]).split('.')[0] for row in pure}
    owners = metadata.packages_distributions()
    installed = list(metadata.distributions())
    names, ambiguous = _collected_owner_names(modules, owners, pure, installed)
    # A dependency may contribute only native binaries or collected data/source
    # files, with no module in a.pure (e.g. _cffi_backend or jobspy data).
    # Attribute those inputs too; otherwise their distribution/license vanishes.
    resolved_inputs = {str(Path(row[1]).resolve()) for row in [*binaries, *datas]}
    distributions = []
    for dist in installed:
        name = dist.metadata.get('Name', '').lower().replace('_', '-')
        if name in names or any(str(Path(dist.locate_file(file)).resolve()) in resolved_inputs
                                for file in dist.files or ()):
            distributions.append(dist)
    bom = build_sbom(distributions)
    components = bom['components']
    notices = ['Karrierekrake build license notices',
               'License metadata is reported as supplied; unresolved native licenses require review.']
    unresolved = ['module-owner-ambiguous:' + module for module in sorted(ambiguous)]
    native_owners = {}
    for dist, component in zip(sorted(distributions, key=lambda d: (d.metadata['Name'].casefold(), d.version)), components):
        from scripts.distribution_license import distribution_license
        licenses, evidence = distribution_license(dist)
        if licenses:
            component['licenses'] = licenses
            component.setdefault('properties', []).extend(evidence)
        else:
            unresolved.append(component['name'])
        for file in dist.files or ():
            native_owners[str(Path(dist.locate_file(file)).resolve())] = component
            if re.search(r'(^|/)(licenses?|copying|notice)([./_-]|$)', str(file), re.I):
                path = Path(dist.locate_file(file))
                if path.is_file() and path.stat().st_size <= 2 * 1024**2:
                    notices.extend(['\n--- ' + component['name'] + ' / ' + str(file) + ' ---',
                                    path.read_text(encoding='utf-8', errors='replace')])
    from scripts.native_package_metadata import linux_packages, distro_notices
    os_owners = linux_packages([row[1] for row in binaries])
    os_components = {}
    from scripts.native_python_metadata import python_runtime_owners
    python_owners = python_runtime_owners([row[1] for row in binaries])
    python_components = {}
    seen = set()
    for row in binaries:
        name, source = str(row[0]), Path(row[1])
        if not source.is_file() or name in seen:
            continue
        seen.add(name)
        components.append({'type': 'file', 'name': name, 'bom-ref': 'native:' + name,
                           'hashes': [{'alg': 'SHA-256', 'content': digest(source)}],
                           'properties': [{'name': 'kk:inventory-stage', 'value': 'pyinstaller-input'}]})
        # OpenSSL minor versions share one SONAME. Record the embedded release
        # so a native CVE review can distinguish e.g. 3.0.x from 3.6.x.
        crypto_name = _openssl_crypto_name(Path(name).name)
        if crypto_name:
            from scripts.macos_openssl import openssl_release
            try:
                release = openssl_release(source.parent / crypto_name)
                components[-1]['version'] = '.'.join(map(str, release))
                components[-1]['properties'].append({
                    'name': 'kk:native-product', 'value': 'OpenSSL'})
            except (OSError, RuntimeError):
                unresolved.append('native-version:' + name)
        os_owner = os_owners.get(str(source.resolve()))
        if os_owner:
            os_components[os_owner['bom-ref']] = {
                'type': 'library', **os_owner,
                'properties': [*os_owner.get('properties', []),
                               {'name': 'kk:version-source', 'value': 'build-host-dpkg'}]}
            components[-1]['properties'].append({
                'name': 'kk:os-package', 'value': os_owner['bom-ref']})
        python_owner = python_owners.get(str(source.resolve()))
        if python_owner:
            python_components[python_owner['bom-ref']] = python_owner
            components[-1]['properties'].append({
                'name': 'kk:python-runtime', 'value': python_owner['bom-ref']})
        owner = native_owners.get(str(source.resolve()))
        if owner and owner.get('licenses'):
            components[-1]['licenses'] = owner['licenses']
            components[-1]['properties'].append({'name': 'kk:distribution', 'value': owner['name']})
        else:
            unresolved.append('native:' + name)
    from scripts.embedded_sbom import collected_components
    embedded, embedded_unresolved = collected_components(datas)
    components.extend(embedded)
    unresolved.extend(embedded_unresolved)
    components.extend(os_components.values())
    if require_python_runtime and not python_components:
        raise ValueError('release_python_runtime_unidentified')
    components.extend(python_components.values())
    if python_components:
        unresolved.append("runtime-license:CPython")
        from scripts.native_python_metadata import python_license_notice
        python_notice, python_notice_hash = python_license_notice()
        if python_notice is None:
            unresolved.append('runtime-notice:CPython')
        else:
            notices.extend(['\n--- CPython / build-interpreter LICENSE.txt ---', python_notice])
            python_components['runtime:cpython']['properties'].append({
                'name': 'kk:license-file-sha256', 'value': python_notice_hash})
    distro_texts, missing_notices = distro_notices(c['name'] for c in os_components.values())
    notices.extend(distro_texts)
    unresolved.extend('native-notice:' + name for name in missing_notices)
    geo = json.loads((root / 'data/geo/manifest.json').read_text(encoding='utf-8'))
    for country, entry in geo['files'].items():
        path = root / 'data/geo' / entry['path']
        if digest(path) != entry['sha256']:
            raise ValueError('dataset_inventory_hash_mismatch')
        components.append({'type': 'data', 'name': 'GeoNames ' + country, 'version': geo['version'],
                           'bom-ref': 'dataset:geonames:' + country,
                           'licenses': [{'license': {'name': geo['license']}}],
                           'hashes': [{'alg': 'SHA-256', 'content': entry['sha256']}],
                           'externalReferences': [{'type': 'distribution', 'url': geo['source_url']}]})
    notices.append('\n--- dataset: GeoNames ---\n' + geo['attribution'] + '\nLicense: ' + geo['license']
                   + ('\nLicense terms: https://creativecommons.org/licenses/by/4.0/' if 'Attribution 4.0' in geo['license'] else '')
                   + '\nSource: ' + geo['source_url'])
    from guenther.model_manager import MODEL_CATALOG
    from guenther.setup_models import SETUP_MODEL_CATALOG
    for name, entry in {**MODEL_CATALOG, **SETUP_MODEL_CATALOG}.items():
        # Models are separate user downloads, never part of the package: the notices carry their
        # license, origin and expected hash so the user-facing record matches what is downloaded.
        notices.append('\n--- model (separate user download): ' + name + ' ---\nLicense: ' + entry['license']
                       + '\nSource: ' + entry['url'] + '\nSHA-256: ' + entry['sha256'])
        components.append({'type': 'machine-learning-model', 'name': name, 'bom-ref': 'model:' + name,
                           'scope': 'optional',
                           'licenses': [{'license': {'name': entry['license']}}],
                           'hashes': [{'alg': 'SHA-256', 'content': entry['sha256']}],
                           'externalReferences': [{'type': 'distribution', 'url': entry['url']}],
                           'properties': [{'name': 'kk:delivery', 'value': 'separate-user-download'}]})
    # Include every resolved data file (fonts/images/templates included), not
    # just source-tree branding. Absolute build paths never enter the SBOM.
    asset_rows = list(datas) if datas else [(p.relative_to(root).as_posix(), p)
        for p in sorted((root / "assets/brand").rglob("*")) if p.is_file()]
    seen_assets = set()
    for row in asset_rows:
        name, path = str(row[0]), Path(row[1])
        if not path.is_file() or name in seen_assets:
            continue
        seen_assets.add(name)
        component = {"type": "file", "name": name, "bom-ref": "asset:" + name,
                     "hashes": [{"alg": "SHA-256", "content": digest(path)}]}
        owner = native_owners.get(str(path.resolve()))
        if owner and owner.get('licenses'):
            component['licenses'] = owner['licenses']
        elif name.replace('\\', '/').startswith('data/geo/'):
            component['licenses'] = [{'license': {'name': geo['license']}}]
        else:
            unresolved.append("asset-rights:" + name)
        components.append(component)
    components.sort(key=lambda item: item['bom-ref'])
    (output / 'release-sbom.json').write_text(json.dumps(bom, indent=2) + '\n', encoding='utf-8')
    (output / 'THIRD_PARTY_NOTICES.txt').write_text('\n'.join(notices), encoding='utf-8')
    (output / 'license-review.json').write_text(json.dumps({
        'status': 'review-required' if unresolved else 'metadata-complete',
        'unresolved': sorted(unresolved),
        'scope': 'Resolved Python modules, native build inputs, bundled data/assets/fonts, geodata, optional model catalog. '
                 'OS libraries not collected into the artifact and post-signing binary hashes are outside this inventory.'}, indent=2) + '\n', encoding='utf-8')
