"""Base application automation classes.

Adapted from AutoApply bot/apply/base.py (MIT).
"""

from __future__ import annotations

import logging
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.config import ApplicationProfile
from core.models import Job

logger = logging.getLogger("karrierekrake")

MAX_RETRIES = 2
RETRY_DELAYS = [3, 8]


@dataclass
class ApplyResult:
    success: bool
    error_message: str | None = None
    captcha_detected: bool = False
    manual_required: bool = False
    needs_review: bool = False
    login_required: bool = False
    dry_run_stopped: bool = False
    submitted: bool = False
    attempts: int = 1


class BaseApplier(ABC):
    ELEMENT_TIMEOUT = 5000
    NAV_TIMEOUT = 30000

    def __init__(self, page, *, dry_run: bool = True, submit: bool = False) -> None:
        self.page = page
        self.dry_run = dry_run
        self.submit = submit

    @abstractmethod
    def _do_apply(
        self,
        job: Job,
        resume_pdf_path: Path | None,
        cover_letter_text: str,
        profile: ApplicationProfile,
    ) -> ApplyResult:
        ...

    def apply(
        self,
        job: Job,
        resume_pdf_path: Path | None,
        cover_letter_text: str,
        profile: ApplicationProfile,
    ) -> ApplyResult:
        last_result: ApplyResult | None = None
        platform = self.__class__.__name__.replace("Applier", "")
        for attempt in range(1, MAX_RETRIES + 2):
            try:
                result = self._do_apply(job, resume_pdf_path, cover_letter_text, profile)
                result.attempts = attempt
                if result.success or result.captcha_detected or result.manual_required or result.needs_review:
                    return result
                last_result = result
                if result.error_message and any(
                    kw in result.error_message.lower()
                    for kw in ("form error", "validation", "required field", "unknown question")
                ):
                    return result
            except Exception as exc:
                logger.warning("%s attempt %d failed: %s", platform, attempt, exc)
                last_result = ApplyResult(success=False, error_message=str(exc), attempts=attempt)
            if attempt <= MAX_RETRIES:
                time.sleep(RETRY_DELAYS[min(attempt - 1, len(RETRY_DELAYS) - 1)])
        return last_result or ApplyResult(success=False, error_message="All retry attempts exhausted")

    def _human_type(self, locator, text: str) -> None:
        # Playwright fill dispatches input/change without a per-character delay.
        # Keep a single typing fallback for controls that reject fill.
        try:
            locator.fill(text)
        except Exception:
            locator.type(text)

    def _random_pause(self, min_s: float = 0.5, max_s: float = 2.0) -> None:
        time.sleep(random.uniform(min_s, max_s))

    def _detect_captcha(self) -> bool:
        for selector in (
            "iframe[src*='captcha']",
            "iframe[src*='recaptcha']",
            "iframe[src*='hcaptcha']",
            "iframe[src*='challenges.cloudflare']",
            "iframe[src*='turnstile']",
            "#captcha",
            ".g-recaptcha",
            ".h-captcha",
            "[data-hcaptcha-widget-id]",
            ".cf-turnstile",
            "[name='cf-turnstile-response']",
            "[data-sitekey]",
        ):
            if self.page.query_selector(selector):
                return True
        return False

    def _safe_goto(self, url: str, **kwargs) -> None:
        kwargs.setdefault("wait_until", "domcontentloaded")
        kwargs.setdefault("timeout", self.NAV_TIMEOUT)
        self.page.goto(url, **kwargs)

    def _wait_and_query(self, selector: str, timeout: int | None = None) -> Any:
        timeout = timeout or self.ELEMENT_TIMEOUT
        try:
            self.page.wait_for_selector(selector, timeout=timeout, state="visible")
            return self.page.query_selector(selector)
        except Exception:
            return None

    def _safe_fill(self, selector: str, value: str, clear_first: bool = True) -> bool:
        if not value:
            return False
        el = self.page.query_selector(selector)
        if not el or not el.is_visible():
            return False
        if clear_first:
            try:
                current = el.input_value()
            except Exception:
                current = ""
            if current == value:
                return False
            if current:
                el.fill("")
        try:
            if not el.input_value():
                self._human_type(el, value)
                self._random_pause(0.2, 0.5)
                return True
        except Exception:
            el.fill(value)
            return True
        return False

    def _fill_identity_fields(
        self,
        profile: ApplicationProfile,
        *,
        # Prefer precise last_name tokens (avoid matching blast_email via name*='last').
        # Keep DE vorname/nachname/telefon coverage from the reuse branch.
        first_name: str = (
            "input[name*='first'], input[id*='first'], "
            "input[name*='vorname' i], input[id*='vorname' i], "
            "input[placeholder*='Vorname' i]"
        ),
        last_name: str = (
            "input[name*='last_name' i], input[name*='lastName'], "
            "input[id*='last_name' i], input[id*='lastName'], "
            "input[name*='nachname' i], input[id*='nachname' i], "
            "input[placeholder*='Nachname' i]"
        ),
        email: str = (
            "input[type='email'], input[name*='email' i], input[id*='email' i]"
        ),
        phone: str = (
            "input[type='tel'], input[name*='phone' i], input[id*='phone' i], "
            "input[name*='telefon' i], input[placeholder*='Telefon' i]"
        ),
        full_name: str | None = None,
        linkedin: str | None = None,
        resume_pdf_path: Path | None = None,
        file_selectors: str | list[str] | None = "input[type='file']",
    ) -> bool:
        """Fill common contact fields; return False only if CV upload was requested and failed."""
        if first_name:
            self._safe_fill(first_name, profile.first_name)
        if last_name:
            self._safe_fill(last_name, profile.last_name)
        if full_name:
            self._safe_fill(full_name, profile.full_name)
        if email:
            self._safe_fill(email, profile.email)
        if phone:
            self._safe_fill(phone, profile.phone_full)
        if linkedin and profile.linkedin_url:
            self._safe_fill(linkedin, profile.linkedin_url)
        if resume_pdf_path and file_selectors:
            return self._safe_upload(resume_pdf_path, file_selectors)
        return True

    def _fill_german_profile_fields(self, profile: ApplicationProfile) -> None:
        """Best-effort DE/EN profile extras used by Personio-like forms."""
        pairs: list[tuple[str, str]] = [
            (
                "input[name*='street' i], input[id*='street' i], "
                "input[name*='strasse' i], input[name*='straße' i], "
                "input[placeholder*='Straße' i]",
                profile.street or profile.address,
            ),
            (
                "input[name*='postal' i], input[id*='postal' i], "
                "input[name*='plz' i], input[placeholder*='PLZ' i]",
                profile.postal_code,
            ),
            (
                "input[name*='city' i], input[id*='city' i], "
                "input[name*='ort' i], input[placeholder*='Ort' i]",
                profile.city,
            ),
            (
                "input[name*='salary' i], input[id*='salary' i], "
                "input[name*='gehalt' i], input[placeholder*='Gehalt' i], "
                "input[name*='compensation' i]",
                profile.salary_expectation,
            ),
            (
                "input[name*='notice' i], input[name*='kuendigung' i], "
                "input[name*='kündigung' i], input[placeholder*='Kündigungsfrist' i]",
                profile.notice_period,
            ),
            (
                "input[name*='start' i], input[name*='eintritt' i], "
                "input[placeholder*='Eintritt' i]",
                profile.earliest_start_date,
            ),
            (
                "input[name*='authorization' i], input[name*='work_permit' i], "
                "input[name*='arbeitserlaubnis' i], "
                "textarea[name*='authorization' i]",
                profile.work_authorization,
            ),
        ]
        for selector, value in pairs:
            if value:
                self._safe_fill(selector, value)
        # Consent / privacy only — never marketing/newsletter/opt-in.
        for sel in (
            "input[type='checkbox'][name*='privacy' i]",
            "input[type='checkbox'][name*='datenschutz' i]",
            "input[type='checkbox'][name*='terms' i]",
            "input[type='checkbox'][name*='agb' i]",
            "input[type='checkbox'][id*='privacy' i]",
            "input[type='checkbox'][id*='datenschutz' i]",
        ):
            try:
                for box in self.page.query_selector_all(sel):
                    name = (box.get_attribute("name") or "") + " " + (box.get_attribute("id") or "")
                    low = name.lower()
                    if any(
                        bad in low
                        for bad in (
                            "marketing",
                            "newsletter",
                            "opt_in",
                            "optin",
                            "werbung",
                            "promo",
                        )
                    ):
                        continue
                    if box.is_visible() and not box.is_checked():
                        box.check()
            except Exception:
                continue

    def _safe_upload(self, resume_path: Path, selectors: str | list[str]) -> bool:
        if isinstance(selectors, str):
            selectors = [selectors]
        for selector in selectors:
            file_input = self.page.query_selector(selector)
            if file_input:
                try:
                    file_input.set_input_files(str(resume_path))
                    self._random_pause(1, 2)
                    return True
                except Exception as exc:
                    logger.warning("Upload failed via %s: %s", selector, exc)
        return False

    def _safe_click(self, selector: str, timeout: int | None = None) -> bool:
        el = self._wait_and_query(selector, timeout=timeout or 3000)
        if not el or not el.is_visible():
            return False
        try:
            if hasattr(el, "is_enabled") and not el.is_enabled():
                return False
        except Exception:
            return False
        el.click()
        return True

    def _fill_cover_letter(
        self,
        text: str,
        selectors: str | list[str] | None = None,
    ) -> bool:
        """Fill the first visible cover-letter textarea matching ``selectors``."""
        if not text:
            return False
        if selectors is None:
            # Never fall back to bare ``textarea`` — that can overwrite
            # unknown required questions / notes fields with cover-letter text.
            selectors = [
                "textarea[name*='cover_letter' i]",
                "textarea[id*='cover_letter' i]",
                "textarea[name*='cover' i]",
                "textarea[id*='cover' i]",
                "textarea[name*='anschreiben' i]",
                "textarea[id*='anschreiben' i]",
                "textarea[placeholder*='cover' i]",
                "textarea[placeholder*='Anschreiben' i]",
                "textarea[aria-label*='cover' i]",
                "textarea[aria-label*='Anschreiben' i]",
                "#cover_letter",
            ]
        if isinstance(selectors, str):
            selectors = [selectors]
        for selector in selectors:
            ta = self.page.query_selector(selector)
            if not ta or not ta.is_visible():
                continue
            try:
                if ta.input_value():
                    return False
            except Exception:
                pass
            ta.fill(text)
            return True
        return False

    def _unknown_required_fields(
        self,
        profile: ApplicationProfile,
        *,
        skip_tokens: tuple[str, ...] = (
            "first",
            "last",
            "email",
            "phone",
            "resume",
            "cover",
            "file",
            "cv",
        ),
    ) -> list[str]:
        """Return required empty fields that are not identity/CV and not in profile.answers."""
        unknown: list[str] = []
        for el in self.page.query_selector_all(
            "input[required], textarea[required], select[required], "
            "input[aria-required='true'], textarea[aria-required='true'], "
            "select[aria-required='true']"
        ):
            try:
                name = (el.get_attribute("name") or el.get_attribute("id") or "").lower()
                if not name:
                    # Nameless required controls still block auto-submit.
                    unknown.append("unnamed_required")
                    continue
                if any(k in name for k in skip_tokens):
                    continue
                answered = False
                for key, val in profile.answers.items():
                    if key.lower() in name and val:
                        attr_name = el.get_attribute("name")
                        if attr_name:
                            self._safe_fill(f"[name='{attr_name}']", val)
                        answered = True
                        break
                if answered:
                    continue
                try:
                    if el.input_value():
                        continue
                except Exception:
                    pass
                unknown.append(name)
            except Exception:
                continue
        return unknown

    def _unknown_required_labels(
        self,
        profile: ApplicationProfile,
        *,
        skip_tokens: tuple[str, ...] = ("name", "email", "phone", "resume", "cover"),
    ) -> list[str]:
        """Ashby-style: required labels marked with ``*`` that lack known answers."""
        unknown: list[str] = []
        for label in self.page.query_selector_all("label"):
            try:
                label_text = label.inner_text().strip().lower()
            except Exception:
                continue
            matched = False
            for key, value in profile.answers.items():
                if key.lower().replace("_", " ") in label_text and value:
                    label_for = label.get_attribute("for")
                    if label_for:
                        self._safe_fill(f"#{label_for}", value)
                        matched = True
                        break
            if matched:
                continue
            if "*" not in label_text:
                continue
            if any(x in label_text for x in skip_tokens):
                continue
            unknown.append(label_text[:80])
        return unknown

    def _maybe_submit(self, submit_selector: str) -> ApplyResult:
        """Central hard guard: never click final submit in dry_run / non-submit mode."""
        if self.dry_run or not self.submit:
            logger.info(
                "TEST MODE: skipped final submit "
                "(dry_run=%s, submit=%s, selector=%s)",
                self.dry_run,
                self.submit,
                submit_selector,
            )
            return ApplyResult(
                success=True,
                dry_run_stopped=True,
                submitted=False,
                error_message="Stopped before submit (dry_run / review mode)",
            )
        btn = self._wait_and_query(submit_selector, timeout=5000)
        if not btn:
            return ApplyResult(
                success=False,
                manual_required=True,
                needs_review=True,
                error_message="Submit button not found",
            )
        try:
            enabled = True if not hasattr(btn, "is_enabled") else bool(btn.is_enabled())
        except Exception:
            enabled = False
        if not enabled:
            return ApplyResult(
                success=False,
                manual_required=True,
                needs_review=True,
                error_message="Submit button disabled",
            )
        btn.click()
        self._random_pause(2, 4)
        return ApplyResult(success=True, submitted=True)
