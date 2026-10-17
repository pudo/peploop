"""Pin pepcorp's rules: the gates, the seat table, name resolution, the dates, and the share's rendering.

    .venv/bin/python -m peploop.corp.check_rules
"""

from datetime import date

from peploop import propose, qs
from peploop.corp import actors, country, load, rules
from peploop.tree.check_filter import expect

TODAY = date(2026, 10, 17)


def answer(kind="enterprise", active=True, verdict="state", level="national", owners=((0, "owner"),),
           quote="Q is owned by the province.", seats=()) -> dict:
    return {"kind": kind, "active": active, "seats": list(seats), "notes": "",
            "control": {"verdict": verdict, "level": level, "quote": quote, "article": "xx",
                        "owners": [{"relation": rel, "controller": i, "name": None, "quote": quote, "article": "xx"}
                                   for i, rel in owners]}}


def seat(name="Erika Muster", body="supervisory", role="member", start="2021", end=None, current=True,
         quote="Erika Muster sits on the supervisory board.") -> dict:
    return {"name": name, "body": body, "role": role, "start": start, "end": end, "current": current,
            "quote": quote, "article": "xx"}


def ent(**claims: list[str]) -> dict:
    return {"claims": {p: [{"rank": "normal", "mainsnak": {"datavalue": {"value": {"id": q}}}} for q in qs_]
                       for p, qs_ in claims.items()}}


MESSAGE = "Q  is owned by\nthe province. Erika Muster sits on the supervisory board. Max Probe runs it."


def gates() -> None:
    expect(rules.gate(answer(), MESSAGE) is None, "a state-controlled national enterprise passes")
    expect(rules.gate(answer(kind="institution"), MESSAGE) is None, "a state institution passes")
    expect(rules.gate(answer(level="regional"), MESSAGE) is None, "the regional tier passes")
    expect(rules.gate(answer(kind="government"), MESSAGE) == "kind:government", "a ministry is peploop's")
    expect(rules.gate(answer(kind="other"), MESSAGE) == "kind:other", "a building or a channel is not written on")
    expect(rules.gate(answer(active=False), MESSAGE) == "inactive", "a dissolved enterprise is skipped")
    expect(rules.gate(answer(verdict="unclear"), MESSAGE) == "control:unclear", "unclear control writes nothing")
    expect(rules.gate(answer(level="municipal"), MESSAGE) == "level:municipal", "the municipal tier waits")
    expect(rules.gate(answer(level="municipal"), MESSAGE, ("national", "regional", "municipal")) is None,
           "a country that writes the municipal tier passes it")
    expect(rules.gate(answer(quote="Q is owned by the state."), MESSAGE) == "control_unquoted",
           "a control quote not in the articles is refused")
    expect(rules.quoted("q is owned by the province.", MESSAGE), "a quote differing only in case counts")


#: (kind, body, role) → the statement it becomes, cell by cell.
TABLE = {
    ("enterprise", "executive", "head"): ("P169", None),
    ("enterprise", "board", "head"): ("P169", None),
    ("enterprise", "executive", "chair"): ("P169", None),
    ("institution", "executive", "head"): ("P1037", None),
    ("institution", "executive", "chair"): ("P1037", None),
    ("enterprise", "supervisory", "chair"): ("P5052", "Q15818143"),
    ("institution", "supervisory", "chair"): ("P5052", "Q140686"),
    ("enterprise", "board", "chair"): ("P488", None),
    ("institution", "board", "chair"): ("P488", None),
    ("enterprise", "supervisory", "member"): ("P5052", None),
    ("institution", "supervisory", "member"): ("P5052", None),
    ("enterprise", "supervisory", "deputy_chair"): ("P5052", "Q1127270"),
    ("enterprise", "board", "deputy_chair"): ("P3320", "Q1127270"),
    ("enterprise", "executive", "member"): ("P3320", "Q141755781"),
    ("institution", "executive", "member"): ("P3320", "Q141755781"),
    ("enterprise", "board", "member"): ("P3320", None),
    ("enterprise", "executive", "managing_director"): ("P3320", "Q19940089"),
    ("institution", "executive", "managing_director"): ("P3320", "Q19940089"),
}


def seats() -> None:
    for key, want in TABLE.items():
        got = rules.seat_statement(*key)
        expect(got == want, f"{' '.join(key)} → {want[0]}" + (f" + {want[1]}" if want[1] else "") + f" (got {got})")
    expect(rules.seat_statement("enterprise", "executive", "party_secretary") is None,
           "a party secretary is unmapped unless the country's spec maps it")
    extra = {"party_secretary": ("P3320", "Q900500")}
    expect(rules.seat_statement("enterprise", "executive", "party_secretary", extra) == ("P3320", "Q900500"),
           "a country's spec maps its own seats")


def names() -> None:
    links = {"xx": {"Erika Muster": "Q900001", "Max Probe (Manager)": "Q900002", "Probe": "Q900003"},
             "en": {"Hans Beispiel": "Q900004"}}
    expect(rules.linked("Erika Muster", "xx", links) == ["Q900001"], "a linked name resolves")
    expect(rules.linked("Dr. Max Probe", "xx", links) == ["Q900002"], "a title and a disambiguator fall away")
    expect(rules.linked("Hans Beispiel", "xx", links) == ["Q900004"], "another language's link is the fallback")
    expect(rules.linked("Fritz Fremd", "xx", links) == [], "an unlinked name resolves to nothing")


def dates() -> None:
    t = propose.time_value
    expect(rules.seat_rule(seat(), t("2021"), None, TODAY) is None, "a current seat since 2021 is written")
    expect(rules.seat_rule(seat(current=False, start=None), None, None, TODAY) == "undated_former",
           "a former seat with no dates is not")
    expect(rules.seat_rule(seat(current=True), t("2020"), t("2023"), TODAY) == "current_ended",
           "a seat said current with an end is contradictory")
    expect(rules.seat_rule(seat(current=False), t("1990"), t("1995"), TODAY) == "tenure_ended",
           "a seat that ended a generation ago is a biography")
    expect(rules.seat_rule(seat(current=False), t("2015"), None, TODAY) == "open_unattested",
           "an open seat older than a term must be said to be current")
    expect(rules.seat_rule(seat(current=True, start=None), None, None, TODAY) is None,
           "an undated seat said to be current is written")
    expect(rules.seat_rule(seat(), t("2023"), t("2021"), TODAY) == "bad_dates", "an end before the start")


def control() -> None:
    arts = [{"lang": "xx", "url": "https://xx.wikipedia.org/wiki/Q", "rev": 1}]
    req = {"answer": answer(), "offered": ["Q900100", "Q900101", "Q900102"], "articles": arts,
           "message": MESSAGE, "links": {}}
    state = {"Q900100", "Q900102"}
    rows = rules.control_rows(req, ent(P31=["Q900200"]), None, state, {"Q900200": {"Q900200", "Q43229"}})
    marker, owner = rows
    expect(marker["_rule"] is None and marker["value"]["id"] == rules.MARKER, "an unmarked enterprise gets the marker")
    expect(owner["_rule"] is None and owner["property"] == "P127" and owner["value"]["id"] == "Q900100",
           "an owner the answer chose is written as P127")
    expect(not any(k.startswith("P") for k in owner["qualifiers"]), "no share, no qualifier on the link")
    rows = rules.control_rows(req, ent(P31=["Q900201"]), None, state, {"Q900201": {"Q900201", "Q270791"}})
    expect(rows[0]["_rule"] == "marked", "an enterprise already typed through a subclass keeps its type")
    inst = {**req, "answer": answer(kind="institution")}
    expect([r["property"] for r in rules.control_rows(inst, ent(), None, state, {})] == ["P127"],
           "an institution gets its link and no marker")
    parent = {**req, "answer": answer(kind="institution", owners=((2, "parent"),))}
    expect([(r["property"], r["value"]["id"]) for r in rules.control_rows(parent, ent(), None, state, {})]
           == [("P749", "Q900102")], "a parent body is written as P749, never P127")
    expect(rules.control_rows(parent, ent(), None, state, {}, None, frozenset({"Q900102"}))[0]["_rule"] == "parent_polity",
           "a state or province as parent organization is not written")
    checked = {**req, "qid": "Q900999"}
    expect(rules.control_rows(checked, ent(), None, state, {}, refused={("Q900999", "P127", "Q900100")})[1]["_rule"]
           == "link_unverified", "a link the quote check refuses is not written")
    two = {**req, "answer": answer(owners=((0, "owner"), (2, "owner")))}
    links = [r for r in rules.control_rows(two, ent(), None, state, {}) if r["property"] == "P127"]
    expect([o["value"]["id"] for o in links] == ["Q900100", "Q900102"] and all(o["_rule"] is None for o in links),
           "two public owners give two statements")
    by_name = {**req, "answer": answer(kind="institution", owners=((None, "parent"),))}
    by_name["answer"]["control"]["owners"][0]["name"] = "Ministry of Probes"
    row = rules.control_rows(by_name, ent(), None, state | {"Q900400"}, {}, {"Ministry of Probes": "Q900400"})[0]
    expect((row["property"], row["value"]["id"], row["_rule"]) == ("P749", "Q900400", None),
           "a named parent resolved through the article's links is written")
    row = rules.control_rows(by_name, ent(), None, state, {}, {"Ministry of Probes": "Q900400"})[0]
    expect(row["_rule"] == "controller_not_state", "a named body that is no government body is not")
    other = {**req, "answer": answer(owners=((1, "owner"),))}
    expect(rules.control_rows(other, ent(), None, state, {})[1]["_rule"] == "controller_not_state",
           "a controller that is no state actor is not written")
    unq = {**req, "answer": answer()}
    unq["answer"]["control"]["owners"][0]["quote"] = "MSC bought a stake."
    expect(rules.control_rows(unq, ent(), None, state, {})[1]["_rule"] == "owner_unquoted",
           "an owner whose quote is not in the articles is not written")
    via = {**req, "answer": answer(owners=((1, "owner"),))}
    expect(rules.control_rows(via, ent(), ["Q900300", "Q900101", "Q900102"], state, {})[1]["_rule"]
           == "controller_not_state", "an owner on the loaded chain but no state actor is not enough")
    chain = ["Q900300", "Q900101", "Q900100"]
    expect(rules.control_rows(req, ent(), chain, state, {})[1]["_rule"] == "chain_reaches",
           "no shortcut to a controller the chain reaches through another owner")


def claim(prop: str, value: str, guid: str) -> dict:
    return {"id": guid, "rank": "normal", "mainsnak": {"property": prop, "datavalue": {"value": {"id": value}}}}


def crawler_cases() -> None:
    """The cases OpenSanctions' crawler runs got wrong, pinned."""
    arts = [{"lang": "xx", "url": "https://xx.wikipedia.org/wiki/Q", "rev": 1}]
    base = {"offered": ["Q900100", "Q900101", "Q900102"], "articles": arts, "message": MESSAGE, "links": {}}
    state = {"Q900100", "Q900600"}
    # A private co-owner beside the state owner is not linked; the state one is.
    req = {**base, "answer": answer(owners=((0, "owner"), (1, "owner")))}
    links = [r for r in rules.control_rows(req, ent(), None, state, {}) if r["property"] == "P127"]
    expect([(o["value"]["id"], o["_rule"]) for o in links] == [("Q900100", None), ("Q900101", "controller_not_state")],
           "a co-owner that is no state body gets no link")
    # A sovereign fund's holding is written only on its own verdict, not the fund's.
    held = {**base, "offered": ["Q900600"], "answer": answer(verdict="unclear", owners=((0, "owner"),))}
    expect(rules.gate(held["answer"], MESSAGE) == "control:unclear", "a fund's minority holding is not written")
    controlled = {**base, "offered": ["Q900600"], "answer": answer(owners=((0, "owner"),))}
    rows = rules.control_rows(controlled, ent(), None, state, {})
    expect([r["property"] for r in rows] == ["P31", "P127"] and all(r["_rule"] is None for r in rows),
           "a company the fund controls gets the marker and the link")
    # A subsidiary of an enterprise this run finds state-controlled is itself marked.
    sub = {**base, "offered": ["Q900700"], "answer": answer(owners=((0, "owner"),))}
    rows = rules.control_rows(sub, ent(), ["Q900800", "Q900700", "Q900100"], state | {"Q900700"}, {})
    expect(rows[0]["property"] == "P31" and rows[0]["_rule"] is None, "a state enterprise's subsidiary gets the marker")
    # A municipal verdict on an item marked as a state enterprise: municipal marker added, the wrong one proposed.
    muni = {**base, "answer": answer(level="municipal")}
    marked = {"claims": {"P31": [claim("P31", "Q270791", "Q1$A")]}}
    kind, add, wrong = rules.correction(muni, marked, {"Q270791": {"Q270791"}}, ("national", "regional"))
    expect(kind == "municipal" and [a["value"]["id"] for a in add] == [rules.MUNICIPAL] and [c["id"] for c in wrong] == ["Q1$A"],
           "a municipal body marked state-owned gains the municipal marker and loses the state one")
    kind, add, wrong = rules.correction(muni, marked, {"Q270791": {"Q270791"}},
                                        ("national", "regional", "municipal"))
    expect(kind is None, "where the municipal tier is written, a municipal body is no correction")
    priv = {**base, "answer": answer(verdict="private")}
    kind, add, wrong = rules.correction(priv, marked, {"Q270791": {"Q270791"}}, ("national", "regional"))
    expect(kind == "private" and not add and [c["id"] for c in wrong] == ["Q1$A"], "a private body's marker is proposed for removal only")
    unq = {**base, "answer": answer(verdict="private", quote="Nobody said this.")}
    expect(rules.correction(unq, marked, {"Q270791": {"Q270791"}}, ("national", "regional"))[0] is None,
           "no correction without a quote")
    sub = {"claims": {"P31": [claim("P31", "Q900900", "Q1$B")]}}
    expect(rules.correction(muni, sub, {"Q900900": {"Q900900", "Q270791"}}, ("national", "regional"))[0] is None,
           "a subclass someone chose, such as a mixed public company, is never proposed for removal")
    city = {**base, "answer": answer(level="municipal", owners=((0, "owner"),))}
    expect(rules.correction(city, marked, {"Q270791": {"Q270791"}}, ("national", "regional"), frozenset({"Q900100"}))[0] is None,
           "a company of a city-state, which is a first-level subdivision, is not corrected to municipal")
    # The head is written once: not as CEO where the same person is already director.
    links = {"xx": {"Max Probe": "Q901000"}}
    head = {**base, "links": links, "message": MESSAGE + " Max Probe runs it.",
            "answer": answer(seats=[seat(name="Max Probe", body="executive", role="head", quote="Max Probe runs it.")])}
    rows = rules.seat_rows(head, {"Q901000"}, TODAY, None, ent(P1037=["Q901000"]))
    expect(rows[0]["property"] == "P169" and rows[0]["_rule"] == "head_other", "a head already recorded as director is not written again")
    rows = rules.seat_rows(head, {"Q901000"}, TODAY, None, ent())
    expect(rows[0]["_rule"] is None, "a head recorded under neither property is written")
    rows = rules.seat_rows(head, {"Q901000"}, TODAY, None, ent(), frozenset({"Q901000"}))
    expect(rows[0]["_rule"] == "holder_dead", "no open seat for a person who has died")
    # A ministry is a parent, never an owner; a link one step past an existing one is a shortcut.
    owner = {**base, "answer": answer(kind="institution", owners=((0, "owner"),))}
    expect(rules.control_rows(owner, ent(), None, state, {}, government=frozenset({"Q900100"}))[0]["_rule"] == "owner_ministry",
           "a ministry is never written as owner")
    expect(rules.control_rows(owner, ent(), None, state, {}, reached=frozenset({"Q900100"}))[0]["_rule"] == "chain_existing",
           "no link that shortcuts a chain the item already has")
    line = qs.describe("pepcorp", ["+Q900000", "P31", "Q270791"])
    expect(line.endswith("mark as a state-owned enterprise"), "the marker says what it marks")
    # Never candidates: sports clubs, diplomatic missions, places; and a country's chambers.
    expect({"Q476028", "Q847017", "Q7843791", "Q3917681", "Q56061", "Q192350", "Q7188"} <= load.EXCLUDED,
           "clubs, missions, places, ministries and governments are never candidates")


def unowned() -> None:
    """An enterprise with no public owner named is not written on, whatever the item already says."""
    import inspect
    src = inspect.getsource(rules.decide)
    expect('kind"] == "enterprise" and not links' in src and "enterprise_unowned" in src,
           "an enterprise whose article names no public owner is gated out")


def historic() -> None:
    def state(types: list[str], end: str | None = None) -> dict:
        e = ent(P31=types)
        if end:
            e["claims"]["P576"] = [{"rank": "normal", "mainsnak": {"datavalue": {"value": {"time": end, "precision": 9}}}}]
        return e
    expect(country.historical(state(["Q3024240"], "+1945-05-08T00:00:00Z")), "a predecessor state that ended before 1991 is historical")
    expect(not country.historical(state(["Q3024240"])), "a historical type with no end date counts as current")
    expect(not country.historical(state(["Q3024240"], "+2011-01-01T00:00:00Z")), "an end after the cutoff counts as current")
    expect(not country.historical(state(["Q6256"], "+1945-05-08T00:00:00Z")), "an end date alone, without the type, is not enough")


def reach() -> None:
    a = actors.Actors(state="Q900000", kinds={"Q900000": "state"},
                      links={"P127": {"Q900000": {"Q1"}, "Q1": {"Q2"}, "Q3": {"Q4"}}, "P749": {"Q2": {"Q3"}}})
    chains = a.reach()
    expect(a.parented() == set(), "parented means a state actor's direct child")
    a.links["P749"]["Q900000"] = {"Q9"}
    expect(a.parented() == {"Q9"}, "a body whose parent organization is a state actor")
    expect(chains["Q3"] == ["Q3", "Q2", "Q1", "Q900000"], "a chain runs from the item to the actor, through owners and parents")
    expect("Q4" not in chains, "a chain longer than the hop limit is not followed")
    kinds = actors.classify("Q900000", {"Q900000", "Q900001"}, {"Q900010": {"Q900020"}, "Q900011": {"Q900020"}},
                            {"Q900010": {"Q900001"}, "Q900011": {"Q900099"}}, {"Q900020": {"Q900020", "Q327333"}})
    expect(kinds.get("Q900010") == "government", "an agency placed in a subdivision is a state actor")
    expect("Q900011" not in kinds, "another country's agency is not")
    kinds = actors.classify("Q900000", {"Q900000"}, {"Q900012": {"Q900021"}}, {"Q900012": {"Q900000"}},
                            {"Q900021": {"Q900021", "Q2659904", "Q56061"}})
    expect("Q900012" not in kinds, "a municipality the type tree calls a government organization is no actor")
    kinds = actors.classify("Q900000", {"Q900000", "Q900001"}, {"Q900013": {"Q900020"}, "Q900014": {"Q900020"}},
                            {"Q900013": {"Q900000"}, "Q900014": {"Q900000"}}, {"Q900020": {"Q900020", "Q35798"}},
                            jurisdictions={"Q900013": {"Q900050"}, "Q900014": {"Q900001"}})
    expect("Q900013" not in kinds, "a town's administration, placed in the country but governing a town, is no actor")
    expect(kinds.get("Q900014") == "government", "a body governing a first-level subdivision is one")


def filters() -> None:
    e = {"claims": {}, "sitelinks": {"xxwiki": {"title": "Q"}}}
    expect(load.classify(e, True, ["xx", "en"]) is None, "an organisation with an article is kept")
    expect(load.classify(None, True, ["xx"]) == "missing", "a deleted item is dropped")
    expect(load.classify({**ent(P576=["Q1"]), "sitelinks": e["sitelinks"]}, True, ["xx"]) == "dissolved",
           "a dissolved enterprise is dropped")
    expect(load.classify(e, False, ["xx"]) == "not_organisation", "a building is dropped")
    expect(load.classify({"claims": {}, "sitelinks": {"frwiki": {}}}, True, ["xx", "en"]) == "no_article",
           "no article in the country's languages or English")


def main() -> None:
    gates()
    seats()
    names()
    dates()
    control()
    crawler_cases()
    unowned()
    historic()
    reach()
    filters()


if __name__ == "__main__":
    main()
