"""Pin which Windows job memory limit the CV import child gets, and its value.

``JOB_OBJECT_LIMIT_JOB_MEMORY`` caps committed memory (private bytes), not
RSS. A 4B Q2_K_XL load was measured at RSS ~2.4 GiB but private bytes up to
5.62 GiB. Any commit cap below that kills the import while an RSS gate is
green. These tests pin today's behaviour so a change goes red:

* default (no ``KARRIEREKRAKE_PHYSICAL_I3_8GB``): no job memory limit at all;
* attested i3: ``JOB_OBJECT_LIMIT_JOB_MEMORY`` (not PROCESS_MEMORY) at the
  child budget derived from 3_300_000_000, which is below 5.62 GiB (risk).
"""

from __future__ import annotations

import pytest

from core.cv_docpick_import import (
    child_budget_for_app_private,
    fresh_app_child_budget_bytes,
    job_enforce_memory_bytes,
)
from desktop import cv_import_supervisor as sup
from devops.win_job_object import JOB_OBJECT_LIMIT_JOB_MEMORY, containment_limit_flags

MEASURED_4B_PRIVATE_COMMIT_BYTES = int(5.62 * 1024**3)
JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x00000100


def _publish_budget(monkeypatch: pytest.MonkeyPatch, *, i3: bool) -> int:
    app_private = 167_272_448
    budget = child_budget_for_app_private(app_private)
    monkeypatch.setenv("KARRIEREKRAKE_CV_CHILD_BUDGET_BYTES", str(budget))
    monkeypatch.setenv("KARRIEREKRAKE_CV_APP_PRIVATE_BYTES", str(app_private))
    if i3:
        monkeypatch.setenv("KARRIEREKRAKE_PHYSICAL_I3_8GB", "1")
    else:
        monkeypatch.delenv("KARRIEREKRAKE_PHYSICAL_I3_8GB", raising=False)
    return budget


def test_default_cv_child_sets_no_commit_based_job_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    budget = _publish_budget(monkeypatch, i3=False)
    assert job_enforce_memory_bytes(child_budget=budget, app_private=167_272_448) == 0
    limit = sup._job_limit_from_environ()
    assert limit is None
    flags = containment_limit_flags(enforce_memory_bytes=limit)
    assert flags & JOB_OBJECT_LIMIT_JOB_MEMORY == 0
    assert flags & JOB_OBJECT_LIMIT_PROCESS_MEMORY == 0


def test_attested_i3_job_limit_is_commit_cap_below_measured_4b_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    budget = _publish_budget(monkeypatch, i3=True)
    limit = sup._job_limit_from_environ()
    assert limit == budget == fresh_app_child_budget_bytes() == 3_132_727_552
    flags = containment_limit_flags(enforce_memory_bytes=limit)
    assert flags & JOB_OBJECT_LIMIT_JOB_MEMORY
    assert flags & JOB_OBJECT_LIMIT_PROCESS_MEMORY == 0
    # Documented risk: this commit cap would kill a 5.62 GiB-commit 4B load.
    assert limit < MEASURED_4B_PRIVATE_COMMIT_BYTES
