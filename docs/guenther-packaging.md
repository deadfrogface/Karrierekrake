# Günther / CV — Packaging / EXE (offline bundle)

- `packaging/Karrierekrake.spec` collects `guenther` + `integrations` + `llama_cpp` (native libs via `collect_all`).
- Chromium is **not** bundled (runtime install into AppData).
- Production GGUF **is** prepared into `vendor/cv_model/` and shipped via PyInstaller datas **and** `dist/models/` sidecar next to the EXE.
- Resolve order (`core/cv_llm_runtime.py`): env → `_MEIPASS/models` → `<exe>/models` → AppData materialize → cache.
- After fresh install: offline import without download, model path dialog, terminal, or manual server. No Phi/DET fallback.
- Build: `scripts/prepare_bundled_cv_model.py` then PyInstaller with `KARRIEREKRAKE_REQUIRE_BUNDLED_CV_MODEL=1`.
- Gate: `scripts/ci_cv_import_exe_offline_e2e.py` (Windows Smoke / Build Windows).
- AppData `models/` from `desktop.paths.ensure_app_dirs` holds the durable materialized copy.
- UI must not show model/tech names; see `docs/project/CV_IMPORT_EXE_OFFLINE_RELEASE_GATE.md`.
