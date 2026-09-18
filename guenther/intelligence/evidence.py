"""Canonical EvidenceItem store — structured evidence independent of the LLM."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Iterable


class EvidenceSource(str, Enum):
    PROFILE = "profile"
    CV = "cv"
    JOB = "job"
    EMAIL = "email"
    MANUAL = "manual"
    USER = "user"


class EvidenceKind(str, Enum):
    SKILL = "skill"
    TITLE = "title"
    EMPLOYER = "employer"
    EDUCATION = "education"
    CREDENTIAL = "credential"
    CERTIFICATE = "certificate"
    LANGUAGE = "language"
    DUTY = "duty"
    OTHER = "other"


@dataclass
class EvidenceItem:
    """Trusted fact extracted from PROFILE/CV/MANUAL — never from JOB alone."""

    id: str
    text: str
    source: EvidenceSource
    kind: EvidenceKind = EvidenceKind.OTHER
    quote: str = ""
    aliases: tuple[str, ...] = ()
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["source"] = self.source.value
        d["kind"] = self.kind.value
        d["aliases"] = list(self.aliases)
        return d


@dataclass
class EvidenceStore:
    items: list[EvidenceItem] = field(default_factory=list)

    def add(self, item: EvidenceItem) -> None:
        self.items.append(item)

    def extend(self, items: Iterable[EvidenceItem]) -> None:
        self.items.extend(items)

    def texts(self) -> list[str]:
        out: list[str] = []
        for it in self.items:
            out.append(it.text)
            if it.quote:
                out.append(it.quote)
            out.extend(it.aliases)
        return out

    def corpus(self) -> str:
        return "\n".join(self.texts())

    def by_kind(self, kind: EvidenceKind) -> list[EvidenceItem]:
        return [i for i in self.items if i.kind == kind]

    def to_list(self) -> list[dict[str, Any]]:
        return [i.to_dict() for i in self.items]


def build_evidence_store(
    *,
    profile_text: str = "",
    existing_evidence: list[dict[str, Any]] | None = None,
) -> EvidenceStore:
    """Build store from profile lines + optional structured evidence dicts.

    JOB text must NOT be ingested as candidate evidence here.
    """
    store = EvidenceStore()
    idx = 0
    for line in (profile_text or "").splitlines():
        t = line.strip(" -\t")
        if len(t) < 3:
            continue
        kind = _guess_kind(t)
        aliases: tuple[str, ...] = ()
        if not _line_negates_credential(t):
            aliases = _aliases_for(t, kind)
        else:
            kind = EvidenceKind.OTHER
        store.add(
            EvidenceItem(
                id=f"prof_{idx}",
                text=t,
                source=EvidenceSource.PROFILE,
                kind=kind,
                quote=t,
                aliases=aliases,
            )
        )
        idx += 1
    for raw in existing_evidence or []:
        claim = str(raw.get("claim") or raw.get("text") or "").strip()
        if not claim:
            continue
        src = str(raw.get("source") or "manual").lower()
        try:
            source = EvidenceSource(src)
        except ValueError:
            source = EvidenceSource.MANUAL
        # Never accept JOB-sourced rows as candidate evidence
        if source == EvidenceSource.JOB:
            continue
        kind_raw = raw.get("kind")
        if isinstance(kind_raw, EvidenceKind):
            kind = kind_raw
        elif kind_raw:
            try:
                kind = EvidenceKind(str(kind_raw))
            except ValueError:
                kind = _guess_kind(claim)
        else:
            kind = _guess_kind(claim)
        store.add(
            EvidenceItem(
                id=str(raw.get("id") or f"ev_{idx}"),
                text=claim,
                source=source,
                kind=kind,
                quote=str(raw.get("quote") or claim),
                aliases=tuple(raw.get("aliases") or _aliases_for(claim, kind)),
            )
        )
        idx += 1
    return store


def _line_negates_credential(text: str) -> bool:
    low = text.lower()
    if not any(p in low for p in ("keine ", "kein ", "ohne ", "nicht ")):
        return False
    return any(
        k in low
        for k in (
            "ausbildung",
            "studium",
            "bachelor",
            "master",
            "ihk",
            "zertifikat",
            "abschluss",
            "pflege",
            "examen",
            "schein",
            "lizenz",
        )
    )


def _guess_kind(text: str) -> EvidenceKind:
    low = text.lower()
    if any(
        k in low
        for k in (
            "ausbildung",
            "studium",
            "bachelor",
            "master",
            "ihk",
            "zertifikat",
            "abschluss",
            "pflegeausbildung",
            "abitur",
        )
    ):
        return EvidenceKind.CREDENTIAL if "zertifikat" not in low else EvidenceKind.CERTIFICATE
    if "kenntnisse" in low or low.startswith("- "):
        return EvidenceKind.SKILL
    if any(k in low for k in ("gmbh", " ag", " se ", "klinik", "stadt ", "sparkasse", "volksbank")):
        return EvidenceKind.EMPLOYER
    # Bare "bank" alone is too noisy (person names like "Tina Bank").
    if re.search(r"\b[\w\-]+\s+bank\s+(?:ag|gmbh|se)\b", low) or re.search(
        r"\b(?:deutsche|commerz|hypo|post)\s+bank\b", low
    ):
        return EvidenceKind.EMPLOYER
    if any(k in low for k in ("deutsch", "englisch", "französisch")):
        return EvidenceKind.LANGUAGE
    return EvidenceKind.OTHER


def _aliases_for(text: str, kind: EvidenceKind) -> tuple[str, ...]:
    low = text.lower()
    aliases: list[str] = []
    # Common DE skill aliases
    mapping = {
        "datev": ("datev", "datev-kenntnisse", "datev kreditoren"),
        "excel": ("excel", "excel-auswertungen", "ms excel"),
        "personio": ("personio",),
        "pflegeausbildung": ("pflegeausbildung", "pflegefachkraft", "examinierte pflege"),
        "goä": ("goä", "goa", "abrechnung goä"),
        "active directory": ("active directory", "ad grundlagen"),
    }
    for key, vals in mapping.items():
        if key in low:
            aliases.extend(vals)
    if kind == EvidenceKind.CREDENTIAL and "kauffrau" in low:
        aliases.append("kauffrau für büromanagement")
    return tuple(dict.fromkeys(aliases))
