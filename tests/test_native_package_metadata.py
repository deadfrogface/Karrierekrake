from types import SimpleNamespace
from scripts import native_package_metadata as native


def test_preserves_package_security_revision_and_binary_attribution(tmp_path, monkeypatch):
    source = tmp_path / 'libcrypto.so.3'
    source.touch()
    calls = []
    monkeypatch.setattr(native.platform, 'freedesktop_os_release', lambda: {'ID':'ubuntu','VERSION_ID':'22.04'})
    monkeypatch.setattr(native.sys, 'platform', 'linux')
    def run(command, **kwargs):
        calls.append(command)
        if command[1] == '-S':
            return SimpleNamespace(stdout=f'libssl3:amd64: {source}\n', returncode=0)
        return SimpleNamespace(stdout='libssl3:amd64\t3.0.2-0ubuntu1.20\n', returncode=0)
    monkeypatch.setattr(native.subprocess, 'run', run)
    package = native.linux_packages([source])[str(source.resolve())]
    assert package['name'] == 'libssl3:amd64'
    assert package['version'] == '3.0.2-0ubuntu1.20'
    assert package['purl'] == 'pkg:deb/ubuntu/libssl3@3.0.2-0ubuntu1.20?arch=amd64&distro=ubuntu-22.04'
    assert len(calls) == 2


def test_missing_package_tool_leaves_unknown_explicit(tmp_path, monkeypatch):
    monkeypatch.setattr(native.sys, 'platform', 'linux')
    def absent(*args, **kwargs):
        raise FileNotFoundError('dpkg-query')
    monkeypatch.setattr(native.subprocess, 'run', absent)
    assert native.linux_packages([tmp_path / 'unowned.so']) == {}


def test_non_linux_does_not_run_dpkg(monkeypatch):
    monkeypatch.setattr(native.sys, 'platform', 'darwin')
    monkeypatch.setattr(native.subprocess, 'run', lambda *a, **k: (_ for _ in ()).throw(AssertionError()))
    assert native.linux_packages(['/lib/test.so']) == {}


def test_source_package_identity_is_not_confused_with_binary_name(tmp_path, monkeypatch):
    source = tmp_path / 'libcrypto.so.3'
    source.touch()
    monkeypatch.setattr(native.sys, 'platform', 'linux')
    def run(command, **kwargs):
        if command[1] == '-S':
            return SimpleNamespace(stdout=f'libssl3:amd64: {source}\n', returncode=0)
        assert '${source:Package}' in command[2]
        return SimpleNamespace(stdout='libssl3:amd64\t3.0.2-0ubuntu1.20\topenssl\t3.0.2-0ubuntu1.20\n', returncode=0)
    monkeypatch.setattr(native.subprocess, 'run', run)
    package = native.linux_packages([source])[str(source.resolve())]
    assert package['name'] == 'libssl3:amd64'
    assert {'name': 'kk:source-package', 'value': 'openssl'} in package['properties']
    assert {'name': 'kk:source-version', 'value': '3.0.2-0ubuntu1.20'} in package['properties']


def test_distro_copyright_and_referenced_license_are_retained(tmp_path):
    docs, common = tmp_path / 'doc', tmp_path / 'licenses'
    (docs / 'example-lib').mkdir(parents=True)
    common.mkdir()
    (docs / 'example-lib/copyright').write_text(
        'Copyright Example. See /usr/share/common-licenses/GPL-3.\n')
    (common / 'GPL-3').write_text('Synthetic complete license fixture')
    texts, missing = native.distro_notices(['example-lib:amd64', 'example-lib:amd64'],
                                          doc_root=docs, common_root=common)
    assert not missing
    assert sum('Copyright Example' in text for text in texts) == 1
    assert 'Synthetic complete license fixture' in texts


def test_missing_notices_are_explicit_and_paths_are_not_traversed(tmp_path):
    texts, missing = native.distro_notices(['absent', '../outside'], doc_root=tmp_path)
    assert not texts
    assert missing == ['../outside', 'absent']
