"""An unsaved, null or single-colour capture fails the real-font screenshot run (exit 1)."""
import importlib.util
from pathlib import Path

import pytest
from PySide6.QtGui import QColor, QImage

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "capture_real_font_screenshots.py"


def _script():
    spec = importlib.util.spec_from_file_location("capture_real_font_screenshots", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Pixmap:
    """Stand-in for QPixmap: real QImage content, controllable save() result."""

    def __init__(self, image: QImage, saved: bool = True):
        self._image, self._saved = image, saved

    def isNull(self):
        return self._image.isNull()

    def toImage(self):
        return self._image

    def save(self, _path):
        return self._saved


def _uniform(w=40, h=30, color="white"):
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(QColor(color))
    return img


def _drawn():
    img = _uniform()
    for x in range(10, 20):
        img.setPixelColor(x, 15, QColor("black"))
    return img


def _result(**checks):
    base = {"all_buttons_labels_inside_window": True, "outside": [], "longest_word_fits": True,
            "window_width": 640, "panel_min_width_le_640": True, "saved": True, "non_uniform": True}
    base.update(checks)
    return {"file": "lock_de_wizard_x_dpr1.0.png", "checks": base}


def test_saved_drawn_capture_passes(tmp_path):
    checks = _script()._save_capture(_Pixmap(_drawn()), tmp_path / "a.png")
    assert checks == {"saved": True, "non_uniform": True}
    assert _script()._failed_files([_result(**checks)]) == []


@pytest.mark.parametrize("pixmap, expected", [
    (_Pixmap(_drawn(), saved=False), {"saved": False, "non_uniform": True}),
    (_Pixmap(QImage()), {"saved": False, "non_uniform": False}),
    (_Pixmap(_uniform()), {"saved": True, "non_uniform": False}),
    (_Pixmap(_uniform(color="black"), saved=False), {"saved": False, "non_uniform": False}),
], ids=["save_false", "null_image", "uniform_white", "uniform_unsaved"])
def test_unsaved_or_blank_capture_is_failed(tmp_path, pixmap, expected):
    module = _script()
    checks = module._save_capture(pixmap, tmp_path / "a.png")
    assert checks == expected
    assert module._failed_files([_result(**checks)]) == ["lock_de_wizard_x_dpr1.0.png"]


@pytest.mark.parametrize("missing", ["saved", "non_uniform"])
def test_missing_capture_check_is_failed(missing):
    result = _result()
    del result["checks"][missing]
    assert _script()._failed_files([result]) == ["lock_de_wizard_x_dpr1.0.png"]
