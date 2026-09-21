"""Central Karrierekrake product identity (display + technical).

Canonical human spelling: ``Karrierekrake``
Canonical technical slug: ``karrierekrake``

Legacy AppData folder recognition lives only in ``desktop.legacy_migration``.
"""

from __future__ import annotations

from pathlib import Path

# --- Canonical technical identity ---
TECHNICAL_NAME = "Karrierekrake"
DATA_DIR_NAME = "Karrierekrake"
EXE_BASENAME = "Karrierekrake"
SINGLE_INSTANCE_KEY = "KarrierekrakeSingleInstance"
LOCAL_SERVER_NAME = "KarrierekrakeLocalServer"
TASK_SCHEDULER_NAME = "KarrierekrakeAutoRun"
ORG_DOMAIN = "karrierekrake.local"
USER_AGENT = "Karrierekrake/1.0 (local personal use)"
LOGGER_NAME = "karrierekrake"
ENV_PREFIX = "KARRIEREKRAKE"

# --- User-facing product brand ---
DISPLAY_NAME = "Karrierekrake"
TAGLINE_DE = "FINDE. BEWIRB. BEHALTE DEN ÜBERBLICK."
TAGLINE_EN = "FIND. APPLY. KEEP THE OVERVIEW."
SHORT_DESCRIPTION_DE = (
    "Desktop-App für die Jobsuche in Deutschland: finden, bewerten, "
    "Bewerbungen vorbereiten — alles lokal auf Ihrem PC."
)
SHORT_DESCRIPTION_EN = (
    "Desktop app for job search in Germany: find, score, and prepare "
    "applications — everything stays on your PC."
)

# ---------------------------------------------------------------------------
# Canonical palette (centralized design tokens)
# Orange is reserved for brand artwork — not general UI chrome.
# ---------------------------------------------------------------------------
COLOR_NAVY = "#132238"
COLOR_TEAL = "#18A999"
COLOR_TEAL_HOVER = "#148F82"
COLOR_ORANGE = "#E86A45"  # brand / illustration only
COLOR_SUCCESS = "#1F7A4C"
COLOR_WARN = "#C47A1A"
COLOR_ERROR = "#B83A3A"
COLOR_LIGHT_BG = "#F8FAFC"  # V2 canvas (was #EEF2F5)
COLOR_LIGHT_SURFACE = "#FFFFFF"
COLOR_LIGHT_BORDER = "#D5DEE8"
COLOR_LIGHT_TEXT = "#1C2430"
COLOR_LIGHT_MUTED = "#5A6B7A"
COLOR_DARK_BG = "#0E1620"
COLOR_DARK_SURFACE = "#1A2430"
COLOR_DARK_BORDER = "#2B3A4A"
COLOR_DARK_TEXT = "#E8EEF4"
COLOR_DARK_MUTED = "#9AB5B6"
COLOR_MARK = "#F4F7FA"

# Back-compat aliases used by theme / tray
COLOR_PRIMARY = COLOR_TEAL
COLOR_PRIMARY_HOVER = COLOR_TEAL_HOVER
COLOR_ACCENT = COLOR_WARN  # warnings — not brand orange
COLOR_SIDEBAR_TOP = COLOR_NAVY
COLOR_SIDEBAR_BOTTOM = "#0A1520"

# Asset layout relative to repo / frozen bundle
ASSET_REL = Path("assets") / "brand"
ICON_MASTER_NAME = "karrierekrake-app-icon-master.png"
LOGO_MASTER_NAME = "karrierekrake-logo-master.png"


def _asset_roots() -> list[Path]:
    """Candidate roots that may contain ``assets/brand`` (dev + frozen)."""
    import sys

    from desktop.paths import project_root

    roots: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        roots.append(Path(meipass))
    roots.append(project_root())
    # Deduplicate
    seen: set[str] = set()
    out: list[Path] = []
    for root in roots:
        key = str(root)
        if key in seen:
            continue
        seen.add(key)
        out.append(root)
    return out


def project_assets_dir() -> Path:
    """Return the first existing ``assets/brand`` directory."""
    for root in _asset_roots():
        candidate = root / ASSET_REL
        if candidate.is_dir():
            return candidate
    return _asset_roots()[0] / ASSET_REL


def icon_path(size: int | None = None) -> Path | None:
    """Prefer sized PNG for UI, then ICO, then master icon."""
    for root in _asset_roots():
        base = root / ASSET_REL
        candidates: list[Path] = []
        if size:
            candidates.append(base / "icons" / f"icon-{size}.png")
        candidates.extend(
            [
                base / "app.ico",
                base / "icons" / "icon-256.png",
                base / "icons" / "icon-128.png",
                base / ICON_MASTER_NAME,
                base / "logo.png",
            ]
        )
        for path in candidates:
            if path.is_file():
                return path
    return None


def logo_path(*, master: bool = False) -> Path | None:
    """Large brand artwork (MASTER A) for README / onboarding / About."""
    name = LOGO_MASTER_NAME if master else "logo.png"
    for root in _asset_roots():
        base = root / ASSET_REL
        for candidate in (base / name, base / LOGO_MASTER_NAME, base / "logo.png"):
            if candidate.is_file():
                return candidate
    return None


def app_icon_master_path() -> Path | None:
    path = project_assets_dir() / ICON_MASTER_NAME
    return path if path.is_file() else None


def social_preview_path() -> Path | None:
    path = project_assets_dir() / "social-preview.png"
    return path if path.is_file() else None


def display_name() -> str:
    return DISPLAY_NAME


def tagline(language: str = "de") -> str:
    return TAGLINE_EN if (language or "de").lower().startswith("en") else TAGLINE_DE
