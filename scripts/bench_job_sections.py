#!/usr/bin/env python3
"""Time split_job_sections + requirements_first_excerpt.

Label: VM, nicht i3. Pins the process to one CPU when the OS allows it.
HTML fixtures are cleaned first, the same way the regression tests do
(``job_from_job_posting``). The timer covers only the two pure functions.

Uses time.perf_counter_ns. Warm-up runs are not included in the figures.
"""

from __future__ import annotations

import math
import os
import sys
import time
import tracemalloc
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.job_sections import requirements_first_excerpt, split_job_sections
from tests.test_job_sections import synthetic_ad_near_headings, synthetic_ad_no_headings
from tests.test_scraped_ad_html_clean import REGRESSION_CASES, _cleaned

_WARMUP_PASSES = 40
_SAMPLE_PASSES = 80
_BATCH = 5000
_LARGE_WARMUP = 5
_LARGE_SAMPLES = 11


def _pin_one_core() -> str:
    if not hasattr(os, "sched_setaffinity"):
        return "affinity unsupported"
    try:
        os.sched_setaffinity(0, {0})
    except (AttributeError, OSError) as exc:
        return f"affinity failed: {exc}"
    return "cpu 0"


def _pair(text: str) -> None:
    split_job_sections(text)
    requirements_first_excerpt(text)


def _percentile(sorted_ns: list[int], fraction: float) -> float:
    """Nearest-rank percentile. ``sorted_ns`` must be sorted ascending."""
    if not sorted_ns:
        return 0.0
    rank = max(1, math.ceil(fraction * len(sorted_ns)))
    return float(sorted_ns[rank - 1])


def _corpus_texts() -> list[str]:
    return [_cleaned(case.html) for case in REGRESSION_CASES]


def _time_corpus(texts: list[str]) -> tuple[float, float, float]:
    for _ in range(_WARMUP_PASSES):
        for text in texts:
            _pair(text)
    samples: list[int] = []
    for _ in range(_SAMPLE_PASSES):
        for text in texts:
            started = time.perf_counter_ns()
            _pair(text)
            samples.append(time.perf_counter_ns() - started)
    samples.sort()
    median_us = samples[len(samples) // 2] / 1000.0
    p95_us = _percentile(samples, 0.95) / 1000.0
    started = time.perf_counter_ns()
    for index in range(_BATCH):
        _pair(texts[index % len(texts)])
    total_s = (time.perf_counter_ns() - started) / 1_000_000_000.0
    return median_us, p95_us, total_s


def _time_large(text: str) -> tuple[float, int]:
    for _ in range(_LARGE_WARMUP):
        _pair(text)
    samples: list[float] = []
    for _ in range(_LARGE_SAMPLES):
        started = time.perf_counter()
        _pair(text)
        samples.append(time.perf_counter() - started)
    samples.sort()
    median_s = samples[len(samples) // 2]
    tracemalloc.start()
    _pair(text)
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return median_s, peak


def main() -> None:
    affinity = _pin_one_core()
    texts = _corpus_texts()
    median_us, p95_us, total_s = _time_corpus(texts)
    plain = synthetic_ad_no_headings()
    near = synthetic_ad_near_headings()
    plain_s, plain_peak = _time_large(plain)
    near_s, near_peak = _time_large(near)
    print("label: VM, nicht i3")
    print(f"affinity: {affinity}")
    print(f"corpus_ads: {len(texts)}")
    print(f"corpus_chars: {[len(text) for text in texts]}")
    print(f"median_us: {median_us:.2f}")
    print(f"p95_us: {p95_us:.2f}")
    print(f"total_5000_s: {total_s:.4f}")
    print(f"no_heading_s: {plain_s:.4f}")
    print(f"no_heading_bytes: {len(plain.encode('utf-8'))}")
    print(f"no_heading_peak_kib: {plain_peak / 1024:.1f}")
    print(f"near_heading_s: {near_s:.4f}")
    print(f"near_heading_bytes: {len(near.encode('utf-8'))}")
    print(f"near_heading_peak_kib: {near_peak / 1024:.1f}")


if __name__ == "__main__":
    main()
