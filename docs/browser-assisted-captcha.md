# Browser assistance in Python / Playwright

This implementation runs locally and uses free packages. No paid proxies, CAPTCHA solvers or model services are required. It cannot guarantee a CAPTCHA-free experience or improve an IP address's reputation. Random typing and scrolling are optional interaction behavior, not evidence of a lower challenge rate.

## Settings

In the app-owned `config/settings.yaml`:

```yaml
browser_manual_captcha: true
browser_humanized: true
browser_stealth: false
browser_automation_profile: ""
```

Manual assistance starts a visible browser from the beginning. Playwright cannot turn a live headless browser into a visible browser without relaunching, which would lose unsaved form state. A detected CAPTCHA brings the same page forward and pauses for up to five minutes. Solving it manually resumes that step. Cancellation, closing the page or timing out stops the application loop. There is no CAPTCHA-solving service, automatic challenge click or repeated submission in this wait path.

Humanized mode types short fields with 40–100 ms key delays, scrolls before clicks and uses 4–9 second pauses. Long cover letters use direct fill so they do not take several minutes to enter. These changes apply to browser application forms. The separate HTTP job-search adapters cannot gain browser trust through simulated typing.

`browser_stealth: true` enables the pinned `playwright-stealth==2.0.3` package, with only its webdriver patch enabled. Other fingerprint overrides are disabled to avoid inventing inconsistent device properties. The library itself calls its techniques limited; this flag is experimental and does not mask all browser/network signals.

## Persistent login profile

Karrierekrake already uses its own persistent profile. Log in inside that visible browser once. Subsequent runs reuse its cookies/session until the site's login expires.

An optional `browser_automation_profile` may specify another dedicated directory. Do not point it at the main Chrome/Edge profile: modern Chrome/Playwright do not support automating that directory. The code rejects detected standard main-profile paths and their children/symlinks. It never copies personal cookies into the app's profile.

## Dynamically locate existing profile paths

```python
from browser.profiles import discover_profiles

# Windows LOCALAPPDATA, macOS Application Support, Linux XDG_CONFIG_HOME.
# Returns existing roots. Chrome's "Default" or "Profile 1" is below that root.
for browser, user_data_dir in discover_profiles().items():
    print(browser, user_data_dir)
```

For a nonstandard Chrome installation, `chrome://version` shows the active profile path. That is informational and should not be passed to automation as the daily browsing profile.

## Standalone use

```python
from browser.browser_manager import BrowserManager
from core.platform_paths import user_data_dir

manager = BrowserManager(
    user_data_dir() / 'browser_profile',
    headless=True,  # Manual mode overrides this to preserve a visible session.
    manual_captcha=True,
    humanized=True,
    stealth=False,  # Enable only when evaluating the webdriver patch.
    progress=print,
)
try:
    page = manager.get_page()
    # The existing ATS appliers call the challenge handler when a challenge appears.
    # BrowserManager alone does not scrape Google or automatically submit anything.
finally:
    manager.close()
```

## Validation and limits

Unit tests exercise typing, scrolling, pause bounds, same-page manual resolution, cancellation, solved response tokens, independent challenge widgets, profile rejection and loading the actual pinned stealth script. A smoke test runs against an installed Chromium-compatible browser on runners that have one, using a local data page; it measures webdriver visibility only.

No Google/real-site challenge-rate comparison was completed in the development environment. A browser download failed, so functional tests must not be presented as proof that this defeats IP blocks or CAPTCHAs. Changing browsers does not guarantee a new public IP or a different network reputation.

References:
- https://playwright.dev/python/docs/api/class-browsertype#browser-type-launch-persistent-context
- https://pypi.org/project/playwright-stealth/2.0.3/
- https://github.com/ultrafunkamsterdam/undetected-chromedriver
