"""Shared fixtures for tests.e2e package."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.e2e.harness import E2EEnv, make_e2e_env


@pytest.fixture()
def e2e_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> E2EEnv:
    return make_e2e_env(tmp_path, monkeypatch)
