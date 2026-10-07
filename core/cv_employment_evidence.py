"""Preserve verbatim duties from unambiguous, already extracted CV stations.

This never discovers a role or employer. Ambiguous layouts yield no duties.
"""
from __future__ import annotations

from dataclasses import replace
import re

_SECTION = re.compile(
    r"(?i)^(?:ausbildung|education|studium|schulbildung|sprachen|languages?|"
    r"software|systems?|tools?|kenntnisse|skills?|key skills|competencies|"
    r"weiterbildungen?|certificates?|certifications?|training|führerschein|"
    r"driving licen[cs]e|profil|profile|hobbys?|interests?|references?)\s*:?$"
)
_DATED = re.compile(r"^(?:(?:\d{1,2}[./]){1,2})?(?:19|20)\d{2}\b")


def _fold(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def station_source_duties(title: str, company: str, source: str, *, other_stations=()) -> list[str]:
    """Quote lines after a unique adjacent role/employer pair, never across jobs."""
    if not title or not company or not source:
        return []
    lines = [line.strip() for line in source.splitlines()]
    folded = [_fold(line) for line in lines]
    roles = [i for i, line in enumerate(folded) if _fold(title) in line]
    employers = [i for i, line in enumerate(folded) if _fold(company) in line]
    pairs = [(a, b) for a in roles for b in employers if abs(a - b) <= 2]
    if len(pairs) != 1:
        return []
    start = max(pairs[0]) + 1
    duties = []
    for line in lines[start:]:
        plain = line.lstrip("•*-– ").strip()
        if any(_fold(anchor) in _fold(plain)
               for station in other_stations for anchor in station if anchor):
            break
        if _SECTION.fullmatch(plain) or _DATED.match(plain) or "|" in plain:
            break
        if not plain:
            break
        # Short headings / dates / isolated location lines are not duties.
        if plain.endswith(":") or len(plain) < 12 or len(plain.split()) < 2:
            break
        if line == plain and not any(mark in plain for mark in (",", ";", ".")):
            break
        duties.append(plain)
    return list(dict.fromkeys(duties))


def with_source_duties(entries, source: str, *, cv_import: bool = False):
    """Backfill old imports without changing their confirmed roles or stored data."""
    return [
        replace(entry, responsibilities=station_source_duties(
            entry.title, entry.company, source,
            other_stations=[(other.title, other.company) for other in entries if other is not entry],
        ))
        if not entry.responsibilities and (
            entry.source == "cv" or (not entry.source and cv_import)
        ) else entry
        for entry in entries
    ]
