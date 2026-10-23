"""Normalise text before two pieces of it are compared.

Reach for this instead of writing a lane's own `_norm`. Each function says
how much it forgives. A comparison that forgives too little rejects honest
quoting. One that forgives too much matches what was never said.
"""

import re
import unicodedata

WHITESPACE = re.compile(r"\s+")


def squash(text: str) -> str:
    """Collapse whitespace and control characters to single spaces, and trim.

    The reduction that turns an article into prompt text is the one thing a
    model's copy of a passage can honestly differ by.
    """
    text = "".join(" " if unicodedata.category(ch) == "Cc" else ch for ch in text)
    return WHITESPACE.sub(" ", text).strip()
