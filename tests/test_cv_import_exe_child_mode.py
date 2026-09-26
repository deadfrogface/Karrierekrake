"""Packaged EXE must spawn CV import via --cv-import-child, not -m.

When frozen, ``sys.executable`` is Karrierekrake.exe. Spawning
``exe -m desktop.cv_import_child`` re-enters the GUI entrypoint, hits the
single-instance lock, and exits 1 with „Karrierekrake läuft bereits“.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

from desktop.cv_import_supervisor import cv_import_child_argv


def test_dev_spawn_uses_module_invocation(tmp_path: Path):
    cv = tmp_path / "cv.pdf"
    out = tmp_path / "out.json"
    with patch.object(sys, "frozen", False, create=True):
        argv = cv_import_child_argv(cv, out)
    assert argv[0] == sys.executable
    assert argv[1:3] == ["-m", "desktop.cv_import_child"]
    assert "--cv-import-child" not in argv
    assert argv[argv.index("--cv") + 1] == str(cv)
    assert argv[argv.index("--out") + 1] == str(out)


def test_frozen_spawn_uses_cv_import_child_flag(tmp_path: Path):
    cv = tmp_path / "cv.docx"
    out = tmp_path / "out.json"
    exe = str(tmp_path / "Karrierekrake.exe")
    with patch.object(sys, "frozen", True, create=True), patch.object(sys, "executable", exe):
        argv = cv_import_child_argv(cv, out)
    assert argv[0] == str(Path(exe).resolve())
    assert argv[1] == "--cv-import-child"
    assert "-m" not in argv
    assert "desktop.cv_import_child" not in argv
    assert argv[argv.index("--cv") + 1] == str(cv)
    assert argv[argv.index("--out") + 1] == str(out)


def test_main_cv_import_child_skips_gui_and_instance_lock(monkeypatch, tmp_path: Path):
    from desktop import app as app_mod

    cv = tmp_path / "cv.pdf"
    out = tmp_path / "out.json"
    seen: list[list[str] | None] = []

    def fake_child(argv=None):
        seen.append(list(argv) if argv is not None else None)
        return 0

    def boom_run() -> int:
        raise AssertionError("GUI run() must not start for --cv-import-child")

    def boom_lock():
        raise AssertionError("single-instance lock must not run for --cv-import-child")

    monkeypatch.setattr(
        sys,
        "argv",
        ["Karrierekrake.exe", "--cv-import-child", "--cv", str(cv), "--out", str(out)],
    )
    monkeypatch.setattr("desktop.cv_import_child.run", fake_child)
    monkeypatch.setattr(app_mod, "run", boom_run)
    monkeypatch.setattr(app_mod, "acquire_single_instance_lock", boom_lock)

    assert app_mod.main() == 0
    assert seen == [["--cv", str(cv), "--out", str(out)]]


def test_main_cv_import_child_propagates_child_exit(monkeypatch, tmp_path: Path):
    from desktop import app as app_mod

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "Karrierekrake.exe",
            "--cv-import-child",
            "--cv",
            str(tmp_path / "cv.pdf"),
            "--out",
            str(tmp_path / "out.json"),
        ],
    )
    monkeypatch.setattr("desktop.cv_import_child.run", lambda argv=None: 1)
    monkeypatch.setattr(app_mod, "run", lambda: (_ for _ in ()).throw(AssertionError("no gui")))

    assert app_mod.main() == 1
