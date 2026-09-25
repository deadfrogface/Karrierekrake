#!/usr/bin/env python3
"""Phase-2 desktop/CV performance baseline (offscreen).

Measures real call paths without claiming a full GUI UX study.
Writes JSON under artifacts/perf_phase2/.
"""

from __future__ import annotations

import json
import os
import resource
import sys
import time
import tracemalloc
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
OUT = ROOT / "artifacts" / "perf_phase2"
OUT.mkdir(parents=True, exist_ok=True)


def _rss_mb() -> float:
    # Linux: ru_maxrss is KiB
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def measure_app_startup() -> dict:
    t0 = time.perf_counter()
    from PySide6.QtWidgets import QApplication
    from desktop.services import ConfigService
    from desktop.main_window import MainWindow

    app = QApplication.instance() or QApplication(sys.argv)
    t_app = time.perf_counter()
    cfg = ConfigService()
    t_cfg = time.perf_counter()
    win = MainWindow(cfg)
    t_win = time.perf_counter()
    # Navigate pages if stack exists
    nav_times = {}
    page_attrs = [
        ("dashboard", "dashboard"),
        ("profile", "profile"),
        ("jobs", "jobs"),
        ("search", "search"),
        ("settings", "settings"),
        ("applications", "applications"),
        ("inbox", "inbox"),
        ("logs", "logs"),
    ]
    for name, attr in page_attrs:
        page = getattr(win, attr, None) or getattr(win, name, None)
        if page is not None and hasattr(win, "stack"):
            s = time.perf_counter()
            try:
                win.stack.setCurrentWidget(page)
                # Process events so layout/paint cost is included
                app.processEvents()
                nav_times[name] = round(time.perf_counter() - s, 4)
            except Exception as exc:  # noqa: BLE001
                nav_times[name] = f"err:{type(exc).__name__}"
    t_nav = time.perf_counter()
    win.close()
    return {
        "qapplication_s": round(t_app - t0, 4),
        "config_service_s": round(t_cfg - t_app, 4),
        "mainwindow_s": round(t_win - t_cfg, 4),
        "navigation_s": round(t_nav - t_win, 4),
        "total_startup_s": round(t_win - t0, 4),
        "nav_page_s": nav_times,
        "peak_rss_mb": round(_rss_mb(), 1),
    }


def measure_cv_import_breakdown(pdf: Path) -> dict:
    from core.cv_docpick_import import extract_cv_text, import_cv_docpick, _llm_extract

    out: dict = {"pdf": str(pdf.relative_to(ROOT)), "exists": pdf.is_file()}
    if not pdf.is_file():
        return out
    # Docling
    t0 = time.perf_counter()
    rss0 = _rss_mb()
    text = extract_cv_text(pdf)
    out["docling_s"] = round(time.perf_counter() - t0, 3)
    out["docling_rss_delta_mb"] = round(_rss_mb() - rss0, 1)
    out["text_chars"] = len(text)
    # LLM (reuse warm server if up)
    t1 = time.perf_counter()
    try:
        raw = _llm_extract(text)
        out["llm_s"] = round(time.perf_counter() - t1, 3)
        out["llm_ok"] = True
        out["llm_keys"] = sorted(raw.keys())[:20]
    except Exception as exc:  # noqa: BLE001
        out["llm_s"] = round(time.perf_counter() - t1, 3)
        out["llm_ok"] = False
        out["llm_error"] = f"{type(exc).__name__}: {exc}"
    # Full import (includes mapping)
    t2 = time.perf_counter()
    try:
        parsed = import_cv_docpick(pdf)
        out["full_import_s"] = round(time.perf_counter() - t2, 3)
        out["pipeline"] = parsed.get("pipeline")
        out["phi_extract_call_count"] = parsed.get("phi_extract_call_count")
    except Exception as exc:  # noqa: BLE001
        out["full_import_s"] = round(time.perf_counter() - t2, 3)
        out["full_import_error"] = f"{type(exc).__name__}: {exc}"
    out["peak_rss_mb"] = round(_rss_mb(), 1)
    return out


def measure_cv_dialog_ui_responsiveness(pdf: Path) -> dict:
    """Prove dialog opens without waiting for Docpick (async worker).

    Does not start a real LLM import — that would contend with timed breakdowns.
    """
    from PySide6.QtWidgets import QApplication
    from core.config import ApplicationProfile, QualificationsConfig
    import desktop.widgets.cv_import_dialog as dlg_mod

    app = QApplication.instance() or QApplication(sys.argv)

    def _noop_start(self) -> None:  # noqa: ANN001
        # Leave OK disabled; simulate "still extracting" UI state.
        self.status_label.setText("extracting (mocked)")

    original = dlg_mod.CvImportDialog._start_extract
    dlg_mod.CvImportDialog._start_extract = _noop_start  # type: ignore[method-assign]
    try:
        t0 = time.perf_counter()
        dlg = dlg_mod.CvImportDialog(pdf, QualificationsConfig(), ApplicationProfile())
        t_shown = time.perf_counter()
        ok_enabled_at_show = bool(dlg.ok_btn.isEnabled())
        for _ in range(20):
            app.processEvents()
            time.sleep(0.01)
        t_pump = time.perf_counter()
        dlg.close()
    finally:
        dlg_mod.CvImportDialog._start_extract = original  # type: ignore[method-assign]
    return {
        "dialog_ctor_s": round(t_shown - t0, 4),
        "ok_enabled_at_show": ok_enabled_at_show,
        "event_pump_0_2s_wall_s": round(t_pump - t_shown, 4),
        "note": "ctor must stay << full import; OK disabled until extract finishes",
    }


def main() -> int:
    tracemalloc.start()
    report = {
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "note": (
            "Offscreen baseline. Productive CV dialog uses QThread (async); "
            "this script measures Docling/LLM wall time separately from UI."
        ),
    }
    print("Measuring app startup…", flush=True)
    report["startup"] = measure_app_startup()
    print(json.dumps(report["startup"], indent=2), flush=True)

    pdf = ROOT / "tests/fixtures/cv_corpus/DE_01_Klassisch.pdf"
    print("Measuring CV dialog UI responsiveness (async)…", flush=True)
    report["cv_dialog_ui"] = measure_cv_dialog_ui_responsiveness(pdf)
    print(json.dumps(report["cv_dialog_ui"], indent=2), flush=True)

    print("Measuring CV import breakdown (cold-ish Docling, warm LLM if server up)…", flush=True)
    report["cv_import_first"] = measure_cv_import_breakdown(pdf)
    print(json.dumps(report["cv_import_first"], indent=2), flush=True)
    print("Measuring CV import follow-up…", flush=True)
    report["cv_import_followup"] = measure_cv_import_breakdown(pdf)
    print(json.dumps(report["cv_import_followup"], indent=2), flush=True)

    current, peak = tracemalloc.get_traced_memory()
    report["tracemalloc_peak_mb"] = round(peak / (1024 * 1024), 1)
    out = OUT / "BASELINE.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
