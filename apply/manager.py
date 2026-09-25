"""Application manager — safety checks and adapter dispatch."""

from __future__ import annotations

import logging
import time
from pathlib import Path

from apply.ashby import AshbyApplier
from apply.base import ApplyResult, BaseApplier
from apply.detector import ATSDetector, classify_ats_support
from apply.greenhouse import GreenhouseApplier
from apply.indeed import IndeedApplier
from apply.lever import LeverApplier
from apply.linkedin import LinkedInApplier
from apply.personio import PersonioApplier
from apply.preview import build_application_preview
from apply.smartrecruiters import SmartRecruitersApplier
from apply.stepstone import StepstoneApplier
from apply.successfactors import SuccessFactorsApplier
from apply.workday import WorkdayApplier
from core.config import AppConfig
from core.application_queue import is_application_source
from core.cover_letter import compose_cover_letter, save_cover_letter
from core.parser_debt import auto_actions_blocked
from core.database import Database
from core.known_jobs import refuse_reapply
from core.lifecycle import CaseStatus
from core.models import ApplicationRecord, Job, JobStatus, OperatingMode, utc_now_iso

logger = logging.getLogger("karrierekrake")

APPLIERS: dict[str, type[BaseApplier]] = {
    "greenhouse": GreenhouseApplier,
    "lever": LeverApplier,
    "ashby": AshbyApplier,
    "indeed": IndeedApplier,
    "linkedin": LinkedInApplier,
    "workday": WorkdayApplier,
    "personio": PersonioApplier,
    "stepstone": StepstoneApplier,
    "smartrecruiters": SmartRecruitersApplier,
    "successfactors": SuccessFactorsApplier,
}


class ApplicationManager:
    def __init__(self, config: AppConfig, db: Database, page=None) -> None:
        self.config = config
        self.db = db
        self.page = page
        self.applied_this_run = 0
        self.failed_this_run = 0
        # Fail-closed submit gate: snapshot at manager creation. A mid-run settings
        # escalate (dry_run off / auto-submit on) must never open this gate.
        # Tightening safety live still closes submit via _submit_allowed().
        settings = config.settings
        self._submit_gate_open = (
            settings.mode == OperatingMode.FULLY_AUTOMATIC.value
            and not bool(settings.dry_run)
            and bool(getattr(settings, "automatic_submission", False))
        )

    def _resolve_cv_path(self) -> Path | None:
        """Resolve the active CV (role=cv). Cover letters never win."""
        from core.documents import resolve_active_cv_path

        meta: dict = {}
        meta_path = self.config.root / "meta.json"
        if meta_path.is_file():
            try:
                import json

                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                meta = {}
        path = resolve_active_cv_path(
            meta,
            fallback_cv_path=self.config.application.cv_path,
            root=self.config.root,
        )
        if path is None:
            return None
        # Refuse non-cv roles even if path was somehow set.
        variants = meta.get("cv_variants") or []
        for v in variants:
            if str(v.get("path") or "") in {str(path), self.config.application.cv_path}:
                from core.documents import normalize_role

                if normalize_role(v.get("role")) != "cv":
                    return None
        return path

    def _submit_allowed(self, settings, *, force_submit: bool | None) -> bool:
        """Final submit only when start-of-run gate AND live settings permit it."""
        live_dry = bool(settings.dry_run)
        if force_submit is not None:
            return bool(force_submit) and not live_dry and self._submit_gate_open
        live_ok = (
            settings.mode == OperatingMode.FULLY_AUTOMATIC.value
            and not live_dry
            and bool(getattr(settings, "automatic_submission", False))
        )
        return bool(self._submit_gate_open and live_ok)

    def can_auto_apply(self, job: Job) -> tuple[bool, str]:
        settings = self.config.settings
        debt = auto_actions_blocked(self.config)
        if debt.blocked:
            return False, debt.reason
        if not is_application_source(job):
            return False, "source not allowlisted"
        if job.match_score < settings.minimum_match_for_auto_apply:
            return False, f"score {job.match_score} < {settings.minimum_match_for_auto_apply}"
        # Defense in depth: ApplicationCase known statuses even if search dedup failed.
        blocked, block_reason = refuse_reapply(self.db, job)
        if blocked:
            return False, block_reason
        if self.db.has_applied(job):
            return False, "already applied (safety)"
        if self.applied_this_run >= settings.max_applications_per_run:
            return False, "max applications per run reached"
        if self.db.count_applications_today() >= settings.max_applications_per_day:
            return False, "max applications per day reached"
        if self.failed_this_run >= settings.max_failed_applications_per_run:
            return False, "max failed applications per run reached"
        app = self.config.application
        missing = [
            f
            for f, v in {
                "first_name": app.first_name,
                "last_name": app.last_name,
                "email": app.email,
                "phone": app.phone,
                "cv_path": app.cv_path,
            }.items()
            if not str(v or "").strip()
        ]
        if missing:
            return False, f"missing profile fields: {', '.join(missing)}"
        cv_path = self._resolve_cv_path()
        if cv_path is None or not cv_path.is_file():
            return False, "CV file missing or unreadable"
        # Role hard-block: active document must be a CV.
        try:
            with cv_path.open("rb") as fh:
                fh.read(1)
        except OSError:
            return False, "CV file missing or unreadable"
        # Treat stored "unknown" like empty so URL re-detection can still win.
        ats = (
            job.ats_type
            if job.ats_type and job.ats_type != "unknown"
            else ATSDetector.detect(job.application_url or job.url)
        )
        if ats == "unknown" or ats not in APPLIERS:
            return False, f"ATS unsupported: {ats}"
        return True, "ok"

    def prepare_and_apply(self, job: Job, *, force_submit: bool | None = None) -> ApplyResult:
        settings = self.config.settings
        mode = settings.mode
        submit = self._submit_allowed(settings, force_submit=force_submit)

        allowed, reason = self.can_auto_apply(job)
        if not allowed:
            # Hard safety blocks apply in every mode (review must not open ATS
            # without CV / against duplicates). Soft reasons (score, ATS) still
            # allow review-mode preview attempts.
            hard_block = (
                reason.startswith("already applied")
                or reason.startswith("missing profile fields")
                or reason.startswith("CV file missing")
                or reason.startswith("max applications")
                or reason.startswith("max failed")
                or reason.startswith("source not allowlisted")
                or reason.startswith("demo source")
                or reason.startswith("needs_confirmation")
            )
            if hard_block or mode == OperatingMode.FULLY_AUTOMATIC.value:
                existing = self.db.get_job(job.id) if job.id else None
                protected = {
                    JobStatus.APPLIED.value,
                    JobStatus.FAILED.value,
                    JobStatus.NEEDS_REVIEW.value,
                    JobStatus.CAPTCHA.value,
                    JobStatus.APPLYING.value,
                }
                # Never demote an attempt/outcome row when blocking re-entry.
                if existing is None or existing.status not in protected:
                    job.status = JobStatus.NEEDS_REVIEW.value
                    job.rejection_reasons = list({*job.rejection_reasons, reason})
                    self.db.upsert_job(job)
                return ApplyResult(success=False, needs_review=True, error_message=reason)

        ats = ATSDetector.detect(job.application_url or job.url)
        job.ats_type = ats
        support, note = classify_ats_support(ats, job.application_url or job.url)
        # Safety: never final-submit for partial/unknown ATS (Personio etc.),
        # even under fully_automatic + automatic_submission.
        if submit and support != "supported":
            submit = False
            logger.info(
                "Submit blocked: ATS %s classified as %s (final submit only when supported)",
                ats,
                support,
            )
        preview = build_application_preview(
            job,
            self.config,
            meta=(
                __import__("json").loads(
                    (self.config.root / "meta.json").read_text(encoding="utf-8")
                )
                if (self.config.root / "meta.json").is_file()
                else None
            ),
        )
        if getattr(preview, "quality_gate", "") == "BLOCKED":
            reason = "CV hard-block: " + "; ".join(preview.warnings[:2] or ["document role/CV invalid"])
            job.status = JobStatus.NEEDS_REVIEW.value
            job.rejection_reasons = list({*job.rejection_reasons, reason})
            self.db.upsert_job(job)
            return ApplyResult(success=False, needs_review=True, error_message=reason)
        if ats == "unknown" or ats not in APPLIERS:
            job.status = JobStatus.NEEDS_REVIEW.value
            job.rejection_reasons = list(
                {
                    *job.rejection_reasons,
                    f"ATS {ats}: {note}",
                    f"URL: {job.application_url or job.url or '—'}",
                }
            )
            self.db.upsert_job(job)
            self.db.save_application(
                ApplicationRecord(
                    job_id=job.id,
                    company=job.company,
                    position=job.title,
                    application_date=utc_now_iso(),
                    platform=ats,
                    status=JobStatus.NEEDS_REVIEW.value,
                    cv_used=str(self.config.application.cv_path or ""),
                    cover_letter_used="",
                    result="manual_required",
                    error_message=(
                        f"Unsupported ATS: {ats} ({support}). {note}\n\n"
                        f"--- PREVIEW ---\n{preview.text_report()}"
                    ),
                )
            )
            return ApplyResult(
                success=False,
                needs_review=True,
                manual_required=True,
                error_message=f"Unsupported ATS: {ats} — open URL manually",
            )

        if self.page is None:
            return ApplyResult(success=False, error_message="Browser page not available")

        # Final never-apply-twice check
        if self.db.has_applied(job):
            return ApplyResult(success=False, error_message="already applied (safety)")

        outcome = compose_cover_letter(job, self.config)
        cover = outcome.text if outcome.ok else ""
        cover_path: Path | str = ""
        if outcome.ok:
            from core.cover_guard import confirmed_profile_text, screen_cover_letter

            debt = auto_actions_blocked(self.config)
            claim_screen = screen_cover_letter(
                cover,
                confirmed_text=confirmed_profile_text(self.config),
                job_text=f"{job.title} {job.description}",
                allowed_context=f"{job.title} {job.company}",
            )
            if debt.blocked or not cover.strip() or not claim_screen.ok:
                reason = debt.reason or (
                    "needs_confirmation: unsubstantiated_claims"
                    if not claim_screen.ok
                    else "needs_confirmation: cover_blocked"
                )
                job.status = JobStatus.NEEDS_REVIEW.value
                job.rejection_reasons = list({*job.rejection_reasons, reason})
                self.db.upsert_job(job)
                return ApplyResult(success=False, needs_review=True, error_message=reason)
            cover_path = self.config.root / "cover_letters" / f"{job.id}.txt"
            save_cover_letter(cover, cover_path)
        cv_path = self._resolve_cv_path()

        job.status = JobStatus.APPLYING.value
        self.db.upsert_job(job)

        # Central safety: dry_run always forces submit=False on every applier.
        # Fail-closed: live dry_run OR closed start gate both force dry.
        effective_dry_run = bool(settings.dry_run) or not submit or not self._submit_gate_open
        effective_submit = bool(submit) and not effective_dry_run
        if effective_dry_run:
            logger.info(
                "TEST MODE: ApplicationManager will not allow final submit "
                "(settings.dry_run=%s, mode=%s, force_submit=%s, gate_open=%s)",
                settings.dry_run,
                mode,
                force_submit,
                self._submit_gate_open,
            )
        applier_cls = APPLIERS[ats]
        applier = applier_cls(
            self.page, dry_run=effective_dry_run, submit=effective_submit
        )
        result = applier.apply(
            job,
            cv_path if cv_path is not None and cv_path.is_file() else None,
            cover,
            self.config.application,
        )

        # Always attach intended preview for dry-run / review inspection.
        preview_blob = preview.text_report()
        if result.dry_run_stopped or result.needs_review or not result.submitted:
            extra = (result.error_message or "").strip()
            result.error_message = (
                f"{extra}\n\n--- PREVIEW ---\n{preview_blob}".strip()
                if extra
                else f"--- PREVIEW ---\n{preview_blob}"
            )

        status = JobStatus.NEEDS_REVIEW.value
        if result.captcha_detected:
            status = JobStatus.CAPTCHA.value
            self.failed_this_run += 1
        elif result.needs_review or result.manual_required or result.dry_run_stopped:
            status = JobStatus.NEEDS_REVIEW.value
        elif result.success and result.submitted:
            status = JobStatus.APPLIED.value
            self.applied_this_run += 1
        elif result.success and not result.submitted:
            status = JobStatus.NEEDS_REVIEW.value
        else:
            status = JobStatus.FAILED.value
            self.failed_this_run += 1

        job.status = status
        self.db.upsert_job(job)
        self.db.save_application(
            ApplicationRecord(
                job_id=job.id,
                company=job.company,
                position=job.title,
                application_date=utc_now_iso(),
                platform=ats,
                status=status,
                cv_used=str(cv_path or ""),
                cover_letter_used=str(cover_path),
                result="submitted" if result.submitted else ("dry_run" if result.dry_run_stopped else "stopped"),
                error_message=result.error_message or "",
            )
        )
        # Lifecycle: track ApplicationCase so search never rediscovers as new.
        case_status = CaseStatus.TO_APPLY.value
        if status == JobStatus.APPLIED.value:
            case_status = CaseStatus.APPLIED.value
        elif status in {
            JobStatus.NEEDS_REVIEW.value,
            JobStatus.CAPTCHA.value,
            JobStatus.FAILED.value,
            JobStatus.APPLYING.value,
        }:
            # Still suppress rediscovery of attempted vacancies.
            case_status = CaseStatus.APPLIED.value
        try:
            self.db.ensure_case_from_job(job, status=case_status)
        except Exception:
            logger.exception("Failed to upsert ApplicationCase for job %s", job.id)
        time.sleep(max(1, settings.delay_between_applications_seconds))
        return result
