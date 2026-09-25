"""CV import confirmation dialog — Replace (default) or Merge with preview & conflicts.

Parsing runs in a worker process off the UI thread. The dialog switches UX
state from that worker's result: progress, cancelled, success, empty, or
error (including OOM and timeout). Nothing here retries on its own or
switches model.

The first Cancel while a run is active stops that process group and shows the
cancelled sentence before any result is applied. The dialog stays open. A
later Schließen, after a short grace so a double-click cannot dismiss it,
closes without applying. ``KARRIEREKRAKE_CV_IMPORT_OBSERVE_S`` (default unset
/ 0) holds the worker before the child starts so Progress and Cancel can be
checked. It is not a production delay.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QLabel,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.config import ApplicationProfile, QualificationsConfig
from core.cv_parser import parsed_to_qualifications
from core.local_llm_cv_gate import local_llm_cv_parsing_allowed
from desktop.cv_import_supervisor import (
    CvImportSupervisor,
    ImportAttemptResult,
)
from desktop.design_system.a11y import set_accessible_name
from desktop.design_system.polish import (
    apply_button_icon,
    footer_actions_layout,
    polish_interactive,
    soft_shadow,
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
from desktop.widgets.dialog_geometry import fit_dialog_to_screen
from desktop.workers import start_worker

# A second click in the same double-click must not dismiss the cancelled state.
_CANCEL_CLOSE_GRACE_S = 0.8

_REDUCED_MOTION_VALUES = {"1", "true", "yes", "on", "reduce", "reduced"}


def _prefers_reduced_motion() -> bool:
    """Honor KK_REDUCED_MOTION and prefers-reduced-motion. Shadows stay allowed."""
    for key in ("KK_REDUCED_MOTION", "PREFERS_REDUCED_MOTION", "prefers_reduced_motion"):
        if os.environ.get(key, "").strip().lower() in _REDUCED_MOTION_VALUES:
            return True
    return False


def _polish_primary(button: QPushButton) -> None:
    """Same hover polish as profile Save. Reduced motion keeps a static shadow."""
    if _prefers_reduced_motion():
        soft_shadow(button, blur=16.0, y_offset=4.0, alpha=38)
        button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        return
    polish_interactive(button)


def _bind_button_qss(button: QPushButton) -> None:
    """Make objectName QSS win over the platform button chrome."""
    style = button.style()
    style.unpolish(button)
    style.polish(button)


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
        self._phase = "idle"
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

        self.mode_box = QGroupBox(tr("cv_import.mode"))
        mode_layout = QVBoxLayout(self.mode_box)
        mode_layout.addWidget(self.mode_replace)
        mode_layout.addWidget(self.mode_merge)
        mode_layout.addWidget(self.mode_hint)

        self.llm_notice = QLabel()
        self.llm_notice.setWordWrap(True)
        self.llm_notice.setObjectName("CvImportLlmNotice")
        llm_allowed = local_llm_cv_parsing_allowed(settings)
        self.llm_notice.setVisible(not llm_allowed)
        if not llm_allowed:
            self.llm_notice.setText(tr("settings.local_llm_cv_disabled_hint"))

        self.status_label = QLabel()
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
        self.cancel_text = self._cancelled_banner
        self.path_label = QLabel()
        self.path_label.setWordWrap(True)
        self.path_label.setObjectName("CvImportPath")
        self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.progress = QProgressBar()
        self.progress.setObjectName("CvImportProgress")
        self.progress.setRange(0, 0)
        self.progress.setMinimumHeight(18)
        self.progress.setTextVisible(False)
        self.progress.setVisible(False)

        self.empty_box = QWidget()
        self.empty_box.setObjectName("CvImportEmpty")
        empty_layout = QVBoxLayout(self.empty_box)
        empty_layout.setContentsMargins(0, 0, 0, 0)
        self.empty_title = QLabel(tr("cv_import.empty_title"))
        self.empty_title.setObjectName("CvImportEmptyTitle")
        self.empty_title.setStyleSheet("font-weight: 600;")
        self.empty_body = QLabel(tr("cv_import.empty_body"))
        self.empty_body.setWordWrap(True)
        self.empty_body.setObjectName("CvImportEmptyBody")
        empty_layout.addWidget(self.empty_title)
        empty_layout.addWidget(self.empty_body)

        self.error_box = QWidget()
        self.error_box.setObjectName("CvImportError")
        error_layout = QVBoxLayout(self.error_box)
        error_layout.setContentsMargins(0, 0, 0, 0)
        self.error_text = QLabel()
        self.error_text.setWordWrap(True)
        self.error_text.setObjectName("CvImportErrorText")
        self.error_detail = QLabel()
        self.error_detail.setWordWrap(True)
        self.error_detail.setObjectName("CvImportErrorDetail")
        self.error_detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        error_layout.addWidget(self.error_text)
        error_layout.addWidget(self.error_detail)

        self.preview = QTextEdit()
        self.preview.setReadOnly(True)

        self.conflict_box = QGroupBox(tr("cv_import.conflicts"))
        self.conflict_form = QFormLayout(self.conflict_box)
        self.conflict_box.setVisible(False)

        # Plain QPushButtons, not QDialogButtonBox: the box keeps Fusion/Windows
        # bevels and stock icons even when Primary/Secondary QSS is active.
        self._ok_btn = QPushButton(tr("cv_import.apply"), self)
        self._ok_btn.setObjectName("PrimaryButton")
        self._ok_btn.setAutoDefault(True)
        self._ok_btn.setDefault(True)
        self._ok_btn.setEnabled(False)
        self._ok_btn.clicked.connect(self._accept)
        set_accessible_name(self._ok_btn, tr("cv_import.apply"))
        apply_button_icon(self._ok_btn, "check", color="#ffffff")
        _polish_primary(self._ok_btn)
        _bind_button_qss(self._ok_btn)

        self._cancel_btn = QPushButton(tr("cv_import.cancel_btn"), self)
        self._cancel_btn.setObjectName("SecondaryButton")
        self._cancel_btn.setAutoDefault(False)
        self._cancel_btn.setDefault(False)
        self._cancel_btn.clicked.connect(self.reject)
        set_accessible_name(self._cancel_btn, tr("cv_import.cancel_btn"))
        _bind_button_qss(self._cancel_btn)

        self._retry_btn = QPushButton(tr("cv_import.retry"), self)
        self._retry_btn.setObjectName("SecondaryButton")
        self._retry_btn.setVisible(False)
        self._retry_btn.clicked.connect(self._manual_retry)
        set_accessible_name(self._retry_btn, tr("cv_import.retry"))
        _bind_button_qss(self._retry_btn)

        self._read_again_btn = QPushButton(tr("cv_import.read_again"), self)
        self._read_again_btn.setObjectName("SecondaryButton")
        self._read_again_btn.setVisible(False)
        self._read_again_btn.clicked.connect(self._read_again)
        set_accessible_name(self._read_again_btn, tr("cv_import.read_again"))
        _bind_button_qss(self._read_again_btn)

        self._choose_btn = QPushButton(tr("cv_import.choose_other"), self)
        self._choose_btn.setObjectName("SecondaryButton")
        self._choose_btn.setVisible(False)
        self._choose_btn.clicked.connect(self._choose_other_file)
        set_accessible_name(self._choose_btn, tr("cv_import.choose_other"))
        _bind_button_qss(self._choose_btn)

        layout = QVBoxLayout(self)
        self._intro = QLabel(tr("cv_import.intro"))
        self._intro.setWordWrap(True)
        layout.addWidget(self._intro)
        layout.addWidget(self.llm_notice)
        layout.addWidget(self.mode_box)
        layout.addWidget(self.status_label)
        layout.addWidget(self._cancelled_banner)
        layout.addWidget(self.path_label)
        layout.addWidget(self.progress)
        layout.addWidget(self.empty_box)
        layout.addWidget(self.error_box)
        self._detected_label = QLabel(tr("cv_import.detected"))
        layout.addWidget(self._detected_label)
        layout.addWidget(self.preview, 1)
        layout.addWidget(self.conflict_box)
        layout.addLayout(
            footer_actions_layout(
                self._ok_btn,
                self._cancel_btn,
                self._retry_btn,
                self._read_again_btn,
                self._choose_btn,
            )
        )
        self._refresh_path_label()
        self._apply_phase("idle")
        fit_dialog_to_screen(self, preferred_width=760, preferred_height=640)

        if autostart:
            self._autostart = QTimer(self)
            self._autostart.setSingleShot(True)
            self._autostart.timeout.connect(self.start_parse)
            self._autostart.start(0)

    @property
    def cv_path(self) -> Path:
        return self._cv_path

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
        self.preview.clear()
        self._ok_btn.setEnabled(False)
        self._refresh_path_label()
        self._apply_phase("progress")
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
        """One user-triggered retry of the same file. Never called by itself."""
        if self._running or self._phase != "error":
            return
        self.start_parse()

    def _read_again(self) -> None:
        """Manual re-read after cancel. Does not start on its own."""
        if self._running or self._phase != "cancelled":
            return
        self.start_parse()

    def _choose_other_file(self) -> None:
        """Pick another file from the empty state. Cancelling the picker keeps the path."""
        if self._running or self._phase != "empty":
            return
        picked = self._pick_other_file()
        if not picked:
            self._refresh_path_label()
            return
        self._cv_path = Path(picked)
        self._refresh_path_label()
        self.start_parse()

    def _pick_other_file(self) -> str:
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("cv_import.choose_other"),
            str(self._cv_path.parent) if str(self._cv_path.parent) else "",
            "Dokumente (*.pdf *.docx);;Alle Dateien (*.*)",
        )
        return path or ""

    def _on_progress(self, _message: str) -> None:
        if self._closing or self._cancel_requested or not self._running:
            return
        self.progress.setVisible(True)
        self.status_label.setText(tr("cv_import.progress"))

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
            self._last_kind = "error"
            self._show_failure("error", str(result))
            return
        self._last_kind = result.kind
        if result.ok and isinstance(result.parsed, dict):
            self._apply_parsed(result.parsed)
            if self._detection_is_empty():
                self._last_kind = "empty"
                self.preview.clear()
                self._show_empty()
                return
            self._show_success()
            return
        if result.kind == "cancelled":
            self._show_cancelled()
            return
        self._show_failure(result.kind, result.message)

    def _show_success(self) -> None:
        self._apply_phase("success")
        self.status_label.setText(tr("cv_import.ready"))
        self._ok_btn.setEnabled(True)

    def _show_empty(self) -> None:
        self.result_quals = None
        self.result_application = None
        self._ok_btn.setEnabled(False)
        self._apply_phase("empty")

    def _show_cancelled(self) -> None:
        self._present_cancelled()

    def _show_failure(self, kind: str, message: str) -> None:
        self._clear_unapplied()
        self.preview.clear()
        if kind == "oom":
            text = tr("cv_import.error_oom")
        elif kind == "timeout":
            text = tr("cv_import.error_timeout")
        else:
            text = tr("cv_import.error_generic")
        self.error_text.setText(text)
        detail = (message or "").strip()
        if detail.lower() in {"", "oom", "timeout", "error", "cancelled"}:
            self.error_detail.clear()
            self.error_detail.setVisible(False)
        else:
            self.error_detail.setText(detail)
            self.error_detail.setVisible(True)
        self._apply_phase("error")

    def _clear_unapplied(self) -> None:
        self.incoming = None
        self.parsed = None
        self.personal_incoming = {}
        self.plan = None
        self.result_quals = None
        self.result_application = None
        self._ok_btn.setEnabled(False)

    def _refresh_path_label(self) -> None:
        self.path_label.setText(f"{tr('cv_import.file')}: {self._cv_path.name}\n{self._cv_path}")

    def _apply_phase(self, phase: str) -> None:
        """Show one state. Actions that must not run are hidden, not left as dead clicks."""
        self._phase = phase
        progress = phase == "progress"
        success = phase == "success"
        empty = phase == "empty"
        error = phase == "error"
        cancelled = phase == "cancelled"
        review = phase in {"idle", "success"}

        self.status_label.setVisible(progress or success or cancelled)
        if progress:
            self.status_label.setText(tr("cv_import.progress"))
        if cancelled:
            text = tr("cv_import.cancelled")
            self.status_label.setText(text)
            self._cancelled_banner.setText(text)
            self._cancelled_banner.setVisible(True)
            self.preview.setPlainText(text)
        else:
            self._cancelled_banner.setVisible(False)
        self.progress.setVisible(progress)
        self.path_label.setVisible(True)
        self.empty_box.setVisible(empty)
        self.error_box.setVisible(error)
        self._intro.setVisible(review)
        self.mode_box.setVisible(review)
        self._detected_label.setVisible(success)
        self.preview.setVisible(success or cancelled)
        if not success:
            self.conflict_box.setVisible(False)

        self._ok_btn.setVisible(success)
        self._ok_btn.setDefault(success)
        if not success:
            self._ok_btn.setEnabled(False)
        self._retry_btn.setVisible(error)
        self._read_again_btn.setVisible(cancelled and not self._running)
        self._choose_btn.setVisible(empty)
        if progress or success:
            self._cancel_btn.setText(tr("cv_import.cancel_btn"))
        else:
            self._cancel_btn.setText(tr("cv_import.close"))

    def _detection_is_empty(self) -> bool:
        if self.personal_incoming:
            return False
        if self.incoming is None:
            return True
        summary = summarize_incoming(self.incoming)
        return not any(summary.values())

    def _apply_parsed(self, parsed: dict) -> None:
        self.parsed = filter_parsed_for_import(parsed)
        self.incoming = parsed_to_qualifications(self.parsed)
        self.personal_incoming = personal_from_parsed(self.parsed)
        self._refresh_preview()

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

    def _arm_cancel(self) -> None:
        """Stop the run and show the cancelled sentence without closing."""
        first = not self._cancel_requested
        self._cancel_requested = True
        self._clear_unapplied()
        self._apply_phase("cancelled")
        if self._running:
            self.progress.setVisible(True)
        if self._close_allowed_at == float("inf"):
            self._close_allowed_at = time.monotonic() + _CANCEL_CLOSE_GRACE_S
        if first and self._worker is not None:
            self._worker.request_cancel()
        if not self._running:
            self._present_cancelled()

    def _present_cancelled(self) -> None:
        """Show the cancelled state while the dialog is still open. Nothing is applied."""
        self._running = False
        self._last_kind = "cancelled"
        self._cancel_requested = True
        self._clear_unapplied()
        self._apply_phase("cancelled")
        self.progress.setVisible(False)
        if self._close_allowed_at == float("inf"):
            self._close_allowed_at = time.monotonic() + _CANCEL_CLOSE_GRACE_S

    def _finish_close(self) -> None:
        self._closing = True
        self.result_quals = None
        self.result_application = None
        if self._worker is not None:
            self._worker.request_cancel()
        super().reject()

    def reject(self) -> None:  # noqa: D102 — first close becomes the cancelled state
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
        if not self._closing:
            self._closing = True
            self.result_quals = None
            self.result_application = None
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
        if self._phase != "success" or self._running or self.incoming is None or self.plan is None:
            return
        if self._detection_is_empty():
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
        # Persist Docpick/CV source text so Anschreiben evidence can refuse
        # unevidenced job-title claims on the real apply path.
        raw_src = ""
        if isinstance(self.parsed, dict):
            raw_src = str(
                self.parsed.get("source_text") or self.parsed.get("raw_text") or ""
            ).strip()
        app.cv_source_text = raw_src
        self.result_application = app
        self.accept()
