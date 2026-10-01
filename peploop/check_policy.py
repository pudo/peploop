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

from peploop import policy, propose

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
        "inception": None, "abolished": None, "diplomatic": None,
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
    check("an alias is never written",
          policy.decide(case("alias:aa", {"language": "aa", "text": "A B"})),
          policy.SKIPPED, "lane_removed")
    check("a label is never written",
          policy.decide(case("label:aa", {"language": "aa", "text": "A B"})),
          policy.SKIPPED, "lane_removed")
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
    check("a term qualifier is not a scoping one",
          policy.decide(case(position=office(scope_qualifier="P2937"))),
          policy.PENDING, "unverified")

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
