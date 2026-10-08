"""Nonblocking update controls shared by startup and Settings."""
import sys

from PySide6.QtCore import QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout

from core import app_updates as updates
from core import native_model_download as native_models
from core import native_updates
from desktop.i18n import tr
from desktop.widgets.confirm_dialog import confirm_action
from desktop.workers import FunctionWorker, connect_queued, start_worker


class UpdatePanel(QFrame):
    available = Signal(str)
    restart_requested = Signal()
    download_progress = Signal(float, float)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('KkCard')
        self.download_progress.connect(self._show_progress)
        self.manifest = None
        self.busy = False
        layout = QVBoxLayout(self)
        self.title = QLabel(tr('updates.title'))
        self.title.setObjectName('CardTitle')
        layout.addWidget(self.title)
        self.status = QLabel(tr('updates.startup'))
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.check_button = QPushButton(tr('updates.check'))
        self.check_button.clicked.connect(self.check)
        layout.addWidget(self.check_button)
        self.install_button = QPushButton(tr('updates.install'))
        self.install_button.setObjectName('KkPrimary')
        self.install_button.clicked.connect(self.install)
        self.install_button.hide()
        layout.addWidget(self.install_button)
        self.version = QLabel()
        layout.addWidget(self.version)
        self.native = native_updates.current() if sys.platform != 'win32' else {}
        current = updates.read_current(updates.install_root())
        self.version.setText(tr('updates.version', version=current.get('display_version', current.get('tag', tr('updates.development')))))
        self.managed = getattr(sys, 'frozen', False) and (updates.install_root() / updates.CURRENT).is_file()
        if self.managed and not (updates.install_root() / updates.MODEL_PATH).is_file():
            self.manifest = updates.bootstrap_manifest(updates.install_root())
            self.status.setText(tr('updates.initial'))
            self.install_button.setText(tr('updates.model_install'))
            self.install_button.show()
        if self.managed and (updates.install_root() / 'update-error.txt').is_file():
            self.status.setText(tr('updates.rollback'))
        if self.native:
            self.managed = True
            self.version.setText(tr('updates.version', version=self.native.get('display_version', self.native['commit'][:12])))
            self.status.setText(tr('updates.native_ready') if native_models.available() else tr('updates.initial'))
            if not native_models.available():
                self.install_button.setText(tr('updates.model_install'))
                self.install_button.show()
        elif not self.managed:
            self.status.setText(tr('updates.legacy'))
            self.check_button.setEnabled(False)

    def retranslate(self):
        self.title.setText(tr('updates.title'))
        self.check_button.setText(tr('updates.check'))
        if self.native:
            self.install_button.setText(tr('updates.native_download') if native_models.available() else tr('updates.model_install'))
            self.version.setText(tr('updates.version', version=self.native.get('display_version', self.native['commit'][:12])))
            return
        self.install_button.setText(tr('updates.model_install') if self.managed and not (updates.install_root() / updates.MODEL_PATH).is_file() else tr('updates.install'))
        current = updates.read_current(updates.install_root())
        self.version.setText(tr('updates.version', version=current.get('display_version', current.get('tag', tr('updates.development')))))

    def _run(self, operation, success, *, quiet=False):
        if self.busy:
            return
        self.busy = True
        self.check_button.setEnabled(False)
        self.install_button.setEnabled(False)
        def finish(value, failed=False):
            self.busy = False
            self.check_button.setEnabled(self.managed)
            self.install_button.setEnabled(True)
            if failed:
                self.status.setText(tr('updates.offline') if quiet else
                                    tr('updates.failure'))
            else:
                success(value)
        self.worker = FunctionWorker(operation)
        connect_queued(self.worker.finished, lambda value: finish(value))
        connect_queued(self.worker.failed, lambda error: finish(error, True))
        self.thread = start_worker(self.worker)

    def check(self, *, quiet=False):
        if not self.managed or self.busy:
            return
        if self.native:
            self._check_native(quiet=quiet)
            return
        if not (updates.install_root() / updates.MODEL_PATH).is_file():
            self.available.emit(tr('updates.model_notice'))
        self.status.setText(tr('updates.checking'))
        def result(manifest):
            self.manifest = manifest
            self.install_button.setVisible(bool(manifest))
            if manifest:
                names = updates.changed_components(manifest, updates.install_root())
                size = sum(manifest['components'][n]['size'] for n in names)
                self.status.setText(tr('updates.available', megabytes=f'{size / 1024**2:.0f}'))
                self.available.emit(tr('updates.notice'))
            elif not (updates.install_root() / updates.MODEL_PATH).is_file():
                self.manifest = updates.bootstrap_manifest(updates.install_root())
                self.install_button.setText(tr('updates.model_install'))
                self.install_button.show()
                self.status.setText(tr('updates.model_missing'))
            else:
                self.status.setText(tr('updates.current'))
        self._run(updates.check_for_update, result, quiet=quiet)

    def _check_native(self, *, quiet=False):
        self.status.setText(tr('updates.checking'))
        def result(manifest):
            self.manifest = manifest
            self.install_button.setVisible(bool(manifest))
            self.install_button.setText(tr('updates.native_download') if native_models.available() else tr('updates.model_install'))
            missing = not native_models.available()
            self.status.setText(tr('updates.model_missing') if missing else tr('updates.native_available') if manifest else tr('updates.current'))
            if manifest:
                self.available.emit(tr('updates.model_notice') if missing else tr('updates.notice'))
        self._run(lambda: native_updates.check_for_update(self.native, include_current=not native_models.available()), result, quiet=quiet)

    def _show_progress(self, done, total):
        percent = 100 * done / total if total else 100
        self.status.setText(tr('updates.progress', percent=f'{percent:.0f}', done=f'{done / 1024**2:.0f}', total=f'{total / 1024**2:.0f}'))

    def install(self):
        if self.busy:
            return
        if self.native and not self.manifest and not native_models.available():
            self.check()
            return
        if not self.manifest:
            return
        if self.native and not native_models.available():
            self.status.setText(tr('updates.downloading'))
            def model_ready(_path):
                self.manifest = None
                self.install_button.hide()
                self.status.setText(tr('updates.native_ready'))
            self._run(lambda: native_models.download(
                self.manifest, cancelled=self.worker._cancel.is_set,
                progress=self.download_progress.emit), model_ready)
            return
        if self.native:
            if not QDesktopServices.openUrl(QUrl(self.manifest['url'])):
                self.status.setText(tr('updates.launch_failed'))
            return
        if not confirm_action(self, tr('updates.confirm_title'),
                              tr('updates.confirm'),
                              confirm_text=tr('updates.install')):
            return
        self.status.setText(tr('updates.downloading'))
        def ready(stage):
            try:
                updates.launch_installer(stage)
            except Exception:
                self.status.setText(tr('updates.launch_failed'))
                return
            self.status.setText(tr('updates.restarting'))
            QTimer.singleShot(0, self.restart_requested.emit)
        missing_model = self.managed and not (updates.install_root() / updates.MODEL_PATH).is_file()
        only = {'model'} if missing_model else None
        self._run(lambda: updates.stage_update(
            self.manifest,
            cancelled=self.worker._cancel.is_set,
            progress=self.download_progress.emit,
            only_components=only,
        ), ready)
