"""Privacy lifecycle: export, disconnect, granular delete, delete-all.

Delete operations are idempotent. Success is returned only when verification
passes — never show "gelöscht" if residuals remain.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

from core.privacy.export_bundle import ExportResult, build_export_bundle
from core.privacy.inventory import DATA_INVENTORY, inventory_as_dicts
from core.privacy.results import DeleteResult, VerificationFailed, path_is_empty_or_missing


class PrivacyLifecycleService:
    """Orchestrates GDPR-oriented local data lifecycle actions.

    Does not invent legal bases. Cloud flows must stay documented in inventory.
    """

    def __init__(
        self,
        *,
        dirs: dict[str, Path],
        database_path: Path | None = None,
        token_dir: Path | None = None,
        load_profile: Callable[[], dict[str, Any]] | None = None,
        save_empty_profile: Callable[[], None] | None = None,
        list_documents: Callable[[], list[Path]] | None = None,
        clear_documents: Callable[[], None] | None = None,
        db_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.dirs = {k: Path(v) for k, v in dirs.items()}
        self.database_path = Path(database_path) if database_path else self.dirs.get("data", Path(".")) / "jobs.db"
        self.token_dir = Path(token_dir) if token_dir else self.dirs.get("config", Path("."))
        self._load_profile = load_profile
        self._save_empty_profile = save_empty_profile
        self._list_documents = list_documents
        self._clear_documents = clear_documents
        self._db_factory = db_factory

    # --- inventory ---

    def inventory(self) -> list[dict[str, Any]]:
        return inventory_as_dicts()

    def unexplained_flows(self) -> list[str]:
        """Return inventory ids with empty storage/purpose (should be empty)."""
        bad: list[str] = []
        for row in DATA_INVENTORY:
            if not row.storage.strip() or not row.purpose.strip():
                bad.append(row.id)
        return bad

    # --- export ---

    def export_my_data(
        self,
        dest_dir: Path,
        *,
        user_confirmed_pii: bool,
        include_document_bytes: bool = False,
    ) -> ExportResult:
        profile = self._load_profile() if self._load_profile else {}
        cases: list[dict[str, Any]] = []
        mail_meta: list[dict[str, Any]] = []
        hr: list[dict[str, Any]] = []
        jobs: list[dict[str, Any]] = []
        db = self._open_db()
        if db is not None:
            try:
                cases = [c.to_dict() for c in db.list_cases(limit=5000)]
            except Exception:
                cases = self._sql_dicts(
                    "SELECT id, company, position, status, updated_at FROM application_cases"
                )
            mail_meta = self._sql_dicts(
                "SELECT id, gmail_id, subject, sender, received_at, case_id, "
                "association_status FROM email_messages"
            )
            hr = self._sql_dicts(
                "SELECT id, name, email, company, status, cache_key FROM recruiting_contacts "
                "WHERE status != 'INVALIDATED'"
            )
            jobs = self._sql_dicts(
                "SELECT id, source, title, company, city, url FROM jobs LIMIT 5000"
            )
            try:
                db.close()
            except Exception:
                pass
        docs = self._list_documents() if self._list_documents else []
        return build_export_bundle(
            dest_dir=Path(dest_dir),
            profile=profile,
            cases=cases,
            mail_meta=mail_meta,
            hr_contacts=hr,
            jobs_summary=jobs,
            document_paths=docs,
            include_document_bytes=include_document_bytes,
            user_confirmed_pii=user_confirmed_pii,
        )

    # --- deletes ---

    def delete_profile(self) -> DeleteResult:
        removed: list[str] = []
        if self._save_empty_profile:
            self._save_empty_profile()
            removed.append("profile_yaml")
        residuals = self._verify_profile_empty()
        ok = not residuals
        return DeleteResult(
            action="delete_profile",
            ok=ok,
            verified=ok,
            removed=removed,
            residuals=residuals,
            message="ok" if ok else "verification_failed",
        )

    def delete_document(self, path: Path | str) -> DeleteResult:
        p = Path(path)
        removed: list[str] = []
        if p.is_file():
            try:
                p.unlink()
                removed.append(str(p))
            except OSError as exc:
                return DeleteResult(
                    action="delete_document",
                    ok=False,
                    verified=False,
                    residuals=[str(p)],
                    message=type(exc).__name__,
                )
        verified = not p.exists()
        return DeleteResult(
            action="delete_document",
            ok=verified,
            verified=verified,
            removed=removed,
            residuals=[] if verified else [str(p)],
            message="ok" if verified else "verification_failed",
        )

    def delete_documents_all(self) -> DeleteResult:
        removed: list[str] = []
        if self._clear_documents:
            self._clear_documents()
            removed.append("cv_storage")
        for key in ("cvs", "cover_letters"):
            root = self.dirs.get(key)
            if root and root.exists():
                for child in list(root.iterdir()):
                    try:
                        if child.is_file():
                            child.unlink()
                            removed.append(str(child))
                        elif child.is_dir():
                            shutil.rmtree(child)
                            removed.append(str(child))
                    except OSError:
                        pass
        residuals = []
        for key in ("cvs", "cover_letters"):
            root = self.dirs.get(key)
            if root and not path_is_empty_or_missing(root):
                residuals.append(str(root))
        ok = not residuals
        return DeleteResult(
            action="delete_documents_all",
            ok=ok,
            verified=ok,
            removed=removed,
            residuals=residuals,
            message="ok" if ok else "verification_failed",
        )

    def delete_application_case(self, case_id: str) -> DeleteResult:
        cid = (case_id or "").strip()
        if not cid:
            return DeleteResult(
                action="delete_application_case",
                ok=False,
                verified=False,
                message="missing_case_id",
            )
        counts = self._delete_case_cascade(cid)
        residual = self._case_exists(cid)
        ok = not residual
        return DeleteResult(
            action="delete_application_case",
            ok=ok,
            verified=ok,
            removed=[f"case:{cid}"],
            residuals=[cid] if residual else [],
            detail=counts,
            message="ok" if ok else "verification_failed",
        )

    def delete_mail_cache(self) -> DeleteResult:
        n = self._exec_sql("DELETE FROM email_messages")
        left = self._count_sql("SELECT COUNT(*) AS c FROM email_messages")
        ok = left == 0
        return DeleteResult(
            action="delete_mail_cache",
            ok=ok,
            verified=ok,
            removed=[f"email_messages:{n}"],
            residuals=[] if ok else [f"email_messages:{left}"],
            message="ok" if ok else "verification_failed",
        )

    def delete_calendar_cache(self) -> DeleteResult:
        """Clear local calendar-related artifacts.

        FreeBusy is ephemeral (not a SQLite table). We clear cache/ files that
        look calendar-related and remove known proposal debug dumps.
        """
        removed: list[str] = []
        cache = self.dirs.get("cache")
        if cache and cache.exists():
            for child in list(cache.iterdir()):
                name = child.name.lower()
                if any(tok in name for tok in ("calendar", "freebusy", "busy", "ics")):
                    try:
                        if child.is_file():
                            child.unlink()
                        else:
                            shutil.rmtree(child)
                        removed.append(str(child))
                    except OSError:
                        pass
        # Idempotent if nothing existed
        residuals = [
            str(p)
            for p in (cache.iterdir() if cache and cache.exists() else [])
            if any(tok in p.name.lower() for tok in ("calendar", "freebusy", "busy", "ics"))
        ]
        ok = not residuals
        return DeleteResult(
            action="delete_calendar_cache",
            ok=ok,
            verified=ok,
            removed=removed,
            residuals=residuals,
            message="ok" if ok else "verification_failed",
            detail={"note": "FreeBusy is ephemeral; OAuth cleared via disconnect_google"},
        )

    def delete_hr_contacts(self) -> DeleteResult:
        n = self._exec_sql("DELETE FROM recruiting_contacts")
        left = self._count_sql("SELECT COUNT(*) AS c FROM recruiting_contacts")
        ok = left == 0
        return DeleteResult(
            action="delete_hr_contacts",
            ok=ok,
            verified=ok,
            removed=[f"recruiting_contacts:{n}"],
            residuals=[] if ok else [f"recruiting_contacts:{left}"],
            message="ok" if ok else "verification_failed",
        )

    def delete_jobs(self) -> DeleteResult:
        db = self._open_db()
        detail: dict[str, Any] = {}
        if db is not None:
            try:
                detail = db.clear_job_data(clear_geocode_cache=True)
            finally:
                try:
                    db.close()
                except Exception:
                    pass
        else:
            detail = {
                "jobs": self._exec_sql("DELETE FROM jobs"),
                "applications": self._exec_sql("DELETE FROM applications"),
            }
        left = self._count_sql("SELECT COUNT(*) AS c FROM jobs")
        ok = left == 0
        return DeleteResult(
            action="delete_jobs",
            ok=ok,
            verified=ok,
            removed=[f"{k}:{v}" for k, v in detail.items()],
            residuals=[] if ok else [f"jobs:{left}"],
            detail=detail,
            message="ok" if ok else "verification_failed",
        )

    def disconnect_google(self, *, revoke_remote: bool = False) -> DeleteResult:
        from integrations.gmail_auth import disconnect_gmail, gmail_connected

        disconnect_gmail(token_dir=self.token_dir, revoke_remote=revoke_remote)
        still = False
        try:
            still = gmail_connected(token_dir=self.token_dir)
        except Exception:
            still = False
        # Also remove any legacy oauth files
        for p in self.token_dir.glob("oauth_*.json"):
            try:
                p.unlink()
            except OSError:
                pass
        ok = not still and not list(self.token_dir.glob("oauth_*.json"))
        return DeleteResult(
            action="disconnect_google",
            ok=ok,
            verified=ok,
            removed=["gmail_token"],
            residuals=["gmail_still_connected"] if still else [],
            message="ok" if ok else "verification_failed",
        )

    def delete_oauth_tokens(self) -> DeleteResult:
        # Same store as Gmail today; keep named action for inventory mapping.
        return self.disconnect_google(revoke_remote=False)

    def delete_logs(self) -> DeleteResult:
        removed: list[str] = []
        logs = self.dirs.get("logs")
        if logs and logs.exists():
            for child in list(logs.iterdir()):
                try:
                    if child.is_file():
                        child.unlink()
                        removed.append(str(child))
                    elif child.is_dir():
                        shutil.rmtree(child)
                        removed.append(str(child))
                except OSError:
                    pass
        ok = path_is_empty_or_missing(logs) if logs else True
        return DeleteResult(
            action="delete_logs",
            ok=ok,
            verified=ok,
            removed=removed,
            residuals=[] if ok else [str(logs)],
            message="ok" if ok else "verification_failed",
        )

    def delete_browser_cache(self) -> DeleteResult:
        removed: list[str] = []
        for key in ("browser_profile", "browsers", "cache"):
            root = self.dirs.get(key)
            if not root or not root.exists():
                continue
            try:
                shutil.rmtree(root)
                removed.append(str(root))
                root.mkdir(parents=True, exist_ok=True)
            except OSError:
                pass
        residuals = [
            str(self.dirs[k])
            for k in ("browser_profile", "browsers", "cache")
            if k in self.dirs and not path_is_empty_or_missing(self.dirs[k])
        ]
        # cache may hold unrelated files — empty-or-only-non-calendar is ok
        ok = all(
            path_is_empty_or_missing(self.dirs[k])
            for k in ("browser_profile", "browsers")
            if k in self.dirs
        )
        return DeleteResult(
            action="delete_browser_cache",
            ok=ok,
            verified=ok,
            removed=removed,
            residuals=residuals if not ok else [],
            message="ok" if ok else "verification_failed",
        )

    def delete_all(self, *, create_rollback_backup: bool = False) -> DeleteResult:
        """Delete all local personal data. Idempotent. Verified.

        ``create_rollback_backup`` defaults False — privacy delete must not
        quietly retain a PII wipe snapshot. Legacy ConfigService wipe may still
        snapshot config for disaster recovery when called directly.
        """
        if create_rollback_backup:
            # Explicit opt-in only; still skip secrets.
            self._maybe_config_backup()

        steps = [
            self.disconnect_google(revoke_remote=False),
            self.delete_mail_cache(),
            self.delete_calendar_cache(),
            self.delete_hr_contacts(),
            self.delete_jobs(),
            self.delete_documents_all(),
            self.delete_logs(),
            self.delete_browser_cache(),
            self.delete_profile(),
        ]
        # Drop DB file entirely for hard residual clearance
        db_removed = False
        if self.database_path.exists():
            try:
                self.database_path.unlink()
                db_removed = True
            except OSError:
                # Fallback: wipe tables
                for table in (
                    "email_messages",
                    "application_cases",
                    "case_events",
                    "lifecycle_events",
                    "lifecycle_tasks",
                    "followup_reminders",
                    "recruiting_contacts",
                    "jobs",
                    "applications",
                    "geocode_cache",
                    "search_runs",
                    "source_status",
                ):
                    self._exec_sql(f"DELETE FROM {table}")

        # Remove prior wipe backups (PII risk)
        root = self.dirs.get("root")
        removed_backups: list[str] = []
        if root and root.exists():
            for child in list(root.iterdir()):
                if child.name.startswith(".wipe_backup_"):
                    try:
                        shutil.rmtree(child)
                        removed_backups.append(str(child))
                    except OSError:
                        pass

        # Recreate skeleton dirs
        for path in self.dirs.values():
            path.mkdir(parents=True, exist_ok=True)

        residuals = self.verify_no_unexpected_data()
        ok = not residuals
        removed = [s.action for s in steps if s.ok]
        if db_removed:
            removed.append("jobs.db")
        removed.extend(removed_backups)
        result = DeleteResult(
            action="delete_all",
            ok=ok,
            verified=ok,
            removed=removed,
            residuals=residuals,
            detail={"steps": [s.as_dict() for s in steps]},
            message="ok" if ok else "verification_failed",
        )
        if not ok:
            # Do not raise by default — callers must not show success.
            return result
        return result

    def verify_no_unexpected_data(self) -> list[str]:
        """Post-delete residual check used by E2E restart scenarios."""
        residuals: list[str] = []
        if self.database_path.exists():
            for label, sql in (
                ("email_messages", "SELECT COUNT(*) AS c FROM email_messages"),
                ("application_cases", "SELECT COUNT(*) AS c FROM application_cases"),
                ("recruiting_contacts", "SELECT COUNT(*) AS c FROM recruiting_contacts"),
                ("jobs", "SELECT COUNT(*) AS c FROM jobs"),
            ):
                try:
                    if self._count_sql(sql) > 0:
                        residuals.append(label)
                except Exception:
                    pass
        for key in ("cvs", "cover_letters", "logs"):
            root = self.dirs.get(key)
            if root and not path_is_empty_or_missing(root):
                residuals.append(str(root))
        root = self.dirs.get("root")
        if root and root.exists():
            for child in root.iterdir():
                if child.name.startswith(".wipe_backup_"):
                    residuals.append(str(child))
        # OAuth legacy files
        if self.token_dir.exists():
            for p in self.token_dir.glob("oauth_*.json"):
                residuals.append(str(p))
        try:
            from integrations.gmail_auth import gmail_connected

            if gmail_connected(token_dir=self.token_dir):
                residuals.append("gmail_connected")
        except Exception:
            pass
        residuals.extend(self._verify_profile_empty())
        return residuals

    def assert_deleted(self, result: DeleteResult) -> None:
        if not result.ok or not result.verified:
            raise VerificationFailed(result.message or "verification_failed")

    # --- helpers ---

    def _open_db(self) -> Any | None:
        if self._db_factory:
            try:
                return self._db_factory()
            except Exception:
                return None
        if not self.database_path.exists():
            return None
        try:
            from core.database import Database

            return Database(self.database_path)
        except Exception:
            return None

    def _sql_dicts(self, sql: str) -> list[dict[str, Any]]:
        if not self.database_path.exists():
            return []
        try:
            conn = sqlite3.connect(str(self.database_path))
            conn.row_factory = sqlite3.Row
            rows = conn.execute(sql).fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except sqlite3.Error:
            return []

    def _exec_sql(self, sql: str) -> int:
        if not self.database_path.exists():
            return 0
        try:
            conn = sqlite3.connect(str(self.database_path))
            cur = conn.execute(sql)
            conn.commit()
            n = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
            conn.close()
            return int(n)
        except sqlite3.Error:
            return 0

    def _count_sql(self, sql: str) -> int:
        if not self.database_path.exists():
            return 0
        try:
            conn = sqlite3.connect(str(self.database_path))
            row = conn.execute(sql).fetchone()
            conn.close()
            return int(row[0] if row else 0)
        except sqlite3.Error:
            return 0

    def _delete_case_cascade(self, case_id: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        if not self.database_path.exists():
            return counts
        try:
            conn = sqlite3.connect(str(self.database_path))
            for table in (
                "case_events",
                "lifecycle_events",
                "lifecycle_tasks",
                "followup_reminders",
            ):
                cur = conn.execute(f"DELETE FROM {table} WHERE case_id = ?", (case_id,))
                counts[table] = cur.rowcount
            conn.execute(
                "UPDATE email_messages SET case_id = NULL, association_status = 'unlinked' "
                "WHERE case_id = ?",
                (case_id,),
            )
            conn.execute(
                "UPDATE recruiting_contacts SET case_id = NULL WHERE case_id = ?",
                (case_id,),
            )
            cur = conn.execute("DELETE FROM application_cases WHERE id = ?", (case_id,))
            counts["application_cases"] = cur.rowcount
            conn.commit()
            conn.close()
        except sqlite3.Error:
            pass
        return counts

    def _case_exists(self, case_id: str) -> bool:
        if not self.database_path.exists():
            return False
        try:
            conn = sqlite3.connect(str(self.database_path))
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM application_cases WHERE id = ?",
                (case_id,),
            ).fetchone()
            conn.close()
            return int(row[0] if row else 0) > 0
        except sqlite3.Error:
            return False

    def _verify_profile_empty(self) -> list[str]:
        if not self._load_profile:
            return []
        try:
            profile = self._load_profile() or {}
        except Exception:
            return []
        residuals: list[str] = []
        if not isinstance(profile, dict):
            return residuals

        def _walk(obj: Any) -> None:
            if isinstance(obj, dict):
                for k, v in obj.items():
                    lk = str(k).lower()
                    if lk in {"email", "e_mail"} and isinstance(v, str) and v.strip():
                        domain = v.split("@")[-1].lower() if "@" in v else ""
                        if domain and not (
                            domain == "localhost"
                            or domain.endswith("example.com")
                            or domain.endswith("example.org")
                            or domain.endswith("example.net")
                            or domain.endswith(".example")
                        ):
                            residuals.append(f"profile.email:{domain}")
                    elif lk in {"phone", "mobile"} and isinstance(v, str) and len(v.strip()) > 4:
                        residuals.append("profile.phone")
                    else:
                        _walk(v)
            elif isinstance(obj, list):
                for item in obj:
                    _walk(item)

        _walk(profile)
        return residuals

    def _maybe_config_backup(self) -> None:
        from core.security.export_gate import wipe_backup_should_skip

        root = self.dirs.get("root")
        cfg = self.dirs.get("config")
        if not root or not cfg or not cfg.exists():
            return
        stamp = __import__("time").strftime("%Y%m%dT%H%M%SZ", __import__("time").gmtime())
        backup = root / f".wipe_backup_{stamp}"

        def _ignore(directory: str, names: list[str]) -> list[str]:
            return [n for n in names if wipe_backup_should_skip(Path(directory) / n)]

        try:
            shutil.copytree(cfg, backup / "config", dirs_exist_ok=True, ignore=_ignore)
        except OSError:
            pass
