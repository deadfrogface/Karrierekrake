"""A window wider than 640 px (or a card needing more) fails the real-font screenshot run (exit 1)."""
import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "capture_real_font_screenshots.py"


def _script():
    spec = importlib.util.spec_from_file_location("capture_real_font_screenshots", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _result(**checks):
    base = {"all_buttons_labels_inside_window": True, "outside": [], "longest_word_fits": True,
            "window_width": 640, "panel_min_width_le_640": True}
    base.update(checks)
    return {"file": "lock_de_wizard_x_dpr1.5.png", "checks": base}


def test_all_ok_is_not_failed():
    assert _script()._failed_files([_result()]) == []


@pytest.mark.parametrize("checks", [
    {"window_width": 700},
    {"panel_min_width_le_640": False},
    {"window_width": 700, "panel_min_width_le_640": False},
])
def test_too_wide_window_or_card_is_failed(checks):
    assert _script()._failed_files([_result(**checks)]) == ["lock_de_wizard_x_dpr1.5.png"]
