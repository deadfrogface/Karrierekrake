"""The packaged new-user journey, driven with a stand-in import child and search worker.

The real proof runs in CI inside the built package with the real model and network
(``--checks model_setup,new_user_journey``). This test proves the driver itself:
setup assistant -> CV import dialog -> finish -> search, at 200 % scaling.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("PySide6.QtWidgets")

ROOT = Path(__file__).resolve().parents[1]

DRIVER = r'''
import faulthandler, json, sys
faulthandler.dump_traceback_later(150, exit=True)  # a hang shows its stack instead of a bare timeout
from pathlib import Path
from desktop import cv_import_supervisor, package_selfcheck, workers

IMPORT_OK = sys.argv[3] == "ok"

class Proc:
    returncode = 0
    def poll(self): return 0
    def terminate(self): pass
    def wait(self, timeout=None): return 0
    def close(self): pass

def spawn(cv_path, out_path):
    parsed = {
        "personal": {"first_name": "Ada", "last_name": "Lovelace"},
        "emails": ["ada@example.com"], "phones": [], "languages": [], "education": [],
        "work_experience": [{"title": "Sachbearbeiterin", "company": "Beispiel GmbH",
                             "start_date": "2020", "end_date": "2024"}],
        "certificates": [], "software": [], "skills": [], "driving_license": [],
        "confidence": {"personal": "high"}, "source_path": str(cv_path),
        "uncertain_items": [], "intelligence_status": "docpick_qwen35",
    }
    payload = {"ok": True, "parsed": parsed} if IMPORT_OK else {"ok": False, "kind": "llm_empty", "message": "leer"}
    Path(out_path).write_text(json.dumps(payload), encoding="utf-8")
    return Proc()

cv_import_supervisor.default_spawn = spawn
cv_import_supervisor._read_app_private_bytes = lambda: 167_272_448
def run(self):
    import time
    time.sleep(0.5)  # a real search never ends before the window has connected its result handler
    self.finished.emit({"new": 2, "matches": 1})

workers.PipelineWorker.run = run
sys.exit(package_selfcheck.main(["--out", sys.argv[1], "--checks", "new_user_journey", "--cv", sys.argv[2]]))
'''


def _run(tmp_path: Path, outcome: str) -> tuple[int, dict]:
    out = tmp_path / "report.json"
    env = {k: v for k, v in os.environ.items() if not k.startswith(("KARRIEREKRAKE_", "QT_"))}
    env.update(KARRIEREKRAKE_DATA_DIR=str(tmp_path / "data"), KARRIEREKRAKE_MODELS_DIR=str(tmp_path / "models"),
               LOCALAPPDATA=str(tmp_path / "localappdata"), HOME=str(tmp_path / "home"),
               QT_QPA_PLATFORM="offscreen", PYTHONPATH=str(ROOT))
    cv = ROOT / "tests" / "fixtures" / "cv_corpus" / "DE_01_Klassisch.pdf"
    done = subprocess.run([sys.executable, "-c", DRIVER, str(out), str(cv), outcome], env=env, cwd=ROOT,
                          capture_output=True, text=True, timeout=240, check=False)
    assert out.is_file(), done.stderr[-6000:]
    return done.returncode, json.loads(out.read_text(encoding="utf-8"))["checks"]["new_user_journey"]


def test_new_person_reaches_a_finished_search(tmp_path):
    code, result = _run(tmp_path, "ok")
    assert result.get("ok") is True and code == 0, json.dumps(result, ensure_ascii=False)[:3000]
    assert result["fresh_profile"] is True and result["device_pixel_ratio"] == 2.0
    assert len(result["wizard_pages"]) == 6
    assert result["setup"]["finished"] and result["setup"]["cv_stored"] and result["setup"]["work_experience"] == 1
    assert result["search"]["finished"] and result["search"]["recorded"]


def test_failed_import_fails_the_journey_and_does_not_finish_setup(tmp_path):
    code, result = _run(tmp_path, "fail")
    assert result["ok"] is False and code == 1
    assert result["cv_import"]["ok"] is False
    assert result["setup"]["finished"] is False
    assert result["search"] == {"started": False}
