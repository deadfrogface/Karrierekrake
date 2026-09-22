"""Structured German/English CV profile parsing.

Text extraction: ``core.cv_extract``. Section headings/split: ``core.cv_sections``.
This module never invents qualifications that are not present in the text. No paid AI.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from core.config import (
    CertificateEntry,
    EducationEntry,
    ExperienceEntry,
    LanguageEntry,
    QualificationsConfig,
    parse_qualifications,
)
from core.cv_extract import extract_text
from core.cv_sections import (
    is_document_title as _is_document_title,
    is_heading as _is_heading,
    is_heading_value as _is_heading_value,
    normalize_bullet as _normalize_bullet,
    split_named_sections as _split_named_sections,
)

logger = logging.getLogger("karrierekrake")

_MONTH = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
)
_DATE = (
    rf"(?:{_MONTH}\s+\d{{4}}|"
    r"\d{1,2}\.\d{1,2}\.\d{2,4}|"
    r"\d{1,2}[./]\d{4}|"
    r"\d{4})"
)
_END = rf"(?:{_DATE}|heute|aktuell|present|current|ohne\s+abschluss|abgebrochen|abbruch)"
_PERIOD = re.compile(
    rf"(?P<start>(?:Seit|seit)\s+{_DATE}|{_DATE})\s*[–\-—]\s*(?P<end>{_END})",
    re.IGNORECASE,
)
_SINCE = re.compile(rf"^(?:Seit|seit)\s+(?P<start>{_DATE})\s*$", re.IGNORECASE)
_SINCE_INLINE = re.compile(
    rf"^(?:Seit|seit)\s+(?P<start>{_DATE})\s*[–\-—]?\s+(?P<title>.+)$",
    re.IGNORECASE,
)
_ABSCHLUSS = re.compile(
    rf"Abschluss\s*:\s*(?P<date>{_DATE})",
    re.IGNORECASE,
)
_LEVEL = re.compile(
    r"\b([ABC][12]|Muttersprache|Muttersprachler(?:in)?|native(?:\s+speaker)?)\b",
    re.IGNORECASE,
)

# EU driving licence class tokens (normalized uppercase).
# Order matters for alternation: longer tokens first so BE matches before B, C1E before C1, etc.
_LICENSE_CLASS = re.compile(
    r"\b(AM|A1|A2|A|B1|BE|B|C1E|C1|CE|C|D1E|D1|DE|D|L|T)\b",
    re.IGNORECASE,
)

_DEGREE_HINT = re.compile(
    r"(?i)\b("
    r"bachelor|master|b\.?a\.?|b\.?sc\.?|bcom|m\.?a\.?|m\.?sc\.?|mba|"
    r"ausbildung|kaufmann|kauffrau|abitur|fachabitur|realschule|"
    r"hauptschule|mittlere\s+reife|fachhochschulreife|studium|"
    r"promotion|diplom|ihk|university|hochschule|college|a\s*levels?"
    r")\b"
)


# Overlap with CEFR language levels — only accept with explicit licence context.
_AMBIGUOUS_LICENCE_CEFR = frozenset({"A1", "A2", "B1", "C1"})
_LICENCE_CONTEXT = re.compile(
    r"(?i)(führerschein|fuehrerschein|fahrerlaubnis|fahrerlaubnis|"
    r"klasse|klassen|category|categories|driving\s*licen)"
)


def normalize_driving_license(raw: str | list[str]) -> list[str]:
    """Normalize German/EU licence text to class codes like ``B``, ``BE``, ``C1``.

    Bare CEFR-overlapping tokens (A1/A2/B1/C1) are ignored unless the chunk
    contains licence context (``Klasse``, ``Führerschein``, …) or an unambiguous
    licence class (``B``, ``BE``, ``C``, …) on the same chunk.
    """
    chunks = raw if isinstance(raw, list) else [raw]
    found: list[str] = []
    for chunk in chunks:
        text = str(chunk or "").strip()
        if not text or _is_heading_value(text):
            continue
        codes = [m.group(1).upper() for m in _LICENSE_CLASS.finditer(text)]
        if not codes:
            continue
        has_context = bool(_LICENCE_CONTEXT.search(text))
        has_unambiguous = any(c not in _AMBIGUOUS_LICENCE_CEFR for c in codes)
        for code in codes:
            if code in _AMBIGUOUS_LICENCE_CEFR and not (has_context or has_unambiguous):
                continue
            if code not in found:
                found.append(code)
    return found


# User-facing label when a field is simply absent from the CV — not a parser crash.
MISSING_IN_DOCUMENT = "Im Dokument nicht gefunden"


def field_confidence(value: Any) -> str:
    """Return ``high`` / ``low`` / ``Im Dokument nicht gefunden`` for empty values."""
    if value is None:
        return MISSING_IN_DOCUMENT
    if isinstance(value, (list, dict, str)) and not value:
        return MISSING_IN_DOCUMENT
    if isinstance(value, list) and all(not str(v).strip() for v in value):
        return MISSING_IN_DOCUMENT
    return "high"


def _split_language_chunks(line: str) -> list[str]:
    """Split one line that may contain several language/level pairs."""
    # "English - Native | German - B2 | French - A2"
    # "Deutsch: Muttersprache; Englisch: B2"
    # Do NOT split "Deutsch | C2" (single pair).
    cefr_hits = len(re.findall(r"\b(?:[ABC][12]|Muttersprache|Muttersprachler(?:in)?|native)\b", line, re.I))
    seps = len(re.findall(r"[|;]", line))
    if seps >= 1 and cefr_hits >= 2:
        return [p.strip() for p in re.split(r"\s*[|;]\s*", line) if p.strip()]
    if re.search(r",\s*[A-Za-zÄÖÜäöüß].*(?:[ABC][12]|Muttersprache|native)", line, re.I):
        # "Deutsch C2, Englisch B2, Tschechisch A2"
        if cefr_hits >= 2:
            return [p.strip() for p in re.split(r"\s*,\s*", line) if p.strip()]
    return [line]


def _normalize_lang_level(level: str, meta: str = "", full_line: str = "") -> str:
    level = (level or "").strip()
    meta = (meta or "").strip()
    blob = f"{meta} {level} {full_line}"
    # Prefer explicit CEFR anywhere on the line over Muttersprache/native wording.
    cefr = re.findall(r"\b([ABC][12])\b", blob, re.I)
    if cefr:
        return cefr[-1].upper()
    low = blob.lower()
    if "muttersprach" in low or re.search(r"\bnative(?:\s+speaker)?\b", low):
        return "native"
    if re.fullmatch(r"[ABC][12]", level, re.I):
        return level.upper()
    return level


# Real spoken/written languages only (DE + EN names). Never treat software,
# soft skills, or Weiterbildungen as Sprachen.
_KNOWN_LANGUAGES = frozenset(
    {
        "deutsch",
        "englisch",
        "französisch",
        "franzoesisch",
        "spanisch",
        "italienisch",
        "portugiesisch",
        "niederländisch",
        "niederlaendisch",
        "holländisch",
        "hollaendisch",
        "russisch",
        "polnisch",
        "tschechisch",
        "slowakisch",
        "ungarisch",
        "rumänisch",
        "rumaenisch",
        "bulgarisch",
        "griechisch",
        "türkisch",
        "tuerkisch",
        "arabisch",
        "hebräisch",
        "hebraeisch",
        "chinesisch",
        "japanisch",
        "koreanisch",
        "schwedisch",
        "norwegisch",
        "dänisch",
        "daenisch",
        "finnisch",
        "isländisch",
        "islaendisch",
        "kroatisch",
        "serbisch",
        "bosnisch",
        "slowenisch",
        "ukrainisch",
        "weißrussisch",
        "weissrussisch",
        "litauisch",
        "lettisch",
        "estnisch",
        "albanisch",
        "vietnamesisch",
        "thailändisch",
        "thailaendisch",
        "hindi",
        "persisch",
        "farsi",
        "kurdisch",
        "latein",
        "german",
        "english",
        "french",
        "spanish",
        "italian",
        "portuguese",
        "dutch",
        "russian",
        "polish",
        "czech",
        "slovak",
        "hungarian",
        "romanian",
        "bulgarian",
        "greek",
        "turkish",
        "arabic",
        "hebrew",
        "chinese",
        "mandarin",
        "cantonese",
        "japanese",
        "korean",
        "swedish",
        "norwegian",
        "danish",
        "finnish",
        "icelandic",
        "croatian",
        "serbian",
        "bosnian",
        "slovenian",
        "ukrainian",
        "belarusian",
        "lithuanian",
        "latvian",
        "estonian",
        "albanian",
        "vietnamese",
        "thai",
        "persian",
        "latin",
        "sign language",
        "gebärdensprache",
        "gebaerdensprache",
        "dgs",
        # Additional real languages seen in DE CVs / minority languages
        "romanes",
        "romani",
        "romanesisch",
        "sinti",
        "romanes-sintitikes",
    }
)


def is_known_language_name(name: str) -> bool:
    """True only for real language names — not skills, tools, or certificates."""
    raw = (name or "").strip()
    if not raw:
        return False
    # Strip trailing CEFR / native markers for the name check.
    raw = re.sub(
        r"\s*(?:[–\-—|:]\s*)?(?:[ABC][12]|Muttersprache|Muttersprachler(?:in)?|"
        r"native(?:\s+speaker)?)\s*$",
        "",
        raw,
        flags=re.I,
    ).strip(" -–—|():")
    low = raw.lower()
    if low in _KNOWN_LANGUAGES:
        return True
    # Multi-word: "American Sign Language", "British English"
    tokens = re.split(r"[\s/]+", low)
    if any(tok in _KNOWN_LANGUAGES for tok in tokens):
        return True
    return False


def classify_non_language_token(value: str) -> str:
    """Route a non-language token to software | skill | certificate | uncertain."""
    text = (value or "").strip()
    if not text:
        return "uncertain"
    if _looks_like_software(text):
        return "software"
    low = text.lower()
    # Continuing education / compliance / methodology → certificates
    # (checked before soft-skill compounds so "Lean Management" is Weiterbildung).
    if any(
        hint in low
        for hint in (
            "lean",
            "six sigma",
            "datenschutz",
            "dsgvo",
            "gdpr",
            "zertifikat",
            "certificate",
            "weiterbildung",
            "schulung",
            "seminar",
            "ihk",
            "iso ",
            "first aid",
            "ersthelfer",
            "staplerschein",
            "beschwerdemanagement",
        )
    ):
        return "certificate"
    if _looks_like_soft_skill(text):
        return "skill"
    # Single product-ish tokens without language markers → software guess.
    if _known_software_token_match(low) or re.search(r"\b(bi|erp|crm|sap|datev)\b", low):
        return "software"
    if len(text) >= 4:
        return "certificate"
    return "uncertain"


def _parse_one_language(chunk: str) -> LanguageEntry | None:
    line = chunk.strip().strip("•-–—*· ")
    if not line or _is_heading_value(line):
        return None
    # Bare CEFR token without a language name — never invent "C"/"B"/"A".
    if re.fullmatch(r"[ABC][12]", line, re.I):
        return None

    m = re.match(
        r"^(?P<lang>[A-Za-zÄÖÜäöüß][A-Za-zÄÖÜäöüß\-/']*)\s*"
        r"(?:[–\-—|:]\s*)?(?P<body>.+)?$",
        line,
        re.I,
    )
    if m:
        lang = m.group("lang").strip(" :")
        body = (m.group("body") or "").strip()
        # "C1" splits as lang=C body=1 — reject single-letter fake languages.
        if re.fullmatch(r"[ABC]", lang, re.I) and re.fullmatch(r"[12]", body or ""):
            return None
        # Multi-word non-languages ("Lean Management", "Power BI") must not
        # collapse to the first token ("Lean", "Power").
        if body and not re.fullmatch(
            r"(?:[ABC][12]|Muttersprache|Muttersprachler(?:in)?|native(?:\s+speaker)?|"
            r"fließend|fliesend|gut|grundkenntnisse|verhandlungssicher).*$",
            body,
            re.I,
        ):
            # Likely "Name Level" only when body is a level phrase; otherwise
            # treat the whole line as a candidate below.
            if not is_known_language_name(lang):
                return None
        if lang and not _is_heading_value(lang):
            if not is_known_language_name(lang):
                return None
            level = _normalize_lang_level(body, full_line=line)
            if level or body:
                return LanguageEntry(language=lang, level=level)
            # Bare language name on its own line (level may follow/precede).
            if re.fullmatch(r"[A-Za-zÄÖÜäöüß][A-Za-zÄÖÜäöüß\-/']{1,}", lang):
                return LanguageEntry(language=lang, level="")
    level_m = _LEVEL.search(line)
    if level_m:
        lang = line[: level_m.start()].strip(" -–—|():")
        if lang and not _is_heading_value(lang) and is_known_language_name(lang):
            return LanguageEntry(
                language=lang,
                level=_normalize_lang_level(level_m.group(1), full_line=line),
            )
    # Whole-line known language without separators.
    if is_known_language_name(line) and not _LEVEL.search(line):
        # Prefer canonical first token capitalization from the line itself.
        return LanguageEntry(language=line.strip(), level="")
    return None


def _parse_languages(body: str) -> list[LanguageEntry]:
    results: list[LanguageEntry] = []
    pending_level: str | None = None
    for raw in body.splitlines():
        line = _normalize_bullet(raw)
        if not line:
            continue
        # Orphan CEFR token on its own line — attach to the next language name.
        if re.fullmatch(r"[ABC][12]", line, re.I):
            pending_level = line.upper()
            continue
        for chunk in _split_language_chunks(line):
            amp = re.match(
                r"^(?P<langs>.+?)\s*[–\-—|:]\s*(?P<level>[ABC][12]|Muttersprache|native(?:\s+speaker)?)\s*$",
                chunk,
                re.I,
            )
            if amp and ("&" in amp.group("langs") or " und " in amp.group("langs").lower()):
                level = _normalize_lang_level(amp.group("level"), full_line=chunk)
                parts = re.split(r"\s*(?:&| und )\s*", amp.group("langs"), flags=re.I)
                for part in parts:
                    name = re.sub(r"\(.*?\)", "", part).strip(" -–—|:")
                    if name and not _is_heading_value(name):
                        results.append(LanguageEntry(language=name, level=level))
                pending_level = None
                continue
            entry = _parse_one_language(chunk)
            if entry:
                if pending_level and not (entry.level or "").strip():
                    entry = LanguageEntry(language=entry.language, level=pending_level)
                    pending_level = None
                elif entry.level:
                    pending_level = None
                results.append(entry)
    seen: set[str] = set()
    unique: list[LanguageEntry] = []
    for item in results:
        key = item.normalized_key()
        if key and key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def _parse_software(body: str) -> list[str]:
    items: list[str] = []
    for raw in body.splitlines():
        line = _normalize_bullet(raw)
        if not line or _is_heading_value(line):
            continue
        # Strip section-style labels pasted into a body line.
        line = re.sub(r"(?i)^(software|edv|it|tools)\s*:\s*", "", line).strip()
        if not line:
            continue
        # Skip licence / mobility fragments accidentally mixed in.
        if re.match(r"(?i)^(führerschein|fuehrerschein|driving\s+licen)", line):
            continue
        m = re.match(r"^(?P<head>MS Office)\s*\((?P<inner>.+)\)$", line, re.I)
        if m:
            items.append(m.group("head"))
            inner = m.group("inner")
            chunks = re.split(r",|/", inner)
            for chunk in chunks:
                chunk = chunk.strip()
                if not chunk:
                    continue
                if "excel" in chunk.lower():
                    items.append(
                        "Excel – fortgeschritten"
                        if "fortgeschritten" in chunk.lower() or "fortgeschritten" in inner.lower()
                        else "Excel"
                    )
                elif "word" in chunk.lower():
                    items.append("Word")
                else:
                    items.append(chunk)
            continue
        # Split on comma/pipe only — keep versioned product names like SAP S/4HANA.
        if re.search(r"[,|]", line) and not re.search(r"\(.+[,|].+\)", line):
            for part in re.split(r"[,|]", line):
                part = part.strip()
                if part and not _is_heading_value(part):
                    items.append(part)
            continue
        paren = re.match(r"^(?P<desc>.+?)\s*\((?P<name>[^)]+)\)\s*$", line)
        if paren and len(paren.group("name")) < 40:
            # Keep a single canonical entry (name / description). Do NOT also
            # append the bare name — that creates ZA Office duplicates.
            items.append(f"{paren.group('name').strip()} / {paren.group('desc').strip()}")
            continue
        items.append(line)
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in items:
        key = item.lower()
        if key in seen:
            continue
        if item.lower() == "excel" and any(
            "excel" in c.lower() and "fortgeschritten" in c.lower() for c in items
        ):
            continue
        seen.add(key)
        cleaned.append(item)
    # Drop bare names that are already covered by a richer "Name / Desc" entry.
    richer_prefixes = set()
    for item in cleaned:
        if " / " in item:
            richer_prefixes.add(item.split(" / ", 1)[0].strip().lower())
    cleaned = [
        item
        for item in cleaned
        if (" / " in item) or (item.lower() not in richer_prefixes)
    ]
    return cleaned


def _parse_certificates(body: str) -> list[CertificateEntry]:
    result: list[CertificateEntry] = []
    for raw in body.splitlines():
        line = _normalize_bullet(raw)
        if not line or _is_heading_value(line):
            continue
        # Strip trailing years: "IHK Beschwerdemanagement, 2024"
        line = re.sub(r",?\s*\b(?:19|20)\d{2}\b\s*$", "", line).strip(" ,;")
        parts = re.split(r"\s*;\s*", line) if ";" in line else [line]
        for part in parts:
            part = part.strip()
            if part and not _is_heading_value(part):
                result.append(CertificateEntry(name=part))
    return result


def _parse_driving(body: str) -> list[str]:
    lines = [_normalize_bullet(raw) for raw in body.splitlines() if _normalize_bullet(raw)]
    normalized = normalize_driving_license(lines)
    if normalized:
        return normalized
    result: list[str] = []
    for line in lines:
        if _is_heading_value(line):
            continue
        low = line.lower()
        if "führerschein" in low or "fuehrerschein" in low or "fahrerlaubnis" in low:
            continue
        if "driving" in low and "licen" in low:
            continue
        result.append(line)
    return list(dict.fromkeys(result))


def _inline_licence_mentions(text: str) -> list[str]:
    """Only extract licences from explicit licence phrases — never bare CEFR tokens."""
    found: list[str] = []
    patterns = (
        r"(?:Führerschein|Fuehrerschein|Fahrerlaubnis|Driving\s+Licen[cs]e)\s*[:\-]\s*([^\n|;]+)",
        r"Klassen?\s+([A-Z0-9]{1,3}(?:\s*(?:und|,|/|&)\s*[A-Z0-9]{1,3})*)",
        r"Category\s+([A-Z0-9]{1,3})",
        r"Klasse\s+([A-Z0-9]{1,3})",
    )
    for pat in patterns:
        for m in re.finditer(pat, text, re.I):
            found.extend(normalize_driving_license(m.group(1)))
    return list(dict.fromkeys(found))


_QUAL_START = re.compile(
    r"^(Berufsausbildung|Ausbildung\s+zum|Ausbildung\s+zur|"
    r"Kaufmann|Kauffrau|Mittlere Reife|Fachhochschulreife|Abitur|Bachelor|Master|"
    r"Studium|Fachabitur|Realschulabschluss|Hauptschulabschluss|Promotion|"
    r"B\.?\s*A\.?|B\.?\s*Sc\.?|BCom|M\.?\s*A\.?|M\.?\s*Sc\.?|MBA|A\s*Levels?)",
    re.IGNORECASE,
)


def _looks_like_certificate_line(line: str) -> bool:
    """Single-year training/cert line without a degree-range."""
    if _PERIOD.search(line):
        return False
    # Year-dash open ranges that are education rows (pipe-separated) are not certs.
    if re.match(r"^(?:19|20)\d{2}\s*[–\-—]\s*.+\|", line):
        return False
    if _DEGREE_HINT.search(line) and re.search(r"\d{4}\s*[–\-—]\s*\d{4}", line):
        return False
    return bool(re.match(r"^(?:19|20)\d{2}\s+\S+", line))


def _parse_education(body: str) -> tuple[list[EducationEntry], list[CertificateEntry]]:
    lines = [ln.rstrip() for ln in body.splitlines()]
    entries: list[EducationEntry] = []
    leftover_certs: list[CertificateEntry] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line or line.startswith(("•", "-", "–")):
            i += 1
            continue
        if line.lower().startswith("abschluss"):
            i += 1
            continue
        if _is_heading(line):
            i += 1
            continue

        # Date-first layouts: "2013 - 2016 BA Business ..., University"
        pm = _PERIOD.search(line)
        if pm and (pm.start() < 3 or line.lower().startswith("seit")):
            rest = line[pm.end() :].strip(" |–—-")
            start = pm.group("start").replace("Seit ", "").replace("seit ", "").strip()
            end = pm.group("end").strip()
            qualification = rest
            institution = ""
            location = ""
            j = i + 1
            # Continuation lines for institution
            while j < len(lines):
                nxt = lines[j].strip()
                if not nxt:
                    j += 1
                    continue
                if _PERIOD.search(nxt) or _QUAL_START.match(nxt) or _is_heading(nxt) or _looks_like_certificate_line(nxt):
                    break
                if not qualification:
                    qualification = nxt
                elif not institution:
                    institution = nxt
                else:
                    institution = f"{institution} {nxt}".strip()
                j += 1
            if qualification and "|" in qualification:
                left, right = [p.strip() for p in qualification.split("|", 1)]
                qualification, institution = left, right or institution
            if qualification and "," in qualification and not institution:
                # "BA Business Management, University of the West of England"
                left, right = qualification.split(",", 1)
                if _DEGREE_HINT.search(left) or len(left.split()) <= 8:
                    qualification, institution = left.strip(), right.strip()
            if qualification:
                # Pipe leftovers: "Kaufmann ... (IHK) | Nordwest ... | Note 2,1"
                chunks = [c.strip() for c in qualification.split("|") if c.strip()]
                if len(chunks) >= 2 and not institution:
                    qualification = chunks[0]
                    institution = " / ".join(chunks[1:])
                    note_m = re.search(r"Note\s+[\d,]+", institution, re.I)
                    if note_m:
                        institution = institution[: note_m.start()].strip(" |/")
                entries.append(
                    EducationEntry(
                        qualification=qualification,
                        institution=institution,
                        location=location,
                        start_date=start,
                        end_date=end,
                        completion_date=end if re.search(r"\d", end) else "",
                    )
                )
            i = max(j, i + 1)
            continue

        # Single-year certificate-like lines inside education & training
        if _looks_like_certificate_line(line):
            name = re.sub(r"^(?:19|20)\d{2}\s+", "", line).strip()
            if name:
                leftover_certs.append(CertificateEntry(name=name))
            i += 1
            continue

        if not _QUAL_START.match(line):
            i += 1
            continue
        qualification = line
        completion = ""
        institution_parts: list[str] = []
        locations: list[str] = []
        j = i + 1
        while j < len(lines):
            nxt = lines[j].strip()
            if not nxt:
                j += 1
                continue
            if _is_heading(nxt) or _QUAL_START.match(nxt) or _PERIOD.search(nxt):
                break
            am = _ABSCHLUSS.search(nxt)
            if am:
                completion = am.group("date")
                j += 1
                continue
            if nxt.startswith(("•", "-", "–")):
                j += 1
                continue
            if "," in nxt:
                left, right = nxt.rsplit(",", 1)
                institution_parts.append(left.strip())
                if right.strip():
                    locations.append(right.strip())
            else:
                institution_parts.append(nxt)
            j += 1
        entries.append(
            EducationEntry(
                qualification=qualification,
                institution=" / ".join(institution_parts) if institution_parts else "",
                location=", ".join(dict.fromkeys(locations)),
                completion_date=completion,
                end_date=completion,
            )
        )
        i = max(j, i + 1)
    return [e for e in entries if e.qualification], leftover_certs


def _parse_experience(body: str) -> list[ExperienceEntry]:
    lines = [ln.rstrip() for ln in body.splitlines()]
    entries: list[ExperienceEntry] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        if _is_heading(line):
            i += 1
            continue

        start = end = ""
        title = ""
        company = ""
        location = ""

        sm_inline = _SINCE_INLINE.match(line)
        pm = _PERIOD.search(line)
        sm = _SINCE.match(line)

        if sm_inline and not pm:
            start = sm_inline.group("start")
            end = "aktuell"
            title = sm_inline.group("title").strip(" |–—-")
            i += 1
        elif pm and pm.start() <= 2:
            start = pm.group("start").replace("Seit ", "").replace("seit ", "").strip()
            end = pm.group("end").strip()
            rest = line[pm.end() :].strip(" |–—-")
            i += 1
            if rest:
                # "date | title | company" or "date - title"
                parts = [p.strip() for p in re.split(r"\s*\|\s*", rest) if p.strip()]
                if len(parts) >= 2:
                    title = parts[0]
                    company = parts[1]
                    if len(parts) >= 3:
                        location = parts[2]
                else:
                    title = rest
        elif sm:
            start = sm.group("start")
            end = "aktuell"
            i += 1
        else:
            if line.startswith(("•", "-", "–", "*")):
                i += 1
                continue
            # Title-/company-first layouts: peek ahead for a date line.
            look = None
            look_idx = None
            for j in range(i + 1, min(i + 4, len(lines))):
                cand = lines[j].strip()
                if not cand:
                    continue
                if (
                    _PERIOD.search(cand)
                    or _SINCE.match(cand)
                    or _SINCE_INLINE.match(cand)
                ):
                    look = cand
                    look_idx = j
                    break
                if _is_heading(cand) or cand.startswith(("•", "-", "–", "*")):
                    break
            if look is None or look_idx is None:
                i += 1
                continue
            title = line
            # Optional company line between title and date
            company_candidate = ""
            for j in range(i + 1, look_idx):
                mid = lines[j].strip()
                if mid and not mid.startswith(("•", "-", "–", "*")):
                    company_candidate = mid
                    break
            if company_candidate:
                company = company_candidate
            sm_inline = _SINCE_INLINE.match(look)
            pm = _PERIOD.search(look)
            sm = _SINCE.match(look)
            if sm_inline and not pm:
                start = sm_inline.group("start")
                end = "aktuell"
                if sm_inline.group("title").strip():
                    # rare: "Seit DATE title" after company
                    pass
            elif pm:
                start = pm.group("start").replace("Seit ", "").replace("seit ", "").strip()
                end = pm.group("end").strip()
            elif sm:
                start = sm.group("start")
                end = "aktuell"
            i = look_idx + 1

        def _next_nonempty(idx: int) -> tuple[int, str]:
            while idx < len(lines) and not lines[idx].strip():
                idx += 1
            if idx >= len(lines):
                return idx, ""
            return idx, lines[idx].strip()

        if not title:
            i, title = _next_nonempty(i)
            if title and not (_PERIOD.search(title) or _SINCE.match(title) or _is_heading(title)):
                i += 1
            else:
                title = ""

        # Title may still contain "title | company"
        if title and "|" in title and not company:
            parts = [p.strip() for p in title.split("|")]
            title = parts[0]
            if len(parts) > 1:
                company = parts[1]
            if len(parts) > 2:
                location = parts[2]

        if not company:
            i, company_line = _next_nonempty(i)
            if company_line and not (
                _PERIOD.search(company_line)
                or _SINCE.match(company_line)
                or _is_heading(company_line)
                or company_line.startswith(("•", "-", "–", "*"))
            ):
                company = company_line
                i += 1
                if "," in company_line:
                    company, location = [p.strip() for p in company_line.rsplit(",", 1)]

        responsibilities: list[str] = []
        while i < len(lines):
            nxt = lines[i].strip()
            if not nxt:
                i += 1
                if i < len(lines) and (
                    _PERIOD.search(lines[i].strip()) or _SINCE.match(lines[i].strip()) or _SINCE_INLINE.match(lines[i].strip())
                ):
                    break
                continue
            if _PERIOD.search(nxt) or _SINCE.match(nxt) or _SINCE_INLINE.match(nxt) or _is_heading(nxt):
                break
            # Title-first next job (title [/ company] / date). Do not preempt when
            # the next date line already embeds a title ("MM/YYYY - … | Role") —
            # then ``nxt`` is still a prose responsibility of the current job.
            if not nxt.startswith(("•", "-", "–", "*")):
                date_line: str | None = None
                intervening = 0
                for j in range(i + 1, min(i + 4, len(lines))):
                    cand = lines[j].strip()
                    if not cand:
                        continue
                    if _PERIOD.search(cand) or _SINCE.match(cand) or _SINCE_INLINE.match(cand):
                        date_line = cand
                        break
                    if cand.startswith(("•", "-", "–", "*")) or _is_heading(cand):
                        break
                    intervening += 1
                if date_line is not None:
                    embeds_title = "|" in date_line or bool(
                        _SINCE_INLINE.match(date_line) and not _PERIOD.search(date_line)
                    )
                    if not (embeds_title and intervening == 0):
                        break
            cleaned = _normalize_bullet(nxt)
            if cleaned:
                responsibilities.append(cleaned)
            i += 1

        if title or company:
            entries.append(
                ExperienceEntry(
                    title=title,
                    company=company,
                    location=location,
                    start_date=start,
                    end_date=end,
                    responsibilities=responsibilities,
                )
            )
    return entries


_LICENCE_LINE = re.compile(
    r"(?i)^(führerschein|fuehrerschein|fahrerlaubnis|driving\s+licen)"
)

_EDU_LINE_HINT = re.compile(
    r"(?i)\b("
    r"ausbildung|studium|bachelor|master|diplom|magister|abitur|matura|"
    r"schule|schulisch|university|hochschule|fachhochschule|berufsschule|"
    r"handelsschule|realschule|gymnasium|volksschule|oberschule|"
    r"student|studierende|lehrgang\s+zum|lehre\b"
    r")\b"
)


def _split_education_and_experience_body(body: str) -> tuple[str, str, str]:
    """Split a compound Ausbildung+Berufserfahrung section into edu / work / other."""
    edu_lines: list[str] = []
    exp_lines: list[str] = []
    other_lines: list[str] = []
    for raw in body.splitlines():
        stripped = raw.strip()
        if not stripped:
            continue
        if re.match(r"(?i)^(software|edv|it|tools)\s*:", stripped):
            other_lines.append(raw)
            continue
        if _EDU_LINE_HINT.search(stripped):
            edu_lines.append(raw)
        else:
            exp_lines.append(raw)
    return "\n".join(edu_lines), "\n".join(exp_lines), "\n".join(other_lines)


def _parse_skills(body: str) -> list[str]:
    skills: list[str] = []
    # Employment / education lines that leaked into a Kenntnisse body.
    _EMP_LEAK = re.compile(
        r"(?i)^(?:"
        r"\d{1,2}/\d{4}\s*[-–]"  # 01/2018 - …
        r"|\d{4}\s*[-–]\s*(?:\d{4}|heute|ohne)"  # 2011 - 2014
        r"|.+\|\s*.+\|\s*.+"  # date|role|company style
        r")"
    )
    _NOISE_TOKEN = re.compile(
        r"(?i)^(?:"
        r"\d{1,2}"  # bare month
        r"|\d{4}"  # bare year
        r"|in|heute|praxis|bildungsweg|stationen|werdegang"
        r")$"
    )
    for raw in body.splitlines():
        line = _normalize_bullet(raw)
        if not line or _is_heading_value(line) or _is_heading(line):
            continue
        # Prefixed multi-category lines under Kenntnisse are handled elsewhere.
        if re.match(
            r"(?i)^(software|edv|it|tools|fachkenntnisse|hard\s*skills|soft\s*skills|"
            r"zertifikate|certificates|führerschein|fuehrerschein|driving\s+licen|"
            r"berufswunsch|ziel|target\s*role|languages?|sprachen)\s*:",
            line,
        ):
            continue
        # PDF extraction sometimes replaces middle-dots with control chars.
        line = re.sub(r"[\x00-\x1f\x7f•·∙⋅]+", "|", line)
        # Skip long prose / project descriptions
        if len(line) > 120 and not re.search(r"[,;|/]", line):
            continue
        # Licence lines belong in driving_license, not skills.
        if _LICENCE_LINE.match(line):
            continue
        # Reject employment/education leak lines entirely.
        if _EMP_LEAK.match(line):
            continue
        if re.search(r"(?i)\b(gmbh| ug| ag| kg|e\.?\s*v\.?|mbh)\b", line) and re.search(
            r"\d{4}", line
        ):
            continue
        # CEFR / native language lines under bare "Kenntnisse" belong in languages.
        if _LEVEL.search(line) and _parse_one_language(line) is not None:
            continue
        # "Deutsch: Muttersprache" style without relying solely on _LEVEL.
        if _parse_one_language(line) is not None:
            continue
        # Prefer semicolon/comma splits; keep "/" inside product names (S/4HANA)
        # but still split role forms like "Praktikant/in" only when not a tool line.
        if re.search(r"[,;|]", line):
            parts = re.split(r"\s*[,;|]\s*", line)
        elif re.search(r"(?i)\b(praktikant|aushilfe|mitarbeiter)/in\b", line):
            parts = re.split(r"/", line)
        else:
            parts = [line]
        for part in parts:
            part = part.strip(" .")
            if not part or _is_heading_value(part) or len(part) >= 80:
                continue
            if _NOISE_TOKEN.match(part):
                continue
            if _LICENCE_LINE.match(part):
                continue
            if _LEVEL.search(part) and _parse_one_language(part) is not None:
                continue
            if _parse_one_language(part) is not None:
                continue
            # Company-like leftovers
            if re.search(r"(?i)\b(gmbh| ug\b| ag\b| kg\b|e\.?\s*v\.?)\b", part):
                continue
            skills.append(part)
    return list(dict.fromkeys(skills))


def _split_kenntnisse_list_items(payload: str) -> list[str]:
    """Split labeled Kenntnisse payloads without breaking product slashes (S/4HANA)."""
    parts: list[str] = []
    for part in re.split(r"\s*[,;|]\s*", payload or ""):
        part = part.strip(" .")
        if part:
            parts.append(part)
    return parts


def _route_labeled_kenntnisse_lines(body: str) -> dict[str, list]:
    """Split compact 'Kenntnisse' blocks with labeled lines into categories.

    General pattern (not fixture-specific):
      Software: DATEV, Jira
      Fachkenntnisse: …
      Zertifikate: …
      Führerschein: B
      Berufswunsch: …   (ignored for employment — future intent only)
      Deutsch: Muttersprache
    """
    out: dict[str, list] = {
        "skills": [],
        "software": [],
        "certificates": [],
        "languages": [],
        "licenses": [],
        "target_role": [],
    }
    pending_bucket: str | None = None
    for raw in (body or "").splitlines():
        line = _normalize_bullet(raw)
        if not line:
            continue
        # Continuation of a previous labeled list ending with a comma.
        if pending_bucket and not re.match(
            r"(?i)^(software|edv|it|tools|fachkenntnisse|hard\s*skills|soft\s*skills|"
            r"kompetenzen|zertifikate|certificates|führerschein|fuehrerschein|"
            r"driving\s+licen|berufswunsch|ziel|sprachen|languages?)\s*:",
            line,
        ):
            items = _split_kenntnisse_list_items(line.rstrip(","))
            if pending_bucket == "languages":
                for item in items:
                    lang = _parse_one_language(item)
                    if lang is not None:
                        out["languages"].append(lang)
            else:
                out[pending_bucket].extend(items)
            pending_bucket = pending_bucket if line.rstrip().endswith(",") else None
            continue
        pending_bucket = None
        m = re.match(r"(?i)^(software|edv|it[- ]?kenntnisse|tools|programme)\s*:\s*(.+)$", line)
        if m:
            items = _split_kenntnisse_list_items(m.group(2).rstrip(","))
            out["software"].extend(items)
            if line.rstrip().endswith(","):
                pending_bucket = "software"
            continue
        m = re.match(r"(?i)^(fachkenntnisse|hard\s*skills|soft\s*skills|kompetenzen)\s*:\s*(.+)$", line)
        if m:
            items = _split_kenntnisse_list_items(m.group(2).rstrip(","))
            out["skills"].extend(items)
            if line.rstrip().endswith(","):
                pending_bucket = "skills"
            continue
        m = re.match(r"(?i)^(zertifikate|certificates?|weiterbildungen?)\s*:\s*(.+)$", line)
        if m:
            items = _split_kenntnisse_list_items(m.group(2).rstrip(","))
            out["certificates"].extend(items)
            if line.rstrip().endswith(","):
                pending_bucket = "certificates"
            continue
        m = re.match(r"(?i)^(führerschein|fuehrerschein|driving\s+licen[cs]e?)\s*:\s*(.+)$", line)
        if m:
            out["licenses"].extend(_inline_licence_mentions(m.group(0)) or _parse_driving(m.group(2)))
            continue
        m = re.match(r"(?i)^(berufswunsch|ziel(?:beruf)?|target\s*role|desired\s*role)\s*:\s*(.+)$", line)
        if m:
            role = m.group(2).strip()
            if role:
                out["target_role"].append(role)
            continue
        # Language lines "Deutsch: Muttersprache" / "Englisch: A2"
        lang = _parse_one_language(line)
        if lang is not None:
            out["languages"].append(lang)
            continue
    for k, vals in list(out.items()):
        if k == "languages":
            continue
        out[k] = list(dict.fromkeys(vals))
    return out


def _parse_mixed_languages_tools_mobility(body: str) -> tuple[list[LanguageEntry], list[str], list[str]]:
    lang_lines: list[str] = []
    soft_lines: list[str] = []
    lic: list[str] = []
    for raw in body.splitlines():
        line = _normalize_bullet(raw)
        if not line:
            continue
        if re.match(r"(?i)^(führerschein|fuehrerschein|driving\s+licen)", line):
            lic.extend(_inline_licence_mentions(line))
            continue
        if _LEVEL.search(line) and re.search(r"[A-Za-zÄÖÜäöüß]{3,}", line):
            # Language-looking if CEFR/native tokens present and not pure tool list
            if not re.search(r"(?i)\b(excel|sap|outlook|teams|power\s*bi|jira)\b", line) or _LEVEL.search(line):
                # Prefer language parse when CEFR present with language names
                if re.search(
                    r"(?i)\b(deutsch|englisch|französisch|spanisch|türkisch|tschechisch|"
                    r"german|english|french|spanish|italian|arabic|dutch|polish)\b",
                    line,
                ):
                    lang_lines.append(line)
                    continue
        soft_lines.append(line)
    return _parse_languages("\n".join(lang_lines)), _parse_software("\n".join(soft_lines)), lic


_KNOWN_SOFTWARE_TOKENS = (
    "microsoft 365", "microsoft office", "office 365", "m365", "docuware",
    "sharepoint", "onedrive", "teams", "power automate", "power apps",
    "datev", "sap", "salesforce", "hubspot", "jira", "confluence",

    "office", "excel", "word", "outlook", "powerpoint", "sap", "datev", "jira",
    "confluence", "salesforce", "teams", "windows", "linux", "photoshop",
    "illustrator", "indesign", "adobe indesign", "autocad", "python", "java", "sql", "powerpoint",
    "power bi", "powerbi", "tableau", "zendesk", "hubspot", "navision", "odoo",
    "za office", "upway", "sage", "lexware", "tobii", "chrome", "firefox",
    # Common tools in DE skilled-trade / tech CVs (secondary signal only)
    "figma", "docker", "blender", "qgis", "protool", "davinci resolve", "davinci",
    "unreal engine", "unreal engine 5", "siemens tia portal",
    "tia portal", "s/4hana", "sap s/4hana",
)



_SOFT_SKILL_HINTS = (
    # Note: bare "management" / "-tion" are intentionally NOT hints — they over-match
    # (e.g. compound product names, "Automation", "Documentation"). Compounds like
    # Beschwerdemanagement are handled via _SOFT_SKILL_COMPOUND below.
    "beratung", "orientierung", "kommunikation", "organisation",
    "teamfähigkeit", "teamfaehigkeit", "belastbarkeit", "zuverlässigkeit",
    "zuverlaessigkeit", "verkauf", "akquise", "verhandlung", "reklamation",
    "beschwerde", "kunden", "serviceorient", "führung", "fuehrung",
)

# Compounds / phrases that are soft skills without treating bare "management" as a hint.
_SOFT_SKILL_COMPOUND = re.compile(
    r"(?i)(?:"
    r"\w{3,}(?:management|orientierung|beratung)\b"
    r"|(?<!\w)management(?!\w)\s+\w"
    r"|\w+\s+(?<!\w)management(?!\w)"
    r")"
)


def _known_software_token_match(low: str) -> bool:
    """True when a known software token appears as a whole word (not a substring)."""
    return any(
        re.search(rf"(?<!\w){re.escape(tok)}(?!\w)", low)
        for tok in _KNOWN_SOFTWARE_TOKENS
    )


def _soft_skill_hint_match(low: str) -> bool:
    """Stem/prefix hint match with a leading word boundary (not mid-token)."""
    return any(re.search(rf"(?<!\w){re.escape(h)}", low) for h in _SOFT_SKILL_HINTS)


def _looks_like_soft_skill(value: str) -> bool:
    """True for competency phrases that should not live in the software list."""
    low = (value or "").strip().lower()
    if not low or " / " in low or "(" in low:
        return False
    if _known_software_token_match(low):
        return False
    # Product-like tokens (digits, versions, brand-ish single tokens)
    if re.search(r"\d|\b(office|excel|word|sap|datev|sql|linux|windows|notion|asana|jira|slack|trello)\b", low):
        return False
    if len(low) > 60 or len(low) < 4:
        return False
    hint = _soft_skill_hint_match(low)
    compound = bool(_SOFT_SKILL_COMPOUND.search(low))
    # Single-token product names (Notion, DocuWare) are NOT soft skills.
    if " " not in low and not hint and not compound:
        return False
    if hint or compound:
        return True
    # Multi-word competency suffixes — exclude bare "-tion" (too many FPs).
    return " " in low and any(low.endswith(suf) for suf in ("keit", "ung", "ismus"))


def _looks_like_software(value: str) -> bool:
    low = (value or "").lower()
    if " / " in low:
        return True
    return _known_software_token_match(low)


def parse_cv_text(text: str) -> dict[str, Any]:
    """Heuristic extraction — never invents values not present in text."""
    empty = {
        "raw_text_preview": text[:2000],
        "skills": [],
        "software": [],
        "languages": [],
        "education": [],
        "work_experience": [],
        "certificates": [],
        "driving_license": [],
        "experience_lines": [],
        "emails": [],
        "phones": [],
        "personal": {},
        "uncertain": [],
        "uncertain_items": [],
        "confidence": {},
    }
    if not text.strip():
        empty["confidence"] = {
            k: MISSING_IN_DOCUMENT
            for k in (
                "skills",
                "software",
                "languages",
                "education",
                "work_experience",
                "certificates",
                "driving_license",
                "personal",
            )
        }
        return empty

    from core.text_normalize import extract_german_phones

    emails = re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
    phones = extract_german_phones(text)
    sections = _split_named_sections(text)
    personal = _parse_personal_header(text, sections)
    if phones and not personal.get("phone"):
        personal["phone"] = phones[0]

    languages = _parse_languages(sections.get("languages", ""))
    # Reclassify non-language lines that lived under Sprachen (Weiterbildung,
    # software, soft skills) — never leave Lean Management / Power BI as a language.
    relocated_certs: list[CertificateEntry] = []
    relocated_skills: list[str] = []
    relocated_software: list[str] = []
    uncertain_tokens: list[str] = []
    for raw in (sections.get("languages") or "").splitlines():
        line = _normalize_bullet(raw)
        if not line or _is_heading_value(line) or _is_heading(line):
            continue
        if _parse_one_language(line) is not None:
            continue
        # Ampersand language pairs already handled; skip orphan CEFR.
        if re.fullmatch(r"[ABC][12]", line, re.I):
            continue
        kind = classify_non_language_token(line)
        if kind == "software":
            relocated_software.append(line)
        elif kind == "skill":
            relocated_skills.append(line)
        elif kind == "certificate":
            relocated_certs.append(CertificateEntry(name=line))
        else:
            uncertain_tokens.append(line)
            # Still keep visible as certificate candidate rather than silent drop.
            relocated_certs.append(CertificateEntry(name=line))
    # Drop any residual non-language entries that slipped past chunk parsing.
    languages = [lang for lang in languages if is_known_language_name(lang.language)]
    software = [
        s for s in _parse_software(sections.get("software", "")) if not _is_heading_value(s)
    ]
    if relocated_software:
        software = list(dict.fromkeys([*software, *relocated_software]))
    skills = _parse_skills(sections.get("skills", ""))
    if relocated_skills:
        skills = list(dict.fromkeys([*skills, *relocated_skills]))
    # Compact Kenntnisse blocks with "Software:" / "Fachkenntnisse:" / etc.
    routed = _route_labeled_kenntnisse_lines(sections.get("skills", ""))
    if routed["software"]:
        software = list(dict.fromkeys([*software, *routed["software"]]))
    if routed["skills"]:
        skills = list(dict.fromkeys([*skills, *routed["skills"]]))
    if routed["languages"]:
        known_l = {(lang.language.lower(), (lang.level or "").lower()) for lang in languages}
        for entry in routed["languages"]:
            key = (entry.language.lower(), (entry.level or "").lower())
            if key not in known_l:
                languages.append(entry)
                known_l.add(key)
    routed_licenses = list(routed["licenses"])
    routed_cert_names = list(routed["certificates"])
    target_roles = list(routed["target_role"])
    # Strip leftover labeled lines that slipped into skills before routing.
    skills = [
        s
        for s in skills
        if not re.match(
            r"(?i)^(software|edv|fachkenntnisse|zertifikate|führerschein|berufswunsch)\s*:",
            s,
        )
    ]
    # If the CV only has EDV/IT/"Weitere Kenntnisse" (mapped to software), recover
    # non-tool competency lines as skills — never invent skills not present.
    if not skills:
        soft_body = sections.get("software", "")
        recovered: list[str] = []
        for raw in soft_body.splitlines():
            line = _normalize_bullet(raw)
            if not line or _is_heading_value(line) or _is_heading(line):
                continue
            if _LEVEL.search(line) and _parse_one_language(line) is not None:
                continue
            if _looks_like_software(line) and not _looks_like_soft_skill(line):
                continue
            parts = re.split(r"\s*[,;|/]\s*", line) if re.search(r"[,;|/]", line) else [line]
            for part in parts:
                part = part.strip(" .")
                if not part or len(part) > 80:
                    continue
                if _looks_like_software(part) and not _looks_like_soft_skill(part):
                    continue
                if _looks_like_soft_skill(part) or not _looks_like_software(part):
                    recovered.append(part)
        if recovered:
            skills = list(dict.fromkeys(recovered))
            soft_drop = {s.lower() for s in skills}
            # Remove recovered soft skills from software — keep all real tools,
            # including unknown product names (DocuWare, Microsoft 365, …).
            software = [s for s in software if s.lower() not in soft_drop]
    # Always strip soft-skill phrases that leaked into software and relocate them
    # into skills — even when the skills list is already nonempty.
    if software:
        relocated = [s for s in software if _looks_like_soft_skill(s)]
        software = [s for s in software if not _looks_like_soft_skill(s)]
        if relocated:
            skills = list(dict.fromkeys([*skills, *relocated]))
    # Inverse: tools/languages that leaked into skills after labeled-block parsing
    # (e.g. wrapped "Software: …,\nFigma" also seen by _parse_skills).
    if skills:
        kept_skills: list[str] = []
        for s in skills:
            lang_entry = _parse_one_language(s)
            if lang_entry is not None:
                key = (lang_entry.language.lower(), (lang_entry.level or "").lower())
                known_keys = {(lang.language.lower(), (lang.level or "").lower()) for lang in languages}
                if key not in known_keys:
                    languages.append(lang_entry)
                continue
            # Certificate fragments like bare "Sicherheitsunterweisung" — drop from
            # skills; the full "Role - Sicherheitsunterweisung" line is routed separately.
            if re.search(r"(?i)sicherheitsunterweisung", s) and len(s.split()) <= 4:
                continue
            if _looks_like_software(s) or classify_non_language_token(s) == "software":
                software.append(s)
                continue
            kept_skills.append(s)
        soft_l = {x.lower() for x in software}
        skills = [s for s in kept_skills if s.lower() not in soft_l]
        software = list(dict.fromkeys(software))
    # Bare "Kenntnisse" maps to skills — recover only CEFR/native language lines.
    known = {(lang.language.lower(), (lang.level or "").lower()) for lang in languages}
    for raw in sections.get("skills", "").splitlines():
        line = _normalize_bullet(raw)
        if not line or not _LEVEL.search(line):
            continue
        entry = _parse_one_language(line)
        if entry is None:
            continue
        key = (entry.language.lower(), (entry.level or "").lower())
        if key not in known:
            languages.append(entry)
            known.add(key)
    certificates = [
        c for c in _parse_certificates(sections.get("certificates", "")) if not _is_heading_value(c.name)
    ]
    if relocated_certs:
        existing = {c.name.lower() for c in certificates}
        for c in relocated_certs:
            if c.name.lower() not in existing:
                certificates.append(c)
                existing.add(c.name.lower())
    driving = _parse_driving(sections.get("license", ""))
    # Licence lines parked under Kenntnisse/Skills still count as driving licences.
    for raw in sections.get("skills", "").splitlines():
        line = _normalize_bullet(raw)
        if line and _LICENCE_LINE.match(line):
            for code in _inline_licence_mentions(line) or _parse_driving(line):
                if code not in driving:
                    driving.append(code)
    for code in routed_licenses:
        if code not in driving:
            driving.append(code)
    if routed_cert_names:
        existing = {c.name.lower() for c in certificates}
        for name in routed_cert_names:
            nl = name.lower()
            if nl in existing:
                continue
            # Skip fragments already covered by a longer certificate name.
            if any(nl in ex or ex in nl for ex in existing if len(ex) >= 8):
                continue
            certificates.append(CertificateEntry(name=name))
            existing.add(nl)
    edu_body = sections.get("education", "")
    exp_body = sections.get("experience", "")
    combo = sections.get("education_and_experience", "")
    if combo:
        c_edu, c_exp, c_other = _split_education_and_experience_body(combo)
        edu_body = "\n".join(part for part in (edu_body, c_edu) if part)
        exp_body = "\n".join(part for part in (exp_body, c_exp) if part)
        if c_other:
            extra_soft = [
                s for s in _parse_software(c_other) if not _is_heading_value(s)
            ]
            if extra_soft:
                software = list(dict.fromkeys([*software, *extra_soft]))
    education, edu_certs = _parse_education(edu_body)
    if edu_certs and not certificates:
        certificates.extend(edu_certs)
    elif edu_certs:
        existing = {c.name.lower() for c in certificates}
        for c in edu_certs:
            if c.name.lower() not in existing:
                certificates.append(c)
    experience = _parse_experience(exp_body)
    # Do not drop real jobs that share a title with Berufswunsch — only the
    # labeled intent line is excluded via Kenntnisse routing (target_role).

    if "languages_tools_mobility" in sections:
        m_langs, m_soft, m_lic = _parse_mixed_languages_tools_mobility(
            sections["languages_tools_mobility"]
        )
        if m_langs and not languages:
            languages = m_langs
        if m_soft and not software:
            software = m_soft
        if m_lic and not driving:
            driving = m_lic

    # Fallback: only explicit licence phrases — never scan CEFR from full text.
    if not driving:
        driving = _inline_licence_mentions(text)

    uncertain: list[str] = []
    if driving and not all(re.fullmatch(r"[A-Z0-9]{1,3}", d) for d in driving):
        uncertain.append("driving_license")
    if uncertain_tokens:
        uncertain.append("languages_reclassified")
        # Keep raw tokens visible for import review — never silent drop.
        result_uncertain_items = list(dict.fromkeys(uncertain_tokens))
    else:
        result_uncertain_items = []

    # Semantic confidence downgrades
    confidence = {
        "skills": field_confidence(skills),
        "software": field_confidence(software),
        "languages": field_confidence(languages),
        "education": field_confidence(education),
        "work_experience": field_confidence(experience),
        "certificates": field_confidence(certificates),
        "driving_license": field_confidence(driving),
        "personal": field_confidence(personal),
    }
    fn = (personal.get("first_name") or "").strip()
    ln = (personal.get("last_name") or "").strip()
    if fn and (_is_document_title(fn) or _is_heading_value(f"{fn} {ln}".strip()) or _is_document_title(f"{fn} {ln}")):
        confidence["personal"] = "low"
        uncertain.append("personal")
    for key in uncertain:
        if confidence.get(key) == "high":
            confidence[key] = "low"

    result = {
        "raw_text_preview": text[:2000],
        "skills": list(dict.fromkeys(skills)),
        "software": software,
        "languages": [
            {"language": lang.language, "level": lang.level, "source": "cv"}
            for lang in languages
        ],
        "education": [
            {
                "qualification": e.qualification,
                "institution": e.institution,
                "location": e.location,
                "start_date": e.start_date,
                "end_date": e.end_date,
                "completion_date": e.completion_date,
                "source": "cv",
            }
            for e in education
        ],
        "work_experience": [
            {
                "title": e.title,
                "company": e.company,
                "location": e.location,
                "start_date": e.start_date,
                "end_date": e.end_date,
                "responsibilities": e.responsibilities,
                "source": "cv",
            }
            for e in experience
        ],
        "certificates": [
            {"name": c.name, "issuer": c.issuer, "date": c.date, "source": "cv"}
            for c in certificates
        ],
        "driving_license": [{"value": d, "source": "cv"} for d in dict.fromkeys(driving)],
        "experience_lines": [e.label() for e in experience],
        "emails": list(dict.fromkeys(emails)),
        "phones": list(dict.fromkeys(p.strip() for p in phones)),
        "personal": personal,
        "target_role": target_roles[0] if target_roles else "",
        "uncertain": uncertain,
        "uncertain_items": result_uncertain_items,
        "confidence": confidence,
    }
    return result


_HEADING_LINE = re.compile(
    r"^(Berufserfahrung|Berufliche Erfahrung|Beruflicher Werdegang|Ausbildung|"
    r"Weiterbildungen|Sprachen|Sprachkenntnisse|EDV|EDV-Kenntnisse|Führerschein|"
    r"Fähigkeiten|Kompetenzen|Kenntnisse|Experience|Education|Skills|"
    r"Professional Experience|Employment History|Career History|Employment|"
    r"Academic Background|Language Proficiency|Certifications|Certificates|"
    r"Tech Stack|Tools|Systems|Additional Skills|Core Skills|Key Skills|"
    r"Capabilities|Praxiserfahrung|Fahrerlaubnis|Qualifikation|Weiterbildung|"
    r"Persönliche Daten|Über mich|Profil|Zusammenfassung|Kontakt|"
    r"Praxis|Stationen|Werdegang|Bildungsweg|Schule\s*&\s*Ausbildung|"
    r"Schule\s+und\s+Ausbildung)\b",
    re.I,
)
_POSTAL_DE = re.compile(
    r"(?P<street>.+?)\s*,?\s*(?P<plz>\d{5})\s+(?P<city>[A-Za-zÄÖÜäöüß][A-Za-zÄÖÜäöüß\-\s]+?)"
    r"(?:\s*,\s*(?P<country>DE|AT|CH|Deutschland|Österreich|Schweiz|Germany|Austria|Switzerland))?"
    r"(?=\s*[,|]|\s*$)"
)
_POSTAL_UK_IE = re.compile(
    r"(?P<street>.+?)\s*[·|,]\s*(?P<city>[A-Za-z][A-Za-z\-\s]+?)\s+"
    r"(?P<pc>(?:[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}|[A-Z]\d{2}\s*[A-Z0-9]{4}))"
    r"(?:\s*,?\s*(?P<country>United Kingdom|Ireland|UK|IE))?",
    re.I,
)
_CITY_ONLY = re.compile(
    r"^(?P<city>[A-Za-zÄÖÜäöüß][A-Za-zÄÖÜäöüß\-\s]{1,40})"
    r"(?:\s*,\s*(?P<country>DE|AT|CH|Deutschland|Österreich|Schweiz|Germany|Austria|Switzerland|[A-Za-z][A-Za-z\s]+))?"
    r"\s*(?:\||$)",
    re.I,
)
_DOB = re.compile(
    r"(?:Geburtsdatum|geboren(?:\s+am)?|DoB|Date of birth)\s*[:\-]?\s*"
    r"(?P<dob>\d{1,2}\.\d{1,2}\.\d{2,4})",
    re.I,
)
_NAME_RE = re.compile(
    r"^[A-Za-zÄÖÜäöüß][A-Za-zÄÖÜäöüß\-']+(?:\s+[A-Za-zÄÖÜäöüß][A-Za-zÄÖÜäöüß\-']+){1,3}$"
)


def _norm_simple(s: str) -> str:
    s = (s or "").strip().lower()
    s = s.replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", s)


def _contains_name(text: str, personal: dict[str, str]) -> bool:
    full = f"{personal.get('first_name', '')} {personal.get('last_name', '')}".strip().lower()
    return bool(full) and full in (text or "").strip().lower()


def _clean_street_fragment(
    street: str,
    personal: dict[str, str],
    *,
    labels: tuple[str, ...] = ("Adresse", "Anschrift"),
) -> str:
    """Strip name prefixes, bullets, and address labels from street captures."""
    raw = (street or "").strip(" ,;·|•-*–—")
    if not raw:
        return ""
    label_re = "|".join(re.escape(l) for l in labels)
    raw = re.sub(rf"^(?:{label_re})\s*[:\-]?\s*", "", raw, flags=re.I)
    raw = re.sub(r",?\s*(Germany|Deutschland|United Kingdom|Ireland)\s*$", "", raw, flags=re.I)
    raw = re.sub(r"^[\s•\-–—*·]+", "", raw)
    # Drop leading person name duplicated onto the address line.
    fn = (personal.get("first_name") or "").strip()
    ln = (personal.get("last_name") or "").strip()
    if fn and ln:
        raw = re.sub(
            rf"^{re.escape(fn)}\s+{re.escape(ln)}\s*[,|]?\s*",
            "",
            raw,
            flags=re.I,
        )
    elif fn:
        raw = re.sub(rf"^{re.escape(fn)}\s*[,|]?\s*", "", raw, flags=re.I)
    raw = raw.strip(" ,;·|")
    if not raw or "@" in raw:
        return ""
    # Prefer streets that look like an address (digit or known street suffix).
    if re.search(r"\d", raw) or re.search(
        r"(?i)\b(str(?:asse|\.|aße)?|weg|platz|allee|ring|gasse)\b", raw
    ):
        return raw
    return ""


def _extract_personal_from_lines(lines: list[str], personal: dict[str, str]) -> dict[str, str]:
    """Fill missing name/address fields from an arbitrary list of CV lines."""
    for line in lines:
        line = (line or "").strip()
        if not line:
            continue
        if "@" in line or re.search(r"\+?\d[\d\s\-()]{7,}\d", line):
            continue
        if _DOB.search(line):
            continue
        if _is_heading_value(line) or _is_heading(line) or _is_document_title(line):
            continue
        if line.isupper() and len(line.split()) >= 2:
            continue
        if not personal.get("first_name") and _NAME_RE.fullmatch(line):
            parts = line.split()
            if 2 <= len(parts) <= 4:
                personal["first_name"] = parts[0]
                personal["last_name"] = " ".join(parts[1:])
                break

    for line in lines:
        line = (line or "").strip()
        if not line or personal.get("postal_code"):
            continue
        m = _POSTAL_DE.search(line)
        if m:
            street = _clean_street_fragment(m.group("street"), personal)
            if street:
                personal["street"] = street
            personal["postal_code"] = m.group("plz")
            city = m.group("city").strip(" ,;·|")
            city = re.sub(r",?\s*(Germany|Deutschland)\s*$", "", city, flags=re.I).strip()
            personal["city"] = city
            if m.groupdict().get("country"):
                personal["country"] = m.group("country").strip()
            hn = re.search(r"^(?P<s>.+?)\s+(?P<n>\d+[a-zA-Z]?)$", personal.get("street", ""))
            if hn:
                personal["house_number"] = hn.group("n")
            break
        m2 = _POSTAL_UK_IE.search(line)
        if m2:
            street = _clean_street_fragment(m2.group("street"), personal, labels=("Adresse", "Address"))
            if street:
                personal["street"] = street
            personal["city"] = m2.group("city").strip()
            personal["postal_code"] = re.sub(r"\s+", " ", m2.group("pc").strip().upper())
            if m2.group("country"):
                personal["country"] = m2.group("country").strip()
            break

    # Standalone "12345 München" or street-only line above PLZ.
    if not personal.get("postal_code"):
        for idx, line in enumerate(lines):
            line = (line or "").strip()
            m = re.match(r"^(?P<plz>\d{5})\s+(?P<city>[A-Za-zÄÖÜäöüß][A-Za-zÄÖÜäöüß\\-\\s]+)$", line)
            if not m:
                continue
            personal["postal_code"] = m.group("plz")
            personal["city"] = m.group("city").strip()
            # Previous non-empty line may be the street
            if not personal.get("street") and idx > 0:
                prev = (lines[idx - 1] or "").strip()
                if prev and "@" not in prev and not re.match(r"^\d{5}\b", prev):
                    if not (_NAME_RE.fullmatch(prev) and len(prev.split()) >= 2):
                        cleaned = _clean_street_fragment(prev, personal)
                        if cleaned:
                            personal["street"] = cleaned
                            hn = re.search(r"^(?P<s>.+?)\s+(?P<n>\d+[a-zA-Z]?)$", cleaned)
                            if hn:
                                personal["house_number"] = hn.group("n")
            break

    if not personal.get("city"):
        for line in lines:
            candidate = (line or "").split("|", 1)[0].strip()
            if not candidate or "@" in candidate or re.search(r"\d", candidate):
                continue
            if personal.get("first_name") and _contains_name(candidate, personal):
                continue
            if _NAME_RE.fullmatch(candidate) and len(candidate.split()) >= 2:
                continue
            m3 = _CITY_ONLY.match(candidate) or _CITY_ONLY.match(line)
            if m3 and not re.search(r"\d", m3.group("city")):
                city = m3.group("city").strip()
                if city.lower() not in {"germany", "deutschland", "united kingdom", "ireland"}:
                    personal["city"] = city
                    if m3.group("country"):
                        personal["country"] = m3.group("country").strip()
                    break

    if personal.get("street") or personal.get("postal_code"):
        parts = [
            personal.get("street", ""),
            f"{personal.get('postal_code', '')} {personal.get('city', '')}".strip(),
        ]
        personal["address"] = ", ".join(p for p in parts if p)
    elif personal.get("city") and not personal.get("address"):
        personal["address"] = personal["city"]
    return personal


def _parse_personal_header(text: str, sections: dict[str, str]) -> dict[str, str]:
    """Extract name/address from the CV header (before first known section)."""
    personal: dict[str, str] = {}
    header_lines: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            if header_lines and not all(_is_document_title(x) for x in header_lines):
                break
            continue
        # Document titles must be skipped before heading detection so that
        # "Resume" / "Curriculum Vitae" / "PROFILE" never end the header early.
        if _is_document_title(line):
            continue
        if _HEADING_LINE.match(line) or _is_heading(line):
            break
        header_lines.append(line)
        if len(header_lines) >= 12:
            break

    for line in header_lines:
        if "@" in line or re.search(r"\+?\d[\d\s\-()]{7,}\d", line):
            continue
        if _DOB.search(line):
            continue
        if _is_heading_value(line) or _is_heading(line) or _is_document_title(line):
            continue
        # Reject ALL-CAPS multi-word titles that aren't typical names
        if line.isupper() and len(line.split()) >= 2:
            continue
        if _NAME_RE.fullmatch(line):
            parts = line.split()
            if 2 <= len(parts) <= 4:
                personal["first_name"] = parts[0]
                personal["last_name"] = " ".join(parts[1:])
                break

    for line in header_lines:
        # German PLZ
        m = _POSTAL_DE.search(line)
        if m:
            street = _clean_street_fragment(m.group("street"), personal)
            if street:
                personal["street"] = street
            personal["postal_code"] = m.group("plz")
            city = m.group("city").strip(" ,;·|")
            city = re.sub(r",?\s*(Germany|Deutschland)\s*$", "", city, flags=re.I).strip()
            personal["city"] = city
            if m.groupdict().get("country"):
                personal["country"] = m.group("country").strip()
            hn = re.search(r"^(?P<s>.+?)\s+(?P<n>\d+[a-zA-Z]?)$", personal.get("street", ""))
            if hn:
                personal["house_number"] = hn.group("n")
            break

        m2 = _POSTAL_UK_IE.search(line)
        if m2:
            street = _clean_street_fragment(
                m2.group("street"), personal, labels=("Adresse", "Address")
            )
            if street:
                personal["street"] = street
            personal["city"] = m2.group("city").strip()
            personal["postal_code"] = re.sub(r"\s+", " ", m2.group("pc").strip().upper())
            if m2.group("country"):
                personal["country"] = m2.group("country").strip()
            hn = re.match(r"^(?P<n>\d+[a-zA-Z]?)\s+(?P<s>.+)$", street or "")
            if hn:
                personal["house_number"] = hn.group("n")
            break

    # City-only headers (deliberately incomplete contact data)
    if not personal.get("city"):
        for line in header_lines:
            # Prefer the segment before "|" when contact is "City | email"
            candidate = line.split("|", 1)[0].strip()
            if "@" in candidate or re.search(r"\d", candidate):
                continue
            # Do not treat the person's name line as a city.
            if personal.get("first_name") and _contains_name(candidate, personal):
                continue
            if _NAME_RE.fullmatch(candidate) and len(candidate.split()) >= 2:
                continue
            m3 = _CITY_ONLY.match(candidate) or _CITY_ONLY.match(line)
            if m3 and not re.search(r"\d", m3.group("city")):
                city = m3.group("city").strip()
                if city.lower() not in {"germany", "deutschland", "united kingdom", "ireland"}:
                    personal["city"] = city
                    if m3.group("country"):
                        personal["country"] = m3.group("country").strip()
                    break

    dob_m = _DOB.search(text)
    if dob_m:
        personal["date_of_birth"] = dob_m.group("dob")

    if personal.get("street") or personal.get("postal_code"):
        parts = [
            personal.get("street", ""),
            f"{personal.get('postal_code', '')} {personal.get('city', '')}".strip(),
        ]
        personal["address"] = ", ".join(p for p in parts if p)
    elif personal.get("city"):
        personal["address"] = personal["city"]

    # Many German CVs put contact data under "Persönliche Daten" / Profil —
    # that content lands in sections["profile"] and was previously ignored.
    needs = not (personal.get("first_name") and (personal.get("street") or personal.get("city")))
    if needs:
        profile_body = sections.get("profile") or sections.get("general") or ""
        if profile_body.strip():
            personal = _extract_personal_from_lines(profile_body.splitlines(), personal)

    return personal


def parsed_to_qualifications(parsed: dict[str, Any]) -> QualificationsConfig:
    def _as_sourced(items: list) -> list[dict[str, str]]:
        out = []
        for s in items or []:
            if isinstance(s, dict):
                val = str(s.get("value") or s.get("text") or "").strip()
                if val:
                    out.append({"value": val, "source": "cv"})
            elif str(s).strip():
                out.append({"value": str(s).strip(), "source": "cv"})
        return out

    return parse_qualifications(
        {
            "skills": _as_sourced(parsed.get("skills") or []),
            "software": _as_sourced(parsed.get("software") or []),
            "driving_license": _as_sourced(parsed.get("driving_license") or []),
            "languages": parsed.get("languages") or [],
            "education": parsed.get("education") or [],
            "work_experience": parsed.get("work_experience") or [],
            "certificates": parsed.get("certificates") or [],
        }
    )


def import_cv(
    path: Path,
    *,
    guenther_enabled: bool = False,
    manual_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Import CV via canonical pipeline (deterministic + optional Phi)."""
    from core.cv_intelligence import import_cv_canonical

    return import_cv_canonical(
        path,
        guenther_enabled=guenther_enabled,
        manual_profile=manual_profile,
    )
