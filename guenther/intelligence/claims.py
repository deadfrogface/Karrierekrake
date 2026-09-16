"""Extract GeneratedClaims from model output — support status decided elsewhere."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Iterable


class ClaimKind(str, Enum):
    CREDENTIAL = "credential"
    SKILL = "skill"
    EMPLOYER = "employer"
    ROLE = "role"
    COMPANY = "company"
    EXPERIENCE = "experience"
    OTHER = "other"


@dataclass
class GeneratedClaim:
    text: str
    kind: ClaimKind
    span: str = ""
    requires_direct: bool = False
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["kind"] = self.kind.value
        return d


# Formal credentials / degrees — MUST be DIRECT-supported in profile
_CREDENTIAL_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"pflegeausbildung(?:\s+\w+){0,4}", re.I), "Pflegeausbildung"),
    (re.compile(r"abgeschlossene\s+pflegeausbildung", re.I), "Pflegeausbildung"),
    (re.compile(r"examinierte[rn]?\s+pflege(?:fach)?kraft", re.I), "Pflegeausbildung"),
    (re.compile(r"pflegefachkraft", re.I), "Pflegefachkraft"),
    (re.compile(r"ausbildung\s+als\s+[\w\-äöüÄÖÜß\s]{3,40}", re.I), "Ausbildung"),
    (re.compile(r"ausbildung[:\s]+[\w\-äöüÄÖÜß\s/]{3,40}", re.I), "Ausbildung"),
    (re.compile(r"bachelor(?:\s+(?:of|in)\s+[\w\s]{2,30})?", re.I), "Bachelor"),
    (re.compile(r"master(?:\s+(?:of|in)\s+[\w\s]{2,30})?", re.I), "Master"),
    (re.compile(r"ihk[\w\s\-]{0,40}", re.I), "IHK"),
    (re.compile(r"zertifikat[:\s]+[\w\-äöüÄÖÜß\s]{3,40}", re.I), "Zertifikat"),
    (re.compile(r"abitur", re.I), "Abitur"),
    (re.compile(r"(?:2\.\s*)?staatsexamen", re.I), "Staatsexamen"),
    (re.compile(r"meisterbrief", re.I), "Meisterbrief"),
    (re.compile(r"\bmeister\b", re.I), "Meister"),
    (re.compile(r"istqb", re.I), "ISTQB"),
    (re.compile(r"netzwerkzertifikat", re.I), "Netzwerkzertifikat"),
    (re.compile(r"\bccna\b", re.I), "CCNA"),
    (re.compile(r"controlling[\-\s]?studium", re.I), "Studium"),
    (re.compile(r"\bstudium\b", re.I), "Studium"),
]

_EMPLOYER_PATTERNS = [
    re.compile(
        r"(?:bei|für|an\s+der|an\s+dem)\s+([A-ZÄÖÜ][\w\-äöüÄÖÜß]*(?:\s+[A-ZÄÖÜ][\w\-äöüÄÖÜß]*){0,4})",
    ),
    re.compile(r"\b([A-ZÄÖÜ][\w\-]+(?:\s+(?:GmbH|AG|SE|KG|OHG|Bank|Klinik|Mart|Works|Digital))?)\b"),
]


# Possession / qualification assertions (language patterns — grounding uses evidence, not this list).
_POSSESSION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"(?:ich|wir)\s+(?:habe|haben|bin|besitze|verfüge|erwarb|erhalten|absolviert|abgeschlossen)\s+"
        r"(?:eine|einen|meine|meinen|das|die|den)?\s*([A-ZÄÖÜa-zäöüß0-9][\w\-äöüÄÖÜß\s/]{3,55})",
        re.I,
    ),
    re.compile(
        r"mit\s+(?:meiner|meinem|einer|einem)\s+(?:abgeschlossenen|erworbenen|bestandenen)?\s*"
        r"([\w\-äöüÄÖÜß\s/]{4,55})",
        re.I,
    ),
    re.compile(
        r"(?:als|zum|zur)\s+(?:zertifizierte[rn]?|examinierte[rn]?|geprüfte[rn]?|qualifizierte[rn]?)\s+"
        r"([\w\-äöüÄÖÜß\s/]{4,55})",
        re.I,
    ),
    re.compile(
        r"(?:ich|wir)\s+(?:bin|sind)\s+(?:zertifiziert|examiniert|lizenziert)\s+(?:als|für)?\s*"
        r"([\w\-äöüÄÖÜß\s/]{4,55})",
        re.I,
    ),
]

_POSSESSION_STOP = frozenset(
    {
        "sehr",
        "geehrte",
        "damen",
        "herren",
        "freue",
        "mich",
        "darauf",
        "team",
        "position",
        "stelle",
        "bewerbung",
        "interesse",
        "vielen",
        "dank",
        "grüßen",
        "mit",
        "freundlichen",
    }
)


def _clean_possession_phrase(phrase: str) -> str:
    p = re.sub(r"\s+", " ", (phrase or "").strip(" .,;:"))
    # Trim trailing clause glue
    p = re.split(r"\s+(?:und|sowie|mit|für|in|bei|an)\s+", p, maxsplit=1)[0].strip()
    return p


def extract_claims_from_text(text: str, *, subject: str = "") -> list[GeneratedClaim]:
    """Pull factual claims from free text. Does NOT decide support status."""
    blob = f"{subject or ''}\n{text or ''}"
    claims: list[GeneratedClaim] = []
    seen: set[str] = set()

    for pat in _POSSESSION_PATTERNS:
        for m in pat.finditer(blob):
            phrase = _clean_possession_phrase(m.group(1))
            if len(phrase) < 4:
                continue
            toks = {t.lower() for t in re.findall(r"\w+", phrase) if len(t) >= 3}
            if toks and toks <= _POSSESSION_STOP:
                continue
            key = phrase.lower()
            if key in seen:
                continue
            seen.add(key)
            claims.append(
                GeneratedClaim(
                    text=phrase,
                    kind=ClaimKind.CREDENTIAL,
                    span=m.group(0).strip(),
                    requires_direct=True,
                    meta={"family": "possession_assertion", "assertion": "POSSESSES"},
                )
            )

    for pat, label in _CREDENTIAL_PATTERNS:
        for m in pat.finditer(blob):
            span = m.group(0).strip()
            key = span.lower()
            if key in seen:
                continue
            seen.add(key)
            claims.append(
                GeneratedClaim(
                    text=span,
                    kind=ClaimKind.CREDENTIAL,
                    span=span,
                    requires_direct=True,
                    meta={"family": label},
                )
            )

    # Explicit "abgeschlossene X" style
    for m in re.finditer(
        r"mit\s+(?:meiner\s+)?abgeschlossenen\s+([\w\-äöüÄÖÜß\s]{4,40})",
        blob,
        re.I,
    ):
        span = m.group(0).strip()
        key = span.lower()
        if key not in seen:
            seen.add(key)
            claims.append(
                GeneratedClaim(
                    text=span,
                    kind=ClaimKind.CREDENTIAL,
                    span=span,
                    requires_direct=True,
                    meta={"family": "abgeschlossen"},
                )
            )

    return claims


def extract_claims_from_writing(suggestion: dict[str, Any]) -> list[GeneratedClaim]:
    return extract_claims_from_text(
        str(suggestion.get("body") or ""),
        subject=str(suggestion.get("subject") or ""),
    )


def extract_claims_from_interview(suggestion: dict[str, Any]) -> list[GeneratedClaim]:
    parts: list[str] = []
    for key in ("talking_points", "questions", "gap_notes"):
        vals = suggestion.get(key) or []
        if isinstance(vals, list):
            parts.extend(str(v) for v in vals)
    return extract_claims_from_text("\n".join(parts))


def claims_to_dicts(claims: Iterable[GeneratedClaim]) -> list[dict[str, Any]]:
    return [c.to_dict() for c in claims]
