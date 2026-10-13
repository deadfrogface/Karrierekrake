from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QLineEdit, QPushButton, QWidget, QVBoxLayout

from desktop.design_system.a11y import (
    annotate_button, annotate_error_text, bind_label,
    collect_tab_focusable, ensure_keyboard_focusable,
)


def test_accessibility_form_label_and_keyboard_focus(qtbot):
    root = QWidget()
    layout = QVBoxLayout(root)
    label = QLabel("&Berufsziel")
    field = QLineEdit()
    field.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    layout.addWidget(label)
    layout.addWidget(field)
    bind_label(label, field)
    ensure_keyboard_focusable(field)
    qtbot.addWidget(root)
    root.show()
    assert label.buddy() is field
    assert field.accessibleName() == "Berufsziel"
    assert field in collect_tab_focusable(root)


def test_accessibility_button_has_name_and_focus(qtbot):
    button = QPushButton("&Weiter")
    button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    annotate_button(button, description="Zum nächsten Einrichtungsschritt")
    qtbot.addWidget(button)
    assert button.accessibleName() == "Weiter"
    assert button.accessibleDescription() == "Zum nächsten Einrichtungsschritt"
    assert button.focusPolicy() != Qt.FocusPolicy.NoFocus


def test_error_message_is_not_color_only(qtbot):
    label = QLabel()
    qtbot.addWidget(label)
    annotate_error_text(label, "Download unterbrochen")
    assert label.text() == "Download unterbrochen"
    assert "Download unterbrochen" in label.accessibleDescription()
    assert label.objectName() == "KkErrorText"
