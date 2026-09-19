"""Design tokens — typography, spacing, radii, colors, semantic status."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

from desktop import branding as brand

ThemeName = Literal["light", "dark"]


@dataclass(frozen=True)
class TypographyTokens:
    font_family: str = '"Segoe UI", "Calibri", sans-serif'
    mono_family: str = '"Cascadia Mono", "Consolas", monospace'
    size_xs: int = 11
    size_sm: int = 12
    size_md: int = 13
    size_lg: int = 16
    size_xl: int = 20
    size_display: int = 22
    weight_regular: int = 400
    weight_semibold: int = 600
    weight_bold: int = 700


@dataclass(frozen=True)
class SpacingTokens:
    xxs: int = 2
    xs: int = 4
    sm: int = 8
    md: int = 12
    lg: int = 16
    xl: int = 24
    xxl: int = 32


@dataclass(frozen=True)
class RadiusTokens:
    sm: int = 4
    md: int = 6
    lg: int = 8
    xl: int = 10
    pill: int = 999


@dataclass(frozen=True)
class ColorTokens:
    bg: str
    surface: str
    border: str
    text: str
    muted: str
    primary: str
    primary_hover: str
    navy: str
    focus_ring: str
    error: str
    warning: str
    success: str
    # Semantic surfaces (not color-only meaning — also used with icons/text)
    error_bg: str
    warning_bg: str
    success_bg: str
    info_bg: str
    info_fg: str
    disabled_bg: str
    disabled_fg: str
    brand_orange: str = brand.COLOR_ORANGE  # artwork only


@dataclass(frozen=True)
class ControlTokens:
    button_pad_v: int = 9
    button_pad_h: int = 16
    input_pad_v: int = 6
    input_pad_h: int = 8
    focus_width: int = 2
    min_touch: int = 28


@dataclass(frozen=True)
class DesignTokens:
    theme: ThemeName
    typography: TypographyTokens
    spacing: SpacingTokens
    radii: RadiusTokens
    colors: ColorTokens
    controls: ControlTokens
    schema_version: str = "1.0.0"


def _light_colors() -> ColorTokens:
    return ColorTokens(
        bg=brand.COLOR_LIGHT_BG,
        surface=brand.COLOR_LIGHT_SURFACE,
        border=brand.COLOR_LIGHT_BORDER,
        text=brand.COLOR_LIGHT_TEXT,
        muted=brand.COLOR_LIGHT_MUTED,
        primary=brand.COLOR_PRIMARY,
        primary_hover=brand.COLOR_PRIMARY_HOVER,
        navy=brand.COLOR_NAVY,
        focus_ring=brand.COLOR_TEAL,
        error=brand.COLOR_ERROR,
        warning=brand.COLOR_WARN,
        success=brand.COLOR_SUCCESS,
        error_bg="#f5d6d6",
        warning_bg="#fce8d5",
        success_bg="#d8efe8",
        info_bg="#d5f0eb",
        info_fg="#0f5c54",
        disabled_bg="#9bb5ad",
        disabled_fg="#f2f2f2",
    )


def _dark_colors() -> ColorTokens:
    return ColorTokens(
        bg=brand.COLOR_DARK_BG,
        surface=brand.COLOR_DARK_SURFACE,
        border=brand.COLOR_DARK_BORDER,
        text=brand.COLOR_DARK_TEXT,
        muted=brand.COLOR_DARK_MUTED,
        primary=brand.COLOR_TEAL,
        primary_hover=brand.COLOR_PRIMARY_HOVER,
        navy=brand.COLOR_NAVY,
        focus_ring="#9fd5c4",
        error="#f0a0a0",
        warning="#f0c090",
        success="#9fd5c4",
        error_bg="#3d1a1a",
        warning_bg="#3d2a18",
        success_bg="#1f3d36",
        info_bg="#1a3040",
        info_fg="#a8c8dc",
        disabled_bg="#3a4a55",
        disabled_fg="#9aa8b4",
    )


def tokens_for_theme(theme: ThemeName) -> DesignTokens:
    colors = _dark_colors() if theme == "dark" else _light_colors()
    return DesignTokens(
        theme=theme,
        typography=TypographyTokens(),
        spacing=SpacingTokens(),
        radii=RadiusTokens(),
        colors=colors,
        controls=ControlTokens(),
    )


def with_dpi_scale(tokens: DesignTokens, scale: float) -> DesignTokens:
    """Return spacing/control tokens scaled for high-DPI (fonts stay px in QSS)."""
    if abs(scale - 1.0) < 0.01:
        return tokens
    s = tokens.spacing
    c = tokens.controls

    def sp(v: int) -> int:
        return max(1, int(round(v * scale)))

    return replace(
        tokens,
        spacing=SpacingTokens(
            xxs=sp(s.xxs),
            xs=sp(s.xs),
            sm=sp(s.sm),
            md=sp(s.md),
            lg=sp(s.lg),
            xl=sp(s.xl),
            xxl=sp(s.xxl),
        ),
        controls=ControlTokens(
            button_pad_v=sp(c.button_pad_v),
            button_pad_h=sp(c.button_pad_h),
            input_pad_v=sp(c.input_pad_v),
            input_pad_h=sp(c.input_pad_h),
            focus_width=max(2, sp(c.focus_width)),
            min_touch=sp(c.min_touch),
        ),
    )
