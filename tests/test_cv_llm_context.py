"""In-process CV LLM: fit check before generation, truncation, thread policy."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.cv_docpick_import import CvImportError
from core.cv_llm_runtime import (
    CV_LLM_CTX_SLACK_TOKENS,
    CV_LLM_MIN_COMPLETION_TOKENS,
    chat_completion_inprocess,
    completion_token_budget,
    logical_cpu_count,
    physical_cpu_count,
    resolve_cv_llm_n_ctx,
    resolve_cv_llm_threads,
)


class _FakeLlama:
    instances: list["_FakeLlama"] = []

    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs
        self.generate_calls = 0
        self.prompt_tokens = 100
        self.finish_reason = "stop"
        self.content = '{"name":{"first_name":"A","last_name":"B"}}'
        _FakeLlama.instances.append(self)

    def count_chat_tokens(self, messages):
        assert messages
        return self.prompt_tokens

    def create_chat_completion(self, **kwargs):
        self.generate_calls += 1
        self.completion_kwargs = kwargs
        assert kwargs.get("stream") is True
        content = self.content
        finish = self.finish_reason

        def chunks():
            yield {
                "choices": [
                    {"delta": {"content": content}, "finish_reason": None}
                ]
            }
            yield {"choices": [{"delta": {}, "finish_reason": finish}]}

        return chunks()


@pytest.fixture
def fake_llama(monkeypatch: pytest.MonkeyPatch):
    _FakeLlama.instances.clear()

    def factory():
        return _FakeLlama

    monkeypatch.setattr("core.cv_llm_runtime._llama_cls", factory)
    return _FakeLlama


def test_overlong_prompt_does_not_generate(fake_llama, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KARRIEREKRAKE_CV_LLM_N_CTX", "4096")
    created: list[_FakeLlama] = []
    # Remainder would be 4096 - 4000 - slack, below the minimum.
    class Counting(_FakeLlama):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.prompt_tokens = 4000
            created.append(self)

    monkeypatch.setattr("core.cv_llm_runtime._llama_cls", lambda: Counting)
    with pytest.raises(CvImportError) as ei:
        chat_completion_inprocess(
            [{"role": "user", "content": "x"}],
            model_path=Path("unused.gguf"),
        )
    assert ei.value.code == "llm_prompt_too_long"
    assert len(created) == 1
    assert created[0].generate_calls == 0


def test_remainder_equal_to_minimum_generates_once(fake_llama, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KARRIEREKRAKE_CV_LLM_N_CTX", "4096")
    n_prompt = 4096 - CV_LLM_CTX_SLACK_TOKENS - CV_LLM_MIN_COMPLETION_TOKENS

    class Fits(_FakeLlama):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.prompt_tokens = n_prompt

    monkeypatch.setattr("core.cv_llm_runtime._llama_cls", lambda: Fits)
    text = chat_completion_inprocess(
        [{"role": "user", "content": "x"}],
        model_path=Path("unused.gguf"),
    )
    assert text.startswith("{")
    assert Fits.instances[-1].generate_calls == 1
    assert Fits.instances[-1].completion_kwargs["max_tokens"] == CV_LLM_MIN_COMPLETION_TOKENS


def test_one_token_over_does_not_generate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KARRIEREKRAKE_CV_LLM_N_CTX", "4096")
    n_prompt = 4096 - CV_LLM_CTX_SLACK_TOKENS - CV_LLM_MIN_COMPLETION_TOKENS + 1

    class Over(_FakeLlama):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.prompt_tokens = n_prompt

    monkeypatch.setattr("core.cv_llm_runtime._llama_cls", lambda: Over)
    with pytest.raises(CvImportError) as ei:
        chat_completion_inprocess(
            [{"role": "user", "content": "x"}],
            model_path=Path("unused.gguf"),
        )
    assert ei.value.code == "llm_prompt_too_long"
    assert Over.instances[-1].generate_calls == 0
    assert completion_token_budget(4096, n_prompt - 1) == CV_LLM_MIN_COMPLETION_TOKENS


def test_finish_reason_length_is_truncated_not_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KARRIEREKRAKE_CV_LLM_N_CTX", "4096")

    class Trunc(_FakeLlama):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.prompt_tokens = 100
            self.finish_reason = "length"
            self.content = "{"

    monkeypatch.setattr("core.cv_llm_runtime._llama_cls", lambda: Trunc)
    with pytest.raises(CvImportError) as ei:
        chat_completion_inprocess(
            [{"role": "user", "content": "x"}],
            model_path=Path("unused.gguf"),
        )
    assert ei.value.code == "llm_output_truncated"
    assert Trunc.instances[-1].generate_calls == 1


def test_default_n_ctx_is_4096(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KARRIEREKRAKE_CV_LLM_N_CTX", raising=False)
    assert resolve_cv_llm_n_ctx() == 4096


def test_thread_defaults_follow_cpu_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KARRIEREKRAKE_CV_LLM_N_THREADS", raising=False)
    monkeypatch.delenv("KARRIEREKRAKE_CV_LLM_N_THREADS_BATCH", raising=False)
    monkeypatch.setattr("core.cv_llm_runtime.physical_cpu_count", lambda: 2)
    monkeypatch.setattr("core.cv_llm_runtime.logical_cpu_count", lambda: 4)
    assert resolve_cv_llm_threads() == (2, 4)


def test_thread_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KARRIEREKRAKE_CV_LLM_N_THREADS", "3")
    monkeypatch.setenv("KARRIEREKRAKE_CV_LLM_N_THREADS_BATCH", "5")
    assert resolve_cv_llm_threads() == (3, 5)


def test_thread_env_rejects_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KARRIEREKRAKE_CV_LLM_N_THREADS", "0")
    with pytest.raises(CvImportError) as ei:
        resolve_cv_llm_threads()
    assert ei.value.code == "llm_bad_config"


def test_physical_count_uses_psutil_then_half_logical(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr("core.cv_llm_runtime._psutil_cpu_count", lambda **_k: 4)
    assert physical_cpu_count() == 4
    monkeypatch.setattr("core.cv_llm_runtime._psutil_cpu_count", lambda **_k: None)
    monkeypatch.setattr("core.cv_llm_runtime.os.cpu_count", lambda: 8)
    with caplog.at_level("WARNING"):
        assert physical_cpu_count() == 4
    assert "psutil.cpu_count(logical=False) is None" in caplog.text
    monkeypatch.setattr("core.cv_llm_runtime.os.cpu_count", lambda: None)
    assert physical_cpu_count() == 1
    assert logical_cpu_count() == 1


def test_linux_physical_cpu_count_dedups_siblings(tmp_path: Path) -> None:
    from core.cv_llm_runtime import _linux_physical_cpu_count

    for name, core in (("cpu0", "0"), ("cpu1", "0"), ("cpu2", "1")):
        topo = tmp_path / name / "topology"
        topo.mkdir(parents=True)
        (topo / "core_id").write_text(core + "\n", encoding="utf-8")
        (topo / "physical_package_id").write_text("0\n", encoding="utf-8")
    assert _linux_physical_cpu_count(tmp_path) == 2


def test_gate_is_sampled_while_fake_model_is_still_alive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KARRIEREKRAKE_CV_LLM_N_CTX", "4096")
    stages: list[str] = []

    def boom(*, stage: str, include_llama_server: bool = True) -> None:
        stages.append(stage)
        assert include_llama_server is False
        if stage == "after_generation":
            raise CvImportError("peak_rss_exceeded", "over")

    class Spy(_FakeLlama):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.prompt_tokens = 10

    monkeypatch.setattr("core.cv_llm_runtime._llama_cls", lambda: Spy)
    monkeypatch.setattr("core.cv_docpick_import._enforce_peak_rss", boom)
    with pytest.raises(CvImportError) as ei:
        chat_completion_inprocess(
            [{"role": "user", "content": "x"}],
            model_path=Path("unused.gguf"),
        )
    assert ei.value.code == "peak_rss_exceeded"
    assert stages == ["after_load", "after_prompt_eval", "after_generation"]
    assert Spy.instances[-1].generate_calls == 1


def test_llama_constructor_receives_thread_and_ctx(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KARRIEREKRAKE_CV_LLM_N_CTX", "4096")
    monkeypatch.setattr("core.cv_llm_runtime.resolve_cv_llm_threads", lambda: (2, 4))
    seen: dict = {}

    class Spy(_FakeLlama):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            seen.update(kwargs)
            self.prompt_tokens = 10

    monkeypatch.setattr("core.cv_llm_runtime._llama_cls", lambda: Spy)
    chat_completion_inprocess(
        [{"role": "user", "content": "x"}],
        model_path=Path("unused.gguf"),
    )
    assert seen["n_ctx"] == 4096
    assert seen["n_threads"] == 2
    assert seen["n_threads_batch"] == 4
    assert seen["n_batch"] == 512
    assert seen["verbose"] is False
    assert Spy.instances[-1].completion_kwargs["max_tokens"] == (
        4096 - 10 - CV_LLM_CTX_SLACK_TOKENS
    )
