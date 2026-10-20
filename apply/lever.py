"""Lever ATS application automation. Adapted from AutoApply (MIT)."""

from __future__ import annotations

import logging
from pathlib import Path

from apply.base import ApplyResult, BaseApplier
from core.config import ApplicationProfile
from core.models import Job

logger = logging.getLogger("karrierekrake")


class LeverApplier(BaseApplier):
    # Lever redirects to /<company>/<posting-uuid>/thanks.
    CONFIRM_URL_PATTERNS = (r"jobs\.lever\.co/[^/]+/[0-9a-f-]{36}/thanks",)
    CONFIRM_SELECTORS = (".application-confirmation", "[data-qa='msg-submit-success']")
    ERROR_SELECTORS = (".application-error", "[data-qa='msg-submit-error']", ".error-text")

    def _do_apply(
        self,
        job: Job,
        resume_pdf_path: Path | None,
        cover_letter_text: str,
        profile: ApplicationProfile,
    ) -> ApplyResult:
        apply_url = job.application_url or job.url
        if "/apply" not in apply_url:
            apply_url = apply_url.rstrip("/") + "/apply"
        logger.info("Lever: applying to %s at %s", job.title, job.company)
        self._safe_goto(apply_url)
        self._random_pause(1, 3)
        if self._detect_captcha():
            return ApplyResult(success=False, captcha_detected=True, error_message="CAPTCHA detected")
        form = self._wait_and_query(
            "form.application-form, form[action*='apply'], .application-form, form.postings-form",
            timeout=8000,
        )
        if not form:
            return ApplyResult(success=False, manual_required=True, needs_review=True, error_message="Lever form not found")
        self._fill_identity_fields(
            profile,
            first_name="",
            last_name="",
            full_name="input[name='name']",
            email="input[name='email']",
            phone="input[name='phone']",
            linkedin="input[name='urls[LinkedIn]'], input[name*='linkedin']",
            resume_pdf_path=resume_pdf_path,
            file_selectors=["input[type='file'][name='resume']", "input[type='file']"],
        )
        self._fill_cover_letter(
            cover_letter_text,
            ["textarea[name='comments'], textarea[name*='cover']"],
        )
        unknown = self._unknown_required_fields(profile)
        if unknown:
            return ApplyResult(
                success=False,
                needs_review=True,
                manual_required=True,
                error_message=f"Unknown required fields: {', '.join(unknown)}",
            )
        return self._maybe_submit(
            "button.postings-btn[type='submit'], button[type='submit'], input[type='submit']"
        )
