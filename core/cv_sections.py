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
        "expérience professionnelle",
        "experience professionnelle",
        "employment history",
        "work experience",
        "career history",
        "werkervaring",
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
        "education / ausbildung",
        "education/ausbildung",
        "education & ausbildung",
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
        "formation",
        "opleiding",
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
        "sprachen & fahrerlaubnis",
        "sprachen & führerschein",
        "sprachen & fuehrerschein",
        "sprachkenntnisse und fahrerlaubnis",
        "sprachkenntnisse und führerschein",
        "sprachkenntnisse und fuehrerschein",
        "sprachkenntnisse & fahrerlaubnis",
        "sprachkenntnisse & führerschein",
        "sprachkenntnisse & fuehrerschein",
        "languages and driving licence",
        "languages and driving license",
        "languages and licences",
        "languages and licenses",
        "languages & mobility",
        "languages and mobility",
        "langues et mobilité",
        "langues et mobilite",
        "talen en mobiliteit",
        "langues et permis",
        "kenntnisse sprachen",
        "skills languages",
        "language proficiency",
        "language skills",
        "language skill",
        "sprachkenntnisse",
        "fremdsprachen",
        "languages",
        "langues",
        "talen",
        "sprachen",
    ),
    "software": (
        "applications & platforms",
        "applications and platforms",
        "applications / programme",
        "applications/programme",
        "applications / programmes",
        "programme und werkzeuge",
        "programme & werkzeuge",
        "digitale werkzeuge",
        "outils numériques",
        "outils numeriques",
        "digitale tools",
        "software tools",
        "technical tools",
        "digital tools",
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
        "anwendungen",
        "programme",
        "logiciels",
        "systems",
        "software",
        "tools",
        "edv",
        "it",
    ),
    "license": (
        "führerscheinklassen",
        "fuehrerscheinklassen",
        "fahrerlaubnisklassen",
        "fahrerlaubnisklasse",
        "führerscheinklasse",
        "fuehrerscheinklasse",
        "driving licence",
        "driving license",
        "licence class",
        "license class",
        "driving permits",
        "fahrerlaubnis",
        "führerschein",
        "fuehrerschein",
    ),
    "skills": (
        "schlüsselkompetenzen",
        "fachkompetenzen",
        "kernkompetenzen",
        "kompetenzprofil",
        "core competencies",
        "key competencies",
        "additional skills",
        "professional skills",
        "compétences professionnelles",
        "competences professionnelles",
        "fachkenntnisse",
        "core skills",
        "key skills",
        "soft skills",
        "capabilities",
        "competencies",
        "compétences",
        "competences",
        "vaardigheden",
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
        "informations complémentaires",
        "informations complementaires",
        "aanvullende informatie",
        "zusätzliche angaben",
        "zusaetzliche angaben",
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
    "mobility",
    "mobiliteit",
    "werkzeuge",
    "programme",
    "programmes",
    "anwendungen",
    "platforms",
    "ausbildung",
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


_HEADING_TRAILING_JOIN = re.compile(
    r"(?i)^(?P<head>.+?)\s*(?P<join>&|und|and|/)\s*$"
)


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


def _join_wrapped_heading_lines(lines: list[str]) -> list[str]:
    """Merge ``Sprachkenntnisse &`` + ``Führerschein`` into one heading line.

    PDF extractors often wrap composite headings after ``&`` / ``und`` / ``and``.
    Only join when the next non-empty line is itself a heading token or a
    composite-rest token — never swallow body content.
    """
    out: list[str] = []
    i = 0
    while i < len(lines):
        raw = lines[i]
        line = raw.strip()
        m = _HEADING_TRAILING_JOIN.match(line) if line else None
        if m:
            # Peek next non-empty line
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines):
                nxt = lines[j].strip()
                joined = f"{m.group('head')} {m.group('join')} {nxt}"
                # Accept join when the combined line is a known heading, or when
                # the head alone is a heading prefix and nxt is a rest-ok token.
                if is_heading(joined) or (
                    is_heading(m.group("head"))
                    and _normalize_heading_key(nxt) in _COMPOSITE_REST_OK
                ):
                    out.append(joined)
                    i = j + 1
                    continue
        out.append(raw)
        i += 1
    return out


_CONTEXTUAL_SOFTWARE_HEADINGS = frozenset(
    {
        "applications",
        "application",
        "anwendungen",
    }
)

_SOFTWARE_LINE_HINT = re.compile(
    r"(?i)(-|\u2013|\u2014|:)\s*(grundlagen|grundkenntnisse|gute\s+kenntnisse|"
    r"sehr\s+gut|fortgeschritten|kenntnisse|beginner|intermediate|advanced)\s*$"
    r"|\b(sap|office|excel|sql|python|java|linux|windows|studio|tableau|"
    r"grafana|postgres|oracle|adobe|fusion|gimp|ansys|minitab|qgis|jira)\b"
)


def _following_looks_like_software(lines: list[str], start: int, *, limit: int = 6) -> bool:
    """True when upcoming lines look like tool entries (not job-application prose)."""
    seen = 0
    for j in range(start, min(len(lines), start + limit)):
        line = lines[j].strip()
        if not line:
            continue
        if is_heading(line):
            break
        seen += 1
        if _SOFTWARE_LINE_HINT.search(line) or (
            len(line) <= 40 and re.search(r"[A-Z]{2,}|\d|[A-Z][a-z]+[A-Z]", line)
        ):
            return True
        if seen >= 3:
            break
    return False


def split_named_sections(text: str) -> dict[str, str]:
    lines = _join_wrapped_heading_lines(text.splitlines())
    sections: dict[str, list[str]] = {"general": []}
    current = "general"
    for idx, raw in enumerate(lines):
        line = raw.strip()
        if not line:
            sections.setdefault(current, []).append("")
            continue
        heading = is_heading(line)
        if not heading:
            key = _normalize_heading_key(line)
            if key in _CONTEXTUAL_SOFTWARE_HEADINGS and _following_looks_like_software(
                lines, idx + 1
            ):
                heading = "software"
        if heading:
            current = heading
            sections.setdefault(current, [])
            continue
        if is_document_title(line):
            continue
        sections.setdefault(current, []).append(raw.rstrip())
    return {k: "\n".join(v).strip() for k, v in sections.items() if "".join(v).strip()}
