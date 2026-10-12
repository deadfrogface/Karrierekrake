from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from browser.profiles import automation_profile, discover_profiles
from browser.browser_manager import BrowserManager
from apply.base import BaseApplier, ApplyResult


class Applier(BaseApplier):
    def _do_apply(self, *args):
        return ApplyResult(success=False)


class Page:
    def __init__(self):
        self.frames = {'iframe[src*=\'recaptcha\']': object()}
        self.token = ''
        self.closed = False
        self.waits = []
        self.mouse = SimpleNamespace(wheel=Mock())
    def query_selector(self, selector):
        if selector == "[name='g-recaptcha-response']":
            return SimpleNamespace(input_value=lambda: self.token)
        return self.frames.get(selector)
    def is_closed(self):
        return self.closed
    def bring_to_front(self):
        pass
    def wait_for_timeout(self, ms):
        self.waits.append(ms)
        self.token = 'human-solved-response'


def test_manual_challenge_resumes_same_page_without_submission(tmp_path):
    messages = []
    manager = BrowserManager(tmp_path / 'profile', manual_captcha=True, progress=messages.append)
    page = Page()
    manager._page = page
    page._kk_challenge_handler = manager.wait_for_manual_captcha
    applier = Applier(page)
    assert not manager.headless
    assert applier._detect_captcha() is False
    assert manager._page is page and page.waits == [500]
    assert len(messages) == 2
    assert applier._detect_captcha() is False  # Solved iframe remains; no second prompt.


def test_cancellation_preserves_captcha_stop(tmp_path):
    manager = BrowserManager(tmp_path / 'profile', manual_captcha=True, should_stop=lambda: True)
    page = Page()
    manager._page = page
    page._kk_challenge_handler = manager.wait_for_manual_captcha
    assert Applier(page)._detect_captcha() is True
    assert not page.waits


def test_solved_recaptcha_does_not_hide_separate_turnstile():
    page = Page()
    page.token = 'solved-recaptcha'
    page.frames["iframe[src*='challenges.cloudflare']"] = object()
    assert Applier(page)._detect_captcha() is True


def test_typing_and_scroll_are_real_interaction_options():
    page = Page()
    page._kk_humanized = True
    element = SimpleNamespace(fill=Mock(), type=Mock(), scroll_into_view_if_needed=Mock(),
                              is_visible=lambda: True, is_enabled=lambda: True, click=Mock())
    applier = Applier(page)
    applier._human_type(element, 'Verkäufer')
    assert element.type.call_args.args == ('Verkäufer',)
    assert 40 <= element.type.call_args.kwargs['delay'] <= 100
    applier._wait_and_query = lambda *args, **kw: element
    assert applier._safe_click('button')
    element.scroll_into_view_if_needed.assert_called_once()
    page.mouse.wheel.assert_called_once()


def test_human_pause_is_bounded():
    page = Page()
    page._kk_humanized = True
    Applier(page)._random_pause()
    assert 4000 <= page.waits[0] <= 9000


def test_default_profile_and_symlink_are_rejected(tmp_path, monkeypatch):
    import browser.profiles as profiles
    root = tmp_path / 'User Data'
    root.mkdir()
    monkeypatch.setattr(profiles, 'system_profile_roots', lambda: {'chrome': root})
    assert discover_profiles() == {'chrome': root}
    for path in (root, root / 'Default'):
        with pytest.raises(ValueError, match='Alltagsprofil'):
            automation_profile(path)
    linked = tmp_path / 'link'
    linked.symlink_to(root, target_is_directory=True)
    with pytest.raises(ValueError):
        automation_profile(linked)
    assert automation_profile(tmp_path / 'automation') == tmp_path / 'automation'


def test_profile_root_discovery_uses_windows_environment(tmp_path, monkeypatch):
    import browser.profiles as profiles
    monkeypatch.setattr(profiles.sys, 'platform', 'win32')
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    assert profiles.system_profile_roots()['chrome'] == tmp_path / 'Google/Chrome/User Data'


def test_optional_stealth_payload_is_pinned_and_loadable():
    from playwright_stealth import Stealth, ALL_EVASIONS_DISABLED_KWARGS
    context = SimpleNamespace(add_init_script=Mock())
    patch = Stealth(**{**ALL_EVASIONS_DISABLED_KWARGS, 'navigator_webdriver': True,
                       'navigator_languages_override': None, 'navigator_platform_override': None})
    patch.apply_stealth_sync(context)
    context.add_init_script.assert_called_once()
    assert 'navigator.webdriver' in context.add_init_script.call_args.args[0]


def test_stealth_in_actual_installed_browser(tmp_path):
    """Local data-page smoke only; measures webdriver, not CAPTCHA success."""
    from desktop.services.browser_install import find_system_browser
    executable = find_system_browser()
    if executable is None:
        pytest.skip('No installed Chromium-compatible browser; no download in tests')
    from playwright.sync_api import sync_playwright
    from playwright_stealth import Stealth, ALL_EVASIONS_DISABLED_KWARGS
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            str(tmp_path / 'isolated-profile'), executable_path=str(executable), headless=True)
        try:
            patch = Stealth(**{**ALL_EVASIONS_DISABLED_KWARGS, 'navigator_webdriver': True,
                               'navigator_languages_override': None, 'navigator_platform_override': None})
            patch.apply_stealth_sync(context)
            page = context.new_page()
            page.goto('data:text/html,<title>Local browser test</title>')
            assert page.evaluate('navigator.webdriver') is not True
        finally:
            context.close()


def test_challenge_window_error_stops_instead_of_retrying():
    page = Page()
    def failed_wait(unresolved):
        raise RuntimeError('page closed during wait')
    page._kk_challenge_handler = failed_wait
    assert Applier(page)._detect_captcha() is True


def test_default_workflow_never_enables_manual_captcha_or_humanizing():
    from core.config import SettingsConfig
    settings = SettingsConfig()
    assert settings.headless is True
    assert settings.browser_manual_captcha is False
    assert settings.browser_humanized is False
