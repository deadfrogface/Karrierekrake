"""T01.09.03: the committed CI timings reproduce the medians in the measurement report."""

from __future__ import annotations

import json

import pytest

from scripts.ci_runtime_compare import TIMINGS, medians

# (platform, phase): (n, job, install, smoke) as published in
# docs/project/T01_09_03_CI_RUNTIME_2026-10-20.md
REPORTED = {
    ("linux", "vor"): (5, 10.9, 0.7, 5.8),
    ("linux", "nach"): (6, 10.2, 0.6, 5.2),
    ("mac-arm", "vor"): (5, 10.5, 0.5, 7.0),
    ("mac-arm", "nach"): (6, 11.1, 0.5, 6.5),
    ("mac-intel", "vor"): (5, 21.6, 1.9, 11.1),
    ("mac-intel", "nach"): (6, 20.6, 1.7, 10.9),
}


@pytest.fixture(scope="module")
def computed():
    return medians(json.loads(TIMINGS.read_text(encoding="utf-8")))


@pytest.mark.parametrize("key", sorted(REPORTED))
def test_reported_medians_match_raw_timings(computed, key) -> None:
    n, job, install, smoke = REPORTED[key]
    m = computed[key]
    assert m["n"] == n
    assert round(m["job"], 1) == job
    assert round(m["install"], 1) == install
    assert round(m["smoke"], 1) == smoke


def test_workflow_edit_rebuild_before_and_cache_hit_after(computed) -> None:
    """105bf449 (before) rebuilt after workflow edits; adc297cf (after, workflow edited) hit the cache."""
    runs = {r["head_sha"][:8]: r for r in json.loads(TIMINGS.read_text(encoding="utf-8"))}

    def install(sha: str, platform: str) -> float:
        job = next(j for j in runs[sha]["jobs"] if platform in j["name"])
        return sum(s["minutes"] for s in job["steps"] if s["name"].startswith("Install native dependencies"))

    for platform in ("ubuntu", "macos-14", "intel"):
        assert install("105bf449", platform) > 2 * install("adc297cf", platform)
