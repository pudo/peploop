"""Pin what an accepted proposal turns into before anything is sent.

What the plan says is what reaches Wikidata, so this is where the three silent
failures are caught: a statement
whose qualifiers were dropped looks like a clean edit, a duplicate looks like a
clean edit, and a reference nobody can follow looks like a clean edit. None of
them raises, and all three are visible only by reading the payload.

`plan_claim` and `plan_person` are pure functions of an entity and some rows, so
none of this needs the network, a database or a credential. Run it as
`python -m peploop.check_plan` from the repository root.
"""

import sys
from typing import Any

from peploop import plan as planner
from peploop import prompt, propose, wikipedia

OFFICE = "Q0000001"
OTHER = "Q0000002"
PERSON = "Q0000009"
STATE = "Q0000003"
GUID = f"{PERSON}$0000-1111"
#: The one thing in this path that would otherwise reach the network:
#: `references` asks which item a language's Wikipedia is, and the real lookup
#: is a SPARQL query behind a seven-day cache. `ac` is left out on purpose, so
#: the case of a wiki Wikidata has no item for is pinned too.
EDITIONS = {"aa": "Q0000101", "ab": "Q0000102"}
wikipedia.edition_items = lambda: EDITIONS


def day(text: str) -> dict[str, Any]:
    """A day-precision time value, as `propose` writes one."""
    year, month, rest = text.split("-", 2)
    return {
        "time": f"+{year}-{month}-{rest}T00:00:00Z", "precision": 11, "timezone": 0,
        "before": 0, "after": 0, "calendarmodel": propose.CALENDAR,
    }


def row(prop: str, value: Any, quals: dict[str, Any] | None = None, **over: Any) -> dict[str, Any]:
    """One accepted proposal as `accepted_rows` hands it over."""
    base = {
        "id": over.pop("id", 1), "property": prop, "value": value, "qualifiers": quals,
        "source_lang": "aa", "source_url": "https://aa.wikipedia.org/wiki/X", "source_rev": 7,
    }
    base.update(over)
    return base


def office(qid: str = OFFICE, quals: dict[str, Any] | None = None, **over: Any) -> dict[str, Any]:
    """A P39 proposal for one office, with whatever span it carries."""
    return row("P39", {"entity-type": "item", "id": qid}, quals, **over)


def claim(qid: str, quals: dict[str, Any] | None = None, **over: Any) -> dict[str, Any]:
    """One P39 statement already on the item."""
    out: dict[str, Any] = {
        "id": over.pop("id", GUID), "rank": over.pop("rank", "normal"),
        "mainsnak": {"snaktype": "value", "property": "P39", "datatype": "wikibase-item",
                     "datavalue": {"type": "wikibase-entityid",
                                   "value": {"entity-type": "item", "id": qid}}},
    }
    if quals:
        out["qualifiers"] = {
            prop: [{"property": prop, "snaktype": "value", "datatype": "time",
                    "datavalue": {"type": "time", "value": value}}]
            for prop, value in quals.items()
        }
    out.update(over)
    return out


def item(*claims: dict[str, Any], **over: Any) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for one in claims:
        grouped.setdefault(one["mainsnak"]["property"], []).append(one)
    return {"lastrevid": over.pop("lastrevid", 4242), "claims": grouped, **over}


def span(start: str | None = None, end: str | None = None) -> dict[str, Any]:
    return {prop: day(text) for prop, text in (("P580", start), ("P582", end)) if text}


def cited_wikis(claim: dict[str, Any]) -> list[str]:
    return [snak["datavalue"]["value"]["id"] for ref in claim.get("references") or []
            for snak in ref["snaks"].get("P143", [])]


def refs(claim: dict[str, Any]) -> set[str]:
    return {prop for ref in claim.get("references") or [] for prop in ref["snaks"]}


def main() -> int:
    """Run every case and report what each one found."""
    failures: list[str] = []

    def expect(got: Any, want: Any, message: str) -> None:
        ok = got == want
        print(("  ok   " if ok else "  FAIL ") + message + ("" if ok else f" (got {got!r})"))
        if not ok:
            failures.append(message)

    print("a tenure the item does not record:")
    plan = planner.plan_person(PERSON, item(), [office(quals=span("2020-10-15", "2022-06-01"))])
    made = (plan.data or {}).get("claims", [])
    expect(len(made), 1, "one statement is created")
    expect(dict(plan.routes), {"new": 1}, "routed as new")
    expect(sorted((made[0].get("qualifiers") or {})), ["P580", "P582"], "carrying both endpoints")
    expect(made[0].get("qualifiers-order"), ["P580", "P582"], "and an explicit qualifier order")
    expect(refs(made[0]), {"P143", "P4656", "P813"},
           "with the wiki, the permanent revision url and the day it was read")
    url = made[0]["references"][0]["snaks"]["P4656"][0]["datavalue"]["value"]
    expect("oldid=7" in url, True, "and the url names the revision, not the page")

    print("two spells of one office:")
    rows = [office(quals=span("2004-12-03", "2008-11-21"), id=1),
            office(quals=span("2020-10-15", "2022-06-01"), id=2)]
    plan = planner.plan_person(PERSON, item(), rows)
    made = (plan.data or {}).get("claims", [])
    # The whole reason this path writes through the API and not QuickStatements.
    expect(len(made), 2, "stay two statements, not one carrying both starts")
    expect([sorted(c["qualifiers"]) for c in made], [["P580", "P582"]] * 2,
           "and each keeps its own dates")

    print("one spell attested twice:")
    rows = [office(quals=span("2020-10-15", "2022-06-01"), id=1),
            office(quals=span("2020-10-15", "2022-06-01"), id=2,
                   source_lang="ab", source_url="https://ab.wikipedia.org/wiki/X")]
    plan = planner.plan_person(PERSON, item(), rows)
    made = (plan.data or {}).get("claims", [])
    expect(len(made), 1, "is one statement, because the API de-duplicates nothing")
    expect(len(made[0]["references"]), 1, "citing one of the articles, never one reference per wiki")
    expect(plan.routes["merged"], 1, "and the second row is recorded as merged")
    rows = [office(quals=span("2020-10-15"), id=1, seed_lang="ab"),
            office(quals=span("2020-10-15"), id=2, seed_lang="ab",
                   source_lang="ab", source_url="https://ab.wikipedia.org/wiki/X")]
    made = planner.plan_person(PERSON, item(), rows).data["claims"]
    expect(cited_wikis(made[0]), ["Q0000102"],
           "the folded rows cite the home wiki, though the other row came first")

    print("which wiki a statement cites:")
    expect(prompt.wiki_order(["aa", "en", "ab", "ac"], "ab", {}, sizes={"aa": 10, "ac": 99}),
           ["en", "ab", "ac", "aa"], "for reading: English, the home languages, the rest longest first")
    expect(prompt.wiki_order(["aa", "en", "ab", "ac"], "ab", {}, home_first=True, sizes={"aa": 10, "ac": 99}),
           ["ab", "en", "ac", "aa"], "for citing: the home languages before English")
    expect(prompt.wiki_order(["aa", "aa", "ac"], None, {}), ["aa", "ac"],
           "each language once, ties in the order given")
    home = {"lang": "ab", "url": "https://ab.wikipedia.org/wiki/X", "rev": 3}
    english = {"lang": "en", "url": "https://en.wikipedia.org/wiki/X", "rev": 4}
    small = {"lang": "aa", "url": "https://aa.wikipedia.org/wiki/X", "rev": 5}
    large = {"lang": "ac", "url": "https://ac.wikipedia.org/wiki/X", "rev": 6}
    sizes = {"aa": 10, "ac": 99}

    def cites(*sources: dict[str, Any]) -> Any:
        one = office(quals={"_sources": list(sources)}, seed_lang="ab", article_chars=sizes)
        return planner.cited_source(one, item())
    expect(cites(english, small, home), home, "the home wiki where it attests the value")
    expect(cites(small, english), english, "English where the home wiki does not")
    expect(cites(small, large), large, "and otherwise the longest article")
    later = {**small, "rev": 9}
    expect(cites(small, later), small, "two revisions of one wiki: the first")
    made = planner.plan_person(PERSON, item(), [office(quals={**span("2020-10-15"), "_sources": [small, english, home]},
                                                       seed_lang="ab")]).data["claims"]
    expect(len(made[0]["references"]), 1, "one reference for a row three wikis attest")

    print("a tenure the item records without dates:")
    live = item(claim(OFFICE))
    plan = planner.plan_person(PERSON, live, [office(quals=span("1997-02-01", "2000-06-30"))])
    made = (plan.data or {}).get("claims", [])
    expect(dict(plan.routes), {"refine": 1}, "is a refinement, not a second statement")
    expect(made[0].get("id"), GUID, "sent back under the id of the statement it sharpens")
    expect(sorted(made[0].get("qualifiers") or {}), ["P580", "P582"], "now carrying the dates")
    expect(len(made[0].get("references") or []), 1, "and our reference, since it had none")
    sourced = {"snaks": {"P248": [{"snaktype": "value", "property": "P248",
                                   "datavalue": {"type": "wikibase-entityid", "value": {"id": "Q36578"}}}]}}
    live = item(claim(OFFICE, references=[sourced]))
    made = planner.plan_person(PERSON, live, [office(quals=span("1997-02-01", "2000-06-30"))]).data["claims"]
    expect(made[0].get("references"), [sourced],
           "one that already has a reference takes the dates and none of ours")

    print("two spells, and one undated statement to land on:")
    live = item(claim(OFFICE))
    rows = [office(quals=span("1998-07-20", "2002-07-19"), id=1),
            office(quals=span("2002-07-20", "2006-07-19"), id=2)]
    plan = planner.plan_person(PERSON, live, rows)
    made = (plan.data or {}).get("claims", [])
    expect(dict(plan.routes), {"refine": 1, "new": 1},
           "the first takes the undated statement, the second is a further term")
    expect([c.get("id") for c in made], [GUID, None], "one sent back under its id, one created")
    expect([c["qualifiers"]["P580"][0]["datavalue"]["value"]["time"][:5] for c in made],
           ["+1998", "+2002"], "each carrying its own start, neither lost")
    expect(len(made[1].get("references") or []), 1,
           "and the new one carries only its own reference")
    rows = [office(quals=span("1998-07-20", "2002-07-19"), id=1),
            office(quals=span("1998-07-20", "2002-07-19"), id=2, source_lang="bb")]
    plan = planner.plan_person(PERSON, live, rows)
    expect(dict(plan.routes), {"refine": 1, "merged": 1},
           "while the same spell from two wikis still merges into one")

    print("an undated statement that carries a term:")
    term = {"P2937": [{"property": "P2937", "snaktype": "value", "datatype": "wikibase-item",
                       "datavalue": {"type": "wikibase-entityid",
                                     "value": {"entity-type": "item", "id": "Q0000077"}}}]}
    live = item(claim(OFFICE, qualifiers=term))
    plan = planner.plan_person(PERSON, live, [office(quals=span("2003-01-01", "2012-12-31"))])
    expect(dict(plan.routes), {"termed": 1},
           "is a specific tenure, not a blank: nothing is written")
    expect(plan.data, {}, "and nothing is sent")
    planner._TERM_SPANS["Q0000077"] = {"P580": day("2020-08-19"), "P582": day("2025-03-18")}
    plan = planner.plan_person(PERSON, live, [office(quals={"P580": day("2025-04-28")})])
    expect(dict(plan.routes), {"new": 1},
           "but a spell outside the term the statement names is a further term, written new")
    plan = planner.plan_person(PERSON, live, [office(quals=span("2021-01-01", "2024-12-31"))])
    expect(dict(plan.routes), {"termed": 1}, "while one inside that term stays termed")
    planner._TERM_SPANS.clear()

    print("a tenure the item already dates:")
    live = item(claim(OFFICE, {"P580": day("1997-02-01")}))
    plan = planner.plan_person(PERSON, live, [office(quals=span("1999-01-01", "2000-06-30"))])
    expect(dict(plan.routes), {"exists": 1},
           "is never re-dated, because replacing a date is not this tool's to do")
    expect(plan.data, {}, "and nothing is sent")
    expect([reason for _id, reason in plan.skipped], ["exists"],
           "and the row is closed under the route that refused it")

    print("a further term of an office the item already dates:")
    live = item(claim(OFFICE, span("1996-01-01", "2000-01-01")))
    plan = planner.plan_person(PERSON, live, [office(quals=span("2004-12-03", "2008-11-21"))])
    made = (plan.data or {}).get("claims", [])
    # The gap this was written for: keyed on the office alone, a legislator's
    # every later term read as already recorded and was never written.
    expect(dict(plan.routes), {"new": 1}, "is a second statement, not 'exists'")
    expect(made[0].get("id") if made else "none", None, "created, not sent back under an id")

    print("a term the item records with a start and no end:")
    live = item(claim(OFFICE, span("2018-06-22")))
    plan = planner.plan_person(PERSON, live, [office(quals=span("2018-06-22", "2022-05-13"))])
    made = (plan.data or {}).get("claims", [])
    expect(dict(plan.routes), {"refine": 1}, "takes the end the article gives")
    expect(made[0].get("id"), GUID, "on the statement that is there")
    expect(sorted(made[0].get("qualifiers") or {}), ["P580", "P582"],
           "keeping the start it already had")
    live = item(claim(OFFICE, span("2018-06-03")))
    plan = planner.plan_person(PERSON, live, [office(quals=span("2018-06-22", "2022-05-13"))])
    expect(dict(plan.routes), {"exists": 1},
           "but a start that disagrees by days is a near miss, and nothing is touched")
    live = item(claim(OFFICE, span("2018-06-22", "2022-05-13")))
    year = {"P580": {**day("2018-01-01"), "precision": 9},
            "P582": {**day("2022-01-01"), "precision": 9}}
    plan = planner.plan_person(PERSON, live, [office(quals=year)])
    expect(dict(plan.routes), {"exists": 1},
           "and a year-precision spell inside a day-precision one adds nothing")

    print("a refinement QuickStatements cannot aim:")
    live = item(claim(OTHER, span("1990-01-01", "1994-01-01"), id=f"{PERSON}$dated"),
                claim(OTHER, id=f"{PERSON}$undated"))
    plan = planner.plan_person(PERSON, live, [office(OTHER, quals=span("2001-01-01"))])
    expect(dict(plan.routes), {planner.AMBIGUOUS: 1},
           "dates for the undated one of two statements: QS3 merges into the first by value, so none")
    expect(plan.data, {}, "and nothing is sent")
    live = item(claim(OTHER, id=f"{PERSON}$undated"))
    plan = planner.plan_person(PERSON, live, [office(OTHER, quals=span("2001-01-01"))])
    expect(dict(plan.routes), {"refine": 1}, "while the only statement for the office takes them")

    print("a date sharpened in place:")
    year = {"time": "+1950-00-00T00:00:00Z", "precision": 9, "timezone": 0,
            "before": 0, "after": 0, "calendarmodel": propose.CALENDAR}
    imported = {"snaks": {"P143": [{"snaktype": "value", "property": "P143",
                                    "datavalue": {"type": "wikibase-entityid", "value": {"id": "Q328"}}}]}}

    def born(*values: dict[str, Any]) -> dict[str, Any]:
        return {"lastrevid": 1, "claims": {"P569": [
            {"id": f"{PERSON}$b{i}", "rank": "normal", "references": [imported],
             "mainsnak": {"snaktype": "value", "property": "P569", "datavalue": {"type": "time", "value": v}}}
            for i, v in enumerate(values)]}}
    sharp = {**year, "time": "+1950-03-01T00:00:00Z", "precision": 11}
    plan = planner.plan_person(PERSON, born(year), [row("P569", sharp)])
    expect(dict(plan.routes), {"refine": 1}, "an imported year on one statement is sharpened in place")
    plan = planner.plan_person(PERSON, born(year, year), [row("P569", sharp)])
    expect(dict(plan.routes), {planner.AMBIGUOUS: 1}, "the same year twice: which one to switch is QS3's guess")

    print("a value the item contradicts:")
    birth = {"time": "+1950-03-01T00:00:00Z", "precision": 11, "timezone": 0,
             "before": 0, "after": 0, "calendarmodel": propose.CALENDAR}
    live = {"lastrevid": 1, "claims": {"P569": [
        {"rank": "normal", "mainsnak": {"snaktype": "value", "property": "P569",
         "datavalue": {"type": "time", "value": birth}}}]}}
    other = dict(birth, time="+1962-02-06T00:00:00Z")
    plan = planner.plan_person(PERSON, live, [row("P569", other)])
    expect(dict(plan.routes), {"conflict": 1}, "is a human's to-do, not an edit")
    expect(plan.data, {}, "and nothing is sent")
    expect([reason for _id, reason in plan.skipped], ["conflict"],
           "and the row is closed, so a send does not select it forever")

    print("a wiki Wikidata has no item for:")
    plan = planner.plan_person(PERSON, item(), [office(quals=span("2020-10-15"), source_lang="ac",
                                                    source_url="https://ac.wikipedia.org/wiki/X")])
    made = (plan.data or {}).get("claims", [])
    expect(refs(made[0]), {"P4656", "P813"},
           "is still a reference, just without the import-from")

    print(f"{len(failures)} failures")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
