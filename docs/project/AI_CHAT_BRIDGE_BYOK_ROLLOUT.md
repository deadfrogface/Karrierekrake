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

## Premium API (future)
- No BYOK in free tier.
- Premium API use needs a separately implemented managed service, subscription checks, quotas, and spending limits.
- Do not place shared provider credentials in the desktop application.
- External CV processing requires transparent user approval.
- Premium API integration is not yet implemented.

## Quality bake-off
Use the same verified profile and job text for local Qwen, ChatGPT, Claude, Gemini and Kimi.
Score anonymized letters for factual accuracy, relevance to actual job requirements,
specificity, natural German, non-repetition and formatting. Human blind review is required.
Do not claim a provider wins without a reproducible test and matched models.

## Release gate
No PR merge until CI, Windows packaging, privacy and human UX testing are green.
