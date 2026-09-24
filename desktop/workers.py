"""Background workers so the GUI never freezes."""

from __future__ import annotations

import threading

from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot

from core.config import AppConfig
from desktop.services.browser_install import check_browser, repair_browser
from desktop.services.shutdown import get_shutdown_manager

# playwright / jobspy / app.main stay lazy — imported inside PipelineWorker.run only


class PipelineWorker(QObject):
    progress = Signal(str)
    finished = Signal(dict)
    failed = Signal(str)

    def __init__(self, config: AppConfig, mode: str | None = None) -> None:
        super().__init__()
        self.config = config
        self.mode = mode
        self._cancel = threading.Event()
        self._pause = threading.Event()

    def request_cancel(self) -> None:
        self._cancel.set()
        try:
            from app.main import cancel_active_searches

            cancel_active_searches()
        except Exception:
            pass

    def set_paused(self, paused: bool) -> None:
        """Mid-run pause: stop further search/apply work (fail-closed)."""
        if paused:
            self._pause.set()
        else:
            self._pause.clear()

    def run(self) -> None:
        try:
            # Lazy: avoids importing playwright/jobspy at desktop startup
            from app.main import run_pipeline

            stats = run_pipeline(
                self.config,
                mode=self.mode,
                progress_callback=self.progress.emit,
                should_stop=lambda: self._cancel.is_set() or self._pause.is_set(),
                recover_interrupted=False,
            )
            if self._cancel.is_set():
                self.progress.emit("Abgebrochen.")
            elif self._pause.is_set():
                stats = dict(stats or {})
                stats["paused"] = True
                stats["cancelled"] = True
                self.progress.emit("Pausiert.")
            self.finished.emit(stats or {})
        except Exception as exc:  # noqa: BLE001 — surface user-friendly via failed
            self.failed.emit(str(exc))


class BrowserCheckWorker(QObject):
    finished = Signal(bool, str)

    def __init__(self) -> None:
        super().__init__()
        self._cancel = threading.Event()

    def request_cancel(self) -> None:
        self._cancel.set()

    def run(self) -> None:
        if self._cancel.is_set():
            self.finished.emit(False, "Abgebrochen.")
            return
        ok, msg = check_browser()
        self.finished.emit(ok, msg)


class BrowserRepairWorker(QObject):
    finished = Signal(bool, str)

    def __init__(self) -> None:
        super().__init__()
        self._cancel = threading.Event()

    def request_cancel(self) -> None:
        self._cancel.set()

    def run(self) -> None:
        if self._cancel.is_set():
            self.finished.emit(False, "Abgebrochen.")
            return
        ok, msg = repair_browser()
        self.finished.emit(ok, msg)


# Backwards-compatible alias
BrowserInstallWorker = BrowserRepairWorker


class _GuiDispatchHub(QObject):
    """GUI-thread receiver: QueuedConnection to @Slot has real thread affinity.

    Bare Python callables connected with QueuedConnection alone have *no* receiver
    QObject, so PySide6 may still invoke them on the emitter (worker) thread.
    """

    invoke = Signal(object)  # zero-arg callable

    def __init__(self) -> None:
        super().__init__()
        self._forwards: list = []
        self.invoke.connect(self._execute, Qt.ConnectionType.QueuedConnection)

    @Slot(object)
    def _execute(self, fn: object) -> None:
        if callable(fn):
            fn()


_gui_hub: _GuiDispatchHub | None = None


def _dispatch_hub() -> _GuiDispatchHub:
    """Return a process-wide hub living on the GUI (QApplication) thread."""
    global _gui_hub
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if _gui_hub is None:
        _gui_hub = _GuiDispatchHub()
        if app is not None:
            _gui_hub.moveToThread(app.thread())
    elif app is not None and _gui_hub.thread() is not app.thread():
        _gui_hub.moveToThread(app.thread())
    return _gui_hub


def thread_is_running(thread: QThread | None) -> bool:
    """True if *thread* is a live, running QThread (never raises on deleted C++)."""
    if thread is None:
        return False
    try:
        return bool(thread.isRunning())
    except RuntimeError:
        # C++ QThread already destroyed (e.g. after deleteLater).
        return False


def connect_queued(signal, slot) -> None:
    """Always deliver *slot* on the GUI thread.

    Uses a GUI-affinity QObject hub (signal→@Slot) so plain callables and nested
    functions cannot run on the worker/emitter thread.
    """
    hub = _dispatch_hub()

    def _forward(*args, **kwargs) -> None:
        # May run on the emitter thread — only package work for the hub.
        captured_args = args
        captured_kwargs = kwargs
        hub.invoke.emit(lambda: slot(*captured_args, **captured_kwargs))

    hub._forwards.append(_forward)
    signal.connect(_forward)


def start_worker(worker: QObject, slot_name: str = "run") -> QThread:
    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(getattr(worker, slot_name))
    worker.finished.connect(thread.quit)
    if hasattr(worker, "failed"):
        worker.failed.connect(thread.quit)

    mgr = get_shutdown_manager()
    mgr.register_thread(thread)
    mgr.register_worker(worker)

    def _unregister() -> None:
        # Avoid double-ownership: do not call methods on this thread from shutdown
        # after it has finished. deleteLater only after unregister.
        with mgr._lock:
            if thread in mgr._threads:
                mgr._threads.remove(thread)
            if worker in mgr._workers:
                mgr._workers.remove(worker)
        try:
            worker.deleteLater()
        except RuntimeError:
            pass
        try:
            thread.deleteLater()
        except RuntimeError:
            pass

    thread.finished.connect(_unregister)
    thread.start()
    return thread
