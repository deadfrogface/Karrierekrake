# Günther — Privacy (Phase 17)

- No cloud AI fallback (OpenAI/Anthropic/etc. endpoints hard-blocked).
- No required telemetry.
- Logs: event codes only via `guenther.privacy.log_event` — never CV body, email body, or prompts.
- Model weights stored under `%LOCALAPPDATA%\Karrierekrake\models\` (user-managed).
- Benchmark/tests use fictional `*.example.com` data only.
