"""Pin what `propose` makes of a reconciled office, offline.

The position lane decides three things that are wrong in ways nothing later
notices. A tenure the item already records under slightly different dates can
be shown to a reviewer as an edit, when the plan could never write it and the
reviewer can only wave it through -- so a quarter of the lane is attention
spent on nothing. The same spell read in two languages can become two rows
asking a reviewer one question twice. And an acting tenure can go out as an
ordinary one, which asserts more than the article did.

Overlap is where the silence is worst, because both ways of getting it wrong
look fine from outside: judge it against every office and a minister keeping
their parliamentary seat disappears, judge it too narrowly and the duplicates
come back as `conflict`. Both directions are pinned below.

No network, no key, no database: every case is a hand-built entity and a
hand-built extraction. Run it as `python -m peploop.check_propose` from the
repository root.
"""

import sys
from datetime import date
from typing import Any

from peploop import propose

# A stand-in office, a second one to hold the concurrency case, and two
# stand-in articles. Nothing here names a real country: `check_neutral` is
# about rules, and a fixture that reads as one country's is how the next
# country's case stops being written.
OFFICE = "Q0000001"
OTHER = "Q0000002"


def day(text: str) -> dict[str, Any]:
    """A day-precision time value, as the extraction's own parser writes one."""
    value = propose.time_value(text)
    assert value is not None, text
    return value


def coarse(text: str, precision: int) -> dict[str, Any]:
    """A time value below day precision, stored the way Wikidata stores one.

    What the precision does not reach is `00`, so a decade and a year are the
    same string at different precisions and only the precision says which.
    """
    return {
        "time": f"+{(text + '-00-00')[:10]}T00:00:00Z",
        "precision": precision,
        "calendarmodel": propose.CALENDAR,
        "timezone": 0,
        "before": 0,
        "after": 0,
    }


def statement(start: str | None = None, end: str | None = None,
              qid: str = OFFICE) -> dict[str, Any]:
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
                                   "value": {"entity-type": "item", "id": qid}}},
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

    print("citizenship_territory, a community name is no state:")
    community = sorted(propose.NOT_A_STATE)[0]
    expect(propose.citizenship_territory(community.upper()), None,
           "a community's name is no citizenship, however it is cased")
    expect(propose.citizenship_territory("Norwegian").qid, "Q20",
           "a demonym still names its state")

    term = span("2020-10-15", "2022-06-01")

    print("tenure_status, a spell the item already records:")
    expect(propose.tenure_status([], span("2020-10-15")), "new",
           "an office the item does not record is new")
    expect(propose.tenure_status([term], span("2020-10-15", "2022-06-01")),
           propose.OVERLAPPING, "the very same spell is already written down")
    # The case the lane exists for: the article and the item date one
    # appointment days apart, and two Occupancies downstream is the cost.
    expect(propose.tenure_status([term], span("2020-10-15", "2022-04-20")),
           propose.OVERLAPPING, "an end three days out is the same appointment")
    expect(propose.tenure_status([term], span("2021-01-08", "2021-11-30")),
           propose.OVERLAPPING, "a spell inside a longer recorded term is agreement")
    expect(propose.tenure_status([term], span("2022-04-20", "2024-03-01")),
           propose.OVERLAPPING, "a spell straddling one boundary is the same appointment")
    # A recorded open term blocks only a spell with another start: one with the
    # same start is the end the record is missing, and is `refine` below.
    expect(propose.tenure_status([span("2020-10-15")], span("2022-01-01", "2024-03-01")),
           propose.OVERLAPPING, "a recorded open term blocks a spell starting elsewhere in it")

    print("tenure_status, the end a recorded open term is missing:")
    expect(propose.tenure_status([span("2020-10-15")], span("2020-10-15", "2024-03-01"),
                                 today=date(2026, 6, 15)),
           "refine", "the same start with an end by today closes it")
    expect(propose.tenure_status([{"P580": coarse("2020", 9)}], span("2020-10-15", "2024-03-01"),
                                 today=date(2026, 6, 15)),
           "refine", "the same start at the precision both share is the same start")
    expect(propose.tenure_status([span("2020-10-15")], span("2020-10-15", "2027-01-01"),
                                 today=date(2026, 6, 15)),
           propose.OVERLAPPING, "an end still to come is a schedule and closes nothing")
    expect(propose.tenure_status([span("2020-10-15", "2022-06-01")], span("2020-10-15", "2024-03-01"),
                                 today=date(2026, 6, 15)),
           propose.OVERLAPPING, "a recorded end is not missing, and a second one is a clash")
    expect(propose.tenure_status([span("2020-10-15")], span("2020-10-15"),
                                 today=date(2026, 6, 15)),
           propose.OVERLAPPING, "an open proposal adds nothing to an open record")

    print("tenure_status, a spell it does not:")
    # The case that read `conflict` before overlap: an earlier term of an
    # office the item records one later term of is coverage, not a dispute.
    expect(propose.tenure_status([term], span("2004-12-03", "2008-11-21")), "new",
           "an earlier term nothing recorded covers is new")
    expect(propose.tenure_status([span(end="2008-11-21")], span("2020-10-15", "2022-06-01")),
           "new", "a recorded end with no start bounds it, and a later spell is new")

    print("tenure_status, a recorded statement with no dates:")
    expect(propose.tenure_status([{}], span("2020-10-15", "2022-06-01")), "refine",
           "an undated statement is what the proposal exists to sharpen")
    expect(propose.tenure_status([{}], {}), "refine",
           "and an undated proposal against it is still a refinement")
    expect(propose.tenure_status([{}, term], span("2020-10-15", "2022-04-20")),
           propose.OVERLAPPING, "a clash is asked before the undated exception")

    expect(propose.tenure_status([span("2020-10-15", "2022-06-01")], {}), propose.OVERLAPPING,
           "a proposal with no dates says less than the statement already does")
    expect(propose.tenure_status([{}, span("2020-10-15", "2022-06-01")], {}), propose.OVERLAPPING,
           "and an undated statement beside a dated one does not rescue it")

    print("tenure_status, at coarse precision:")
    expect(propose.tenure_status([term], {"P580": coarse("2021", 9),
                                          "P582": coarse("2021", 9)}),
           propose.OVERLAPPING, "a year inside a recorded term overlaps it")
    expect(propose.tenure_status([term], {"P580": coarse("1930", 8),
                                          "P582": coarse("1930", 8)}),
           "new", "a decade nowhere near the recorded term is new")

    print("tenure_status, several statements for one office:")
    two_terms = [span("2004-12-03", "2008-11-21"), term]
    expect(propose.tenure_status(two_terms, span("2020-10-15", "2022-06-01")),
           propose.OVERLAPPING, "a second term matches the term it is, not the other one")
    expect(propose.tenure_status(two_terms, span("2012-02-10", "2013-03-20")), "new",
           "a third spell in the gap between them is a further term")

    print("the lane as a whole:")
    placed = {0: (OFFICE, 1)}
    out = propose._positions(item(), {"positions": [mention()]}, placed, set())
    expect([(p.property, p.status, p.value["id"], p.resolution_id) for p in out],
           [("P39", "new", OFFICE, 1)], "a placed mention becomes one new P39")
    expect(sorted((out[0].qualifiers or {})), ["P580", "P582"],
           "the tenure's endpoints become P580 and P582")

    # The rule that must not generalise: a concurrent seat is a real tenure.
    out = propose._positions(item(statement("2020-10-15", "2022-06-01", qid=OTHER)),
                             {"positions": [mention()]}, placed, set())
    expect([p.status for p in out], ["new"],
           "a spell overlapping a different office is concurrency, not a clash")

    out = propose._positions(item(statement("2020-10-15", "2022-06-01")),
                             {"positions": [mention(end="2022-04-20")]}, placed, set())
    expect([p.status for p in out], [propose.OVERLAPPING],
           "the same spell of the same office is set aside")
    expect((out[0].qualifiers or {}).get("_reason"), "overlaps 2020-10-15..2022-06-01",
           "and it names the recorded spell it clashed with")

    both = {"positions": [mention(), mention(lang="ab", title="finance minister",
                                             quotes=["finance minister, 2020 to 2022"])]}
    out = propose._positions(item(), both, {0: (OFFICE, 1), 1: (OFFICE, 2)}, set())
    expect(len(out), 1, "the same spell in two languages is one row")
    expect(sorted(s.lang or "" for s in out[0].sources), ["aa", "ab"],
           "and it carries both articles as sources")

    differ = {"positions": [mention(), mention(lang="ab", start="2020-02-21", end="2022-04-25")]}
    out = propose._positions(item(), differ, {0: (OFFICE, 1), 1: (OFFICE, 2)}, set())
    expect([(p.status, (p.qualifiers or {}).get("_reason")) for p in out],
           [(propose.FILTERED, "sources_disagree")],
           "two articles dating one year's spell differently are not one statement citing both")

    gap = {"positions": [mention(), mention(start="2004-12-03", end="2008-11-21")]}
    out = propose._positions(item(), gap, {0: (OFFICE, 1), 1: (OFFICE, 2)}, set())
    expect(len(out), 2, "two spells with a gap stay two rows")

    out = propose._positions(item(), {"positions": [mention(acting=True)]}, placed, set())
    expect([p.status for p in out], [propose.FILTERED],
           "an acting tenure is filtered, not asserted")

    expect((out[0].qualifiers or {}).get("_reason"), "acting",
           "and it says which rule filtered it")

    out = propose._positions(item(), {"positions": [mention()]}, {}, set())
    expect(out, [], "a mention reconciliation refused proposes nothing")

    out = propose._positions(item(), {"positions": [mention()]}, placed,
                             {"took office on 15 October 2020"})
    expect([p.status for p in out], ["unquoted"],
           "a mention whose only quote is bad is unquoted")

    print("several terms of one office:")

    def terms(entity: dict[str, Any], *starts: str, end: str | None = None) -> list[Any]:
        mentions = [mention(start=start, end=None, quotes=[f"elected in {start}"])
                    for start in starts]
        if end is not None:
            mentions[-1]["end"] = end
        found = propose._positions(entity, {"positions": mentions},
                                   {i: (OFFICE, i + 1) for i in range(len(mentions))}, set())
        return sorted(found, key=lambda p: p.qualifiers["P580"]["time"])

    def spans(found: list[Any]) -> list[str]:
        return [propose.span_text({k: v for k, v in p.qualifiers.items() if k.startswith("P")})
                for p in found]

    # Sun Jianguo: the 13th congress from 2018 and the 14th from 2023, both open.
    sun = terms(item(), "2018", "2023")
    expect(spans(sun), ["2018..2023", "2023.."],
           "an open term ends where the next one starts")
    expect([(s.lang, s.quote, s.dates) for s in sun[0].sources],
           [("aa", "elected in 2018", None), ("aa", "elected in 2023", "P582")],
           "citing the next term's quote for that end")
    # Wang Suilian: the 13th congress from 2018 and nothing after.
    expect(spans(terms(item(), "2018-02-24")), ["2018-02-24.."],
           "a single open term stays open")
    expect(spans(terms(item(), "2013", "2018", "2023")), ["2013..2018", "2018..2023", "2023.."],
           "a chain of three closes each at the next")
    other_wiki = [mention(start="2018", end=None, quotes=["elected in 2018"]),
                  mention(start="2023", end=None, lang="ab", quotes=["elected in 2023"])]
    expect(spans(sorted(propose._positions(item(), {"positions": other_wiki},
                                           {0: (OFFICE, 1), 1: (OFFICE, 2)}, set()),
                        key=lambda p: p.qualifiers["P580"]["time"])),
           ["2018..", "2023.."], "only the same article's next term closes one")
    expect([(spans([p]), p.status) for p in terms(item(), "2017-08-01", "2017-09-01")],
           [(["2017-08-01.."], propose.FILTERED)],
           "and only in a later year: weeks apart is one appointment dated twice")
    expect(spans(terms(item(statement("2010-03-05", "2013-03-05")), "2013", "2018")),
           ["2013..2018", "2018.."], "a dated statement beside them changes nothing of this")

    def termed(*terms_: str, start: str | None = None) -> dict[str, Any]:
        claim = statement(start)
        claim.setdefault("qualifiers", {})["P2937"] = [
            {"property": "P2937", "snaktype": "value", "datatype": "wikibase-item",
             "datavalue": {"type": "wikibase-entityid",
                           "value": {"entity-type": "item", "id": term_}}}
            for term_ in terms_]
        return item(claim)

    career = terms(termed("Q0000021", "Q0000022"), "2013", "2018")
    expect([(spans(career), p.status, p.qualifiers.get("_terms"),
             p.qualifiers.get("_last_start", {}).get("time")) for p in career[:1]] + [len(career)],
           [(["2013.."], "refine", 2, day("2018")["time"]), 1],
           "a statement holding two terms is one row dating it, judged by the last start")
    expect(sorted(s.quote for s in career[0].sources), ["elected in 2013", "elected in 2018"],
           "resting on every term's quote")
    expect(spans(terms(termed("Q0000021", "Q0000022"), "2013", "2018", end="2023")),
           ["2013..2023"], "ending where the last term ended")
    expect(spans(terms(item(statement()), "2013", "2018")), ["2013.."],
           "so is an undated statement the article gives several terms for")
    months = [mention(start=start, end=start, quotes=[f"president in {start}"])
              for start in ("2013-11-01", "2015-02-01")]
    expect(len(propose._positions(item(statement()), {"positions": months},
                                  {0: (OFFICE, 1), 1: (OFFICE, 2)}, set())), 2,
           "but terms with years between them are not one career: the span would claim the gap")
    expect(spans(terms(item(statement()), "2013")), ["2013.."],
           "while one term on it is that term")
    expect(spans(terms(termed("Q0000021"), "2013", "2018")), ["2013..2018", "2018.."],
           "and a statement of one term is that term, the others beside it")

    print("what identifies a stored proposal:")
    value = {"entity-type": "item", "id": OFFICE}
    first = propose.proposal_key("P39", value, span("1996-01-01", "2000-01-01"))
    second = propose.proposal_key("P39", value, span("2004-12-03", "2008-11-21"))
    expect(first == second, False,
           "two spells of one office are two proposals, whatever one of them was ruled")
    expect(propose.proposal_key("P39", value, {**span("1996-01-01"), "_sources": [1]}),
           propose.proposal_key("P39", value, {**span("1996-01-01"), "_reason": "x"}),
           "and peploop's own bookkeeping keys are not part of it")

    print("a value with no quote at all:")
    expect(propose.quote_status("new", [], set()), "unquoted",
           "has no evidence behind it, however well it agrees with the item")

    print("the statuses the lane may emit:")
    expect(propose.OVERLAPPING in propose.STATUS_RANK, False,
           "overlapping is never ranked against a date comparison")

    print("a row the plan closed, on a re-propose:")
    # A seat recorded with a district and no dates is a specific tenure the
    # article's dates may not be about: the plan closes the row as `termed`, and
    # a re-propose must not bring it back as `accepted`.
    districted = statement()
    districted["qualifiers"] = {"P768": [{"property": "P768", "snaktype": "value",
                                          "datatype": "wikibase-item", "datavalue": {
                                              "type": "wikibase-entityid",
                                              "value": {"entity-type": "item", "id": OTHER}}}]}
    closed = {"property": "P39", "value": value, "qualifiers": span("2020-10-15"),
              "decided_by": "plan:termed"}
    expect(propose.plan_decision_holds(item(districted), closed), True,
           "stays closed while the item still records only the undated, districted seat")
    expect(propose.plan_decision_holds(item(districted, statement("2020-10-15")), closed), False,
           "is re-derived once the item records a spell the row now matches")
    expect(propose.plan_decision_holds(item(), closed), False,
           "and once the districted seat is gone")
    expect(propose.plan_decision_holds(None, closed), False,
           "and is never kept with no item to plan against")
    born = {"property": "P569", "value": day("1960-03-01"), "qualifiers": None,
            "decided_by": "plan:conflict"}
    recorded = {"claims": {"P569": [{"rank": "normal", "mainsnak": {
        "property": "P569", "snaktype": "value", "datatype": "time",
        "datavalue": {"type": "time", "value": day("1961-07-04")}}}]}}
    expect(propose.plan_decision_holds(recorded, born), True,
           "a conflicting birth date stays closed while the other date stands")
    expect(propose.plan_decision_holds({"claims": {}}, born), False,
           "and is re-derived once it is gone")

    print(f"{len(failures)} failures")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
