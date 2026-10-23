"""Where does each sentence of a cover letter come from?

Every sentence is matched against the person's own profile (stations, tasks, education, skills, software,
languages, certificates) and against the job ad. A sentence that matches nothing is labelled as standard wording,
so nothing looks like a claim about the person when it is not. The match is by words, not by understanding; the
label says "erkannt", it is a pointer to check, not a guarantee.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_WORD = re.compile(r"[a-zäöüß0-9][a-zäöüß0-9+#./-]*", re.IGNORECASE)
_STOP = {
    "und", "oder", "der", "die", "das", "den", "dem", "des", "ein", "eine", "einen", "einem", "einer", "mit", "für", "von",
    "bei", "im", "in", "am", "an", "auf", "zu", "zur", "zum", "als", "ich", "mich", "mir", "meine", "meiner", "meinen",
    "sie", "ihre", "ihrer", "ihren", "ihr", "sehr", "geehrte", "damen", "herren", "gruß", "grüßen", "freundlichen",
    "m/w/d", "w/m/d", "all", "genders", "gmbh", "ag", "kg", "co", "mbh", "e.v.",
}


@dataclass(frozen=True)
class Source:
    kind: str  # station | task | education | skill | software | language | certificate | ad | standard
    label: str


@dataclass
class SentenceSource:
    text: str
    sources: list[Source] = field(default_factory=list)

    @property
    def is_standard(self) -> bool:
        return not self.sources


def _words(text: str) -> set[str]:
    return {w.lower().strip(".-/") for w in _WORD.findall(text or "")
            if len(w.strip(".-/")) >= 4 and w.lower().strip(".-/") not in _STOP}


def _hit(sentence_words: set[str], key_words: set[str], need: int) -> bool:
    if not key_words:
        return False
    common = sentence_words & key_words
    return len(common) >= min(need, len(key_words))


def explain_sentences(letter: str, qualifications: Any, *, job_title: str = "", company: str = "") -> list[SentenceSource]:
    """One entry per sentence of ``letter``, each with the profile or ad items it is built from."""
    quals = qualifications
    items: list[tuple[Source, set[str], int]] = []
    phrases: list[tuple[Source, str]] = []  # short names such as SAP or C++ are matched as whole words
    for exp in getattr(quals, "work_experience", None) or []:
        head = " bei ".join(p for p in (exp.title, exp.company) if p)
        items.append((Source("station", head), _words(exp.title), 2))
        if exp.company:
            items.append((Source("station", head), _words(exp.company), 1))
        for task in exp.responsibilities or []:
            items.append((Source("task", f"Aufgabe bei {exp.company or exp.title}: {task[:60]}"), _words(task), 2))
    for edu in getattr(quals, "education", None) or []:
        items.append((Source("education", edu.label()), _words(edu.qualification), 2))
    for name, group in (("skill", "skill_values"), ("software", "software_values")):
        for value in getattr(quals, group)() if hasattr(quals, group) else []:
            phrases.append((Source(name, ("Kenntnis: " if name == "skill" else "Programm: ") + value), value))
    for lang in getattr(quals, "languages", None) or []:
        items.append((Source("language", "Sprache: " + lang.label()), _words(lang.language), 1))
    for cert in getattr(quals, "certificates", None) or []:
        items.append((Source("certificate", "Zertifikat: " + cert.name), _words(cert.name), 2))
    ad_words = _words(job_title)
    result: list[SentenceSource] = []
    for raw in _SENTENCE_SPLIT.split(letter or ""):
        sentence = raw.strip()
        if len(sentence) < 12:
            continue
        sw = _words(sentence)
        found: list[Source] = []
        for source, key, need in items:
            if _hit(sw, key, need) and source not in found:
                found.append(source)
        low = sentence.lower()
        for source, value in phrases:
            if value.strip() and re.search(r"(?<!\w)" + re.escape(value.strip().lower()) + r"(?!\w)", low) and source not in found:
                found.append(source)
        if company and company.lower() in sentence.lower():
            found.append(Source("ad", f"Anzeige: {company}"))
        elif _hit(sw, ad_words, 2):
            found.append(Source("ad", f"Anzeige: {job_title[:50]}"))
        result.append(SentenceSource(sentence, found[:4]))
    return result
