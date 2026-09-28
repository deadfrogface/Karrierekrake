"""Licence words shared by the parser, ``read_driving_classes`` and the guard.

The order is the parser's match order. A longer compound stands before the
stem it contains, and the English forms are the ones the parser already
accepts in front of a class. Matching reads classes through
``read_driving_classes``, which uses this list.
"""

from __future__ import annotations

# One list. ``cv_parser.leading_driving_class`` and the cover-letter guard
# both import it. Do not reorder: the prefix match depends on this sequence.
LICENCE_WORD_ALTERNATIVES: tuple[str, ...] = (
    r"driving\s+licen[cs]e",
    r"driver['\u2019]s\s+licen[cs]e",
    r"führerscheinklassen",
    r"fuehrerscheinklassen",
    r"fahrerlaubnisklassen",
    r"führerscheinklasse",
    r"fuehrerscheinklasse",
    r"fahrerlaubnisklasse",
    r"führerschein",
    r"fuehrerschein",
    r"fahrerlaubnis",
    r"klassen",
    r"category",
    r"categories",
    r"class",
    r"classes",
    r"klasse",
    r"kl\.",
)

# English „class“ / „category“ name a licence class only together with
# licence/license. They stay in the shared list for the parser.
ENGLISH_CLASS_WORDS: frozenset[str] = frozenset(
    {
        r"category",
        r"categories",
        r"class",
        r"classes",
    }
)

LICENCE_WORD_GROUP: str = "(?:" + "|".join(LICENCE_WORD_ALTERNATIVES) + ")"

# Same prefix the parser used before the list moved here, including
# „der“/„die“ and the colon.
LEADING_CLASS_PREFIX_PATTERN: str = (
    LICENCE_WORD_GROUP + r"(?:\s+(?:der|die))?(?:\s*:\s*|\s+)"
)
