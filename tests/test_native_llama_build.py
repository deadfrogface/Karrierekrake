"""Regression for Apple's forced upstream settings and architecture checks."""
import shutil
import subprocess

import pytest

from core.cv_llm_runtime import format_llama_build_report, llama_build_report_valid
from scripts.build_native_llama import patch_apple_defaults


@pytest.mark.parametrize('machine,features,valid', [
    ('AMD64', 'CPU : AVX2 = 1 |', True),
    ('x86_64', 'CPU : SSE3 = 1 |', False),
    ('arm64', 'CPU : NEON = 1 | ARM_FMA = 1 |', True),
    ('aarch64', 'CPU : NEON = 1 |', True),
    ('arm64', 'CPU : AVX2 = 1 |', False),
    ('x86_64', 'CPU : AVX2 = 1 | AVX512 = 1 |', False),
    ('AMD64', 'CPU : AVX2 = 1 | AMX_INT8 = 1 |', False),
    ('unknown', 'CPU : AVX2 = 1 |', False),
])
def test_report_accepts_only_portable_kernels_for_architecture(machine, features, valid):
    text = format_llama_build_report(features, ['libggml-cpu.dylib'])
    assert llama_build_report_valid(text, machine=machine) is valid
    dynamic = format_llama_build_report(features, ['ggml-cpu-haswell.dll'])
    assert not llama_build_report_valid(dynamic, machine=machine)


def apple_forced_defaults():
    lines = [f'set({flag} "OFF" CACHE BOOL "ggml: enable {name}" FORCE)'
             for flag, name in [('GGML_AVX', 'AVX'), ('GGML_AVX2', 'AVX2'),
                                ('GGML_FMA', 'FMA'), ('GGML_F16C', 'F16C')]]
    return '\n'.join(lines + ['set(GGML_METAL "ON" CACHE BOOL "ggml: enable Metal" FORCE)'])


def test_patch_rejects_changed_upstream_source():
    with pytest.raises(ValueError, match='source_patch_mismatch'):
        patch_apple_defaults(apple_forced_defaults().replace('GGML_AVX2', 'CHANGED'))


@pytest.mark.skipif(not shutil.which('cmake'), reason='CMake needed for actual cache override test')
def test_actual_cmake_options_survive_apple_defaults(tmp_path):
    # Reproduce the upstream FORCE behavior in a real CMake configure.
    source = tmp_path / 'source'
    source.mkdir()
    defaults = apple_forced_defaults()
    header = 'cmake_minimum_required(VERSION 3.21)\nproject(apple_defaults NONE)\n'
    cmake = source / 'CMakeLists.txt'
    cmake.write_text(header + defaults)
    flags = ['-DGGML_AVX=ON', '-DGGML_AVX2=ON', '-DGGML_FMA=ON',
             '-DGGML_F16C=ON', '-DGGML_METAL=OFF']
    before = tmp_path / 'before'
    subprocess.run(['cmake', '-S', str(source), '-B', str(before), *flags], check=True,
                   capture_output=True)
    old_cache = (before / 'CMakeCache.txt').read_text()
    assert 'GGML_AVX2:BOOL=OFF' in old_cache
    assert 'GGML_METAL:BOOL=ON' in old_cache
    cmake.write_text(header + patch_apple_defaults(defaults))
    after = tmp_path / 'after'
    subprocess.run(['cmake', '-S', str(source), '-B', str(after), *flags], check=True,
                   capture_output=True)
    cache = (after / 'CMakeCache.txt').read_text()
    for flag in flags:
        name, value = flag[2:].split('=')
        assert f'{name}:BOOL={value}' in cache
