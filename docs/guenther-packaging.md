# Günther — Packaging / EXE awareness (Phase 23)

- `packaging/Karrierekrake.spec` collects `guenther` + `integrations` submodules.
- EXE does **not** bundle GGUF weights or Chromium.
- `llama-cpp-python` is optional; without it Günther stays off or uses fail-closed / heuristic assist when enabled.
- AppData `models/` created by `desktop.paths.ensure_app_dirs`.
- Model manager requires explicit `allow_download=True` — no silent multi-GB fetch.
