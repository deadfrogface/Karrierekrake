"""Enforce the actual desktop attack surface, including collect_all data paths."""
from pathlib import Path
import sys

import pytest
from core.security.llama_surface import verify_llama_surface
import importlib.util
spec = importlib.util.spec_from_file_location('kk_surface_policy',
    Path(__file__).resolve().parents[1] / 'packaging/kk_content_policy.py')
policy = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = policy
spec.loader.exec_module(policy)
filter_collect_all_datas = policy.filter_collect_all_datas
path_has_forbidden_marker = policy.path_has_forbidden_marker


def test_actual_cpu_backend_does_not_support_rpc():
    assert verify_llama_surface() == {'rpc': False, 'desktop_c_api': True}


def test_rpc_capable_replacement_is_rejected(monkeypatch):
    from llama_cpp import llama_cpp as api
    monkeypatch.setattr(api, 'llama_supports_rpc', lambda: True)
    with pytest.raises(RuntimeError, match='rpc_backend_present'):
        verify_llama_surface()


@pytest.mark.parametrize('relative', ['llama_cpp/server/app.py', 'llama_cpp/server/__main__.py',
                                      'PYZ-00.pyz/llama_cpp.server', 'llama_cpp/server'])
def test_retired_server_payload_cannot_bypass_analysis_as_data(relative):
    assert path_has_forbidden_marker(relative)
    assert not filter_collect_all_datas([('/site-packages/'+relative, relative)])
    assert filter_collect_all_datas([('/site-packages/llama_cpp/llama.py', 'llama_cpp')])


@pytest.mark.parametrize('relative', ['llama_cpp/server/app.py', 'llama_cpp/lib/rpc-server', 'llama-server.exe'])
def test_frozen_gate_rejects_present_server_files(tmp_path, monkeypatch, relative):
    from importlib import util
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, '_MEIPASS', str(tmp_path), raising=False)
    monkeypatch.setattr(util, 'find_spec', lambda _: None)
    path = tmp_path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'synthetic server payload')
    with pytest.raises(RuntimeError, match='server_payload_present'):
        verify_llama_surface()
