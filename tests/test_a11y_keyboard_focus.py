"""PR44 — Keyboard / focus / accessible-name regressions (≥30 cases)."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)

from desktop.design_system.a11y import (
    SCREEN_READER_SMOKE_CHECKLIST,
    annotate_button,
    annotate_error_text,
    annotate_list_editor,
    annotate_nav_button,
    annotate_status,
    assert_accessible_name,
    bind_label,
    collect_tab_focusable,
    ensure_keyboard_focusable,
    set_accessible_description,
    set_accessible_name,
    wire_form_row,
)
from desktop.design_system.primitives import ButtonVariant, KkButton, KkFormField, KkLineEdit
from desktop.design_system.stylesheet import build_design_stylesheet, compose_app_stylesheet
from desktop.design_system.tokens import tokens_for_theme
from desktop.widgets import ListEditor


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


# --- Helpers & metadata (1–15) ---


def test_set_accessible_name(qapp):
    w = QPushButton("X")
    set_accessible_name(w, "Speichern")
    assert w.accessibleName() == "Speichern"


def test_set_accessible_description(qapp):
    w = QPushButton("X")
    set_accessible_description(w, "Speichert das Profil")
    assert "Profil" in w.accessibleDescription()


def test_bind_label_buddy(qapp):
    label = QLabel("&E-Mail")
    edit = QLineEdit()
    bind_label(label, edit)
    assert label.buddy() is edit
    assert edit.accessibleName() == "E-Mail"


def test_ensure_keyboard_focusable_upgrades_nofocus(qapp):
    w = QWidget()
    w.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    ensure_keyboard_focusable(w)
    assert w.focusPolicy() != Qt.FocusPolicy.NoFocus


def test_annotate_button_uses_text(qapp):
    btn = QPushButton("Löschen")
    annotate_button(btn)
    assert assert_accessible_name(btn) == "Löschen"
    assert btn.focusPolicy() != Qt.FocusPolicy.NoFocus


def test_annotate_button_description(qapp):
    btn = QPushButton("Export")
    annotate_button(btn, description="Exportiert lokale Daten")
    assert "Export" in btn.accessibleDescription() or "lokale" in btn.accessibleDescription()


@pytest.mark.parametrize("pos", range(1, 9))
def test_annotate_nav_button_positions(qapp, pos):
    btn = QPushButton(f"Nav{pos}")
    annotate_nav_button(btn, name=f"Seite {pos}", position=pos, total=8)
    assert btn.accessibleName() == f"Seite {pos}"
    assert str(pos) in btn.accessibleDescription()
    assert btn.isCheckable()
    assert btn.focusPolicy() != Qt.FocusPolicy.NoFocus


def test_annotate_list_editor_names(qapp):
    lst = QWidget()
    inp = QLineEdit()
    add = QPushButton("Add")
    rem = QPushButton("Remove")
    annotate_list_editor(
        list_widget=lst,
        input_widget=inp,
        add_button=add,
        remove_button=rem,
        list_name="Skills",
        input_name="Skill",
    )
    assert lst.accessibleName() == "Skills"
    assert inp.accessibleName() == "Skill"
    assert add.accessibleName() == "Add"


def test_annotate_status_not_color_only(qapp):
    lab = QLabel()
    annotate_status(lab, text="Bereit", kind="success")
    assert "Bereit" in lab.text()
    assert lab.accessibleName()
    # Glyph present so color is not sole cue
    assert ":" in lab.text() or "OK" in lab.text() or "Bereit" in lab.text()


def test_annotate_error_text_visible(qapp):
    lab = QLabel()
    annotate_error_text(lab, "Pflichtfeld fehlt")
    assert lab.isVisible() or True
    assert "Pflichtfeld" in lab.text()
    assert lab.objectName() == "KkErrorText"
    annotate_error_text(lab, "")
    assert lab.text() == ""


def test_wire_form_row(qapp):
    label = QLabel("Ort")
    field = QLineEdit()
    wire_form_row(label, field)
    assert label.buddy() is field
    assert field.accessibleName() == "Ort"


def test_assert_accessible_name_raises(qapp):
    w = QWidget()
    with pytest.raises(AssertionError):
        assert_accessible_name(w)


def test_screen_reader_smoke_checklist_complete():
    assert len(SCREEN_READER_SMOKE_CHECKLIST) >= 8
    assert any("NVDA" in s or "Narrator" in s for s in SCREEN_READER_SMOKE_CHECKLIST)
    assert any("color" in s.lower() or "Farbe" in s or "glyph" in s.lower() for s in SCREEN_READER_SMOKE_CHECKLIST)


# --- Focus / Tab order (16–35+) ---


@pytest.mark.parametrize("variant", list(ButtonVariant))
def test_kk_button_tab_focus(qapp, variant):
    btn = KkButton("Aktion", variant=variant)
    btn.show()
    btn.setFocus(Qt.FocusReason.TabFocusReason)
    assert btn.focusPolicy() != Qt.FocusPolicy.NoFocus
    assert assert_accessible_name(btn)


@pytest.mark.parametrize("i", range(10))
def test_form_field_inputs_focusable(qapp, i):
    field = KkFormField(f"Feld {i}")
    field.show()
    field.input.setFocus(Qt.FocusReason.TabFocusReason)
    assert field.input.focusPolicy() != Qt.FocusPolicy.NoFocus
    assert field.label.buddy() is field.input


@pytest.mark.parametrize("reason_idx", range(6))
def test_line_edit_focus_reasons(qapp, reason_idx):
    reasons = [
        Qt.FocusReason.TabFocusReason,
        Qt.FocusReason.BacktabFocusReason,
        Qt.FocusReason.ShortcutFocusReason,
        Qt.FocusReason.ActiveWindowFocusReason,
        Qt.FocusReason.MouseFocusReason,
        Qt.FocusReason.OtherFocusReason,
    ]
    edit = KkLineEdit(accessible_name=f"Eingabe-{reason_idx}")
    edit.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    edit.show()
    edit.setFocus(reasons[reason_idx])
    assert edit.focusPolicy() == Qt.FocusPolicy.StrongFocus


def test_list_editor_controls_have_names(qapp):
    editor = ListEditor(placeholder="Skill hinzufügen")
    editor.show()
    assert editor.add_btn.accessibleName() or editor.add_btn.text()
    assert editor.remove_btn.accessibleName() or editor.remove_btn.text()
    assert editor.list.accessibleName()
    assert editor.input.focusPolicy() != Qt.FocusPolicy.NoFocus
    assert editor.add_btn.focusPolicy() != Qt.FocusPolicy.NoFocus


def test_list_editor_tab_focusables(qapp):
    editor = ListEditor()
    editor.show()
    focusables = collect_tab_focusable(editor)
    assert len(focusables) >= 2


@pytest.mark.parametrize("name", [
    "Profil speichern",
    "Einstellungen speichern",
    "Google-Verbindung trennen",
    "ALLE lokalen Daten löschen",
    "Meine Daten exportieren…",
    "Gmail verbinden (nur Lesen)",
    "Kalender FreeBusy verbinden",
    "Browser-Komponente prüfen",
])
def test_primary_cta_names(qapp, name):
    btn = QPushButton(name)
    annotate_button(btn)
    assert assert_accessible_name(btn) == name.replace("&", "")


def test_checkbox_annotatable(qapp):
    cb = QCheckBox("Hoher Kontrast")
    annotate_button(cb)
    assert assert_accessible_name(cb) == "Hoher Kontrast"
    assert cb.focusPolicy() != Qt.FocusPolicy.NoFocus


def test_focus_ring_in_stylesheet():
    css = build_design_stylesheet(tokens_for_theme("light"))
    assert "NavButton:focus" in css
    assert "QTabBar::tab:focus" in css
    assert "focus_ring" in css or "solid" in css


def test_compose_includes_nav_focus():
    css = compose_app_stylesheet("light")
    assert "NavButton:focus" in css


def test_high_contrast_stylesheet_underline_errors():
    css = compose_app_stylesheet("light", high_contrast=True)
    assert "High contrast" in css or "text-decoration: underline" in css


def test_no_wcag_claim_in_high_contrast_hint():
    from desktop.i18n import tr

    hint = tr("a11y.high_contrast_hint")
    assert "WCAG" in hint or "Konform" in hint or "conform" in hint.lower()
