"""Greenhouse ATS application automation.

Adapted from AutoApply bot/apply/greenhouse.py (MIT).
"""

from __future__ import annotations

import logging
from pathlib import Path

from apply.base import ApplyResult, BaseApplier
from core.config import ApplicationProfile
from core.models import Job

logger = logging.getLogger("karrierekrake")


class GreenhouseApplier(BaseApplier):
    # Confirmation page lives under the posting: /<board>/jobs/<id>/confirmation.
    CONFIRM_URL_PATTERNS = (r"/jobs/\d+/confirmation",)
    CONFIRM_SELECTORS = ("#application_confirmation", "[data-testid='application-confirmation']")
    ERROR_SELECTORS = (".field-error-msg", "#error_flash", ".helper-text--error")

    def _do_apply(
        self,
        job: Job,
        resume_pdf_path: Path | None,
        cover_letter_text: str,
        profile: ApplicationProfile,
    ) -> ApplyResult:
        logger.info("Greenhouse: applying to %s at %s", job.title, job.company)
        self._safe_goto(job.application_url or job.url)
        self._random_pause(1, 3)

        if self._detect_captcha():
            return ApplyResult(success=False, captcha_detected=True, error_message="CAPTCHA detected")

        self._safe_click(
            "a#apply_button, a[href*='#app'], button[id*='apply'], a.btn[href*='apply']",
            timeout=3000,
        )
        self._random_pause(1, 2)
        self._fill_identity_fields(
            profile,
            first_name="#first_name, input[name*='first_name']",
            last_name="#last_name, input[name*='last_name']",
            email="#email, input[name*='email']",
            phone="#phone, input[name*='phone']",
            linkedin="input[name*='linkedin'], input[id*='linkedin']",
            resume_pdf_path=resume_pdf_path,
            file_selectors=[
                "input[type='file'][name*='resume']",
                "input[type='file'][id*='resume']",
                "input[type='file']",
            ],
        )
        self._fill_cover_letter(
            cover_letter_text,
            [
                "textarea[name*='cover_letter']",
                "textarea[id*='cover_letter']",
                "#cover_letter",
            ],
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
            "input[type='submit']#submit_app, input[type='submit'][value*='Submit'], "
            "button[type='submit'], input#submit_app"
        )
