"""Pin what each planned statement becomes as a QS3 line, and what a batch refuses.

QS3 cannot be aimed at a statement: a plain line merges into the first one
holding its value, a `+` line always creates one. Each route below is pinned to
the one line shape that does what the plan meant, and each case no line can aim
to the route that closes it. Offline: `route` is a pure function of an entity and
rows. Run it as `python -m peploop.check_qs`.
"""

import sys
from typing import Any

from peploop import ledger, plan, qs, route
from peploop.check_plan import GUID, OFFICE, OTHER, PERSON, STATE, claim, day, item, office, row, span

IMPORTED = {"snaks": {"P143": [{"snaktype": "value", "property": "P143",
                                "datavalue": {"type": "wikibase-entityid", "value": {"id": "Q328"}}}]}}


def main() -> int:
    failures: list[str] = []

    def expect(got: Any, want: Any, message: str) -> None:
        ok = got == want
        print(("  ok   " if ok else "  FAIL ") + message + ("" if ok else f" (got {got!r})"))
        if not ok:
            failures.append(message)

    print("a tenure the item lacks:")
    out = route.route(PERSON, item(), [office(quals=span("2020-10-15", "2022-06-01"))])
    expect(dict(out.routes), {"create": 1}, "is created")
    expect(out.edits[0][1], [1], "carrying its row")
    expect(out.lines[0].split("\t")[:7],
           [f"+{PERSON}", "P39", OFFICE, "P580", "+2020-10-15T00:00:00Z/11", "P582", "+2022-06-01T00:00:00Z/11"],
           "as a `+` line: QS3 creates it and merges it into nothing")
    expect("\tS143\tQ0000101\tS4656\t" in out.lines[0] and "\tS813\t+" in out.lines[0], True,
           "the reference: wiki, revision URL, retrieved")

    print("two wikis attesting one statement:")
    rows = [office(quals=span("2020-10-15")),
            office(quals=span("2020-10-15"), id=2, source_lang="ab", source_url="https://ab.wikipedia.org/wiki/X")]
    out = route.route(PERSON, item(), rows)
    expect(len(out.lines), 1, "is one line, never one per reference: each `+` line is a statement")
    expect("\t!S" in out.lines[0], False, "carrying a single reference block")
    expect(out.lines[0].count("\tS143\t"), 1, "citing one wiki")
    expect(out.edits[0][1], [1, 2], "and the line carries both rows")
    rows = [office(quals=span("2020-10-15"), seed_lang="ab"),
            office(quals=span("2020-10-15"), id=2, seed_lang="ab",
                   source_lang="ab", source_url="https://ab.wikipedia.org/wiki/X")]
    out = route.route(PERSON, item(), rows)
    expect("\tS143\tQ0000102\t" in out.lines[0] and "\tS143\tQ0000101\t" not in out.lines[0], True,
           "the one it cites is the home wiki, by `wiki_order`")

    print("two spells of one office, and a spell beside a recorded one:")
    out = route.route(PERSON, item(), [office(quals=span("2001-01-01", "2003-01-01")),
                                    office(quals=span("2005-01-01", "2007-01-01"), id=2)])
    expect([line.split("\t")[0] for line in out.lines], [f"+{PERSON}"] * 2, "two `+` lines, so two statements")
    live = item(claim(OFFICE, span("1990-01-01", "1994-01-01")))
    out = route.route(PERSON, live, [office(quals=span("2001-01-01"))])
    expect(dict(out.routes), {"create": 1}, "a further term beside a dated one is created, not merged")

    print("dates for the one statement that says nothing:")
    out = route.route(PERSON, item(claim(OFFICE)), [office(quals=span("1997-02-01", "2000-06-30"))])
    expect(dict(out.routes), {"merge": 1}, "is a merge")
    expect(out.lines[0].split("\t")[:7],
           [PERSON, "P39", OFFICE, "P580", "+1997-02-01T00:00:00Z/11", "P582", "+2000-06-30T00:00:00Z/11"],
           "a plain line: QS3 merges it into the only statement with the value")
    expect("\tS143\t" in out.lines[0], True, "adding our reference to a statement that had none")
    sourced = {"snaks": {"P248": [{"snaktype": "value", "property": "P248",
                                   "datavalue": {"type": "wikibase-entityid", "value": {"id": "Q36578"}}}]}}
    out = route.route(PERSON, item(claim(OFFICE, references=[sourced])), [office(quals=span("1997-02-01", "2000-06-30"))])
    expect(qs.columns(out.lines[0]),
           [PERSON, "P39", OFFICE, "P580", "+1997-02-01T00:00:00Z/11", "P582", "+2000-06-30T00:00:00Z/11"],
           "while one already referenced gets the dates alone, no reference column at all")
    out = route.route(PERSON, item(claim(OFFICE, span("2018-06-22"))), [office(quals=span("2018-06-22", "2022-05-13"))])
    expect(qs.qualifier_pairs(out.lines[0]), [("P582", "+2022-05-13T00:00:00Z/11")],
           "and it carries only what the statement lacks, never a qualifier it has")

    print("what no line can aim:")
    live = item(claim(OTHER, span("1990-01-01", "1994-01-01"), id=f"{PERSON}$dated"), claim(OTHER, id=f"{PERSON}$u"))
    out = route.route(PERSON, live, [office(OTHER, quals=span("2001-01-01"))])
    expect(out.skipped, [(1, plan.AMBIGUOUS)], "a merge with two statements to choose from is closed")
    expect(out.lines, [], "and writes nothing")
    julian = {**day("1650-01-01"), "calendarmodel": "http://www.wikidata.org/entity/Q1985786"}
    out = route.route(PERSON, item(), [office(quals={"P580": julian})])
    expect(out.skipped, [(1, qs.UNRENDERABLE)], "a Julian date is closed as unrenderable")

    print("a sharper date beside somebody's coarse one:")
    year = {**day("1950-01-01"), "time": "+1950-00-00T00:00:00Z", "precision": 9}
    sourced = {"snaks": {"P248": [{"snaktype": "value", "property": "P248",
                                   "datavalue": {"type": "wikibase-entityid", "value": {"id": "Q36578"}}}]}}

    def born(value: dict[str, Any], ref: dict[str, Any]) -> dict[str, Any]:
        return {"lastrevid": 1, "claims": {"P569": [{
            "id": GUID, "rank": "normal", "references": [ref],
            "mainsnak": {"snaktype": "value", "property": "P569", "datavalue": {"type": "time", "value": value}}}]}}
    out = route.route(PERSON, born(year, sourced), [row("P569", day("1950-03-04"))])
    expect(dict(out.routes), {"preferred": 1}, "is created beside it")
    expect(out.lines[0].split("\t")[:4], [f"+{PERSON}", "P569", "+1950-03-04T00:00:00Z/11", "R+"],
           "outranking it: `R+` right after the value")

    print("a coarse imported date:")
    out = route.route(PERSON, born(year, IMPORTED), [row("P569", day("1950-03-04"))])
    expect(dict(out.routes), {"switch": 1}, "is sharpened in place")
    expect(qs.columns(out.lines[0]),
           [qs.SWITCH, PERSON, "P569", "+1950-00-00T00:00:00Z/9", "+1950-03-04T00:00:00Z/11"],
           "by SWITCH_VALUE, which keeps the statement's id")
    expect(qs.columns(out.lines[1]), [PERSON, "P569", "+1950-03-04T00:00:00Z/11"],
           "then a plain line that adds no reference: the statement already has one")
    unsourced = born(year, IMPORTED)
    del unsourced["claims"]["P569"][0]["references"]
    out = route.route(PERSON, unsourced, [row("P569", day("1950-03-04"))])
    expect("\tS143\tQ0000101\t" in out.lines[1], True, "an unreferenced one gets ours")

    print("a merge and a creation for one office in one edit:")
    live = item(claim(OFFICE))
    out = route.route(PERSON, live, [office(quals=span("1997-02-01", "2000-06-30")),
                                  office(quals=span("2010-01-01", "2012-01-01"), id=2)])
    expect(dict(out.routes), {"merge": 1, "deferred": 1},
           "the creation waits: in one batch the merge could land on the statement it makes")
    expect(out.deferred, [2], "and its row stays accepted for the next send")

    print("a statement an earlier send wrote with a reference per wiki:")
    three = [office(quals=span("2020-10-15", "2022-06-01"), id=n, source_lang=lang,
                    source_url=f"https://{lang}.wikipedia.org/wiki/X") for n, lang in ((1, "aa"), (2, "ab"), (3, "ac"))]
    old = plan.plan_person(PERSON, item(), three).data["claims"][0]
    old["references"] = [plan.reference(r["source_lang"], r["source_url"], 7) for r in three]
    old["id"] = GUID
    out = route.route(PERSON, item(old), [office(quals=span("2020-10-15", "2022-06-01"), id=4)])
    expect((out.lines, out.skipped), ([], [(4, "exists")]),
           "is already there: nothing is planned, so a ledger key without its extra references never resends it")
    citizen = {"id": f"{PERSON}$c", "rank": "normal", "references": old["references"],
               "mainsnak": {"snaktype": "value", "property": "P27",
                            "datavalue": {"type": "wikibase-entityid", "value": {"entity-type": "item", "id": STATE}}}}
    out = route.route(PERSON, {"lastrevid": 1, "claims": {"P27": [citizen]}},
                      [row("P27", {"entity-type": "item", "id": STATE}, id=5)])
    expect((out.lines, out.skipped), ([], [(5, "exists")]), "and the same for a value with no qualifiers")

    print("a batch:")
    line = f"+{PERSON}\tP39\t{OFFICE}\tP580\t+2001-00-00T00:00:00Z/9 /* t */"
    expect(route.validate([line]), [], "a `+` line is well-formed")
    expect(route.validate([line, line]) != [], True, "a line twice is refused")
    expect(route.validate([line, f"{PERSON}\tP39\t{OFFICE}\tP582\t+2003-00-00T00:00:00Z/9 /* t */"]) != [], True,
           "a statement both created and merged into is refused")
    switch = f"{qs.SWITCH}\t{PERSON}\tP569\t+1950-00-00T00:00:00Z/9\t+1950-03-04T00:00:00Z/11 /* t */"
    expect(route.validate([switch]), [], "a switch is well-formed")
    expect(route.validate([switch, switch.replace("03-04", "03-05")]) != [], True, "two switches of one value are refused")
    expect(route.validate([f"-STATEMENT\t{GUID} /* t */"]) != [], True, "a removal is refused in an add batch")
    expect(ledger.key(line) == ledger.key(line.replace(" /* t */", " /* u */")), True,
           "a line's ledger key leaves its summary out")

    print("reading a line back:")
    landed = claim(OFFICE, {"P580": {**day("2001-01-01"), "time": "+2001-00-00T00:00:00Z", "precision": 9}})
    expect(qs.live_lines([line], {PERSON: item(landed)}), [line], "a statement with the value and qualifiers is live")
    expect(qs.live_lines([line], {PERSON: item(claim(OFFICE))}), [], "the value alone is not that spell")
    expect(qs.live_lines([switch], {PERSON: born({**year, "time": "+1950-03-04T00:00:00Z", "precision": 11},
                                                 IMPORTED)}), [switch], "a switch is live once the new value is")

    print("what an edit says on Wikidata:")
    url = '"https://{}.wikipedia.org/w/index.php?title=X&oldid=1"'
    made = route.route(PERSON, item(), [office(quals=span("2020-10-15", "2022-06-01"))]).lines
    expect(len(made) == 1 and made[0].endswith(
        " /* [[User:Pudox/PEP|PEP coverage]]: add position held from Wikipedia (aa) */"), True,
           "a person line names the objective, the property and the source wiki, not the run")
    many = [f"+{PERSON}", "P27", OFFICE] + [c for w in "abcdefgh" for c in ("S4656", url.format(w * 2))]
    expect(qs.describe("peploop", many),
           "[[User:Pudox/PEP|PEP coverage]]: add country of citizenship from Wikipedia (aa, bb, cc, dd, ee, ff and 2 more)",
           "many source wikis are counted past the first few")
    expect(qs.describe("peploop", [qs.SWITCH, PERSON, "P569", "+1950", "+1950-03-04"]).endswith("refine date of birth"),
           True, "a switch refines its value")
    stale = f"{PERSON}\tP39\t{OFFICE} /* peploop: add position from aa.wikipedia (rev 7) */"
    expect(qs.stamp("peptree", stale).endswith(" /* [[User:Pudox/PEP|PEP coverage]]: "
                                                "classify a political position and its jurisdiction */"), True,
           "a line queued before is restamped when it goes out")
    expect(ledger.key(qs.stamp("peptree", stale)), ledger.key(stale), "and keeps its ledger key")
    removal = f"-STATEMENT\t{GUID} /* [[User:Pudox/PEP|PEP coverage]]: remove a statement: wrong office */"
    expect(qs.stamp("peploop", removal), removal, "a removal keeps the reason written for it")

    print(f"{len(failures)} failures")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
