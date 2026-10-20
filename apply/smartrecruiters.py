"""SmartRecruiters application adapter (Germany-relevant ATS)."""

from __future__ import annotations

import logging
from pathlib import Path

from apply.base import ApplyResult, BaseApplier
from core.config import ApplicationProfile
from core.models import Job

logger = logging.getLogger("karrierekrake")


class SmartRecruitersApplier(BaseApplier):
    CONFIRM_URL_PATTERNS = (r"smartrecruiters\.com/.*/(?:confirmation|thank-you)",)
    CONFIRM_SELECTORS = ("[data-test='application-confirmation']", "oc-application-confirmation")
    ERROR_SELECTORS = ("[data-test*='error' i]", ".c-spl-error-message")

    def _do_apply(
        self,
        job: Job,
        resume_pdf_path: Path | None,
        cover_letter_text: str,
        profile: ApplicationProfile,
    ) -> ApplyResult:
        logger.info("SmartRecruiters: applying to %s at %s", job.title, job.company)
        self._safe_goto(job.application_url or job.url)
        self._random_pause(1, 3)
        if self._detect_captcha():
            return ApplyResult(success=False, captcha_detected=True, error_message="CAPTCHA detected")
        self._safe_click(
            "button:has-text('Apply'), a:has-text('Apply'), button:has-text('Jetzt bewerben')",
            timeout=4000,
        )
        self._fill_identity_fields(
            profile,
            first_name="input[name*='firstName' i], input[id*='firstName' i], input[name*='vorname' i]",
            last_name="input[name*='lastName' i], input[id*='lastName' i], input[name*='nachname' i]",
            email="input[type='email'], input[name*='email' i], input[id*='email' i]",
            phone="input[type='tel'], input[name*='phone' i], input[name*='tel' i]",
            resume_pdf_path=resume_pdf_path,
        )
        self._fill_german_profile_fields(profile)
        self._fill_cover_letter(cover_letter_text)
        unknown = self._unknown_required_fields(
            profile,
            skip_tokens=(
                "first",
                "last",
                "email",
                "phone",
                "tel",
                "resume",
                "cover",
                "file",
                "cv",
                "street",
                "postal",
                "city",
                "salary",
            ),
        )
        if unknown:
            return ApplyResult(
                success=False,
                needs_review=True,
                error_message=f"Unknown SmartRecruiters fields: {', '.join(unknown[:5])}",
            )
        result = self._maybe_submit(
            "button[type='submit'], button:has-text('Submit'), button:has-text('Send')"
        )
        result.needs_review = True
        if not result.error_message:
            result.error_message = "SmartRecruiters partially supported — review before final submit"
        return result
