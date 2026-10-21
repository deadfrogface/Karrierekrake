"""CI gate: SBOM and network hosts checked against the BUILT package (Teamlead 19.10.2026).

``scripts/ci_built_package_inventory_check.py`` reads the PYZ of the built
executable. Every first-party host must be in
``docs/privacy/NETWORK_TARGETS_PR144.json``, and for a module whose files are
installed by several distributions (urllib3 / urllib3-future) the SBOM must
list exactly the distribution whose code is in the package.
"""
import base64
import hashlib
import json
from importlib import metadata
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _record_hash(data: bytes) -> str:
    return 'sha256=' + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b'=').decode()


def _dist(site, name, version, files):
    info = site / f"{name.replace('-', '_')}-{version}.dist-info"
    info.mkdir(parents=True)
    (info / 'METADATA').write_text(f'Metadata-Version: 2.4\nName: {name}\nVersion: {version}\n', encoding='utf-8')
    rows = [f'{path},{_record_hash(data)},{len(data)}' for path, data in files.items()]
    (info / 'RECORD').write_text('\n'.join(rows) + '\n', encoding='utf-8')
    return metadata.PathDistribution(info)


def _overwritten_urllib3(tmp_path):
    site = tmp_path / 'site'
    (site / 'urllib3').mkdir(parents=True)
    (site / 'urllib3' / '_version.py').write_bytes(b'__version__ = "2.25.901"\n')
    classic = _dist(site, 'urllib3', '2.8.0', {'urllib3/_version.py': b'__version__ = "2.8.0"\n'})
    future = _dist(site, 'urllib3-future', '2.25.901', {'urllib3/_version.py': b'__version__ = "2.25.901"\n'})
    return [classic, future]


def _sbom(*libraries):
    return {'components': [{'type': 'library', 'name': n, 'version': v} for n, v in libraries]}


_PYZ = {'urllib3': ['annotations'], 'urllib3._version': ['annotations', '2.25.901']}


def test_sbom_listing_overwritten_distribution_is_rejected(tmp_path):
    from scripts.ci_built_package_inventory_check import sbom_problems
    problems = sbom_problems(_PYZ, _sbom(('urllib3', '2.8.0'), ('urllib3-future', '2.25.901')),
                             _overwritten_urllib3(tmp_path))
    assert any(p.startswith('sbom_lists_overwritten_distribution urllib3 2.8.0') for p in problems), problems


def test_sbom_missing_collected_distribution_is_rejected(tmp_path):
    from scripts.ci_built_package_inventory_check import sbom_problems
    problems = sbom_problems(_PYZ, _sbom(('urllib3', '2.8.0')), _overwritten_urllib3(tmp_path))
    assert any(p.startswith('sbom_missing_collected_distribution urllib3-future 2.25.901') for p in problems)


def test_sbom_with_collected_owner_only_passes(tmp_path):
    from scripts.ci_built_package_inventory_check import sbom_problems
    assert sbom_problems(_PYZ, _sbom(('urllib3-future', '2.25.901')), _overwritten_urllib3(tmp_path)) == []


def test_packaged_version_must_match_listed_owner(tmp_path):
    from scripts.ci_built_package_inventory_check import sbom_problems
    pyz = {'urllib3': [], 'urllib3._version': ['2.8.0']}
    problems = sbom_problems(pyz, _sbom(('urllib3-future', '2.25.901')), _overwritten_urllib3(tmp_path))
    assert any(p.startswith('package_version_mismatch urllib3') for p in problems), problems


def test_shared_module_not_in_package_is_not_checked(tmp_path):
    from scripts.ci_built_package_inventory_check import sbom_problems
    assert sbom_problems({'jobspy': []}, _sbom(('urllib3', '2.8.0')), _overwritten_urllib3(tmp_path)) == []


_REGISTER = {'hosts': {'rest.arbeitsagentur.de': {}, 'apis.indeed.com': {}, 'search.brave.com': {}}}


def test_unregistered_first_party_host_is_rejected():
    from scripts.ci_built_package_inventory_check import host_problems
    pyz = {'search.bundesagentur': ['https://rest.arbeitsagentur.de/jobboerse', 'https://new-tracker.example.com/x']}
    problems = host_problems(pyz, _REGISTER, first_party={'search'})
    assert problems == ['host_not_in_register new-tracker.example.com (search.bundesagentur)']


def test_first_party_clients_and_selected_ddgs_engine_hosts_are_scanned():
    from scripts.ci_built_package_inventory_check import host_problems, package_hosts
    pyz = {
        'search.company_web': ['duckduckgo', 'brave'],
        'ddgs.engines.brave': ['https://search.brave.com/search'],
        'ddgs.engines.duckduckgo': ['https://duckduckgo.com/y.js?'],
        'ddgs.engines.yandex': ['https://yandex.com/search'],
        'search.indeed_api': ['https://apis.indeed.com/graphql'],
        'jobspy.glassdoor': ['https://www.glassdoor.com/'],
    }
    hosts = package_hosts(pyz, first_party={'search'}, ddgs_backends={'brave'})
    assert set(hosts) == {'search.brave.com', 'apis.indeed.com'}
    assert host_problems(pyz, _REGISTER, first_party={'search'}, ddgs_backends={'brave'}) == []
    missing = host_problems(pyz, _REGISTER, first_party={'search'}, ddgs_backends={'mojeek'})
    assert missing == ['host_not_in_register ddgs-backend-not-packaged:mojeek (ddgs)']


def test_backend_literal_is_read_from_first_party_source():
    from scripts.ci_built_package_inventory_check import ddgs_backends_from_source
    assert 'brave' in ddgs_backends_from_source()


def test_repository_directory_provided_by_a_distribution_is_third_party():
    from scripts.ci_built_package_inventory_check import first_party_tops
    pyz = {'packaging.tags': [], 'search.x': [], 'core.y': []}
    assert first_party_tops(pyz, claimed={'packaging'}) == {'search', 'core'}


def test_identical_shared_files_are_not_an_ownership_conflict(tmp_path):
    from scripts.ci_built_package_inventory_check import sbom_problems
    site = tmp_path / 'site'
    (site / 'PySide6').mkdir(parents=True)
    (site / 'PySide6' / '__init__.py').write_bytes(b'# shared\n')
    a = _dist(site, 'PySide6', '6.11.2', {'PySide6/__init__.py': b'# shared\n'})
    b = _dist(site, 'PySide6-Addons', '6.11.2', {'PySide6/__init__.py': b'# shared\n'})
    assert sbom_problems({'PySide6': []}, _sbom(('PySide6', '6.11.2')), [a, b]) == []


def test_mail_host_constant_must_be_registered():
    from scripts.ci_built_package_inventory_check import host_problems
    pyz = {'integrations.provider_verified_settings': ['imap.mailbox.example.org']}
    assert host_problems(pyz, _REGISTER, first_party={'integrations'}) == [
        'host_not_in_register imap.mailbox.example.org (integrations.provider_verified_settings)']


def test_run_writes_result_and_fails_closed(monkeypatch, tmp_path):
    from scripts import ci_built_package_inventory_check as ci
    monkeypatch.setattr(ci, 'pyz_strings', lambda exe: {'search.x': ['https://unknown.example.net/']})
    sbom = tmp_path / 'release-sbom.json'
    sbom.write_text(json.dumps(_sbom()), encoding='utf-8')
    out = tmp_path / 'package-inventory.json'
    with pytest.raises(SystemExit, match='host_not_in_register unknown.example.net'):
        ci.run(tmp_path / 'Karrierekrake', sbom, out, installed=[], first_party={'search'}, ddgs_backends=set())
    recorded = json.loads(out.read_text(encoding='utf-8'))
    assert recorded['ok'] is False and recorded['problems']


def test_run_reads_no_empty_package(monkeypatch, tmp_path):
    from scripts import ci_built_package_inventory_check as ci
    monkeypatch.setattr(ci, 'pyz_strings', lambda exe: {})
    sbom = tmp_path / 'release-sbom.json'
    sbom.write_text(json.dumps(_sbom()), encoding='utf-8')
    with pytest.raises(SystemExit, match='pyz_empty'):
        ci.run(tmp_path / 'Karrierekrake', sbom, tmp_path / 'o.json', installed=[], ddgs_backends=set())


def test_check_runs_against_the_built_package_in_every_native_workflow():
    platforms = (ROOT / '.github/workflows/desktop-platforms.yml').read_text(encoding='utf-8')
    windows = (ROOT / '.github/workflows/windows-smoke.yml').read_text(encoding='utf-8')
    assert ('scripts/ci_built_package_inventory_check.py --exe ${{ matrix.exe }} '
            '--sbom build/release-compliance/release-sbom.json') in platforms
    assert ('scripts/ci_built_package_inventory_check.py --exe dist/Karrierekrake.exe '
            '--sbom build/release-compliance/release-sbom.json') in windows
