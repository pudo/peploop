"""Pin which accepted rows the QuickStatements export may carry, and what it writes.

The export's whole risk is one QS behaviour: a line is matched to a statement
on item, property and value, and its qualifiers are folded into whatever it
finds. A row routed to QS that the item already records under its value, or
that shares its value with a second spell in the same edit, becomes one
statement with two tenures' dates and nothing pairing them. Each such case is
pinned here as staying with `apply`. Offline: `route` is a pure function of an
entity and rows. Run it as `python -m peploop.check_qs`.
"""

import sys
from typing import Any

from peploop import qs
from peploop.check_apply import GUID, OFFICE, OTHER, PERSON, claim, day, item, office, row, span


def main() -> int:
    failures: list[str] = []

    def expect(got: Any, want: Any, message: str) -> None:
        ok = got == want
        print(("  ok   " if ok else "  FAIL ") + message + ("" if ok else f" (got {got!r})"))
        if not ok:
            failures.append(message)

    print("what goes out:")
    out = qs.route(PERSON, item(), [office(quals=span("2020-10-15", "2022-06-01"))], "t")
    expect(dict(out.routes), {"qs": 1}, "a dated tenure the item lacks goes to QS")
    expect(out.rows, [1], "carrying its row")
    expect(out.lines[0].split("\t")[:7],
           [PERSON, "P39", OFFICE, "P580", "+2020-10-15T00:00:00Z/11", "P582", "+2022-06-01T00:00:00Z/11"],
           "statement and qualifiers in QS columns")
    expect("\tS143\tQ0000101\tS4656\t" in out.lines[0] and "\tS813\t+" in out.lines[0], True,
           "the reference keeps apply's shape: wiki, revision URL, retrieved")
    expect(out.lines[0].endswith(" /* t */"), True, "the summary rides on the last column")

    print("two wikis attesting one statement:")
    rows = [
        office(quals=span("2020-10-15"), id=1),
        office(quals=span("2020-10-15"), id=2, source_lang="ab",
               source_url="https://ab.wikipedia.org/wiki/Y", source_rev=8),
    ]
    out = qs.route(PERSON, item(), rows, "t")
    expect(len(out.lines), 2, "one line per reference")
    expect(sorted(out.rows), [1, 2], "both rows recorded against it")
    expect(qs.validate(out.lines), [], "and the pair passes validation: same qualifiers")

    print("what stays with apply:")
    out = qs.route(PERSON, item(claim(OFFICE, span("2010-01-01", "2014-01-01"))),
                   [office(quals=span("2020-10-15"))], "t")
    expect((dict(out.routes), out.lines), ({"api:value-on-item": 1}, []),
           "a further spell of an office the item records: QS would merge into it")
    out = qs.route(PERSON, item(), [office(quals=span("2010-01-01", "2014-01-01"), id=1),
                                    office(quals=span("2020-10-15"), id=2)], "t")
    expect((dict(out.routes), out.rows), ({"api:spells-together": 2}, []),
           "two spells of one office in one edit: QS would collapse them")
    out = qs.route(PERSON, item(claim(OFFICE)), [office(quals=span("2020-10-15"))], "t")
    expect((dict(out.routes), out.rows), ({"api:refine": 1}, []),
           "dates for an undated statement are a refinement")
    born = row("P569", day("1970-05-01"))
    coarse = {"id": f"{PERSON}$b", "rank": "normal", "mainsnak": {
        "snaktype": "value", "property": "P569", "datavalue": {"type": "time", "value": {
            **day("1970-01-01"), "time": "+1970-00-00T00:00:00Z", "precision": 9}}},
        "references": [{"snaks": {"P999": []}}]}
    out = qs.route(PERSON, item(coarse), [born], "t")
    expect(out.lines, [], "a sharper birth date beside somebody's sourced year is not new")
    julian = row("P569", {**day("1700-05-01"), "calendarmodel": "http://www.wikidata.org/entity/Q1985786"})
    out = qs.route(PERSON, item(), [julian], "t")
    expect(dict(out.routes), {"api:unrenderable": 1}, "a Julian date is left to the API")
    out = qs.route(PERSON, item(claim(OTHER)), [office(quals=span("2020-10-15"))], "t")
    expect(dict(out.routes), {"qs": 1}, "another office on the item is no obstacle")

    print("validation:")
    a = f"{PERSON}\tP39\t{OFFICE}\tP580\t+2020-10-15T00:00:00Z/11 /* t */"
    b = f"{PERSON}\tP39\t{OFFICE}\tP580\t+2010-01-01T00:00:00Z/11 /* t */"
    expect(len(qs.validate([a, b])), 1, "one value twice with different qualifiers is refused")
    expect(len(qs.validate([a, a])), 1, "a duplicate line is refused")
    expect(len(qs.validate([f"-{a}"])), 1, "a removal is refused")

    print("chunks:")
    big = [qs.Export(qid=f"Q{i}", baserevid=1, lines=["x\ty\tz\tS1\ta"] * 100) for i in range(4)]
    expect([len(c) for c in qs.chunked(big, cap=300)], [1, 1, 1, 1],
           "a person is never split, and 200 commands leave no room for a second")

    expect([qs.commands(line) for line in (
        f"{PERSON}\tP569\t+1953-11-28T00:00:00Z/11\tS143\tQ328\tS813\t+2026-10-08T00:00:00Z/11 /* t */",
        f"{PERSON}\tP39\t{OFFICE}\tP580\t+2018-05-09T00:00:00Z/11\tP582\t+2025-11-29T00:00:00Z/11"
        f"\tS143\tQ328 /* t */",
    )], [2, 4], "commands counted as QS's parse counts them")
    same = [office(quals=span("2020-10-15"), id=1), office(quals=span("2020-10-15"), id=2)]
    out = qs.route(PERSON, item(), same, "t")
    expect((len(out.lines), sorted(out.rows)), (1, [1, 2]),
           "two rows citing one revision are one line, both rows recorded")

    print("read back:")
    live = claim(OFFICE, span("2020-10-15"))
    landed = {"value": {"id": OFFICE}, "qualifiers": {**span("2020-10-15"), "_sources": []}}
    expect(qs._carries(live, landed), True, "a live claim with the value and every qualifier")
    expect(qs._carries(claim(OFFICE), landed), False, "not one missing a qualifier")
    expect(GUID.startswith(PERSON), True, "fixture sanity")

    print(f"\n{len(failures)} failed" if failures else "\nall ok")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
