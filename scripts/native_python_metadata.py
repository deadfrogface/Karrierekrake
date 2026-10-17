"""Attribute CPython-owned native inputs to the actual build interpreter.

No version is inferred from a filename. Third-party extensions and vendor DLLs
are excluded even when installed underneath the standard-library directory.
"""
from __future__ import annotations

from pathlib import Path
import platform
import hashlib
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
    if libdir and libname:
        libraries.append(Path(libdir) / libname)
    if sys.platform == 'win32':
        libraries.extend(Path(sys.base_prefix) / name for name in (
            f'python{sys.version_info.major}{sys.version_info.minor}.dll', 'python3.dll'))
    framework = sysconfig.get_config_var('PYTHONFRAMEWORK')
    framework_prefix = sysconfig.get_config_var('PYTHONFRAMEWORKPREFIX')
    if framework and framework_prefix:
        libraries.append(Path(framework_prefix) / (framework + '.framework') / 'Versions' /
                         str(sysconfig.get_config_var('VERSION')) / framework)
    return identify(paths, stdlib=sysconfig.get_path('stdlib'), prefix=sys.base_prefix,
                    libraries=libraries, version=platform.python_version(), windows=sys.platform == 'win32')


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
