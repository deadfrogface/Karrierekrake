"""Personio careers application adapter (Germany-focused)."""

from __future__ import annotations

import logging
from pathlib import Path

from apply.base import ApplyResult, BaseApplier
from core.config import ApplicationProfile
from core.models import Job

logger = logging.getLogger("karrierekrake")


class PersonioApplier(BaseApplier):
    CONFIRM_URL_PATTERNS = (r"jobs\.personio\.(?:de|com)/.*(?:application-success|bewerbung-erfolgreich)",)
    CONFIRM_SELECTORS = ("[data-test-id='application-success']", "[data-testid='application-success']")
    ERROR_SELECTORS = ("[data-test-id*='error' i]", "[data-testid*='field-error' i]")

    def _do_apply(
        self,
        job: Job,
        resume_pdf_path: Path | None,
        cover_letter_text: str,
        profile: ApplicationProfile,
    ) -> ApplyResult:
        logger.info("Personio: applying to %s at %s", job.title, job.company)
        self._safe_goto(job.application_url or job.url)
        self._random_pause(1, 3)
        if self._detect_captcha():
            return ApplyResult(success=False, captcha_detected=True, error_message="CAPTCHA detected")

        self._safe_click(
            "a:has-text('Jetzt bewerben'), button:has-text('Jetzt bewerben'), "
            "a:has-text('Apply'), button:has-text('Apply')",
            timeout=4000,
        )
        self._random_pause(1, 2)

        uploaded = self._fill_identity_fields(
            profile,
            phone=(
                "input[type='tel'], input[name*='phone' i], "
                "input[name*='telefon' i], input[placeholder*='Telefon' i]"
            ),
            resume_pdf_path=resume_pdf_path,
        )
        if resume_pdf_path and not uploaded:
            return ApplyResult(success=False, needs_review=True, error_message="Personio CV upload failed")
        self._fill_german_profile_fields(profile)
        self._fill_cover_letter(
            cover_letter_text,
            [
                "textarea[name*='cover' i]",
                "textarea[id*='cover' i]",
                "textarea[name*='anschreiben' i]",
                "textarea[id*='anschreiben' i]",
                "textarea[placeholder*='Anschreiben' i]",
                "textarea[placeholder*='cover' i]",
                "textarea[aria-label*='cover' i]",
                "textarea[aria-label*='Anschreiben' i]",
            ],
        )

        unknown = self._unknown_required_fields(
            profile,
            skip_tokens=(
                "first",
                "last",
                "email",
                "phone",
                "telefon",
                "vorname",
                "nachname",
                "resume",
                "cover",
                "file",
                "cv",
                "street",
                "strasse",
                "postal",
                "plz",
                "city",
                "ort",
                "salary",
                "gehalt",
                "privacy",
                "consent",
                "datenschutz",
            ),
        )
        if unknown:
            return ApplyResult(
                success=False,
                needs_review=True,
                error_message=f"Unknown Personio fields: {', '.join(unknown[:5])}",
            )
        # Partial support: prefer review even when fill looks complete.
        result = self._maybe_submit(
            "button[type='submit'], input[type='submit'], "
            "button:has-text('Senden'), button:has-text('Submit')"
        )
        result.needs_review = True
        if not result.error_message:
            result.error_message = "Personio partially supported — review before final submit"
        return result
