"""Controlled extraction of recruiting contacts from structured + visible text.

Uses schema.org JobPosting / contactPoint first. Visible HTML text is parsed
conservatively; raw HTML is never persisted — only short evidence quotes.
Optional: extruct / selectolax / trafilatura when installed (clear OSS licenses).
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from bs4 import BeautifulSoup

from core.contacts.classify import find_emails, is_generic_mailbox
from core.contacts.models import (
    ContactCandidate,
    ContactEvidence,
    ContactKind,
    SourceType,
)
from core.models import utc_now_iso
from core.text_normalize import clean_text
from search.jsonld import iter_job_postings

logger = logging.getLogger("karrierekrake.contacts")

# German / English contact role cues near a name.
_ROLE_CUES = (
    r"Recruiter(?:in)?",
    r"Talent\s*Acquisition",
    r"HR[\s\-]?Manager(?:in)?",
    r"Personal(?:referent(?:in)?|wesen)",
    r"Hiring\s*Manager",
    r"Ansprechpartner(?:in)?",
    r"Bewerbungsmanagement",
    r"People\s*(?:Ops|Operations|Team)",
)

_NAME_TOKEN = r"[A-ZÄÖÜ][a-zäöüß\-]+(?:\s+[A-ZÄÖÜ][a-zäöüß\-]+){0,2}"

_CONTACT_BLOCK_RE = re.compile(
    rf"(?:"
    rf"(?:Ihre?\s+)?Ansprechpartner(?:in)?|"
    rf"Kontakt(?:person)?|"
    rf"\bRecruiter(?:in)?\b|"
    rf"Bewerbung(?:en)?\s+(?:bitte\s+)?an|"
    rf"Fragen\s+an"
    rf")"
    rf"\s*[:\-]?\s*"
    rf"(?P<body>[^\n]{{3,160}})",
    re.I,
)

_NAME_EMAIL_RE = re.compile(
    rf"(?P<name>{_NAME_TOKEN})\s*"
    rf"(?:\(|–|-|,)\s*"
    rf"(?P<role>{'|'.join(_ROLE_CUES)})"
    rf"[^@\n]{{0,60}}?"
    rf"(?P<email>[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{{2,}})",
    re.I,
)

_PHONE_RE = re.compile(
    r"(?:\+49|0)\s*[\d\s/\-()]{6,18}\d"
)

_STALE_META_RE = re.compile(
    r"(?:datePublished|dateModified|article:modified_time|og:updated_time)"
    r"""['\"\s:=]+['\"]?(?P<ts>\d{4}-\d{2}-\d{2})""",
    re.I,
)

_SALUTATION_STRIP = re.compile(
    r"^\s*(?:Herr|Frau|Mr\.?|Ms\.?|Mrs\.?|Hr\.?|Fr\.)\s+",
    re.I,
)


def _now() -> str:
    return utc_now_iso()


def _ev(
    field: str,
    quote: str,
    source_type: SourceType | str,
    source_url: str = "",
) -> ContactEvidence:
    st = source_type.value if isinstance(source_type, SourceType) else str(source_type)
    return ContactEvidence(
        field=field,
        quote=quote.strip()[:500],
        source_type=st,
        source_url=source_url or "",
        extracted_at=_now(),
    )


def _strip_salutation(name: str) -> str:
    return _SALUTATION_STRIP.sub("", clean_text(name)).strip()


def _looks_like_person_name(name: str) -> bool:
    n = _strip_salutation(name)
    if not n or len(n) < 3:
        return False
    # Reject obvious non-names
    low = n.lower()
    if low in {"hr", "team", "kontakt", "info", "personal", "recruiting"}:
        return False
    parts = n.split()
    if len(parts) > 4:
        return False
    # Require capitalised tokens (already partially enforced by pattern)
    return bool(re.match(rf"^{_NAME_TOKEN}$", n))


def _candidate_from_parts(
    *,
    name: str = "",
    role: str = "",
    department: str = "",
    email: str = "",
    phone: str = "",
    source_type: SourceType,
    source_url: str,
    quotes: dict[str, str],
    page_timestamp: str = "",
    stale: bool = False,
) -> ContactCandidate | None:
    name = _strip_salutation(name)
    email = clean_text(email).lower()
    role = clean_text(role)
    department = clean_text(department)
    phone = clean_text(phone)

    if email and is_generic_mailbox(email) and not name:
        # Generic mailbox alone — not a person candidate
        evidence = [_ev("email", quotes.get("email") or email, source_type, source_url)]
        return ContactCandidate(
            email=email,
            source_url=source_url,
            source_type=source_type.value,
            evidence=evidence,
            timestamp=_now(),
            contact_kind=ContactKind.GENERIC_MAILBOX.value,
            page_timestamp=page_timestamp,
            stale=stale,
        )

    if email and is_generic_mailbox(email) and name:
        # Never attach a guessed person to info@ — drop the name association
        # unless the name appears in the same evidence quote as the email.
        quote = quotes.get("name") or quotes.get("email") or ""
        if email.lower() not in quote.lower() or name.lower() not in quote.lower():
            name = ""
            role = role if role else ""
            # Fall through as generic if no co-located name
            if not name:
                evidence = [
                    _ev("email", quotes.get("email") or email, source_type, source_url)
                ]
                return ContactCandidate(
                    email=email,
                    role=role,
                    source_url=source_url,
                    source_type=source_type.value,
                    evidence=evidence
                    + (
                        [_ev("role", quotes.get("role") or role, source_type, source_url)]
                        if role
                        else []
                    ),
                    timestamp=_now(),
                    contact_kind=ContactKind.GENERIC_MAILBOX.value,
                    page_timestamp=page_timestamp,
                    stale=stale,
                )

    evidence: list[ContactEvidence] = []
    if name:
        if not _looks_like_person_name(name):
            name = ""
        else:
            evidence.append(
                _ev("name", quotes.get("name") or name, source_type, source_url)
            )
    if role:
        evidence.append(_ev("role", quotes.get("role") or role, source_type, source_url))
    if department:
        evidence.append(
            _ev("department", quotes.get("department") or department, source_type, source_url)
        )
    if email:
        evidence.append(
            _ev("email", quotes.get("email") or email, source_type, source_url)
        )
    if phone:
        evidence.append(
            _ev("phone", quotes.get("phone") or phone, source_type, source_url)
        )

    if not evidence:
        return None

    kind = ContactKind.PERSON.value if name else (
        ContactKind.GENERIC_MAILBOX.value
        if email and is_generic_mailbox(email)
        else ContactKind.UNKNOWN.value
    )
    cand = ContactCandidate(
        name=name,
        role=role,
        department=department,
        email=email,
        phone=phone,
        source_url=source_url,
        source_type=source_type.value,
        evidence=evidence,
        timestamp=_now(),
        contact_kind=kind,
        page_timestamp=page_timestamp,
        stale=stale,
    )
    if cand.validate_evidence():
        return None
    return cand


def parse_jsonld_documents(html: str) -> list[dict[str, Any]]:
    """Extract JSON-LD objects from HTML. Prefer extruct when available."""
    docs: list[dict[str, Any]] = []
    try:
        import extruct  # type: ignore

        data = extruct.extract(
            html or "",
            syntaxes=["json-ld"],
            errors="ignore",
        )
        for item in data.get("json-ld") or []:
            if isinstance(item, dict):
                docs.append(item)
            elif isinstance(item, list):
                docs.extend(x for x in item if isinstance(x, dict))
        if docs:
            return docs
    except Exception:  # noqa: BLE001 — optional dependency / malformed
        pass

    soup = BeautifulSoup(html or "", "lxml")
    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or script.get_text() or ""
        raw = raw.strip()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, list):
            docs.extend(x for x in payload if isinstance(x, dict))
        elif isinstance(payload, dict):
            docs.append(payload)
    return docs


def visible_text_from_html(html: str) -> str:
    """Visible text only — prefer selectolax/trafilatura, fall back to bs4."""
    if not html:
        return ""
    try:
        import trafilatura  # type: ignore

        extracted = trafilatura.extract(html, include_comments=False, include_tables=True)
        if extracted and len(extracted.strip()) > 40:
            return extracted.strip()
    except Exception:  # noqa: BLE001
        pass
    try:
        from selectolax.parser import HTMLParser  # type: ignore

        tree = HTMLParser(html)
        for node in tree.css("script, style, noscript"):
            node.decompose()
        text = tree.body.text(separator="\n") if tree.body else tree.text()
        if text and len(text.strip()) > 20:
            return re.sub(r"\n{3,}", "\n\n", text).strip()
    except Exception:  # noqa: BLE001
        pass
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return soup.get_text("\n", strip=True)


def detect_page_timestamp(html: str, structured: list[dict[str, Any]] | None = None) -> str:
    """Best-effort page/dateModified for stale detection."""
    for doc in structured or []:
        for key in ("dateModified", "datePosted", "uploadDate"):
            val = doc.get(key)
            if isinstance(val, str) and re.match(r"\d{4}-\d{2}-\d{2}", val):
                return val[:10]
        for posting in iter_job_postings(doc):
            for key in ("dateModified", "datePosted"):
                val = posting.get(key)
                if isinstance(val, str) and re.match(r"\d{4}-\d{2}-\d{2}", val):
                    return val[:10]
    m = _STALE_META_RE.search(html or "")
    if m:
        return m.group("ts")
    return ""


def is_stale_timestamp(page_ts: str, *, stale_after_days: int = 90) -> bool:
    if not page_ts or stale_after_days <= 0:
        return False
    try:
        dt = datetime.strptime(page_ts[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return False
    age = datetime.now(timezone.utc) - dt
    return age.days > stale_after_days


def _contact_point_to_candidate(
    cp: dict[str, Any],
    *,
    source_type: SourceType,
    source_url: str,
    page_timestamp: str,
    stale: bool,
) -> ContactCandidate | None:
    if not isinstance(cp, dict):
        return None
    name = str(cp.get("name") or cp.get("contactType") or "").strip()
    # contactType alone is a role, not a name
    role = ""
    if cp.get("contactType") and not cp.get("name"):
        role = str(cp.get("contactType") or "")
        name = ""
    elif cp.get("contactType") and cp.get("name"):
        role = str(cp.get("contactType") or "")
        name = str(cp.get("name") or "")
    email = str(cp.get("email") or "").strip()
    phone = str(cp.get("telephone") or cp.get("phone") or "").strip()
    dept = str(cp.get("department") or "").strip()
    quote_blob = json.dumps(cp, ensure_ascii=False)[:400]
    return _candidate_from_parts(
        name=name,
        role=role,
        department=dept,
        email=email,
        phone=phone,
        source_type=source_type,
        source_url=source_url,
        quotes={
            "name": quote_blob,
            "role": quote_blob,
            "department": quote_blob,
            "email": quote_blob,
            "phone": quote_blob,
        },
        page_timestamp=page_timestamp,
        stale=stale,
    )


def extract_from_jsonld(
    docs: list[dict[str, Any]],
    *,
    source_url: str = "",
    stale_after_days: int = 90,
) -> list[ContactCandidate]:
    """Extract contacts from JobPosting / Organization structured data."""
    page_ts = detect_page_timestamp("", docs)
    stale = is_stale_timestamp(page_ts, stale_after_days=stale_after_days)
    out: list[ContactCandidate] = []
    seen: set[str] = set()

    def _add(c: ContactCandidate | None) -> None:
        if not c:
            return
        key = f"{c.email}|{c.name}|{c.source_type}"
        if key in seen:
            return
        seen.add(key)
        out.append(c)

    for doc in docs:
        postings = iter_job_postings(doc) or (
            [doc] if str(doc.get("@type") or "") in {"Organization", "Corporation"} else []
        )
        # Also walk bare Organization
        nodes = list(postings)
        if doc.get("@type") in ("Organization", "Corporation", "LocalBusiness"):
            nodes.append(doc)
        for g in doc.get("@graph") or []:
            if isinstance(g, dict):
                nodes.append(g)

        for node in nodes:
            if not isinstance(node, dict):
                continue
            # schema.org applicationContact / hiringOrganization.contactPoint
            for key in ("applicationContact", "contactPoint", "contact"):
                raw = node.get(key)
                items = raw if isinstance(raw, list) else [raw] if raw else []
                for item in items:
                    if isinstance(item, dict):
                        _add(
                            _contact_point_to_candidate(
                                item,
                                source_type=SourceType.JOB_POSTING_JSONLD,
                                source_url=source_url,
                                page_timestamp=page_ts,
                                stale=stale,
                            )
                        )
            org = node.get("hiringOrganization")
            if isinstance(org, dict):
                for key in ("contactPoint", "contact", "email"):
                    raw = org.get(key)
                    if key == "email" and isinstance(raw, str) and raw:
                        _add(
                            _candidate_from_parts(
                                email=raw,
                                source_type=SourceType.JOB_POSTING_JSONLD,
                                source_url=source_url,
                                quotes={"email": raw},
                                page_timestamp=page_ts,
                                stale=stale,
                            )
                        )
                    else:
                        items = raw if isinstance(raw, list) else [raw] if raw else []
                        for item in items:
                            if isinstance(item, dict):
                                _add(
                                    _contact_point_to_candidate(
                                        item,
                                        source_type=SourceType.JOB_POSTING_JSONLD,
                                        source_url=source_url,
                                        page_timestamp=page_ts,
                                        stale=stale,
                                    )
                                )
            # Conflicting structured data: collect all; pipeline ranks later
            if node.get("email") and isinstance(node.get("email"), str):
                _add(
                    _candidate_from_parts(
                        email=str(node["email"]),
                        name=str(node.get("name") or ""),
                        source_type=SourceType.JOB_POSTING_JSONLD,
                        source_url=source_url,
                        quotes={
                            "email": str(node["email"]),
                            "name": str(node.get("name") or node["email"]),
                        },
                        page_timestamp=page_ts,
                        stale=stale,
                    )
                )
    return out


def extract_from_visible_text(
    text: str,
    *,
    source_type: SourceType = SourceType.JOB_POSTING_TEXT,
    source_url: str = "",
    page_timestamp: str = "",
    stale: bool = False,
) -> list[ContactCandidate]:
    """Conservative regex extraction from job/company visible text."""
    if not text or len(text.strip()) < 8:
        return []
    out: list[ContactCandidate] = []
    seen: set[str] = set()
    known_emails = set(find_emails(text))

    def _add(c: ContactCandidate | None) -> None:
        if not c:
            return
        if c.email and known_emails and c.email not in known_emails:
            # Drop fragment emails that are not full matches in the source text.
            return
        key = f"{c.email}|{c.name}".lower()
        if key in seen:
            # Merge richer fields into the first hit
            for existing in out:
                if f"{existing.email}|{existing.name}".lower() == key:
                    if c.phone and not existing.phone:
                        existing.phone = c.phone
                        existing.evidence.extend(
                            e for e in c.evidence if e.field == "phone"
                        )
                    if c.role and not existing.role:
                        existing.role = c.role
                    break
            return
        seen.add(key)
        out.append(c)

    for m in _CONTACT_BLOCK_RE.finditer(text):
        body = m.group("body") or ""
        quote = m.group(0)[:500]
        emails = [e for e in find_emails(body) if e in known_emails or not known_emails]
        phone_m = _PHONE_RE.search(body)
        phone = phone_m.group(0).strip() if phone_m else ""
        name = ""
        role = ""
        ne = _NAME_EMAIL_RE.search(body)
        if ne and (ne.group("email") or "").lower() in (set(emails) | known_emails):
            name = ne.group("name") or ""
            role = (ne.group("role") or "").strip()
        else:
            nm = re.match(rf"^\s*(?:Herr|Frau)?\s*({_NAME_TOKEN})", body)
            if nm:
                name = nm.group(1)
            role_m = re.search("|".join(_ROLE_CUES), body, re.I)
            if role_m:
                role = role_m.group(0)
            # "Name — email" without role cue inside a labeled contact block
            if not name:
                loose = re.search(
                    rf"(?P<name>{_NAME_TOKEN})\s*[–\—,]\s*"
                    rf"(?P<email>[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{{2,}})",
                    body,
                )
                if loose and loose.group("email").lower() in known_emails:
                    name = loose.group("name")
        email = emails[0] if emails else ""
        # Prefer email that appears with the name in the quote
        if name and emails:
            for e in emails:
                if e in quote.lower() or e in body.lower():
                    email = e
                    break
        _add(
            _candidate_from_parts(
                name=name,
                role=role
                or ("Ansprechpartner" if "ansprechpartner" in quote.lower() else ""),
                email=email,
                phone=phone,
                source_type=source_type,
                source_url=source_url,
                quotes={
                    "name": quote,
                    "role": quote,
                    "email": quote if email else "",
                    "phone": quote if phone else "",
                },
                page_timestamp=page_timestamp,
                stale=stale,
            )
        )

    # Name + role + email only (requires role cue — avoids splitting emails)
    for m in _NAME_EMAIL_RE.finditer(text):
        email = (m.group("email") or "").lower()
        if email not in known_emails:
            continue
        quote = m.group(0)[:500]
        _add(
            _candidate_from_parts(
                name=m.group("name") or "",
                role=(m.group("role") or "").strip(),
                email=email,
                source_type=source_type,
                source_url=source_url,
                quotes={"name": quote, "role": quote, "email": quote},
                page_timestamp=page_timestamp,
                stale=stale,
            )
        )

    return out


def extract_from_ats_metadata(
    meta: dict[str, Any] | None,
    *,
    source_url: str = "",
) -> list[ContactCandidate]:
    """ATS adapter metadata (hiring manager fields, etc.)."""
    if not meta:
        return []
    name = str(
        meta.get("contact_name")
        or meta.get("recruiter_name")
        or meta.get("hiring_manager")
        or ""
    )
    email = str(
        meta.get("contact_email")
        or meta.get("recruiter_email")
        or meta.get("email")
        or ""
    )
    phone = str(meta.get("contact_phone") or meta.get("phone") or "")
    role = str(meta.get("contact_role") or meta.get("role") or "")
    dept = str(meta.get("department") or "")
    if not any([name, email, phone]):
        return []
    blob = json.dumps(
        {k: meta[k] for k in meta if k in {
            "contact_name", "recruiter_name", "hiring_manager",
            "contact_email", "recruiter_email", "email",
            "contact_phone", "phone", "contact_role", "role", "department",
        }},
        ensure_ascii=False,
    )[:400]
    c = _candidate_from_parts(
        name=name,
        role=role,
        department=dept,
        email=email,
        phone=phone,
        source_type=SourceType.ATS_METADATA,
        source_url=source_url,
        quotes={
            "name": blob,
            "role": blob,
            "department": blob,
            "email": blob,
            "phone": blob,
        },
    )
    return [c] if c else []


def extract_from_signature(
    signature_text: str,
    *,
    source_url: str = "",
    thread_confirmed: bool = False,
) -> list[ContactCandidate]:
    """Recruiter signature from an already correctly associated email thread.

    Without thread_confirmed=True this returns nothing (avoid wrong attribution).
    """
    if not thread_confirmed or not signature_text:
        return []
    emails = find_emails(signature_text)
    if not emails:
        return []
    email = emails[0]
    lines = [ln.strip() for ln in signature_text.splitlines() if ln.strip()]
    name = ""
    role = ""
    for i, ln in enumerate(lines):
        if email in ln.lower():
            if i > 0 and _looks_like_person_name(lines[i - 1]):
                name = _strip_salutation(lines[i - 1])
            break
    if not name:
        for ln in lines:
            if email in ln.lower():
                break
            if _looks_like_person_name(ln):
                name = _strip_salutation(ln)
    # Split "Nora Recruiter" → name Nora, role Recruiter when second token is a cue
    if name:
        parts = name.split()
        if len(parts) >= 2:
            maybe_role = parts[-1]
            if re.fullmatch("|".join(_ROLE_CUES), maybe_role, re.I):
                role = maybe_role
                name = " ".join(parts[:-1])
    if not role:
        role_m = re.search(r"\b(?:" + "|".join(_ROLE_CUES) + r")\b", signature_text, re.I)
        if role_m:
            role = role_m.group(0)
    quote = signature_text.strip()[:500]
    c = _candidate_from_parts(
        name=name,
        role=role or "Recruiter",
        email=email,
        source_type=SourceType.RECRUITER_SIGNATURE,
        source_url=source_url,
        quotes={"name": quote, "role": quote, "email": quote},
    )
    return [c] if c else []


def extract_from_html(
    html: str,
    *,
    source_type: SourceType,
    source_url: str = "",
    stale_after_days: int = 90,
) -> list[ContactCandidate]:
    """Full page: structured data first, then controlled visible text."""
    if not html:
        return []
    # Malformed HTML: BeautifulSoup/lxml still yield something; never raise.
    try:
        docs = parse_jsonld_documents(html)
    except Exception:  # noqa: BLE001
        docs = []
    page_ts = detect_page_timestamp(html, docs)
    stale = is_stale_timestamp(page_ts, stale_after_days=stale_after_days)
    candidates = extract_from_jsonld(
        docs, source_url=source_url, stale_after_days=stale_after_days
    )
    # Override source_type for career/contact pages on JSON-LD hits from those pages
    if source_type in (
        SourceType.COMPANY_CAREER_PAGE,
        SourceType.COMPANY_CONTACT_PAGE,
    ):
        for c in candidates:
            c.source_type = source_type.value
            for e in c.evidence:
                e.source_type = source_type.value
    try:
        text = visible_text_from_html(html)
    except Exception:  # noqa: BLE001
        text = ""
    text_cands = extract_from_visible_text(
        text,
        source_type=source_type
        if source_type
        != SourceType.JOB_POSTING_JSONLD
        else SourceType.JOB_POSTING_TEXT,
        source_url=source_url,
        page_timestamp=page_ts,
        stale=stale,
    )
    # Prefer structured; append text-only uniques
    seen = {f"{c.email}|{c.name}" for c in candidates}
    for c in text_cands:
        key = f"{c.email}|{c.name}"
        if key not in seen:
            seen.add(key)
            candidates.append(c)
    return candidates
