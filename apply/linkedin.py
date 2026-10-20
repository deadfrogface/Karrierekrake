"""LinkedIn Easy Apply. Adapted from AutoApply (MIT)."""

from __future__ import annotations

import logging
from pathlib import Path

from apply.base import ApplyResult, BaseApplier
from core.config import ApplicationProfile
from core.models import Job

logger = logging.getLogger("karrierekrake")

_SUBMIT_SEL = (
    "button[aria-label*='Submit application'], button[aria-label*='Submit']"
)
_NEXT_SEL = (
    "button[aria-label*='Continue'], button[aria-label*='Next'], "
    "button[aria-label*='Review']"
)


class LinkedInApplier(BaseApplier):
    # Easy Apply shows a post-apply modal for this job; the apply modal is gone.
    CONFIRM_SELECTORS = (
        "[data-test-modal-id='post-apply-modal']",
        "div[aria-labelledby*='post-apply' i]",
    )
    ERROR_SELECTORS = (".artdeco-inline-feedback--error",)

    def _do_apply(
        self,
        job: Job,
        resume_pdf_path: Path | None,
        cover_letter_text: str,
        profile: ApplicationProfile,
    ) -> ApplyResult:
        logger.info("LinkedIn: applying to %s at %s", job.title, job.company)
        self._safe_goto(job.application_url or job.url)
        self._random_pause(1, 3)
        if self._detect_captcha():
            return ApplyResult(success=False, captcha_detected=True, error_message="CAPTCHA detected")
        btn = self._wait_and_query(
            "button.jobs-apply-button, button[aria-label*='Easy Apply'], .jobs-apply-button--top-card",
            timeout=8000,
        )
        if not btn:
            return ApplyResult(
                success=False,
                manual_required=True,
                needs_review=True,
                error_message="Easy Apply button not found",
            )
        btn.click()
        self._random_pause(1, 2)
        for _ in range(10):
            if self._detect_captcha():
                return ApplyResult(success=False, captcha_detected=True, error_message="CAPTCHA detected")
            self._fill_identity_fields(
                profile,
                first_name="",
                last_name="",
                email="",
                phone="input[name*='phone'], input[id*='phone']",
                resume_pdf_path=resume_pdf_path,
            )
            self._fill_cover_letter(
                cover_letter_text,
                ["textarea[name*='cover'], textarea[id*='cover']"],
            )
            submit = self._wait_and_query(_SUBMIT_SEL, timeout=1500)
            if submit:
                unknown = self._unknown_required_fields(profile)
                if unknown:
                    return ApplyResult(
                        success=False,
                        needs_review=True,
                        manual_required=True,
                        error_message=f"Unknown required fields: {', '.join(unknown)}",
                    )
                return self._maybe_submit(_SUBMIT_SEL)
            if not self._safe_click(_NEXT_SEL, timeout=2000):
                break
            self._random_pause(1, 2)
        return ApplyResult(
            success=False,
            needs_review=True,
            error_message="Could not complete Easy Apply",
        )
