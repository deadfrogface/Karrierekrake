"""Confirm dialogs whose buttons always carry a text label (DE/EN via i18n).

``QMessageBox.question`` uses Qt standard buttons: their labels depend on a Qt
translator being installed and some platform styles render them icon-first.
Destructive and confirm flows must never rely on that.
"""

from __future__ import annotations

from PySide6.QtWidgets import QDialogButtonBox, QMessageBox, QWidget

from desktop.design_system.a11y import set_accessible_name
from desktop.i18n import tr

_STANDARD_LABEL_KEYS = {
    QDialogButtonBox.StandardButton.Ok: "btn.ok",
    QDialogButtonBox.StandardButton.Cancel: "btn.cancel",
    QDialogButtonBox.StandardButton.Close: "btn.close",
    QDialogButtonBox.StandardButton.Save: "btn.save",
}


def label_button_box(buttons: QDialogButtonBox) -> QDialogButtonBox:
    """Give standard dialog buttons i18n labels (independent of Qt translations)."""
    for standard, key in _STANDARD_LABEL_KEYS.items():
        btn = buttons.button(standard)
        if btn is not None:
            btn.setText(tr(key))
            set_accessible_name(btn, tr(key))
    return buttons


def build_confirm_box(
    parent: QWidget | None,
    title: str,
    text: str,
    *,
    confirm_text: str = "",
    cancel_text: str = "",
    informative: str = "",
    destructive: bool = False,
) -> tuple[QMessageBox, object, object]:
    """Return ``(box, confirm_button, cancel_button)`` without executing it."""
    box = QMessageBox(parent)
    box.setObjectName("KkConfirmDialog")
    box.setWindowTitle(title)
    box.setIcon(QMessageBox.Icon.Warning if destructive else QMessageBox.Icon.Question)
    box.setText(text)
    if informative:
        box.setInformativeText(informative)
    confirm_label = confirm_text or tr("dialog.confirm")
    cancel_label = cancel_text or tr("btn.cancel")
    role = QMessageBox.ButtonRole.DestructiveRole if destructive else QMessageBox.ButtonRole.AcceptRole
    confirm_btn = box.addButton(confirm_label, role)
    cancel_btn = box.addButton(cancel_label, QMessageBox.ButtonRole.RejectRole)
    set_accessible_name(confirm_btn, confirm_label)
    set_accessible_name(cancel_btn, cancel_label)
    # Destructive flows default to the safe choice (Enter must not delete).
    box.setDefaultButton(cancel_btn if destructive else confirm_btn)
    box.setEscapeButton(cancel_btn)
    return box, confirm_btn, cancel_btn


def confirm_action(
    parent: QWidget | None,
    title: str,
    text: str,
    *,
    confirm_text: str = "",
    cancel_text: str = "",
    informative: str = "",
    destructive: bool = False,
) -> bool:
    """Show a labeled confirm dialog; True only if the confirm button was clicked."""
    box, confirm_btn, _cancel_btn = build_confirm_box(
        parent,
        title,
        text,
        confirm_text=confirm_text,
        cancel_text=cancel_text,
        informative=informative,
        destructive=destructive,
    )
    box.exec()
    return box.clickedButton() is confirm_btn
