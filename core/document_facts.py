"""Read Arbeitszeugnisse, certificates and other documents and add what they prove to the profile.

Deterministic on purpose: no model call, so a document can never add a claim that is not written in it. The
cover letter is built from the profile, so everything found here reaches the letter through the profile, with
the source ``document`` so the person can see where it came from.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from core.config import CertificateEntry, QualificationsConfig, SourcedText

SOURCE_DOCUMENT = "document"

KIND_ZEUGNIS = "zeugnis"
KIND_CERTIFICATE = "zertifikat"
KIND_OTHER = "sonstiges"

_ZEUGNIS = re.compile(r"(?<![a-zäöüß])(arbeits|zwischen|dienst|ausbildungs)?zeugnis(?![a-zäöüß])", re.I)
_CERTIFICATE = re.compile(
    r"\b(zertifikat|teilnahmebescheinigung|bescheinigung|urkunde|zertifizierung|certificate|certification)\b", re.I)
_DATE = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b")
_PERIOD = re.compile(
    r"vom\s+(\d{1,2}\.\d{1,2}\.\d{4})\s+bis\s+(?:zum\s+|zu\s+)?(\d{1,2}\.\d{1,2}\.\d{4})", re.I)
_SINCE = re.compile(r"seit\s+(?:dem\s+)?(\d{1,2}\.\d{1,2}\.\d{4})", re.I)
_POSITION = re.compile(
    r"\bals\s+(?P<pos>[A-ZÄÖÜ][^\n,.;]{2,70}?)(?=\s+(?:bei|in|für|tätig|beschäftigt|angestellt|im|im\s+Bereich)\b|[,.;\n])")
_EMPLOYER = re.compile(r"\b(GmbH|mbH|AG|KG|UG|SE|e\.\s?V\.|& Co\.?|OHG|GbR)\b")
_TASK_HEADING = re.compile(r"(aufgaben|tätigkeiten|aufgabengebiet|verantwortungsbereich|zu (?:ihren|seinen) aufgaben)", re.I)
_BULLET = re.compile(r"^\s*[•\-–*·▪]\s+(?P<t>\S.*)$")
_GRADES = (
    (re.compile(r"stets\s+(?:zu\s+)?(?:unserer|meiner)\s+vollsten\s+zufriedenheit", re.I), "sehr gut"),
    (re.compile(r"stets\s+(?:zu\s+)?(?:unserer|meiner)\s+vollen\s+zufriedenheit", re.I), "gut"),
    (re.compile(r"(?:zu\s+)?(?:unserer|meiner)\s+vollen\s+zufriedenheit", re.I), "befriedigend"),
)


@dataclass
class DocumentFacts:
    kind: str = KIND_OTHER
    employer: str = ""
    position: str = ""
    start: str = ""
    end: str = ""
    tasks: list[str] = field(default_factory=list)
    software: list[str] = field(default_factory=list)
    certificate: str = ""
    date: str = ""
    grade: str = ""

    def is_empty(self) -> bool:
        return not (self.employer or self.position or self.tasks or self.software or self.certificate)


def detect_kind(text: str, filename: str = "") -> str:
    head = (text or "")[:700] + " " + filename
    if _ZEUGNIS.search(head):
        return KIND_ZEUGNIS
    if _CERTIFICATE.search(head):
        return KIND_CERTIFICATE
    return KIND_OTHER


def _month_year(raw: str) -> str:
    match = _DATE.search(raw or "")
    return f"{int(match.group(2)):02d}/{match.group(3)}" if match else ""


def _software(text: str) -> list[str]:
    from core.cv_parser import _KNOWN_SOFTWARE_TOKENS

    found: list[str] = []
    seen: set[str] = set()
    for token in _KNOWN_SOFTWARE_TOKENS:
        match = re.search(rf"(?<!\w){re.escape(token)}(?!\w)", text, flags=re.I)
        if match and token.lower() not in seen:
            seen.add(token.lower())
            found.append(match.group(0))
    return found[:12]


def _employer(lines: list[str]) -> str:
    for line in lines[:18]:
        stripped = line.strip(" \t|,")
        if 3 < len(stripped) <= 80 and _EMPLOYER.search(stripped) and not _ZEUGNIS.search(stripped):
            return stripped
    return ""


def _tasks(lines: list[str]) -> list[str]:
    tasks: list[str] = []
    active = False
    for line in lines:
        if _TASK_HEADING.search(line) and len(line) < 120:
            active = True
        bullet = _BULLET.match(line)
        if bullet and (active or not tasks):
            value = bullet.group("t").strip().rstrip(";,.")
            if 6 <= len(value) <= 160:
                tasks.append(value)
        elif active and tasks and line.strip() and not bullet and len(tasks) >= 3:
            break
    return tasks[:10]


def extract_facts(text: str, filename: str = "") -> DocumentFacts:
    text = text or ""
    facts = DocumentFacts(kind=detect_kind(text, filename))
    lines = text.splitlines()
    facts.software = _software(text)
    if facts.kind == KIND_ZEUGNIS:
        facts.employer = _employer(lines)
        period = _PERIOD.search(text)
        if period:
            facts.start, facts.end = _month_year(period.group(1)), _month_year(period.group(2))
        else:
            since = _SINCE.search(text)
            if since:
                facts.start = _month_year(since.group(1))
        position = _POSITION.search(text)
        if position:
            facts.position = position.group("pos").strip()
        facts.tasks = _tasks(lines)
        for pattern, grade in _GRADES:
            if pattern.search(text):
                facts.grade = grade
                break
    elif facts.kind == KIND_CERTIFICATE:
        for line in lines[:14]:
            stripped = line.strip()
            if 4 <= len(stripped) <= 120 and not _DATE.fullmatch(stripped):
                if not re.fullmatch(r"(?i)(zertifikat|bescheinigung|urkunde|certificate)", stripped):
                    facts.certificate = stripped
                    break
        dates = _DATE.findall(text)
        if dates:
            day, month, year = dates[-1]
            facts.date = f"{int(month):02d}/{year}"
    return facts


def _same_company(a: str, b: str) -> bool:
    def key(value: str) -> str:
        value = re.sub(r"(?i)\b(gmbh|mbh|ag|kg|ug|se|e\.\s?v\.|co\.?|ohg|gbr)\b", "", value or "")
        return re.sub(r"[^a-z0-9äöüß]+", "", value.lower())

    ka, kb = key(a), key(b)
    return bool(ka and kb and (ka in kb or kb in ka))


def apply_facts(quals: QualificationsConfig, facts: DocumentFacts, label: str = "") -> list[str]:
    """Add what the document proves to ``quals``; returns one German line per change or hint."""
    changes: list[str] = []
    have_software = {s.normalized_key() for s in quals.software}
    for name in facts.software:
        if name.lower() not in have_software:
            quals.software.append(SourcedText(value=name, source=SOURCE_DOCUMENT))
            have_software.add(name.lower())
            changes.append(f"Software ergänzt: {name}")
    if facts.kind == KIND_CERTIFICATE and facts.certificate:
        known = {c.normalized_key() for c in quals.certificates}
        if facts.certificate.lower() not in known:
            quals.certificates.append(CertificateEntry(name=facts.certificate, date=facts.date, source=SOURCE_DOCUMENT))
            changes.append(f"Zertifikat ergänzt: {facts.certificate}")
    if facts.kind == KIND_ZEUGNIS and facts.employer:
        entry = next((e for e in quals.work_experience if _same_company(e.company, facts.employer)), None)
        if entry is None:
            changes.append(f"Hinweis: {facts.employer} steht nicht im Lebenslauf – bitte dort prüfen und ergänzen.")
        else:
            have = {r.strip().lower() for r in entry.responsibilities}
            added = 0
            for task in facts.tasks:
                if task.lower() not in have:
                    entry.responsibilities.append(task)
                    have.add(task.lower())
                    added += 1
            if added:
                changes.append(f"{added} Aufgabe(n) bei {entry.company} aus dem Zeugnis ergänzt")
            if facts.start and not entry.start_date:
                entry.start_date = facts.start
            if facts.end and not entry.end_date:
                entry.end_date = facts.end
    return changes


def read_document(path: Path) -> DocumentFacts:
    from core.cv_extract import extract_text

    return extract_facts(extract_text(Path(path)), Path(path).name)
