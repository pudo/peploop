"""Pin what a missing office would be minted as, and every reason not to.

An item, once created, can only be undone by a deletion or a merge, and each
gate in `offices.guard` fails silently in the other direction: a floor counted
in rows instead of people, a description reading "judge of Q123", a body that
happens to be a construction brand. None of them raises; all of them are
visible only by reading the payload, so this reads it.

Everything checked is a pure function of a `Spec` and some records, so none of
it needs the network, a database or a credential. Run it as
`python -m peploop.check_mint` from the repository root.
"""

import sys
from dataclasses import replace
from collections import Counter
from typing import Any

from peploop import offices
from peploop.offices import Found, Siblings, Spec

STATE = "Q0000001"
PROVINCE = "Q0000002"
BODY = "Q0000003"
OLD = "Q0000004"
#: What the closure says reaches `Q4164871`: every archetype's parent.
CLOSURE = {shape.parent for shape in offices.ARCHETYPES.values()}
LABELS = {STATE: "Aland", PROVINCE: "Bray Province", BODY: "Supreme Tribunal of Aland"}


def entity(qid: str, label: str, *, p31: str | None = None, p17: str | None = None,
           aliases: tuple[str, ...] = ()) -> dict[str, Any]:
    """A `wbgetentities` record with just the fields the guard reads."""
    claims: dict[str, list[dict[str, Any]]] = {}
    for prop, value in (("P31", p31), ("P17", p17)):
        if value:
            claims[prop] = [{"rank": "normal", "mainsnak": {
                "snaktype": "value", "property": prop,
                "datavalue": {"type": "wikibase-entityid", "value": {"entity-type": "item", "id": value}}}}]
    return {
        "id": qid,
        "labels": {"en": {"language": "en", "value": label}},
        "aliases": {"en": [{"language": "en", "value": text} for text in aliases]} if aliases else {},
        "claims": claims,
    }


COURT = entity(BODY, "Supreme Tribunal of Aland", p31="Q43229", p17=STATE)
BRAY = entity(PROVINCE, "Bray Province", p17=STATE)


def judge(**over: Any) -> Spec:
    """A court-president office whose body and state check out."""
    base: dict[str, Any] = dict(
        ref="t/court-president", archetype="court_president",
        labels={"en": "President of the Supreme Tribunal"}, state_qid=STATE, body_qid=BODY,
        descriptions={"en": "president of Supreme Tribunal of Aland"},
    )
    base.update(over)
    return Spec(**base)


def governor(**over: Any) -> Spec:
    base: dict[str, Any] = dict(
        ref="t/governor-bray", archetype="governor", labels={"en": "Governor of Bray"},
        state_qid=STATE, jurisdiction_qid=PROVINCE, descriptions={"en": "governor of Bray Province"},
    )
    base.update(over)
    return Spec(**base)


def guard(spec: Spec, **over: Any) -> list[str]:
    """The guard with every input clean, so a case changes only what it tests."""
    args: dict[str, Any] = dict(
        holders=2, current_holders=1, single_seat_source_ok=False, duplicates=(),
        run_labels=(), body=COURT if spec.body_qid else None,
        jurisdiction=BRAY if spec.jurisdiction_qid else None, closure=CLOSURE,
        state_names=(LABELS[STATE],),
    )
    args.update(over)
    return offices.guard(spec, **args)


def dissolution(time: str, rank: str = "normal") -> dict[str, Any]:
    return {"rank": rank, "mainsnak": {"snaktype": "value", "property": "P576",
            "datavalue": {"type": "time", "value": {"time": time, "precision": 9}}}}


def check_subdivisions(expect: Any, merged: dict[str, Any]) -> None:
    """Both P150 readers drop a subdivision whose own item says it was dissolved."""
    from peploop import mint, wikidata

    other = "Q0000005"
    world = {
        STATE: {"id": STATE, "claims": {"P150": [
            {"rank": "normal", "mainsnak": {"datavalue": {"value": {"id": q}}}} for q in (PROVINCE, other)]}},
        PROVINCE: merged,
        other: entity(other, "Cray Province", p17=STATE),
    }
    real = wikidata.fetch_items
    wikidata.fetch_items = lambda qids, props="": {q: world[q] for q in qids if q in world}
    try:
        expect([q for q, _l in offices.subdivisions(STATE)], [other],
               "the state's subdivisions leave out a merged province its P150 still lists")
        expect(mint._subdivisions(STATE), [other], "and so does the census expansion")
        expect(mint._subdivisions(STATE, dissolved=True), [PROVINCE, other],
               "but categorize may still name it, so a mention of it is not scoped to the state")
    finally:
        wikidata.fetch_items = real


def statement(data: dict[str, Any], prop: str) -> list[str]:
    return [claim["mainsnak"]["datavalue"]["value"]["id"]
            for claim in data["claims"] if claim["mainsnak"]["property"] == prop]


def main() -> int:
    """Run every case and report what each one found."""
    failures: list[str] = []

    def expect(got: Any, want: Any, message: str) -> None:
        ok = got == want
        print(("  ok   " if ok else "  FAIL ") + message + ("" if ok else f" (got {got!r})"))
        if not ok:
            failures.append(message)

    print("the evidence floor counts people, not rows:")
    rows = [{"person": "Q9", "current": True}] * 3
    held = offices.distinct_holders(rows)
    current = offices.distinct_holders(r for r in rows if r["current"])
    expect(held, 1, "three mentions of one person are one holder")
    expect(guard(judge(archetype="minister", body_qid=None), holders=held, current_holders=current),
           ["holders/1"], "and one holder fails the floor of a many-seat office")
    two = rows + [{"person": "Q8", "current": False}, {"person": None, "current": True}]
    expect(offices.distinct_holders(two), 2, "a second person counts, a row naming nobody does not")
    expect(guard(judge(), current_holders=0), ["current/0"], "an office nobody holds now is refused")

    print("a one-seat office:")
    expect(guard(governor(), holders=1, single_seat_source_ok=True), [],
           "passes on its one current holder plus an official source")
    expect(guard(governor(), holders=1), ["holders/1"], "and fails on the holder alone")
    expect(guard(judge(archetype="legislator", descriptions={"en": "member of Supreme Tribunal of Aland"}),
                 holders=1, single_seat_source_ok=True),
           ["holders/1"], "a source does not lower the floor of a many-seat office")

    print("text that leaks an identifier:")
    expect(guard(judge(descriptions={"en": f"president of {BODY}"})), ["qid-in-description/en"],
           "a QID in a description is refused")
    expect(offices.describe(judge(), LABELS), "president of the Supreme Tribunal of Aland",
           "describe fills the template from resolved labels")
    expect(offices.describe(judge(), {STATE: "Aland"}), None,
           "and gives nothing rather than a QID when a label is missing")
    expect(offices.describe(governor(), {PROVINCE: PROVINCE}), None,
           "or when the label it resolved is itself a QID")
    expect(guard(judge(descriptions={})), ["description/en"], "an office with no description is refused")
    expect(guard(judge(), langs=("xx",)), ["label/xx"], "and one missing a label in a state language")

    print("the body:")
    expect(guard(judge()), [], "a court the office is named after passes")
    brand = entity(BODY, "Hormigones Tribunal", p31="Q43229")
    expect(guard(judge(labels={"en": "President of the Court of Appeal"}), body=brand),
           [f"body-word/{BODY}"], "a body sharing no content word with the office is refused")
    expect(guard(judge(labels={"en": "President of Aland"}), body=entity(BODY, "Government of Aland")),
           [f"body-word/{BODY}"], "sharing only a role word and the state's name is no agreement")
    expect(guard(judge(), body=entity(BODY, "Supreme Tribunal", p31="Q294414")),
           [f"body-is-position/{BODY}"], "a body that is itself an office is refused")
    expect(guard(judge(), body=entity(BODY, "Supreme Tribunal", p17="Q0000099")),
           [f"body-state/{BODY}"], "as is a body of another state")
    expect(guard(judge(), body=None), [f"body/{BODY}"], "and a body that did not resolve")
    expect(guard(judge(labels={"en": "Supreme Tribunal of Aland"})), [f"office-is-body/{BODY}"],
           "an office labelled as its own body is the body, not a seat in it")

    print("the jurisdiction:")
    expect(guard(governor(), jurisdiction=entity(PROVINCE, "Bray", p17="Q0000099")),
           [f"jurisdiction-state/{PROVINCE}"], "a subdivision of another state is refused")
    expect(guard(governor(), jurisdiction=None), [f"jurisdiction/{PROVINCE}"],
           "as is one that did not resolve")

    print("a dissolved jurisdiction:")
    merged = {**BRAY, "claims": {**BRAY["claims"], "P576": [dissolution("+2025-00-00T00:00:00Z")]}}
    expect(offices.dissolved(merged), True, "a province merged in 2025 is dissolved")
    expect(offices.dissolved({"claims": {"P576": [dissolution("+2999-01-01T00:00:00Z")]}}), False,
           "a dissolution still ahead is not")
    expect(offices.dissolved({"claims": {"P576": [dissolution("+2025-00-00T00:00:00Z", "deprecated")]}}),
           False, "nor a deprecated one")
    expect(offices.dissolved({"claims": {"P576": [{"rank": "normal", "mainsnak": {"snaktype": "somevalue"}}]}}),
           True, "and one of unknown date is")
    expect(guard(governor(), jurisdiction=merged), [f"jurisdiction-dissolved/{PROVINCE}"],
           "a governorship of a merged province is refused for it, whoever is said to hold it")
    expect(guard(governor(), jurisdiction=merged, regions=set())[0], f"jurisdiction-dissolved/{PROVINCE}",
           "ahead of the level check, which says less")
    check_subdivisions(expect, merged)

    print("label languages follow the state's own offices:")
    measured = Siblings(offices=30, label_langs=Counter({"en": 30, "fr": 28, "rn": 0}))
    expect(offices.label_langs(measured, ("en", "fr", "rn")), ["en", "fr"],
           "a language none of the state's offices is labelled in is not required")
    expect(guard(judge(labels={"en": "President of the Supreme Tribunal", "fr": "président du Tribunal"}),
                 langs=offices.label_langs(measured, ("en", "fr", "rn"))), [],
           "so an office labelled in English and French passes")
    half = Siblings(offices=30, label_langs=Counter({"en": 30, "rn": 15}))
    expect(offices.label_langs(half, ("en", "rn")), ["en", "rn"], "half the siblings is enough to require it")
    expect(offices.label_langs(Siblings(), ("en", "fr", "rn")), ["en", "fr", "rn"],
           "with no siblings to measure, every state language is required")

    print("one-seat archetypes:")
    expect(guard(judge(archetype="agency_head"), holders=1, single_seat_source_ok=True), [],
           "an agency has one head at a time, so the census can stand in for a second holder")
    expect(guard(judge(archetype="speaker", labels={"en": "President of the Senate of Aland"},
                       descriptions={"en": "presiding officer of the Senate"}),
                 holders=1, single_seat_source_ok=True,
                 body=entity(BODY, "Senate of Aland", p31="Q43229", p17=STATE)), [],
           "as does a chamber's speaker")
    data = offices.entity_data(judge(archetype="speaker"))
    expect((statement(data, "P279"), statement(data, "P2389"), statement(data, "P361")),
           (["Q1758037"], [BODY], []), "a speaker is kind speaker, naming its chamber under P2389")

    print("postings between states:")
    for label in ("Ambassador of Aland to Bray", "Embajador de Aland en Bray",
                  "Ambassadeur d'Aland au Bray"):
        expect(guard(judge(archetype="agency_head", body_qid=None, labels={"en": label},
                           descriptions={"en": "x"})),
               ["bilateral"], f"{label!r} is refused")
    expect(offices.bilateral("Ambassador-at-large"), False, "an ambassador-at-large is not a posting")

    print("duplicates:")
    hit = Found(qid="Q77", label_match=True, country_qids=(STATE,), country_match=True,
                types=frozenset({"Q294414"}))
    expect(guard(judge(), duplicates=[hit]), ["duplicate/Q77"], "a live match blocks")
    expect(guard(judge(), run_labels=["president of the supreme tribunal"]), ["run-duplicate"],
           "as does another candidate of this run with the same folded label")
    expect(offices.duplicate_of([replace(hit, types=frozenset({offices.LIST_ARTICLE}))]), None,
           "a pure list article is not a duplicate")
    expect(offices.duplicate_of([replace(hit, types=frozenset({offices.LIST_ARTICLE, "Q294414"}))]),
           "Q77", "but a list that is also something else is")
    expect(offices.duplicate_of([replace(hit, types=frozenset({"Q5"}))]), None,
           "a human carrying the office as an alias is not")
    expect(offices.duplicate_of([replace(hit, country_match=False, country_qids=("Q0000099",))]),
           None, "the same title in another state is another office")
    expect(offices.duplicate_of([replace(hit, country_match=False, country_qids=())]), "Q77",
           "a match that names no state at all still blocks")
    expect(offices.duplicate_of([replace(hit, label_match=False)]), None,
           "and a hit whose name does not match is just a search result")

    print("shape:")
    expect(guard(judge(parent="Q4164871")), ["untyped"], "an office that never says which kind is refused")
    expect(guard(judge(archetype="central_committee_member")), ["archetype/central_committee_member"],
           "a membership recorded as P463 on the body has no archetype, so it is never minted")
    print("the level of polity an office governs:")
    mayor = lambda **kw: governor(archetype="mayor", labels={"en": "Mayor of Bray"},
                                  descriptions={"en": "mayor of Bray"}, **kw)
    expect(guard(mayor(jurisdiction_qid=None), regions={PROVINCE}), ["jurisdiction-level/municipality"],
           "a mayor that fell back to the state is refused")
    expect(guard(mayor(), regions={PROVINCE}), ["jurisdiction-level/municipality"],
           "and so is one scoped to a first-level subdivision, the department its town is in")
    expect(guard(governor(), regions={PROVINCE}), [], "a governor of a first-level subdivision passes")
    expect(guard(governor(jurisdiction_qid=None), regions={PROVINCE}), ["jurisdiction-level/region"],
           "but a governor scoped to the state does not")
    expect(guard(mayor()), [], "without the state's subdivisions the level is not judged")
    expect(guard(judge(parent="Q12737077")), ["not-an-office/Q12737077"], "an occupation is not a kind of office")
    expect(guard(judge(parent="Q0000050")), ["unreached/Q0000050"], "nor is a class the closure never reaches")
    expect(offices.shape_defects(judge(parent="Q0000050"), lambda qid: qid == "Q0000050"), [],
           "the closure can be a live callable")
    expect(guard(judge(metaclass="Q114962596")), ["metaclass/Q114962596"],
           "a current office is not minted as a historical one")

    print("the payload:")
    data = offices.entity_data(governor(aliases={"en": ["Bray Governor"]}, replaces=OLD))
    expect("id" in data, False, "no id, so the edit creates")
    expect(any("references" in claim for claim in data["claims"]), False, "no references on structural claims")
    expect([claim["mainsnak"]["property"] for claim in data["claims"]],
           ["P31", "P279", "P17", "P1001", "P1365"], "the claims an office is made of, in order")
    expect((statement(data, "P31"), statement(data, "P279"), statement(data, "P17"), statement(data, "P1001")),
           (["Q294414"], ["Q132050"], [STATE], [PROVINCE]),
           "typed public office, kind governor, of the state, governing the province")
    expect(data["labels"], {"en": {"language": "en", "value": "Governor of Bray"}}, "labels in Wikibase form")
    expect(data["aliases"], {"en": [{"language": "en", "value": "Bray Governor"}]}, "and aliases")
    snak = data["claims"][0]["mainsnak"]
    expect(snak["datavalue"]["type"], "wikibase-entityid", "snaks shaped as apply writes them")
    data = offices.entity_data(judge())
    expect(statement(data, "P1001"), [STATE], "a national office governs the state")
    expect(statement(data, "P2389"), [BODY], "and sits in its body through the archetype's property")
    offices.ARCHETYPES["t_unscoped"] = offices.Archetype("Q484876", description="head of {body}", scoped=False)
    try:
        data = offices.entity_data(judge(archetype="t_unscoped"))
        expect(statement(data, "P1001"), [], "an unscoped office carries no P1001")
    finally:
        del offices.ARCHETYPES["t_unscoped"]

    print("shape follows the state's own offices:")
    siblings = Siblings(
        metaclass_by_parent={"Q132050": Counter({"Q4164871": 3, "Q294414": 1})},
        metaclasses=Counter({"Q17279032": 5, "Q294414": 2}),
    )
    expect(offices.metaclass_for(siblings, "Q132050"), "Q4164871", "siblings of the same kind decide first")
    expect(offices.metaclass_for(siblings, "Q83307"), "Q17279032", "then the state's usual metaclass")
    expect(offices.metaclass_for(Siblings(), "Q83307"), "Q294414", "then public office")
    tied = Siblings(metaclass_by_parent={"Q83307": Counter({"Q4164871": 2, "Q294414": 2})},
                    metaclasses=Counter({"Q17279032": 3}))
    expect(offices.metaclass_for(tied, "Q83307"), "Q17279032", "a tie among siblings falls through")
    historic = Siblings(metaclasses=Counter({"Q114962596": 9, "Q4164871": 1}))
    expect(offices.metaclass_for(historic, "Q83307"), "Q4164871", "and a historical metaclass never wins")
    narrow = Siblings(parents={"governor": Counter({"Q0000060": 5, "Q132050": 1})})
    expect(offices.parent_for(narrow, "governor"), "Q0000060", "siblings agreeing on a narrower kind win")
    split = Siblings(parents={"governor": Counter({"Q0000060": 3, "Q132050": 2})})
    expect(offices.parent_for(split, "governor"), "Q132050", "below two thirds, the archetype's parent")
    lone = Siblings(parents={"governor": Counter({"Q0000060": 1})})
    expect(offices.parent_for(lone, "governor"), "Q132050", "and one sibling is not agreement")

    print("a live search hit, judged:")
    office = entity("Q70", "President of Aland", p31="Q294414", p17=STATE,
                    aliases=("Head of State of Aland",))
    office["labels"]["xx"] = {"language": "xx", "value": "Presidénte de Aland"}
    hit = offices.found_from(office, "President of Aland", STATE, {})
    expect((hit.qid, hit.label_match, hit.country_match, hit.country_qids, hit.types),
           ("Q70", True, True, (STATE,), frozenset({"Q294414"})),
           "a hit labelled as searched, of the state, matches on both")
    expect("head of state of aland" in hit.names and "presidente de aland" in hit.names, True,
           "its names are every label and alias, in every language, folded")
    expect(offices.found_from(office, "presidente  de ALAND", STATE, {}).label_match, True,
           "the label matches folded: case, diacritics and spacing")
    expect(offices.found_from(office, "The President of Aland", STATE, {}).label_match, True,
           "and with a leading article dropped")
    expect(offices.found_from(office, "President of Bray", STATE, {}).label_match, False,
           "a different office of the same state does not match")
    scoped = entity("Q71", "Governor of Bray", p31="Q294414")
    scoped["claims"]["P1001"] = entity("x", "x", p17=PROVINCE)["claims"]["P17"]
    expect(offices.found_from(scoped, "Governor of Bray", STATE, {PROVINCE: [STATE]}).country_match,
           True, "an office of a province matches the state one hop up")
    expect(offices.found_from(scoped, "Governor of Bray", STATE, {PROVINCE: ["Q0000099"]}).country_match,
           False, "but not when the province belongs to another state")
    expect(offices.found_from(scoped, "Governor of Bray", STATE, {}).country_qids, (PROVINCE,),
           "and its P1001 is what it names")
    deprecated = entity("Q72", "President of Aland", p31="Q5", p17=STATE)
    deprecated["claims"]["P31"][0]["rank"] = "deprecated"
    expect(offices.found_from(deprecated, "President of Aland", STATE, {}).types, frozenset(),
           "a deprecated type is not read")
    preferred = entity("Q73", "President of Aland", p31="Q4164871", p17=STATE)
    preferred["claims"]["P31"].insert(0, {**preferred["claims"]["P31"][0], "rank": "preferred",
        "mainsnak": {**preferred["claims"]["P31"][0]["mainsnak"],
                     "datavalue": {"value": {"id": "Q294414"}}}})
    expect(offices.found_from(preferred, "President of Aland", STATE, {}).types,
           frozenset({"Q4164871", "Q294414"}), "but a preferred one does not hide the normal ones")

    print("a kind of office is not a duplicate of a state's seat:")
    generic = entity("Q74", "president of the senate", p31="Q4164871")
    # The search runs per label and alias, and an article's bare "President of
    # the Senate" is an alias of the state's seat.
    seen = offices.found_from(generic, "President of the Senate", STATE, {})
    expect((seen.label_match, seen.country_qids), (True, ()),
           "a stateless 'president of the senate' matches the seat's bare alias")
    expect(offices.duplicate_of([seen]), "Q74", "and, read as an office, it blocks")
    expect(offices.duplicate_of([replace(seen, is_class=True)]), None,
           "but not once other offices are seen to subclass it")
    stateless = offices.found_from(entity("Q75", "President of the Senate", p31="Q4164871",
                                          aliases=("President of the Senate of Aland",)),
                                   "President of the Senate", STATE, {})
    expect(offices.duplicate_of([replace(seen, is_class=True), stateless]), "Q75",
           "while a stateless item of the same office, which nothing subclasses, still blocks")
    world = {"Q76": entity("Q76", "President of the Senate of Bray", p31="Q294414"),
             "Q77": entity("Q77", "Senate rules", p31="Q7748")}
    items = lambda qs: {q: world[q] for q in qs}
    expect(offices.is_office_class("Q74", children=lambda _q: ["Q77", "Q76"], items=items), True,
           "an item one office subclasses is a kind of office")
    expect(offices.is_office_class("Q74", children=lambda _q: ["Q77"], items=items), False,
           "one only a non-office subclasses is not")
    expect(offices.is_office_class("Q74", children=lambda _q: [], items=items), False,
           "nor one nothing subclasses")

    print(f"{len(failures)} failures")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
