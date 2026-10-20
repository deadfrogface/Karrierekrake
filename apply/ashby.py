"""Ashby ATS application automation. Adapted from AutoApply (MIT)."""

from __future__ import annotations

import logging
from pathlib import Path

from apply.base import ApplyResult, BaseApplier
from core.config import ApplicationProfile
from core.models import Job

logger = logging.getLogger("karrierekrake")


class AshbyApplier(BaseApplier):
    CONFIRM_SELECTORS = (
        "[class*='ashby-application-form-success-container']",
        "[data-testid='application-submitted']",
    )
    ERROR_SELECTORS = (
        "[class*='ashby-application-form-field-error']",
        "[class*='ashby-application-form-failure']",
    )

    def _do_apply(
        self,
        job: Job,
        resume_pdf_path: Path | None,
        cover_letter_text: str,
        profile: ApplicationProfile,
    ) -> ApplyResult:
        logger.info("Ashby: applying to %s at %s", job.title, job.company)
        self._safe_goto(job.application_url or job.url)
        self._random_pause(1, 3)
        if self._detect_captcha():
            return ApplyResult(success=False, captcha_detected=True, error_message="CAPTCHA detected")
        self._safe_click('a:has-text("Apply"), button:has-text("Apply")', timeout=3000)
        self._random_pause(1, 2)
        self._fill_identity_fields(
            profile,
            first_name='input[name*="firstName"], input[name*="first_name"]',
            last_name='input[name*="lastName"], input[name*="last_name"]',
            email='input[type="email"], input[name*="email"]',
            phone='input[type="tel"], input[name*="phone"]',
            full_name='input[name="name"]',
            linkedin='input[name*="linkedin"], input[placeholder*="LinkedIn"]',
            resume_pdf_path=resume_pdf_path,
        )
        self._fill_cover_letter(
            cover_letter_text,
            ['textarea[name*="cover"], textarea[placeholder*="cover"]'],
        )
        unknown = self._unknown_required_labels(profile)
        if unknown:
            return ApplyResult(
                success=False,
                needs_review=True,
                error_message=f"Unknown questions: {', '.join(unknown[:3])}",
            )
        return self._maybe_submit('button[type="submit"]')
