"""Attribute Linux build inputs to installed distro packages, without guessing ABI versions."""
from __future__ import annotations

from pathlib import Path
import subprocess
import platform
import sys
from urllib.parse import quote, urlencode


def linux_packages(paths):
    if not sys.platform.startswith('linux'):
        return {}
    aliases = {}
    for value in paths:
        path = Path(value)
        for candidate in {str(path), str(path.resolve())}:
            aliases[candidate] = str(path.resolve())
            if candidate.startswith('/usr/lib/'):
                aliases[candidate[4:]] = str(path.resolve())
            elif candidate.startswith('/lib/'):
                aliases['/usr' + candidate] = str(path.resolve())
    if not aliases:
        return {}
    try:
        owners = subprocess.run(['dpkg-query', '-S', *sorted(aliases)], text=True,
                                capture_output=True, timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return {}
    by_path = {}
    for line in owners.stdout.splitlines():
        package, separator, file = line.rpartition(': ')
        if separator and file in aliases and ', ' not in package:
            by_path[aliases[file]] = package
    if not by_path:
        return {}
    try:
        info = subprocess.run(['dpkg-query', '-W', '-f=${binary:Package}\t${Version}\n',
                               *sorted(set(by_path.values()))], text=True,
                              capture_output=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return {}
    versions = dict(line.split('\t', 1) for line in info.stdout.splitlines() if '\t' in line)
    try:
        release = platform.freedesktop_os_release()
    except OSError:
        release = {}
    result = {}
    for path, package in by_path.items():
        version = versions.get(package)
        if not version:
            continue
        # Distro package versions include security backport revisions; they are
        # kept distinct from an upstream version inferred from a SONAME.
        entry = {'name': package, 'version': version, 'bom-ref': 'os-package:' + package}
        distro = release.get('ID', '')
        if distro:
            qualifiers = {}
            if ':' in package:
                qualifiers['arch'] = package.split(':', 1)[1]
            if release.get('VERSION_ID'):
                qualifiers['distro'] = distro + '-' + release['VERSION_ID']
            entry['purl'] = ('pkg:deb/' + quote(distro, safe='') + '/'
                             + quote(package.split(':')[0], safe='') + '@' + quote(version, safe='')
                             + ('?' + urlencode(qualifiers) if qualifiers else ''))
        result[path] = entry
    return result
