"""QSS builders for the design-system layer (composable with legacy theme)."""

from __future__ import annotations

from desktop.design_system.tokens import DesignTokens, tokens_for_theme
from desktop.theme import resolve_theme


def _mix_toward_white(hex_color: str, amount: float) -> str:
    """Lighten an existing token hex. Not a new palette entry."""
    raw = hex_color.strip().lstrip("#")
    if len(raw) != 6:
        return hex_color
    red, green, blue = int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)

    def channel(value: int) -> int:
        mixed = value + (255 - value) * amount
        return max(0, min(255, round(mixed)))

    return f"#{channel(red):02x}{channel(green):02x}{channel(blue):02x}"


# Resting fill of QLabel#BadgeMuted in the dark legacy sheet.
_DARK_MUTED_CHIP_BG = "#243343"
# Keeps muted text (#9AB5B6) at about 4.6:1 on the lifted fill.
_DARK_CHIP_HOVER_LIFT = 0.08


def dark_chip_hover_qss(tokens: DesignTokens | None = None) -> str:
    """Instant :hover for dark chips — lighter border and fill, no animation.

    Text color stays the existing foreground so contrast does not drop under
    the small background lift. The border uses the dark focus-ring token.
    """
    colors = tokens.colors if tokens is not None else tokens_for_theme("dark").colors
    pairs = (
        ("QLabel#BadgeOk:hover, QLabel#KkStatusSuccess:hover", colors.success_bg, colors.success),
        ("QLabel#BadgeWarn:hover, QLabel#KkStatusWarning:hover", colors.warning_bg, colors.warning),
        ("QLabel#BadgeDanger:hover, QLabel#KkStatusError:hover", colors.error_bg, colors.error),
        ("QLabel#BadgeMuted:hover", _DARK_MUTED_CHIP_BG, colors.muted),
        ("QLabel#BadgeInfo:hover", colors.info_bg, colors.info_fg),
    )
    rules = [
        """
QLabel#BadgeOk, QLabel#KkStatusSuccess,
QLabel#BadgeWarn, QLabel#KkStatusWarning,
QLabel#BadgeDanger, QLabel#KkStatusError,
QLabel#BadgeMuted, QLabel#BadgeInfo {
    border: 1px solid transparent;
}
""".strip()
    ]
    for selector, background, foreground in pairs:
        lifted = _mix_toward_white(background, _DARK_CHIP_HOVER_LIFT)
        rules.append(
            f"{selector} {{\n"
            f"    background: {lifted};\n"
            f"    color: {foreground};\n"
            f"    border: 1px solid {colors.focus_ring};\n"
            f"}}"
        )
    return "/* dark chip hover — stylesheet only */\n" + "\n".join(rules) + "\n"


def build_design_stylesheet(tokens: DesignTokens) -> str:
    """Primitive focus / validation / status rules layered on shared object names."""
    c = tokens.colors
    r = tokens.radii
    ctrl = tokens.controls
    ty = tokens.typography
    css = f"""
/* === Design system primitives (schema {tokens.schema_version}) === */
QWidget#KkPrimitive {{
    font-family: {ty.font_family};
    font-size: {ty.size_md}px;
}}
/* Unnamed buttons (QMessageBox / QDialogButtonBox / wizard): the global text
   color would otherwise sit on the native light button face in dark mode. */
QPushButton {{
    background: {c.surface};
    color: {c.text};
    border: 1px solid {c.border};
    border-radius: {r.md}px;
    padding: {ctrl.input_pad_v}px {ctrl.button_pad_h - 2}px;
    min-height: {ctrl.min_touch - 4}px;
}}
QPushButton:hover {{
    border-color: {c.primary};
}}
QPushButton:default {{
    border: {ctrl.focus_width}px solid {c.primary};
    font-weight: {ty.weight_semibold};
}}
QPushButton:disabled {{
    color: {c.muted};
}}
QToolButton#SecondaryButton {{
    background: {c.surface};
    color: {c.text};
    border: 1px solid {c.border};
    border-radius: {r.md}px;
    padding: {ctrl.button_pad_v - 1}px {ctrl.button_pad_h - 2}px;
    min-height: {ctrl.min_touch}px;
}}
QToolButton#SecondaryButton:hover, QToolButton#SecondaryButton:checked {{
    border-color: {c.primary};
}}
QToolButton#GhostButton {{
    background: transparent;
    border: none;
}}
QToolButton#GhostButton:hover {{
    background: {c.bg};
    border-radius: {r.sm}px;
}}
QPushButton#AccentButton {{
    background: {c.surface};
    color: {c.primary};
    border: 1px solid {c.primary};
    border-radius: {r.md}px;
    padding: {ctrl.button_pad_v - 1}px {ctrl.button_pad_h}px;
    min-height: {ctrl.min_touch}px;
    font-weight: {ty.weight_semibold};
}}
QPushButton#AccentButton:hover {{
    background: {c.success_bg};
}}
QPushButton#AccentButton:disabled {{
    color: {c.muted};
    border-color: {c.border};
}}
QScrollArea > QWidget > QWidget {{
    background: transparent;
}}
QLabel#KkNotice {{
    background: {c.info_bg};
    color: {c.info_fg};
    border-radius: {r.md}px;
    padding: {tokens.spacing.sm}px {tokens.spacing.md}px;
}}
QFrame#Card[kkClickable="true"]:hover {{
    border-color: {c.primary};
    background: {c.bg};
}}
QFrame#Card[kkClickable="true"]:focus {{
    border: {ctrl.focus_width}px solid {c.focus_ring};
}}
QFrame#Card[kkExpanded="true"] {{
    border-color: {c.primary};
}}
QLabel#BadgeOk, QLabel#BadgeWarn, QLabel#BadgeDanger, QLabel#BadgeMuted, QLabel#BadgeInfo {{
    padding: 4px 10px;
    border-radius: {r.sm}px;
    font-size: {ty.size_xs}px;
    font-weight: {ty.weight_semibold};
}}
QPushButton#KkPrimary, QPushButton#PrimaryButton {{
    background: {c.primary};
    color: #ffffff;
    border: none;
    border-radius: {r.md}px;
    padding: {ctrl.button_pad_v + 1}px {ctrl.button_pad_h + 4}px;
    font-weight: {ty.weight_semibold};
    min-height: {ctrl.min_touch}px;
}}
QPushButton#KkPrimary:hover, QPushButton#PrimaryButton:hover {{
    background: {c.primary_hover};
}}
QPushButton#KkPrimary:pressed, QPushButton#PrimaryButton:pressed {{
    background: {c.primary_hover};
    padding-top: {ctrl.button_pad_v + 2}px;
    padding-bottom: {ctrl.button_pad_v}px;
}}
QPushButton#KkPrimary:disabled, QPushButton#PrimaryButton:disabled,
QPushButton#KkSecondary:disabled, QPushButton#SecondaryButton:disabled {{
    background: {c.disabled_bg};
    color: {c.disabled_fg};
}}
QPushButton#KkPrimary:focus, QPushButton#KkSecondary:focus,
QPushButton#PrimaryButton:focus, QPushButton#SecondaryButton:focus,
QPushButton#KkGhost:focus, QPushButton#GhostButton:focus {{
    outline: none;
    border: {ctrl.focus_width}px solid {c.focus_ring};
}}
QPushButton#KkSecondary, QPushButton#SecondaryButton {{
    background: {c.surface};
    color: {c.text};
    border: 1px solid {c.border};
    border-radius: {r.md}px;
    padding: {ctrl.button_pad_v - 1}px {ctrl.button_pad_h - 2}px;
    min-height: {ctrl.min_touch}px;
}}
QPushButton#KkSecondary:hover, QPushButton#SecondaryButton:hover {{
    background: {c.bg};
    border-color: {c.primary};
}}
QPushButton#KkSecondary:pressed, QPushButton#SecondaryButton:pressed {{
    padding-top: {ctrl.button_pad_v}px;
    padding-bottom: {ctrl.button_pad_v - 2}px;
}}
QPushButton#KkGhost, QPushButton#GhostButton {{
    background: transparent;
    color: {c.primary};
    border: {ctrl.focus_width}px solid transparent;
    padding: {ctrl.input_pad_v}px {ctrl.input_pad_h + 2}px;
    font-weight: {ty.weight_semibold};
}}
QPushButton#KkGhost:hover, QPushButton#GhostButton:hover {{
    background: rgba(47, 122, 104, 0.08);
    border-color: transparent;
    border-radius: {r.sm}px;
}}
QLineEdit#KkInput, QTextEdit#KkInput, QPlainTextEdit#KkInput,
QComboBox#KkInput, QSpinBox#KkInput, QDoubleSpinBox#KkInput {{
    background: {c.surface};
    color: {c.text};
    border: 1px solid {c.border};
    border-radius: {r.sm + 1}px;
    padding: {ctrl.input_pad_v}px {ctrl.input_pad_h}px;
    min-height: {ctrl.min_touch}px;
    selection-background-color: {c.primary};
    selection-color: #ffffff;
}}
QLineEdit#KkInput:focus, QTextEdit#KkInput:focus, QPlainTextEdit#KkInput:focus,
QComboBox#KkInput:focus, QSpinBox#KkInput:focus, QDoubleSpinBox#KkInput:focus,
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus,
QSpinBox:focus, QDoubleSpinBox:focus {{
    border: {ctrl.focus_width}px solid {c.focus_ring};
}}
QLineEdit#KkInput[kkState="error"], QLineEdit[kkState="error"],
QTextEdit#KkInput[kkState="error"], QPlainTextEdit#KkInput[kkState="error"] {{
    border: {ctrl.focus_width}px solid {c.error};
}}
QLineEdit#KkInput[kkState="warning"], QLineEdit[kkState="warning"] {{
    border: {ctrl.focus_width}px solid {c.warning};
}}
QLineEdit#KkInput:disabled, QComboBox#KkInput:disabled, QSpinBox#KkInput:disabled {{
    background: {c.bg};
    color: {c.muted};
}}
QFrame#KkCard, QFrame#Card, QFrame#HeroCard, QFrame#DetailPanel {{
    background: {c.surface};
    border: 1px solid {c.border};
    border-radius: {r.xl}px;
}}
QWidget#SettingsFooter {{
    background: {c.surface};
    border-top: 1px solid {c.border};
}}
QLabel#KkStatusSuccess, QLabel#BadgeOk {{
    background: {c.success_bg};
    color: {c.success};
    padding: 2px 8px;
    border-radius: {r.sm}px;
    font-size: {ty.size_xs}px;
    font-weight: {ty.weight_semibold};
}}
QLabel#KkStatusWarning, QLabel#BadgeWarn {{
    background: {c.warning_bg};
    color: {c.warning};
    padding: 2px 8px;
    border-radius: {r.sm}px;
    font-size: {ty.size_xs}px;
    font-weight: {ty.weight_semibold};
}}
QLabel#KkStatusError, QLabel#BadgeDanger {{
    background: {c.error_bg};
    color: {c.error};
    padding: 2px 8px;
    border-radius: {r.sm}px;
    font-size: {ty.size_xs}px;
    font-weight: {ty.weight_semibold};
}}
QLabel#KkHint {{
    color: {c.muted};
    font-size: {ty.size_sm}px;
}}
QLabel#KkErrorText {{
    color: {c.error};
    font-size: {ty.size_sm}px;
    font-weight: {ty.weight_semibold};
}}
QDialog#KkDialog {{
    background: {c.bg};
}}
/* === PR44 focus / keyboard surfaces === */
QPushButton#NavButton:focus {{
    outline: none;
    border: {ctrl.focus_width}px solid {c.focus_ring};
}}
QTabBar::tab:focus {{
    border: {ctrl.focus_width}px solid {c.focus_ring};
}}
QCheckBox:focus, QRadioButton:focus {{
    outline: none;
    border: {ctrl.focus_width}px solid {c.focus_ring};
    border-radius: {r.sm}px;
}}
QListWidget:focus, QTreeWidget:focus, QTableWidget:focus,
QAbstractItemView:focus {{
    border: {ctrl.focus_width}px solid {c.focus_ring};
}}
QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border: {ctrl.focus_width}px solid {c.focus_ring};
}}
"""
    if tokens.theme == "dark":
        css += "\n" + dark_chip_hover_qss(tokens)
    return css


def build_high_contrast_stylesheet(tokens: DesignTokens) -> str:
    """Extra contrast rules — status still uses text glyphs (never color-only)."""
    return f"""
/* === High contrast overlay (PR44) === */
QWidget {{
    background: {tokens.colors.bg};
    color: {tokens.colors.text};
}}
QPushButton#PrimaryButton, QPushButton#KkPrimary {{
    border: 2px solid {tokens.colors.text};
}}
QPushButton#SecondaryButton, QPushButton#KkSecondary,
QPushButton#NavButton {{
    border: 2px solid {tokens.colors.border};
}}
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    border: 2px solid {tokens.colors.text};
}}
QLabel#KkErrorText, QLabel#BadgeDanger {{
    font-weight: 700;
    text-decoration: underline;
}}
"""


def compose_app_stylesheet(
    preference: str,
    *,
    use_design_layer: bool = True,
    dpi_scale: float = 1.0,
    high_contrast: bool = False,
) -> str:
    """Legacy theme QSS + optional design-system overlay (rollback: use_design_layer=False)."""
    from desktop.design_system.tokens import with_dpi_scale
    from desktop.theme import legacy_stylesheet_for

    legacy = legacy_stylesheet_for(preference)
    if not use_design_layer:
        return legacy
    theme = resolve_theme(preference)
    tokens = with_dpi_scale(tokens_for_theme(theme), dpi_scale)  # type: ignore[arg-type]
    css = legacy + "\n" + build_design_stylesheet(tokens)
    if high_contrast:
        css += "\n" + build_high_contrast_stylesheet(tokens)
    return css
