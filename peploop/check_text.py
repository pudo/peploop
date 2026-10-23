"""Pin how much each text normalisation forgives.

`fold` and `strip_marks` key retrieval and the gazetteer, so a change here
re-ranks shortlists and re-keys requests: these cases make such a change loud.

Run it as `python -m peploop.check_text` from the repository root.
"""

from peploop.checks import expect
from peploop.text import fold, squash, strip_marks


def main() -> None:
    expect(squash("  a\n\tb\x00c  ") == "a b c", "squash collapses whitespace and control characters")
    expect(fold("Río Ålesund") == "rio alesund", "fold drops diacritics")
    expect(fold("Москва") == "moskva", "fold transliterates another script")
    expect(fold("Łódź") == "lodz", "fold reads Ł as L")
    expect(strip_marks("Río Ä") == "rio a", "strip_marks drops diacritics")
    expect(strip_marks("Łódź") == "łodz", "strip_marks keeps a letter that is not a mark")
    expect(strip_marks("Москва") == "москва", "strip_marks keeps the script")


if __name__ == "__main__":
    main()
