"""Pin what the policy decides, one fabricated case per rule, offline.

The policy is the gate that replaced a human, so every rule in it is a way of
being wrong that nobody will see: a rule that never fires lets its class of
error through, and a rule that fires too early swallows the rows a later one
was written for. Each case below is the smallest proposal that one rule, and
only that rule, decides; the last cases are the ones no rule touches, which
must come out `pending` before a verifier has answered and `accepted` after.

No network, no key, no database: a case is a hand-built entity and a
hand-built row. Run it as `python -m peploop.check_policy` from the
repository root.
"""

import sys
from datetime import date
from typing import Any

from peploop import offices, policy, positions, propose

OFFICE = "Q0000001"
STATE = "Q0000003"
OTHER_STATE = "Q0000004"
#: A day well inside the run, so the scope arithmetic has a fixed reference.
TODAY = date(2026, 6, 15)


def time(text: str) -> dict[str, Any]:
    """A time value at the precision its text carries."""
    value = propose.time_value(text)
    assert value is not None, text
    return value


def claim(prop: str, value: dict[str, Any], references: list[dict[str, Any]] | None = None,
          rank: str = "normal") -> dict[str, Any]:
    """One statement as `wbgetentities` returns it, with optional references."""
    return {
        "rank": rank,
        "mainsnak": {"property": prop, "snaktype": "value",
                     "datavalue": {"type": "time" if "time" in value else "wikibase-entityid",
                                   "value": value}},
        "references": references or [],
    }


def item(*claims: dict[str, Any]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for one in claims:
        grouped.setdefault(one["mainsnak"]["property"], []).append(one)
    return {"claims": grouped}


def office(**over: Any) -> dict[str, Any]:
    """A `position` row for an office of the run's own state, unremarkable."""
    row: dict[str, Any] = {
        "qid": OFFICE, "label": "an office", "country_qid": STATE,
        "jurisdiction_qid": STATE, "sources": ["descent", "usage"],
        "not_office": False, "holders": None, "holders_by_country": None,
        "instance_count": None, "subclass_count": None, "held_subclasses": None,
        "inception": None, "abolished": None, "diplomatic": None, "sender_qid": None,
        "scope_qualifier": None, "first_held_year": None, "polity_inception_year": None,
    }
    row.update(over)
    return row


def case(prop: str = "P39", value: dict[str, Any] | None = None, **over: Any) -> policy.Case:
    """A proposal that clears every rule: a dated, confident, quoted tenure."""
    fields: dict[str, Any] = dict(
        property=prop,
        value=value or {"entity-type": "item", "id": OFFICE},
        qualifiers={"P580": time("2018-06-22"), "P582": time("2022-05-13"),
                    "_sources": [{"lang": "aa", "quote": "was in office"}]},
        proposed="new",
        quote="was in office",
        lang="aa",
        entity=item(),
        extracted={"birth_date": [{"value": "1970"}]},
        state_qid=STATE,
        seed_lang="aa",
        resolution={"kind": "same-office", "confidence": "high", "qid": OFFICE},
        position=office(),
        verification=None,
        today=TODAY,
    )
    fields.update(over)
    return policy.Case(**fields)


def main() -> int:
    failures = 0

    def check(name: str, got: policy.Disposition, status: str, rule: str) -> None:
        nonlocal failures
        ok = got.status == status and got.rule == rule
        failures += 0 if ok else 1
        mark = "ok  " if ok else "FAIL"
        detail = "" if ok else f"  (got {got.status} by {got.rule})"
        print(f"  {mark} {name}{detail}")

    print("what belongs in the write path at all:")
    check("the articles' own dates set a person aside the item did not",
          policy.decide(case(extracted={"death_date": [{"value": "1901-03-02"}]})),
          policy.SKIPPED, "extracted_out_of_scope")
    check("a coarse extracted date that could still be recent keeps them",
          policy.decide(case(extracted={"birth_date": [{"value": "1936"}]})),
          policy.PENDING, "unverified")
    check("a value nobody quoted for has nothing to verify",
          policy.decide(case(qualifiers={"P580": time("2018"),
                                         "_sources": [{"lang": "aa", "quote": None}]})),
          policy.SKIPPED, "no_quote")
    check("a tenure whose end is still to come is a schedule, not a record",
          policy.decide(case(qualifiers={"P580": time("2024-01-01"), "P582": time("2027-12-31"),
                                         "_sources": [{"lang": "aa", "quote": "q"}]})),
          policy.SKIPPED, "future_date")
    check("and so is a start still to come",
          policy.decide(case(qualifiers={"P580": time("2026-08-07"),
                                         "_sources": [{"lang": "aa", "quote": "q"}]})),
          policy.SKIPPED, "future_date")
    check("a year that has begun is not in the future",
          policy.decide(case(qualifiers={"P580": time("2026"),
                                         "_sources": [{"lang": "aa", "quote": "q"}]})),
          policy.PENDING, "unverified")

    print("dates:")
    check("a date only a minor wiki gives is skipped",
          policy.decide(case("P569", time("1970-01-02"),
                             qualifiers={"_sources": [{"lang": "zz", "quote": "born"}]})),
          policy.SKIPPED, "minor_wiki_only")
    check("the same date from the seed language passes",
          policy.decide(case("P569", time("1970-01-02"),
                             qualifiers={"_sources": [{"lang": "aa", "quote": "born"}]})),
          policy.PENDING, "unverified")
    check("two minor wikis agreeing pass",
          policy.decide(case("P569", time("1970-01-02"),
                             qualifiers={"_sources": [{"lang": "zz", "quote": "born"},
                                                      {"lang": "yy", "quote": "born"}]})),
          policy.PENDING, "unverified")
    check("two articles giving different days are both skipped",
          policy.decide(case("P569", time("1970-01-02"),
                             qualifiers={"_sources": [{"lang": "aa", "quote": "born"}]},
                             siblings=[(time("1970-01-03"), "new")])),
          policy.SKIPPED, "contested")
    check("a sibling agreeing at the precision it has is no dispute",
          policy.decide(case("P569", time("1970-01-02"),
                             qualifiers={"_sources": [{"lang": "aa", "quote": "born"}]},
                             siblings=[(time("1970"), "new")])),
          policy.PENDING, "unverified")
    check("a sibling a rule already threw out is no dispute either",
          policy.decide(case("P569", time("1970-01-02"),
                             qualifiers={"_sources": [{"lang": "aa", "quote": "born"}]},
                             siblings=[(time("1971-01-02"), propose.FILTERED)])),
          policy.PENDING, "unverified")
    check("a second citizenship is not a dispute",
          policy.decide(case("P27", {"entity-type": "item", "id": STATE},
                             qualifiers={"_basis": "explicit",
                                         "_sources": [{"lang": "aa", "quote": "q"}]},
                             siblings=[({"entity-type": "item", "id": OTHER_STATE}, "new")])),
          policy.PENDING, "unverified")
    sourced = claim("P569", time("1970"), references=[{"snaks": {"P248": []}}])
    imported = claim("P569", time("1970"), references=[{"snaks": {"P143": []}}])
    check("a refinement over somebody else's citation is skipped",
          policy.decide(case("P569", time("1970-01-02"), proposed="refine",
                             entity=item(sourced),
                             qualifiers={"_sources": [{"lang": "aa", "quote": "born"}]})),
          policy.SKIPPED, "refine_over_sourced")
    check("a refinement over an import-only statement passes",
          policy.decide(case("P569", time("1970-01-02"), proposed="refine",
                             entity=item(imported),
                             qualifiers={"_sources": [{"lang": "aa", "quote": "born"}]})),
          policy.PENDING, "unverified")

    print("citizenship:")
    home = {"entity-type": "item", "id": STATE}
    abroad = {"entity-type": "item", "id": OTHER_STATE}
    demonym = {"_basis": "demonym", "_sources": [{"lang": "aa", "quote": "a politician"}]}
    explicit = {"_basis": "explicit", "_sources": [{"lang": "aa", "quote": "citizen of"}]}
    check("a demonym of the run's own state passes",
          policy.decide(case("P27", home, qualifiers=dict(demonym))),
          policy.PENDING, "unverified")
    check("a foreign demonym beside a recorded citizenship is skipped",
          policy.decide(case("P27", abroad, qualifiers=dict(demonym),
                             entity=item(claim("P27", home)))),
          policy.SKIPPED, "demonym/second_citizenship")
    check("a foreign demonym on an item with none is skipped too",
          policy.decide(case("P27", abroad, qualifiers=dict(demonym))),
          policy.SKIPPED, "demonym/foreign")
    check("an explicit foreign citizenship passes",
          policy.decide(case("P27", abroad, qualifiers=dict(explicit))),
          policy.PENDING, "unverified")

    print("positions:")
    check("a medium-confidence match is skipped",
          policy.decide(case(resolution={"kind": "same-office", "confidence": "medium"})),
          policy.SKIPPED, "resolution/medium")
    check("a rename is skipped",
          policy.decide(case(resolution={"kind": "renamed", "confidence": "high"})),
          policy.SKIPPED, "resolution/renamed")
    check("a P39 with no verdict behind it is skipped",
          policy.decide(case(resolution=None)), policy.SKIPPED, "resolution/missing")
    check("a tenure that ended a generation ago is skipped",
          policy.decide(case(qualifiers={"P580": time("2000"), "P582": time("2004"),
                                         "_sources": [{"lang": "aa", "quote": "q"}]})),
          policy.SKIPPED, "tenure_ended")
    check("and so is one that started then and never ended",
          policy.decide(case(qualifiers={"P580": time("2001"),
                                         "_sources": [{"lang": "aa", "quote": "q"}]})),
          policy.SKIPPED, "tenure_ended")
    check("a tenure that ended within a generation goes on to the verifier",
          policy.decide(case(qualifiers={"P580": time("2006"), "P582": time("2010"),
                                         "_sources": [{"lang": "aa", "quote": "q"}]})),
          policy.PENDING, "unverified")
    check("a tenure with no start is skipped",
          policy.decide(case(qualifiers={"P582": time("2015"),
                                         "_sources": [{"lang": "aa", "quote": "q"}]})),
          policy.SKIPPED, "undated_tenure")
    check("a refinement carrying only an end passes",
          policy.decide(case(proposed="refine",
                             qualifiers={"P582": time("2015"),
                                         "_sources": [{"lang": "aa", "quote": "q"}]})),
          policy.PENDING, "unverified")
    decade = {**time("2010"), "precision": 8}
    check("a start coarser than the bar is skipped",
          policy.decide(case(qualifiers={"P580": decade,
                                         "_sources": [{"lang": "aa", "quote": "q"}]})),
          policy.SKIPPED, "start_precision")
    check("a year-precision start passes the bar",
          policy.decide(case(qualifiers={"P580": time("2010"),
                                         "_sources": [{"lang": "aa", "quote": "q"}]})),
          policy.PENDING, "unverified")
    check("an office the table does not hold is skipped",
          policy.decide(case(position=None)), policy.SKIPPED, "office/unindexed")
    other = {"mainsnak": {"property": "P39", "snaktype": "value", "datavalue": {
                 "type": "wikibase-entityid", "value": {"entity-type": "item", "id": "Q7"}}},
             "qualifiers": {"P580": [{"datavalue": {"value": time("2018-06-22")}}]}}
    check("an unheld twin of a spell already recorded elsewhere is skipped",
          policy.decide(case(entity={"claims": {"P39": [other]}},
                             position=office(holders_by_country={STATE: 0}))),
          policy.SKIPPED, "office/recorded-elsewhere")
    check("but an office others hold is not",
          policy.decide(case(entity={"claims": {"P39": [other]}},
                             position=office(holders_by_country={STATE: 3}))),
          policy.PENDING, "unverified")
    check("nor an office minted this run, which is uncounted",
          policy.decide(case(entity={"claims": {"P39": [other]}}, position=office())),
          policy.PENDING, "unverified")
    check("an item that is not an office is skipped",
          policy.decide(case(position=office(not_office=True))),
          policy.SKIPPED, "office/not-office")
    check("a class of office is skipped",
          policy.decide(case(position=office(instance_count=12))),
          policy.SKIPPED, "office/abstract")
    check("another state's mission to this one is skipped",
          policy.decide(case(position=office(diplomatic=True))),
          policy.SKIPPED, "office/inbound-diplomatic")
    check("this state's own mission abroad passes",
          policy.decide(case(position=office(diplomatic=True, country_qid=OTHER_STATE,
                                             jurisdiction_qid=OTHER_STATE,
                                             sources=["citizen"]))),
          policy.PENDING, "unverified")
    check("another state's mission that names its sender is skipped",
          policy.decide(case(position=office(diplomatic=True, sender_qid=OTHER_STATE))),
          policy.SKIPPED, "office/inbound-diplomatic")
    check("this state's own mission whose P17 names the sender passes",
          policy.decide(case(position=office(diplomatic=True, sender_qid=STATE))),
          policy.PENDING, "unverified")
    check("this state's own mission found by the outbound lane passes",
          policy.decide(case(position=office(diplomatic=True, country_qid=OTHER_STATE,
                                             jurisdiction_qid=None, sender_qid=STATE,
                                             sources=["outbound"]))),
          policy.PENDING, "unverified")
    check("this state's own mission reached only through a citizen passes",
          policy.decide(case(position=office(diplomatic=True, country_qid=OTHER_STATE,
                                             jurisdiction_qid=None, sender_qid=STATE,
                                             sources=["citizen"]))),
          policy.PENDING, "unverified")
    check("another state's office reached only through a citizen is skipped",
          policy.decide(case(position=office(country_qid=OTHER_STATE,
                                             jurisdiction_qid=OTHER_STATE,
                                             sources=["citizen"]))),
          policy.SKIPPED, "office/foreign-scoped")
    check("an office abolished before the tenure began is skipped",
          policy.decide(case(position=office(abolished="1990-01-01"))),
          policy.SKIPPED, "office/date-conflict")
    check("a generic item used with a scoping qualifier, sent without it, is skipped",
          policy.decide(case(position=office(scope_qualifier="P642"))),
          policy.SKIPPED, "generic_needs_scope")
    check("the same item passes once the proposal carries the qualifier",
          policy.decide(case(position=office(scope_qualifier="P642"),
                             qualifiers={"P580": time("2018"), "P642": {"id": "Q1"},
                                         "_sources": [{"lang": "aa", "quote": "q"}]})),
          policy.PENDING, "unverified")
    mayor = {"entity-type": "item", "id": "Q30185"}
    check("a P39 onto a listed generic class is skipped as one",
          policy.decide(case(value=mayor, position=office(qid="Q30185", country_qid=None,
                                                          jurisdiction_qid=None))),
          policy.SKIPPED, "office/generic")
    check("before the tags, which call the same class abstract",
          policy.decide(case(value=mayor, position=office(qid="Q30185", instance_count=12))),
          policy.SKIPPED, "office/generic")
    check("and before generic_needs_scope: no qualifier makes it one office",
          policy.decide(case(value=mayor, position=office(qid="Q30185", scope_qualifier="P642"),
                             qualifiers={"P580": time("2018"), "P642": {"id": "Q1"},
                                         "_sources": [{"lang": "aa", "quote": "q"}]})),
          policy.SKIPPED, "office/generic")
    order = [rule.__name__ for rule in policy.RULES]
    before = order.index("generic_office") < order.index("generic_needs_scope")
    check("the generic rule precedes generic_needs_scope in the table",
          policy.Disposition(policy.SKIPPED, "before" if before else "after"),
          policy.SKIPPED, "before")
    check("a term qualifier is not a scoping one",
          policy.decide(case(position=office(scope_qualifier="P2937"))),
          policy.PENDING, "unverified")
    seat = {"mainsnak": {"datavalue": {"value": {"id": OFFICE}}}}
    terms = [{"claims": {"P39": [{**seat, "qualifiers": {"P2937": [], "P1545": [], "P580": []}}]}},
             {"claims": {"P39": [{**seat, "qualifiers": {"P2937": [], "P642": []}}]}}]
    modal = positions.modal_scope_qualifiers(terms)
    failures += 0 if modal == {OFFICE: "P642"} else 1
    print(f"  {'ok  ' if modal == {OFFICE: 'P642'} else 'FAIL'} a seat's term and ordinal never"
          f" stand in for the qualifier that scopes it {modal}")

    print("several spells of one office:")
    closed = {"P580": time("1992"), "P582": time("1996"), "_sources": [1, 2]}
    open_ = {"P580": time("1992"), "_sources": [1]}
    later = {"P580": time("2000"), "_sources": [1]}
    found = policy.spell_conflicts([(1, closed), (2, open_), (3, later)])
    check("the open-ended reading of a closed spell is set aside",
          policy.Disposition(policy.SKIPPED, found.get(2, "-")), policy.SKIPPED, "sibling_spell")
    check("the closed spell itself stands",
          policy.Disposition(policy.SKIPPED if 1 in found else policy.PENDING, found.get(1, "-")),
          policy.PENDING, "-")
    check("a later term is judged against the survivors only, and stands",
          policy.Disposition(policy.SKIPPED if 3 in found else policy.PENDING, found.get(3, "-")),
          policy.PENDING, "-")
    ends_a = {"P580": time("2023"), "P582": time("2025")}
    ends_b = {"P580": time("2023-09"), "P582": time("2024-10")}
    found = policy.spell_conflicts([(1, ends_a), (2, ends_b)])
    check("two closed spells disagreeing on the end are both contested",
          policy.Disposition(policy.SKIPPED, found.get(1, "-") + "/" + found.get(2, "-")),
          policy.SKIPPED, "contested/contested")
    both_open = {"P580": time("1992")}, {"P580": time("2004")}
    found = policy.spell_conflicts([(1, both_open[0]), (2, both_open[1])])
    check("of two open spells the earlier is contested and the later stands",
          policy.Disposition(policy.SKIPPED, found.get(1, "-") + "/" + found.get(2, "-")),
          policy.SKIPPED, "contested/-")
    terms = [(1, {"P580": time("1992"), "P582": time("1996")}),
             (2, {"P580": time("1996"), "P582": time("2000")}),
             (3, {"P580": time("2000")})]
    check("consecutive terms sharing a boundary year are not in dispute",
          policy.Disposition(policy.SKIPPED if policy.spell_conflicts(terms) else policy.PENDING,
                             str(policy.spell_conflicts(terms))),
          policy.PENDING, "{}")
    mixed = [(1, {"P580": time("1992")}), (2, {"P580": time("1996"), "P582": time("2000")})]
    found = policy.spell_conflicts(mixed)
    check("an open spell overlapping a closed later one is contested alone",
          policy.Disposition(policy.SKIPPED, found.get(1, "-") + "/" + found.get(2, "-")),
          policy.SKIPPED, "contested/-")
    found = policy.spell_conflicts([(1, closed), (2, {"P580": time("1992"), "P582": time("1996")})])
    check("the same closed spell twice keeps the better attested one",
          policy.Disposition(policy.SKIPPED, found.get(2, "-") + "/" + str(1 in found)),
          policy.SKIPPED, "sibling_spell/False")
    check("a P39 flagged by its siblings is skipped under that name",
          policy.decide(case(spell_conflict="contested")), policy.SKIPPED, "contested")

    print("one office on two items:")
    # One interior-minister tenure accepted on both of its state's items: the
    # pt article's dates on the one typed `P31 = interior minister`, the fr
    # article's on the one typed only `P279 = minister`. No shared kind, no
    # shared stem; the alias of the kind is what joins them.
    ruritania = "Ruritania | Republic of Ruritania | République de Ruritanie"
    use = {"Q294414": 40, "Q83307": 15, "Q17578116": 1, "Q21814449": 118, "Q21814438": 2}
    names = {"Q17578116": ["interior minister", "Minister of Internal Affairs",
                           "minister of home affairs", "ministre de l'Intérieur"]}
    typed = office(qid="Q0000011", label="Interior minister of Ruritania",
                   kind_qids=["Q17578116"], jurisdiction_text=ruritania,
                   names=["Interior minister of Ruritania"])
    untyped = office(qid="Q0000012", label="Minister of Internal Affairs of Ruritania",
                     kind_qids=["Q294414", "Q83307"], jurisdiction_text=ruritania,
                     names=["Minister of Internal Affairs of Ruritania",
                            "ministre de l'Intérieur et de la Sécurité publique"])
    pt_spell = {"P580": time("2006-08-13"), "P582": time("2007-02-22")}
    fr_spell = {"P580": time("2006-03-17"), "P582": time("2007-11-14")}

    def family(*spells: tuple[int, dict[str, Any], dict[str, Any]]) -> str:
        found = policy.family_conflicts(list(spells), use, names)
        return "/".join(found.get(pid, "-") for pid, _office, _span in spells)

    check("one tenure on both interior-minister items is contested on both",
          policy.Disposition(policy.SKIPPED,
                             family((1, typed, pt_spell), (2, untyped, fr_spell))),
          policy.SKIPPED, "contested/twin/contested/twin")
    check("the open reading of it alone, where one is open",
          policy.Disposition(policy.SKIPPED,
                             family((1, typed, {"P580": time("2006-08-13")}),
                                    (2, untyped, fr_spell))),
          policy.SKIPPED, "contested/twin/-")
    finance = office(qid="Q0000013", label="Minister of Finance of Ruritania",
                     kind_qids=["Q294414", "Q83307"], jurisdiction_text=ruritania)
    planning = office(qid="Q0000014", label="Minister of Planning of Ruritania",
                      kind_qids=["Q294414", "Q83307"], jurisdiction_text=ruritania)
    check("two concurrent portfolios typed only as minister are not one office",
          policy.Disposition(policy.PENDING,
                             family((1, finance, fr_spell), (2, planning, pt_spell))),
          policy.PENDING, "-/-")
    check("consecutive terms on the two items, touching at the year, are not in dispute",
          policy.Disposition(policy.PENDING,
                             family((1, typed, {"P580": time("2006"), "P582": time("2010")}),
                                    (2, untyped, {"P580": time("2010"), "P582": time("2014")}))),
          policy.PENDING, "-/-")
    deputy = office(qid="Q0000015", label="Deputy Minister of Internal Affairs of Ruritania",
                    kind_qids=["Q83307"], jurisdiction_text=ruritania,
                    names=["Deputy Minister of Internal Affairs of Ruritania"])
    check("a deputy's office does not borrow the minister's kind by containing its name",
          policy.Disposition(policy.PENDING,
                             family((1, typed, pt_spell), (2, deputy, fr_spell))),
          policy.PENDING, "-/-")
    # The second planning item says `P279 = the ministry`: an organisation
    # where the kind belongs. Read as a kind it joined nothing, since nothing
    # else declares it and the position table holds no names for it.
    ministry = "Q0000040"
    org_names = {**names, ministry: ["Ministry of Planning and External Cooperation",
                                     "ministère de la Planification et de la Coopération externe"]}
    planned = office(qid="Q0000041", label="Minister of Planning and External Cooperation",
                     kind_qids=["Q294414", "Q83307"], jurisdiction_text=ruritania,
                     names=["Minister of Planning and External Cooperation"])
    by_ministry = office(qid="Q0000042",
                         label="ministre de la Planification et de la Coopération externe",
                         kind_qids=[ministry, "Q294414"], jurisdiction_text=ruritania,
                         names=["ministre de la Planification et de la Coopération externe"])
    spell = {"P580": time("2019-05")}

    def via_ministry(*spells: tuple[int, dict[str, Any], dict[str, Any]],
                     orgs: frozenset[str] = frozenset({ministry})) -> str:
        found = policy.family_conflicts(list(spells), {**use, ministry: 1}, org_names, orgs)
        return "/".join(found.get(pid, "-") for pid, _office, _span in spells)

    check("an office typed as its ministry joins one named after the ministry",
          policy.Disposition(policy.SKIPPED, via_ministry((1, planned, spell), (2, by_ministry, spell))),
          policy.SKIPPED, "contested/twin/contested/twin")
    planning_deputy = office(qid="Q0000043", label="Deputy Minister of Planning and External Cooperation",
                             kind_qids=["Q83307"], jurisdiction_text=ruritania,
                             names=["Deputy Minister of Planning and External Cooperation"])
    check("but not the ministry's deputy",
          policy.Disposition(policy.PENDING,
                             via_ministry((1, planning_deputy, spell), (2, by_ministry, spell))),
          policy.PENDING, "-/-")
    check("and an organisation is never a kind two offices share",
          policy.Disposition(policy.PENDING,
                             via_ministry((1, {**planning_deputy, "kind_qids": [ministry]}, spell),
                                          (2, by_ministry, spell))),
          policy.PENDING, "-/-")
    district = [office(qid=f"Q000002{n}", label=f"chairman of district {n}",
                       kind_qids=["Q21814449"]) for n in (1, 2)]
    check("a kind most of a state's offices declare names a class, not a seat",
          policy.Disposition(policy.PENDING,
                             family((1, district[0], fr_spell), (2, district[1], pt_spell))),
          policy.PENDING, "-/-")
    envoys = [office(qid=f"Q000003{n}", label=f"ambassador to {n}", diplomatic=True,
                     kind_qids=["Q21814438"]) for n in (1, 2)]
    check("two ambassadorships at once are one envoy accredited twice",
          policy.Disposition(policy.PENDING,
                             family((1, envoys[0], fr_spell), (2, envoys[1], pt_spell))),
          policy.PENDING, "-/-")
    ok = (policy.state_office(office(country_qid=None, jurisdiction_qid=STATE), STATE)
          and policy.state_office(office(jurisdiction_qid=None), STATE)
          and not policy.state_office(office(country_qid=OTHER_STATE, jurisdiction_qid=OTHER_STATE),
                                      STATE))
    failures += 0 if ok else 1
    print(f"  {'ok  ' if ok else 'FAIL'} an office with P1001 and no P17 is the state's,"
          " and its twins are judged")

    plural = {a.parent for a in offices.ARCHETYPES.values()} - policy.FAMILY_GENERIC
    ok = plural == {"Q5097014", "Q107363151", "Q3368517"} and {
        q for a in offices.ARCHETYPES.values() for q in a.parents} <= policy.FAMILY_GENERIC
    failures += 0 if ok else 1
    print(f"  {'ok  ' if ok else 'FAIL'} every archetype parent but the one-per-state seats"
          f" is generic {sorted(plural)}")

    # The era rules sit behind the recency rule and are asked about tenures the
    # recency rule would take first, so these cases are judged from a day when
    # those tenures were recent.
    era = date(1971, 6, 15)
    later = date(2000, 6, 15)
    print("before the polity existed:")
    check("a tenure that ended before the state was founded is skipped",
          policy.decide(case(today=later, position=office(polity_inception_year=1991),
                             qualifiers={"P580": time("1978"), "P582": time("1980"),
                                         "_sources": [{"lang": "aa", "quote": "q"}]})),
          policy.SKIPPED, "tenure_before_polity")
    check("the state's first government, a year before recognition, passes",
          policy.decide(case(today=later, position=office(polity_inception_year=1991),
                             qualifiers={"P580": time("1990"), "P582": time("1992"),
                                         "_sources": [{"lang": "aa", "quote": "q"}]})),
          policy.PENDING, "unverified")

    print("before anyone was recorded in the office:")
    check("a tenure generations before the first recorded holder is skipped",
          policy.decide(case(today=era, position=office(first_held_year=1995),
                             qualifiers={"P580": time("1948"), "P582": time("1951"),
                                         "_sources": [{"lang": "aa", "quote": "q"}]})),
          policy.SKIPPED, "tenure_before_record")
    check("one inside the margin passes",
          policy.decide(case(today=later, position=office(first_held_year=2008),
                             qualifiers={"P580": time("1990"), "P582": time("1994"),
                                         "_sources": [{"lang": "aa", "quote": "q"}]})),
          policy.PENDING, "unverified")
    check("an office nobody is dated in says nothing",
          policy.decide(case(today=era, position=office(first_held_year=None),
                             qualifiers={"P580": time("1948"), "P582": time("1951"),
                                         "_sources": [{"lang": "aa", "quote": "q"}]})),
          policy.PENDING, "unverified")
    check("an office with an inception is the date-conflict tag's business",
          policy.decide(case(today=era,
                             position=office(first_held_year=1995, inception="1900-01-01"),
                             qualifiers={"P580": time("1948"), "P582": time("1951"),
                                         "_sources": [{"lang": "aa", "quote": "q"}]})),
          policy.PENDING, "unverified")

    print("an open tenure somebody later evidently ended:")
    me = {"id": "Q0000009", "claims": {}}

    def spell(person: str, start: str, end: str | None = None,
              live: bool = True) -> policy.OfficeSpell:
        span = {"P580": time(start), **({"P582": time(end)} if end else {})}
        return policy.OfficeSpell(person, span, live)

    def open_from(start: str) -> dict[str, Any]:
        return {"P580": time(start), "_sources": [{"lang": "aa", "quote": "q"}]}

    # A chamber elected every five years: one spell per member and term, a
    # vacancy filled late, a member re-elected on one statement, and the
    # 2025 chamber's first members on record.
    chamber = [
        *(spell(f"Q10{n}", "2010-06-01", "2015-09-07") for n in range(4)),
        *(spell(f"Q11{n}", "2015-09-07", "2020-08-19") for n in range(3)),
        spell("Q120", "2013-01-10", "2015-09-07"),
        spell("Q121", "2010-06-01", "2020-08-19"),
        spell("Q130", "2025-05-03"), spell("Q131", "2025-05-03"),
    ]
    seat = office(kind_qids=["Q4164871", "Q486839"])
    check("an open 2010 seat in a chamber re-formed in 2025 is skipped",
          policy.decide(case(entity=me, position=seat, office_spells=chamber,
                             qualifiers=open_from("2010-06-01"))),
          policy.SKIPPED, "open_superseded/chamber")
    check("a seat of the chamber's current term is kept",
          policy.decide(case(entity=me, position=seat, office_spells=chamber,
                             qualifiers=open_from("2025-05-03"))),
          policy.PENDING, "unverified")
    check("so is one filled by a by-election late in the last term",
          policy.decide(case(entity=me, position=seat, office_spells=chamber,
                             qualifiers=open_from("2023-02-01"))),
          policy.PENDING, "unverified")
    check("a chamber whose term cannot be measured is left alone",
          policy.decide(case(entity=me, position=seat, office_spells=chamber[-3:],
                             qualifiers=open_from("2010-06-01"))),
          policy.PENDING, "unverified")
    check("one later by-election is not a new term",
          policy.decide(case(entity=me, position=seat,
                             office_spells=[*chamber[:-2], spell("Q130", "2025-05-03")],
                             qualifiers=open_from("2015-09-07"))),
          policy.PENDING, "unverified")

    ministry = [spell("Q200", "2015-09-09", "2020-08-19"), spell("Q201", "2020-08-19", "2025-05-01")]
    check("a current minister whose successor isn't recorded is kept",
          policy.decide(case(entity=me, office_spells=ministry,
                             qualifiers=open_from("2025-05-01"))),
          policy.PENDING, "unverified")
    check("a minister whose successor took office later is skipped",
          policy.decide(case(entity=me, office_spells=ministry,
                             qualifiers=open_from("2010-05-28"))),
          policy.SKIPPED, "open_superseded/single")
    check("and so is one whose successor is only proposed",
          policy.decide(case(entity=me, office_spells=[spell("Q202", "2021-01-01", live=True)],
                             qualifiers=open_from("2018-03-01"))),
          policy.SKIPPED, "open_superseded/single")
    check("a successor a rule set aside succeeds nobody",
          policy.decide(case(entity=me, office_spells=[spell("Q202", "2021-01-01", live=False)],
                             qualifiers=open_from("2018-03-01"))),
          policy.PENDING, "unverified")
    check("a start in the same year at year precision is not a later one",
          policy.decide(case(entity=me, office_spells=[spell("Q202", "2025-05-03")],
                             qualifiers=open_from("2025"))),
          policy.PENDING, "unverified")
    check("the holder's own later spell is not a successor",
          policy.decide(case(entity=me, office_spells=[spell("Q0000009", "2021-01-01")],
                             qualifiers=open_from("2018-03-01"))),
          policy.PENDING, "unverified")
    shared = [spell("Q300", "2012-01-01", "2019-01-01"), spell("Q301", "2014-01-01", "2020-01-01")]
    check("an office two held at once for years is not one seat",
          policy.decide(case(entity=me, office_spells=[*shared, spell("Q302", "2022-01-01")],
                             qualifiers=open_from("2018-03-01"))),
          policy.PENDING, "unverified")
    check("nor is one declared a deputy ministry",
          policy.decide(case(entity=me, position=office(kind_qids=["Q26204040"]),
                             office_spells=[spell("Q202", "2021-01-01")],
                             qualifiers=open_from("2018-03-01"))),
          policy.PENDING, "unverified")
    check("an office whose holders nobody read is left alone",
          policy.decide(case(entity=me, office_spells=None, qualifiers=open_from("2010-05-28"))),
          policy.PENDING, "unverified")
    check("an open 2017 seat in a body dissolved in 2023 is skipped",
          policy.decide(case(entity=me, dissolved=[time("2023-01-10")],
                             qualifiers=open_from("2017-01-10"))),
          policy.SKIPPED, "open_superseded/dissolved")
    check("and so is one on an office abolished since, with nobody's holders read",
          policy.decide(case(entity=me, position=office(abolished="2023-01-10"),
                             qualifiers=open_from("2017-01-10"))),
          policy.SKIPPED, "open_superseded/dissolved")
    check("a body dissolved before the tenure began was re-formed, and says nothing",
          policy.decide(case(entity=me, dissolved=[time("2016-01-10")],
                             qualifiers=open_from("2017-01-10"))),
          policy.PENDING, "unverified")
    check("a dissolution still to come ends nothing yet",
          policy.decide(case(entity=me, dissolved=[time("2027-02-07")],
                             qualifiers=open_from("2024-04-25"))),
          policy.PENDING, "unverified")
    check("a closed tenure is never superseded",
          policy.decide(case(entity=me, office_spells=ministry)),
          policy.PENDING, "unverified")

    print("the verifier:")
    check("nothing is accepted before the verifier has answered",
          policy.decide(case()), policy.PENDING, "unverified")
    check("a supported verdict at high confidence is accepted",
          policy.decide(case(verification={"verdict": "supported", "confidence": "high"})),
          policy.ACCEPTED, policy.ACCEPT_RULE)
    check("a supported verdict at low confidence is skipped",
          policy.decide(case(verification={"verdict": "supported", "confidence": "low"})),
          policy.SKIPPED, "verify/low")
    check("any other verdict is skipped under its own name",
          policy.decide(case(verification={"verdict": "wrong-item", "confidence": "high"})),
          policy.SKIPPED, "verify/wrong-item")
    check("the verifier is asked only after every rule has passed",
          policy.decide(case(resolution=None,
                             verification={"verdict": "supported", "confidence": "high"})),
          policy.SKIPPED, "resolution/missing")

    print("the report:")
    funnel = policy.Funnel()
    funnel.add(case(), policy.decide(case()))
    funnel.add(case(position=None), policy.decide(case(position=None)))
    lines = policy.report_lines(funnel, {OFFICE: "an office"})
    ok = any("office/unindexed" in line for line in lines)
    ok = ok and any(OFFICE in line for line in lines)
    failures += 0 if ok else 1
    mark = "ok  " if ok else "FAIL"
    print(f"  {mark} every rule that fired is a line, and the offices are listed")
    names = [rule.__name__ for rule in policy.RULES]
    ok = policy._rule_order("verify/low")[0] == names.index("verify_refused") and (
        policy._rule_order("office/abstract")[0] == names.index("office_rejected"))
    failures += 0 if ok else 1
    print(f"  {'ok  ' if ok else 'FAIL'} a dynamic rule name sorts with the rule that made it")

    print(f"{failures} failures")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
