"""V2 Postfach — demo split layout, refresh icon, contextual actions.

Preserves Lifecycle association / draft / approval flows without a permanent
six-button control wall.
"""

from __future__ import annotations

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.database import Database
from desktop.design_system.a11y import set_accessible_name
from desktop.design_system.v2_chrome import ContentCard, EmptyStatePanel, StatusChip
from desktop.util.human_time import format_human_date_short, format_human_datetime
from desktop.i18n import i18n, tr
from desktop.pages.lifecycle import LifecyclePage
from desktop.services import ConfigService


def _assoc_chip(status: str) -> tuple[str, str]:
    status = (status or "").lower()
    if status in {"ambiguous", "review_required"}:
        return tr("inbox.chip_review"), "warn"
    if status in {"linked", "confirmed"}:
        return tr("inbox.chip_linked"), "ok"
    if status in {"unlinked", ""}:
        return tr("inbox.chip_unlinked"), "muted"
    return status or "—", "muted"


class InboxPage(QWidget):
    """Postfach surface matching approved demo composition."""

    def __init__(self, config_service: ConfigService, parent=None) -> None:
        super().__init__(parent)
        self.config_service = config_service
        self._emails: list[dict] = []
        self._selected: dict | None = None
        self._refreshing = False
        self._spin_phase = 0

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QHBoxLayout()
        header.setContentsMargins(16, 12, 16, 12)
        title_col = QVBoxLayout()
        self.title = QLabel()
        self.title.setObjectName("PageTitle")
        self.subtitle = QLabel()
        self.subtitle.setObjectName("PageSubtitle")
        title_col.addWidget(self.title)
        title_col.addWidget(self.subtitle)
        header.addLayout(title_col, stretch=1)
        self.account_chip = QLabel()
        self.account_chip.setObjectName("BadgeMuted")
        header.addWidget(self.account_chip)
        self.refresh_btn = QToolButton()
        self.refresh_btn.setObjectName("SecondaryButton")
        self.refresh_btn.setToolTip(tr("inbox.refresh_tooltip"))
        self.refresh_btn.clicked.connect(self._on_refresh)
        set_accessible_name(self.refresh_btn, tr("inbox.refresh_tooltip"))
        header.addWidget(self.refresh_btn)
        self.refresh_error = QLabel()
        self.refresh_error.setObjectName("WarningLabel")
        self.refresh_error.hide()
        header.addWidget(self.refresh_error)
        root.addLayout(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        left = QWidget()
        left_l = QVBoxLayout(left)
        left_l.setContentsMargins(0, 0, 0, 0)
        left_l.setSpacing(0)
        search_bar = QHBoxLayout()
        search_bar.setContentsMargins(8, 8, 8, 8)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("inbox.search_placeholder"))
        self.search.textChanged.connect(self._reload_list)
        search_bar.addWidget(self.search)
        left_l.addLayout(search_bar)
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._on_select)
        left_l.addWidget(self.list, 1)
        self.empty_panel = EmptyStatePanel()
        self.empty_panel.setVisible(False)
        left_l.addWidget(self.empty_panel, 1)
        splitter.addWidget(left)

        right = QWidget()
        right_l = QVBoxLayout(right)
        right_l.setContentsMargins(16, 16, 16, 16)
        right_l.setSpacing(12)

        self.context_card = ContentCard()
        ctx = self.context_card.body()
        self.context_label = QLabel()
        self.context_label.setObjectName("KkHint")
        self.context_case = QLabel()
        self.context_case.setObjectName("NextActionTitle")
        self.context_case.setWordWrap(True)
        self.open_case_btn = QPushButton()
        self.open_case_btn.setObjectName("SecondaryButton")
        self.open_case_btn.clicked.connect(self._open_application)
        ctx_row = QHBoxLayout()
        ctx_col = QVBoxLayout()
        ctx_col.addWidget(self.context_label)
        ctx_col.addWidget(self.context_case)
        ctx_row.addLayout(ctx_col, stretch=1)
        ctx_row.addWidget(self.open_case_btn)
        ctx.addLayout(ctx_row)
        right_l.addWidget(self.context_card)

        mail_card = ContentCard()
        mail_body = mail_card.body()
        self.mail_subject = QLabel()
        self.mail_subject.setObjectName("PageTitle")
        self.mail_subject.setWordWrap(True)
        self.mail_chip = StatusChip("", kind="muted")
        subj_row = QHBoxLayout()
        subj_row.addWidget(self.mail_subject, stretch=1)
        subj_row.addWidget(self.mail_chip)
        mail_body.addLayout(subj_row)
        self.mail_meta = QLabel()
        self.mail_meta.setObjectName("PageSubtitle")
        self.mail_meta.setWordWrap(True)
        mail_body.addWidget(self.mail_meta)
        self.mail_body = QTextEdit()
        self.mail_body.setReadOnly(True)
        self.mail_body.setMinimumHeight(220)
        mail_body.addWidget(self.mail_body, 1)
        right_l.addWidget(mail_card, 1)

        action_bar = QFrame()
        action_bar.setObjectName("Card")
        ab = QHBoxLayout(action_bar)
        self.action_hint = QLabel()
        self.action_hint.setObjectName("KkHint")
        self.action_hint.setWordWrap(True)
        ab.addWidget(self.action_hint, stretch=1)
        self.primary_action = QPushButton()
        self.primary_action.setObjectName("PrimaryButton")
        self.primary_action.clicked.connect(self._on_primary)
        ab.addWidget(self.primary_action)
        self.more_btn = QToolButton()
        self.more_btn.setText("…")
        self.more_btn.setObjectName("SecondaryButton")
        self.more_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        set_accessible_name(self.more_btn, tr("inbox.more_actions"))
        self._more_menu = QMenu(self)
        self.more_btn.setMenu(self._more_menu)
        ab.addWidget(self.more_btn)
        right_l.addWidget(action_bar)

        # Embedded lifecycle keeps approval/guenther methods; hide crowded chrome.
        self.lifecycle = LifecyclePage(config_service)
        self.lifecycle.set_embedded_inbox_mode(True)
        self.lifecycle.hide()
        self.lifecycle.guenther_bar.hide()  # contextual actions live on our bar, not a capability wall
        right_l.addWidget(self.lifecycle.approval)
        # Do not add guenther_bar to layout — permanent wall violates demo density.
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([360, 640])
        root.addWidget(splitter, 1)

        self._spin_timer = QTimer(self)
        self._spin_timer.setInterval(120)
        self._spin_timer.timeout.connect(self._tick_spin)

        self.retranslate_ui()
        self._clear_detail()

    def retranslate_ui(self) -> None:
        self.title.setText(tr("nav.inbox"))
        self.subtitle.setText(tr("inbox.subtitle"))
        self.search.setPlaceholderText(tr("inbox.search_placeholder"))
        self.refresh_btn.setText("↻")
        self.refresh_btn.setToolTip(tr("inbox.refresh_tooltip"))
        set_accessible_name(self.refresh_btn, tr("inbox.refresh_tooltip"))
        self.context_label.setText(tr("inbox.linked_application"))
        self.open_case_btn.setText(tr("inbox.open_application"))
        self.account_chip.setText(tr("inbox.mirrored_account"))
        self.empty_panel.set_texts(tr("inbox.empty_title"), tr("inbox.empty_body"))
        if hasattr(self.lifecycle, "retranslate"):
            self.lifecycle.retranslate()
        self._rebuild_more_menu()
        self._reload_list()

    def _rebuild_more_menu(self) -> None:
        """Populate overflow from selected email state — never the full capability set."""
        self._more_menu.clear()
        email = self._selected
        if not email:
            return
        for label, slot in self._contextual_actions(email):
            if slot is self._on_primary:
                continue  # primary lives on the bar
            self._more_menu.addAction(label, slot)

    def _email_kind(self, email: dict) -> str:
        cat = (email.get("category") or email.get("lifecycle_class") or "").lower()
        if cat in {"interview", "interview_invite", "interview_reschedule"}:
            return "interview"
        if cat in {"rejection", "reject"}:
            return "rejection"
        if cat in {"offer"}:
            return "offer"
        if cat in {"confirmation", "application_confirmation", "receipt"}:
            return "confirmation"
        return "generic"

    def _contextual_actions(self, email: dict) -> list[tuple[str, object]]:
        """Return (label, callable) pairs appropriate for this message."""
        status = (email.get("association_status") or "").lower()
        kind = self._email_kind(email)
        case_id = (email.get("case_id") or "").strip()
        actions: list[tuple[str, object]] = []

        if status in {"ambiguous", "review_required"}:
            actions.append((tr("inbox.action_review_association"), self._action_link))
        elif status in {"unlinked", ""} and not case_id:
            actions.append((tr("lifecycle.link_email"), self._action_link))

        if case_id:
            actions.append((tr("inbox.open_application"), self._open_application))

        # Reply draft — only when responding makes sense (not rejection/confirmation-only)
        if (
            case_id
            and status not in {"ambiguous", "review_required"}
            and kind in {"interview", "offer", "generic"}
        ):
            actions.append((tr("lifecycle.draft_reply"), self._action_draft))

        # Interview actions only for real interview domain state
        if kind == "interview" and case_id:
            actions.append((tr("lifecycle.interview_prep"), self._action_prep))
            actions.append((tr("lifecycle.calendar_proposal"), self._action_calendar))

        return actions

    def _apply_contextual_chrome(self, email: dict) -> None:
        actions = self._contextual_actions(email)
        if not actions:
            self.primary_action.setEnabled(False)
            self.primary_action.setText(tr("inbox.action_prepare_reply"))
            self.action_hint.setText("")
            self._rebuild_more_menu()
            return
        primary_label, primary_slot = actions[0]
        self.primary_action.setText(primary_label)
        self.primary_action.setEnabled(True)
        self._primary_slot = primary_slot
        status = (email.get("association_status") or "").lower()
        if status in {"ambiguous", "review_required"}:
            self.action_hint.setText(tr("inbox.hint_needs_association"))
        elif self._email_kind(email) == "interview":
            self.action_hint.setText(tr("inbox.hint_interview"))
        elif primary_slot == self._action_draft:
            self.action_hint.setText(tr("inbox.hint_prepare_reply"))
        else:
            self.action_hint.setText("")
        self._rebuild_more_menu()
        self.more_btn.setVisible(len(actions) > 1)

    def refresh(self) -> None:
        self._reload_list()
        if hasattr(self.lifecycle, "refresh"):
            self.lifecycle.refresh()

    def _on_refresh(self) -> None:
        if self._refreshing:
            return
        self._refreshing = True
        self.refresh_btn.setEnabled(False)
        self.refresh_error.hide()
        self._spin_timer.start()
        try:
            self.refresh()
        except Exception as exc:  # noqa: BLE001 — surface sync failures calmly
            self.refresh_error.setText(tr("inbox.refresh_failed"))
            self.refresh_error.setToolTip(str(exc))
            self.refresh_error.show()
        finally:
            self._spin_timer.stop()
            self.refresh_btn.setText("↻")
            self.refresh_btn.setEnabled(True)
            self._refreshing = False

    def _tick_spin(self) -> None:
        frames = ("↻", "⟳", "↺", "⟲")
        self._spin_phase = (self._spin_phase + 1) % len(frames)
        self.refresh_btn.setText(frames[self._spin_phase])

    def _db(self) -> Database:
        return Database(self.config_service.load().db_path)

    def _reload_list(self) -> None:
        db = self._db()
        self._emails = db.list_inbox_emails(limit=200, query=self.search.text())
        self.list.clear()
        for email in self._emails:
            sender = (email.get("sender") or "—").split("<")[0].strip() or "—"
            subject = email.get("subject") or "—"
            status = email.get("association_status") or ""
            chip, _kind = _assoc_chip(status)
            when = format_human_date_short(
                email.get("received_at") or email.get("created_at"),
                lang=i18n.language,
            )
            item = QListWidgetItem(f"{sender}\n{subject}\n{chip} · {when}")
            item.setData(Qt.ItemDataRole.UserRole, email.get("id"))
            self.list.addItem(item)
        if self._emails:
            self.list.setVisible(True)
            self.empty_panel.setVisible(False)
            self.list.setCurrentRow(0)
        else:
            self.list.setVisible(False)
            self.empty_panel.setVisible(True)
            self._clear_detail()

    def _on_select(self, row: int) -> None:
        if row < 0 or row >= len(self._emails):
            self._clear_detail()
            return
        self._selected = self._emails[row]
        self._bind_detail(self._selected)
        # Sync lifecycle email table selection for prepare_link_email
        email_id = self._selected.get("id") or ""
        for r in range(self.lifecycle.emails.rowCount()):
            item = self.lifecycle.emails.item(r, 3)
            if item and item.text() == email_id:
                self.lifecycle.emails.selectRow(r)
                break

    def _clear_detail(self) -> None:
        self._selected = None
        self._primary_slot = None
        self.mail_subject.setText(tr("inbox.no_selection_title"))
        self.mail_meta.setText(tr("inbox.no_selection_body"))
        self.mail_body.clear()
        self.mail_chip.set_status(tr("inbox.chip_unlinked"), kind="muted")
        self.context_case.setText("—")
        self.open_case_btn.setEnabled(False)
        self.open_case_btn.setVisible(False)
        self.primary_action.setEnabled(False)
        self.primary_action.setText(tr("inbox.action_prepare_reply"))
        self.action_hint.setText("")
        self._more_menu.clear()
        self.more_btn.setVisible(False)

    def _bind_detail(self, email: dict) -> None:
        self.mail_subject.setText(email.get("subject") or "—")
        sender = email.get("sender") or "—"
        when = format_human_datetime(
            email.get("received_at") or email.get("created_at"),
            lang=i18n.language,
        )
        self.mail_meta.setText(f"{sender}\n{when}")
        self.mail_body.setPlainText(email.get("body_text") or "")
        chip, kind = _assoc_chip(email.get("association_status") or "")
        self.mail_chip.set_status(chip, kind=kind)
        case_id = email.get("case_id") or ""
        if case_id:
            case = self._db().get_case(case_id)
            if case:
                self.context_case.setText(f"{case.position} · {case.company}")
                self.open_case_btn.setEnabled(True)
                self.open_case_btn.setVisible(True)
            else:
                self.context_case.setText(case_id)
                self.open_case_btn.setEnabled(False)
                self.open_case_btn.setVisible(False)
        else:
            self.context_case.setText(tr("inbox.no_linked_case"))
            self.open_case_btn.setEnabled(False)
            self.open_case_btn.setVisible(False)
        self._apply_contextual_chrome(email)

    def _on_primary(self) -> None:
        if not self._selected:
            return
        slot = getattr(self, "_primary_slot", None)
        if callable(slot):
            slot()
            return
        status = (self._selected.get("association_status") or "").lower()
        if status in {"ambiguous", "review_required"}:
            self._action_link()
        else:
            self._action_draft()

    def _action_link(self) -> None:
        self.lifecycle.refresh()
        email = self._selected or {}
        email_id = email.get("id") or ""
        if not email_id:
            QMessageBox.information(self, tr("nav.inbox"), tr("lifecycle.select_email"))
            return
        from desktop.widgets.association_review_dialog import AssociationReviewDialog

        db = self._db()
        cases = db.list_cases(limit=100)
        candidates = [
            {
                "id": c.id,
                "company": c.company,
                "position": c.position,
                "updated_at": c.updated_at,
                "created_at": getattr(c, "created_at", ""),
            }
            for c in cases
        ]
        dlg = AssociationReviewDialog(
            subject=email.get("subject") or "",
            sender=email.get("sender") or "",
            excerpt=email.get("body_text") or "",
            candidates=candidates,
            parent=self,
        )
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        case_id = dlg.selected_case_id
        if case_id is None:
            return
        if case_id == "":
            # Explicit "none" — leave unlinked; do not guess.
            QMessageBox.information(self, tr("nav.inbox"), tr("assoc.left_unlinked"))
            return
        self.lifecycle.prepare_link_email_ids(
            email_id=str(email_id),
            case_id=str(case_id),
            subject=email.get("subject") or "",
            sender=email.get("sender") or "",
        )

    def _action_draft(self) -> None:
        case_id = (self._selected or {}).get("case_id") or ""
        if case_id:
            # Select matching case row for lifecycle draft helper
            for r in range(self.lifecycle.cases.rowCount()):
                item = self.lifecycle.cases.item(r, 4)
                if item and item.text() == case_id:
                    self.lifecycle.cases.selectRow(r)
                    break
        self.lifecycle.prepare_followup_draft()

    def _action_calendar(self) -> None:
        self.lifecycle.prepare_calendar_proposal()

    def _action_prep(self) -> None:
        self.lifecycle.show_prep()

    def _action_followups(self) -> None:
        self.lifecycle.generate_followups()

    def _open_application(self) -> None:
        case_id = (self._selected or {}).get("case_id") or ""
        if not case_id:
            return
        parent = self.window()
        if parent is not None and hasattr(parent, "navigate_to"):
            parent.navigate_to("nav.applications")  # type: ignore[attr-defined]
