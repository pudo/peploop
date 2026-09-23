"""Pin what an accepted proposal turns into before anything is sent.

This is the only module that changes a public database, and it was the only one
with no check. The three failures it guards against are all silent: a statement
whose qualifiers were dropped looks like a clean edit, a duplicate looks like a
clean edit, and a reference nobody can follow looks like a clean edit. None of
them raises, and all three are visible only by reading the payload.

`plan_claim` and `plan_person` are pure functions of an entity and some rows, so
none of this needs the network, a database or a credential. Run it as
`python -m peploop.check_apply` from the repository root.
"""

import sys
from typing import Any

from peploop import apply, propose, wikipedia

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
    plan = apply.plan_person(PERSON, item(), [office(quals=span("2020-10-15", "2022-06-01"))])
    made = (plan.data or {}).get("claims", [])
    expect(len(made), 1, "one statement is created")
    expect(dict(plan.routes), {"new": 1}, "routed as new")
    expect(sorted((made[0].get("qualifiers") or {})), ["P580", "P582"], "carrying both endpoints")
    expect(made[0].get("qualifiers-order"), ["P580", "P582"], "and an explicit qualifier order")
    expect(refs(made[0]), {"P143", "P4656", "P813"},
           "with the wiki, the permanent revision url and the day it was read")
    url = made[0]["references"][0]["snaks"]["P4656"][0]["datavalue"]["value"]
    expect("oldid=7" in url, True, "and the url names the revision, not the page")
    expect(plan.baserevid, 4242, "against the revision the decision was made on")
    expect("position" in plan.summary and "aa.wikipedia" in plan.summary, True,
           "and a summary naming the property and the wiki")

    print("two spells of one office:")
    rows = [office(quals=span("2004-12-03", "2008-11-21"), id=1),
            office(quals=span("2020-10-15", "2022-06-01"), id=2)]
    plan = apply.plan_person(PERSON, item(), rows)
    made = (plan.data or {}).get("claims", [])
    # The whole reason this path writes through the API and not QuickStatements.
    expect(len(made), 2, "stay two statements, not one carrying both starts")
    expect([sorted(c["qualifiers"]) for c in made], [["P580", "P582"]] * 2,
           "and each keeps its own dates")

    print("one spell attested twice:")
    rows = [office(quals=span("2020-10-15", "2022-06-01"), id=1),
            office(quals=span("2020-10-15", "2022-06-01"), id=2,
                   source_lang="ab", source_url="https://ab.wikipedia.org/wiki/X")]
    plan = apply.plan_person(PERSON, item(), rows)
    made = (plan.data or {}).get("claims", [])
    expect(len(made), 1, "is one statement, because the API de-duplicates nothing")
    expect(len(made[0]["references"]), 2, "carrying both articles as references")
    expect(plan.routes["merged"], 1, "and the second row is recorded as merged")

    print("a tenure the item records without dates:")
    live = item(claim(OFFICE))
    plan = apply.plan_person(PERSON, live, [office(quals=span("1997-02-01", "2000-06-30"))])
    made = (plan.data or {}).get("claims", [])
    expect(dict(plan.routes), {"refine": 1}, "is a refinement, not a second statement")
    expect(made[0].get("id"), GUID, "sent back under the id of the statement it sharpens")
    expect(sorted(made[0].get("qualifiers") or {}), ["P580", "P582"], "now carrying the dates")

    print("a tenure the item already dates:")
    live = item(claim(OFFICE, {"P580": day("1997-02-01")}))
    plan = apply.plan_person(PERSON, live, [office(quals=span("1999-01-01", "2000-06-30"))])
    expect(dict(plan.routes), {"exists": 1},
           "is never re-dated, because replacing a date is not this tool's to do")
    expect(plan.data, {}, "and nothing is sent")

    print("which statement a refinement lands on:")
    live = item(claim(OTHER, {"P580": day("1990-01-01")}, id=f"{PERSON}$dated"),
                claim(OTHER, id=f"{PERSON}$undated"))
    plan = apply.plan_person(PERSON, live, [office(OTHER, quals=span("2001-01-01"))])
    made = (plan.data or {}).get("claims", [])
    expect(made[0].get("id") if made else None, f"{PERSON}$undated",
           "the one saying nothing, not the one already dated")

    print("a value the item contradicts:")
    birth = {"time": "+1950-03-01T00:00:00Z", "precision": 11, "timezone": 0,
             "before": 0, "after": 0, "calendarmodel": propose.CALENDAR}
    live = {"lastrevid": 1, "claims": {"P569": [
        {"rank": "normal", "mainsnak": {"snaktype": "value", "property": "P569",
         "datavalue": {"type": "time", "value": birth}}}]}}
    other = dict(birth, time="+1962-02-06T00:00:00Z")
    plan = apply.plan_person(PERSON, live, [row("P569", other)])
    expect(dict(plan.routes), {"conflict": 1}, "is a human's to-do, not an edit")
    expect(plan.data, {}, "and nothing is sent")

    print("a label the item already has:")
    live = {"lastrevid": 1, "claims": {}, "labels": {"aa": {"language": "aa", "value": "X"}}}
    plan = apply.plan_person(PERSON, live, [row("label:aa", {"text": "Y"})])
    expect([reason for _id, reason in plan.skipped], ["term already on the item"],
           "is left alone, because a label is filled in and never replaced")

    print("a wiki Wikidata has no item for:")
    plan = apply.plan_person(PERSON, item(), [office(quals=span("2020-10-15"), source_lang="ac",
                                                    source_url="https://ac.wikipedia.org/wiki/X")])
    made = (plan.data or {}).get("claims", [])
    expect(refs(made[0]), {"P4656", "P813"},
           "is still a reference, just without the import-from")

    print("finding back the statement a row produced:")
    live = item(claim(OFFICE, {"P580": day("1996-01-01")}, id="A"),
                claim(OFFICE, {"P580": day("2000-01-01")}, id="B"))
    value = {"entity-type": "item", "id": OFFICE}
    fp = lambda text: {"P580": [{"datavalue": {"value": day(text)}}]}  # noqa: E731
    expect(apply._find_guid(live, "P39", value, fp("1996-01-01")), "A",
           "two spells of one office are told apart by their dates")
    expect(apply._find_guid(live, "P39", value, fp("2000-01-01")), "B",
           "and each row is recorded under the statement it made")
    expect(apply._find_guid(live, "P39", value, fp("2010-01-01"), {"A"}), "B",
           "a spell the item words differently takes one nothing else claimed")

    print("what every edit carries:")
    plan = apply.plan_person(PERSON, item(), [office(quals=span("2020-10-15"))])
    payload = apply.write_payload(plan, "TOKEN+\\")
    expect("bot" in payload, False,
           "no bot key at all, because its presence is what asks for the flag")
    expect(payload.get("assert"), "user",
           "an assertion, so a lapsed session fails instead of editing as an IP")
    expect(payload.get("baserevid"), 4242, "the revision the decision was made against")
    expect(payload.get("maxlag"), apply.MAXLAG, "and a maxlag the site can push back with")
    expect("toollabs:editgroups" in payload["summary"], True,
           "a batch marker, so a bad run is revertable in one action")

    print(f"{len(failures)} failures")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
