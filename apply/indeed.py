"""Indeed Quick Apply. Adapted from AutoApply (MIT)."""

from __future__ import annotations

import logging
from pathlib import Path

from apply.base import ApplyResult, BaseApplier
from core.config import ApplicationProfile
from core.models import Job

logger = logging.getLogger("karrierekrake")

_SUBMIT_SEL = "button[aria-label*='Submit'], button[id*='submit']"
_CONTINUE_SEL = (
    "button.ia-continueButton, button[aria-label*='Continue'], button[id*='continue']"
)


class IndeedApplier(BaseApplier):
    CONFIRM_URL_PATTERNS = (r"smartapply\.indeed\.com/.*/post-apply",)
    CONFIRM_SELECTORS = ("[data-testid='ia-PostApply']", ".ia-PostApply")
    ERROR_SELECTORS = ("[data-testid*='error' i]", ".css-error-message", ".ia-ErrorMessage")

    def _do_apply(
        self,
        job: Job,
        resume_pdf_path: Path | None,
        cover_letter_text: str,
        profile: ApplicationProfile,
    ) -> ApplyResult:
        page = self.page
        logger.info("Indeed: applying to %s at %s", job.title, job.company)
        self._safe_goto(job.application_url or job.url)
        self._random_pause(1, 3)
        if self._detect_captcha():
            return ApplyResult(success=False, captcha_detected=True, error_message="CAPTCHA detected")
        apply_btn = self._wait_and_query(
            "button#indeedApplyButton, button[id*='indeedApply'], button[aria-label*='Apply now']",
            timeout=8000,
        )
        if not apply_btn:
            return ApplyResult(
                success=False,
                manual_required=True,
                needs_review=True,
                error_message="Indeed apply button not found / external ATS",
            )
        apply_btn.click()
        self._random_pause(2, 3)
        if "indeed.com" not in page.url:
            return ApplyResult(
                success=False,
                manual_required=True,
                needs_review=True,
                error_message="Redirected to external ATS",
            )
        for _ in range(8):
            if self._detect_captcha():
                return ApplyResult(success=False, captcha_detected=True, error_message="CAPTCHA detected")
            self._fill_identity_fields(
                profile,
                first_name="",
                last_name="",
                full_name="input[name='name'], input[id='name'], input[autocomplete='name']",
                email="input[name*='email'], input[id*='email']",
                phone="input[name*='phone'], input[id*='phone']",
                resume_pdf_path=resume_pdf_path,
            )
            self._fill_cover_letter(
                cover_letter_text,
                [
                    "textarea[name*='cover']",
                    "textarea[id*='cover']",
                    "textarea[aria-label*='cover']",
                    "textarea[placeholder*='cover']",
                    "textarea[name*='anschreiben']",
                    "textarea[placeholder*='Anschreiben']",
                ],
            )
            submit = self._wait_and_query(_SUBMIT_SEL, timeout=1500)
            if submit:
                # Central hard guard — never click submit outside _maybe_submit.
                unknown = self._unknown_required_fields(profile)
                if unknown:
                    return ApplyResult(
                        success=False,
                        needs_review=True,
                        manual_required=True,
                        error_message=f"Unknown required fields: {', '.join(unknown)}",
                    )
                return self._maybe_submit(_SUBMIT_SEL)
            if not self._safe_click(_CONTINUE_SEL, timeout=2000):
                break
            self._random_pause(1, 2)
        return ApplyResult(
            success=False,
            needs_review=True,
            error_message="Could not complete Indeed application",
        )
