"""Non-blocking inference jobs with cancel + idle unload."""

from __future__ import annotations

import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable

from guenther.privacy import log_event
from guenther.provider import GenerationRequest, GenerationResult, LocalAIProvider, ProviderStatus


@dataclass
class InferenceJob:
    future: Future
    cancel_event: threading.Event
    started_at: float
    capability: str


class InferenceController:
    """Runs generate() off the UI thread; supports cancel and idle unload."""

    def __init__(
        self,
        provider: LocalAIProvider,
        *,
        max_workers: int = 1,
        idle_unload_s: float = 180.0,
        ram_tight: bool = False,
    ) -> None:
        self.provider = provider
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="guenther")
        self._lock = threading.Lock()
        self._jobs: list[InferenceJob] = []
        self._last_used = time.monotonic()
        self.idle_unload_s = 60.0 if ram_tight else idle_unload_s
        self._watch: threading.Thread | None = None
        self._watch_stop = threading.Event()
        # Start idle watcher lazily on first submit — avoids native crashes when
        # GuentherService is constructed in short-lived pytest processes.

    def _ensure_watch(self) -> None:
        if self._watch is not None and self._watch.is_alive():
            return
        self._watch_stop.clear()
        self._watch = threading.Thread(target=self._idle_watch, daemon=True, name="guenther-idle")
        self._watch.start()

    def submit(self, request: GenerationRequest, *, capability: str = "") -> InferenceJob:
        self._ensure_watch()
        cancel_event = threading.Event()
        orig = request.cancel_check

        def _cancel() -> bool:
            if cancel_event.is_set():
                return True
            return bool(orig and orig())

        request.cancel_check = _cancel

        def _run() -> GenerationResult:
            self._last_used = time.monotonic()
            return self.provider.generate(request)

        fut = self._pool.submit(_run)
        job = InferenceJob(future=fut, cancel_event=cancel_event, started_at=time.monotonic(), capability=capability)
        with self._lock:
            self._jobs.append(job)
        return job

    def cancel(self, job: InferenceJob) -> None:
        job.cancel_event.set()
        log_event("inference_cancel", capability=job.capability)

    def shutdown(self) -> None:
        self._watch_stop.set()
        watch = self._watch
        if watch is not None and watch.is_alive() and watch is not threading.current_thread():
            watch.join(timeout=2.0)
        self._watch = None
        self.provider.unload_model()
        self._pool.shutdown(wait=False, cancel_futures=True)

    def _idle_watch(self) -> None:
        while not self._watch_stop.wait(15.0):
            if time.monotonic() - self._last_used >= self.idle_unload_s:
                if self.provider.status() == ProviderStatus.READY:
                    self.provider.unload_model()
                    log_event("idle_unload")
