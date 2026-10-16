"""Attribute Linux build inputs to installed distro packages, without guessing ABI versions."""
from __future__ import annotations

from pathlib import Path
import subprocess
import platform
import re
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
        info = subprocess.run(['dpkg-query', '-W',
                               '-f=${binary:Package}\t${Version}\t${source:Package}\t${source:Version}\n',
                               *sorted(set(by_path.values()))], text=True,
                              capture_output=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return {}
    records = {fields[0]: fields[1:] for line in info.stdout.splitlines()
               if len(fields := line.split('\t')) >= 2}
    try:
        release = platform.freedesktop_os_release()
    except OSError:
        release = {}
    result = {}
    for path, package in by_path.items():
        record = records.get(package)
        if not record or not record[0]:
            continue
        version = record[0]
        # Distro package versions include security backport revisions; they are
        # kept distinct from an upstream version inferred from a SONAME.
        entry = {'name': package, 'version': version, 'bom-ref': 'os-package:' + package}
        if len(record) >= 3 and record[1] and record[2]:
            entry['properties'] = [
                {'name': 'kk:source-package', 'value': record[1]},
                {'name': 'kk:source-version', 'value': record[2]}]
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


def distro_notices(packages, *, doc_root=Path('/usr/share/doc'),
                   common_root=Path('/usr/share/common-licenses')):
    """Retain shipped distro notices and referenced common license texts.

    Missing texts remain explicit review items; this does not infer a license
    expression or grant a legal clearance from a package name.
    """
    texts, missing, seen = [], [], set()
    for package in sorted(set(packages)):
        name = package.split(':', 1)[0]
        if not re.fullmatch(r'[a-z0-9][a-z0-9+.-]*', name):
            missing.append(package)
            continue
        path = Path(doc_root) / name / 'copyright'
        try:
            if path.stat().st_size > 2 * 1024**2:
                raise ValueError('notice_too_large')
            content = path.read_text(encoding='utf-8')
        except (OSError, ValueError):
            missing.append(package)
            continue
        texts.extend(['\n--- distro package: ' + package + ' ---', content])
        for reference in re.findall(r'/usr/share/common-licenses/([A-Za-z0-9+_.-]+)', content):
            reference = reference.rstrip('.')
            if reference in seen or reference in {'', '.', '..'}:
                continue
            seen.add(reference)
            try:
                path = Path(common_root) / reference
                if path.stat().st_size > 2 * 1024**2:
                    raise ValueError('license_too_large')
                license_text = path.read_text(encoding='utf-8')
            except (OSError, ValueError):
                missing.append('common-license:' + reference)
                continue
            texts.extend(['\n--- common license: ' + reference + ' ---', license_text])
    return texts, missing
