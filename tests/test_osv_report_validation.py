"""Malformed scanner reports never create a false security pass."""
import json
from types import SimpleNamespace

import pytest
from scripts import run_security_scans as scans


def report(vulnerabilities=()):
    return {'results': [{'packages': [{'package': {'name': 'synthetic', 'version': '1.0'},
                                      'vulnerabilities': list(vulnerabilities)}]}]}


def execute(tmp_path, monkeypatch, payload, code):
    monkeypatch.setattr(scans, 'ROOT', tmp_path)
    monkeypatch.setattr(scans.shutil, 'which', lambda _: '/scanner')
    def freeze(path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('synthetic==1.0\n')
        return path
    monkeypatch.setattr(scans, '_write_runtime_freeze', freeze)
    def run(command, **kwargs):
        if '--output-file' in command:
            (tmp_path / 'artifacts/osv-scanner.json').write_text(json.dumps(payload))
        return SimpleNamespace(returncode=code)
    monkeypatch.setattr(scans, '_run', run)
    return scans.run_osv()


@pytest.mark.parametrize('payload', [
    {'results': []}, {'results': [{}]}, {'results': [{'packages': {}}]},
    {'results': [{'packages': [None]}]},
    {'results': [{'packages': [{'package': {'name': 'x'}}]}]},
    report([{'id': 'TEST', 'severity': ['bad']}]),
    report([{'id': 'TEST', 'aliases': 'bad'}]),
    report([{'id': 'TEST', 'database_specific': []}]),
    report([{'severity': []}]),
])
def test_incomplete_nested_report_blocks(tmp_path, monkeypatch, payload):
    assert execute(tmp_path, monkeypatch, payload, 0) == 1


def test_exit_one_without_findings_blocks(tmp_path, monkeypatch):
    assert execute(tmp_path, monkeypatch, report(), 1) == 1


def test_valid_clean_report_passes(tmp_path, monkeypatch):
    assert execute(tmp_path, monkeypatch, report(), 0) == 0


def test_valid_low_findings_remain_visible_and_nonblocking(tmp_path, monkeypatch, capsys):
    low = {'id': 'SYNTHETIC-LOW', 'database_specific': {'severity': 'LOW'}}
    assert execute(tmp_path, monkeypatch, report([low]), 1) == 0
    assert 'SYNTHETIC-LOW' in capsys.readouterr().out


def test_unknown_severity_stays_blocking(tmp_path, monkeypatch):
    assert execute(tmp_path, monkeypatch, report([{'id': 'SYNTHETIC-UNKNOWN'}]), 1) == 1
