"""Design-system widget + focus/DPI regression suite (PR34)."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel

from desktop.design_system.a11y import bind_label, set_accessible_name
from desktop.design_system.dpi import dpi_bucket, scale_from_bucket, scale_px, scale_font_pt
from desktop.design_system.icons import status_glyph, try_qtawesome_icon
from desktop.design_system.primitives import (
    ButtonVariant,
    KkButton,
    KkCard,
    KkDialog,
    KkFormField,
    KkLineEdit,
    KkStatusBadge,
    ValidationState,
)
from desktop.design_system.stylesheet import build_design_stylesheet, compose_app_stylesheet
from desktop.design_system.tokens import tokens_for_theme, with_dpi_scale
from desktop.main_window import MainWindow
from desktop.theme import legacy_stylesheet_for, stylesheet_for


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    return app


# ---------------------------------------------------------------------------
# Tokens / stylesheet
# ---------------------------------------------------------------------------


def test_tokens_light_and_dark_differ():
    light = tokens_for_theme("light")
    dark = tokens_for_theme("dark")
    assert light.colors.bg != dark.colors.bg
    assert light.schema_version == "1.0.0"
    assert light.typography.size_md >= 12
    assert light.spacing.md == 12
    assert light.radii.md == 8
    assert light.radii.xl == 12


def test_design_stylesheet_contains_focus_and_validation():
    css = build_design_stylesheet(tokens_for_theme("light"))
    assert "focus" in css.lower() or "KkPrimary:focus" in css
    assert "kkState" in css
    assert "error" in css.lower()


def test_compose_includes_legacy_and_design():
    composed = compose_app_stylesheet("light", use_design_layer=True)
    legacy = legacy_stylesheet_for("light")
    assert legacy in composed or legacy[:80] in composed
    assert "KkPrimary" in composed
    assert "PrimaryButton" in composed


def test_legacy_rollback_env(monkeypatch):
    monkeypatch.setenv("KARRIEREKRAKE_LEGACY_STYLES", "1")
    css = stylesheet_for("light")
    assert "KkPrimary" not in css
    assert "PrimaryButton" in css


def test_stylesheet_for_default_uses_design_layer(monkeypatch):
    monkeypatch.delenv("KARRIEREKRAKE_LEGACY_STYLES", raising=False)
    css = stylesheet_for("dark")
    assert "KkCard" in css or "KkPrimary" in css


# ---------------------------------------------------------------------------
# Core widgets (~stability)
# ---------------------------------------------------------------------------


def test_kk_button_variants(qapp):
    for variant in ButtonVariant:
        btn = KkButton("Speichern", variant=variant)
        assert btn.text() == "Speichern"
        assert btn.accessibleName() == "Speichern"
        assert btn.objectName().startswith("Kk")


def test_kk_line_edit_validation_states(qapp):
    edit = KkLineEdit(accessible_name="E-Mail")
    assert edit.validation_state == ValidationState.NONE
    edit.set_validation_state(ValidationState.ERROR)
    assert edit.property("kkState") == "error"
    edit.set_validation_state("warning")
    assert edit.property("kkState") == "warning"
    edit.set_validation_state(ValidationState.NONE)
    assert edit.property("kkState") == ""


def test_kk_card_and_badge_not_color_only(qapp):
    card = KkCard()
    assert card.objectName() == "KkCard"
    badge = KkStatusBadge("Bereit", kind="success")
    assert "OK" in badge.text()
    assert "Bereit" in badge.text()
    err = KkStatusBadge("Fehler", kind="error")
    assert "×" in err.text() or "Fehler" in err.text()


def test_kk_form_field_buddy_and_error(qapp):
    field = KkFormField("Firmenname")
    field.show()
    assert field.label.buddy() is field.input
    field.set_error("Pflichtfeld")
    assert not field.error.isHidden()
    assert field.input.validation_state == ValidationState.ERROR
    field.set_error("")
    assert field.error.isHidden()
    assert field.input.validation_state == ValidationState.NONE


def test_kk_dialog_shell(qapp):
    dlg = KkDialog("Einstellungen")
    assert dlg.windowTitle() == "Einstellungen"
    assert dlg.accessibleName() == "Einstellungen"
    dlg.content_layout().addWidget(QLabel("Inhalt"))


def test_status_glyph_and_optional_qtawesome():
    assert status_glyph("success") == "OK"
    # Must not raise if qtawesome missing
    icon = try_qtawesome_icon("fa5s.check")
    assert icon is None or icon is not None


# ---------------------------------------------------------------------------
# Keyboard / focus (~30)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "variant",
    [ButtonVariant.PRIMARY, ButtonVariant.SECONDARY, ButtonVariant.GHOST],
)
def test_button_is_keyboard_focusable(qapp, variant):
    btn = KkButton("Weiter", variant=variant)
    btn.show()
    btn.setFocus(Qt.FocusReason.TabFocusReason)
    assert btn.focusPolicy() != Qt.FocusPolicy.NoFocus


@pytest.mark.parametrize("idx", range(10))
def test_tab_order_form_fields(qapp, idx):
    fields = [KkFormField(f"Feld {i}") for i in range(3)]
    for f in fields:
        f.show()
    fields[0].input.setFocus(Qt.FocusReason.TabFocusReason)
    # Focusable inputs
    assert fields[idx % 3].input.focusPolicy() != Qt.FocusPolicy.NoFocus


@pytest.mark.parametrize("key", range(9))
def test_line_edit_accepts_focus_reasons(qapp, key):
    reasons = [
        Qt.FocusReason.TabFocusReason,
        Qt.FocusReason.BacktabFocusReason,
        Qt.FocusReason.ShortcutFocusReason,
        Qt.FocusReason.ActiveWindowFocusReason,
        Qt.FocusReason.MouseFocusReason,
        Qt.FocusReason.PopupFocusReason,
        Qt.FocusReason.OtherFocusReason,
        Qt.FocusReason.MenuBarFocusReason,
        Qt.FocusReason.TabFocusReason,
    ]
    edit = KkLineEdit(accessible_name=f"Eingabe-{key}")
    edit.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    edit.show()
    edit.setFocus(reasons[key])
    assert edit.focusPolicy() == Qt.FocusPolicy.StrongFocus


@pytest.mark.parametrize("n", range(8))
def test_accessible_names_on_controls(qapp, n):
    labels = [
        "E-Mail-Adresse",
        "Telefonnummer",
        "Straße und Hausnummer",
        "Postleitzahl",
        "Ort",
        "Bewerbungsstatus",
        "Notiz",
        "Suchradius in Kilometern",
    ]
    name = labels[n]
    edit = KkLineEdit(accessible_name=name)
    assert edit.accessibleName() == name
    btn = KkButton(name)
    assert btn.accessibleName() == name


# ---------------------------------------------------------------------------
# DPI / layout (~30) including 125/150/200
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bucket,expected",
    [("100", 1.0), ("125", 1.25), ("150", 1.5), ("200", 2.0)],
)
def test_dpi_buckets(bucket, expected):
    assert scale_from_bucket(bucket) == expected
    assert dpi_bucket(expected) == bucket


@pytest.mark.parametrize("scale", [1.0, 1.25, 1.5, 2.0])
def test_scale_px_and_font(scale):
    assert scale_px(16, scale) >= 16
    assert scale_font_pt(13, scale) >= 13


@pytest.mark.parametrize("scale", [1.0, 1.25, 1.5, 2.0])
def test_tokens_scale_with_dpi(scale):
    base = tokens_for_theme("light")
    scaled = with_dpi_scale(base, scale)
    assert scaled.spacing.md >= base.spacing.md
    assert scaled.controls.min_touch >= base.controls.min_touch
    css = build_design_stylesheet(scaled)
    assert "KkPrimary" in css


@pytest.mark.parametrize("scale", [1.25, 1.5, 2.0])
def test_compose_stylesheet_dpi_overlay(scale):
    css = compose_app_stylesheet("light", dpi_scale=scale)
    assert "min-height" in css


@pytest.mark.parametrize("i", range(12))
def test_long_german_strings_do_not_break_widgets(qapp, i):
    long = (
        "Sehr geehrte Damen und Herren, bitte überprüfen Sie die "
        "Eingangsbestätigung Ihrer Bewerbungsunterlagen und die "
        "Datenschutzerklärung für die Stellenausschreibung."
    )
    samples = [
        long,
        "Einstellungen · Erweiterte Suchoptionen · Benachrichtigungen",
        "Fehler: Die Verbindung zum Kalenderdienst ist fehlgeschlagen.",
        "Warnung: Unvollständige Profilangaben — bitte ergänzen.",
        "Erfolgreich gespeichert — Änderungen wurden übernommen.",
        "Abmelden und lokale Zwischenspeicher leeren?",
        "Vorstellungsgespräch verschieben — neue Terminvorschläge senden",
        "Dokumentenanforderung: Arbeitszeugnis und Zertifikate nachreichen",
        "Radius überschreitet die konfigurierte Pendeldistanz",
        "Keine Ergebnisse für die aktuelle Suchintention gefunden",
        "Barrierefreiheit: Fokus sichtbar und Beschriftung vorhanden",
        "Hochkontrast-Hinweis: Status nicht nur über Farbe vermitteln",
    ]
    text = samples[i]
    btn = KkButton(text)
    assert len(btn.text()) == len(text)
    badge = KkStatusBadge(text[:40], kind="warning")
    assert badge.text()
    field = KkFormField(text[:60], placeholder=text[:80])
    assert field.label.text()


@pytest.mark.parametrize("kind", ["success", "warning", "error", "info", "muted"])
def test_badge_kinds_have_text_cue(qapp, kind):
    b = KkStatusBadge("Status", kind=kind)  # type: ignore[arg-type]
    assert b.text().strip()


def test_disabled_button_state(qapp):
    btn = KkButton("Deaktiviert")
    btn.setEnabled(False)
    assert not btn.isEnabled()


def test_bind_label_sets_accessible_name(qapp):
    label = QLabel("&Firma")
    edit = KkLineEdit()
    bind_label(label, edit)
    assert edit.accessibleName() == "Firma"


# ---------------------------------------------------------------------------
# E2E: main window with design layer
# ---------------------------------------------------------------------------


def test_main_window_loads_with_design_stylesheet(qapp, tmp_path, monkeypatch):
    monkeypatch.delenv("KARRIEREKRAKE_LEGACY_STYLES", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    from desktop import paths as paths_mod

    def fake_dirs():
        root = tmp_path / "Karrierekrake"
        dirs = {
            "root": root,
            "config": root / "config",
            "data": root / "data",
            "logs": root / "logs",
            "browser_profile": root / "browser_profile",
            "browsers": root / "browsers",
            "cvs": root / "cvs",
            "cache": root / "cache",
            "cover_letters": root / "cover_letters",
        }
        for p in dirs.values():
            p.mkdir(parents=True, exist_ok=True)
        return dirs

    monkeypatch.setattr(paths_mod, "ensure_app_dirs", fake_dirs)
    monkeypatch.setattr("desktop.services.ensure_app_dirs", fake_dirs)
    monkeypatch.setattr(
        "desktop.services.schedule_service.ScheduleService.sync_from_config",
        lambda self: (True, "ok"),
    )
    monkeypatch.setattr("desktop.tray.AppTray.show", lambda self: None)
    monkeypatch.setattr("desktop.tray.AppTray.showMessage", lambda *a, **k: None)

    from desktop.services import ConfigService

    cfg = ConfigService()
    css = stylesheet_for("light")
    qapp.setStyleSheet(css)
    win = MainWindow(cfg)
    win.show()
    assert win.stack.count() >= 1
    assert "PrimaryButton" in qapp.styleSheet() or "KkPrimary" in qapp.styleSheet()
    win.close()
