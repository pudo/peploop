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
from wd.gazetteer import Entry, Gazetteer, is_offerable  # noqa: E402
from wd.infobox import Evidence  # noqa: E402
from wd.officebox import Tenure  # noqa: E402
from wd.dossier import territory_langs  # noqa: E402
from wd.positions import OfficeIndex, fold, tokens  # noqa: E402
from wd.rerank import MATCH_KINDS, settle  # noqa: E402

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


#: A frozen slice of Poland's real index, carrying the two offices the old
#: matcher wrongly queued for creation and the three generic classes it would
#: have matched them to instead. Real QIDs and real labels: the point of these
#: pins is that the shapes are the ones Wikidata actually has.
FIXTURE = [
    ("Q140428371", "Marshal of Warmian-Masurian Voivodeship"),
    ("Q140458581", "Marshal of Łódź Voivodeship"),
    ("Q1558362", "voivodeship marshal"),
    ("Q1558362", "marszałek województwa"),
    ("Q25919989", "Polish Minister of Family, Labour and Social Policy"),
    ("Q107919654", "Minister of Family and Social Policy"),
    ("Q177529", "mayor"),
    ("Q11788787", "Chief Inspector"),
    ("Q130582164", "member of the voivodeship sejmik"),
    ("Q111008336", "chair of the city council of Warsaw"),
    ("Q25598671", "Minister for Foreign Affairs (Poland)"),
    ("Q124460155", "Undersecretary of State"),
]

RETRIEVAL_CHECKS = 24


def check_retrieval() -> int:
    """Pin what the index must and must not surface as a *covering* match.

    `covers` is the asymmetry the whole placement lane rests on: the candidate
    has to name everything the query names. It is the one rule someone will be
    tempted to relax to raise the match count, and relaxing it writes a named
    person's mayoralty onto `Q177529 mayor`.
    """
    bad = 0
    index = OfficeIndex(country_qid="Q36")
    for qid, label in FIXTURE:
        index.add(qid, label)

    def top(query, *terms):
        hits = index.search([query, *terms], limit=3)
        return hits[0] if hits else None

    # Folding: the old `[^a-z0-9]` strip deleted non-ASCII rather than
    # transliterating it, so `Łódź` became `d`.
    if fold("Łódź Voivodeship") != "lodz voivodeship":
        bad += 1
        print(f"FAIL fold diacritics: {fold('Łódź Voivodeship')!r}")
    if fold("Warmian–Masurian") != "warmian-masurian":
        bad += 1
        print(f"FAIL fold en-dash: {fold('Warmian–Masurian')!r}")
    if "the" in tokens("Mayor of the City"):
        bad += 1
        print("FAIL stopwords not dropped")
    if not tokens("The Of"):
        bad += 1
        print("FAIL stripping emptied a name with no content tokens")

    # The two real items the label search missed, and why.
    hit = top("Marshal of Warmian–Masurian Voivodeship")
    if not (hit and hit.qid == "Q140428371" and hit.covers):
        bad += 1
        print(f"FAIL en-dash retrieval: {hit}")
    hit = top("Minister of Family, Labour and Social Policy")
    if not (hit and hit.qid == "Q25919989" and hit.covers):
        bad += 1
        print(f"FAIL renamed-office retrieval: {hit}")

    # The generic-office trap, three ways. Each of these is a real row from
    # Poland's queue whose best candidate is the *class*, not the seat. They
    # may be retrieved — the reranker needs to see and reject them — but they
    # must never be reported as covering.
    for query, generic in (("Mayor of Chełm", "Q177529"),
                           ("Chief Labour Inspector", "Q11788787"),
                           ("member of the Łódź Voivodeship Sejmik", "Q130582164")):
        hits = {h.qid: h for h in index.search([query], limit=5)}
        hit = hits.get(generic)
        if hit is not None and hit.covers:
            bad += 1
            print(f"FAIL generic class covers {query!r}: {hit}")

    # A verdict kind that is not a match must never place an item.
    if "generic-class" in MATCH_KINDS or "wrong-office" in MATCH_KINDS:
        bad += 1
        print(f"FAIL non-match kind counted as a match: {MATCH_KINDS}")

    # The two-signal rule. Every one of these is a way a plausible verdict must
    # still fail to become a statement on a public database.
    SHOWN = ["Q140428371", "Q1558362"]
    for name, args, want in (
        ("a clean match applies",
         ("same-office", "Q140428371", SHOWN, None), ("Q140428371", None)),
        ("a rename applies",
         ("renamed", "Q140428371", SHOWN, None), ("Q140428371", None)),
        ("a generic-class verdict never applies",
         ("generic-class", "Q1558362", SHOWN, None), (None, None)),
        ("a wrong-office verdict never applies",
         ("wrong-office", "Q1558362", SHOWN, None), (None, None)),
        ("a QID off the shortlist is refused",
         ("same-office", "Q99999999", SHOWN, None), (None, "off-shortlist")),
        ("an item naming no polity is refused",
         ("same-office", "Q1558362", SHOWN, "no-polity"), (None, "no-polity")),
    ):
        got = settle(*args)
        if got != want:
            bad += 1
            print(f"FAIL settle: {name}: got {got}, want {want}")

    # Which wikis a country's politicians are written up in. `rigour` holds
    # ISO 639-3 and Wikipedia is 639-1, so the conversion is load-bearing.
    for code, want in (
        ("cz", ("cs",)),                    # 14th in the global size ordering
        ("be", ("de", "fr", "nl")),         # multilingual
        ("ua", ("ru", "uk")),
        ("xx", ()),                         # an unknown code must not raise
    ):
        got = territory_langs(code)
        if got != want:
            bad += 1
            print(f"FAIL territory_langs({code!r}): got {got}, want {want}")
    # South Africa lists twelve official languages, three with no two-letter
    # code at all. `en` has to win the one slot a two-wiki read can spare.
    # What may be offered as a choice at all. The holders signal is what keeps
    # `not_a_position` from over-firing on an item people demonstrably hold.
    for name, entry, want in (
        ("a clean office", Entry(qid="Q1", holders=3), True),
        ("an unheld non-position (an army rank)",
         Entry(qid="Q2", defects=["not_a_position"], holders=0), False),
        ("a doubted item people actually hold",
         Entry(qid="Q3", defects=["not_a_position"], holders=1), True),
    ):
        if is_offerable(entry) is not want:
            bad += 1
            print(f"FAIL is_offerable: {name}: got {not want}")

    za = territory_langs("za")
    if not za or za[0] != "en" or None in za:
        bad += 1
        print(f"FAIL territory_langs('za'): {za}")
    return bad


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

    # The statement's own property must survive having qualifiers attached. A
    # loop variable named `prop` rebound it, and the rendered .qs carried a P39
    # whose property column read "P768" — valid syntax, wrong statement.
    got = check({"qid": "Q1", "proposals": [proposal(district="Legnica district",
                                                     group="Civic Club")]},
                dossier(), GAZ, qualifiers={"P768": DISTRICTS, "P4100": GROUPS})[0]
    st = records("s", dossier(), [got], campaign="c")[0].statements[0]
    if st.property != "P39" or st.value.id != "Q9":
        bad += 1
        print(f"FAIL qualifiers rebound the statement: {st.property}={st.value.id}")
    if {q.property for q in st.qualifiers} != {"P580", "P582", "P768", "P4100"}:
        bad += 1
        print(f"FAIL qualifier snaks: {[q.property for q in st.qualifiers]}")

    # An open-ended statement that the evidence closes is the same tenure, not a
    # new one. Reading it as new duplicated four Polish seats in a claims file.
    open_ended = dossier(tenures=[{"position": "Q9", "start": "2013", "end": None,
                                   "qualifiers": ["P580"]}])
    got = check({"qid": "Q1", "proposals": [proposal()]}, open_ended, GAZ)[0]
    rule = records("s", open_ended, [got], campaign="c")[0].decision.rule
    if rule != "closes_existing_statement":
        bad += 1
        print(f"FAIL closing an open-ended statement: got {rule} ({got.flags})")

    # A recorded span the evidence contradicts is a human's call, not an add.
    other = dossier(tenures=[{"position": "Q9", "start": "2013", "end": "2021",
                              "qualifiers": ["P580", "P582"]}])
    got = check({"qid": "Q1", "proposals": [proposal()]}, other, GAZ)[0]
    rule = records("s", other, [got], campaign="c")[0].decision.rule
    if rule != "contradicts_recorded":
        bad += 1
        print(f"FAIL contradicting span: got {rule} ({got.flags})")

    # One office needing both a merge and a new statement has no safe write
    # order, so the whole person is surgical rather than a batch line.
    mixed = check({"qid": "Q1", "proposals": [
        proposal(),                                   # closes the open-ended one
        proposal(start="2019", end="2023",
                 quote="served as Minister of Roads from 2013 to 2017"),
    ]}, open_ended, GAZ)
    rules = {records("s", open_ended, [c], campaign="c")[0].decision.rule
             for c in mixed}
    if rules != {"mixed_write_paths"}:
        bad += 1
        print(f"FAIL merge plus creation on one office: got {rules}")

    # The structural backstop: every merge rule must be named in the renderer's
    # refusal list, or a future rule could be routed to the API silently.
    merge_rules = {"dates_existing_statement", "closes_existing_statement",
                   "qualifies_existing_statement"}
    text = (Path(__file__).resolve().parent / "render_edit_plan.py").read_text()
    missing = [r for r in merge_rules if f'"{r}"' not in text]
    if missing:
        bad += 1
        print(f"FAIL render_edit_plan.py must refuse to API-route: {missing}")

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

    bad += check_retrieval()

    total = len(CASES) + 15 + RETRIEVAL_CHECKS
    if bad:
        raise SystemExit(f"\n{bad} of {total} enrichment checks failed")
    print(f"{total} enrichment checks pass (rules, undated split, qualifier "
          f"isolation, birth-date channels, office retrieval)")


if __name__ == "__main__":
    main()
