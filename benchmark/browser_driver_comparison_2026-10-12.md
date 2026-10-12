# Browser driver comparison — 2026-10-12

Tested on Windows Server 2025 using the same installed Edge 154.0.8037.58 executable, Playwright 1.63.0 and Patchright 1.63.0. Three rounds with fresh, isolated profiles; session persistence was checked after closing and reopening the same profile. The current launch flags were read from the repository source, not guessed.

| Check | Current Karrierekrake / Playwright | Patchright, same settings |
|---|---|---|
| Form interaction | 3/3 passed | 3/3 passed |
| Session persistence | 3/3 passed | 3/3 passed |
| navigator.webdriver true | No, 3/3 | No, 3/3 |
| HeadlessChrome in UA | Yes, 3/3 | Yes, 3/3 |
| Detected automation globals | None, 3/3 | None, 3/3 |
| Local CDP serialization probe triggered | No, 3/3 | No, 3/3 |
| WebGL renderer | SwiftShader | Microsoft Basic Render Driver |

The visible/no-viewport Patchright recommendation did not report HeadlessChrome, but it changes browser mode as well as the driver. It therefore does not prove a driver-only improvement. The unmodified Playwright control did report navigator.webdriver=true in all three rounds, showing that the webdriver probe distinguishes the existing Karrierekrake configuration from the default.

No measured CAPTCHA advantage is established. The WebGL difference is an observable change, not proof of less detection. No Google searches or real CAPTCHA challenges were exercised; the test does not establish whether users' private/incognito Google browsing is protected. Only one runner environment was used. Timing measurements are included in the raw JSON but three rounds are not a robust performance benchmark.

[Successful workflow run](https://github.com/deadfrogface/Karrierekrake/actions/runs/38233795369)
