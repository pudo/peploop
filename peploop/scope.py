"""Decide from the item alone whether a person is still worth an extraction.

Reach for this the moment the Wikidata item is in hand and before any article
is fetched: a category seed queues everyone it ever admitted, and a large share
of them are long dead or implausibly old, each costing an article fetch and an
LLM call. Everyone this cannot judge -- no dates, a date too coarse to place, a
value the parser does not recognise -- is kept, because a person kept in error
costs one extraction and a person dropped in error is never looked at again.
"""

import re
from datetime import date
from typing import Any

from peploop import wikidata

#: Alive and older than this many years: no longer worth reading about.
MAX_AGE_YEARS = 90
#: Dead for longer than this many years: no longer worth reading about.
MAX_YEARS_DEAD = 5

#: A year, month and day. A tuple rather than `datetime.date`, which starts at
#: year 1 and raises on the BCE dates Wikidata holds for ancient office-holders.
Point = tuple[int, int, int]

_TIME = re.compile(r"^([+-]?)(\d+)-(\d{2})-(\d{2})T")


def _parse(time: str) -> Point | None:
    """Read a Wikidata time string as year, month and day, a BCE year negative."""
    match = _TIME.match(time)
    if match is None:
        return None
    sign, year, month, day = match.groups()
    return (-int(year) if sign == "-" else int(year), int(month), int(day))


def _last_day(year: int, month: int) -> int:
    """The last day of a month, by the proleptic Gregorian leap rule."""
    if month == 2:
        leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
        return 29 if leap else 28
    return 31 if month in (1, 3, 5, 7, 8, 10, 12) else 30


def interval(time: str, precision: int) -> tuple[Point, Point] | None:
    """Widen a Wikidata time value into the first and last day it could mean.

    Reach for this before comparing a Wikidata date with anything: below
    precision 9 the stored year is not a year, and reading it as one turns the
    20th century into the year 2000. None means the value cannot be placed --
    unparseable, or coarser than a millennium -- and a caller keeps whoever it
    was asked about rather than guessing.
    """
    parsed = _parse(time)
    if parsed is None or precision < 6:
        return None
    year, month, day = parsed
    if precision >= 11 and 1 <= month <= 12 and 1 <= day <= _last_day(year, month):
        return (year, month, day), (year, month, day)
    if precision >= 10 and 1 <= month <= 12:
        return (year, month, 1), (year, month, _last_day(year, month))
    if precision >= 9:
        return (year, 1, 1), (year, 12, 31)
    if precision == 8:
        # A decade is stored as the year it opens: +1930-00-00 is 1930 to 1939.
        first = year - year % 10
        return (first, 1, 1), (first + 9, 12, 31)
    # A century and a millennium are stored as the year they *close*, so the
    # 20th century is +2000-00-00 and runs 1901 to 2000. Items storing the
    # opening year exist too, so the span is the one the stored year falls
    # inside rather than one counted off the stored year in a fixed direction.
    size = 100 if precision == 7 else 1000
    closes = -(-year // size) * size
    return (closes - size + 1, 1, 1), (closes, 12, 31)


def _years_between(point: Point, now: Point) -> int:
    """Count whole years from a day to a day, the way an age is counted."""
    years = now[0] - point[0]
    if now[1:] < point[1:]:
        years -= 1
    return years


def _year_text(point: Point) -> str:
    """Name the year of a bound, BCE years the way a reader writes them."""
    year = point[0]
    return str(year) if year > 0 else f"{1 - year} BCE"


def _latest_readings(values: list[tuple[str, int]], now: Point, limit: int) -> Point | None:
    """The last day any of these values could mean, or None to keep the person.

    None covers both ways a set of values fails to rule someone out: one of
    them cannot be placed at all, or one of them can be read as recent enough
    to stay in scope. Wikidata holds contradictory dates and a person is kept
    if any single value keeps them.
    """
    latest: Point | None = None
    for time, precision in values:
        bounds = interval(time, precision)
        if bounds is None:
            return None
        closes = bounds[1]
        if _years_between(closes, now) <= limit:
            return None
        latest = closes if latest is None or closes > latest else latest
    return latest


#: A date as Wikidata stores one: the time string and its precision.
Dated = tuple[str, int]


def out_of_scope_dates(
    births: list[Dated], deaths: list[Dated], today: date | None = None
) -> str | None:
    """Say why someone with these dates is no longer politically relevant.

    The one rule behind both gates: `out_of_scope` reads the dates off the
    item before any article is fetched, and the policy reads the dates the
    extraction found, which is how a mayor of 1595 whose item carries no date
    at all is still set aside. A death date answers on its own -- how old they
    would be now says nothing about anyone who is not alive -- and the rule
    only ever fires when *every* reading of the dates agrees: someone born in
    the 1930s could be 87, so the decade keeps them.
    """
    reference = today or date.today()
    now: Point = (reference.year, reference.month, reference.day)
    if deaths:
        latest = _latest_readings(deaths, now, MAX_YEARS_DEAD)
        return None if latest is None else f"dead since {_year_text(latest)}"
    latest = _latest_readings(births, now, MAX_AGE_YEARS)
    if latest is None:
        return None
    return f"born {_year_text(latest)}, no death recorded"


def out_of_scope(entity: dict[str, Any], today: date | None = None) -> str | None:
    """Say why a person is no longer politically relevant, or None to keep them.

    A reason discards them; None sends them on to the article fetch.
    """
    return out_of_scope_dates(
        wikidata.claim_time(entity, "P569", include_deprecated=False),
        wikidata.claim_time(entity, "P570", include_deprecated=False),
        today,
    )


#: `YYYY`, `YYYY-MM`, `YYYY-MM-DD` as the extraction writes them, to a precision.
_TEXT_PRECISION = {4: 9, 7: 10, 10: 11}


def extracted_dates(data: dict[str, Any]) -> tuple[list[Dated], list[Dated]]:
    """Read the birth and death dates an extraction found, as Wikidata times.

    The strings are the extraction schema's own (`YYYY[-MM[-DD]]`), padded the
    way Wikidata pads an unknown month and day; anything else is left out.
    """
    out: tuple[list[Dated], list[Dated]] = ([], [])
    for slot, key in enumerate(("birth_date", "death_date")):
        for entry in data.get(key) or []:
            text = str(entry.get("value") or "")
            precision = _TEXT_PRECISION.get(len(text))
            if precision is None:
                continue
            padded = (text + "-00-00")[:10]
            out[slot].append((f"+{padded}T00:00:00Z", precision))
    return out


def out_of_scope_extracted(data: dict[str, Any], today: date | None = None) -> str | None:
    """Say why the person the articles describe is no longer relevant, or None.

    The second gate, after extraction: the item gate keeps everyone whose item
    carries no dates, and for a long-dead mayor the article is the only thing
    that says so. Same rule, same thresholds, read off the extraction instead.
    """
    births, deaths = extracted_dates(data)
    return out_of_scope_dates(births, deaths, today)
