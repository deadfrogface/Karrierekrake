"""Cover-letter claim guard.

Personal claims may paraphrase confirmed profile facts. They must not invent
qualifications, and job-ad requirements are not the applicant's skills.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from core.config import AppConfig, ExtractReview, QualificationsConfig
from core.licence_words import (
    ENGLISH_CLASS_WORDS,
    LICENCE_WORD_ALTERNATIVES,
)
from core.match_contract import section_confirmed
from core.text_normalize import clean_text

_CLAIM_TOKEN = re.compile(r"[A-Za-zÄÖÜäöüß][A-Za-zÄÖÜäöüß0-9+\-]{2,}")
# C1/B1/A2 are also language levels. A class counts only in a licence sentence.
# German compounds (Führerscheinklasse, Klassen, …) are enough. English
# „class“/„category“ count only together with licence/license in the same sentence.
_LICENCE_WORD_BODY: tuple[str, ...] = tuple(
    word for word in LICENCE_WORD_ALTERNATIVES if word not in ENGLISH_CLASS_WORDS and word != r"kl\."
)
_LICENCE_SENTENCE = re.compile(
    r"\b(?:" + "|".join(_LICENCE_WORD_BODY) + r")\b|\bkl\.",
    re.I,
)
_ENGLISH_CLASS_WORD = re.compile(
    r"\b(?:"
    + "|".join(word for word in LICENCE_WORD_ALTERNATIVES if word in ENGLISH_CLASS_WORDS)
    + r")\b",
    re.I,
)
_ENGLISH_LICENCE_WORD = re.compile(r"\blicen[cs]e\b", re.I)
_VEHICLE_LICENCE = re.compile(
    r"\b(?P<vehicle>lkw|lastwagen|truck|hgv|bus|motorrad|motorcycle|motorbike)"
    r"(?:[-\s]*)"
    r"(?:führerschein|fuehrerschein|fahrerlaubnis|(?:(?:driver(?:['’]s)?|driving)\s+)?licen[cs]e)\b|"
    r"\b(?:führerschein|fuehrerschein|fahrerlaubnis|(?:(?:driver(?:['’]s)?|driving)\s+)?licen[cs]e)"
    r"\s+(?:für|fuer|for)\s+(?:einen?\s+)?"
    r"(?P<after>lkw|lastwagen|truck|hgv|bus|motorrad|motorcycle|motorbike)\b",
    re.I,
)
_VEHICLE_LICENCE_CLASSES = {
    "lkw": frozenset({"C1", "C1E", "C", "CE"}),
    "bus": frozenset({"D1", "D1E", "D", "DE"}),
    "motorrad": frozenset({"A1", "A2", "A"}),
}


def _vehicle_licence_claims(sentence: str, allowed: frozenset[str]) -> list[str]:
    """Reject broad vehicle claims unless a fitting confirmed class exists."""
    unsupported: list[str] = []
    for match in _VEHICLE_LICENCE.finditer(sentence):
        vehicle = (match.group("vehicle") or match.group("after")).casefold()
        if vehicle in {"lastwagen", "truck", "hgv"}:
            vehicle = "lkw"
        elif vehicle in {"motorcycle", "motorbike"}:
            vehicle = "motorrad"
        if not (_VEHICLE_LICENCE_CLASSES[vehicle] & allowed):
            unsupported.append(match.group(0))
    return unsupported
# A newline always ends a sentence. Space after . ! ? ends it too, except when
# the period belongs to an abbreviation. ``\s`` is not used: it would swallow
# the newline and glue the next line to a class (``Klasse C.\nMit``).
_CLAIM_SENTENCE_BREAK = re.compile(r"[.!?][ \t]+|\n+")
_ABBREV_BEFORE_PERIOD = frozenset(
    {
        "jan",
        "feb",
        "febr",
        "mär",
        "maerz",
        "mrz",
        "apr",
        "mai",
        "jun",
        "juni",
        "jul",
        "juli",
        "aug",
        "sept",
        "sep",
        "okt",
        "nov",
        "dez",
        "nr",
        "kl",
        "ca",
        "bzw",
        "inkl",
        "evtl",
        "ggf",
        "usw",
        "dr",
        "str",
    }
)
_WORD_BEFORE_PERIOD = re.compile(r"[A-Za-zÄÖÜäöüß]+$")
_ORDINAL_BEFORE_PERIOD = re.compile(r"\d+$")
_WORD_AFTER_PERIOD = re.compile(r"[ \t]+([A-Za-zÄÖÜäöüß]+)")
# „u. a.“, „z. B.“, „d. h.“: letter, period, optional space, letter, period.
# The second letter may be uppercase (``z. B.``).
_LETTER_DOT_PAIR_AFTER = re.compile(r"[ \t]*[A-Za-zÄÖÜäöüß]\.")
_LETTER_DOT_PAIR_BEFORE = re.compile(r"[A-Za-zÄÖÜäöüß]\.[ \t]*[A-Za-zÄÖÜäöüß]$")
# A number keeps the sentence only when a month or a lowercase word follows.
_MONTH_AFTER_NUMBER = frozenset(
    {
        "januar",
        "jan",
        "februar",
        "feb",
        "febr",
        "märz",
        "maerz",
        "mär",
        "mrz",
        "april",
        "apr",
        "mai",
        "juni",
        "jun",
        "juli",
        "jul",
        "august",
        "aug",
        "september",
        "sept",
        "sep",
        "oktober",
        "okt",
        "november",
        "nov",
        "dezember",
        "dez",
    }
)
# A lowercase class counts only when a licence word stands directly before it.
_LOWER_CODE_AFTER_LICENCE_WORD = re.compile(
    r"(?:^|\W)(?:"
    r"führerscheinklassen|fuehrerscheinklassen|fahrerlaubnisklassen|"
    r"führerscheinklasse|fuehrerscheinklasse|fahrerlaubnisklasse|"
    r"führerschein|fuehrerschein|fahrerlaubnis|"
    r"klassen|klasse|"
    r"categories|category|classes|class|"
    r"licen[cs]es|licen[cs]e|"
    r"kl\."
    r")\s*:?\s*$",
    re.IGNORECASE,
)
_FIRST_PERSON = re.compile(
    r"\b(ich|meine|meiner|meinem|meinen|mir|mich|i|my|mine)\b",
    re.I,
)
_APPLICATION_SENTENCE = re.compile(
    r"bewerbe ich mich|ausgeschriebene position|persönlichen gespräch|"
    r"mit freundlichen grüßen|sehr geehrte",
    re.I,
)
_CREDENTIAL = re.compile(
    r"\b([A-Za-z0-9][A-Za-z0-9+\-]{2,})\s*-?\s*zertifikat\b|"
    r"\bzertifikat\s+([A-Za-z0-9][A-Za-z0-9+\-]{2,})\b|"
    r"\babschluss\s+als\s+([A-Za-zÄÖÜäöüß0-9+\-]{3,})\b|"
    r"\bausbildung\s+als\s+([A-Za-zÄÖÜäöüß0-9+\-]{3,})",
    re.I,
)
# „den Master in BWL abgeschlossen“ is a degree claim. The name has to sit
# in the same sentence as the completion, which the sentence splitter keeps
# together across „3.“ and „u. a.“.
_COMPLETED_DEGREE = re.compile(
    r"\b((?:master|bachelor|diplom|staatsexamen|promotion)"
    r"(?:\s+in\s+[A-Za-zÄÖÜäöüß0-9+\-]{2,})?)\b"
    r"(?=[^.!?\n]{0,40}\babgeschlossen\b)",
    re.I,
)
_METRIC = re.compile(
    r"\b\d+(?:[.,]\d+)?\s*(?:%|prozent)\b|\b\d+\s*jahre\b",
    re.I,
)
_EMPLOYER = re.compile(
    r"\b(?:bei|für|fuer|arbeitgeber)\s+([A-ZÄÖÜ][\w&.'\-]+(?:\s+[A-ZÄÖÜ][\w&.'\-]+){0,3})",
)

# Glue that must never count as a personal qualification.
_STOP = frozenset(
    {
        "ich",
        "meine",
        "meiner",
        "meinem",
        "meinen",
        "mir",
        "mich",
        "habe",
        "hat",
        "besitze",
        "bringe",
        "bringen",
        "insbesondere",
        "kenntnissen",
        "kenntnisse",
        "tätigkeit",
        "taetigkeit",
        "erfahrungen",
        "erfahrung",
        "praktische",
        "praktischen",
        "praktischer",
        "praktisches",
        "stelle",
        "relevanten",
        "relevante",
        "bisherigen",
        "beruflichen",
        "team",
        "gespräch",
        "gespraech",
        "möglichkeit",
        "moeglichkeit",
        "freundlichen",
        "grüßen",
        "gruesse",
        "position",
        "unternehmen",
        "gern",
        "gerne",
        "zählen",
        "zaehlen",
        "zählt",
        "fuer",
        "für",
        "und",
        "oder",
        "mit",
        "bei",
        "als",
        "ein",
        "eine",
        "einer",
        "einem",
        "eines",
        "der",
        "die",
        "das",
        "den",
        "dem",
        "des",
        "ihr",
        "ihre",
        "ihrem",
        "ihren",
        "über",
        "ueber",
        "aus",
        "von",
        "vom",
        "zum",
        "zur",
        "nicht",
        "auch",
        "sowie",
        "diese",
        "dieser",
        "dieses",
        "persönlichen",
        "persoenlichen",
        "freue",
        "sammle",
        "gesammelt",
        "zertifikat",
        "abschluss",
        "ausbildung",
        "jahre",
        "jahr",
        "fünf",
        "fuenf",
    }
)


# --- Anrede, Geschlecht, Muttersprache (Personaler, 18.10.2026) -------------
# A gendered noun the applicant uses for themself. The article (or „als“)
# before it ties the noun to the writer; „viele Bewerber“ stays untouched.
_GENDERED_SELF = re.compile(
    r"\b(?i:als|bin|sei|ein|eine|einen|einem|einer|der|die|den|dem|zum|zur)\s+"
    r"(?:[A-Za-zÄÖÜäöüß\-]+\s+){0,3}?"
    r"(?P<noun>Kandidatin|Kandidaten|Kandidat|Bewerberin|Bewerber|Fachfrau|Fachmann|"
    r"Muttersprachlerin|Muttersprachler)\b"
)
_FEMININE_SELF = frozenset({"kandidatin", "bewerberin", "fachfrau", "muttersprachlerin"})
_PROFILE_FEMALE = frozenset({"w", "f", "weiblich", "female", "frau"})
_PROFILE_MALE = frozenset({"m", "männlich", "maennlich", "male", "herr", "mann"})
# „Muttersprache“, „Muttersprachler(in)“, „muttersprachlich“, „native speaker“,
# „native German“, „mother tongue“, „first language“.
# Only the technical compounds „React Native“ and „cloud-native“ (space or
# hyphen) are not language claims. Every other „native“ still counts.
_NATIVE_CLAIM = re.compile(
    r"\bmuttersprach\w*|"
    r"(?<!react )(?<!react-)(?<!cloud )(?<!cloud-)\bnative\b|"
    # „cloud native speaker“, „React-Native speaker“ stay native claims.
    r"\bnative(?=[\s-]+speakers?\b)|"
    r"\bmother[\s-]+tongue\b|\bfirst\s+language\b|"
    # Kritiker/Teamlead #190: „Erstsprache“, „natively“; „zweisprachig“ and
    # „bilingual“ claim two native languages.
    r"\berstsprach\w*|\bnatively\b|\bzweisprachig\w*|\bbilingual\w*",
    re.I,
)
# Signals that claim two native languages: both must be named and native.
_TWO_NATIVE_CLAIM = re.compile(r"\bzweisprachig\w*|\bbilingual\w*", re.I)
_NATIVE_LEVEL = re.compile(
    # „Erstsprache“ as a profile level is not native (yet): letter side only,
    # Teamlead decides (UNSICHER in #190).
    r"muttersprach|\bnative\b|mother\s+tongue|\bfirst\s+language\b", re.I
)
# Profile side: near-native is C2, never native. A negation is never native.
_NEAR_NATIVE_LEVEL = re.compile(
    r"\b(?:nahezu|fast|annähernd|annaehernd|beinahe|quasi|near|almost|nearly)[\s-]*"
    r"(?:(?:wie|like)\s+(?:eine?\s+|a\s+)?)?(?:muttersprach\w*|native|erstsprach\w*)|"
    # „muttersprachenah“, „Muttersprachniveau“, „muttersprachliches Niveau“,
    # „native-like“, „native level“: a level, not a native language.
    r"muttersprach\w*?nah\b|muttersprach\w*?niveau\b|muttersprachliche[ns]?\s+niveau\b|"
    r"\bnative[\s-]*(?:like|level)\b|\bwie\s+(?:eine?\s+)?muttersprach\w*|"
    r"\blike\s+a\s+native\b",
    re.I,
)
_NEGATED_NATIVE_LEVEL = re.compile(
    r"\bnon[\s-]*native\b|\bnot\s+(?:a\s+)?native\b|\bno\s+native\b|"
    r"\bkeine?\s+(?:muttersprach\w*|native|erstsprach\w*)|"
    r"\bnicht\s+(?:muttersprach\w*|native|erstsprach\w*)|"
    # „Muttersprache: nein“, „native: no“
    r"(?:muttersprach\w*|native|erstsprach\w*)\s*[:=\-–]?\s*(?:nein|no|false)\b",
    re.I,
)
_C2_LEVEL = re.compile(r"\bc2\b", re.I)
# The only level statements a C2 profile carries („auf muttersprachlichem
# Niveau“, „muttersprachliche (Deutsch)kenntnisse“). Never a native claim.
_NATIVE_LEVEL_PHRASE = re.compile(
    r"\bauf\s+muttersprachliche[mn]?\s+niveau\b|"
    r"\bmuttersprachliche[mnrs]?\s+niveau\b|"
    r"\bmuttersprachliche[mnrs]?\s+[a-zäöüß]*kenntnisse[n]?\b",
    re.I,
)


def _level_class(level: str) -> str:
    """``native``, ``c2`` or ``other`` for one profile language level."""
    text = clean_text(level or "")
    # A negation first: it never counts as native, nor as an approximation.
    if _NEGATED_NATIVE_LEVEL.search(text):
        return "c2" if _C2_LEVEL.search(text) else "other"
    if _NEAR_NATIVE_LEVEL.search(text):
        return "c2"
    if _NATIVE_LEVEL.search(text):
        return "native"
    if _C2_LEVEL.search(text):
        return "c2"
    return "other"
# Closed alias list: German and English names of one language map to one key.
_LANGUAGE_ALIASES: dict[str, tuple[str, ...]] = {
    "deutsch": ("deutsch", "german"),
    "englisch": ("englisch", "english"),
    "französisch": ("französisch", "franzoesisch", "french"),
    "spanisch": ("spanisch", "spanish"),
    "italienisch": ("italienisch", "italian"),
    "polnisch": ("polnisch", "polish"),
    "türkisch": ("türkisch", "tuerkisch", "turkish"),
    "russisch": ("russisch", "russian"),
    "ukrainisch": ("ukrainisch", "ukrainian"),
    "arabisch": ("arabisch", "arabic"),
    "niederländisch": ("niederländisch", "niederlaendisch", "dutch"),
    "portugiesisch": ("portugiesisch", "portuguese"),
    "rumänisch": ("rumänisch", "rumaenisch", "romanian"),
    "tschechisch": ("tschechisch", "czech"),
    "ungarisch": ("ungarisch", "hungarian"),
    "griechisch": ("griechisch", "greek"),
    "kroatisch": ("kroatisch", "croatian"),
    "serbisch": ("serbisch", "serbian"),
    "chinesisch": ("chinesisch", "chinese"),
    "japanisch": ("japanisch", "japanese"),
    "albanisch": ("albanisch", "albanian"),
    "bosnisch": ("bosnisch", "bosnian"),
    "bulgarisch": ("bulgarisch", "bulgarian"),
    "dänisch": ("dänisch", "daenisch", "danish"),
    "finnisch": ("finnisch", "finnish"),
    "schwedisch": ("schwedisch", "swedish"),
    "norwegisch": ("norwegisch", "norwegian"),
    "slowakisch": ("slowakisch", "slovak"),
    "slowenisch": ("slowenisch", "slovenian", "slovene"),
    "litauisch": ("litauisch", "lithuanian"),
    "lettisch": ("lettisch", "latvian"),
    "estnisch": ("estnisch", "estonian"),
    "mazedonisch": ("mazedonisch", "makedonisch", "macedonian"),
    "persisch": ("persisch", "farsi", "persian"),
    "dari": ("dari",),
    "paschtu": ("paschtu", "pashto"),
    "kurdisch": ("kurdisch", "kurdish"),
    "hebräisch": ("hebräisch", "hebraeisch", "hebrew"),
    "hindi": ("hindi",),
    "urdu": ("urdu",),
    "bengalisch": ("bengalisch", "bengali"),
    "tamil": ("tamil",),
    "vietnamesisch": ("vietnamesisch", "vietnamese"),
    "koreanisch": ("koreanisch", "korean"),
    "thai": ("thai",),
    "indonesisch": ("indonesisch", "indonesian"),
    "malaiisch": ("malaiisch", "malay"),
    "tagalog": ("tagalog", "filipino"),
    "georgisch": ("georgisch", "georgian"),
    "armenisch": ("armenisch", "armenian"),
    "aserbaidschanisch": ("aserbaidschanisch", "azerbaijani"),
    "kasachisch": ("kasachisch", "kazakh"),
    "usbekisch": ("usbekisch", "uzbek"),
    "belarussisch": ("belarussisch", "weißrussisch", "belarusian"),
    "amharisch": ("amharisch", "amharic"),
    "tigrinya": ("tigrinya", "tigrinisch"),
    "somali": ("somali", "somalisch"),
    "swahili": ("swahili", "suaheli"),
    "katalanisch": ("katalanisch", "catalan"),
    "isländisch": ("isländisch", "islaendisch", "icelandic"),
    "irisch": ("irisch", "irish"),
    "luxemburgisch": ("luxemburgisch", "luxembourgish"),
}
# A word the claim names as the language, also outside the closed list
# („Meine Muttersprache ist Kurmandschi“). Capitalised words only.
_NAMED_NATIVE = (
    re.compile(
        r"(?i:muttersprachen?|erstsprachen?|mother\s+tongue|first\s+language|native\s+language)"
        r"\s+(?i:ist|sind|is|are|:)?\s*(?P<lang>[A-ZÄÖÜ][a-zäöüß\-]+)"
    ),
    re.compile(
        r"(?P<lang>[A-ZÄÖÜ][a-zäöüß\-]+)\s+(?i:ist|is)\s+(?i:meine|my)\s+"
        r"(?i:muttersprache|erstsprache|mother\s+tongue|first\s+language|native\s+language)"
    ),
    re.compile(
        r"(?i:muttersprachler(?:in)?|muttersprachlich\w*|native\s+speaker)\s+"
        r"(?:(?i:in|für|fuer|of|im|auf)\s+)?(?P<lang>[A-ZÄÖÜ][a-zäöüß\-]+)"
    ),
    re.compile(r"(?i:native)\s+(?P<lang>[A-ZÄÖÜ][a-zäöüß\-]+)\s+(?i:speaker)"),
)
_NOT_A_LANGUAGE = frozenset(
    {
        "das", "dies", "diese", "dieses", "sie", "es", "er", "the", "it", "this", "that",
        "niveau", "kenntnisse", "kenntnissen", "level",
    }
)
_COMPOUND_TAIL = re.compile(r"(?:sprach)?kenntnisse[n]?$")


def _profile_language_alias(token: str, profile_languages: frozenset[str]) -> bool:
    """``German`` is confirmed when the profile has ``Deutsch`` (and vice versa).

    Only a name from the closed alias list, and only for a language the
    confirmed profile actually lists. Level and native status are not implied.
    """
    folded = token.casefold()
    for key, aliases in _LANGUAGE_ALIASES.items():
        if folded in aliases:
            return key in profile_languages
    return False


def _named_native_languages(clause: str) -> list[str]:
    keys: list[str] = []
    for pattern in _NAMED_NATIVE:
        for match in pattern.finditer(clause):
            word = match.group("lang")
            if word.casefold() in _NOT_A_LANGUAGE:
                continue
            keys.append(_compound_language_key(word))
    return keys


# Inflected German adjective of a closed-list language: „deutscher
# Muttersprachler“, „deutsche Muttersprache“ → ``deutsch``.
_ADJECTIVE_ENDING = re.compile(r"e[mnrs]?")


def _compound_language_key(word: str) -> str:
    """``Deutschkenntnisse``/``deutscher`` → ``deutsch``; else via ``_language_key``."""
    folded = word.casefold()
    for key, aliases in _LANGUAGE_ALIASES.items():
        for alias in aliases:
            if not folded.startswith(alias):
                continue
            tail = folded[len(alias):]
            if _COMPOUND_TAIL.fullmatch(tail):
                return key
            if alias.endswith("sch") and _ADJECTIVE_ENDING.fullmatch(tail):
                return key
    return _language_key(word)


def _language_key(name: str) -> str:
    folded = clean_text(name or "").casefold().strip()
    for key, aliases in _LANGUAGE_ALIASES.items():
        if folded in aliases:
            return key
    return folded


def _languages_in(text: str, extra: frozenset[str]) -> list[tuple[int, str]]:
    """(position, language key) for every language word in ``text``.

    A language word also counts as the head of a compound
    (``Deutschkenntnisse``), never in the middle of a word.
    """
    found: list[tuple[int, str]] = []
    folded = text.casefold()
    names = {alias: key for key, aliases in _LANGUAGE_ALIASES.items() for alias in aliases}
    for key in extra:
        names.setdefault(key, key)
    for alias, key in names.items():
        if len(alias) < 3:
            continue
        for match in re.finditer(rf"(?<!\w){re.escape(alias)}", folded):
            found.append((match.start(), key))
    return sorted(found)


def _norm_salutation(line: str) -> str:
    return re.sub(r"\s+", " ", (line or "").casefold()).strip().rstrip(",;:!. ")


_SALUTATION_LINE = re.compile(
    r"^(?:sehr\s+geehrte[rn]?|guten\s+tag|hallo|liebe|lieber|moin|servus|dear|hello)\b",
    re.I,
)


def _salutation_violations(letter: str, expected: str) -> list[str]:
    """The salutation line must be exactly the one built from the ad.

    The salutation is the first line that opens like one, so an address
    header from a custom template does not count. No salutation at all is
    a finding too.
    """
    if not expected:
        return []
    lines = [line.strip() for line in (letter or "").splitlines() if line.strip()]
    found = next((line for line in lines if _SALUTATION_LINE.match(line)), "")
    if found and _norm_salutation(found) == _norm_salutation(expected):
        return []
    return [found or "(keine Anrede)"]


def _gender_violation(sentence: str, gender: str) -> bool:
    if not _FIRST_PERSON.search(sentence):
        return False
    stated = (gender or "").strip().casefold()
    for match in _GENDERED_SELF.finditer(sentence):
        feminine = match.group("noun").casefold() in _FEMININE_SELF
        if stated in _PROFILE_FEMALE and feminine:
            continue
        if stated in _PROFILE_MALE and not feminine:
            continue
        # Unstated gender: every gendered self-description fails. The first
        # name is never evidence.
        return True
    return False


_CLAUSE_SPLIT = re.compile(r"[,;]")
_CLAUSE_TOKEN = re.compile(r"[A-Za-zÄÖÜäöüß][A-Za-zÄÖÜäöüß0-9\-]*")
# Words a walk from a native marker steps over to reach the language.
_NATIVE_WALK = frozenset(
    {
        "als", "ist", "sind", "bin", "ich", "spreche", "sprechen", "spricht",
        "meine", "mein", "meiner", "meinem", "meinen", "my", "is", "are", "am",
        "a", "an", "the", "i", "ebenfalls", "auch", "eigentlich", "tatsächlich",
        "tatsaechlich", "wirklich", "also", "too", "in", "im", "für", "fuer",
        "of", "auf", "speaker", "speakers", "language", "languages", "sprache",
        "sprachen", "und", "and",
    }
)
# Words in a native-marker clause that are never a language. Everything
# else in that clause is a possible language and must be allowed.
_NOT_A_LANGUAGE_IN_CLAUSE = _STOP | _NATIVE_WALK | frozenset(
    {
        "mich", "mir", "hiermit", "über", "ueber", "niveau", "kenntnisse",
        "kenntnissen", "sprachkenntnisse", "level", "verfüge", "verfuege",
        "bewerbe", "react", "cloud", "mother", "tongue", "first",
        "ausgeschriebene", "ausgeschriebenen", "aufgewachsen", "speak", "speaks",
        "with", "both", "beide", "beiden", "sowohl",
    }
)
# The marker words themselves (also the English parts of a marker phrase).
_NATIVE_MARKER_WORD = re.compile(
    r"(?:muttersprach\w*|erstsprach\w*|zweisprachig\w*|bilingual\w*|natively|native|"
    r"mother|tongue|first|languages?|speakers?)",
    re.I,
)
# A negation in a native-marker clause is a finding of its own
# („Meine Muttersprache ist nicht Deutsch sondern Kurmandschi“).
_CLAUSE_NEGATION = frozenset(
    {"nicht", "kein", "keine", "keiner", "keinen", "keinem", "not", "no", "non", "never", "nie"}
)


def _clause_native_violation(
    clause: str, native: frozenset[str], known: frozenset[str], level_ok: frozenset[str]
) -> bool:
    """One clause with a native marker, checked on its own (fail-closed).

    The clause needs a recognisable language that the profile allows, and
    every word of the clause that is not glue or the marker itself counts as
    a possible language: it must be an allowed language. An enumeration
    („Deutsch und Kurmandschi“), a stop word before the language („das
    Kurmandschi“) and an unknown word are all findings. So is a negation.
    """
    strong = [
        (m.start(), m.end())
        for m in _NATIVE_CLAIM.finditer(
            _NATIVE_LEVEL_PHRASE.sub(lambda m: " " * len(m.group(0)), clause)
        )
    ]
    level = [(m.start(), m.end()) for m in _NATIVE_LEVEL_PHRASE.finditer(clause)]
    if not strong and not level:
        return False
    allowed = native if strong else level_ok
    langs = {key for _pos, key in _languages_in(clause, known)}
    langs.update(_named_native_languages(clause))
    if not langs or any(key not in allowed for key in langs):
        return True
    for match in _CLAUSE_TOKEN.finditer(clause):
        word = match.group(0)
        folded = word.casefold()
        if folded in _CLAUSE_NEGATION:
            return True
        if any(ch.isdigit() for ch in word) or folded in _NOT_A_LANGUAGE_IN_CLAUSE:
            continue
        if _NATIVE_MARKER_WORD.fullmatch(word):
            continue
        if _compound_language_key(word) not in allowed:
            return True
    return False


def _native_violation(
    sentence: str,
    native: frozenset[str],
    known: frozenset[str],
    level_ok: frozenset[str] = frozenset(),
) -> bool:
    """Fail-closed at sentence level.

    A sentence with a native signal (Muttersprache, muttersprachlich,
    Muttersprachler/in, native, mother tongue, first language) must name at
    least one language, and every language it names (closed list, or the
    word a claim pattern names) must be a native profile language. No
    identifiable language is a finding.

    Only exception: when the sole signals are level phrases („auf
    muttersprachlichem Niveau“, „muttersprachliche Deutschkenntnisse“),
    every named language must be in the profile at C2 or native.
    """
    if not _NATIVE_CLAIM.search(sentence):
        return False
    rest = _NATIVE_LEVEL_PHRASE.sub(lambda m: " " * len(m.group(0)), sentence)
    strong = _NATIVE_CLAIM.search(rest) is not None
    langs = {key for _pos, key in _languages_in(sentence, known)}
    langs.update(_named_native_languages(sentence))
    if not langs:
        return True
    allowed = native if strong else level_ok
    if any(key not in allowed for key in langs):
        return True
    # „zweisprachig“/„bilingual“: two native languages, both named.
    if _TWO_NATIVE_CLAIM.search(sentence) and len(langs) < 2:
        return True
    # Each clause with a marker on its own: „…, Kurmandschi spreche ich
    # ebenfalls muttersprachlich“ is a finding next to an allowed language.
    return any(
        _clause_native_violation(part, native, known, level_ok)
        for part in _CLAUSE_SPLIT.split(sentence)
    )


@dataclass
class ClaimScreen:
    ok: bool = True
    violations: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PreparedCoverCheck:
    """Profile side of one preview, fixed for the life of the dialog.

    Confirmed classes, employers, degrees and the normalized evidence are
    computed once. A letter scan reads only these fields and the letter.
    """

    confirmed_norm: str
    job_norm: str
    licence_codes: frozenset[str]
    employers: tuple[str, ...]
    degrees: tuple[str, ...]
    # Salutation ``compose_cover_letter`` builds from one named ad contact.
    # Empty: no contact, two contacts, or an English ad.
    expected_salutation: str = ""
    # Only an explicit profile statement. Empty means unknown, never inferred.
    applicant_gender: str = ""
    # Language keys the confirmed languages section marks as native.
    native_languages: frozenset[str] = frozenset()
    # Every confirmed profile language (so a custom name is still recognised).
    profile_languages: frozenset[str] = frozenset()
    # Languages at C2 or native (C2 includes near-native); level phrases only.
    level_languages: frozenset[str] = frozenset()


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").casefold()).strip()


def _supported(token: str, confirmed_norm: str) -> bool:
    tok = token.casefold()
    if len(tok) < 3 or tok in _STOP:
        return True
    if tok in confirmed_norm:
        return True
    # Paraphrase: shared stem with a confirmed fact (Steuerfach ↔ Steuerfachangestellte).
    for fact in re.findall(r"[a-zäöüß0-9+\-]{4,}", confirmed_norm):
        if len(tok) >= 5 and (tok.startswith(fact) or fact.startswith(tok)):
            return True
        if len(tok) >= 5 and len(fact) >= 5 and (tok in fact or fact in tok):
            return True
    return False


def _word_after_period(text: str, dot: int) -> str:
    match = _WORD_AFTER_PERIOD.match(text, dot + 1)
    if match is None:
        return ""
    return match.group(1)


def _number_keeps_sentence(text: str, dot: int) -> bool:
    """``1. März`` and ``3. größten`` stay. ``2031. Gerne`` splits."""
    word = _word_after_period(text, dot)
    if not word:
        return False
    if word.casefold() in _MONTH_AFTER_NUMBER:
        return True
    return word[:1].islower()


# Only the tail before a period matters. Scanning the whole letter on every
# dot would be quadratic on a page of abbreviations.
_PERIOD_LOOKBACK = 40


def _single_letter_keeps_sentence(text: str, dot: int) -> bool:
    """Keep only ``u. a.`` / ``z. B.`` / ``d. h.``. ``Klasse C. Hiermit`` splits."""
    if _LETTER_DOT_PAIR_AFTER.match(text, dot + 1):
        return True
    tail = text[max(0, dot - _PERIOD_LOOKBACK) : dot]
    return _LETTER_DOT_PAIR_BEFORE.search(tail) is not None


def _period_keeps_sentence(text: str, dot: int) -> bool:
    """True when this period belongs to an abbreviation, not a sentence end."""
    before = text[max(0, dot - _PERIOD_LOOKBACK) : dot]
    if _ORDINAL_BEFORE_PERIOD.search(before):
        return _number_keeps_sentence(text, dot)
    word = _WORD_BEFORE_PERIOD.search(before)
    if word is None:
        return False
    token = word.group(0)
    if len(token) == 1:
        return _single_letter_keeps_sentence(text, dot)
    return token.casefold() in _ABBREV_BEFORE_PERIOD


def _split_claim_sentences(letter: str) -> list[str]:
    """Split a letter into sentences. Abbreviations stay in the same sentence."""
    text = letter or ""
    sentences: list[str] = []
    start = 0
    for match in _CLAIM_SENTENCE_BREAK.finditer(text):
        mark = match.start()
        # A newline always separates, even after a class or an abbreviation.
        if text[mark] != "\n" and text[mark] == "." and _period_keeps_sentence(text, mark):
            continue
        end = mark if text[mark] == "\n" else mark + 1
        chunk = text[start:end].strip()
        if chunk:
            sentences.append(chunk)
        start = match.end()
    tail = text[start:].strip()
    if tail:
        sentences.append(tail)
    return sentences


def _licence_codes_in_sentence(sentence: str) -> list[str]:
    """Class codes a licence sentence may claim.

    The scan is :func:`core.cv_parser._iter_licence_classes`. An uppercase
    code counts anywhere in the sentence. A lowercase code counts only
    directly after a licence word (``Klasse b``, ``Führerschein c``,
    ``class b``). ``am`` is therefore not class AM, and the article ``a``
    is not class A.
    """
    from core.cv_parser import _iter_licence_classes

    codes: list[str] = []
    for start, code in _iter_licence_classes(sentence):
        span = sentence[start : start + len(code)]
        letters = [char for char in span if char.isalpha()]
        upper = bool(letters) and all(char.isupper() for char in letters)
        if not upper and _LOWER_CODE_AFTER_LICENCE_WORD.search(sentence[:start]) is None:
            continue
        codes.append(code)
    return codes


def _is_licence_sentence(sentence: str) -> bool:
    """True when this sentence may name a driving-licence class.

    ``class`` and ``category`` do not count on their own. They count when the
    same sentence also contains ``licence`` or ``license``.
    """
    if _LICENCE_SENTENCE.search(sentence) or _VEHICLE_LICENCE.search(sentence):
        return True
    return bool(
        _ENGLISH_CLASS_WORD.search(sentence) and _ENGLISH_LICENCE_WORD.search(sentence)
    )


def _in_job(token: str, job_norm: str) -> bool:
    tok = token.casefold()
    if len(tok) < 3:
        return False
    return bool(re.search(rf"(?<!\w){re.escape(tok)}(?!\w)", job_norm))


def confirmed_licence_codes(config: AppConfig) -> set[str]:
    """Classes a letter may claim.

    The value is ``read_driving_classes(qualifications.driving_license).evidence``,
    read as a leading class (``CE 95`` → ``CE``), and only when the driving
    licence section is confirmed. Name, skills, software, education and
    experience stay in the profile text and are not split into classes.
    """
    from core.cv_parser import leading_driving_class, read_driving_classes

    review = getattr(config.profile, "extract_review", None)
    if not section_confirmed(review, "driving_license"):
        return set()
    found: set[str] = set()
    for item in read_driving_classes(config.profile.qualifications.driving_license).evidence:
        code = leading_driving_class(str(item))
        if code:
            found.add(code)
    return found


def _fact_supported(token: str, names: tuple[str, ...], confirmed_norm: str) -> bool:
    """Employers and degrees were fixed when the profile side was prepared."""
    if _supported(token, confirmed_norm):
        return True
    folded = token.casefold()
    return any(folded == name.casefold() for name in names)


def _claims_in_prepared_letter(letter: str, prepared: PreparedCoverCheck) -> list[str]:
    """Scan the letter only. ``prepared`` is not rebuilt here."""
    violations: list[str] = []
    seen: set[str] = set()
    for line in _salutation_violations(letter, prepared.expected_salutation):
        seen.add(line.casefold())
        violations.append(line)
    for sentence in _split_claim_sentences(letter):
        # Native and gender run on every sentence. The application-sentence
        # skip below covers only the older claim checks; „Hiermit bewerbe ich
        # mich als ideale Kandidatin …“ is still a finding.
        if _native_violation(
            sentence,
            prepared.native_languages,
            prepared.profile_languages,
            prepared.level_languages,
        ) or _gender_violation(sentence, prepared.applicant_gender):
            key = sentence.casefold()
            if key not in seen:
                seen.add(key)
                violations.append(sentence)
            continue
        if _APPLICATION_SENTENCE.search(sentence):
            continue
        if not _FIRST_PERSON.search(sentence):
            continue
        flagged: list[str] = []
        for match in _CREDENTIAL.finditer(sentence):
            name = next((g for g in match.groups() if g), "")
            if name and not _supported(name, prepared.confirmed_norm):
                flagged.append(name)
        for match in _COMPLETED_DEGREE.finditer(sentence):
            name = match.group(1)
            if name and not _fact_supported(name, prepared.degrees, prepared.confirmed_norm):
                flagged.append(name)
        for match in _METRIC.finditer(sentence):
            snippet = match.group(0)
            if snippet.casefold() not in prepared.confirmed_norm:
                flagged.append(snippet)
        for match in _EMPLOYER.finditer(sentence):
            employer = match.group(1).strip()
            if employer and not _fact_supported(
                employer, prepared.employers, prepared.confirmed_norm
            ):
                flagged.append(employer)
        if _is_licence_sentence(sentence):
            for code in _licence_codes_in_sentence(sentence):
                if code not in prepared.licence_codes:
                    flagged.append(code)
            flagged.extend(_vehicle_licence_claims(sentence, prepared.licence_codes))
        for token in _CLAIM_TOKEN.findall(sentence):
            if token.casefold() in _STOP:
                continue
            if not _in_job(token, prepared.job_norm):
                continue
            if _supported(token, prepared.confirmed_norm):
                continue
            if _profile_language_alias(token, prepared.profile_languages):
                continue
            flagged.append(token)
        if flagged:
            key = sentence.casefold()
            if key not in seen:
                seen.add(key)
                violations.append(sentence)
    return violations


def find_unsubstantiated_personal_claims(
    letter: str,
    *,
    confirmed_text: str,
    job_text: str,
    allowed_context: str = "",
    confirmed_licences: set[str] | None = None,
    native_languages: frozenset[str] = frozenset(),
    profile_languages: frozenset[str] = frozenset(),
    level_languages: frozenset[str] = frozenset(),
    applicant_gender: str = "",
) -> list[str]:
    """Return personal claim snippets that are not backed by confirmed facts.

    Job-ad tokens used as if they were the applicant's qualifications are
    violations. The application sentence (title/company) is not a personal claim.
    Licence classes come only from ``confirmed_licences``, never from scanning
    ``confirmed_text``. The native and gender rules use the profile languages
    and gender passed here; without them every native claim and every
    gendered self-description is a finding (fail-closed).
    """
    prepared = PreparedCoverCheck(
        confirmed_norm=_norm(f"{confirmed_text} {allowed_context}"),
        job_norm=_norm(job_text),
        licence_codes=frozenset(code.upper() for code in (confirmed_licences or ())),
        employers=(),
        degrees=(),
        applicant_gender=applicant_gender,
        native_languages=frozenset(native_languages),
        profile_languages=frozenset(profile_languages),
        level_languages=frozenset(level_languages),
    )
    return _claims_in_prepared_letter(letter, prepared)


def screen_cover_letter(
    letter: str,
    *,
    confirmed_text: str,
    job_text: str,
    allowed_context: str = "",
    confirmed_licences: set[str] | None = None,
    native_languages: frozenset[str] = frozenset(),
    profile_languages: frozenset[str] = frozenset(),
    level_languages: frozenset[str] = frozenset(),
    applicant_gender: str = "",
) -> ClaimScreen:
    violations = find_unsubstantiated_personal_claims(
        letter,
        confirmed_text=confirmed_text,
        job_text=job_text,
        allowed_context=allowed_context,
        confirmed_licences=confirmed_licences,
        native_languages=native_languages,
        profile_languages=profile_languages,
        level_languages=level_languages,
        applicant_gender=applicant_gender,
    )
    return ClaimScreen(ok=not violations, violations=violations)


def screen_prepared_letter(letter: str, prepared: PreparedCoverCheck) -> ClaimScreen:
    """Guard one letter against a profile side that was built earlier."""
    violations = _claims_in_prepared_letter(letter, prepared)
    return ClaimScreen(ok=not violations, violations=violations)


def unconfirmed_licence_codes(
    letter: str,
    *,
    confirmed_licences: set[str] | None = None,
) -> list[str]:
    """Class codes a personal licence sentence claims beyond the profile.

    Order follows the letter. The same sentence split as
    :func:`find_unsubstantiated_personal_claims` decides where a class sits.
    """
    allowed = {code.upper() for code in (confirmed_licences or ())}
    found: list[str] = []
    seen: set[str] = set()
    for sentence in _split_claim_sentences(letter):
        if _APPLICATION_SENTENCE.search(sentence):
            continue
        if not _FIRST_PERSON.search(sentence):
            continue
        if not _is_licence_sentence(sentence):
            continue
        for code in _licence_codes_in_sentence(sentence):
            if code in allowed or code in seen:
                continue
            seen.add(code)
            found.append(code)
    return found


def _entry_text(entry: object) -> str:
    parts: list[str] = []
    label = getattr(entry, "label", None)
    if callable(label):
        text = clean_text(label())
        if text:
            parts.append(text)
    if not parts:
        for attr in (
            "value",
            "title",
            "company",
            "qualification",
            "institution",
            "name",
            "language",
            "level",
        ):
            parts.append(clean_text(getattr(entry, attr, "")))
    responsibilities = getattr(entry, "responsibilities", None) or []
    parts.extend(clean_text(item) for item in responsibilities)
    return " ".join(part for part in parts if part)


def confirmed_profile_text(config: AppConfig) -> str:
    """Facts the cover letter may paraphrase. Unconfirmed CV extracts are omitted."""
    quals: QualificationsConfig = config.profile.qualifications
    review: ExtractReview | None = getattr(config.profile, "extract_review", None)
    chunks: list[str] = []
    app = config.application
    for attr in ("full_name", "first_name", "last_name"):
        value = getattr(app, attr, "")
        if callable(value):
            value = value()
        text = clean_text(value)
        if text:
            chunks.append(text)
    sections = {
        "skills": quals.skills,
        "software": quals.software,
        "languages": quals.languages,
        "education": quals.education,
        "work_experience": quals.work_experience,
        "certificates": quals.certificates,
        "driving_license": quals.driving_license,
    }
    from core.cv_employment_evidence import with_source_duties

    sections["work_experience"] = with_source_duties(
        quals.work_experience or [], str(getattr(app, "cv_source_text", "") or ""),
        cv_import=getattr(review, "source", "") == "cv",
    )
    for name, entries in sections.items():
        if not section_confirmed(review, name):
            continue
        if name == "driving_license":
            from core.cv_parser import read_driving_classes

            # Recovered classes (BE from [B, E]) are not evidence. A class the
            # stored list already spells out is. Confirmation does not change that.
            for code in read_driving_classes(entries).evidence:
                text = clean_text(code)
                if text:
                    chunks.append(text)
            continue
        for entry in entries or []:
            if (getattr(entry, "source", "") or "").strip().lower() == "cv" and not section_confirmed(
                review, name
            ):
                continue
            text = _entry_text(entry)
            if text:
                chunks.append(text)
    return "\n".join(chunks)


def _confirmed_field(config: AppConfig, section: str, attr: str) -> tuple[str, ...]:
    """Named facts from one confirmed section. Unconfirmed sections contribute nothing."""
    review = getattr(config.profile, "extract_review", None)
    if not section_confirmed(review, section):
        return ()
    entries = getattr(config.profile.qualifications, section, None) or []
    names: list[str] = []
    for entry in entries:
        text = clean_text(getattr(entry, attr, "") or "")
        if text:
            names.append(text)
    return tuple(names)


# „Deutsch (Muttersprache)“ in the language-name field: the name before the
# parenthesis is the language, the parenthesis is a level statement.
_LANGUAGE_FIELD_NOTE = re.compile(r"^(?P<name>[^()]+?)\s*\((?P<note>[^()]*)\)\s*$")
_LEVEL_RANK = {"other": 0, "c2": 1, "native": 2}
_CEFR_CODE = re.compile(r"\b[abc][12]\b", re.I)


def _split_language_field(value: str) -> tuple[str, str]:
    text = clean_text(value or "").strip()
    match = _LANGUAGE_FIELD_NOTE.match(text)
    if not match:
        return text, ""
    return match.group("name").strip(), match.group("note").strip()


def _entry_level_class(level: str, note: str) -> str:
    """Level field and name parenthesis together; on conflict the lower class wins.

    A parenthesis that is no level statement („Englisch (US)“) is ignored.
    """
    parts = [level]
    if _level_class(note) != "other" or _NEGATED_NATIVE_LEVEL.search(note) or _CEFR_CODE.search(note):
        parts.append(note)
    kinds = [_level_class(part) for part in parts if part.strip()]
    if not kinds:
        return "other"
    return min(kinds, key=_LEVEL_RANK.__getitem__)


def _confirmed_languages(
    config: AppConfig,
) -> tuple[frozenset[str], frozenset[str], frozenset[str]]:
    """(native, all, C2-or-native) keys from the confirmed languages section only."""
    review = getattr(config.profile, "extract_review", None)
    if not section_confirmed(review, "languages"):
        return frozenset(), frozenset(), frozenset()
    native: set[str] = set()
    known: set[str] = set()
    level_ok: set[str] = set()
    for entry in getattr(config.profile.qualifications, "languages", None) or []:
        name, note = _split_language_field(getattr(entry, "language", "") or "")
        key = _language_key(name)
        if not key:
            continue
        known.add(key)
        kind = _entry_level_class(getattr(entry, "level", "") or "", note)
        if kind == "native":
            native.add(key)
        if kind in {"native", "c2"}:
            level_ok.add(key)
    return frozenset(native), frozenset(known), frozenset(level_ok)


def _expected_salutation(job_text: str) -> str:
    """Same rule as ``compose_cover_letter``: German ad, one named contact."""
    from core.cover_letter import _ad_language, _greeting_from_ad

    text = job_text or ""
    if _ad_language(text) != "de":
        return ""
    return _greeting_from_ad(text)


def prepare_cover_check(
    config: AppConfig,
    job_text: str,
    allowed_context: str = "",
    *,
    applicant_gender: str = "",
) -> PreparedCoverCheck:
    """Build the profile side once. Later scans pass the letter only.

    ``applicant_gender`` is only an explicit profile statement. The profile
    has no such field today, so callers pass nothing and every gendered
    self-description is a finding. A first name is never used.
    """
    confirmed = confirmed_profile_text(config)
    native, known, level_ok = _confirmed_languages(config)
    return PreparedCoverCheck(
        confirmed_norm=_norm(f"{confirmed} {allowed_context}"),
        job_norm=_norm(job_text),
        licence_codes=frozenset(code.upper() for code in confirmed_licence_codes(config)),
        employers=_confirmed_field(config, "work_experience", "company"),
        degrees=_confirmed_field(config, "education", "qualification"),
        expected_salutation=_expected_salutation(job_text),
        applicant_gender=applicant_gender,
        native_languages=native,
        profile_languages=known,
        level_languages=level_ok,
    )
