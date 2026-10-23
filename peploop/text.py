"""Normalise text before two pieces of it are compared.

Reach for this instead of writing a lane's own `_norm`. Each function says
how much it forgives. A comparison that forgives too little rejects honest
quoting. One that forgives too much matches what was never said.
"""

import re
import unicodedata

from normality import ascii_text

WHITESPACE = re.compile(r"\s+")


def squash(text: str) -> str:
    """Collapse whitespace and control characters to single spaces, and trim.

    The reduction that turns an article into prompt text is the one thing a
    model's copy of a passage can honestly differ by.
    """
    text = "".join(" " if unicodedata.category(ch) == "Cc" else ch for ch in text)
    return WHITESPACE.sub(" ", text).strip()


def fold(text: str) -> str:
    """Casefolded ASCII, so a diacritic or a script cannot break a comparison.

    For matching names across languages: transliterates rather than strips,
    so "Москва" and "Moskva" meet. Two Cyrillic languages' spellings may meet
    too, so a key that must keep them apart uses `strip_marks`.
    """
    return (ascii_text(text) or "").casefold()


def strip_marks(text: str) -> str:
    """Casefolded, with diacritics removed and the script kept.

    "Río" meets "Rio" and "Ä" meets "A", but "Ł" stays "ł" and Cyrillic stays
    Cyrillic. For words compared within one country's languages.
    """
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).casefold()
