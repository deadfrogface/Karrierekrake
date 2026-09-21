"""Black-box pytest config — no Karrierekrake app imports in this package."""

from __future__ import annotations

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "blackbox_windows: requires Windows + packaged EXE + KARRIEREKRAKE_RUN_BLACKBOX=1",
    )
