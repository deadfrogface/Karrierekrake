"""StepStone native application adapter.

If StepStone redirects to an external ATS, ApplicationManager should use ATSDetector.
"""

from __future__ import annotations

import logging
from pathlib import Path

from apply.base import ApplyResult, BaseApplier
from apply.detector import ATSDetector
from core.config import ApplicationProfile
from core.models import Job

logger = logging.getLogger("karrierekrake")


class StepstoneApplier(BaseApplier):
    CONFIRM_SELECTORS = (
        "[data-testid='application-success']",
        "[data-at='application-success']",
        "[data-genesis-element='APPLICATION_SENT']",
    )
    ERROR_SELECTORS = ("[data-testid*='error' i]", "[data-at*='error' i]")

    def _do_apply(
        self,
        job: Job,
        resume_pdf_path: Path | None,
        cover_letter_text: str,
        profile: ApplicationProfile,
    ) -> ApplyResult:
        logger.info("StepStone: applying to %s at %s", job.title, job.company)
        self._safe_goto(job.application_url or job.url)
        self._random_pause(1, 3)
        if self._detect_captcha():
            return ApplyResult(success=False, captcha_detected=True, error_message="CAPTCHA detected")

        # Detect redirect to external ATS
        ats = ATSDetector.detect(self.page.url)
        if ats not in ("stepstone", "unknown"):
            return ApplyResult(
                success=False,
                manual_required=True,
                needs_review=True,
                error_message=f"StepStone redirected to external ATS: {ats}",
            )

        self._safe_click("a:has-text('Jetzt bewerben'), button:has-text('Jetzt bewerben')", timeout=4000)
        self._random_pause(1, 2)
        self._fill_identity_fields(
            profile,
            first_name="input[name*='first'], input[id*='firstName']",
            last_name="input[name*='last_name' i], input[name*='lastName'], input[id*='lastName'], input[name*='nachname' i]",
            resume_pdf_path=resume_pdf_path,
        )
        self._fill_cover_letter(cover_letter_text, ["textarea[name*='cover'], textarea[id*='cover'], textarea[name*='anschreiben'], textarea[placeholder*='Anschreiben']"])
        unknown = self._unknown_required_fields(profile)
        if unknown:
            return ApplyResult(
                success=False,
                needs_review=True,
                manual_required=True,
                error_message=f"Unknown required fields: {', '.join(unknown)}",
            )
        return self._maybe_submit("button[type='submit'], button:has-text('Bewerbung absenden')")
