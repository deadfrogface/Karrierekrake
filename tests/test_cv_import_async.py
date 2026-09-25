"""CV import must leave the UI thread and must not auto-retry resource failures."""

from __future__ import annotations

import inspect
import json
import os
import threading
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialogButtonBox

from core.config import ApplicationProfile, QualificationsConfig
from desktop.cv_import_supervisor import CvImportSupervisor, qa_observe_seconds
from desktop.i18n import i18n, tr
from desktop.widgets.cv_import_dialog import CvImportDialog


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class _Proc:
    def __init__(self, code: int | None) -> None:
        self._code = code
        self.terminated = False
        self.returncode = code

    def poll(self):
        if self.terminated and self._code is None:
            self.returncode = -15
            return -15
        return self._code

    def terminate(self) -> None:
        self.terminated = True
        if self._code is None:
            self._code = -15
            self.returncode = -15

    def wait(self, timeout=None):
        self.terminate()
        return self.returncode

    def close(self) -> None:
        return None


def _parsed(path: Path) -> dict:
    return {
        "personal": {"first_name": "Ada", "last_name": "Lovelace"},
        "emails": ["ada@example.com"],
        "phones": [],
        "languages": [],
        "education": [],
        "work_experience": [],
        "certificates": [],
        "software": [],
        "skills": [],
        "driving_license": [],
        "confidence": {"personal": "high"},
        "source_path": str(path),
        "uncertain_items": [],
        "intelligence_status": "deterministic_only",
    }


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _pump(qapp, predicate, timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        qapp.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_settings_checkbox_shows_kill_wording_and_persists(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    from desktop import paths as paths_mod

    def fake_dirs():
        root = tmp_path / "Karrierekrake"
        dirs = {
            "root": root,
            "config": root / "config",
            "data": root / "data",
            "logs": root / "logs",
            "browser_profile": root / "browser_profile",
            "browsers": root / "browsers",
            "cvs": root / "cvs",
            "cache": root / "cache",
            "cover_letters": root / "cover_letters",
        }
        for p in dirs.values():
            p.mkdir(parents=True, exist_ok=True)
        return dirs

    monkeypatch.setattr(paths_mod, "ensure_app_dirs", fake_dirs)
    monkeypatch.setattr("desktop.services.ensure_app_dirs", fake_dirs)
    monkeypatch.setattr(
        "desktop.services.schedule_service.ScheduleService.sync_from_config",
        lambda self: (True, "ok"),
    )
    monkeypatch.setattr(
        "desktop.pages.settings.QMessageBox.information",
        lambda *args, **kwargs: None,
    )
    from desktop.services import ConfigService
    from desktop.pages.settings import SettingsPage

    i18n.set_language("de")
    page = SettingsPage(ConfigService())
    page.load_from_config()
    page.show()
    qapp.processEvents()
    assert page.local_llm_cv_parsing.isEnabled() is False
    assert page.local_llm_cv_parsing.isChecked() is False
    assert page.local_llm_cv_parsing.toolTip() == i18n.t("settings.local_llm_cv_unavailable")
    assert page.local_llm_cv_hint.text() == (
        "Das lokale LLM-CV-Parsing ist derzeit deaktiviert. "
        "Lebensläufe werden mit dem Standard-Parser gelesen."
    )
    page.save()
    loaded = ConfigService().load()
    assert loaded.settings.local_llm_cv_parsing_enabled is False


def test_dialog_init_does_not_call_import_cv():
    src = inspect.getsource(CvImportDialog.__init__)
    assert "import_cv(" not in src


def test_init_returns_before_spawn_starts(qapp, tmp_path: Path):
    calls: list[int] = []

    def spawn(cv: Path, out: Path):
        calls.append(1)
        _write(out, {"ok": True, "kind": "ok", "parsed": _parsed(cv), "message": ""})
        return _Proc(0)

    dlg = CvImportDialog(
        tmp_path / "cv.txt",
        QualificationsConfig(),
        ApplicationProfile(city="Hamburg"),
        spawn=spawn,
        autostart=True,
    )
    assert calls == []
    assert dlg.attempt_count == 0
    dlg._autostart.stop()
    dlg.close()


def test_parse_runs_off_gui_thread_and_keeps_ok_disabled_until_ready(qapp, tmp_path: Path):
    i18n.set_language("de")
    gui = threading.get_ident()
    seen: list[int] = []
    cv = tmp_path / "cv.txt"
    cv.write_text("Ada\n", encoding="utf-8")

    def spawn(path: Path, out: Path):
        seen.append(threading.get_ident())
        time.sleep(0.15)
        _write(out, {"ok": True, "kind": "ok", "parsed": _parsed(path), "message": ""})
        return _Proc(0)

    app = ApplicationProfile(city="Hamburg", first_name="Manuell")
    quals = QualificationsConfig()
    dlg = CvImportDialog(cv, quals, app, spawn=spawn, autostart=False)
    dlg.show()
    qapp.processEvents()
    assert dlg.llm_notice.isVisible()
    assert dlg.llm_notice.text() == i18n.t("settings.local_llm_cv_disabled_hint")
    dlg.start_parse()
    assert _pump(qapp, lambda: dlg.progress.isVisible() and dlg._running)
    assert seen and seen[0] != gui
    assert dlg._ok_btn.isEnabled() is False
    assert dlg._ok_btn.isVisible() is False
    assert dlg.mode_box.isVisible() is False
    assert dlg.status_label.text() == tr("cv_import.progress")
    assert cv.name in dlg.path_label.text()
    cancel = dlg._buttons.button(QDialogButtonBox.StandardButton.Cancel)
    assert cancel is not None
    assert cancel.text() == tr("cv_import.cancel_btn")
    assert _pump(qapp, lambda: dlg.incoming is not None)
    assert dlg._phase == "success"
    assert dlg._ok_btn.isVisible()
    assert dlg._ok_btn.isEnabled()
    assert dlg._ok_btn.text() == tr("cv_import.apply")
    assert dlg.mode_replace.text() == tr("cv_import.mode_replace")
    assert dlg.mode_box.isVisible()
    assert dlg.empty_box.isVisible() is False
    assert dlg.preview.isVisible()
    text = dlg.preview.toPlainText()
    assert "Ada" in text
    assert f"({tr('cv_import.none')})" in text
    assert app.city == "Hamburg"
    assert app.first_name == "Manuell"
    assert dlg.result_quals is None
    dlg.close()
    qapp.processEvents()


def test_oom_preserves_inputs_and_does_not_auto_retry(qapp, tmp_path: Path):
    i18n.set_language("de")
    calls: list[int] = []
    cv = tmp_path / "cv.txt"

    def spawn(path: Path, out: Path):
        calls.append(1)
        _write(out, {"ok": False, "kind": "oom", "message": "MemoryError", "parsed": None})
        return _Proc(3)

    app = ApplicationProfile(city="Hamburg")
    dlg = CvImportDialog(
        cv,
        QualificationsConfig(),
        app,
        spawn=spawn,
        autostart=False,
    )
    dlg.show()
    qapp.processEvents()
    dlg.mode_merge.setChecked(True)
    dlg.start_parse()
    assert _pump(qapp, lambda: dlg._retry_btn.isVisible())
    assert calls == [1]
    assert dlg.attempt_count == 1
    assert dlg._last_kind == "oom"
    assert dlg._phase == "error"
    assert dlg.error_text.text() == tr("cv_import.error_oom")
    assert "MemoryError" in dlg.error_detail.text()
    assert cv.name in dlg.path_label.text()
    assert dlg.preview.isVisible() is False
    assert dlg.mode_box.isVisible() is False
    assert dlg.result_quals is None
    assert dlg.result_application is None
    assert app.city == "Hamburg"
    assert dlg.mode_merge.isChecked()
    assert dlg._ok_btn.isEnabled() is False
    assert dlg._ok_btn.isVisible() is False
    assert dlg._choose_btn.isVisible() is False
    time.sleep(0.2)
    qapp.processEvents()
    assert calls == [1]
    dlg._retry_btn.click()
    assert _pump(qapp, lambda: dlg.attempt_count == 2 and not dlg._running)
    assert calls == [1, 1]
    assert dlg.cv_path == cv
    assert cv.name in dlg.path_label.text()
    dlg.close()
    qapp.processEvents()


def test_timeout_is_manual_retry_only(qapp, tmp_path: Path):
    i18n.set_language("de")
    calls: list[int] = []

    def spawn(path: Path, out: Path):
        calls.append(1)
        return _Proc(None)

    dlg = CvImportDialog(
        tmp_path / "cv.txt",
        QualificationsConfig(),
        ApplicationProfile(city="Hamburg"),
        spawn=spawn,
        timeout_s=0.05,
        autostart=False,
    )
    dlg.show()
    qapp.processEvents()
    dlg.start_parse()
    assert _pump(qapp, lambda: dlg._last_kind == "timeout", timeout=3)
    assert calls == [1]
    assert dlg._phase == "error"
    assert dlg.error_text.text() == tr("cv_import.error_timeout")
    assert dlg._retry_btn.isVisible()
    assert dlg._retry_btn.text() == tr("cv_import.retry")
    assert dlg._ok_btn.isVisible() is False
    assert "cv.txt" in dlg.path_label.text()
    assert dlg.result_application is None
    time.sleep(0.15)
    qapp.processEvents()
    assert calls == [1]
    dlg.close()
    qapp.processEvents()


def test_cancel_stops_the_worker_without_a_second_launch(qapp, tmp_path: Path):
    i18n.set_language("de")
    calls: list[int] = []
    procs: list[_Proc] = []

    def spawn(path: Path, out: Path):
        calls.append(1)
        proc = _Proc(None)
        procs.append(proc)
        return proc

    dlg = CvImportDialog(
        tmp_path / "cv.txt",
        QualificationsConfig(),
        ApplicationProfile(city="Hamburg"),
        spawn=spawn,
        timeout_s=30,
        autostart=False,
    )
    dlg.show()
    qapp.processEvents()
    dlg.start_parse()
    assert _pump(qapp, lambda: bool(calls) and dlg._running and dlg.progress.isVisible())
    cancel = dlg._buttons.button(QDialogButtonBox.StandardButton.Cancel)
    cancel.click()
    assert dlg.isVisible()
    assert dlg._phase == "cancelled"
    assert dlg.status_label.text() == i18n.t("cv_import.cancelled")
    assert dlg._cancelled_banner.isVisible()
    assert dlg._cancelled_banner.text() == "Einlesen abgebrochen. Es wurde nichts übernommen."
    assert dlg.cancel_text.text() == tr("cv_import.cancelled")
    assert dlg.preview.toPlainText() == i18n.t("cv_import.cancelled")
    assert "cv.txt" in dlg.path_label.text()
    assert dlg._ok_btn.isEnabled() is False
    assert dlg._ok_btn.isVisible() is False
    assert dlg._retry_btn.isVisible() is False
    assert dlg._cancel_btn.text() == i18n.t("cv_import.close")
    # A second signal in the same click must not dismiss the dialog.
    cancel.click()
    dlg.reject()
    assert dlg.isVisible()
    assert _pump(qapp, lambda: dlg._last_kind == "cancelled" and not dlg._running, timeout=3)
    assert calls == [1]
    assert procs[0].terminated
    assert dlg.isVisible()
    assert dlg.status_label.text() == i18n.t("cv_import.cancelled")
    assert dlg.preview.toPlainText() == i18n.t("cv_import.cancelled")
    assert dlg.progress.isVisible() is False
    assert dlg.result_quals is None
    assert dlg.result_application is None
    assert dlg._read_again_btn.isVisible()
    assert dlg._read_again_btn.text() == tr("cv_import.read_again")
    assert _pump(qapp, lambda: not dlg._should_keep_open(), timeout=3)
    cancel.click()
    qapp.processEvents()
    assert dlg.isVisible() is False


def test_read_error_has_manual_retry_cta_and_does_not_auto_start(qapp, tmp_path: Path):
    i18n.set_language("de")
    calls: list[int] = []

    def spawn(path: Path, out: Path):
        calls.append(1)
        _write(out, {"ok": False, "kind": "error", "message": "broken", "parsed": None})
        return _Proc(1)

    app = ApplicationProfile(city="Hamburg")
    cv = tmp_path / "cv.txt"
    dlg = CvImportDialog(cv, QualificationsConfig(), app, spawn=spawn, autostart=False)
    dlg.show()
    qapp.processEvents()
    dlg.start_parse()
    assert _pump(qapp, lambda: dlg._retry_btn.isVisible() and dlg.error_box.isVisible())
    assert calls == [1]
    assert dlg._phase == "error"
    assert dlg.error_text.text() == tr("cv_import.error_generic")
    assert dlg.error_detail.text() == "broken"
    assert dlg.error_detail.textInteractionFlags() & Qt.TextInteractionFlag.TextSelectableByMouse
    assert dlg.preview.isVisible() is False
    assert dlg.mode_box.isVisible() is False
    assert cv.name in dlg.path_label.text()
    assert dlg._ok_btn.isEnabled() is False
    assert dlg._ok_btn.isVisible() is False
    assert app.city == "Hamburg"
    time.sleep(0.15)
    qapp.processEvents()
    assert calls == [1]
    dlg._retry_btn.click()
    assert _pump(qapp, lambda: dlg.attempt_count == 2 and not dlg._running)
    assert calls == [1, 1]
    assert dlg.cv_path == cv
    time.sleep(0.15)
    qapp.processEvents()
    assert calls == [1, 1]
    dlg.close()
    qapp.processEvents()


def _empty_parsed(path: Path) -> dict:
    parsed = _parsed(path)
    parsed["personal"] = {}
    parsed["emails"] = []
    parsed["phones"] = []
    parsed["confidence"] = {}
    parsed["uncertain_items"] = ["unklar, zählt nicht als Inhalt"]
    return parsed


def test_empty_detection_is_its_own_surface_and_close_applies_nothing(qapp, tmp_path: Path):
    i18n.set_language("de")
    cv = tmp_path / "leer.pdf"

    def spawn(path: Path, out: Path):
        _write(out, {"ok": True, "kind": "ok", "parsed": _empty_parsed(path), "message": ""})
        return _Proc(0)

    app = ApplicationProfile(city="Hamburg", first_name="Manuell")
    dlg = CvImportDialog(cv, QualificationsConfig(), app, spawn=spawn, autostart=False)
    dlg.show()
    qapp.processEvents()
    dlg.start_parse()
    assert _pump(qapp, lambda: dlg._last_kind == "empty")
    assert dlg._phase == "empty"
    assert dlg.empty_box.isVisible()
    assert dlg.empty_title.text() == tr("cv_import.empty_title")
    assert dlg.empty_body.text() == tr("cv_import.empty_body")
    assert dlg._choose_btn.isVisible()
    assert dlg._choose_btn.text() == tr("cv_import.choose_other")
    assert dlg._retry_btn.isVisible() is False
    assert dlg._ok_btn.isVisible() is False
    assert dlg.preview.isVisible() is False
    assert dlg.mode_box.isVisible() is False
    assert cv.name in dlg.path_label.text()
    assert dlg.result_quals is None
    assert app.city == "Hamburg"
    assert app.first_name == "Manuell"
    close = dlg._buttons.button(QDialogButtonBox.StandardButton.Cancel)
    assert close is not None
    assert close.text() == tr("cv_import.close")
    close.click()
    qapp.processEvents()
    assert dlg.result() == dlg.DialogCode.Rejected
    assert dlg.isVisible() is False
    assert app.city == "Hamburg"
    assert app.first_name == "Manuell"


def test_empty_file_picker_cancel_keeps_the_path(qapp, tmp_path: Path):
    cv = tmp_path / "leer.pdf"

    def spawn(path: Path, out: Path):
        _write(out, {"ok": True, "kind": "ok", "parsed": _empty_parsed(path), "message": ""})
        return _Proc(0)

    dlg = CvImportDialog(cv, QualificationsConfig(), ApplicationProfile(), spawn=spawn, autostart=False)
    dlg.show()
    qapp.processEvents()
    dlg.start_parse()
    assert _pump(qapp, lambda: dlg._phase == "empty")
    dlg._pick_other_file = lambda: ""  # type: ignore[method-assign]
    dlg._choose_btn.click()
    qapp.processEvents()
    assert dlg._phase == "empty"
    assert dlg.attempt_count == 1
    assert dlg.cv_path == cv
    assert cv.name in dlg.path_label.text()
    dlg.close()
    qapp.processEvents()


def test_empty_choose_other_file_parses_that_path_once(qapp, tmp_path: Path):
    seen: list[str] = []
    other = tmp_path / "andere.pdf"
    other.write_text("x", encoding="utf-8")

    def spawn(path: Path, out: Path):
        seen.append(path.name)
        if path.name == other.name:
            _write(out, {"ok": True, "kind": "ok", "parsed": _parsed(path), "message": ""})
        else:
            _write(out, {"ok": True, "kind": "ok", "parsed": _empty_parsed(path), "message": ""})
        return _Proc(0)

    dlg = CvImportDialog(
        tmp_path / "leer.pdf",
        QualificationsConfig(),
        ApplicationProfile(),
        spawn=spawn,
        autostart=False,
    )
    dlg.show()
    qapp.processEvents()
    dlg.start_parse()
    assert _pump(qapp, lambda: dlg._phase == "empty")
    assert seen == ["leer.pdf"]
    dlg._pick_other_file = lambda: str(other)  # type: ignore[method-assign]
    dlg._choose_btn.click()
    assert _pump(qapp, lambda: dlg._phase == "success" and dlg.attempt_count == 2)
    assert seen == ["leer.pdf", "andere.pdf"]
    assert dlg.cv_path == other
    assert other.name in dlg.path_label.text()
    time.sleep(0.15)
    qapp.processEvents()
    assert seen == ["leer.pdf", "andere.pdf"]
    dlg.close()
    qapp.processEvents()


def test_partial_detection_stays_in_the_preview(qapp, tmp_path: Path):
    i18n.set_language("de")

    def spawn(path: Path, out: Path):
        parsed = _empty_parsed(path)
        parsed["skills"] = ["Python"]
        _write(out, {"ok": True, "kind": "ok", "parsed": parsed, "message": ""})
        return _Proc(0)

    dlg = CvImportDialog(
        tmp_path / "teil.pdf",
        QualificationsConfig(),
        ApplicationProfile(),
        spawn=spawn,
        autostart=False,
    )
    dlg.show()
    qapp.processEvents()
    dlg.start_parse()
    assert _pump(qapp, lambda: dlg._phase == "success")
    assert dlg.empty_box.isVisible() is False
    assert dlg.preview.isVisible()
    text = dlg.preview.toPlainText()
    assert "Python" in text
    assert f"({tr('cv_import.none')})" in text
    assert dlg._ok_btn.isVisible()
    dlg.close()
    qapp.processEvents()


def test_cancel_read_again_starts_one_manual_run(qapp, tmp_path: Path):
    calls: list[int] = []

    def spawn(path: Path, out: Path):
        calls.append(1)
        if len(calls) == 1:
            return _Proc(None)
        _write(out, {"ok": True, "kind": "ok", "parsed": _parsed(path), "message": ""})
        return _Proc(0)

    dlg = CvImportDialog(
        tmp_path / "cv.txt",
        QualificationsConfig(),
        ApplicationProfile(),
        spawn=spawn,
        timeout_s=30,
        autostart=False,
    )
    dlg.show()
    qapp.processEvents()
    dlg.start_parse()
    assert _pump(qapp, lambda: dlg._running and bool(calls))
    cancel = dlg._buttons.button(QDialogButtonBox.StandardButton.Cancel)
    assert cancel is not None
    cancel.click()
    assert _pump(qapp, lambda: dlg._phase == "cancelled" and not dlg._running, timeout=3)
    assert calls == [1]
    dlg._read_again_btn.click()
    assert _pump(qapp, lambda: dlg.attempt_count == 2 and dlg._phase == "success")
    assert calls == [1, 1]
    time.sleep(0.15)
    qapp.processEvents()
    assert calls == [1, 1]
    dlg.close()
    qapp.processEvents()


def test_qa_observe_seconds_defaults_off(monkeypatch):
    monkeypatch.delenv("KARRIEREKRAKE_CV_IMPORT_OBSERVE_S", raising=False)
    assert qa_observe_seconds() == 0.0
    monkeypatch.setenv("KARRIEREKRAKE_CV_IMPORT_OBSERVE_S", "")
    assert qa_observe_seconds() == 0.0
    monkeypatch.setenv("KARRIEREKRAKE_CV_IMPORT_OBSERVE_S", "nope")
    assert qa_observe_seconds() == 0.0
    monkeypatch.setenv("KARRIEREKRAKE_CV_IMPORT_OBSERVE_S", "-3")
    assert qa_observe_seconds() == 0.0
    monkeypatch.setenv("KARRIEREKRAKE_CV_IMPORT_OBSERVE_S", "1.5")
    assert qa_observe_seconds() == 1.5
    monkeypatch.setenv("KARRIEREKRAKE_CV_IMPORT_OBSERVE_S", "999")
    assert qa_observe_seconds() == 120.0


def test_supervisor_observe_cancel_skips_spawn(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("KARRIEREKRAKE_CV_IMPORT_OBSERVE_S", "30")
    calls: list[int] = []

    def spawn(path: Path, out: Path):
        calls.append(1)
        return _Proc(0)

    sup = CvImportSupervisor(tmp_path / "cv.txt", spawn=spawn, timeout_s=2)

    def cancel_soon() -> None:
        time.sleep(0.12)
        sup.request_cancel()

    threading.Thread(target=cancel_soon, daemon=True).start()
    started = time.monotonic()
    result = sup.run_once()
    assert result.kind == "cancelled"
    assert result.attempts == 1
    assert calls == []
    assert time.monotonic() - started < 5


def test_supervisor_observe_delays_spawn(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("KARRIEREKRAKE_CV_IMPORT_OBSERVE_S", "0.35")
    calls: list[float] = []

    def spawn(path: Path, out: Path):
        calls.append(time.monotonic())
        _write(out, {"ok": False, "kind": "error", "message": "stop", "parsed": None})
        return _Proc(1)

    sup = CvImportSupervisor(tmp_path / "cv.txt", spawn=spawn, timeout_s=2)
    started = time.monotonic()
    result = sup.run_once()
    assert result.kind == "error"
    assert calls and calls[0] - started >= 0.3


def test_qa_observe_shows_progress_then_cancel_before_result(qapp, tmp_path: Path, monkeypatch):
    monkeypatch.setenv("KARRIEREKRAKE_CV_IMPORT_OBSERVE_S", "4")
    i18n.set_language("de")
    calls: list[int] = []
    cv = tmp_path / "cv.txt"
    cv.write_text("Ada\n", encoding="utf-8")

    def spawn(path: Path, out: Path):
        calls.append(1)
        _write(out, {"ok": True, "kind": "ok", "parsed": _parsed(path), "message": ""})
        return _Proc(0)

    app = ApplicationProfile(city="Hamburg", first_name="Manuell")
    dlg = CvImportDialog(cv, QualificationsConfig(), app, spawn=spawn, autostart=False)
    dlg.show()
    qapp.processEvents()
    dlg.start_parse()
    assert _pump(
        qapp,
        lambda: dlg.progress.isVisible() and dlg._running and dlg.status_label.text() == i18n.t("cv_import.progress"),
        timeout=2,
    )
    assert calls == []
    assert dlg.incoming is None
    assert "Ada" not in dlg.preview.toPlainText()
    cancel = dlg._cancel_btn
    assert cancel.isEnabled()
    cancel.click()
    assert dlg.isVisible()
    assert dlg.status_label.text() == i18n.t("cv_import.cancelled")
    assert dlg._cancelled_banner.isVisible()
    assert dlg._cancelled_banner.text() == "Einlesen abgebrochen. Es wurde nichts übernommen."
    assert dlg.preview.toPlainText() == i18n.t("cv_import.cancelled")
    assert dlg._ok_btn.isEnabled() is False
    assert dlg._cancel_btn.text() == i18n.t("cv_import.close")
    cancel.click()
    dlg.reject()
    qapp.processEvents()
    assert dlg.isVisible()
    assert _pump(qapp, lambda: dlg._last_kind == "cancelled" and not dlg._running, timeout=3)
    assert calls == []
    assert dlg.isVisible()
    assert dlg.status_label.text() == i18n.t("cv_import.cancelled")
    assert dlg._cancel_btn.text() == i18n.t("cv_import.close")
    assert dlg.preview.toPlainText() == i18n.t("cv_import.cancelled")
    assert "Ada" not in dlg.preview.toPlainText()
    assert dlg._ok_btn.isEnabled() is False
    assert dlg.result_quals is None
    assert app.city == "Hamburg"
    assert app.first_name == "Manuell"
    assert _pump(qapp, lambda: not dlg._should_keep_open(), timeout=3)
    cancel.click()
    qapp.processEvents()
    assert dlg.isVisible() is False


def test_cancel_after_ready_still_closes(qapp, tmp_path: Path):
    i18n.set_language("de")

    def spawn(path: Path, out: Path):
        _write(out, {"ok": True, "kind": "ok", "parsed": _parsed(path), "message": ""})
        return _Proc(0)

    dlg = CvImportDialog(tmp_path / "cv.txt", QualificationsConfig(), ApplicationProfile(), spawn=spawn, autostart=False)
    dlg.show()
    qapp.processEvents()
    dlg.start_parse()
    assert _pump(qapp, lambda: dlg._ok_btn.isEnabled() and not dlg._running)
    assert dlg._cancelled_banner.isVisible() is False
    dlg._cancel_btn.click()
    qapp.processEvents()
    assert dlg.isVisible() is False


def test_supervisor_run_once_does_not_loop_on_oom(tmp_path: Path):
    calls: list[int] = []

    def spawn(path: Path, out: Path):
        calls.append(threading.get_ident())
        _write(out, {"ok": False, "kind": "oom", "message": "MemoryError", "parsed": None})
        return _Proc(3)

    sup = CvImportSupervisor(tmp_path / "cv.txt", spawn=spawn, timeout_s=2)
    result = sup.run_once()
    assert result.kind == "oom"
    assert result.attempts == 1
    assert result.ok is False
    assert calls and calls[0] == threading.get_ident()
    assert len(calls) == 1
