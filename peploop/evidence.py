"""Test whether a claim rests on text the model was actually shown.

Reach for this in every lane's quote gate. A claim is written only on a quote
found verbatim in the material sent with the request. The text may differ in
whitespace, case, JSON escapes and the quote marks around it, and in nothing
else. Anything more is paraphrase or invention.
"""

import re

from rigour.text.scripts import is_dense_script

from peploop import text as textmod

#: Shorter than this, a "quote" ("CEO", "yes") is found in any article.
MIN_QUOTE = 4
#: The same floor in a logographic or syllabic script: "现任", incumbent, is a quote.
MIN_QUOTE_DENSE = 2
#: Marks a model wraps a quote in, or ends it with, that the article need not have there.
WRAPPING = "\"'«»„“”. "
ESCAPE = re.compile(r"\\(u[0-9a-fA-F]{4}|[nrt\"\\/])")
SIMPLE_ESCAPES = {"n": "\n", "r": "\r", "t": "\t", '"': '"', "\\": "\\", "/": "/"}


def unescape(text: str) -> str:
    """Undo JSON escapes a model wrote out literally ("\\u00c4kim" for "Äkim")."""
    def one(m: re.Match) -> str:
        code = m.group(1)
        return chr(int(code[1:], 16)) if code[0] == "u" and len(code) == 5 else SIMPLE_ESCAPES.get(code, m.group(0))
    return ESCAPE.sub(one, text)


def floor(quote: str) -> int:
    """How long a quote must be to prove anything, by its script."""
    return MIN_QUOTE_DENSE if is_dense_script(quote) else MIN_QUOTE


def normal(quote: str) -> str:
    """A quote as the gate compares it: unescaped, squashed, casefolded, unwrapped."""
    return textmod.squash(unescape(quote)).casefold().strip(WRAPPING)


def quoted(quote: str | None, shown: str, min_length: int | None = None) -> bool:
    """Whether a quote is non-trivial and appears in the text that was shown."""
    return not missing([quote or ""], shown, min_length)


def missing(quotes: list[str], shown: str, min_length: int | None = None) -> list[str]:
    """The quotes not found in the text that was shown, normalising the text once.

    The floor is the script's (`floor`) unless `min_length` sets it.
    `min_length=1` accepts a one-character quote, which only a sex can be
    ("男" in a Chinese infobox).
    """
    haystack = textmod.squash(shown).casefold()
    out = []
    for quote in quotes:
        needle = normal(quote) if quote else ""
        if len(needle) < (min_length or floor(needle)) or needle not in haystack:
            out.append(quote)
    return out
