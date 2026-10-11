"""Regression: QThread lifecycle + queued GUI updates (real EXE crash classes)."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6.QtCore")

from PySide6.QtCore import QObject, QThread, Signal  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from desktop.workers import connect_queued, thread_is_running  # noqa: E402


@pytest.fixture
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_thread_is_running_none() -> None:
    assert thread_is_running(None) is False


def test_thread_is_running_swallows_deleted_cpp_object() -> None:
    class Dead:
        def isRunning(self) -> bool:
            raise RuntimeError(
                "libshiboken: Internal C++ object (PySide6.QtCore.QThread) already deleted."
            )

    assert thread_is_running(Dead()) is False  # type: ignore[arg-type]


def test_thread_is_running_after_quit(qapp) -> None:
    thread = QThread()
    thread.start()
    thread.quit()
    assert thread.wait(5000)
    assert thread_is_running(thread) is False


def test_connect_queued_delivers_on_gui_thread(qapp) -> None:
    """Bare callable must run on GUI thread even when signal emits from QThread."""

    class Emitter(QObject):
        ping = Signal(str)

    class BackgroundEmitter(QObject):
        def __init__(self, emitter: Emitter) -> None:
            super().__init__()
            self._emitter = emitter

        def run(self) -> None:
            self._emitter.ping.emit("hello")

    emitter = Emitter()
    seen: list[tuple[str, QThread]] = []
    main_thread = QThread.currentThread()

    def slot(msg: str) -> None:
        seen.append((msg, QThread.currentThread()))

    connect_queued(emitter.ping, slot)

    worker = BackgroundEmitter(emitter)
    thread = QThread()
    worker.moveToThread(thread)
    # Keep emitter on the worker thread so emit originates off-GUI.
    emitter.moveToThread(thread)
    thread.started.connect(worker.run)
    thread.start()

    for _ in range(100):
        if seen:
            break
        qapp.processEvents()
        QThread.msleep(10)

    thread.quit()
    assert thread.wait(5000)

    assert seen, "queued slot was not invoked"
    assert seen[0][0] == "hello"
    assert seen[0][1] is main_thread, (
        f"slot ran on {seen[0][1]!r}, expected GUI thread {main_thread!r}"
    )


def test_spec_defaults_to_windowed_production_exe() -> None:
    import ast
    import re
    from pathlib import Path

    spec = Path("packaging/Karrierekrake.spec").read_text(encoding="utf-8")
    assert "KARRIEREKRAKE_FORCE_CONSOLE" in spec
    assert "KARRIEREKRAKE_CI_CONSOLE" not in spec
    assert "console=bool(os.environ.get" not in spec.replace(" ", "")

    match = re.search(
        r"console=\(os\.environ\.get\(\"KARRIEREKRAKE_FORCE_CONSOLE\",\s*\"\"\)\.strip\(\)\.lower\(\)\s+in\s+(\{[^}]+\})\)",
        spec,
    )
    assert match, "FORCE_CONSOLE must use explicit membership check, not bool(non-empty)"
    allowed = ast.literal_eval(match.group(1))
    assert allowed == {"1", "true", "yes"}


def test_queued_connection_releases_completed_sender_and_receiver(qapp):
    import gc
    import weakref
    from PySide6.QtCore import QObject, Signal

    class Sender(QObject):
        ping = Signal()

    class Receiver:
        def handle(self):
            pass

    sender = Sender()
    receiver = Receiver()
    retained = weakref.ref(receiver)
    connect_queued(sender.ping, receiver.handle)
    sender.ping.disconnect()
    del sender, receiver
    gc.collect()
    assert retained() is None, 'completed account tasks must not retain pages forever'
