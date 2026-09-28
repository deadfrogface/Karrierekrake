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
    cv_llm_thread_report_line,
    physical_cores_report_line,
    physical_cpu_count,
    resolve_cv_llm_n_ctx,
    resolve_cv_llm_thread_plan,
    resolve_cv_llm_threads,
    thread_reserve,
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


@pytest.mark.parametrize(
    ("physical", "logical", "n_threads", "n_batch", "reserve"),
    [
        (8, 8, 7, 7, 1),
        (2, 4, 2, 4, 0),
        (4, 8, 4, 8, 0),
        (2, 2, 2, 2, 0),
        (4, 4, 3, 3, 1),
    ],
)
def test_thread_reserve_keeps_a_core_only_without_smt(
    monkeypatch: pytest.MonkeyPatch,
    physical: int,
    logical: int,
    n_threads: int,
    n_batch: int,
    reserve: int,
) -> None:
    """(8,8), (2,4), (4,8), (2,2), (4,4): physical, logical."""
    monkeypatch.delenv("KARRIEREKRAKE_CV_LLM_N_THREADS", raising=False)
    monkeypatch.delenv("KARRIEREKRAKE_CV_LLM_N_THREADS_BATCH", raising=False)
    monkeypatch.setattr("core.cv_llm_runtime.physical_cpu_count", lambda: physical)
    monkeypatch.setattr("core.cv_llm_runtime.logical_cpu_count", lambda: logical)
    assert thread_reserve(physical, logical) == reserve
    assert resolve_cv_llm_threads() == (n_threads, n_batch)
    plan = resolve_cv_llm_thread_plan()
    assert plan == (n_threads, n_batch, physical, logical, reserve)
    line = cv_llm_thread_report_line()
    assert line == (
        f"n_threads={n_threads} n_threads_batch={n_batch} "
        f"physical={physical} logical={logical} reserve={reserve}"
    )


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
    assert physical_cores_report_line() == "physical_cores source=psutil count=4"
    monkeypatch.setattr("core.cv_llm_runtime._psutil_cpu_count", lambda **_k: None)
    monkeypatch.setattr("core.cv_llm_runtime.os.cpu_count", lambda: 8)
    with caplog.at_level("WARNING"):
        assert physical_cpu_count() == 4
        assert physical_cores_report_line() == "physical_cores source=fallback count=4"
    assert "psutil.cpu_count(logical=False) is None" in caplog.text
    monkeypatch.setattr("core.cv_llm_runtime.os.cpu_count", lambda: None)
    assert physical_cpu_count() == 1
    assert logical_cpu_count() == 1
    monkeypatch.setattr("core.cv_llm_runtime.os.cpu_count", lambda: 1)
    assert physical_cpu_count() == 1


def test_physical_fallback_when_psutil_import_fails(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """psutil missing: max(1, os.cpu_count() // 2), and 1 if that count is None."""
    import builtins

    real_import = builtins.__import__

    def _block_psutil(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "psutil" or (isinstance(name, str) and name.startswith("psutil.")):
            raise ImportError("psutil missing")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _block_psutil)
    monkeypatch.setattr("core.cv_llm_runtime.os.cpu_count", lambda: 8)
    with caplog.at_level("WARNING"):
        assert physical_cpu_count() == 4
    assert "fallback max(1, os.cpu_count()//2)=4" in caplog.text
    monkeypatch.setattr("core.cv_llm_runtime.os.cpu_count", lambda: None)
    assert physical_cpu_count() == 1
    assert physical_cores_report_line() == "physical_cores source=fallback count=1"
    monkeypatch.setattr("core.cv_llm_runtime.os.cpu_count", lambda: 1)
    assert physical_cpu_count() == 1


def test_physical_fallback_when_psutil_returns_none(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """psutil.cpu_count None: same fallback, including os.cpu_count() is None."""

    class _PsutilNone:
        @staticmethod
        def cpu_count(*, logical: bool = True) -> None:
            return None

    monkeypatch.setitem(__import__("sys").modules, "psutil", _PsutilNone())
    monkeypatch.setattr("core.cv_llm_runtime.os.cpu_count", lambda: 8)
    with caplog.at_level("WARNING"):
        assert physical_cpu_count() == 4
    assert "psutil.cpu_count(logical=False) is None" in caplog.text
    monkeypatch.setattr("core.cv_llm_runtime.os.cpu_count", lambda: None)
    assert physical_cpu_count() == 1
    assert logical_cpu_count() == 1


def test_report_line_uses_installed_psutil() -> None:
    psutil = pytest.importorskip("psutil")
    expected = psutil.cpu_count(logical=False)
    if not expected:
        pytest.skip("psutil.cpu_count(logical=False) is None on this host")
    assert physical_cores_report_line() == f"physical_cores source=psutil count={int(expected)}"


def test_linux_physical_cpu_count_dedups_siblings(tmp_path: Path) -> None:
    from core.cv_llm_runtime import _linux_physical_cpu_count

    for name, core in (("cpu0", "0"), ("cpu1", "0"), ("cpu2", "1")):
        topo = tmp_path / name / "topology"
        topo.mkdir(parents=True)
        (topo / "core_id").write_text(core + "\n", encoding="utf-8")
        (topo / "physical_package_id").write_text("0\n", encoding="utf-8")
    assert _linux_physical_cpu_count(tmp_path) == 2


def test_over_limit_after_load_skips_prompt_eval(monkeypatch: pytest.MonkeyPatch) -> None:
    """Private commit over the gate at load must not start prompt evaluation."""
    monkeypatch.setenv("KARRIEREKRAKE_CV_LLM_N_CTX", "4096")
    stages: list[str] = []

    class Spy(_FakeLlama):
        def count_chat_tokens(self, messages):
            raise AssertionError("token count ran after an over-limit load")

        def create_chat_completion(self, **kwargs):
            raise AssertionError("prompt eval ran after an over-limit load")

    def boom(*, stage: str, include_llama_server: bool = True) -> None:
        stages.append(stage)
        assert include_llama_server is False
        if stage == "after_load":
            raise CvImportError("peak_rss_exceeded", "peak_rss_exceeded")

    monkeypatch.setattr("core.cv_llm_runtime._llama_cls", lambda: Spy)
    monkeypatch.setattr("core.cv_docpick_import._enforce_peak_rss", boom)
    with pytest.raises(CvImportError) as ei:
        chat_completion_inprocess(
            [{"role": "user", "content": "x"}],
            model_path=Path("unused.gguf"),
        )
    assert ei.value.code == "peak_rss_exceeded"
    assert stages == ["after_load"]


def test_app_share_after_load_skips_prompt_eval(monkeypatch: pytest.MonkeyPatch) -> None:
    """A load over the current child budget must not evaluate the prompt."""
    from core.cv_docpick_import import (
        CV_IMPORT_CHILD_MIN_AFTER_LOAD_BYTES,
        fresh_app_child_budget_bytes,
        reset_private_commit_high_water,
    )

    reset_private_commit_high_water()
    sample = CV_IMPORT_CHILD_MIN_AFTER_LOAD_BYTES + 1
    assert sample < fresh_app_child_budget_bytes()
    monkeypatch.setenv("KARRIEREKRAKE_CV_LLM_N_CTX", "4096")
    monkeypatch.setenv(
        "KARRIEREKRAKE_CV_CHILD_BUDGET_BYTES",
        str(CV_IMPORT_CHILD_MIN_AFTER_LOAD_BYTES),
    )
    monkeypatch.setenv("KARRIEREKRAKE_CV_APP_PRIVATE_BYTES", "1601831168")
    monkeypatch.setattr(
        "core.cv_docpick_import.cv_path_peak_rss_bytes",
        lambda **_kwargs: sample,
    )

    class Spy(_FakeLlama):
        def count_chat_tokens(self, messages):
            raise AssertionError("token count ran after an over-budget load")

        def create_chat_completion(self, **kwargs):
            raise AssertionError("prompt eval ran after an over-budget load")

    monkeypatch.setattr("core.cv_llm_runtime._llama_cls", lambda: Spy)
    with pytest.raises(CvImportError) as ei:
        chat_completion_inprocess(
            [{"role": "user", "content": "x"}],
            model_path=Path("unused.gguf"),
        )
    assert ei.value.code == "memory_budget_app_share"
    reset_private_commit_high_water()


def test_load_log_keeps_buffer_and_cpu_lines(caplog: pytest.LogCaptureFixture) -> None:
    from core.cv_llm_runtime import _log_llama_load_lines

    blob = "\n".join(
        [
            "llama_model_loader: loaded meta data",
            "load_tensors: CPU_REPACK model buffer size = 1297.97 MiB",
            "load_tensors: AMX model buffer size = 2647.61 MiB",
            "CPU : SSE3 = 1 | AVX2 = 1 | REPACK = 1 | ",
            "some other line",
        ]
    )
    with caplog.at_level("INFO"):
        _log_llama_load_lines(blob)
    assert "CPU_REPACK model buffer" in caplog.text
    assert "AMX model buffer" in caplog.text
    assert "AVX2 = 1" in caplog.text
    assert "loaded meta data" not in caplog.text


def test_build_report_marks_single_cpu_library() -> None:
    from core.cv_llm_runtime import format_llama_build_report

    text = format_llama_build_report(
        "CPU : AVX2 = 1 | REPACK = 1 | ",
        ["ggml-cpu.dll", "ggml.dll"],
    )
    assert "llama_cpu_features=CPU : AVX2 = 1 | REPACK = 1 |" in text
    assert "llama_cpu_all_variants=0" in text
    assert "llama_runtime_isa=fixed" in text
    assert "llama_model_buffer=not_loaded" in text
    variants = format_llama_build_report(
        "CPU : AVX2 = 1 | ",
        ["ggml-cpu-haswell.dll", "ggml-cpu-sapphirerapids.dll"],
    )
    assert "llama_cpu_all_variants=1" in variants
    assert "llama_runtime_isa=runtime" in variants


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
    monkeypatch.setattr(
        "core.cv_llm_runtime.resolve_cv_llm_thread_plan",
        lambda: (2, 4, 2, 4, 0),
    )
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
    assert seen["verbose"] is True
    assert Spy.instances[-1].verbose is False
    assert Spy.instances[-1].completion_kwargs["max_tokens"] == (
        4096 - 10 - CV_LLM_CTX_SLACK_TOKENS
    )


def test_timeout_event_once_and_token_events_at_most_three(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """1000 tokens across 2 s yield at most 3 progress events, and one timeout."""
    import json

    from core.cv_phase_events import TokenProgressThrottle

    throttle = TokenProgressThrottle()
    direct = []
    for index in range(1000):
        event = throttle.consider(tokens_done=index + 1, now=index * (2.0 / 999))
        if event is not None:
            direct.append(event)
    assert len(direct) <= 3
    assert direct[0]["tokens_done"] == 1
    assert all("tokens_done" in event and "max_tokens" not in event for event in direct)

    monkeypatch.setenv("KARRIEREKRAKE_CV_LLM_N_CTX", "4096")
    monkeypatch.setenv("KARRIEREKRAKE_CV_IMPORT_TIMEOUT_S", "95")
    phase = tmp_path / "phase.jsonl"
    monkeypatch.setenv("KARRIEREKRAKE_CV_PHASE_EVENTS", str(phase))
    times = [index * (2.0 / 999) for index in range(1000)]
    cursor = {"i": 0}

    def clock() -> float:
        current = cursor["i"]
        cursor["i"] = current + 1
        return times[current]

    monkeypatch.setattr("core.cv_phase_events.phase_clock", clock)

    class Many(_FakeLlama):
        def create_chat_completion(self, **kwargs):
            self.generate_calls += 1
            self.completion_kwargs = kwargs

            def chunks():
                for number in range(1000):
                    yield {
                        "choices": [
                            {
                                "delta": {"content": "x"},
                                "finish_reason": "stop" if number == 999 else None,
                            }
                        ]
                    }

            return chunks()

    monkeypatch.setattr("core.cv_llm_runtime._llama_cls", lambda: Many)
    with caplog.at_level("INFO"):
        chat_completion_inprocess(
            [{"role": "user", "content": "x"}],
            model_path=Path("unused.gguf"),
        )
    lines = [json.loads(line) for line in phase.read_text(encoding="utf-8").splitlines() if line.strip()]
    timeouts = [line for line in lines if "timeout_s" in line]
    tokens = [line for line in lines if "tokens_done" in line]
    assert timeouts == [{"phase": "generation", "timeout_s": 95}]
    assert len(tokens) <= 3
    assert tokens[0]["tokens_done"] == 1
    assert all("max_tokens" not in item for item in tokens)
    assert "max_tokens=" in caplog.text
    assert cursor["i"] == 1000


def test_prompt_blocks_are_reported_and_prefix_is_reused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Prefill evals each ``n_batch`` block, then the completion reuses it."""
    import json
    import sys

    from core.cv_llm_runtime import _prefix_reuse_from_stderr

    assert _prefix_reuse_from_stderr(
        "Llama.generate: full prompt already cached, skipping reset\n"
    ) == (1, "0")
    assert _prefix_reuse_from_stderr(
        "Llama.generate: 100 prefix-match hit, remaining 12 prompt tokens to eval\n"
    ) == (0, "12")

    monkeypatch.setenv("KARRIEREKRAKE_CV_LLM_N_CTX", "4096")
    phase = tmp_path / "phase.jsonl"
    monkeypatch.setenv("KARRIEREKRAKE_CV_PHASE_EVENTS", str(phase))
    ids = list(range(600))

    class Prefill(_FakeLlama):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.n_batch = kwargs.get("n_batch", 512)
            self.n_tokens = 0
            self.verbose = False
            self.evals: list[list[int]] = []

        def chat_prompt_token_ids(self, messages):
            assert messages
            return list(ids)

        def eval(self, tokens):
            block = [int(token) for token in tokens]
            self.evals.append(block)
            self.n_tokens += len(block)

        def create_chat_completion(self, **kwargs):
            self.generate_calls += 1
            self.completion_kwargs = kwargs

            def chunks():
                if self.verbose and self.n_tokens == len(ids):
                    print(
                        "Llama.generate: full prompt already cached, skipping reset",
                        file=sys.stderr,
                    )
                yield {
                    "choices": [
                        {"delta": {"content": "{}"}, "finish_reason": "stop"}
                    ]
                }

            return chunks()

    monkeypatch.setattr("core.cv_llm_runtime._llama_cls", lambda: Prefill)
    with caplog.at_level("INFO"):
        text = chat_completion_inprocess(
            [{"role": "user", "content": "x"}],
            model_path=Path("unused.gguf"),
        )
    assert text == "{}"
    llama = Prefill.instances[-1]
    assert llama.evals == [ids[:512], ids[512:]]
    assert llama.n_tokens == 600
    assert llama.verbose is False
    lines = [
        json.loads(line)
        for line in phase.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    prompts = [line for line in lines if "prompt_tokens_done" in line]
    assert [line["prompt_tokens_done"] for line in prompts] == [512, 600]
    assert all("t_mono" in line and "block_s" in line for line in prompts)
    assert "cv_llm_prompt_prefix reused=1 remaining_prompt_eval=0" in caplog.text
    assert "first_chunk_eval_tokens=0" in caplog.text
    assert "cv_llm_prompt_prefill n_prompt=600 n_batch=512 blocks=2" in caplog.text


def test_import_timeout_formula_env_floor_and_ceiling(monkeypatch: pytest.MonkeyPatch) -> None:
    """Env wins. DE_01 and DE_06 token counts, plus the floor and the ceiling."""
    from core.cv_docpick_import import (
        CV_IMPORT_R_GEN_TPS,
        CV_IMPORT_R_PROMPT_TPS,
        CV_IMPORT_T_LOAD_S,
        CV_IMPORT_TIMEOUT_BUFFER_S,
        CV_IMPORT_TIMEOUT_CEILING_S,
        CV_IMPORT_TIMEOUT_FLOOR_S,
        import_timeout_seconds,
    )

    de01_prompt = 1763
    de01_max = 4096 - de01_prompt - 8
    de06_prompt = 2000
    de06_max = 4096 - de06_prompt - 8
    assert de01_max == 2325
    assert de06_max == 2088

    def raw(prompt: int, max_tokens: int) -> float:
        return (
            CV_IMPORT_T_LOAD_S
            + prompt / CV_IMPORT_R_PROMPT_TPS
            + max_tokens / CV_IMPORT_R_GEN_TPS
            + CV_IMPORT_TIMEOUT_BUFFER_S
        )

    monkeypatch.delenv("KARRIEREKRAKE_CV_IMPORT_TIMEOUT_S", raising=False)
    assert raw(de01_prompt, de01_max) > CV_IMPORT_TIMEOUT_CEILING_S
    assert raw(de06_prompt, de06_max) > CV_IMPORT_TIMEOUT_CEILING_S
    assert import_timeout_seconds(de01_prompt, de01_max) == int(CV_IMPORT_TIMEOUT_CEILING_S)
    assert import_timeout_seconds(de06_prompt, de06_max) == int(CV_IMPORT_TIMEOUT_CEILING_S)
    assert raw(1, 1) < CV_IMPORT_TIMEOUT_FLOOR_S
    assert import_timeout_seconds(1, 1) == int(CV_IMPORT_TIMEOUT_FLOOR_S)
    assert import_timeout_seconds(100_000, 100_000) == int(CV_IMPORT_TIMEOUT_CEILING_S)

    monkeypatch.setenv("KARRIEREKRAKE_CV_IMPORT_TIMEOUT_S", "95")
    assert import_timeout_seconds(de01_prompt, de01_max) == 95
    assert import_timeout_seconds(1, 1) == 95
