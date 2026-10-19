"""Check SBOM and network hosts against the BUILT package and fail closed.

PR144 Data Engine (Teamlead 19.10.2026, T07.06 / SBOM): reads the PYZ archive
of the built executable (PyInstaller ``CArchiveReader``/``ZlibArchiveReader``,
read-only, no network) and checks

* hosts: every URL host and quoted mail-server host in the packaged
  first-party modules, the JobSpy scrapers Karrierekrake uses and the ddgs
  engines first-party code selects by name must be in
  ``docs/privacy/NETWORK_TARGETS_PR144.json``;
* SBOM: for a top-level module whose files are installed by several
  distributions (urllib3 and urllib3-future), the release SBOM must list
  exactly the distribution whose RECORD matches the collected files, and the
  packaged version module must carry that distribution's version.

Usage: python scripts/ci_built_package_inventory_check.py --exe EXE --sbom SBOM --out OUT.json
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import marshal
import os
import re
import sys
import tempfile
import types
from collections import defaultdict
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTER = ROOT / 'docs/privacy/NETWORK_TARGETS_PR144.json'
URL_RE = re.compile(r"\b(?:https?|wss?)://([A-Za-z0-9][A-Za-z0-9.\-]*[A-Za-z0-9])(?::\d+)?")
MAIL_HOST_RE = re.compile(r"^((?:imap|smtp|pop3?)[a-z0-9\-]*\.[a-z0-9.\-]+\.[a-z]{2,}|outlook\.office365\.com)$")
# Third-party modules whose targets Karrierekrake triggers (as scripts/network_target_inventory.py).
JOBSPY_MODULES = ('jobspy.indeed', 'jobspy.linkedin', 'jobspy.util')
VERSION_MODULES = ('{top}._version', '{top}.__version__', '{top}.version', '{top}')


def _strings(code, consts: list[str], names: list[str]) -> None:
    names.extend(code.co_names)
    stack = list(code.co_consts)
    while stack:
        item = stack.pop()
        if isinstance(item, str):
            consts.append(item)
        elif isinstance(item, types.CodeType):
            _strings(item, consts, names)
        elif isinstance(item, (tuple, frozenset)):
            stack.extend(item)


def pyz_strings(exe: Path) -> dict[str, list[str]]:
    """``{module: string constants, module + '#names': co_names}`` of every PYZ module."""
    from PyInstaller.archive.readers import CArchiveReader, ZlibArchiveReader
    archive = CArchiveReader(str(exe))
    pyz = [name for name in archive.toc if name.endswith('.pyz')]
    if len(pyz) != 1:
        raise SystemExit(f'pyz_not_found in {exe}: {pyz!r}')
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, 'package.pyz')
        with open(path, 'wb') as handle:
            handle.write(archive.extract(pyz[0]))
        reader = ZlibArchiveReader(path)
        result: dict[str, list[str]] = {}
        for module in reader.toc:
            code = reader.extract(module)
            if isinstance(code, (bytes, bytearray)):
                code = marshal.loads(code)
            if not isinstance(code, types.CodeType):
                continue
            consts: list[str] = []
            names: list[str] = []
            _strings(code, consts, names)
            result[module] = consts
            result[module + '#names'] = names
    return result


def _top(module: str) -> str:
    return module.split('#')[0].split('.')[0]


def first_party_tops(strings: dict[str, list[str]], claimed: set[str] | None = None) -> set[str]:
    """Packaged top-level modules that are first-party code of this repository.

    A name that an installed distribution provides (e.g. ``packaging``, also a
    repository directory) is third-party in the package.
    """
    claimed = set(metadata.packages_distributions()) if claimed is None else claimed
    tops = {_top(m) for m in strings}
    return {t for t in tops if ((ROOT / t).is_dir() or (ROOT / f'{t}.py').is_file()) and t not in claimed}


def ddgs_backends_from_source() -> set[str]:
    """ddgs engines selected by a ``backend="…"`` literal in first-party source.

    The backend is a keyword literal, not recoverable from the PYZ strings; the
    engine module itself is then scanned in the built package.
    """
    sys.path.insert(0, str(ROOT))
    try:
        from scripts import network_target_inventory as inventory
    finally:
        sys.path.remove(str(ROOT))
    policy = inventory._policy()
    backends: set[str] = set()
    for prefix in policy.ALLOWED_FIRST_PARTY_PREFIXES:
        base = ROOT / prefix
        for path in sorted(base.rglob('*.py')) if base.is_dir() else []:
            backends |= inventory._ddgs_backends(path)
    return backends


def package_hosts(strings: dict[str, list[str]], *, first_party: set[str],
                  ddgs_backends: set[str] = frozenset()) -> dict[str, set[str]]:
    hosts: dict[str, set[str]] = defaultdict(set)
    scanned = [m for m in strings if '#' not in m and _top(m) in first_party]
    engines = {f'ddgs.engines.{b}' for b in ddgs_backends}
    for engine in sorted(engines - set(strings)):
        hosts[f'ddgs-backend-not-packaged:{engine.rsplit(".", 1)[1]}'].add('ddgs')
    scanned += [m for m in strings if '#' not in m and (m in engines or any(
        m == j or m.startswith(j + '.') for j in JOBSPY_MODULES))]
    for module in scanned:
        for text in strings[module]:
            for match in URL_RE.finditer(text):
                hosts[match.group(1).lower().rstrip('.')].add(module)
            mail = MAIL_HOST_RE.match(text.strip().lower())
            if mail:
                hosts[mail.group(1)].add(module)
    return hosts


def host_problems(strings, register: dict, *, first_party: set[str],
                  ddgs_backends: set[str] = frozenset()) -> list[str]:
    known = set(register.get('hosts', {}))
    hosts = package_hosts(strings, first_party=first_party, ddgs_backends=ddgs_backends)
    return [f'host_not_in_register {host} ({", ".join(sorted(mods))})'
            for host, mods in sorted(hosts.items()) if host not in known]


def _record_ok(dist, file) -> bool | None:
    if file.hash is None or file.hash.mode != 'sha256':
        return None
    path = Path(dist.locate_file(file))
    if not path.is_file():
        return None
    actual = base64.urlsafe_b64encode(hashlib.sha256(path.read_bytes()).digest()).rstrip(b'=').decode()
    return actual == file.hash.value


def _norm(name: str) -> str:
    return re.sub(r'[-_.]+', '-', name).casefold()


def sbom_problems(strings, sbom: dict, installed) -> list[str]:
    """SBOM owner of every packaged top-level module installed by several distributions."""
    listed = {(_norm(c['name']), c.get('version')) for c in sbom.get('components', [])
              if c.get('type') == 'library'}
    shared: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for dist in installed:
        for file in dist.files or ():
            parts = Path(str(file)).parts
            if len(parts) > 1 and parts[-1].endswith('.py') and not parts[0].endswith(('.dist-info', '.data')):
                shared[parts[0]][str(file)].append(dist)
    packaged = {_top(m) for m in strings}
    problems: list[str] = []
    for top, files in sorted(shared.items()):
        overlap = {f: ds for f, ds in files.items() if len(ds) > 1}
        if top not in packaged or not overlap:
            continue
        claimants = {id(d): d for ds in overlap.values() for d in ds}.values()
        owners, others = [], []
        for dist in claimants:
            results = [_record_ok(dist, f) for f in dist.files or () if str(f) in overlap]
            (owners if True in results and False not in results else others).append(dist)
        if not others:
            continue  # identical shared files (namespace/split packages): nothing overwritten
        if not owners:
            problems.append(f'module_owner_ambiguous {top}: '
                            + ', '.join(sorted(f"{d.metadata['Name']} {d.version}" for d in claimants)))
            continue
        for owner in owners:
            if (_norm(owner.metadata['Name']), owner.version) not in listed:
                problems.append(f"sbom_missing_collected_distribution {owner.metadata['Name']} {owner.version} ({top})")
        owned = {(_norm(d.metadata['Name']), d.version) for d in owners}
        for dist in others:
            key = (_norm(dist.metadata['Name']), dist.version)
            if key in listed and key not in owned:
                problems.append(f"sbom_lists_overwritten_distribution {dist.metadata['Name']} {dist.version} ({top})")
        version_strings = [s for pattern in VERSION_MODULES for s in strings.get(pattern.format(top=top), ())
                           if re.fullmatch(r'\d+(?:\.\d+)+\S*', s)]
        owner = owners[0]
        if len(owned) == 1 and version_strings and owner.version not in version_strings:
            problems.append(f'package_version_mismatch {top}: packaged {sorted(set(version_strings))} '
                            f'!= {owner.metadata["Name"]} {owner.version}')
    return problems


def run(exe: Path, sbom_path: Path, out: Path, *, installed=None, first_party: set[str] | None = None,
        ddgs_backends: set[str] | None = None) -> dict:
    strings = pyz_strings(exe)
    if not strings:
        raise SystemExit(f'pyz_empty in {exe}')
    register = json.loads(REGISTER.read_text(encoding='utf-8'))
    sbom = json.loads(Path(sbom_path).read_text(encoding='utf-8'))
    tops = first_party_tops(strings) if first_party is None else first_party
    installed = list(metadata.distributions()) if installed is None else installed
    backends = ddgs_backends_from_source() if ddgs_backends is None else ddgs_backends
    hosts = package_hosts(strings, first_party=tops, ddgs_backends=backends)
    problems = (host_problems(strings, register, first_party=tops, ddgs_backends=backends)
                + sbom_problems(strings, sbom, installed))
    payload = {'ok': not problems, 'problems': problems, 'pyz_modules': sum('#' not in m for m in strings),
               'first_party_tops': sorted(tops), 'hosts': {h: sorted(m) for h, m in sorted(hosts.items())},
               '_platform': sys.platform}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps({k: payload[k] for k in ('ok', 'problems', 'pyz_modules', 'first_party_tops')}, indent=2))
    if problems:
        raise SystemExit('built package inventory check failed: ' + '; '.join(problems))
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--exe', type=Path, required=True)
    parser.add_argument('--sbom', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    run(args.exe, args.sbom, args.out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
