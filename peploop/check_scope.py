"""Pin what the relevance gate makes of a person's dates, offline.

The gate is the one step that ends a person's run without anyone looking at
them, so every way it can be wrong is silent. Three of those ways are what this
file exists for. A coarse date read as the year it stores turns the 20th
century into the year 2000 and drops someone born in it; a boundary counted the
strict way drops a person the day they turn ninety; and a date that cannot be
placed -- a BCE year, a precision below a millennium -- has to keep the person
rather than raise, because a BCE date has aborted a load here before.

No network, no key, no database: every case is a hand-built entity and a fixed
reference day. Run it as `python -m peploop.check_scope` from the repository
root.
"""

import sys
from datetime import date
from typing import Any

from peploop import scope

# A mid-year reference day, so a birthday on either side of it falls on either
# side of the threshold and the boundary cases can be written at all.
TODAY = date(2026, 6, 15)


def time(text: str, precision: int, rank: str = "normal") -> dict[str, Any]:
    """One dated claim, as `wbgetentities` returns one."""
    return {
        "rank": rank,
        "mainsnak": {
            "property": "P569",
            "snaktype": "value",
            "datatype": "time",
            "datavalue": {
                "type": "time",
                "value": {"time": text, "precision": precision, "timezone": 0},
            },
        },
    }


def unknown(rank: str = "normal") -> dict[str, Any]:
    """A `somevalue` claim: it says there is a date, and does not say which."""
    return {"rank": rank, "mainsnak": {"property": "P569", "snaktype": "somevalue"}}


def person(born: list[dict[str, Any]] | None = None,
           died: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    claims: dict[str, list[dict[str, Any]]] = {}
    if born:
        claims["P569"] = born
    if died:
        claims["P570"] = died
    return {"claims": claims}


def alive(text: str, precision: int) -> dict[str, Any]:
    """Someone with one birth date and nothing recording a death."""
    return person(born=[time(text, precision)])


def dead(text: str, precision: int) -> dict[str, Any]:
    """Someone with one death date and no birth date."""
    return person(died=[time(text, precision)])


def main() -> int:
    """Run every case and report what each one found."""
    failures: list[str] = []

    def expect(got: Any, want: Any, message: str) -> None:
        ok = got == want
        print(("  ok   " if ok else "  FAIL ") + f"{message}" + ("" if ok else f" (got {got!r})"))
        if not ok:
            failures.append(message)

    def verdict(entity: dict[str, Any]) -> str | None:
        return scope.out_of_scope(entity, today=TODAY)

    print("what a stored time value could mean:")
    expect(scope.interval("+1935-01-02T00:00:00Z", 11),
           ((1935, 1, 2), (1935, 1, 2)), "a day is itself")
    expect(scope.interval("+1935-02-00T00:00:00Z", 10),
           ((1935, 2, 1), (1935, 2, 28)), "a month runs to its last day")
    expect(scope.interval("+1935-00-00T00:00:00Z", 9),
           ((1935, 1, 1), (1935, 12, 31)), "a year runs to its last day")
    expect(scope.interval("+1935-00-00T00:00:00Z", 8),
           ((1930, 1, 1), (1939, 12, 31)), "a decade is the ten years it opens")
    expect(scope.interval("+2000-00-00T00:00:00Z", 7),
           ((1901, 1, 1), (2000, 12, 31)), "a century is the hundred years it closes")
    expect(scope.interval("+1801-00-00T00:00:00Z", 7),
           ((1801, 1, 1), (1900, 12, 31)), "and is the same span written the other way")
    expect(scope.interval("+2000-00-00T00:00:00Z", 6),
           ((1001, 1, 1), (2000, 12, 31)), "a millennium is the thousand years it closes")
    expect(scope.interval("-0044-03-15T00:00:00Z", 11),
           ((-44, 3, 15), (-44, 3, 15)), "a BCE day parses instead of raising")
    expect(scope.interval("+2000-00-00T00:00:00Z", 5), None,
           "coarser than a millennium cannot be placed")
    expect(scope.interval("not a time", 11), None,
           "and neither can a value that will not parse")

    print("nothing to judge on:")
    expect(verdict(person()), None,
           "no dates at all keeps the person")
    expect(verdict(person(born=[unknown()])), None,
           "a date that says only 'some value' keeps them")
    expect(verdict(alive("+2000-00-00T00:00:00Z", 5)), None,
           "a birth date coarser than a millennium keeps them")

    print("alive, by every reading of the birth date:")
    expect(verdict(alive("+1935-06-16T00:00:00Z", 11)), None,
           "turning ninety today is still in scope")
    expect(verdict(alive("+1935-06-15T00:00:00Z", 11)), "born 1935, no death recorded",
           "one day past ninety-one is out")
    expect(verdict(alive("+1935-06-00T00:00:00Z", 10)), None,
           "a month straddling the birthday is kept on its last day")
    expect(verdict(alive("+1935-05-00T00:00:00Z", 10)), "born 1935, no death recorded",
           "a month whose every day is past ninety is out")
    expect(verdict(alive("+1935-00-00T00:00:00Z", 9)), None,
           "the same year read whole reaches ninety and stays")
    expect(verdict(alive("+1934-00-00T00:00:00Z", 9)), "born 1934, no death recorded",
           "the year before does not")
    # The worked case: the 1930s can be read as 1939, which is 86 here.
    expect(verdict(alive("+1935-00-00T00:00:00Z", 8)), None,
           "a decade is kept on its youngest reading")
    expect(verdict(alive("+1900-00-00T00:00:00Z", 8)), "born 1909, no death recorded",
           "a decade whose youngest reading is over ninety is out")
    expect(verdict(alive("+2000-00-00T00:00:00Z", 7)), None,
           "a century read as the year it stores would drop this one")
    expect(verdict(alive("+1900-00-00T00:00:00Z", 7)), "born 1900, no death recorded",
           "the century before it is out on every reading")
    expect(verdict(alive("+2000-00-00T00:00:00Z", 6)), None,
           "a millennium closing in living memory keeps them")
    expect(verdict(alive("+1000-00-00T00:00:00Z", 6)), "born 1000, no death recorded",
           "the millennium before it does not")
    expect(verdict(alive("-0044-03-15T00:00:00Z", 11)), "born 45 BCE, no death recorded",
           "a BCE birth is out, and says so as a reader would")

    print("dead, and how long ago:")
    expect(verdict(person(born=[time("+1850-01-01T00:00:00Z", 11)],
                          died=[time("+2024-03-02T00:00:00Z", 11)])), None,
           "a recent death outranks a birth date nothing else would keep")
    expect(verdict(dead("+2021-06-16T00:00:00Z", 11)), None,
           "dead five years to the day is still in scope")
    expect(verdict(dead("+2020-06-15T00:00:00Z", 11)), "dead since 2020",
           "a year further back is out")
    expect(verdict(dead("+2021-06-00T00:00:00Z", 10)), None,
           "a month of death inside the window keeps them")
    expect(verdict(dead("+2020-00-00T00:00:00Z", 9)), None,
           "a year of death whose end is inside the window keeps them")
    expect(verdict(dead("+2019-00-00T00:00:00Z", 9)), "dead since 2019",
           "the year before is out")
    expect(verdict(dead("+2010-00-00T00:00:00Z", 8)), "dead since 2019",
           "a decade of death is out on its latest reading")
    expect(verdict(dead("+1900-00-00T00:00:00Z", 7)), "dead since 1900",
           "a 19th-century death is out however it is read")
    expect(verdict(dead("+2000-00-00T00:00:00Z", 6)), "dead since 2000",
           "a millennium of death is out on its latest reading")
    expect(verdict(dead("+2000-00-00T00:00:00Z", 5)), None,
           "a death date that cannot be placed keeps them")

    print("what the item disagrees with itself about:")
    expect(verdict(person(born=[time("+1850-01-01T00:00:00Z", 11),
                                time("+1950-01-01T00:00:00Z", 11)])), None,
           "two birth dates keep them if either one would")
    expect(verdict(person(died=[time("+1900-01-01T00:00:00Z", 11),
                                time("+2025-01-01T00:00:00Z", 11)])), None,
           "two death dates keep them if either one would")
    expect(verdict(person(born=[time("+1850-01-01T00:00:00Z", 11),
                                time("+1860-01-01T00:00:00Z", 11)])),
           "born 1860, no death recorded", "and the reason names the latest of them")
    expect(verdict(person(born=[time("+1850-01-01T00:00:00Z", 11),
                                time("+1950-01-01T00:00:00Z", 11, rank="deprecated")])),
           "born 1850, no death recorded", "a deprecated date is not a reading")
    expect(verdict(person(born=[time("+1850-01-01T00:00:00Z", 11)],
                          died=[time("+2024-03-02T00:00:00Z", 11, rank="deprecated")])),
           "born 1850, no death recorded", "a deprecated death leaves the age rule to answer")

    print(f"{len(failures)} failures")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
