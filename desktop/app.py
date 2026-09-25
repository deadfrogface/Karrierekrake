"""Desktop application bootstrap."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Early frozen diagnostics (before Qt) — opt-in only.
if getattr(sys, "frozen", False) and os.environ.get("KARRIEREKRAKE_BOOT_DIAG", "").strip() in {
    "1",
    "true",
    "yes",
}:
    try:
        _diag = Path(os.environ.get("LOCALAPPDATA") or ".") / "Karrierekrake" / "logs"
        _diag.mkdir(parents=True, exist_ok=True)
        (_diag / "boot.log").write_text(
            f"boot frozen exe={sys.executable} argv={sys.argv}\n",
            encoding="utf-8",
        )
    except Exception:
        pass

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# High-DPI before QApplication
os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")

# Windows AppUserModelID — stable taskbar/pin identity matching branded EXE icon.
if sys.platform == "win32":
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(  # type: ignore[attr-defined]
            "Karrierekrake.Desktop.1"
        )
    except Exception:
        pass

# Packaged Chromium path before any Playwright import (configure only — no playwright import)
try:
    from desktop.services.browser_install import configure_playwright_browsers_path

    configure_playwright_browsers_path()
except Exception:
    pass

from PySide6.QtCore import QSharedMemory, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from desktop.branding import (
    DATA_DIR_NAME,
    DISPLAY_NAME,
    LOCAL_SERVER_NAME,
    SINGLE_INSTANCE_KEY,
)
from desktop.i18n import i18n, install_qt_translator
from desktop.main_window import MainWindow
from desktop.services import ConfigService
from desktop.theme import apply_theme

_INSTANCE_KEY = SINGLE_INSTANCE_KEY
_INSTANCE_SERVER = LOCAL_SERVER_NAME


def acquire_single_instance_lock() -> QSharedMemory | None:
    """Create the single-instance shared-memory lock.

    Returns the lock object on success, or ``None`` if another live instance
    already holds it (caller should notify/focus and exit).
    """
    shared = QSharedMemory(_INSTANCE_KEY)
    if shared.attach():
        if _try_notify_existing_instance():
            return None
        # Stale segment after crash — reclaim
        shared.detach()
    if not shared.create(1):
        return None
    return shared


def apply_appearance(app: QApplication, config_service: ConfigService) -> None:
    cfg = config_service.load()
    lang = (cfg.settings.language or "de").lower()
    if lang not in {"de", "en"}:
        lang = "de"
    i18n.set_language(lang)
    install_qt_translator(app, lang)
    theme_pref = cfg.settings.theme or "system"
    high_contrast = bool(getattr(cfg.settings, "high_contrast", False))
    apply_theme(app, theme_pref, high_contrast=high_contrast)


def _try_notify_existing_instance() -> bool:
    """Return True if another instance accepted the raise signal."""
    socket = QLocalSocket()
    socket.connectToServer(_INSTANCE_SERVER)
    if not socket.waitForConnected(400):
        return False
    socket.write(b"raise\n")
    socket.flush()
    socket.waitForBytesWritten(400)
    socket.disconnectFromServer()
    return True


def run() -> int:
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName(DISPLAY_NAME)
    app.setOrganizationName(DATA_DIR_NAME)
    try:
        from desktop.tray import app_icon

        icon = app_icon()
        if icon is not None and not icon.isNull():
            app.setWindowIcon(icon)
    except Exception:
        pass
    # Quit when the last window closes unless the user opted into tray-minimize.
    # Tray exit / red-X exit always call ApplicationShutdownManager → app.quit().
    app.setQuitOnLastWindowClosed(True)

    # Single-instance lock (QSharedMemory + QLocalServer for focus).
    shared = acquire_single_instance_lock()
    if shared is None:
        _try_notify_existing_instance()
        QMessageBox.warning(None, DISPLAY_NAME, f"{DISPLAY_NAME} läuft bereits.")
        return 1

    from desktop.services.shutdown import get_shutdown_manager
    from core.logging import setup_logging

    try:
        from desktop.paths import ensure_app_dirs

        _dirs = ensure_app_dirs()
        setup_logging(_dirs["logs"])
    except RecursionError:
        raise
    except Exception:
        _dirs = {}
        setup_logging()

    # Windowed EXE has no console — uncaught exceptions must hit the log file.
    import logging
    import traceback

    _prev_hook = sys.excepthook

    def _excepthook(exc_type, exc, tb) -> None:  # noqa: ANN001
        try:
            logging.getLogger("karrierekrake").error(
                "Uncaught exception:\n%s",
                "".join(traceback.format_exception(exc_type, exc, tb)),
            )
        except Exception:
            pass
        _prev_hook(exc_type, exc, tb)

    sys.excepthook = _excepthook

    shutdown = get_shutdown_manager()
    app.aboutToQuit.connect(lambda: shutdown.shutdown(reason="aboutToQuit"))

    config_service = ConfigService()
    apply_appearance(app, config_service)

    # One-shot crash recovery at app start (not on every GUI Database() open).
    try:
        from core.database import Database

        Database(config_service.load().db_path, recover=True)
    except RecursionError:
        raise
    except Exception:
        pass

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.warning(
            None,
            DISPLAY_NAME,
            "System tray is not available. The app can still be used.",
        )

    window = MainWindow(config_service)
    QLocalServer.removeServer(_INSTANCE_SERVER)
    server = QLocalServer(app)
    server.listen(_INSTANCE_SERVER)

    def _on_connection() -> None:
        conn = server.nextPendingConnection()
        if conn is None:
            return
        conn.waitForReadyRead(200)
        _ = conn.readAll()
        conn.disconnectFromServer()
        window.show()
        window.raise_()
        window.activateWindow()

    server.newConnection.connect(_on_connection)
    app._karrierekrake_shared = shared  # type: ignore[attr-defined]
    app._karrierekrake_server = server  # type: ignore[attr-defined]

    window.show()
    window.maybe_run_wizard()
    return app.exec()


def main() -> int:
    if os.environ.get("KARRIEREKRAKE_SMOKE_TEST", "").strip().lower() in {"1", "true", "yes"}:
        return _smoke_test()
    if "--smoke-test" in sys.argv:
        return _smoke_test()
    if "--smoke-browser" in sys.argv:
        return _smoke_browser()
    if "--smoke-cv-corpus" in sys.argv:
        return _smoke_cv_corpus()
    if "--once" in sys.argv:
        return _run_once_headless()
    return run()


def _run_once_headless() -> int:
    """Scheduler entrypoint: one pipeline pass using AppData config, no Qt UI.

    Takes the same single-instance lock as the GUI so Task Scheduler ``--once``
    cannot overlap a live desktop pipeline on the shared AppData DB/YAML.
    """
    from PySide6.QtCore import QCoreApplication

    from app.main import run_pipeline
    from desktop.services import ConfigService

    # QSharedMemory requires a QCoreApplication.
    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    shared = acquire_single_instance_lock()
    if shared is None:
        return 0
    try:
        cfg = ConfigService().load()
        if bool(getattr(cfg.settings, "automation_paused", False)):
            return 0
        run_pipeline(cfg)
        return 0
    finally:
        # Keep segment alive until process exit; detach explicitly for clarity.
        try:
            shared.detach()
        except Exception:
            pass
        _ = app


def _smoke_result_paths() -> list[Path]:
    """Marker files for packaged smoke (AppData first, then next to EXE).

    Windowed onefile bootloaders may return before the child finishes; CI must
    poll these markers (and a per-run token) instead of trusting process exit.
    Writing under LOCALAPPDATA isolates concurrent / overlapping smoke runs.
    """
    paths: list[Path] = []
    local = (os.environ.get("LOCALAPPDATA") or "").strip()
    if local:
        paths.append(Path(local) / DATA_DIR_NAME / "smoke_test_result.txt")
    try:
        paths.append(Path(sys.executable).resolve().parent / "smoke_test_result.txt")
    except Exception:
        pass
    # Deduplicate while preserving order
    seen: set[str] = set()
    out: list[Path] = []
    for p in paths:
        key = str(p)
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def _write_smoke_result(lines: list[str]) -> None:
    text = "\n".join(lines)
    for path in _smoke_result_paths():
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        except Exception:
            continue


def _smoke_test() -> int:
    """Packaged/CI smoke: offscreen Qt + MainWindow + DB schema, then exit 0.

    Uses LOCALAPPDATA from the environment when provided (isolated CI dirs).
    Never submits applications. Never touches a developer's real profile unless
    LOCALAPPDATA was left at the process default (CI must always override it).
    """
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    token = (os.environ.get("KARRIEREKRAKE_SMOKE_TOKEN") or "").strip()
    lines: list[str] = ["SMOKE_START"]
    if token:
        lines.append(f"token={token}")
    # Write early so CI can distinguish boot crash vs later failure.
    _write_smoke_result(lines)
    try:
        from PySide6.QtWidgets import QApplication

        from core.database import Database
        from desktop.i18n import i18n
        from desktop.main_window import MainWindow
        from desktop.services import ConfigService
        from desktop.theme import stylesheet_for

        app = QApplication.instance() or QApplication(sys.argv)
        cfg_service = ConfigService()
        cfg = cfg_service.load()
        i18n.set_language(cfg.settings.language or "de")
        app.setStyleSheet(stylesheet_for(cfg.settings.theme or "system"))

        db = Database(cfg.db_path)
        # Force schema init
        _ = db.dashboard_stats()
        with db.connection() as conn:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(jobs)")}
        if "run_id" not in cols:
            raise RuntimeError("jobs.run_id missing after init")

        window = MainWindow(cfg_service)
        # Navigate all pages
        for idx in range(window.stack.count()):
            window.stack.setCurrentIndex(idx)
            page = window.stack.widget(idx)
            if hasattr(page, "refresh"):
                try:
                    page.refresh()
                except RecursionError:
                    raise
                except Exception:
                    pass
            if hasattr(page, "load_from_config"):
                try:
                    page.load_from_config()
                except RecursionError:
                    raise
                except Exception:
                    pass
        # Theme / language smoke
        for theme in ("system", "light", "dark"):
            apply_theme(app, theme)
        for lang in ("en", "de"):
            i18n.set_language(lang)
            window.retranslate_ui()

        lines.append(f"db={cfg.db_path}")
        lines.append(f"pages={window.stack.count()}")
        lines.append("SMOKE_TEST_OK")
        _write_smoke_result(lines)
        print("\n".join(lines), flush=True)
        window.close()
        app.quit()
        return 0
    except Exception as exc:  # noqa: BLE001
        lines.append(f"FAIL: {exc}")
        _write_smoke_result(lines)
        print("\n".join(lines), flush=True)
        return 1


def _smoke_cv_corpus() -> int:
    """Headless packaged check: parse fictional corpus PDFs passed as argv paths."""
    from core.cv_parser import import_cv

    args = sys.argv[sys.argv.index("--smoke-cv-corpus") + 1 :]
    paths = [Path(a) for a in args if a and not a.startswith("--")]
    log_path = Path(sys.executable).resolve().parent / "smoke_cv_corpus_result.txt"
    lines: list[str] = []
    try:
        if not paths:
            lines.append("FAIL: no PDF paths given after --smoke-cv-corpus")
            log_path.write_text("\n".join(lines), encoding="utf-8")
            return 1
        for path in paths:
            if not path.is_file():
                lines.append(f"FAIL missing: {path}")
                log_path.write_text("\n".join(lines), encoding="utf-8")
                return 1
            parsed = import_cv(path)
            name = f"{(parsed.get('personal') or {}).get('first_name', '')} {(parsed.get('personal') or {}).get('last_name', '')}".strip()
            lines.append(
                f"OK {path.name} name={name!r} "
                f"langs={len(parsed.get('languages') or [])} "
                f"work={len(parsed.get('work_experience') or [])} "
                f"edu={len(parsed.get('education') or [])}"
            )
        lines.append("SMOKE_CV_CORPUS_OK")
        log_path.write_text("\n".join(lines), encoding="utf-8")
        print("\n".join(lines))
        return 0
    except Exception as exc:  # noqa: BLE001
        lines.append(f"FAIL: {exc}")
        try:
            log_path.write_text("\n".join(lines), encoding="utf-8")
        except Exception:
            pass
        print("\n".join(lines))
        return 1


def _smoke_browser() -> int:
    """Headless packaged check: detect Chromium and open about:blank."""
    import tempfile

    from desktop.services.browser_install import check_browser, configure_playwright_browsers_path
    from browser.browser_manager import BrowserManager

    log_path = Path(sys.executable).resolve().parent / "smoke_browser_result.txt"
    lines: list[str] = []
    try:
        configure_playwright_browsers_path()
        ok, msg = check_browser()
        lines.append(msg)
        if not ok:
            log_path.write_text("\n".join(lines), encoding="utf-8")
            return 1
        with tempfile.TemporaryDirectory() as tmp:
            mgr = BrowserManager(Path(tmp) / "profile", headless=True)
            try:
                page = mgr.get_page()
                page.goto("about:blank")
                lines.append(f"SMOKE_BROWSER_OK {page.url}")
            finally:
                mgr.close()
        log_path.write_text("\n".join(lines), encoding="utf-8")
        return 0
    except Exception as exc:  # noqa: BLE001
        lines.append(f"FAIL: {exc}")
        try:
            log_path.write_text("\n".join(lines), encoding="utf-8")
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
