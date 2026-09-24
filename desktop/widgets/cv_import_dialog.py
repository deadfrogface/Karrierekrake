"""CV import confirmation dialog — Replace (default) or Merge with preview & conflicts.

Parsing runs in a worker process off the UI thread. The first Cancel while a
run is active stops that process group and shows the cancelled state before
any result is applied. A second Cancel closes the dialog. OOM and timeout
keep the current profile inputs and wait for a manual retry; the same run is
not started again automatically.

``KARRIEREKRAKE_CV_IMPORT_OBSERVE_S`` (default unset / 0) holds the worker
before the child starts so Progress and Cancel can be checked. It is not a
production delay.
"""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QTextEdit,
    QVBoxLayout,
)

from core.config import ApplicationProfile, QualificationsConfig
from core.cv_parser import parsed_to_qualifications
from core.local_llm_cv_gate import local_llm_cv_parsing_allowed
from desktop.cv_import_supervisor import (
    CvImportSupervisor,
    ImportAttemptResult,
)
from desktop.i18n import tr
from desktop.services.profile_merge import (
    ImportMode,
    PersonalImportPlan,
    apply_personal_updates,
    filter_parsed_for_import,
    merge_qualifications,
    personal_from_parsed,
    plan_personal_import,
    quals_section_labels,
    replace_qualifications,
    summarize_incoming,
    sync_application_summaries,
)
from desktop.widgets.confirm_dialog import label_button_box
from desktop.widgets.dialog_geometry import fit_dialog_to_screen
from desktop.workers import start_worker

# A second click in the same double-click must not dismiss the cancelled state.
_CANCEL_CLOSE_GRACE_S = 0.8


class _CvImportWorker(QObject):
    progress = Signal(str)
    attempt_finished = Signal(object)
    finished = Signal()

    def __init__(self, supervisor: CvImportSupervisor) -> None:
        super().__init__()
        self._supervisor = supervisor

    def request_cancel(self) -> None:
        self._supervisor.request_cancel()

    def run(self) -> None:
        try:
            result = self._supervisor.run_once(progress=self.progress.emit)
            self.attempt_finished.emit(result)
        except Exception as exc:  # noqa: BLE001 — surface in the dialog, do not freeze
            self.attempt_finished.emit(
                ImportAttemptResult(ok=False, kind="error", message=str(exc), parsed=None)
            )
        finally:
            self.finished.emit()


class CvImportDialog(QDialog):
    def __init__(
        self,
        cv_path: Path,
        existing: QualificationsConfig,
        application: ApplicationProfile,
        parent=None,
        *,
        settings=None,
        spawn=None,
        timeout_s: float | None = None,
        autostart: bool = True,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("cv_import.title"))
        self.setMinimumSize(480, 360)
        self.existing = existing
        self.application = application
        self._cv_path = Path(cv_path)
        self._settings = settings
        self._spawn = spawn
        self._timeout_s = timeout_s
        self.incoming: QualificationsConfig | None = None
        self.parsed: dict | None = None
        self.personal_incoming: dict[str, str] = {}
        self.plan: PersonalImportPlan | None = None
        self.result_quals: QualificationsConfig | None = None
        self.result_application: ApplicationProfile | None = None
        self.import_mode: ImportMode = "replace"
        self._conflict_widgets: dict[str, QComboBox] = {}
        self._worker: _CvImportWorker | None = None
        self._thread = None
        self._running = False
        self._closing = False
        self._cancel_requested = False
        self._close_allowed_at = float("inf")
        self._last_kind = ""
        self.attempt_count = 0

        self.mode_replace = QRadioButton(tr("cv_import.mode_replace"))
        self.mode_merge = QRadioButton(tr("cv_import.mode_merge"))
        self.mode_replace.setChecked(True)
        self.mode_hint = QLabel(tr("cv_import.mode_hint"))
        self.mode_hint.setWordWrap(True)
        mode_group = QButtonGroup(self)
        mode_group.addButton(self.mode_replace)
        mode_group.addButton(self.mode_merge)
        self.mode_replace.toggled.connect(self._refresh_preview)

        mode_box = QGroupBox(tr("cv_import.mode"))
        mode_layout = QVBoxLayout(mode_box)
        mode_layout.addWidget(self.mode_replace)
        mode_layout.addWidget(self.mode_merge)
        mode_layout.addWidget(self.mode_hint)

        self.llm_notice = QLabel()
        self.llm_notice.setWordWrap(True)
        self.llm_notice.setObjectName("CvImportLlmNotice")
        llm_allowed = local_llm_cv_parsing_allowed(settings)
        self.llm_notice.setVisible(not llm_allowed)
        if not llm_allowed:
            self.llm_notice.setText(tr("settings.local_llm_cv_kill"))

        self.status_label = QLabel(tr("cv_import.parsing"))
        self.status_label.setWordWrap(True)
        self.status_label.setObjectName("CvImportStatus")
        self._cancelled_banner = QLabel("")
        self._cancelled_banner.setWordWrap(True)
        self._cancelled_banner.setObjectName("CvImportCancelled")
        self._cancelled_banner.setMinimumHeight(48)
        self._cancelled_banner.setVisible(False)
        self._cancelled_banner.setStyleSheet(
            "QLabel#CvImportCancelled {"
            " background: #fff4e5; color: #7a2e0e;"
            " border: 1px solid #e0a060; padding: 12px; font-weight: 600;"
            "}"
        )
        self.progress = QProgressBar()
        self.progress.setObjectName("CvImportProgress")
        self.progress.setRange(0, 0)
        self.progress.setMinimumHeight(18)
        self.progress.setTextVisible(False)
        self.progress.setVisible(False)

        self.preview = QTextEdit()
        self.preview.setReadOnly(True)

        self.conflict_box = QGroupBox(tr("cv_import.conflicts"))
        self.conflict_form = QFormLayout(self.conflict_box)
        self.conflict_box.setVisible(False)

        buttons = label_button_box(
            QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        )
        self._buttons = buttons
        self._ok_btn = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._ok_btn.setText(tr("cv_import.apply"))
        self._ok_btn.setEnabled(False)
        self._cancel_btn = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        self._cancel_btn.setObjectName("CvImportCancel")
        self._cancel_btn.setText(tr("cv_import.cancel_btn"))
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self._cancel_and_reject)
        self._retry_btn = QPushButton(tr("cv_import.retry"))
        self._retry_btn.setObjectName("CvImportRetry")
        self._retry_btn.setVisible(False)
        self._retry_btn.clicked.connect(self._manual_retry)
        buttons.addButton(self._retry_btn, QDialogButtonBox.ButtonRole.ActionRole)
        self._manual_btn = QPushButton(tr("cv_import.manual_profile"))
        self._manual_btn.setObjectName("CvImportManual")
        self._manual_btn.setVisible(False)
        self._manual_btn.clicked.connect(self._keep_manual_profile)
        buttons.addButton(self._manual_btn, QDialogButtonBox.ButtonRole.ActionRole)

        layout = QVBoxLayout(self)
        intro = QLabel(tr("cv_import.intro"))
        intro.setWordWrap(True)
        layout.addWidget(intro)
        layout.addWidget(self.llm_notice)
        layout.addWidget(mode_box)
        layout.addWidget(self.status_label)
        layout.addWidget(self._cancelled_banner)
        layout.addWidget(self.progress)
        layout.addWidget(QLabel(tr("cv_import.detected")))
        layout.addWidget(self.preview, 1)
        layout.addWidget(self.conflict_box)
        layout.addWidget(buttons)
        fit_dialog_to_screen(self, preferred_width=760, preferred_height=640)

        if autostart:
            self._autostart = QTimer(self)
            self._autostart.setSingleShot(True)
            self._autostart.timeout.connect(self.start_parse)
            self._autostart.start(0)

    def start_parse(self) -> None:
        """Start one parse. A second call while running is ignored."""
        if self._running or self._closing:
            return
        self._running = True
        self._cancel_requested = False
        self._close_allowed_at = float("inf")
        self._cancelled_banner.setVisible(False)
        self._cancel_btn.setText(tr("cv_import.cancel_btn"))
        self.attempt_count += 1
        self._last_kind = ""
        self.incoming = None
        self.parsed = None
        self.personal_incoming = {}
        self.plan = None
        self.result_quals = None
        self.result_application = None
        self._ok_btn.setEnabled(False)
        self._retry_btn.setVisible(False)
        self._manual_btn.setVisible(False)
        self.progress.setVisible(True)
        self.status_label.setText(tr("cv_import.parsing"))
        supervisor = CvImportSupervisor(
            self._cv_path,
            spawn=self._spawn,
            timeout_s=self._timeout_s,
        )
        worker = _CvImportWorker(supervisor)
        self._worker = worker
        worker.progress.connect(self._on_progress, Qt.ConnectionType.QueuedConnection)
        worker.attempt_finished.connect(self._on_attempt, Qt.ConnectionType.QueuedConnection)
        self._thread = start_worker(worker)

    def _manual_retry(self) -> None:
        """User-triggered retry. Never invoked automatically after OOM or timeout."""
        if self._running:
            return
        if self._last_kind not in {"oom", "timeout", "error", "empty"}:
            return
        self.start_parse()

    def _on_progress(self, _message: str) -> None:
        if self._closing or self._cancel_requested:
            return
        self.progress.setVisible(True)
        self.status_label.setText(tr("cv_import.parsing"))

    def _on_attempt(self, result: object) -> None:
        self._running = False
        if self._closing:
            return
        if self._cancel_requested or (
            isinstance(result, ImportAttemptResult) and result.kind == "cancelled"
        ):
            self._present_cancelled()
            return
        if not isinstance(result, ImportAttemptResult):
            self._show_failure("error", str(result))
            return
        self._last_kind = result.kind
        self.progress.setVisible(False)
        if result.ok and isinstance(result.parsed, dict):
            self._apply_parsed(result.parsed)
            if self._detection_is_empty():
                self._last_kind = "empty"
                self.status_label.setText(tr("cv_import.empty"))
                self._ok_btn.setEnabled(False)
                self._retry_btn.setVisible(True)
                self._manual_btn.setVisible(True)
                return
            self.status_label.setText(tr("cv_import.ready"))
            self._ok_btn.setEnabled(True)
            self._retry_btn.setVisible(False)
            self._manual_btn.setVisible(False)
            return
        self._show_failure(result.kind, result.message)

    def _show_failure(self, kind: str, message: str) -> None:
        self.incoming = None
        self.parsed = None
        self.plan = None
        self.result_quals = None
        self.result_application = None
        self._ok_btn.setEnabled(False)
        self.progress.setVisible(False)
        if kind == "oom":
            text = tr("cv_import.oom")
        elif kind == "timeout":
            text = tr("cv_import.timeout")
        elif kind == "cancelled":
            text = tr("cv_import.cancelled")
        else:
            text = f"{tr('cv_import.read_error')}\n{message}"
        if message and kind in {"oom", "timeout", "error"}:
            text = f"{text}\n{message}"
        self.status_label.setText(text)
        self.preview.setPlainText(text)
        # Resource and read failures keep a manual CTA. Nothing starts by itself.
        self._retry_btn.setVisible(kind in {"oom", "timeout", "error"})
        self._manual_btn.setVisible(kind in {"oom", "timeout", "error"})

    def _detection_is_empty(self) -> bool:
        if self.personal_incoming:
            return False
        if self.incoming is None:
            return True
        summary = summarize_incoming(self.incoming)
        return not any(summary.values())

    def _keep_manual_profile(self) -> None:
        """Close without writing the profile. Manual entry on the profile page stays."""
        self._closing = True
        self.result_quals = None
        self.result_application = None
        if self._worker is not None:
            self._worker.request_cancel()
        self.reject()

    def _apply_parsed(self, parsed: dict) -> None:
        self.parsed = filter_parsed_for_import(parsed)
        self.incoming = parsed_to_qualifications(self.parsed)
        self.personal_incoming = personal_from_parsed(self.parsed)
        self._refresh_preview()

    def _discard_parse(self) -> None:
        self.incoming = None
        self.parsed = None
        self.personal_incoming = {}
        self.plan = None
        self.result_quals = None
        self.result_application = None

    def _should_keep_open(self) -> bool:
        """True until the cancelled sentence is on screen and the grace has elapsed."""
        if self._closing:
            return False
        if self._running:
            return True
        if not self._cancel_requested:
            return False
        if self._last_kind != "cancelled":
            return True
        return time.monotonic() < self._close_allowed_at

    def _show_cancelled_banner(self) -> None:
        text = tr("cv_import.cancelled")
        self._cancelled_banner.setText(text)
        self._cancelled_banner.setVisible(True)
        self.preview.setPlainText(text)
        self._ok_btn.setEnabled(False)
        self._retry_btn.setVisible(False)
        self._manual_btn.setVisible(False)

    def _arm_cancel(self) -> None:
        """Stop the run and show the cancelled sentence without closing."""
        first = not self._cancel_requested
        self._cancel_requested = True
        self._discard_parse()
        self._show_cancelled_banner()
        self._cancel_btn.setText(tr("cv_import.close"))
        if self._close_allowed_at == float("inf"):
            self._close_allowed_at = time.monotonic() + _CANCEL_CLOSE_GRACE_S
        if self._running and self._last_kind != "cancelled":
            self.progress.setVisible(True)
            self.status_label.setText(tr("cv_import.cancelled"))
        if first and self._worker is not None:
            self._worker.request_cancel()
        if not self._running:
            self._present_cancelled()

    def _present_cancelled(self) -> None:
        """Show the cancelled state while the dialog is still open."""
        self._running = False
        self._last_kind = "cancelled"
        self._discard_parse()
        self.progress.setVisible(False)
        text = tr("cv_import.cancelled")
        self.status_label.setText(text)
        self._show_cancelled_banner()
        self._cancel_btn.setText(tr("cv_import.close"))
        if self._close_allowed_at == float("inf"):
            self._close_allowed_at = time.monotonic() + _CANCEL_CLOSE_GRACE_S

    def _cancel_and_reject(self) -> None:
        if self._running or self._cancel_requested:
            if not self._should_keep_open():
                self._finish_close()
                return
            self._arm_cancel()
            return
        self._finish_close()

    def _finish_close(self) -> None:
        self._closing = True
        if self._worker is not None:
            self._worker.request_cancel()
        super().reject()

    def reject(self) -> None:  # noqa: D102 — Qt override, first close becomes cancelled UI
        if self._closing:
            super().reject()
            return
        if self._should_keep_open():
            self._arm_cancel()
            return
        self._finish_close()

    def closeEvent(self, event) -> None:  # noqa: N802 — Qt override
        if not self._closing and self._should_keep_open():
            event.ignore()
            self._arm_cancel()
            return
        self._closing = True
        super().closeEvent(event)

    def _current_mode(self) -> ImportMode:
        return "replace" if self.mode_replace.isChecked() else "merge"

    def _refresh_preview(self) -> None:
        if self.incoming is None or self.parsed is None:
            return
        mode = self._current_mode()
        self.plan = plan_personal_import(self.application, self.personal_incoming, mode=mode)
        summary = summarize_incoming(self.incoming)
        lines = [f"{tr('cv_import.file')}: {Path(self.parsed.get('source_path', '')).name}", ""]

        lines.append(f"=== {tr('cv_import.personal')} ===")
        if self.personal_incoming:
            for k, v in self.personal_incoming.items():
                lines.append(f"• {k}: {v}")
        else:
            lines.append(f"({tr('cv_import.none')})")
        conf = (self.parsed or {}).get("confidence") or {}
        intel = (self.parsed or {}).get("intelligence_status") or ""
        if intel:
            lines.append("")
            lines.append(f"=== {tr('cv_import.pipeline')} ===")
            lines.append(f"• {tr('cv_import.pipeline_det')}")
            if intel not in {"", "deterministic_only"}:
                lines.append(f"• Status: {intel}")
        if conf:
            lines.append("")
            lines.append(f"=== {tr('cv_import.confidence')} ===")
            for key, label in [
                ("personal", tr("cv_import.personal")),
                ("languages", tr("profile.languages")),
                ("driving_license", tr("profile.license")),
                ("education", tr("profile.education")),
                ("work_experience", tr("profile.experience")),
                ("certificates", tr("profile.certificates")),
                ("software", tr("profile.software")),
                ("skills", tr("profile.skills")),
            ]:
                status = conf.get(key, "Im Dokument nicht gefunden")
                if status in {"Nicht erkannt", "Im Dokument nicht gefunden"}:
                    status = tr("cv_import.not_detected")
                lines.append(f"• {label}: {status}")
        unclear = list((self.parsed or {}).get("uncertain_items") or [])
        if unclear:
            lines.append("")
            lines.append(f"=== {tr('cv_import.review_items')} ===")
            lines.extend(f"• {item}" for item in unclear)
        lines.append("")

        for key, label in [
            ("languages", tr("profile.languages")),
            ("driving_license", tr("profile.license")),
            ("education", tr("profile.education")),
            ("work_experience", tr("profile.experience")),
            ("certificates", tr("profile.certificates")),
            ("software", tr("profile.software")),
            ("skills", tr("profile.skills")),
        ]:
            items = summary.get(key) or []
            lines.append(f"=== {label} ({len(items)}) ===")
            if not items:
                lines.append(f"({tr('cv_import.none')})")
            else:
                lines.extend(f"• {item}" for item in items)
            lines.append("")

        lines.append(f"=== {tr('cv_import.will_replace')} ===")
        replace_bits = list(self.plan.will_replace)
        replace_bits.extend(quals_section_labels(self.incoming))
        if mode == "replace":
            replace_bits.append(tr("cv_import.old_cv_quals"))
        if replace_bits:
            lines.extend(f"• {x}" for x in dict.fromkeys(replace_bits))
        else:
            lines.append(f"({tr('cv_import.none')})")
        lines.append("")

        lines.append(f"=== {tr('cv_import.will_keep')} ===")
        keep_bits = list(self.plan.will_keep)
        if mode == "replace":
            keep_bits.append(tr("cv_import.keep_manual_quals"))
        if keep_bits:
            lines.extend(f"• {x}" for x in dict.fromkeys(keep_bits))
        else:
            lines.append(f"({tr('cv_import.none')})")

        self.preview.setPlainText("\n".join(lines))
        self._rebuild_conflicts()

    def _rebuild_conflicts(self) -> None:
        while self.conflict_form.rowCount():
            self.conflict_form.removeRow(0)
        self._conflict_widgets.clear()
        conflicts = self.plan.conflicts if self.plan else []
        self.conflict_box.setVisible(bool(conflicts))
        for c in conflicts:
            box = QComboBox()
            box.addItem(tr("cv_import.use_cv"), "cv")
            box.addItem(tr("cv_import.keep_current"), "keep")
            box.setCurrentIndex(1)  # default: keep manual
            box.setToolTip(f"{c.current_value}  →  {c.incoming_value}")
            label = QLabel(f"{c.label}\n{tr('cv_import.current')}: {c.current_value}\nCV: {c.incoming_value}")
            label.setWordWrap(True)
            self.conflict_form.addRow(label, box)
            self._conflict_widgets[c.field] = box

    def _accept(self) -> None:
        if self._running or self.incoming is None or self.plan is None:
            return
        mode = self._current_mode()
        self.import_mode = mode
        if mode == "replace":
            # True empty-then-fill for CV-derived data (manual quals still kept)
            self.result_quals = replace_qualifications(self.existing, self.incoming)
        else:
            self.result_quals = merge_qualifications(self.existing, self.incoming)

        choices = {
            field: combo.currentData() for field, combo in self._conflict_widgets.items()
        }
        from copy import deepcopy

        app = deepcopy(self.application)
        if mode == "replace":
            # Clear previous CV personal fields before applying (true empty then fill)
            from desktop.services.profile_merge import clear_cv_personal

            clear_cv_personal(app)
            self.plan = plan_personal_import(app, self.personal_incoming, mode=mode)
        apply_personal_updates(
            app,
            dict(self.plan.updates),
            source="cv",
            conflict_choices=choices,
            conflicts=self.plan.conflicts,
        )
        sync_application_summaries(app, self.result_quals, fill_empty=True)
        self.result_application = app
        self.accept()
