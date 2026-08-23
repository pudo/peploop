#!/usr/bin/env python
"""Assert the enrichment loop's mechanical channel against hand-built cases.

    python scripts/check_enrich.py

Offline by construction — no key, no network, no tokens. `wd/enrich.py:check` is
the second of the two independent signals the loop runs on, and it is the half
that decides whether a model's proposal becomes a statement, so every gate in it
is cheap to get subtly wrong and expensive to discover on a public database.

The cases below are the ones that were got wrong, in the order they were found:
a quote checked against part of the dossier rather than all of it, an undated
recorded statement read as a duplicate, and a loop variable that shadowed the
gazetteer parameter and silently checked positions against electoral districts.
None was caught by reading code.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wd.dossier import Dossier, Fragment  # noqa: E402
from wd.enrich import check, records  # noqa: E402
from wd.gazetteer import Entry, Gazetteer  # noqa: E402
from wd.infobox import Evidence  # noqa: E402
from wd.officebox import Tenure  # noqa: E402

TEXT = ("Jan Kowalski (ur. 22 września 1985 w Bolesławcu) served as Minister of "
        "Roads from 2013 to 2017, elected in the Legnica district, and sat with "
        "the Civic Club. He acted as caretaker from 2011.")


def dossier(**item) -> Dossier:
    base = {"tenures": [], "birth_date": None, "citizenship": [], "gender": None}
    base.update(item)
    d = Dossier(qid="Q1", label="Jan Kowalski", item=base)
    d.fragments = [Fragment(kind="body", source="pl:Jan#article", text=TEXT, url="u")]
    return d


def with_officebox() -> Dossier:
    """A dossier whose only evidence for the span is the rendered officebox."""
    d = dossier()
    d.officebox = [Tenure(office="Minister of Roads", link=None, start="2013",
                          end="2017", period_raw="2013 – 2017")]
    return d


GAZ = Gazetteer(scope="t", entries=[Entry(qid="Q9", label="Minister of Roads",
                                          inception="1990")])
DISTRICTS = Gazetteer(scope="d", entries=[Entry(qid="Q77", label="Legnica district")])
GROUPS = Gazetteer(scope="g", entries=[Entry(qid="Q88", label="Civic Club")])


def proposal(**kw) -> dict:
    base = dict(property="P39", position_qid="Q9", office_name=None, value=None,
                start="2013", end="2017", acting=False, district=None, group=None,
                confidence="high", source="pl:Jan#article", reason="r",
                quote="served as Minister of Roads from 2013 to 2017")
    base.update(kw)
    return base


#: (name, dossier, proposal, kwargs, expected action, expected rule)
CASES = [
    ("clean tenure", dossier(), proposal(), {}, "apply", "dated_tenure"),
    ("paraphrased quote", dossier(), proposal(quote="he ran the roads ministry"),
     {}, "skip", "quote_unverified"),
    # The quote gate must check the *whole* rendered dossier. Four correct
    # Poland proposals were rejected for citing the officebox section, which
    # `render` builds from a structured field rather than from a fragment.
    ("quote from the officebox section", with_officebox(),
     proposal(quote="Minister of Roads — 2013-2017"), {}, "apply", "dated_tenure"),
    ("invented QID", dossier(), proposal(position_qid="Q777"), {},
     "skip", "position_invented"),
    ("office named, no item", dossier(),
     proposal(position_qid=None, office_name="Deputy Minister of Roads"), {},
     "byproduct", "office_unresolved"),
    ("office placed by lookup", dossier(),
     proposal(position_qid=None, office_name="Deputy Minister of Roads"),
     {"resolved": {"Deputy Minister of Roads": "Q9"}}, "apply", "office_resolved"),
    ("start after end", dossier(), proposal(start="2017", end="2013"), {},
     "skip", "malformed"),
    ("before the office existed", dossier(), proposal(start="1980", end="1984"),
     {}, "skip", "before_inception"),
    ("low confidence", dossier(), proposal(confidence="low"), {},
     "skip", "low_confidence"),
    ("acting spell", dossier(),
     proposal(acting=True, start="2011", end=None,
              quote="He acted as caretaker from 2011"), {}, "apply", "acting"),
    # An undated recorded statement is not a duplicate: zavod refuses an
    # Occupancy when nothing is dated, so dating it is the largest class of fix
    # the loop finds. Reading it as recorded suppressed all of them.
    ("dates an undated statement", dossier(
        tenures=[{"position": "Q9", "start": None, "end": None,
                  "position_label": "Minister of Roads"}]),
     proposal(), {}, "apply", "dates_existing_statement"),
    ("same span already recorded", dossier(
        tenures=[{"position": "Q9", "start": "2013", "end": "2017",
                  "position_label": "Minister of Roads"}]),
     proposal(), {}, "skip", "already_recorded"),
]


def main() -> None:
    bad = 0
    for name, d, p, kwargs, action, rule in CASES:
        got = check({"qid": "Q1", "proposals": [p]}, d, GAZ, **kwargs)
        record = records("spec", d, got, campaign="c")[0]
        if (record.decision.action, record.decision.rule) != (action, rule):
            bad += 1
            print(f"FAIL {name}: want {action}/{rule}, got "
                  f"{record.decision.action}/{record.decision.rule} "
                  f"(flags={got[0].flags} failures={got[0].failures})")

    # Two dated terms against one undated statement cannot go through either
    # write path — QS folds them together, the API leaves the undated one beside
    # them — so the undated statement must be removed by a human first.
    d = dossier(tenures=[{"position": "Q9", "start": None, "end": None,
                          "position_label": "Minister of Roads"}])
    pair = check({"qid": "Q1", "proposals": [
        proposal(), proposal(start="2019", end="2023",
                             quote="served as Minister of Roads from 2013 to 2017")]},
        d, GAZ)
    rules = {records("s", d, [c], campaign="c")[0].decision.rule for c in pair}
    if rules != {"undated_needs_removal"}:
        bad += 1
        print(f"FAIL several terms vs one undated statement: got {rules}")

    # The qualifier sets must not shadow the position gazetteer. This shipped:
    # `for prop, gazetteer in qualifiers.items()` rebound the parameter, so
    # Guatemala checked every position against an empty set and rejected its own
    # target, and Poland would have checked positions against 139 districts.
    for label, quals in [
        ("absent", None),
        ("empty", {"P768": Gazetteer("q", []), "P4100": Gazetteer("q", [])}),
        ("populated", {"P768": DISTRICTS, "P4100": GROUPS}),
    ]:
        got = check({"qid": "Q1", "proposals": [proposal()]}, d, GAZ,
                    qualifiers=quals)[0]
        if "position_not_in_gazetteer" in got.failures:
            bad += 1
            print(f"FAIL qualifier sets ({label}) shadowed the position gazetteer")

    # A named qualifier resolves against its closed set; an unnamed one is
    # dropped without costing the tenure.
    got = check({"qid": "Q1", "proposals": [proposal(
        district="Legnica district", group="Civic Club")]}, GAZ and dossier(), GAZ,
        qualifiers={"P768": DISTRICTS, "P4100": GROUPS})[0]
    if got.qualifiers != {"P768": "Q77", "P4100": "Q88"}:
        bad += 1
        print(f"FAIL qualifier resolution: got {got.qualifiers}")
    got = check({"qid": "Q1", "proposals": [proposal(district="Nowhere district")]},
                dossier(), GAZ, qualifiers={"P768": DISTRICTS})[0]
    if got.failures or "district_unmatched" not in got.flags:
        bad += 1
        print(f"FAIL unmatched qualifier must not fail the tenure: {got.failures}")

    # A recorded statement that says nothing about the constituency is not
    # finished: QS merges the qualifier into it. Only with one statement for the
    # office — with two, QS cannot know which one the qualifier belongs to.
    one = dossier(tenures=[{"position": "Q9", "start": "2013", "end": "2017",
                            "position_label": "Minister of Roads",
                            "qualifiers": ["P580", "P582"]}])
    got = check({"qid": "Q1", "proposals": [proposal(district="Legnica district")]},
                one, GAZ, qualifiers={"P768": DISTRICTS})[0]
    rule = records("s", one, [got], campaign="c")[0].decision.rule
    if rule != "qualifies_existing_statement":
        bad += 1
        print(f"FAIL qualifying a recorded statement: got {rule} ({got.flags})")
    two = dossier(tenures=[
        {"position": "Q9", "start": "2013", "end": "2017", "qualifiers": ["P580"]},
        {"position": "Q9", "start": "2019", "end": "2023", "qualifiers": ["P580"]}])
    got = check({"qid": "Q1", "proposals": [proposal(district="Legnica district")]},
                two, GAZ, qualifiers={"P768": DISTRICTS})[0]
    if "ambiguous_merge_target" not in got.flags:
        bad += 1
        print(f"FAIL two statements must not take a merged qualifier: {got.flags}")
    # And nothing to add is still a skip.
    got = check({"qid": "Q1", "proposals": [proposal()]}, one, GAZ)[0]
    if "already_recorded" not in got.failures:
        bad += 1
        print(f"FAIL recorded with nothing to add must skip: {got.flags}")

    # The birth-date gate: prose against the article's own births category.
    d = dossier()
    d.birth_evidence = Evidence(qid="Q1", title="t")
    d.birth_evidence.categories = ["1985"]
    dob = proposal(property="P569", position_qid=None, value="1985-09-22",
                   start=None, end=None,
                   quote="ur. 22 września 1985 w Bolesławcu")
    got = check({"qid": "Q1", "proposals": [dob]}, d, GAZ)[0]
    rule = records("s", d, [got], campaign="c")[0].decision.rule
    if rule != "birth_date":
        bad += 1
        print(f"FAIL birth date with two channels: got {rule}")
    d.birth_evidence.categories = ["1986"]
    got = check({"qid": "Q1", "proposals": [dob]}, d, GAZ)[0]
    if "dob_disagrees_with_category" not in got.failures:
        bad += 1
        print(f"FAIL birth date contradicting its category: {got.failures}")

    total = len(CASES) + 10
    if bad:
        raise SystemExit(f"\n{bad} of {total} enrichment checks failed")
    print(f"{total} enrichment checks pass (rules, undated split, qualifier "
          f"isolation, birth-date channels)")


if __name__ == "__main__":
    main()
