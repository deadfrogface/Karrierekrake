"""Windows policy failures must not load optional DLLs during app startup."""
import builtins
import ctypes
from types import SimpleNamespace
import sys

import pytest

from core.cv_llm_runtime import llama_cpp_installed
from core.native_library_loading import quiet_native_loader
from core.native_library_loading import is_integrity_policy_error
from guenther.provider import ProviderStatus
from guenther.runtime.llama_cpp_provider import LlamaCppProvider


def test_startup_provider_probe_never_imports_native_module(monkeypatch):
    real_import = builtins.__import__
    def guarded_import(name, *args, **kwargs):
        if name == "llama_cpp":
            pytest.fail("startup attempted to load blocked native DLLs")
        return real_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", guarded_import)
    monkeypatch.setattr("importlib.util.find_spec", lambda name: SimpleNamespace(name=name))
    assert llama_cpp_installed()
    assert LlamaCppProvider().status() == ProviderStatus.MODEL_MISSING


def test_windows_error_mode_restores_and_load_error_still_propagates(monkeypatch):
    calls = []
    def set_mode(value, previous):
        calls.append(value)
        if previous is not None:
            previous._obj.value = 4
        return True
    kernel = SimpleNamespace(GetThreadErrorMode=lambda: 4, SetThreadErrorMode=set_mode)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(ctypes, "WinDLL", lambda *a, **k: kernel, raising=False)
    with pytest.raises(OSError, match="blocked"):
        with quiet_native_loader():
            raise OSError("blocked")
    assert calls == [4 | 0x0001 | 0x8000, 4]


def test_wrapped_policy_rejection_is_distinct_from_missing_library():
    failure = OSError("blocked image")
    failure.winerror = 577
    wrapped = RuntimeError("optional library failed to load")
    wrapped.__cause__ = failure
    assert is_integrity_policy_error(wrapped)
    assert is_integrity_policy_error(OSError("status 0xC0E90002"))
    assert not is_integrity_policy_error(ModuleNotFoundError("llama_cpp"))


def test_policy_rejection_returns_readable_cv_failure(monkeypatch, tmp_path):
    from core import cv_llm_runtime as runtime
    from core.cv_docpick_import import CvImportError
    from desktop.cv_import_child import user_message_for_kind
    real_import = builtins.__import__
    def blocked_import(name, *args, **kwargs):
        if name == "llama_cpp":
            error = OSError("blocked image")
            error.winerror = 577
            raise error
        return real_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", blocked_import)
    monkeypatch.setattr(runtime, "http_llm_available", lambda: False)
    monkeypatch.setattr(runtime, "resolve_cv_model_path", lambda: tmp_path / "model.gguf")
    with pytest.raises(CvImportError) as error:
        runtime.ensure_cv_llm_ready()
    assert error.value.code == "local_ai_blocked"
    assert "Windows blockiert" in user_message_for_kind(error.value.code, "")
    monkeypatch.setattr(runtime, "_llama_policy_blocked", False)
