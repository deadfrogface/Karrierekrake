"""CV import confirmation dialog — Replace (default) or Merge with preview & conflicts.

Docpick extraction runs on a background QThread so the UI stays responsive.
DET is never used as a fallback.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QMessageBox,
    QProgressBar,
    QRadioButton,
    QTextEdit,
    QVBoxLayout,
)

from core.config import ApplicationProfile, QualificationsConfig
from core.cv_parser import parsed_to_qualifications
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
from desktop.workers import CvImportWorker, connect_queued, start_worker


class CvImportDialog(QDialog):
    def __init__(
        self,
        cv_path: Path,
        existing: QualificationsConfig,
        application: ApplicationProfile,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("cv_import.title"))
        self.setMinimumSize(480, 360)
        self.cv_path = Path(cv_path)
        self.existing = existing
        self.application = application
        self.incoming: QualificationsConfig | None = None
        self.parsed: dict | None = None
        self.personal_incoming: dict[str, str] = {}
        self.plan: PersonalImportPlan | None = None
        self.result_quals: QualificationsConfig | None = None
        self.result_application: ApplicationProfile | None = None
        self.import_mode: ImportMode = "replace"
        self._conflict_widgets: dict[str, QComboBox] = {}
        self._worker: CvImportWorker | None = None
        self._thread = None

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

        self.status_label = QLabel(tr("cv_import.extracting"))
        self.status_label.setWordWrap(True)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # indeterminate while extracting
        self.progress.setTextVisible(False)

        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setPlainText(tr("cv_import.extracting_hint"))

        self.conflict_box = QGroupBox(tr("cv_import.conflicts"))
        self.conflict_form = QFormLayout(self.conflict_box)
        self.conflict_box.setVisible(False)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.ok_btn = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.ok_btn.setText(tr("cv_import.apply"))
        self.ok_btn.setEnabled(False)
        self.buttons.accepted.connect(self._accept)
        self.buttons.rejected.connect(self._on_reject)

        layout = QVBoxLayout(self)
        intro = QLabel(tr("cv_import.intro"))
        intro.setWordWrap(True)
        layout.addWidget(intro)
        layout.addWidget(mode_box)
        layout.addWidget(self.status_label)
        layout.addWidget(self.progress)
        layout.addWidget(QLabel(tr("cv_import.detected")))
        layout.addWidget(self.preview, 1)
        layout.addWidget(self.conflict_box)
        layout.addWidget(self.buttons)

        fit_dialog_to_screen(self, preferred_width=760, preferred_height=640)
        self._start_extract()

    def _start_extract(self) -> None:
        # Productive path: Docpick + Qwen3.5-4B only. No DET fallback.
        self._worker = CvImportWorker(self.cv_path)
        connect_queued(self._worker.progress, self._on_progress)
        connect_queued(self._worker.finished, self._on_extracted)
        connect_queued(self._worker.failed, self._on_extract_failed)
        self._thread = start_worker(self._worker)

    def _on_progress(self, msg: str) -> None:
        self.status_label.setText(msg)

    def _on_extracted(self, parsed: object) -> None:
        self.progress.setRange(0, 1)
        self.progress.setValue(1)
        try:
            self.parsed = filter_parsed_for_import(parsed if isinstance(parsed, dict) else {})
            if self.parsed.get("needs_manual_review"):
                QMessageBox.information(
                    self,
                    tr("profile.cv"),
                    tr("cv_import.needs_review"),
                )
            self.incoming = parsed_to_qualifications(self.parsed)
            self.personal_incoming = personal_from_parsed(self.parsed)
            self.status_label.setText(tr("cv_import.extract_done"))
            self.ok_btn.setEnabled(True)
            self._refresh_preview()
        except Exception as exc:  # noqa: BLE001
            self._on_extract_failed(str(exc))

    def _on_extract_failed(self, message: str) -> None:
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.status_label.setText(tr("cv_import.read_error"))
        self.preview.setPlainText(
            f"{tr('cv_import.read_error')}\n{message}\n\n{tr('cv_import.manual_hint')}"
        )
        self.parsed = None
        self.incoming = None
        self.ok_btn.setEnabled(False)

    def _on_reject(self) -> None:
        if self._worker is not None:
            self._worker.request_cancel()
        self.reject()

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._worker is not None:
            self._worker.request_cancel()
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
            pipe = (self.parsed or {}).get("pipeline") or "docpick_qwen35_4b"
            lines.append(f"• {pipe}")
            if intel not in {"", "docpick_qwen35"}:
                lines.append(f"• Status: {intel}")
            if (self.parsed or {}).get("needs_manual_review"):
                lines.append(f"• {tr('cv_import.needs_review')}")
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
            label = QLabel(
                f"{c.label}\n{tr('cv_import.current')}: {c.current_value}\nCV: {c.incoming_value}"
            )
            label.setWordWrap(True)
            self.conflict_form.addRow(label, box)
            self._conflict_widgets[c.field] = box

    def _accept(self) -> None:
        if self.incoming is None or self.plan is None:
            self.reject()
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
