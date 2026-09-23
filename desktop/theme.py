"""Theme detection and light/dark stylesheets (Karrierekrake design system)."""

from __future__ import annotations

import sys

from desktop.branding import (
    COLOR_DARK_BG,
    COLOR_DARK_BORDER,
    COLOR_DARK_MUTED,
    COLOR_DARK_SURFACE,
    COLOR_DARK_TEXT,
    COLOR_ERROR,
    COLOR_LIGHT_BG,
    COLOR_LIGHT_BORDER,
    COLOR_LIGHT_MUTED,
    COLOR_LIGHT_SURFACE,
    COLOR_LIGHT_TEXT,
    COLOR_NAVY,
    COLOR_PRIMARY,
    COLOR_PRIMARY_HOVER,
    COLOR_SUCCESS,
    COLOR_TEAL,
    COLOR_WARN,
)


def detect_system_dark() -> bool:
    """Return True if Windows prefers dark mode. Failures fall back to light."""
    if sys.platform != "win32":
        return False
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        )
        value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        winreg.CloseKey(key)
        return int(value) == 0
    except Exception:
        return False


def resolve_theme(preference: str) -> str:
    pref = (preference or "system").lower()
    if pref == "dark":
        return "dark"
    if pref == "light":
        return "light"
    return "dark" if detect_system_dark() else "light"


LIGHT_STYLESHEET = f"""
QWidget {{
    font-family: "Segoe UI", "Calibri", sans-serif;
    font-size: 13px;
    color: {COLOR_LIGHT_TEXT};
}}
QMainWindow, QDialog, QWizard {{
    background: {COLOR_LIGHT_BG};
}}
QScrollArea {{
    border: none;
    background: transparent;
}}
QFrame#Sidebar {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 {COLOR_NAVY}, stop:1 #0A1520);
    border: none;
    min-width: 168px;
    max-width: 240px;
}}
QLabel#Brand {{
    color: #f4f7fa;
    font-size: 17px;
    font-weight: 700;
    letter-spacing: 0.2px;
}}
QLabel#BrandTagline {{
    color: rgba(244,247,250,0.72);
    font-size: 10px;
}}
QLabel#PageTitle {{
    font-size: 20px;
    font-weight: 700;
    color: {COLOR_NAVY};
}}
QLabel#KpiValue {{
    font-size: 32px;
    font-weight: 700;
    color: {COLOR_NAVY};
    letter-spacing: -0.5px;
}}
QLabel#PageSubtitle {{
    color: {COLOR_LIGHT_MUTED};
    font-size: 13px;
}}
QLabel#EmptyState {{
    color: {COLOR_LIGHT_MUTED};
    font-size: 14px;
    padding: 24px;
}}
QLabel#NextActionTitle {{
    font-size: 16px;
    font-weight: 700;
    color: {COLOR_NAVY};
}}
QLabel#BadgeOk, QLabel#BadgeWarn, QLabel#BadgeDanger, QLabel#BadgeMuted, QLabel#BadgeInfo {{
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 600;
}}
QLabel#BadgeOk {{ background: #d8efe8; color: {COLOR_SUCCESS}; }}
QLabel#BadgeWarn {{ background: #fce8d5; color: {COLOR_WARN}; }}
QLabel#BadgeDanger {{ background: #f5d6d6; color: {COLOR_ERROR}; }}
QLabel#BadgeMuted {{ background: #e6edf3; color: {COLOR_LIGHT_MUTED}; }}
QLabel#BadgeInfo {{ background: #d5f0eb; color: #0f5c54; }}
QPushButton#NavButton, QPushButton[objectName^="kk.nav."] {{
    text-align: left;
    padding: 10px 14px;
    border: none;
    border-radius: 6px;
    color: #d7e4ec;
    background: transparent;
}}
QPushButton#NavButton:hover, QPushButton[objectName^="kk.nav."]:hover {{
    background: rgba(255,255,255,0.08);
}}
QPushButton#NavButton:checked, QPushButton[objectName^="kk.nav."]:checked {{
    background: rgba(24, 169, 153, 0.40);
    color: #ffffff;
    font-weight: 600;
}}
QFrame#Card, QFrame#HeroCard, QFrame#DetailPanel {{
    background: {COLOR_LIGHT_SURFACE};
    border: 1px solid {COLOR_LIGHT_BORDER};
    border-radius: 10px;
}}
QFrame#HeroCard {{
    padding: 4px;
}}
QLabel#CardValue {{
    font-size: 22px;
    font-weight: 700;
    color: {COLOR_NAVY};
}}
QLabel#CardTitle {{
    color: {COLOR_LIGHT_MUTED};
    font-size: 12px;
}}
QPushButton#PrimaryButton {{
    background: {COLOR_PRIMARY};
    color: white;
    border: none;
    border-radius: 8px;
    padding: 10px 18px;
    font-weight: 600;
}}
QPushButton#PrimaryButton:hover {{ background: {COLOR_PRIMARY_HOVER}; }}
QPushButton#PrimaryButton:pressed {{
    background: {COLOR_PRIMARY_HOVER};
    padding-top: 11px;
    padding-bottom: 9px;
}}
QPushButton#PrimaryButton:disabled {{ background: #9bb5ad; color: #f2f2f2; }}
QPushButton#SecondaryButton {{
    background: {COLOR_LIGHT_SURFACE};
    color: {COLOR_LIGHT_TEXT};
    border: 1px solid #b7c4d1;
    border-radius: 8px;
    padding: 8px 14px;
}}
QPushButton#SecondaryButton:hover {{
    background: #f3f7fa;
    border-color: {COLOR_PRIMARY};
}}
QPushButton#SecondaryButton:pressed {{
    padding-top: 9px;
    padding-bottom: 7px;
}}
QPushButton#GhostButton {{
    background: transparent;
    color: {COLOR_PRIMARY};
    border: none;
    padding: 6px 10px;
    font-weight: 600;
}}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit, QPlainTextEdit, QListWidget {{
    background: {COLOR_LIGHT_SURFACE};
    color: {COLOR_LIGHT_TEXT};
    border: 1px solid #c5d0db;
    border-radius: 5px;
    padding: 6px 8px;
    selection-background-color: {COLOR_PRIMARY};
    selection-color: #ffffff;
}}
QTableWidget {{
    background: {COLOR_LIGHT_SURFACE};
    color: {COLOR_LIGHT_TEXT};
    border: 1px solid {COLOR_LIGHT_BORDER};
    border-radius: 8px;
    gridline-color: #e6edf3;
}}
QHeaderView::section {{
    background: #f4f7fa;
    color: {COLOR_LIGHT_TEXT};
    padding: 6px;
    border: none;
    border-bottom: 1px solid {COLOR_LIGHT_BORDER};
    font-weight: 600;
}}
QGroupBox {{
    font-weight: 600;
    border: 1px solid {COLOR_LIGHT_BORDER};
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 12px;
    background: {COLOR_LIGHT_SURFACE};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: {COLOR_NAVY};
}}
QTabWidget::pane {{
    border: 1px solid {COLOR_LIGHT_BORDER};
    border-radius: 6px;
    background: {COLOR_LIGHT_SURFACE};
}}
QTabBar::tab {{
    background: #e4ebf2;
    color: {COLOR_LIGHT_TEXT};
    padding: 8px 14px;
    margin-right: 2px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}}
QTabBar::tab:selected {{
    background: {COLOR_LIGHT_SURFACE};
    font-weight: 600;
}}
QStatusBar {{ background: #e4ebf2; color: {COLOR_LIGHT_TEXT}; }}
QScrollBar:vertical {{
    background: {COLOR_LIGHT_BG};
    width: 12px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: #b7c4d1;
    border-radius: 5px;
    min-height: 24px;
}}
QToolTip {{
    background: {COLOR_LIGHT_TEXT};
    color: #ffffff;
    border: none;
    padding: 4px 8px;
}}
QCheckBox, QRadioButton {{ color: {COLOR_LIGHT_TEXT}; spacing: 8px; }}
QMenu {{
    background: {COLOR_LIGHT_SURFACE};
    color: {COLOR_LIGHT_TEXT};
    border: 1px solid {COLOR_LIGHT_BORDER};
}}
QMenu::item:selected {{ background: {COLOR_PRIMARY}; color: #ffffff; }}
QLabel#WarningLabel {{ color: {COLOR_WARN}; font-weight: 600; }}
QPlainTextEdit#LogPlain {{
    font-family: "Cascadia Mono", "Consolas", monospace;
    font-size: 12px;
}}
QListWidget#EventList {{
    border: 1px solid {COLOR_LIGHT_BORDER};
    border-radius: 8px;
    padding: 4px;
}}
"""

DARK_STYLESHEET = f"""
QWidget {{
    font-family: "Segoe UI", "Calibri", sans-serif;
    font-size: 13px;
    color: {COLOR_DARK_TEXT};
}}
QMainWindow, QDialog, QWizard {{
    background: {COLOR_DARK_BG};
}}
QScrollArea {{
    border: none;
    background: transparent;
}}
QFrame#Sidebar {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 {COLOR_NAVY}, stop:1 #071018);
    border: none;
    min-width: 168px;
    max-width: 240px;
}}
QLabel#Brand {{
    color: #f4f7fa;
    font-size: 17px;
    font-weight: 700;
}}
QLabel#BrandTagline {{
    color: rgba(244,247,250,0.65);
    font-size: 10px;
}}
QLabel#PageTitle {{
    font-size: 20px;
    font-weight: 700;
    color: #f2f7fb;
}}
QLabel#KpiValue {{
    font-size: 32px;
    font-weight: 700;
    color: #f2f7fb;
    letter-spacing: -0.5px;
}}
QLabel#PageSubtitle {{
    color: {COLOR_DARK_MUTED};
    font-size: 13px;
}}
QLabel#EmptyState {{
    color: {COLOR_DARK_MUTED};
    font-size: 14px;
    padding: 24px;
}}
QLabel#NextActionTitle {{
    font-size: 16px;
    font-weight: 700;
    color: #f2f7fb;
}}
QLabel#BadgeOk {{ background: #1f3d36; color: #9fd5c4; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }}
QLabel#BadgeWarn {{ background: #3d2a18; color: #f0c090; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }}
QLabel#BadgeDanger {{ background: #3d1a1a; color: #f0a0a0; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }}
QLabel#BadgeMuted {{ background: #243343; color: {COLOR_DARK_MUTED}; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }}
QLabel#BadgeInfo {{ background: #1a3040; color: #a8c8dc; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }}
QPushButton#NavButton, QPushButton[objectName^="kk.nav."] {{
    text-align: left;
    padding: 10px 14px;
    border: none;
    border-radius: 6px;
    color: #c9d7e2;
    background: transparent;
}}
QPushButton#NavButton:hover, QPushButton[objectName^="kk.nav."]:hover {{
    background: rgba(255,255,255,0.08);
}}
QPushButton#NavButton:checked, QPushButton[objectName^="kk.nav."]:checked {{
    background: rgba(24, 169, 153, 0.50);
    color: #ffffff;
    font-weight: 600;
}}
QFrame#Card, QFrame#HeroCard, QFrame#DetailPanel {{
    background: {COLOR_DARK_SURFACE};
    border: 1px solid {COLOR_DARK_BORDER};
    border-radius: 10px;
}}
QLabel#CardValue {{
    font-size: 22px;
    font-weight: 700;
    color: #f2f7fb;
}}
QLabel#CardTitle {{
    color: {COLOR_DARK_MUTED};
    font-size: 12px;
}}
QPushButton#PrimaryButton {{
    background: {COLOR_TEAL};
    color: white;
    border: none;
    border-radius: 8px;
    padding: 10px 18px;
    font-weight: 600;
}}
QPushButton#PrimaryButton:hover {{ background: {COLOR_PRIMARY_HOVER}; }}
QPushButton#PrimaryButton:pressed {{
    background: {COLOR_PRIMARY_HOVER};
    padding-top: 11px;
    padding-bottom: 9px;
}}
QPushButton#PrimaryButton:disabled {{ background: #3a4a55; color: #9aa8b4; }}
QPushButton#SecondaryButton {{
    background: {COLOR_DARK_SURFACE};
    color: {COLOR_DARK_TEXT};
    border: 1px solid #3a4d60;
    border-radius: 8px;
    padding: 8px 14px;
}}
QPushButton#SecondaryButton:hover {{
    background: #223142;
    border-color: {COLOR_TEAL};
}}
QPushButton#SecondaryButton:pressed {{
    padding-top: 9px;
    padding-bottom: 7px;
}}
QPushButton#GhostButton {{
    background: transparent;
    color: #9fd5c4;
    border: none;
    padding: 6px 10px;
    font-weight: 600;
}}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit, QPlainTextEdit, QListWidget {{
    background: #0f161e;
    color: {COLOR_DARK_TEXT};
    border: 1px solid #3a4d60;
    border-radius: 5px;
    padding: 6px 8px;
    selection-background-color: {COLOR_TEAL};
    selection-color: #ffffff;
}}
QComboBox QAbstractItemView {{
    background: {COLOR_DARK_SURFACE};
    color: {COLOR_DARK_TEXT};
    selection-background-color: {COLOR_TEAL};
}}
QTableWidget {{
    background: #0f161e;
    color: {COLOR_DARK_TEXT};
    border: 1px solid {COLOR_DARK_BORDER};
    border-radius: 8px;
    gridline-color: #243343;
    alternate-background-color: #15202b;
}}
QHeaderView::section {{
    background: {COLOR_DARK_SURFACE};
    color: {COLOR_DARK_TEXT};
    padding: 6px;
    border: none;
    border-bottom: 1px solid {COLOR_DARK_BORDER};
    font-weight: 600;
}}
QGroupBox {{
    font-weight: 600;
    border: 1px solid {COLOR_DARK_BORDER};
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 12px;
    background: {COLOR_DARK_SURFACE};
    color: {COLOR_DARK_TEXT};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: #d7e6f0;
}}
QTabWidget::pane {{
    border: 1px solid {COLOR_DARK_BORDER};
    border-radius: 6px;
    background: {COLOR_DARK_SURFACE};
}}
QTabBar::tab {{
    background: #121820;
    color: #c9d7e2;
    padding: 8px 14px;
    margin-right: 2px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}}
QTabBar::tab:selected {{
    background: {COLOR_DARK_SURFACE};
    color: #ffffff;
    font-weight: 600;
}}
QStatusBar {{ background: #0f161e; color: #c9d7e2; }}
QScrollBar:vertical {{
    background: #121820;
    width: 12px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: #3a4d60;
    border-radius: 5px;
    min-height: 24px;
}}
QToolTip {{
    background: {COLOR_DARK_TEXT};
    color: #121820;
    border: none;
    padding: 4px 8px;
}}
QCheckBox, QRadioButton {{ color: {COLOR_DARK_TEXT}; spacing: 8px; }}
QMenu {{
    background: {COLOR_DARK_SURFACE};
    color: {COLOR_DARK_TEXT};
    border: 1px solid {COLOR_DARK_BORDER};
}}
QMenu::item:selected {{ background: {COLOR_TEAL}; color: #ffffff; }}
QMessageBox {{ background: {COLOR_DARK_SURFACE}; }}
QMessageBox QLabel {{ color: {COLOR_DARK_TEXT}; }}
QLabel#WarningLabel {{ color: #f0c090; font-weight: 600; }}
QPlainTextEdit#LogPlain {{
    font-family: "Cascadia Mono", "Consolas", monospace;
    font-size: 12px;
}}
QListWidget#EventList {{
    border: 1px solid {COLOR_DARK_BORDER};
    border-radius: 8px;
    padding: 4px;
}}
"""


def stylesheet_for(
    preference: str,
    *,
    dpi_scale: float | None = None,
    high_contrast: bool | None = None,
) -> str:
    """Return the active app stylesheet.

    Uses the design-system overlay by default. Rollback: set env
    ``KARRIEREKRAKE_LEGACY_STYLES=1`` or call ``legacy_stylesheet_for``.

    ``dpi_scale`` defaults to the primary screen DPR when available.
    ``high_contrast`` defaults to env ``KARRIEREKRAKE_HIGH_CONTRAST=1``.
    """
    import os

    from desktop.design_system.dpi import detect_dpi_scale
    from desktop.design_system.stylesheet import compose_app_stylesheet

    if os.environ.get("KARRIEREKRAKE_LEGACY_STYLES", "").strip() in {
        "1",
        "true",
        "yes",
    }:
        return legacy_stylesheet_for(preference)
    if dpi_scale is None:
        dpi_scale = detect_dpi_scale()
    if high_contrast is None:
        high_contrast = os.environ.get("KARRIEREKRAKE_HIGH_CONTRAST", "").strip().lower() in {
            "1",
            "true",
            "yes",
        }
    return compose_app_stylesheet(
        preference,
        use_design_layer=True,
        dpi_scale=float(dpi_scale),
        high_contrast=bool(high_contrast),
    )


def legacy_stylesheet_for(preference: str) -> str:
    """Pre-design-system QSS path (rollback)."""
    theme = resolve_theme(preference)
    return DARK_STYLESHEET if theme == "dark" else LIGHT_STYLESHEET
