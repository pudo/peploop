"""Read, write and compare Wikidata time values the same way in every lane.

Reach for this whenever a rule looks at a date. Wikidata stores a date with a
precision: "+1962-00-00T00:00:00Z" at precision 9 is the year 1962, and its
padded month and day mean nothing. Two dates are compared at the precision
they share, and a rule that reads digits past a value's precision is wrong.
"""

import re
from datetime import date
from typing import Any

CALENDAR = "http://www.wikidata.org/entity/Q1985727"
#: The precision of a `YYYY`, `YYYY-MM` or `YYYY-MM-DD` string, by its length.
DATE_PRECISION = {4: 9, 7: 10, 10: 11}
TIME_RE = re.compile(r"^([+-]?\d+)-(\d{2})-(\d{2})")
YEAR_RE = re.compile(r"([+-]?\d+)-")


def time_value(text: str) -> dict[str, Any] | None:
    """Render a `YYYY`, `YYYY-MM` or `YYYY-MM-DD` string as a Wikidata time.

    Unknown month and day are padded with `00`, as Wikidata itself stores
    them; the precision is what says how much of the value to read.
    """
    precision = DATE_PRECISION.get(len(text))
    if precision is None:
        return None
    padded = (text + "-00-00")[:10]
    return {
        "time": f"+{padded}T00:00:00Z",
        "precision": precision,
        "calendarmodel": CALENDAR,
        "timezone": 0,
        "before": 0,
        "after": 0,
    }


def at_precision(text: str, precision: int) -> str | None:
    """Truncate a time value to a precision, so two dates compare like for like."""
    match = TIME_RE.match(text)
    if match is None:
        return None
    year, month, day = match.groups()
    if precision >= 11:
        return f"{year}-{month}-{day}"
    if precision == 10:
        return f"{year}-{month}"
    if precision == 9:
        return year
    scale = 10 ** (9 - precision)
    return str(int(year) // scale * scale)


def year(value: Any) -> int | None:
    """The year of a time value or a WDQS date string ("+1909-01-01T…", "-0550-…"), at any precision.

    For spans and eras, where a decade's or century's first year is still the
    best year there is. A rule that needs the year to be known uses `known_year`.
    """
    text = value.get("time") if isinstance(value, dict) else value
    if not text or not isinstance(text, str):
        return None
    m = YEAR_RE.match(text)
    return int(m.group(1)) if m else None


def known_year(value: dict[str, Any] | None) -> int | None:
    """The year of a time value known at least to the year, else None.

    For tenure rules: "20th century" is no year a term could have started in.
    """
    if value is None or value.get("precision", 0) < 9:
        return None
    text = at_precision(value["time"], 9)
    if text is None:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def after_today(value: dict[str, Any] | None, today: date) -> bool:
    """Whether a time value lies after today, compared at its own precision.

    A year that has begun is not in the future, nor is the current month: a
    tenure "from October 2026" is a fact on 23 October. A value coarser than a
    year compares as its year.
    """
    if not value or not isinstance(value.get("time"), str):
        return False
    match = TIME_RE.match(value["time"])
    if match is None:
        return False
    y, m, d = (int(g) for g in match.groups())
    precision = value.get("precision", 11)
    if precision <= 9:
        return y > today.year
    if precision == 10:
        return (y, m) > (today.year, today.month)
    return (y, m, d) > (today.year, today.month, today.day)


def group_dates(entries: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Cluster the date entries that say the same thing, finest value first.

    Two articles giving `1962` and `1962-02-06` are one date one of them knows
    more exactly, not two candidate values; two giving different days are two
    rows and a reviewer's decision. The values are `YYYY[-MM[-DD]]` strings, so
    agreement at the precision they share is a prefix comparison.
    """
    groups: list[list[dict[str, Any]]] = []
    for entry in sorted(entries, key=lambda e: -len(e["value"])):
        for group in groups:
            shared = min(len(group[0]["value"]), len(entry["value"]))
            if group[0]["value"][:shared] == entry["value"][:shared]:
                group.append(entry)
                break
        else:
            groups.append([entry])
    return groups
