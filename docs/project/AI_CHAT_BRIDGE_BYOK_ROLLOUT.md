# Optional AI writing: staged implementation

This PR introduces an **offline-safe foundation**, not a finished external-AI integration.

## Manual chat bridge (first)
1. Explicit user selection of ChatGPT, Claude, Gemini or Kimi.
2. Show precisely what verified CV/profile fields and job text would leave the PC.
3. With consent, copy the prompt to the clipboard and open the provider's official website.
4. User manually sends the prompt and pastes the response into KarriereKrake.
5. Parse only the marked letter; run existing factual/quality guards and show editable preview.
6. Never automatically submit an application, scrape a consumer chat page, reuse session cookies, or silently upload CVs.

The pure functions in `core/ai_chat_bridge.py` implement prompt creation and marked-response parsing. UI integration is **not yet implemented**.

## BYOK (second)
- Local Qwen remains default. External AI requires separate opt-in for CV data transfer.
- OpenAI, Anthropic, Gemini and Moonshot API credentials are **not** consumer chat subscriptions.
- Store keys using OS credential storage; never store plaintext in app config, log or diagnostics.
- Use official API endpoints and documented commercial terms. No embedded developer keys.
- Add per-provider costs/usage disclosure and request timeouts, retries and rate limits.
- Require a second PR for actual network clients, key-management UI and end-to-end tests.
- Remote model outputs are untrusted; enforce existing evidence verification before draft approval.

## Quality bake-off
Use the same verified profile and job text for local Qwen, ChatGPT, Claude, Gemini and Kimi.
Score anonymized letters for factual accuracy, relevance to actual job requirements,
specificity, natural German, non-repetition and formatting. Human blind review is required.
Do not claim a provider wins without a reproducible test and matched models.

## Release gate
No PR merge until CI, Windows packaging, privacy and human UX testing are green.
