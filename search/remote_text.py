"""Work model (onsite / hybrid / remote) from a job's own wording.

Written for Karrierekrake from the German and English phrasings job ads use. Rules, in order:

1. Tool and product words that merely contain "remote" (Remote Desktop, remote access ...) are ignored.
2. An explicit negation ("kein Homeoffice", "ohne Remote") or an on-site duty ("Präsenzpflicht", "vor Ort")
   is on-site evidence. It beats a bare ``flag=True``: the ad's own words win over a portal checkbox.
3. Positive words (Homeoffice, Remote, Telearbeit, "von zu Hause" ...) mean remote; a hybrid cue
   (hybrid, teilweise, anteilig, "2 Tage") turns that into hybrid.
4. Without any wording, an explicit ``flag`` decides; with ``flag=None`` the answer stays unknown.
"""
from __future__ import annotations

import re

from core.models import RemoteType

_TOOLING = re.compile(
    r"remote[\s-]*(?:desktop|access|zugriff|support|wartung|administration|management|monitoring|sensing)", re.IGNORECASE)
_REMOTE_WORDS = (
    r"home[\s-]*office|homeoffice|remote|telearbeit|telecommut\w*|telework\w*|fernarbeit|work[\s-]*from[\s-]*home|"
    r"wfh|mobil(?:e[sn]?)?[\s-]*(?:arbeit\w*|arbeiten|work)|arbeiten?\s+von\s+zu\s+hause|von\s+zu\s+hause|"
    r"ortsunabh[aä]ngig\w*"
)
_NEGATED = re.compile(
    r"(?:\b(?:kein(?:e[nrms]?)?|ohne|nicht|no|without|not)\b[^.;:\n]{0,24}?(?:" + _REMOTE_WORDS + r"))"
    r"|(?:(?:" + _REMOTE_WORDS + r")[^.;:\n]{0,16}?\b(?:nicht|ausgeschlossen|unm[oö]glich|not\s+possible|not\s+available)\b)",
    re.IGNORECASE,
)
_REMOTE = re.compile(r"(?:" + _REMOTE_WORDS + r")", re.IGNORECASE)
_HYBRID = re.compile(
    r"hybrid|teilweise|anteil(?:ig\w*|s)|zeitweise|\b\d+\s*(?:tage?|days?)\b|tageweise|gelegentlich|"
    r"nach\s+absprache|part[\s-]*time\s+remote", re.IGNORECASE)
_ONSITE = re.compile(
    r"pr[aä]senz(?:pflicht|arbeit|stelle)?|vor[\s-]*ort|on[\s-]*site|onsite|vor\s+ort\s+im\s+b[uü]ro|ausschlie[sß]lich\s+im\s+b[uü]ro",
    re.IGNORECASE)


def classify_remote(text: str = "", *, flag: bool | None = None, telecommute: bool = False,
                    flag_true: str = RemoteType.REMOTE.value) -> str:
    """Return ``onsite`` | ``hybrid`` | ``remote`` | ``unknown``.

    ``flag`` is a portal checkbox (True = home office possible, False = explicitly not, None = no information),
    ``telecommute`` the structured ``jobLocationType`` of a JobPosting, ``flag_true`` what a bare True flag means.
    """
    body = _TOOLING.sub(" ", text or "")
    negated = bool(_NEGATED.search(body))
    positive_text = _NEGATED.sub(" ", body)
    has_remote = bool(_REMOTE.search(positive_text)) or telecommute
    on_site_words = bool(_ONSITE.search(_NEGATED.sub(" ", body)))
    if negated and not has_remote:
        return RemoteType.ONSITE.value
    if has_remote:
        hybrid = bool(_HYBRID.search(positive_text))
        return RemoteType.HYBRID.value if hybrid and not telecommute else RemoteType.REMOTE.value
    if _HYBRID.search(positive_text) and re.search(r"hybrid", positive_text, re.IGNORECASE):
        return RemoteType.HYBRID.value
    if on_site_words:
        return RemoteType.ONSITE.value
    if flag is True:
        return flag_true
    if flag is False:
        return RemoteType.ONSITE.value
    return RemoteType.UNKNOWN.value


def truthy_flag(value: object) -> bool | None:
    """True / False for the usual spellings of a yes-no field; None when the value says nothing."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value or "").strip().casefold()
    if text in {"true", "1", "ja", "yes", "y", "wahr"}:
        return True
    if text in {"false", "0", "nein", "no", "n", "falsch"}:
        return False
    return None
