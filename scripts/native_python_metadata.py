"""Attribute CPython-owned native inputs to the actual build interpreter.

No version is inferred from a filename. Third-party extensions and vendor DLLs
are excluded even when installed underneath the standard-library directory.
"""
from __future__ import annotations

from pathlib import Path
import platform
import hashlib
import json
import sys
import sysconfig


def identify(paths, *, stdlib, prefix, libraries, version, windows=False):
    stdlib, prefix = Path(stdlib).resolve(), Path(prefix).resolve()
    extension_root = prefix / 'DLLs' if windows else stdlib / 'lib-dynload'
    libraries = {Path(path).resolve() for path in libraries}
    result = {}
    component = {'type': 'library', 'name': 'CPython', 'version': version,
                 'bom-ref': 'runtime:cpython',
                 'externalReferences': [{'type': 'vcs', 'url': 'https://github.com/python/cpython/tree/v' + version}],
                 'properties': [{'name': 'kk:version-source', 'value': 'build-interpreter'}]}
    for value in paths:
        path = Path(value).resolve()
        extension = (path.parent == extension_root
                     and path.suffix.lower() == ('.pyd' if windows else '.so'))
        if path in libraries or extension:
            result[str(path)] = component
    return result


def python_runtime_owners(paths):
    libraries = []
    libdir, libname = sysconfig.get_config_var('LIBDIR'), sysconfig.get_config_var('LDLIBRARY')
    if libname:
        # Relocatable standalone builds may retain a configured LIBDIR while
        # loading libpython from the relocated installation prefix.
        libraries.append(Path(sys.base_prefix) / 'lib' / libname)
        if libdir:
            libraries.append(Path(libdir) / libname)
    if sys.platform == 'win32':
        libraries.extend(Path(sys.base_prefix) / name for name in (
            f'python{sys.version_info.major}{sys.version_info.minor}.dll', 'python3.dll'))
    framework = sysconfig.get_config_var('PYTHONFRAMEWORK')
    framework_prefix = sysconfig.get_config_var('PYTHONFRAMEWORKPREFIX')
    if framework and framework_prefix:
        libraries.append(Path(framework_prefix) / (framework + '.framework') / 'Versions' /
                         str(sysconfig.get_config_var('VERSION')) / framework)
    result = identify(paths, stdlib=sysconfig.get_path('stdlib'), prefix=sys.base_prefix,
                      libraries=libraries, version=platform.python_version(), windows=sys.platform == 'win32')
    provenance = build_provenance(sys.base_prefix, platform.python_version())
    for component in {c['bom-ref']: c for c in result.values()}.values():
        component['properties'].extend(provenance)
    return result


def python_license_notice(*, stdlib=None, prefix=None):
    """Copy the interpreter's supplied terms, without guessing an SPDX ID."""
    for path in (Path(stdlib or sysconfig.get_path('stdlib')) / 'LICENSE.txt',
                 Path(prefix or sys.base_prefix) / 'LICENSE.txt'):
        try:
            if path.stat().st_size > 2 * 1024**2:
                continue
            data = path.read_bytes()
            return data.decode('utf-8'), hashlib.sha256(data).hexdigest()
        except (OSError, UnicodeDecodeError):
            continue
    return None, None


def build_provenance(prefix, version):
    receipt = Path(prefix) / 'kk-runtime-provenance.json'
    if not receipt.exists():
        return []
    value = json.loads(receipt.read_text(encoding='utf-8'))
    config = json.loads((Path(__file__).resolve().parents[1] / 'packaging/ci_python_runtimes.json').read_text())
    if (not isinstance(value, dict) or value.get('version') != version
            or value.get('version') != config['version'] or value.get('release') != config['release']
            or not any(all(value.get(k) == item[k] for k in ('url', 'sha256', 'size'))
                       for item in config['runtimes'].values())):
        raise ValueError('python_build_provenance_invalid')
    return [{'name': 'kk:python-build-archive', 'value': value['url']},
            {'name': 'kk:python-build-sha256', 'value': value['sha256']},
            {'name': 'kk:python-build-release', 'value': value['release']}]
