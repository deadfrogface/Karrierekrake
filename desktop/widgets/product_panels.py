"""Reusable explainable-fit, timeline, and approval widgets (bind view-models only)."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from desktop.i18n import tr
from desktop.viewmodels.approvals import ApprovalActionViewModel, GuentherActionViewModel
from desktop.viewmodels.case_timeline import (
    CaseTimelineViewModel,
    TIMELINE_STAGE_ORDER,
    primary_path_progress,
)
from desktop.viewmodels.job_fit import JobFitViewModel


_HEADLINE_I18N = {
    "sehr_passend": "fit.sehr_passend",
    "passend": "fit.passend",
    "teilweise_passend": "fit.teilweise_passend",
    "nicht_passend": "fit.nicht_passend",
    "unbekannt": "fit.unbekannt",
}


class JobFitPanel(QFrame):
    """Explainable fit card — headline + ✓/⚠ bullets, no fake %."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("DetailPanel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)
        self.headline = QLabel()
        self.headline.setObjectName("NextActionTitle")
        self.headline.setWordWrap(True)
        self.body = QLabel()
        self.body.setWordWrap(True)
        self.body.setObjectName("PageSubtitle")
        self.sort_hint = QLabel()
        self.sort_hint.setObjectName("PageSubtitle")
        layout.addWidget(self.headline)
        layout.addWidget(self.body)
        layout.addWidget(self.sort_hint)
        self.clear()

    def clear(self) -> None:
        self.headline.setText(tr("fit.empty"))
        self.body.clear()
        self.sort_hint.clear()

    def bind(self, vm: JobFitViewModel | None) -> None:
        if vm is None:
            self.clear()
            return
        key = _HEADLINE_I18N.get(vm.headline_key, "fit.unbekannt")
        self.headline.setText(tr(key))
        lines = vm.primary_lines(limit=10)
        self.body.setText("\n".join(lines) if lines else tr("fit.no_bullets"))
        # Sort score is optional secondary hint — never "84 % Match".
        if vm.sort_score is not None and vm.sort_score > 0:
            self.sort_hint.setText(tr("fit.sort_hint", n=int(vm.sort_score)))
        else:
            self.sort_hint.clear()


class CaseTimelinePanel(QFrame):
    """Canonical lifecycle path + event log with source/time/corrections."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("DetailPanel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        self.status = QLabel()
        self.status.setObjectName("NextActionTitle")
        self.path = QLabel()
        self.path.setWordWrap(True)
        self.path.setObjectName("PageSubtitle")
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(120)
        layout.addWidget(self.status)
        layout.addWidget(self.path)
        layout.addWidget(self.log, 1)
        self.clear()

    def clear(self) -> None:
        self.status.setText(tr("timeline.empty"))
        self.path.clear()
        self.log.clear()

    def bind(self, vm: CaseTimelineViewModel | None) -> None:
        if vm is None:
            self.clear()
            return
        self.status.setText(f"{tr(vm.status_key)} ({vm.status})")
        parts: list[str] = []
        for event_type, reached in primary_path_progress(vm.stage_reached):
            # Display short German path tokens from i18n stage keys.
            from desktop.viewmodels.case_timeline import STAGE_I18N

            label = tr(STAGE_I18N.get(event_type, "timeline.stage.other"))
            parts.append(f"{'●' if reached else '○'} {label}")
        self.path.setText(" → ".join(parts) if parts else tr("timeline.no_events"))
        lines: list[str] = []
        for e in vm.entries:
            when = (e.occurred_at or e.recorded_at or "")[:19]
            src = e.source or "—"
            stage = tr(e.stage_key)
            corr = f" [{tr('timeline.correction')}]" if e.is_correction else ""
            extra = f" — {e.summary}" if e.summary else ""
            lines.append(f"{when} · {stage} · {src}{corr}{extra}")
        self.log.setPlainText("\n".join(lines) if lines else tr("timeline.no_events"))


class ApprovalPanel(QFrame):
    """Explicit approve / cancel for consequential external actions."""

    approved = Signal()
    cancelled = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("HeroCard")
        self._vm: ApprovalActionViewModel | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        self.title = QLabel()
        self.title.setObjectName("NextActionTitle")
        self.title.setWordWrap(True)
        self.body = QTextEdit()
        self.body.setReadOnly(True)
        self.body.setMaximumHeight(140)
        self.gate = QLabel()
        self.gate.setWordWrap(True)
        self.gate.setObjectName("PageSubtitle")
        row = QHBoxLayout()
        self.approve_btn = QPushButton()
        self.approve_btn.setObjectName("PrimaryButton")
        self.cancel_btn = QPushButton()
        self.cancel_btn.setObjectName("SecondaryButton")
        self.approve_btn.clicked.connect(self._on_approve)
        self.cancel_btn.clicked.connect(self.cancelled.emit)
        row.addWidget(self.approve_btn)
        row.addWidget(self.cancel_btn)
        row.addStretch()
        layout.addWidget(self.title)
        layout.addWidget(self.body)
        layout.addWidget(self.gate)
        layout.addLayout(row)
        self.setVisible(False)
        self.retranslate()

    def retranslate(self) -> None:
        self.approve_btn.setText(tr("approval.approve"))
        self.cancel_btn.setText(tr("approval.cancel"))
        if self._vm is not None:
            self.bind(self._vm)

    def bind(self, vm: ApprovalActionViewModel | None) -> None:
        self._vm = vm
        if vm is None:
            self.setVisible(False)
            return
        self.setVisible(True)
        self.title.setText(tr(vm.title_key))
        self.body.setPlainText(vm.body)
        if vm.blocked_reason:
            self.gate.setText(tr("approval.blocked", reason=vm.blocked_reason))
            self.approve_btn.setEnabled(False)
        elif vm.approved:
            self.gate.setText(tr("approval.already_approved"))
            self.approve_btn.setEnabled(False)
        else:
            self.gate.setText(tr("approval.needs_explicit"))
            self.approve_btn.setEnabled(True)

    def _on_approve(self) -> None:
        # Never auto-approve — only emit after explicit click.
        if self._vm is None or self._vm.blocked_reason:
            return
        self.approved.emit()

    @property
    def current(self) -> ApprovalActionViewModel | None:
        return self._vm


class GuentherActionsBar(QWidget):
    """Contextual Günther actions — not a free-form chatbot."""

    action_triggered = Signal(str)  # GuentherActionKind value

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._buttons: dict[str, QPushButton] = {}
        self.hint = QLabel()
        self.hint.setObjectName("PageSubtitle")
        self.hint.setWordWrap(True)
        self._layout.addWidget(self.hint)
        self._layout.addStretch()

    def bind(self, actions: tuple[GuentherActionViewModel, ...]) -> None:
        for btn in list(self._buttons.values()):
            self._layout.removeWidget(btn)
            btn.deleteLater()
        self._buttons.clear()
        enabled_any = False
        for action in actions:
            btn = QPushButton(tr(action.title_key))
            btn.setObjectName("SecondaryButton")
            btn.setEnabled(action.enabled)
            btn.setToolTip(tr(action.hint_key))
            kind = action.kind.value
            btn.clicked.connect(lambda checked=False, k=kind: self.action_triggered.emit(k))
            self._buttons[kind] = btn
            self._layout.insertWidget(self._layout.count() - 1, btn)
            enabled_any = enabled_any or action.enabled
        self.hint.setText(tr("guenther.bar_hint") if enabled_any else tr("guenther.bar_disabled"))
