"""Central configuration service for the desktop GUI."""

from __future__ import annotations

import json
import shutil
from copy import deepcopy
from pathlib import Path
from typing import Any

from core.config import (
    AppConfig,
    CONFIG_DIR,
    load_config,
    save_config,
)
from desktop.paths import ensure_app_dirs, project_root


class ConfigService:
    """Load/save YAML config from AppData and expose it to the GUI."""

    def __init__(self) -> None:
        self.dirs = ensure_app_dirs()
        self.meta_path = self.dirs["root"] / "meta.json"
        self._config: AppConfig | None = None
        self._bootstrap_from_examples()

    @property
    def profile_path(self) -> Path:
        return self.dirs["config"] / "profile.yaml"

    @property
    def application_path(self) -> Path:
        return self.dirs["config"] / "application_profile.yaml"

    @property
    def settings_path(self) -> Path:
        return self.dirs["config"] / "settings.yaml"

    def _bootstrap_from_examples(self) -> None:
        """Seed AppData YAML from repo *.example files once (never from personal YAML).

        Only copies when the destination is missing. Existing empty AppData files
        are left as-is so a reset to empty cannot be overwritten by examples.
        """
        mapping = [
            (self.profile_path, "profile.yaml"),
            (self.application_path, "application_profile.yaml"),
            (self.settings_path, "settings.yaml"),
        ]
        for dest, name in mapping:
            if dest.exists():
                continue
            # Prefer empty-safe examples; do not copy local non-example YAML
            # (repo no longer ships personal profile.yaml).
            example = CONFIG_DIR / f"{name}.example"
            if example.exists():
                shutil.copy2(example, dest)

    def load(self) -> AppConfig:
        config = load_config(
            profile_path=self.profile_path,
            application_path=self.application_path,
            settings_path=self.settings_path,
            root=self.dirs["root"],
            strip_placeholders=True,
        )
        # Force absolute runtime paths under AppData
        config.settings.database_path = str(self.dirs["data"] / "jobs.db")
        config.settings.logs_dir = str(self.dirs["logs"])
        config.settings.browser_profile_dir = str(self.dirs["browser_profile"])
        tpl = Path(config.settings.cover_letter_template)
        if not tpl.is_absolute():
            from desktop.services.browser_install import meipass_dir

            candidates = []
            mi = meipass_dir()
            if mi is not None:
                candidates.append(mi / tpl)
            candidates.append(project_root() / tpl)
            for bundled in candidates:
                if bundled.exists():
                    config.settings.cover_letter_template = str(bundled)
                    break
        self._config = config
        self._apply_shutdown_fix_migration(config)
        # Persist cleaned profile if demo placeholders were stripped
        try:
            from core.config import strip_example_application, strip_example_placeholders
            from copy import deepcopy

            before = deepcopy(config.profile.qualifications)
            strip_example_placeholders(config.profile)
            after = config.profile.qualifications
            before_app = (config.application.first_name, config.application.email)
            strip_example_application(config.application)
            after_app = (config.application.first_name, config.application.email)
            if (
                before.skills != after.skills
                or before.software != after.software
                or before.languages != after.languages
                or before_app != after_app
            ):
                self.save(config)
        except Exception:
            pass
        return config

    def _apply_shutdown_fix_migration(self, config: AppConfig) -> None:
        """One-time: red X must quit by default (disable accidental tray-keep-alive)."""
        meta = self.load_meta()
        if meta.get("shutdown_fix_v1"):
            return
        config.settings.minimize_to_tray = False
        meta["shutdown_fix_v1"] = True
        try:
            self.save(config)
            self.save_meta(meta)
        except Exception:
            pass

    @property
    def config(self) -> AppConfig:
        if self._config is None:
            return self.load()
        return self._config

    def reload(self) -> AppConfig:
        self._config = None
        return self.load()

    def save(self, config: AppConfig | None = None) -> AppConfig:
        config = config or self.config
        config.application.sync_address()
        # Keep runtime paths absolute in memory; persist portable relative names
        to_save = deepcopy(config)
        to_save.settings.database_path = "data/jobs.db"
        to_save.settings.logs_dir = "logs"
        to_save.settings.browser_profile_dir = "browser_profile"
        # Prefer relative template name in YAML
        tpl = Path(to_save.settings.cover_letter_template)
        if tpl.is_absolute():
            to_save.settings.cover_letter_template = "templates/cover_letter.txt"
        save_config(
            to_save,
            profile_path=self.profile_path,
            application_path=self.application_path,
            settings_path=self.settings_path,
        )
        self._config = self.load()
        return self._config

    def save_home_coords_from(self, run_config: AppConfig) -> AppConfig:
        """Persist home lat/lon + geocode fingerprint from a pipeline run.

        Writes only location provenance fields into freshly loaded settings so
        transient overrides (dry_run, mode) from apply-test / worker config are
        not flushed to disk. Always store ``home_geocoded_address`` with the
        coords so a later address edit can invalidate stale coordinates.
        """
        fresh = self.load()
        run_loc = run_config.profile.location
        fresh.profile.location.home_latitude = run_loc.home_latitude
        fresh.profile.location.home_longitude = run_loc.home_longitude
        fresh.profile.location.home_geocoded_address = (
            getattr(run_loc, "home_geocoded_address", "") or run_loc.home_address or ""
        )
        return self.save(fresh)

    def validate(self, config: AppConfig | None = None) -> list[str]:
        config = config or self.config
        errors: list[str] = []
        if config.profile.location.max_distance_km <= 0:
            errors.append("Pendeldistanz muss größer als 0 sein.")
        if config.settings.minimum_match_for_auto_apply < 0:
            errors.append("Mindest-Match darf nicht negativ sein.")
        if config.settings.max_applications_per_day < 1:
            errors.append("Max. Bewerbungen/Tag muss mindestens 1 sein.")
        mode = config.settings.mode
        if mode not in {
            "search_only",
            "review_before_submit",
            "fully_automatic",
        }:
            errors.append(f"Unbekannter Modus: {mode}")
        return errors

    def load_meta(self) -> dict[str, Any]:
        if not self.meta_path.exists():
            return {
                "first_run_completed": False,
                "last_search_run": "",
                "next_scheduled_run": "",
                "cv_variants": [],
            }
        try:
            return json.loads(self.meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"first_run_completed": False}

    def save_meta(self, meta: dict[str, Any]) -> None:
        self.meta_path.write_text(
            json.dumps(meta, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def mark_first_run_done(self) -> None:
        meta = self.load_meta()
        meta["first_run_completed"] = True
        self.save_meta(meta)

    def is_first_run(self) -> bool:
        return not bool(self.load_meta().get("first_run_completed"))

    def set_last_search(self, iso_ts: str) -> None:
        meta = self.load_meta()
        meta["last_search_run"] = iso_ts
        self.save_meta(meta)

    def get_sync_address_to_search(self) -> bool:
        """Opt-in: copy applicant address into search home_address on save."""
        return bool(self.load_meta().get("sync_address_to_search", False))

    def set_sync_address_to_search(self, enabled: bool) -> None:
        meta = self.load_meta()
        meta["sync_address_to_search"] = bool(enabled)
        self.save_meta(meta)

    def get_window_state(self) -> dict[str, Any]:
        meta = self.load_meta()
        return dict(meta.get("window") or {})

    def save_window_state(
        self,
        *,
        width: int,
        height: int,
        x: int | None = None,
        y: int | None = None,
        maximized: bool = False,
    ) -> None:
        meta = self.load_meta()
        meta["window"] = {
            "width": int(width),
            "height": int(height),
            "x": x,
            "y": y,
            "maximized": bool(maximized),
        }
        self.save_meta(meta)

    def apply_safe_defaults(self, config: AppConfig) -> AppConfig:
        """First-run defaults from the conversion plan."""
        config.settings.mode = "search_only"
        config.settings.dry_run = True
        config.settings.automatic_submission = False
        config.settings.run_automatically = False
        config.settings.automation_paused = False
        return config

    def copy_cv_into_storage(
        self,
        source: Path,
        label: str = "Default CV",
        *,
        role: str = "cv",
        set_active: bool | None = None,
    ) -> Path:
        """Copy a document into AppData ``cvs/`` with an explicit role.

        Cover letters never overwrite ``application.cv_path`` / ``active_cv_id``.
        """
        from core.documents import (
            ensure_variant_shape,
            new_variant_id,
            normalize_role,
            normalize_variants,
        )

        source = Path(source)
        dest_dir = self.dirs["cvs"]
        dest = dest_dir / source.name
        if source.resolve() != dest.resolve():
            shutil.copy2(source, dest)
        role_n = normalize_role(role, default="cv")
        if set_active is None:
            set_active = role_n == "cv"
        meta = self.load_meta()
        variants = normalize_variants(meta.get("cv_variants"))
        # Replace same path if present; otherwise append.
        variants = [v for v in variants if v.get("path") != str(dest)]
        entry = ensure_variant_shape(
            {
                "id": new_variant_id(),
                "label": label,
                "path": str(dest),
                "role": role_n,
            }
        )
        assert entry is not None
        variants.append(entry)
        meta["cv_variants"] = variants
        cfg = self.config
        if role_n == "cv" and set_active:
            meta["active_cv_id"] = entry["id"]
            cfg.application.cv_path = str(dest)
            self.save(cfg)
        elif role_n != "cv":
            # Never let cover_letter / other clobber the active CV path.
            pass
        self.save_meta(meta)
        return dest

    def clear_cv_storage(self) -> None:
        """Delete all files under AppData cvs/ and clear meta cv_variants."""
        cvs_dir = self.dirs["cvs"]
        if cvs_dir.exists():
            for path in cvs_dir.iterdir():
                try:
                    if path.is_file():
                        path.unlink()
                    elif path.is_dir():
                        shutil.rmtree(path)
                except OSError:
                    continue
        meta = self.load_meta()
        meta["cv_variants"] = []
        meta["active_cv_id"] = ""
        self.save_meta(meta)

    def get_active_cv_info(self) -> dict[str, Any]:
        from core.documents import active_cv_variant, variant_display_label

        meta = self.load_meta()
        cfg = self.load()
        variant = active_cv_variant(meta, fallback_cv_path=cfg.application.cv_path)
        return {
            "variant": variant,
            "label": variant_display_label(variant)
            or (cfg.application.cv_path or ""),
            "path": (variant or {}).get("path") or cfg.application.cv_path or "",
            "role": (variant or {}).get("role") or ("cv" if cfg.application.cv_path else ""),
        }

    def reset_to_empty_profile(self, *, clear_search_prefs: bool = False) -> AppConfig:
        """Persist an empty applicant + qualifications profile after clearing CV files.

        Removes: application PII, qualifications, CV files/variants.
        Keeps (unless ``clear_search_prefs``): search titles/location/filters,
        settings, job DB, logs. Search prefs are preserved by default (PR22).
        """
        from core.config import empty_application_profile, empty_qualifications, empty_search_preferences
        from desktop.services.profile_merge import clear_complete_application
        from desktop.services.profile_patch import PATCH_SCHEMA_VERSION

        self.clear_cv_storage()
        cfg = self.load()
        cfg.application = clear_complete_application(cfg.application)
        # Ensure identity equals empty helper
        blank = empty_application_profile()
        for name in blank.__dataclass_fields__:
            setattr(cfg.application, name, getattr(blank, name))
        cfg.application.answers = {}
        cfg.application.field_origins = {}
        cfg.profile.qualifications = empty_qualifications()
        if clear_search_prefs:
            loc = cfg.profile.location
            jobs = cfg.profile.jobs
            emp = cfg.profile.employment
            filt = cfg.profile.filters
            empty = empty_search_preferences()
            cfg.profile.location = empty.location
            # preserve commute defaults that are not personal PII
            cfg.profile.location.max_distance_km = loc.max_distance_km
            cfg.profile.location.allow_remote_germany = loc.allow_remote_germany
            cfg.profile.location.allow_hybrid = loc.allow_hybrid
            cfg.profile.location.country = loc.country or "DE"
            cfg.profile.jobs = empty.jobs
            cfg.profile.employment = emp  # keep work-model toggles
            cfg.profile.filters = empty.filters
            _ = (jobs, filt)  # silence unused in clear path
        saved = self.save(cfg)
        meta = self.load_meta()
        meta["profile_patch_schema"] = PATCH_SCHEMA_VERSION
        self.save_meta(meta)
        return saved

    def reset_profile_and_documents(self, *, clear_search_prefs: bool = False) -> AppConfig:
        """Alias: empty profile + delete stored CV/cover documents (same as reset)."""
        return self.reset_to_empty_profile(clear_search_prefs=clear_search_prefs)

    def delete_all_local_data(self) -> dict[str, Any]:
        """Remove all local Karrierekrake AppData contents (config, DB, logs, CVs, cache).

        Recreates empty directory skeleton afterwards. Does not touch other users'
        data or the install directory. Search prefs YAML are deleted with config;
        next ``load()`` re-bootstraps from ``*.example`` (non-PII defaults only).
        """
        import time

        from desktop.services.profile_patch import PATCH_SCHEMA_VERSION

        root = self.dirs["root"]
        removed: list[str] = []
        backup_hint = ""
        # Best-effort snapshot of config before wipe (rollback aid)
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        backup_dir = root / f".wipe_backup_{stamp}"
        try:
            if self.dirs["config"].exists():
                from core.security.export_gate import wipe_backup_should_skip

                def _ignore(directory: str, names: list[str]) -> list[str]:
                    return [
                        n
                        for n in names
                        if wipe_backup_should_skip(Path(directory) / n)
                    ]

                shutil.copytree(
                    self.dirs["config"],
                    backup_dir / "config",
                    dirs_exist_ok=True,
                    ignore=_ignore,
                )
                backup_hint = str(backup_dir)
        except OSError:
            backup_hint = ""

        for key, path in list(self.dirs.items()):
            if key == "root":
                continue
            if not path.exists():
                continue
            try:
                if path.is_dir():
                    shutil.rmtree(path)
                    removed.append(str(path))
                elif path.is_file():
                    path.unlink()
                    removed.append(str(path))
            except OSError:
                continue
        # meta.json lives on root
        if self.meta_path.exists():
            try:
                self.meta_path.unlink()
                removed.append(str(self.meta_path))
            except OSError:
                pass

        # Recreate skeleton + empty-safe bootstrap
        self.dirs = ensure_app_dirs()
        self.meta_path = self.dirs["root"] / "meta.json"
        self._config = None
        self._bootstrap_from_examples()
        meta = {
            "first_run_completed": False,
            "cv_variants": [],
            "active_cv_id": "",
            "profile_patch_schema": PATCH_SCHEMA_VERSION,
            "last_wipe_at": stamp,
            "last_wipe_backup": backup_hint,
        }
        self.save_meta(meta)
        return {"removed": removed, "backup": backup_hint, "schema": PATCH_SCHEMA_VERSION}
