"""SAP SuccessFactors application adapter — conservative needs_review defaults."""

from __future__ import annotations

import logging
from pathlib import Path

from apply.base import ApplyResult, BaseApplier
from core.config import ApplicationProfile
from core.models import Job

logger = logging.getLogger("karrierekrake")

_SUBMIT_SEL = "button[type='submit'], button:has-text('Submit'), button:has-text('Senden')"


class SuccessFactorsApplier(BaseApplier):
    CONFIRM_SELECTORS = ("#applicationConfirmation", "[id*='applyConfirm' i]", ".applySuccessMessage")
    ERROR_SELECTORS = (".sfErrorMessage", "[id*='errorMessage' i]", ".globalErrorMessage")

    def _do_apply(
        self,
        job: Job,
        resume_pdf_path: Path | None,
        cover_letter_text: str,
        profile: ApplicationProfile,
    ) -> ApplyResult:
        logger.info("SuccessFactors: opening %s at %s", job.title, job.company)
        self._safe_goto(job.application_url or job.url)
        self._random_pause(2, 4)
        if self._detect_captcha():
            return ApplyResult(success=False, captcha_detected=True, error_message="CAPTCHA detected")

        # Fill visible identity + address fields only — do not auto-walk multi-page wizards.
        self._fill_identity_fields(
            profile,
            first_name="input[id*='first' i], input[name*='first' i], input[name*='vorname' i]",
            last_name="input[id*='last' i], input[name*='last' i], input[name*='nachname' i]",
            email="input[type='email'], input[name*='email' i]",
            phone="input[type='tel'], input[name*='phone' i], input[name*='telefon' i]",
            resume_pdf_path=resume_pdf_path,
        )
        self._fill_german_profile_fields(profile)
        self._fill_cover_letter(cover_letter_text)

        # Many SF portals require login / complex multi-page flows
        if self.page.query_selector("input[type='password'], text=Sign In, text=Anmelden"):
            return ApplyResult(
                success=False,
                login_required=True,
                needs_review=True,
                error_message="SuccessFactors login required",
            )

        # Always use the central submit guard when a submit control is present.
        if self._wait_and_query(_SUBMIT_SEL, timeout=2000):
            unknown = self._unknown_required_fields(profile)
            if unknown:
                return ApplyResult(
                    success=False,
                    needs_review=True,
                    manual_required=True,
                    error_message=f"Unknown required fields: {', '.join(unknown)}",
                )
            result = self._maybe_submit(_SUBMIT_SEL)
            result.needs_review = True
            if not result.error_message:
                result.error_message = "SuccessFactors partially supported — review recommended"
            return result

        return ApplyResult(
            success=False,
            needs_review=True,
            manual_required=True,
            error_message="SuccessFactors auto-submit not reliable — needs_review",
        )
