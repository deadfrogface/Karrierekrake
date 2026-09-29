"""Smoke JSON timings and the #69 peak key."""

from __future__ import annotations

import sys

from core import cv_docpick_import as doc
from core.cv_llm_runtime import public_llm_step
from scripts.ci_cv_import_exe_offline_e2e import (
    LEGACY_RUSAGE_KEY,
    LEGACY_WORKING_SET_KEY,
    PEAK_JOB_KEY,
    _LLM_NUMERIC,
    _LLM_STEPS,
    build_smoke_metrics,
    format_llm_step_line,
    format_runner_cpu_line,
    outside_model_s,
    parse_linux_cpuinfo,
    parse_win32_processor_rows,
)


def _llm(**overrides: object) -> dict:
    step = {
        "prompt_tokens": 1763,
        "prompt_eval_s": 14.5,
        "prompt_tok_per_s": round(1763 / 14.5, 3),
        "gen_tokens": 655,
        "gen_s": 90.0,
        "gen_tok_per_s": round(655 / 90.0, 3),
        "n_threads": 3,
        "physical_cores": 4,
        "physical_cores_source": "psutil",
        "ggml_cpu_isa": "CPU : SSE3 = 1 | AVX2 = 1 |",
        "ggml_cpu_backend": "ggml-cpu.dll",
        "timing_source": "llama_perf_context",
        "peak_job_memory_used_bytes": 1_800_000_000,
        "peak_counter": "PeakJobMemoryUsed",
    }
    step.update(overrides)
    return step


def _report() -> dict:
    de = _llm(peak_job_memory_used_bytes=1_900_000_000)
    en = _llm(prompt_tokens=1575, gen_tokens=400, peak_job_memory_used_bytes=1_850_000_000)
    cover = _llm(prompt_tokens=40, gen_tokens=80, gen_s=8.0, peak_job_memory_used_bytes=1_700_000_000)
    return {
        "exe_bytes": 50_000_000,
        "sidecar_bytes": 2_740_937_888,
        "steps": {
            "start": {"ok": True, "wall_s": 3.0},
            "import": {"ok": True, "wall_s": 270.0, "llm_step": de},
            "import_en": {"ok": True, "wall_s": 200.0, "llm_step": en},
            "restart": {"ok": True, "wall_s": 2.5},
            "cover_letter": {"ok": True, "wall_s": 12.0, "llm_step": cover},
        },
    }


def test_metrics_keys_are_present_and_numeric() -> None:
    report = _report()
    report["steps"]["import"]["llm_step"]["outside_model_s"] = outside_model_s(270.0, 14.5, 90.0)
    report["steps"]["import_en"]["llm_step"]["outside_model_s"] = outside_model_s(200.0, 14.5, 90.0)
    report["steps"]["cover_letter"]["llm_step"]["outside_model_s"] = outside_model_s(12.0, 14.5, 8.0)
    metrics = build_smoke_metrics(report)
    assert "peak_rss_bytes_children" not in metrics
    assert metrics[PEAK_JOB_KEY] == 1_900_000_000
    assert isinstance(metrics[LEGACY_RUSAGE_KEY], int) and not isinstance(metrics[LEGACY_RUSAGE_KEY], bool)
    assert isinstance(metrics[LEGACY_WORKING_SET_KEY], int) and not isinstance(
        metrics[LEGACY_WORKING_SET_KEY], bool
    )
    for _name, prefix in _LLM_STEPS:
        for key in _LLM_NUMERIC:
            value = metrics["%s_%s" % (prefix, key)]
            assert isinstance(value, (int, float)) and not isinstance(value, bool), key
        assert metrics["%s_physical_cores_source" % prefix] == "psutil"
        assert metrics["%s_ggml_cpu_isa" % prefix].startswith("CPU :")
        assert metrics["%s_peak_counter" % prefix] == "PeakJobMemoryUsed"
    assert metrics["import_de_outside_model_s"] == outside_model_s(270.0, 14.5, 90.0)
    assert metrics["import_de_prompt_tokens"] == 1763
    assert metrics["import_de_n_threads"] == 3
    assert metrics["import_de_physical_cores"] == 4


def test_outside_model_time_is_wall_minus_eval_and_gen() -> None:
    assert outside_model_s(270.0, 20.0, 40.0) == 210.0
    line = format_llm_step_line("import_de", _llm(outside_model_s=210.0))
    assert "outside_model_s=210.0" in line
    assert "n_threads=3" in line
    assert "physical_cores source=psutil count=4" in line
    assert "peak_job_memory_used_bytes=1800000000" in line
    assert 'ggml_cpu_isa="CPU : SSE3 = 1 | AVX2 = 1 |"' in line


def test_public_llm_step_drops_free_text() -> None:
    cleaned = public_llm_step(
        _llm(ggml_cpu_isa="C:\\Users\\secret\\model.gguf", physical_cores_source="env")
    )
    assert cleaned["ggml_cpu_isa"] == ""
    assert cleaned["physical_cores_source"] == ""
    assert cleaned["prompt_tokens"] == 1763


def test_windows_peak_is_the_measure_job_not_pagefile(monkeypatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(doc, "_windows_peak_pagefile_bytes", lambda: 4_400_000_000)
    doc.bind_import_measure_job(7, lambda handle: 1_800_000_000 if handle else 0)
    try:
        assert doc.model_process_peak_job_memory_used_bytes() == 1_800_000_000
    finally:
        doc.reset_import_measure_job()


def test_runner_cpu_parsers() -> None:
    text = (
        "processor\t: 0\nmodel name\t: Intel Xeon\nphysical id\t: 0\ncpu cores\t: 2\n"
        "processor\t: 1\nmodel name\t: Intel Xeon\nphysical id\t: 0\ncpu cores\t: 2\n"
    )
    linux = parse_linux_cpuinfo(text)
    assert linux["runner_cpu_name"] == "Intel Xeon"
    assert linux["runner_logical_cores"] == 2
    assert linux["runner_physical_cores"] == 2
    windows = parse_win32_processor_rows(
        [
            {"Name": "Intel(R) Xeon(R)", "NumberOfLogicalProcessors": 2, "NumberOfCores": 2},
        ]
    )
    assert windows["runner_logical_cores"] == 2
    assert windows["runner_physical_cores"] == 2
    assert format_runner_cpu_line(windows).startswith("runner_cpu name=Intel(R) Xeon(R) logical=2 physical=2")
