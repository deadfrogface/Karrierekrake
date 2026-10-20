"""Workday ATS application automation. Adapted from AutoApply (MIT), simplified for dry-run safety."""

from __future__ import annotations

import logging
from pathlib import Path

from apply.base import ApplyResult, BaseApplier
from core.config import ApplicationProfile
from core.models import Job

logger = logging.getLogger("karrierekrake")

# Submit must go through _maybe_submit (dry_run / review guards). Include DE labels.
_SUBMIT_SEL = (
    "button[data-automation-id='pageFooterNextButton']:has-text('Submit'), "
    "button[data-automation-id='pageFooterNextButton']:has-text('Absenden'), "
    "button[data-automation-id='pageFooterNextButton']:has-text('Senden'), "
    "button:has-text('Submit'), "
    "button:has-text('Absenden'), "
    "button:has-text('Senden')"
)
# Next/Continue only — never bare pageFooterNextButton (that also matches Absenden).
_NEXT_SEL = (
    "button[data-automation-id='pageFooterNextButton']:has-text('Next'), "
    "button[data-automation-id='pageFooterNextButton']:has-text('Continue'), "
    "button[data-automation-id='pageFooterNextButton']:has-text('Weiter'), "
    "button:has-text('Next'), "
    "button:has-text('Continue'), "
    "button:has-text('Weiter')"
)


class WorkdayApplier(BaseApplier):
    CONFIRM_SELECTORS = (
        "[data-automation-id='congratulationsPopup']",
        "[data-automation-id='applicationSubmittedMessage']",
    )
    ERROR_SELECTORS = (
        "[data-automation-id='errorMessage']",
        "[data-automation-id='errorBanner']",
    )

    def _do_apply(
        self,
        job: Job,
        resume_pdf_path: Path | None,
        cover_letter_text: str,
        profile: ApplicationProfile,
    ) -> ApplyResult:
        logger.info("Workday: applying to %s at %s", job.title, job.company)
        self._safe_goto(job.application_url or job.url)
        self._random_pause(2, 4)
        if self._detect_captcha():
            return ApplyResult(success=False, captcha_detected=True, error_message="CAPTCHA detected")

        self._safe_click(
            "a[data-automation-id='jobPostingApplyButton'], button[data-automation-id='adventureButton'], a:has-text('Apply')",
            timeout=5000,
        )
        self._random_pause(2, 3)

        # Create account / sign in walls are common
        if self.page.query_selector("input[data-automation-id='email'], text=Sign In"):
            # Try guest apply if available
            if not self._safe_click("button:has-text('Apply Manually'), a:has-text('Apply Manually')", timeout=3000):
                return ApplyResult(
                    success=False,
                    login_required=True,
                    needs_review=True,
                    error_message="Workday login required",
                )

        self._fill_identity_fields(
            profile,
            first_name="input[data-automation-id='legalNameSection_firstName'], input[name*='firstName']",
            last_name="input[data-automation-id='legalNameSection_lastName'], input[name*='lastName']",
            email="input[data-automation-id='email'], input[type='email']",
            phone="input[data-automation-id='phone-number'], input[type='tel']",
            resume_pdf_path=resume_pdf_path,
        )
        self._fill_cover_letter(
            cover_letter_text,
            [
                "textarea[name*='cover' i]",
                "textarea[id*='cover' i]",
                "textarea[data-automation-id*='cover' i]",
                "textarea[placeholder*='cover' i]",
                "textarea[aria-label*='cover' i]",
                "textarea[placeholder*='Anschreiben' i]",
            ],
        )

        # Multi-step: advance carefully; stop before final submit in dry_run
        for _ in range(6):
            if self._detect_captcha():
                return ApplyResult(success=False, captcha_detected=True, error_message="CAPTCHA detected")
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
            if not self._safe_click(_NEXT_SEL, timeout=2500):
                break
            self._random_pause(1, 2)

        return ApplyResult(success=False, needs_review=True, manual_required=True, error_message="Workday form incomplete")
