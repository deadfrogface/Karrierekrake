"""Playwright browser manager with persistent profile.

Uses installed Chromium-compatible browsers first, then bundled Chromium. Never requires
``python -m playwright`` from a frozen executable.
"""

from __future__ import annotations

import logging
import os
import platform
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("karrierekrake")


def _find_system_chrome() -> str | None:
    candidates = []
    if platform.system() == "Windows":
        for base in [
            os.environ.get("PROGRAMFILES", r"C:\Program Files"),
            os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
            os.path.expandvars(r"%LOCALAPPDATA%"),
        ]:
            candidates.append(os.path.join(base, "Google", "Chrome", "Application", "chrome.exe"))
    elif platform.system() == "Darwin":
        candidates.append("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    else:
        candidates.extend(["/usr/bin/google-chrome", "/usr/bin/chromium-browser", "/usr/bin/chromium"])
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def _resolve_chromium_executable() -> str | None:
    """Prefer bundled / PLAYWRIGHT_BROWSERS_PATH Chromium over system Chrome."""
    try:
        from desktop.services.browser_install import (
            configure_playwright_browsers_path,
            find_chromium_executable,
        )

        configure_playwright_browsers_path()
        bundled = find_chromium_executable()
        if bundled and bundled.exists():
            return str(bundled)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Bundled Chromium lookup failed: %s", exc)
    return None


class BrowserManager:
    def __init__(self, profile_dir: Path, headless: bool = True, *,
                 manual_captcha: bool = False, humanized: bool = False,
                 stealth: bool = False, should_stop=None, progress=None,
                 captcha_timeout: float = 300) -> None:
        # Playwright cannot turn an existing headless session into a visible
        # window without relaunching it and losing unsaved form state.
        self.headless = headless and not manual_captcha
        self.manual_captcha = manual_captcha
        self.humanized = humanized
        self.stealth = stealth
        self.should_stop = should_stop or (lambda: False)
        self.progress = progress or (lambda text: None)
        self.captcha_timeout = max(1, min(float(captcha_timeout), 300))
        from browser.profiles import automation_profile
        self.profile_dir = automation_profile(profile_dir)
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self._playwright: Any = None
        self._context: Any = None
        self._page: Any = None
        self._chrome_pid: int | None = None
        try:
            from desktop.services.browser_install import configure_playwright_browsers_path
            from desktop.services.shutdown import get_shutdown_manager

            configure_playwright_browsers_path()
            get_shutdown_manager().register_browser(self)
        except Exception:
            pass

    def get_page(self):
        if self._page and not self._page.is_closed():
            return self._page
        if self._context is not None:
            self.close()
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Playwright fehlt. Entwicklung: pip install playwright && python -m playwright install chromium"
            ) from exc

        if self._playwright is None:
            self._playwright = sync_playwright().start()

        launch_kwargs = dict(
            user_data_dir=str(self.profile_dir),
            headless=self.headless,
            viewport={"width": 1280, "height": 800},
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-first-run",
                "--no-default-browser-check",
            ],
            ignore_default_args=["--enable-automation"],
        )

        from desktop.services.browser_install import find_system_browser

        system_browser = find_system_browser()
        chromium = str(system_browser) if system_browser else _resolve_chromium_executable()
        if chromium:
            launch_kwargs["executable_path"] = chromium
        else:
            # Last resort: system Chrome (dev machines)
            chrome = _find_system_chrome()
            if chrome:
                launch_kwargs["executable_path"] = chrome
                logger.warning("Using system Chrome; bundled Playwright Chromium not found")

        try:
            self._context = self._playwright.chromium.launch_persistent_context(**launch_kwargs)
        except Exception as exc:
            if "executable doesn't exist" in str(exc).lower():
                raise RuntimeError(
                    "Playwright Chromium fehlt. In der App: Einstellungen → Browser → "
                    "„Browser-Komponente reparieren“. "
                    "Entwicklung: python -m playwright install chromium"
                ) from exc
            # Fallback non-headless if headless fails
            if self.headless:
                logger.warning("Headless launch failed (%s); retrying visible browser", exc)
                self.headless = False
                launch_kwargs["headless"] = False
                self._context = self._playwright.chromium.launch_persistent_context(**launch_kwargs)
            else:
                raise
        if self.stealth:
            # Optional, limited fingerprint patch, not an IP/CAPTCHA guarantee.
            from playwright_stealth import Stealth, ALL_EVASIONS_DISABLED_KWARGS
            Stealth(**{**ALL_EVASIONS_DISABLED_KWARGS, "navigator_webdriver": True,
                       "navigator_languages_override": None, "navigator_platform_override": None}).apply_stealth_sync(self._context)
        self._context.set_default_timeout(5000)
        self._context.set_default_navigation_timeout(30000)
        pages = self._context.pages
        self._page = pages[0] if pages else self._context.new_page()
        self._page._kk_humanized = self.humanized
        if self.manual_captcha:
            self._page._kk_challenge_handler = self.wait_for_manual_captcha
        try:
            # Best-effort: remember Chromium PID for shutdown diagnostics
            browser = getattr(self._context, "browser", None)
            if browser is not None and getattr(browser, "process", None):
                self._chrome_pid = getattr(browser.process, "pid", None)
                if self._chrome_pid:
                    try:
                        from desktop.services.shutdown import get_shutdown_manager
                        get_shutdown_manager().register_pid(self._chrome_pid)
                    except Exception:
                        pass
        except Exception:
            pass
        return self._page

    def wait_for_manual_captcha(self, unresolved) -> bool:
        """Wait in the SAME page. Never click/solve/submit/reload the challenge."""
        page = self._page
        if self.headless or page is None or page.is_closed():
            return False
        page.bring_to_front()
        self.progress("CAPTCHA erkannt. Bitte im Browser lösen; Karrierekrake wartet.")
        deadline = time.monotonic() + self.captcha_timeout
        while time.monotonic() < deadline:
            if self.should_stop() or page.is_closed():
                return False
            if not unresolved():
                self.progress("CAPTCHA gelöst. Karrierekrake setzt den aktuellen Schritt fort.")
                return True
            # Pumps Playwright events and keeps cancellation responsive.
            page.wait_for_timeout(500)
        self.progress("CAPTCHA noch offen. Bewerbungslauf pausiert; keine neue Bewerbung gestartet.")
        return False

    def close(self) -> None:
        if self._chrome_pid:
            try:
                from desktop.services.shutdown import get_shutdown_manager
                get_shutdown_manager().unregister_pid(self._chrome_pid)
            except Exception:
                pass
            self._chrome_pid = None
        if self._context:
            try:
                self._context.close()
            except Exception:
                pass
            self._context = None
            self._page = None
        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None
