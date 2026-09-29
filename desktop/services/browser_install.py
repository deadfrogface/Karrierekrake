"""Playwright Chromium detection and AppData install (never beside EXE).

Packaged EXE must NEVER run ``sys.executable -m playwright`` — that relaunches
Karrierekrake.exe. Use the Playwright driver binary. Browsers live under
``%LOCALAPPDATA%\\Karrierekrake\\browsers`` (not next to the EXE, not bundled).
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

from core.cv_llm_runtime import is_frozen

logger = logging.getLogger("karrierekrake")

BROWSERS_DIRNAME = "browsers"
LEGACY_MS_PLAYWRIGHT = "ms-playwright"


def project_or_bundle_root() -> Path:
    """Directory containing the EXE (frozen) or the repo root (dev)."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent.parent


def meipass_dir() -> Path | None:
    if is_frozen() and hasattr(sys, "_MEIPASS"):
        return Path(getattr(sys, "_MEIPASS"))
    return None


def appdata_browsers_dir() -> Path:
    """Canonical install location: %LOCALAPPDATA%\\Karrierekrake\\browsers."""
    local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(local) / "Karrierekrake" / BROWSERS_DIRNAME


def candidate_browsers_dirs() -> list[Path]:
    """Ordered list of places where Chromium may live."""
    roots: list[Path] = []
    env = (os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or "").strip()
    if env:
        roots.append(Path(env))
    roots.append(appdata_browsers_dir())
    # Legacy locations (read-only fallback during migration)
    local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    roots.append(Path(local) / LEGACY_MS_PLAYWRIGHT)
    root = project_or_bundle_root()
    roots.append(root / LEGACY_MS_PLAYWRIGHT)
    roots.append(root / BROWSERS_DIRNAME)
    mi = meipass_dir()
    if mi:
        roots.append(mi / LEGACY_MS_PLAYWRIGHT)
        roots.append(mi / BROWSERS_DIRNAME)
    # Deduplicate while preserving order
    seen: set[str] = set()
    out: list[Path] = []
    for p in roots:
        key = str(p.resolve()) if p.exists() else str(p)
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def find_chromium_executable(browsers_dir: Path | None = None) -> Path | None:
    dirs = [browsers_dir] if browsers_dir else candidate_browsers_dirs()
    for base in dirs:
        if not base or not base.exists():
            continue
        matches = sorted(base.glob("chromium-*/chrome-win*/chrome.exe"))
        if matches:
            return matches[-1]  # newest revision if multiple
        matches = sorted(base.glob("chromium_headless_shell-*/chrome-win*/headless_shell.exe"))
        if matches:
            return matches[-1]
    return None


def preferred_browsers_dir() -> Path:
    """Directory we set as PLAYWRIGHT_BROWSERS_PATH for installs/repairs."""
    env = (os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or "").strip()
    if env:
        return Path(env)
    # Always AppData for both frozen and dev — never beside the EXE.
    return appdata_browsers_dir()


def configure_playwright_browsers_path() -> Path:
    """Set PLAYWRIGHT_BROWSERS_PATH for packaged/dev use. Call at app startup."""
    existing = (os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or "").strip()
    if existing and find_chromium_executable(Path(existing)):
        return Path(existing)

    for candidate in candidate_browsers_dirs():
        if find_chromium_executable(candidate):
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(candidate)
            return candidate

    target = preferred_browsers_dir()
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(target)
    return target


def playwright_available() -> bool:
    configure_playwright_browsers_path()
    if find_chromium_executable():
        return True
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            path = Path(getattr(p.chromium, "executable_path", "") or "")
            return bool(path) and path.exists()
    except Exception:
        return False


def browser_status_detail() -> str:
    configure_playwright_browsers_path()
    exe = find_chromium_executable()
    if exe:
        return f"OK: {exe}"
    return f"missing (expected under {preferred_browsers_dir()})"


def _playwright_driver_command() -> list[str]:
    """Return argv to run Playwright CLI via its driver — never sys.executable when frozen."""
    from playwright._impl._driver import compute_driver_executable

    driver_executable, driver_cli = compute_driver_executable()
    return [str(driver_executable), str(driver_cli)]


def _run_playwright_install(browsers_path: Path) -> tuple[bool, str]:
    browsers_path.mkdir(parents=True, exist_ok=True)
    try:
        from playwright._impl._driver import get_driver_env
    except Exception as exc:  # noqa: BLE001
        return False, f"Playwright-Treiber fehlt: {exc}"

    try:
        cmd = _playwright_driver_command() + ["install", "chromium"]
    except Exception as exc:  # noqa: BLE001
        return False, f"Playwright-Treiber nicht gefunden: {exc}"

    # Safety: never pass Karrierekrake.exe as interpreter
    if is_frozen() and Path(cmd[0]).resolve() == Path(sys.executable).resolve():
        return False, "Interner Fehler: Playwright-Treiber zeigt auf Karrierekrake.exe."

    env = os.environ.copy()
    env.update(get_driver_env())
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(browsers_path)

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env,
            timeout=600,
        )
    except subprocess.TimeoutExpired:
        return False, "Zeitüberschreitung bei der Browser-Reparatur."
    except OSError as exc:
        return False, str(exc)

    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        return False, detail or "Browser-Reparatur fehlgeschlagen."

    configure_playwright_browsers_path()
    if not find_chromium_executable(browsers_path) and not find_chromium_executable():
        return False, (
            "Download meldete Erfolg, aber Chromium wurde nicht gefunden. "
            f"Bitte Ordner prüfen: {browsers_path}"
        )
    return True, f"Browser-Komponente bereit ({browsers_path})"


def check_browser() -> tuple[bool, str]:
    """Verify optional Chromium install is present (no download)."""
    configure_playwright_browsers_path()
    exe = find_chromium_executable()
    if exe:
        return True, f"Browser-Komponente gefunden:\n{exe}"
    return False, (
        "Browser-Automatisierung ist noch nicht installiert.\n\n"
        f"Zielordner:\n{preferred_browsers_dir()}\n\n"
        "Nutzen Sie „Browser-Automatisierung installieren“ "
        "(einmaliger Download; danach offline nutzbar)."
    )


def repair_browser() -> tuple[bool, str]:
    """Install/repair Chromium into %LOCALAPPDATA%\\Karrierekrake\\browsers.

    Uses the Playwright driver binary — never relaunches the frozen EXE.
    Always attempts a driver-based install/repair (even if a previous binary
    path looks present) so "Reparieren" actually re-downloads a broken install.
    """
    configure_playwright_browsers_path()
    target = preferred_browsers_dir()
    # Hard safety: never invoke sys.executable -m playwright when frozen.
    if is_frozen():
        try:
            cmd = _playwright_driver_command()
        except Exception as exc:  # noqa: BLE001
            return False, f"Playwright-Treiber nicht verfügbar: {exc}"
        if Path(cmd[0]).resolve() == Path(sys.executable).resolve():
            return False, "Interner Fehler: Playwright-Treiber zeigt auf Karrierekrake.exe."

    ok, msg = _run_playwright_install(target)
    if ok:
        return True, msg

    # If install failed but a usable Chromium still exists, report degraded success.
    existing = find_chromium_executable()
    if existing:
        return True, (
            f"Neue Installation fehlgeschlagen ({msg}), "
            f"vorhandene Komponente bleibt nutzbar:\n{existing}"
        )

    if is_frozen():
        return False, (
            f"{msg}\n\n"
            "Chromium konnte nicht installiert werden.\n"
            f"Zielordner: {target}\n"
            "Bitte Internetverbindung prüfen. Die App bleibt geöffnet."
        )
    return False, msg


def install_chromium() -> tuple[bool, str]:
    """Legacy entry: check first; repair only if missing."""
    ok, msg = check_browser()
    if ok:
        return True, msg
    return repair_browser()
