import hashlib
from pathlib import Path
from types import SimpleNamespace

from scripts.distribution_license import distribution_license


def test_exact_mit_classifier_is_declared_but_generic_bsd_is_not_guessed():
    dist = SimpleNamespace(metadata={'Name': 'example', 'Classifier': ['License :: OSI Approved :: MIT License']}, version='1', files=[])
    assert distribution_license(dist, evidence=[])[0] == [{'expression': 'MIT'}]
    dist.metadata['Classifier'] = ['License :: OSI Approved :: BSD License']
    assert distribution_license(dist, evidence=[]) == (None, [])


def test_conflicting_classifiers_do_not_invent_or_and_semantics():
    dist = SimpleNamespace(metadata={'Name': 'example', 'Classifier': ['License :: OSI Approved :: MIT License', 'License :: OSI Approved :: BSD License']}, version='1', files=[])
    assert distribution_license(dist, evidence=[]) == (None, [])


def test_pinned_license_requires_exact_version_and_file_digest(tmp_path):
    file = tmp_path / 'LICENSE'
    file.write_bytes(b'synthetic reviewed license fixture')
    dist = SimpleNamespace(metadata={'Name': 'Example_Package'}, version='1.0', files=[Path('LICENSE')], locate_file=lambda _: file)
    evidence = [{'name': 'example-package', 'version': '1.0', 'filename': 'LICENSE',
                 'sha256': hashlib.sha256(file.read_bytes()).hexdigest(), 'expression': 'MIT',
                 'source_url': 'https://example.invalid/license'}]
    licenses, properties = distribution_license(dist, evidence=evidence)
    assert licenses == [{'expression': 'MIT'}]
    assert {'name': 'kk:license-file-sha256', 'value': evidence[0]['sha256']} in properties
    dist.version = '1.1'
    assert distribution_license(dist, evidence=evidence) == (None, [])
    dist.version = '1.0'
    file.write_bytes(b'changed rights text')
    assert distribution_license(dist, evidence=evidence) == (None, [])


def test_pinned_license_accepts_a_recorded_platform_digest_only(tmp_path):
    """Windows wheels of some packages ship the same LICENSE text with CRLF
    (other bytes, other sha256). Only an exact digest recorded per platform in
    the evidence counts; no normalisation, any other byte change still fails."""
    text = b'synthetic reviewed license fixture\nsecond line\n'
    file = tmp_path / 'LICENSE'
    file.write_bytes(text.replace(b'\n', b'\r\n'))
    dist = SimpleNamespace(metadata={'Name': 'Example_Package'}, version='1.0', files=[Path('LICENSE')], locate_file=lambda _: file)
    windows = hashlib.sha256(file.read_bytes()).hexdigest()
    evidence = [{'name': 'example-package', 'version': '1.0', 'filename': 'LICENSE',
                 'sha256': hashlib.sha256(text).hexdigest(), 'expression': 'MIT',
                 'source_url': 'https://example.invalid/license'}]
    assert distribution_license(dist, evidence=evidence) == (None, [])
    evidence[0]['platform_sha256'] = {'win_amd64': windows}
    licenses, properties = distribution_license(dist, evidence=evidence)
    assert licenses == [{'expression': 'MIT'}]
    assert {'name': 'kk:license-file-sha256', 'value': windows} in properties
    file.write_bytes(text.replace(b'\n', b'\r\n') + b' ')
    assert distribution_license(dist, evidence=evidence) == (None, [])
