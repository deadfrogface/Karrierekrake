# AI provider and free communications architecture

## Rules
- Qwen 3.5 4B GGUF remains the default local/offline runtime. Never require a remote account.
- Commercial third-party AI providers are optional. A ChatGPT/Claude/Gemini web subscription is **not** an API credential. Do not automate consumer websites, reuse browser cookies, or claim subscriptions cover third-party API traffic.
- Implement provider-neutral AI transport only with explicitly authorized endpoints and user-owned API credentials (BYOK), stored in the OS credential vault. Never bundle a developer API key or route requests through a paid KarriereKrake server.
- OpenAI: investigate official commercial ChatGPT subscription partner access; do not expose a button until approved.
- Anthropic Claude: separate API key/billing unless official third-party delegated subscription access is documented and approved.
- Google Gemini: use official Gemini API with user-owned key and consent, not Gemini CLI consumer login or unofficial Code Assist token reuse.
- Moonshot/Kimi: separate API key unless officially supported account authorization is established.
- UI must explicitly label external AI as optional and potentially billable by the provider, with per-request consent before uploading CV/application personal data.
- No automatic fallback from local Qwen to a cloud model.

## Free email/calendar
- IMAP/SMTP direct access can use app passwords when supported by the provider. Open-source libraries do not bypass account authentication.
- Private HTTPS ICS subscription: read-only, no Google API, no Google OAuth, six-hour refresh when calendar is queried. The URL is a bearer secret; treat it as sensitive, do not log or export it.
- CalDAV is an open protocol, but Google CalDAV still requires OAuth; never market Google CalDAV as OAuth-free.
- A private ICS link is read-only and may not contain private events from calendars that were not shared. Never create events or send invitations via ICS subscription.
- Preserve the manually imported ICS fallback.

## Release gates
1. Verify HTTPS private ICS links on Windows with redirect, DNS rebinding, invalid ICS, large response and TLS-failure tests.
2. Ensure free CTAs never open Google OAuth.
3. Confirm secret storage policy and remove URLs from diagnostics.
4. Do not enable cloud AI providers before a separate reviewed PR with licensing, privacy, UI and integration tests.
