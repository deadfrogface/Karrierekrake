"""One-click setup download with an offline recommendation and isolated probe."""
from __future__ import annotations

import re
import logging

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QFrame, QLabel, QPushButton, QProgressBar, QVBoxLayout

from desktop.i18n import tr
from desktop.workers import FunctionWorker, connect_queued, start_worker
from guenther.setup_models import (
    SETUP_MODEL_CATALOG, inspect_setup_device, install_recommended_model,
    selected_model_id, selected_model_path,
)


def model_failure_text(error):
    from guenther.model_manager import download_failure_code

    code = download_failure_code(error) if isinstance(error, OSError) else str(error)
    # ModelManager reports safe, fixed error codes via RuntimeError(message).
    # Never display arbitrary exception strings, URLs or filesystem paths.
    messages = {
        "connection_timeout": "timeout", "connection_interrupted": "interrupted",
        "dns_failed": "dns", "tls_failed": "tls",
        "insufficient_disk": "disk", "write_permission_denied": "permission",
        "checksum_mismatch": "checksum", "invalid_download_response": "response",
        "invalid_download_range": "response",
    }
    if "probe" in code:
        return tr("setup.model.probe_failed")
    if re.fullmatch(r"http_[1-5][0-9]{2}", code):
        return tr("setup.model.error.http", status=code[5:])
    if code in messages:
        return tr("setup.model.error." + messages[code])
    return tr("setup.model.failed")


class ModelSetupPanel(QFrame):
    state_changed = Signal()
    model_ready = Signal(str)
    download_progress = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.busy = False
        self._closed = False
        self.recommendation = None
        self._pending_progress = None
        self.setObjectName("KkCard")
        layout = QVBoxLayout(self)
        self.title = QLabel(tr("setup.model.card"))
        self.title.setObjectName("CardTitle")
        layout.addWidget(self.title)
        self.specs = QLabel()
        self.specs.setWordWrap(True)
        layout.addWidget(self.specs)
        self.recommended = QLabel()
        self.recommended.setWordWrap(True)
        layout.addWidget(self.recommended)
        self.model_choice = QComboBox()
        self.model_choice.setAccessibleName('KI-Modell auswählen')
        layout.addWidget(self.model_choice)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.progress_bar = QProgressBar()
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)
        self.install_button = QPushButton(tr("setup.model.download"))
        self.install_button.setObjectName("KkPrimary")
        self.install_button.clicked.connect(self.install)
        layout.addWidget(self.install_button)
        self.cancel_button = QPushButton(tr("btn.cancel"))
        self.cancel_button.clicked.connect(self.cancel)
        self.cancel_button.hide()
        layout.addWidget(self.cancel_button)
        self.download_progress.connect(self._show_progress)
        # Only a local RAM/CPU/disk snapshot; no model load or network at startup.
        self.refresh_recommendation()

    def refresh_recommendation(self):
        try:
            self.recommendation = inspect_setup_device()
        except Exception:
            self.install_button.setEnabled(False)
            self.status.setText(tr("setup.model.specs_failed"))
            return
        result = self.recommendation
        self.specs.setText(tr("setup.model.specs", ram=f"{result.total_gib:.0f}",
                              free=f"{result.available_gib:.1f}", cores=result.physical_cores))
        previous_choice = self.model_choice.currentData()
        installed_path = selected_model_path()
        installed_mid = selected_model_id() if installed_path is not None else None
        self.model_choice.clear()
        for mid, entry in SETUP_MODEL_CATALOG.items():
            if (entry["ram_gb_min"] + 2 <= result.available_gib
                    and (mid == installed_mid or
                         entry["approx_bytes"] + 500_000_000 <= result.free_disk_bytes)):
                self.model_choice.addItem(f"{entry['display_name']} ({entry['approx_bytes'] / 1_000_000_000:.2f} GB)", mid)
        self.model_choice.setEnabled(self.model_choice.count() > 0)
        if result.model_id:
            preferred = previous_choice if self.model_choice.findData(previous_choice) >= 0 else result.model_id
            self.model_choice.setCurrentIndex(self.model_choice.findData(preferred))
            model = SETUP_MODEL_CATALOG[result.model_id]
            self.recommended.setText(tr("setup.model.recommended", name=model["display_name"],
                                        size=f"{model['approx_bytes'] / 1_000_000_000:.2f}"))
            self.install_button.setEnabled(True)
            self.status.setText(tr("setup.model.optional"))
        else:
            self.recommended.setText(tr("setup.model.insufficient"))
            self.install_button.setText(tr("setup.model.recheck"))
            self.install_button.setEnabled(self.model_choice.count() > 0)
        if installed_mid and self.model_choice.findData(installed_mid) >= 0 and not result.model_id:
            self.model_choice.setCurrentIndex(self.model_choice.findData(installed_mid))
        if installed_path is not None and installed_mid in SETUP_MODEL_CATALOG:
            self.status.setText(tr("setup.model.ready", name=SETUP_MODEL_CATALOG[installed_mid]["display_name"]))
            self.status.setText(self.status.text() + " · Ein anderes Modell kann ausgewählt werden.")
            self.install_button.show()
            self.install_button.setText("Ausgewähltes Modell installieren / wechseln")

    def install(self):
        if self.busy or self._closed:
            return
        # Check current resources again; another application may have consumed RAM.
        self.refresh_recommendation()
        if not self.recommendation:
            return
        mid = self.model_choice.currentData()
        if not mid:
            return
        # An already installed model needs no additional download space.
        if not self.recommendation.model_id and not (mid == selected_model_id() and selected_model_path() is not None):
            return
        self.busy = True
        self.install_button.setEnabled(False)
        self.model_choice.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.cancel_button.show()
        self._pending_progress = None
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.status.setText(tr("setup.model.downloading"))
        self.state_changed.emit()
        worker = FunctionWorker(lambda: install_recommended_model(
            mid, cancelled=worker._cancel.is_set, progress=self._emit_progress))

        def done(value, failed=False):
            self.busy = False
            self.model_choice.setEnabled(True)
            self.cancel_button.hide()
            self.progress_bar.hide()
            self.state_changed.emit()
            if self._closed:
                return
            if worker._cancel.is_set():
                self.status.setText(tr("setup.model.cancelled"))
                self.install_button.setEnabled(True)
            elif failed:
                self.status.setText(model_failure_text(value))
                logging.getLogger("karrierekrake").error(
                    "model_setup_failed model_id=%s reason=%s diagnostic=%s",
                    mid, model_failure_text(value), getattr(value, "download_diagnostic", ""))
                self.install_button.setEnabled(True)
                self.install_button.setText(tr("setup.model.retry"))
            else:
                active_path = selected_model_path()
                active_id = selected_model_id() if active_path is not None else None
                if active_path is None or active_id != mid:
                    self.status.setText(tr("setup.model.failed"))
                    self.install_button.setEnabled(True)
                    self.install_button.setText(tr("setup.model.retry"))
                    return
                self.status.setText(tr("setup.model.ready", name=SETUP_MODEL_CATALOG[mid]["display_name"]))
                self.install_button.setEnabled(True)
                self.install_button.show()
                self.install_button.setText("Ausgewähltes Modell installieren / wechseln")
                self.model_ready.emit(mid)

        connect_queued(worker.finished, done)
        connect_queued(worker.failed, lambda error: done(error, True))
        self.worker = worker
        self.thread = start_worker(worker)

    def _emit_progress(self, progress):
        # Throttle worker→GUI messages: never queue one event per megabyte.
        value = (progress.status, int(100 * progress.bytes_done / progress.bytes_total)
                 if progress.bytes_total else 0)
        if value != self._pending_progress:
            self._pending_progress = value
            from dataclasses import replace
            self.download_progress.emit(replace(progress))

    def _show_progress(self, progress):
        if self._closed or not self.busy:
            return
        if progress.status == "retrying":
            self.status.setText(tr("setup.model.retrying"))
        elif progress.status in {"checking", "verifying", "testing"}:
            self.progress_bar.setRange(0, 0)
            self.status.setText(tr("setup.model.testing" if progress.status == "testing" else "setup.model.verifying"))
        elif progress.status == "downloading":
            self.status.setText(tr("setup.model.downloading"))
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(min(99, int(100 * progress.bytes_done / progress.bytes_total))
                                       if progress.bytes_total else 0)

    def cancel(self):
        worker = getattr(self, "worker", None)
        if self.busy and worker is not None:
            worker.request_cancel()
            self.cancel_button.setEnabled(False)
            self.status.setText(tr("setup.model.cancelling"))

    def shutdown(self):
        self._closed = True
        self.cancel()
