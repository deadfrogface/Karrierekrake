"""Keep compiler/ABI changes distinct while reusing identical native inputs."""
from types import SimpleNamespace

import pytest
from scripts import native_build_cache_key as cache


@pytest.fixture
def root(tmp_path):
    (tmp_path / 'scripts').mkdir()
    for name in ('scripts/build_native_llama.py', 'scripts/native_build_cache_key.py', 'constraints-runtime.txt'):
        (tmp_path / name).write_text('synthetic initial input')
    return tmp_path


def test_unrelated_workflow_edit_keeps_same_key(root):
    key = cache.build_key('linux-x86_64', {'cc': 'gcc 12'}, root=root, environment={})
    (root / 'workflow.yml').write_text('different test selection')
    assert cache.build_key('linux-x86_64', {'cc': 'gcc 12'}, root=root, environment={}) == key


@pytest.mark.parametrize('changed', ['compiler', 'target', 'flags', 'source', 'constraints', 'python'])
def test_native_input_change_invalidates_key(root, changed):
    identity, environment, target = {'cc': 'gcc 12', 'python': '3.12.1'}, {}, 'linux-x86_64'
    before = cache.build_key(target, identity, root=root, environment=environment)
    if changed == 'compiler':
        identity['cc'] = 'gcc 13'
    elif changed == 'python':
        identity['python'] = '3.12.2'
    elif changed == 'target':
        target = 'macos-arm64'
    elif changed == 'flags':
        environment['CMAKE_ARGS'] = '-DGGML_NATIVE=OFF'
    else:
        path = 'scripts/build_native_llama.py' if changed == 'source' else 'constraints-runtime.txt'
        (root / path).write_text('changed native input')
    assert cache.build_key(target, identity, root=root, environment=environment) != before


def test_compiler_override_and_version_are_recorded(monkeypatch):
    monkeypatch.setenv('CC', 'ccache clang')
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(stdout='clang 19\n')
    monkeypatch.setattr(cache.subprocess, 'run', run)
    assert cache.compiler_identity('CC', 'cc')['version'] == 'clang 19'
    assert calls == [['ccache', 'clang', '--version']]


def test_host_target_mismatch_fails_before_cache_reuse(monkeypatch):
    monkeypatch.setattr(cache.sys, 'platform', 'linux')
    monkeypatch.setattr(cache.platform, 'machine', lambda: 'x86_64')
    with pytest.raises(ValueError, match='target_host_mismatch'):
        cache.host_identity('macos-arm64')
