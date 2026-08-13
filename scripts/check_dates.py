#!/usr/bin/env python
"""Assert `wd.roster.parse_date` / `parse_period` against the cells that broke it.

    python scripts/check_dates.py

Reach for this before and after touching either function. Every case below is a
real cell from a real roster that this workbench parsed wrongly at some point,
and `recipes/country_sweep.md` §7 records what each one cost — a silent
month-precision downgrade on the UAE's founding date, a 1,939-day tenure read as
the year 1939. The regression net in `regression/` catches a *decision* that
changed; this catches the parse underneath it, which is cheaper to read.

The Hijri block is the reason this file exists. Most Saudi rosters date in AH,
and no conversion happens: an AH year is simply outside the Gregorian range the
year rule accepts (AH 1500 falls in AD 2076, so nothing in use collides), and a
dual-dated cell keeps its AD half. That behaviour is load-bearing and invisible
— worth pinning before someone "fixes" the year range.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wd.roster import parse_date, parse_period

#: (cell text, expected ISO prefix or None, what it is / what it broke)
DATES = [
    # --- Hijri, and dual-dated cells -------------------------------------
    ("1370 هـ", None, "AH year alone: no Gregorian date to be had"),
    ("28/6/1350هـ", None, "AH day/month/year, numeric"),
    ("20 رمضان 1395 هـ", None, "AH with an AH month name"),
    ("1331هـ/1913م.", "1913", "dual-dated: the AD half wins"),
    ("1 رجب 1441 هـ 25 فبراير 2020 م", "2020-02-25",
     "AH stacked over AD in one cell — returned the bare year 1441→2020 "
     "before `_first_month` kept scanning past the AH month"),
    ("مارس 1963 م", "1963-03", "AD month precision, Arabic"),
    ("5 مارس 2023", "2023-03-05", "AD day precision, Arabic, no era marker"),
    ("2 ديسمبر 1971", "1971-12-02", "the UAE's founding date"),
    ("1761م", "1761", "the era marker glued to the year"),
    # --- the particle and abbreviation traps -----------------------------
    ("2 December 1971", "1971-12-02",
     "`(?:del?\\s*)?` matched the 'De' of December and lost the day"),
    ("17 de jul. de 1834", "1834-07-17", "es abbreviated month, dot after"),
    ("2. července 1992", "1992-07-02", "cs day ordinal, dot after the day"),
    ("5 de julio del 2022", "2022-07-05", "'del' before a four-digit year"),
    ("September 24, 1810", "1810-09-24", "en month-first"),
    ("16 июля 1990", "1990-07-16", "ru genitive month"),
    # --- what must NOT parse ---------------------------------------------
    ("حتى الآن", None, "'to date' is not a date"),
    ("Incumbent", None, "still in office"),
    ("Funkce neobsazena", None, "a gap in the succession"),
    ("1939", "1939", "a day count that is also a plausible year — the reason "
                     "decoy columns get the `days` role rather than a guard here"),
]

#: (cell text, (start, end), what it is)
PERIODS = [
    ("1331هـ/1913م. – 1354هـ/1935م.", ("1913", "1935"), "dual-dated range"),
    ("1370 هـ – 1373 هـ", (None, None), "AH range: nothing to record"),
    ("28/6/1350هـ – 9/3/1353هـ", (None, None), "AH numeric range"),
    ("23 September 1932 – 9 November 1953", ("1932-09-23", "1953-11-09"),
     "an ordinary en reign"),
    ("September 24, 1810 –October 23, 1810", ("1810-09-24", "1810-10-23"),
     "no space on the right of the dash"),
    ("25 January 1972 – 1972", ("1972-01-25", "1972"),
     "coarse end beside a day-precision start — an ordinary cell, not a defect"),
    ("октябрь — декабрь 1995", ("1995-10", "1995-12"),
     "the year stated once, at the end, and meant of both months"),
    ("23 de julio de 1834 (fallecido en el cargo)", ("1834-07-23", None),
     "'died in office' contains the incumbency phrase; the end date survives "
     "as the start of nothing — the term simply ends"),
]


def main() -> None:
    bad = 0
    for text, want, why in DATES:
        got = parse_date(text)
        if got != want:
            bad += 1
            print(f"FAIL parse_date({text!r})\n  want {want!r}, got {got!r}\n  ({why})")
    for text, want, why in PERIODS:
        start, end, _incumbent = parse_period(text)
        if (start, end) != want:
            bad += 1
            print(f"FAIL parse_period({text!r})\n  want {want!r}, "
                  f"got {(start, end)!r}\n  ({why})")
    total = len(DATES) + len(PERIODS)
    if bad:
        raise SystemExit(f"\n{bad} of {total} date cases failed")
    print(f"{total} date cases pass")


if __name__ == "__main__":
    main()
