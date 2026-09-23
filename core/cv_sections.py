"""German + English CV section heading detection and body splitting."""

from __future__ import annotations

import re

# Longer / more specific aliases should appear first within each group so
# compound headings (e.g. "weiterbildungen & zertifikate") match correctly.
HEADINGS: dict[str, tuple[str, ...]] = {
    "experience": (
        "berufliche erfahrung",
        "beruflicher Werdegang",
        "berufserfahrung",
        "berufliche stationen",
        "professional experience",
        "employment history",
        "work experience",
        "career history",
        "praxiserfahrung",
        "berufspraxis",
        "beschäftigung",
        "employment",
        "experience",
        "tätigkeiten",
        "karriere",
        "erfahrung",
        # Short standalone headings common in DE CVs (must end Kenntnisse blocks).
        "stationen",
        "werdegang",
        "praxis",
    ),
    "education_and_experience": (
        "schul- und berufsausbildung und berufserfahrung",
        "ausbildung und berufserfahrung",
        "ausbildung und berufliche erfahrung",
        "ausbildung & berufserfahrung",
        "ausbildung und tätigkeiten",
        "education and experience",
        "education & experience",
        "education and work experience",
    ),
    "education": (
        "schul- und berufsausbildung",
        "schule & ausbildung",
        "schule und ausbildung",
        "academic background",
        "education & training",
        "education and training",
        "akademischer Werdegang",
        "schulischer Werdegang",
        "ausbildungen",
        "ausbildung",
        "schulbildung",
        "qualifikationen",
        "qualifikation",
        "bildungsweg",
        "education",
        "studium",
        "schule",
    ),
    "certificates": (
        "weiterbildungen & zertifikate",
        "weiterbildungen und zertifikate",
        "weiterbildungen",
        "weiterbildung",
        "zertifizierungen",
        "zertifizierung",
        "certifications",
        "certificates",
        "zertifikate",
        "zertifikat",
        "fortbildungen",
        "fortbildung",
        "seminare",
        "kurse",
    ),
    "languages": (
        "sprachen / it / mobilität",
        "sprachen / it / mobilitaet",
        "sprachen und fahrerlaubnis",
        "sprachen und führerschein",
        "sprachen und fuehrerschein",
        "languages and driving licence",
        "languages and driving license",
        "languages and licences",
        "languages and licenses",
        "kenntnisse sprachen",
        "skills languages",
        "language proficiency",
        "language skills",
        "language skill",
        "sprachkenntnisse",
        "fremdsprachen",
        "languages",
        "sprachen",
    ),
    "software": (
        "applications & platforms",
        "applications and platforms",
        "weitere kenntnisse",
        "edv-kenntnisse",
        "edv kenntnisse",
        "it-kenntnisse",
        "it kenntnisse",
        "computerkenntnisse",
        "anwenderkenntnisse",
        "pc-kenntnisse",
        "pc kenntnisse",
        "tech stack",
        "it skills",
        "systems",
        "software",
        "tools",
        "edv",
        "it",
    ),
    "license": (
        "führerscheinklassen",
        "fuehrerscheinklassen",
        "driving licence",
        "driving license",
        "fahrerlaubnis",
        "führerschein",
        "fuehrerschein",
    ),
    "skills": (
        "schlüsselkompetenzen",
        "additional skills",
        "fachkenntnisse",
        "core skills",
        "key skills",
        "soft skills",
        "capabilities",
        "kompetenzen",
        "fähigkeiten",
        "kenntnisse",
        "werkzeuge",  # DE CVs: tools/languages/software block (same routing as Kenntnisse)
        "stärken",
        "skills",
    ),
    "profile": (
        "persönliche daten",
        "persoenliche daten",
        "über mich",
        "ueber mich",
        "zusammenfassung",
        "projekt- und sonderaufgaben",
        "additional information",
        "weitere angaben",
        "sonstiges",
        "summary",
        "profil",
        "kontakt",
        "interessen",
        "hobbys",
        "hobby",
    ),
    # Composite bodies that mix languages + tools + mobility on one block.
    "languages_tools_mobility": (
        "sprachen / it / mobilität",
        "sprachen / it / mobilitaet",
        "sprachen/it/mobilität",
        "sprachen/it/mobilitaet",
    ),
}

# Keep languages_tools_mobility out of the primary languages list for exact
# matching priority — those aliases live only on the composite key.
HEADINGS["languages"] = tuple(
    a
    for a in HEADINGS["languages"]
    if a not in HEADINGS["languages_tools_mobility"]
)

ALL_HEADING_ALIASES = {
    alias.lower() for aliases in HEADINGS.values() for alias in aliases
}

_DOC_TITLE = re.compile(
    r"(?is)^(tabellarischer\s+)?"
    r"(lebenslauf|curriculum\s+vitae|cv|résumé|resume|"
    r"fiktiver(\s+test)?[\-\s]*lebenslauf|bewerbungsprofil|"
    r"personal\s+profile|profile)$"
)

_COMPOSITE_REST_OK = {
    "zertifikate",
    "zertifikat",
    "certificates",
    "certifications",
    "training",
    "kurse",
    "platforms",
    "it",
    "mobilität",
    "mobilitaet",
    "tools",
    # Language + licence composite headings (e.g. "Sprachen & Fahrerlaubnis")
    "fahrerlaubnis",
    "führerschein",
    "fuehrerschein",
    "führerscheine",
    "fuehrerscheine",
    "licence",
    "license",
    "licences",
    "licenses",
    "driving",
    # Compound headings like "Ausbildung und Berufserfahrung"
    "und",
    "and",
    "berufserfahrung",
    "berufserfahrungen",
    "praktika",
    "praktikum",
    "work",
    "experience",
    "employment",
    "schulische",
}


def normalize_bullet(line: str) -> str:
    return re.sub(r"^[\s•\-–—*·]+", "", line).strip()


def is_document_title(line: str) -> bool:
    cleaned = line.strip()
    if not cleaned:
        return False
    return bool(_DOC_TITLE.fullmatch(cleaned))


def _normalize_heading_key(line: str) -> str:
    cleaned = line.strip().lower().rstrip(":").strip()
    cleaned = cleaned.replace("&", " & ")
    # Treat en/em dashes like spaces so "Kenntnisse – Sprachen" matches.
    cleaned = re.sub(r"[–—−]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


def is_heading(line: str) -> str | None:
    cleaned = _normalize_heading_key(line)
    if not cleaned or len(cleaned) > 64:
        return None

    # Exact match — prefer longer aliases via sorted scan.
    best: tuple[int, str] | None = None
    for key, aliases in HEADINGS.items():
        for alias in aliases:
            al = alias.lower()
            if cleaned == al:
                score = len(al)
                if best is None or score > best[0]:
                    best = (score, key)
            elif cleaned.startswith(al):
                rest = cleaned[len(al) :].strip(" &/|,.-")
                if not rest or rest in _COMPOSITE_REST_OK or all(
                    tok in _COMPOSITE_REST_OK for tok in re.split(r"[\s/&]+", rest) if tok
                ):
                    score = len(al)
                    if best is None or score > best[0]:
                        best = (score, key)
    return best[1] if best else None


def is_heading_value(text: str) -> bool:
    cleaned = _normalize_heading_key(text)
    if cleaned in ALL_HEADING_ALIASES:
        return True
    # Reject bare document titles used as values.
    return is_document_title(text)


def split_named_sections(text: str) -> dict[str, str]:
    lines = text.splitlines()
    sections: dict[str, list[str]] = {"general": []}
    current = "general"
    for raw in lines:
        line = raw.strip()
        if not line:
            sections.setdefault(current, []).append("")
            continue
        heading = is_heading(line)
        if heading:
            current = heading
            sections.setdefault(current, [])
            continue
        if is_document_title(line):
            continue
        sections.setdefault(current, []).append(raw.rstrip())
    return {k: "\n".join(v).strip() for k, v in sections.items() if "".join(v).strip()}
