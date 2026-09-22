"""Pin what `propose` makes of a reconciled office, offline.

The position lane decides three things that are wrong in ways nothing later
notices. A tenure whose end contradicts the record but whose start agrees can
be read as `exists`, and an `exists` is invisible to both review and `apply` --
so the contradiction the article found is silently dropped. The same spell read
in two languages can become two rows asking a reviewer one question twice. And
an acting tenure can go out as an ordinary one, which asserts more than the
article did.

No network, no key, no database: every case is a hand-built entity and a
hand-built extraction. Run it as `python -m peploop.check_propose` from the
repository root.
"""

import sys
from typing import Any

from peploop import propose

# A stand-in office and two stand-in articles. Nothing here names a real
# country: `check_neutral` is about rules, and a fixture that reads as one
# country's is how the next country's case stops being written.
OFFICE = "Q0000001"


def day(text: str) -> dict[str, Any]:
    """A day-precision time value, as the extraction's own parser writes one."""
    value = propose.time_value(text)
    assert value is not None, text
    return value


def statement(start: str | None = None, end: str | None = None) -> dict[str, Any]:
    """One P39 claim on the item, with whatever endpoints it records."""
    qualifiers: dict[str, list[dict[str, Any]]] = {}
    for prop, text in (("P580", start), ("P582", end)):
        if text is not None:
            qualifiers[prop] = [{"property": prop, "datatype": "time", "snaktype": "value",
                                 "datavalue": {"type": "time", "value": day(text)}}]
    claim: dict[str, Any] = {
        "rank": "normal",
        "mainsnak": {"property": "P39", "snaktype": "value", "datatype": "wikibase-item",
                     "datavalue": {"type": "wikibase-entityid",
                                   "value": {"entity-type": "item", "id": OFFICE}}},
    }
    if qualifiers:
        claim["qualifiers"] = qualifiers
    return claim


def item(*claims: dict[str, Any]) -> dict[str, Any]:
    return {"claims": {"P39": list(claims)}} if claims else {"claims": {}}


def mention(**over: Any) -> dict[str, Any]:
    base = {"title": "minister of finance", "lang": "aa", "start": "2020-10-15",
            "end": "2022-06-01", "quotes": ["took office on 15 October 2020"],
            "acting": False}
    base.update(over)
    return base


def span(start: str | None = None, end: str | None = None) -> dict[str, Any]:
    return {prop: day(text) for prop, text in (("P580", start), ("P582", end))
            if text is not None}


def main() -> int:
    """Run every case and report what each one found."""
    failures: list[str] = []

    def expect(got: Any, want: Any, message: str) -> None:
        ok = got == want
        print(("  ok   " if ok else "  FAIL ") + f"{message}" + ("" if ok else f" (got {got!r})"))
        if not ok:
            failures.append(message)

    print("tenure_status, one statement at a time:")
    expect(propose.tenure_status([], span("2020-10-15")), "new",
           "an office the item does not record is new")
    expect(propose.tenure_status([span("2020-10-15", "2022-06-01")],
                                 span("2020-10-15", "2022-06-01")), "exists",
           "both endpoints agreeing is already recorded")
    expect(propose.tenure_status([span("2020-10-15")], span("2020-10-15", "2022-06-01")),
           "refine", "an end the item lacks is what this adds")
    # The bug this file exists for: the start agrees and the end does not, and
    # the worst endpoint has to win or the contradiction is never reviewed.
    expect(propose.tenure_status([span("2020-10-15", "2022-06-01")],
                                 span("2020-10-15", "2022-04-20")), "conflict",
           "a matching start does not excuse a contradicting end")
    expect(propose.tenure_status([span(end="2022-06-01")], span("2020-10-15", "2022-04-20")),
           "conflict", "one contradicting endpoint beats one missing one")
    # A coarser reading of the same date is the same date.
    expect(propose.tenure_status([span("2020-10-15")], {"P580": propose.time_value("2020")}),
           "exists", "a year against a day agrees at the precision they share")

    print("tenure_status, several statements for one office:")
    two_terms = [span("2004-12-03", "2008-11-21"), span("2020-10-15", "2022-06-01")]
    expect(propose.tenure_status(two_terms, span("2020-10-15", "2022-06-01")), "exists",
           "a second term matches the term it is, not the other one")
    expect(propose.tenure_status(two_terms, span("2012-02-10", "2013-03-20")), "conflict",
           "a third spell neither statement records is a human's call")

    print("the lane as a whole:")
    placed = {0: (OFFICE, 1)}
    out = propose._positions(item(), {"positions": [mention()]}, placed, set())
    expect([(p.property, p.status, p.value["id"], p.resolution_id) for p in out],
           [("P39", "new", OFFICE, 1)], "a placed mention becomes one new P39")
    expect(sorted((out[0].qualifiers or {})), ["P580", "P582"],
           "the tenure's endpoints become P580 and P582")

    both = {"positions": [mention(), mention(lang="ab", title="finance minister",
                                             quotes=["finance minister, 2020 to 2022"])]}
    out = propose._positions(item(), both, {0: (OFFICE, 1), 1: (OFFICE, 2)}, set())
    expect(len(out), 1, "the same spell in two languages is one row")
    expect(sorted(s.lang or "" for s in out[0].sources), ["aa", "ab"],
           "and it carries both articles as sources")

    gap = {"positions": [mention(), mention(start="2004-12-03", end="2008-11-21")]}
    out = propose._positions(item(), gap, {0: (OFFICE, 1), 1: (OFFICE, 2)}, set())
    expect(len(out), 2, "two spells with a gap stay two rows")

    out = propose._positions(item(), {"positions": [mention(acting=True)]}, placed, set())
    expect([p.status for p in out], [propose.FILTERED],
           "an acting tenure is filtered, not asserted")

    out = propose._positions(item(), {"positions": [mention()]}, {}, set())
    expect(out, [], "a mention reconciliation refused proposes nothing")

    out = propose._positions(item(), {"positions": [mention()]}, placed,
                             {"took office on 15 October 2020"})
    expect([p.status for p in out], ["unquoted"],
           "a mention whose only quote is bad is unquoted")

    print(f"{len(failures)} failures")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
