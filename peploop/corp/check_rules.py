"""Pin pepcorp's rules: the gates, the seat table, name resolution, the dates, and the share's rendering.

    .venv/bin/python -m peploop.corp.check_rules
"""

from datetime import date
from pathlib import Path

from peploop import eras, evidence, qs
from peploop.dates import time_value
from peploop.corp import actors, country, decide, load, reask, rules
from peploop.checks import expect

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
    expect(rules.gate(answer(level="municipal"), MESSAGE, ("national", "regional", "municipal"), unit="Q900050") is None,
           "a country that writes the municipal tier passes it, under a unit of 50,000 or more")
    expect(rules.gate(answer(quote="Q is owned by the state."), MESSAGE) == "control_unquoted",
           "a control quote not in the articles is refused")
    expect(evidence.quoted("q is owned by the province.", MESSAGE), "a quote differing only in case counts")


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
    expect(rules.norm("JUDr. Ing. Erika Muster, Ph.D.") == rules.norm("Ing. Erika Muster, CSc., MBA")
           == rules.norm("Mgr. Erika Muster MBA") == "erika muster", "degrees after a name fall away")
    expect(rules.norm("Charles, Prince of Wales") == "charles prince of wales", "a comma before a title stays")
    page = ('<p><a rel="mw:WikiLink" href="./Ministerstwo_Zdrowia_(Polska)">Ministerstwa Zdrowia</a>'
            '<a rel="mw:WikiLink" href="./Jan_Kowalski#Kariera">Janem Kowalskim</a>'
            '<a rel="mw:WikiLink" href="./Prezes_A">prezes</a><a rel="mw:WikiLink" href="./Prezes_B">prezes</a>'
            '<a rel="mw:WikiLink" href="./Kategoria:X">X</a><a rel="mw:ExtLink" href="https://x.org">Y</a></p>')
    items = {"Ministerstwo Zdrowia (Polska)": "Q900010", "Jan Kowalski": "Q900011", "Prezes A": "Q900012",
             "Prezes B": "Q900013"}
    found = decide.link_names(page, lambda titles: {t: items[t] for t in titles if t in items})
    expect(rules.linked("Ministerstwa Zdrowia", "xx", {"xx": found}) == ["Q900010"],
           "an owner named in an inflected form resolves through the link's anchor text")
    expect(rules.linked("Janem Kowalskim", "xx", {"xx": found}) == ["Q900011"], "so does a person")
    expect("prezes" not in found, "an anchor text linked to two items resolves to nothing")
    red = '<a rel="mw:WikiLink" href="./Jan_Nowak?action=edit&amp;redlink=1" class="new">Jan Nowak</a>'
    asked: list[str] = []
    decide.link_names(red, lambda titles: asked.extend(titles) or {})
    expect(asked == [], "a red link is not looked up")
    chunks = decide.title_chunks(["Национален статистически институт"] * 120)
    expect(all(len(c) <= 50 and sum(len(decide.quote(t)) + 3 for t in c) <= 6000 for c in chunks)
           and sum(map(len, chunks)) == 120, "Cyrillic titles are batched by their encoded length")


def dates() -> None:
    t = time_value
    expect(rules.seat_rule(seat(), t("2021"), None, TODAY) is None, "a current seat since 2021 is written")
    expect(rules.seat_rule(seat(current=False, start=None), None, None, TODAY) == "undated_former",
           "a former seat with no dates is not")
    expect(rules.seat_rule(seat(current=True), t("2020"), t("2023"), TODAY) == "current_ended",
           "a seat said current with an end is contradictory")
    expect(rules.seat_rule(seat(current=False), t("1990"), t("1995"), TODAY) == "tenure_ended",
           "a seat that ended a generation ago is a biography")
    expect(rules.seat_rule(seat(), t("2026-11-01"), None, TODAY) == "future",
           "a head from next month is not written, though the year is this one")
    expect(rules.seat_rule(seat(), t("2026"), None, TODAY) is None and rules.seat_rule(seat(), t("2026-10"), None, TODAY) is None,
           "a start this year or this month, at that precision, is not future")
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
    # A municipal verdict on an item marked as a state enterprise: the municipal marker is added beside it.
    muni = {**base, "answer": answer(level="municipal")}
    marked = {"claims": {"P31": [claim("P31", "Q270791", "Q1$A")]}}
    kind, add = rules.correction(muni, marked, {"Q270791": {"Q270791"}}, ("national", "regional"))
    expect(kind == "municipal" and [a["value"]["id"] for a in add] == [rules.MUNICIPAL],
           "a municipal body marked state-owned gains the municipal marker, and keeps the state one")
    both = {"claims": {"P31": [claim("P31", "Q270791", "Q1$A"), claim("P31", rules.MUNICIPAL, "Q1$C")]}}
    expect(rules.correction(muni, both, {"Q270791": {"Q270791"}}, ("national", "regional"))[0] is None,
           "a body carrying both markers is no correction")
    kind, add = rules.correction(muni, marked, {"Q270791": {"Q270791"}},
                                 ("national", "regional", "municipal"))
    expect(kind is None, "where the municipal tier is written, a municipal body is no correction")
    priv = {**base, "answer": answer(verdict="private")}
    expect(rules.correction(priv, marked, {"Q270791": {"Q270791"}}, ("national", "regional"))[0] is None,
           "a private body whose article does not date the sale keeps its marker untouched")
    priv["answer"]["control"]["ended"] = "1998-05"
    kind, add = rules.correction(priv, marked, {"Q270791": {"Q270791"}}, ("national", "regional"))
    expect(kind == "private" and [(a["value"]["id"], a["qualifiers"]["P582"]["time"]) for a in add]
           == [("Q270791", "+1998-05-00T00:00:00Z")], "a privatised body's marker is ended, never removed")
    unq = {**base, "answer": answer(verdict="private", quote="Nobody said this.")}
    expect(rules.correction(unq, marked, {"Q270791": {"Q270791"}}, ("national", "regional"))[0] is None,
           "no correction without a quote")
    sub = {"claims": {"P31": [claim("P31", "Q900900", "Q1$B")]}}
    expect(rules.correction(muni, sub, {"Q900900": {"Q900900", "Q270791"}}, ("national", "regional"))[0] is None,
           "a subclass someone chose, such as a mixed public company, is no contradiction")
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
    term = {**head, "answer": answer(seats=[seat(name="Max Probe", body="executive", role="head", start="2022",
                                                  end="2027", current=False, quote="Max Probe runs it.")])}
    rows = rules.seat_rows(term, {"Q901000"}, TODAY, None, ent())
    expect(rows[0]["_rule"] is None and "P582" not in rows[0]["qualifiers"],
           "a fixed term running past today is written as held, without its end")
    interim = {**head, "answer": answer(seats=[
        seat(name="Max Probe", body="executive", role="head", start="2024-07", current=False, quote="Max Probe runs it."),
        seat(name="Erika Muster", body="executive", role="head", start="2024-10", current=True)])}
    rows = rules.seat_rows(interim, {"Q901000"}, TODAY, None, ent())
    expect(rows[0]["_rule"] == "superseded", "a head left open before a later head is not written as current")
    # A ministry is a parent, never an owner; a link one step past an existing one is a shortcut.
    owner = {**base, "answer": answer(kind="institution", owners=((0, "owner"),))}
    expect(rules.control_rows(owner, ent(), None, state, {}, government=frozenset({"Q900100"}))[0]["_rule"] == "owner_ministry",
           "a ministry is never written as owner")
    national = {**base, "answer": answer(kind="enterprise", owners=((0, "owner"),))}
    rows = [r for r in rules.control_rows(national, ent(), None, state | {"Q900001"}, {}, government=frozenset({"Q900100"}),
                                          country="Q900001") if r["property"] == "P127"]
    expect([(r["value"]["id"], r["_rule"]) for r in rows] == [("Q900001", None)],
           "a national government named as owner is written as its state")
    both = {**base, "offered": ["Q900100", "Q900001"],
            "answer": answer(kind="enterprise", owners=((0, "owner"), (1, "owner")))}
    rows = [r for r in rules.control_rows(both, ent(), None, state | {"Q900001"}, {}, government=frozenset({"Q900100"}),
                                          country="Q900001") if r["property"] == "P127"]
    expect(len(rows) == 1, "the government and its state named together make one owner")
    via = rules.through_planned({"Q1": {"Q2", "Q3"}, "Q2": {"Q3"}, "Q4": {"Q5", "Q6"}, "Q5": {"Q6"}, "Q6": {"Q5"}},
                                {"Q7": set()})
    expect(via["Q1"] == {"Q3"}, "an owner this run also puts over the body's other owner is a shortcut")
    expect(via["Q4"] == set(), "two owners each planned over the other are a loop: neither is dropped")
    expect(rules.control_rows(owner, ent(), None, state, {}, reached=frozenset({"Q900100"}))[0]["_rule"] == "chain_existing",
           "no link that shortcuts a chain the item already has")
    line = qs.describe("pepcorp", ["+Q900000", "P31", "Q270791"])
    expect(line.endswith("mark as a state-owned enterprise"), "the marker says what it marks")
    # Never candidates: sports clubs, diplomatic missions, places; and a country's chambers.
    expect({"Q476028", "Q847017", "Q7843791", "Q3917681", "Q56061", "Q192350", "Q7188"} <= load.EXCLUDED,
           "clubs, missions, places, ministries and governments are never candidates")


def policy() -> None:
    """Statutory bodies, lists and forms as proof, the state's stand-ins, the marker check."""
    arts = [{"lang": "xx", "url": "https://xx.wikipedia.org/wiki/Q", "rev": 1}]
    base = {"qid": "Q900999", "offered": ["Q900100", "Q900200"], "articles": arts, "message": MESSAGE, "links": {}}
    state = {"Q900100", "Q900200", "Q900001"}
    # A public broadcaster set up by law, with no owner: state, typed, seats.
    tv = {**base, "answer": {**answer(kind="institution", owners=()), "statutory": "broadcaster"}}
    expect(rules.gate(tv["answer"], MESSAGE) is None, "a statutory institution with no owner passes")
    licensed = {**tv["answer"], "control": {**tv["answer"]["control"], "verdict": "unclear", "level": "none"}}
    expect(rules.gate(licensed, MESSAGE) is None, "a public broadcaster that is a licensed association still passes")
    expect(rules.gate({**licensed, "statutory": None}, MESSAGE) == "control:unclear", "an unclear body that is no statutory one does not")
    expect(rules.gate({**licensed, "control": {**licensed["control"], "verdict": "private"}}, MESSAGE) == "control:private",
           "a statutory-sounding body its articles call private does not")
    rows = rules.control_rows(tv, ent(), None, state, {})
    typed = [r for r in rows if r["property"] == "P31"]
    expect([(r["value"]["id"], r["_rule"]) for r in typed] == [("Q1126006", None)],
           "a public broadcaster without its class gets it")
    rows = rules.control_rows(tv, ent(P31=["Q900500"]), None, state, {"Q900500": {"Q900500", "Q1126006"}})
    expect([r["_rule"] for r in rows if r["property"] == "P31"] == ["typed"], "an item already typed is left alone")
    bare = {**base, "answer": {**answer(kind="institution", verdict="unstated", owners=(), quote=None), "statutory": "regulator"}}
    bare["answer"]["control"]["article"] = None
    expect([r["_rule"] for r in rules.control_rows(bare, ent(), None, state, {}) if r["property"] == "P31"]
           == ["statutory_unsourced"], "a class no control quote cites is not written")
    reg = {**base, "answer": {**answer(kind="institution", owners=()), "statutory": "regulator"}}
    rows = rules.control_rows(reg, ent(P31=["Q900801"]), None, state, {"Q900801": {"Q900801"}}, proof="form")
    expect([r["_rule"] for r in rows if r["property"] == "P31"] == ["typed"],
           "a regulator of a country's own state-only form is typed already")
    # Proof by list or form, only where the articles say nothing.
    silent = answer(verdict="unstated", owners=(), quote=None)
    expect(rules.gate(silent, MESSAGE) == "control:unstated", "silence alone proves nothing")
    expect(rules.gate(silent, MESSAGE, proof="list") is None, "silence with a holdings entry passes")
    expect(rules.gate(answer(verdict="unclear"), MESSAGE, proof="list") == "control:unclear",
           "an article naming a mere stake overrides the list")
    spec = country.Spec(cc="xx", forms={"Q900800": "institution"})
    expect(rules.proven({"seed": {"source": "https://list"}, "entity": {}}, spec) == "list", "a listed body is proven")
    expect(rules.proven({"seed": {"source": "https://xx.wikipedia.org/wiki/List"}, "entity": {}}, spec) is None
           and rules.proven({"seed": {"source": "https://www.wikidata.org/wiki/Q1"}, "entity": {}}, spec) is None
           and rules.proven({"seed": {"source": "Annual report"}, "entity": {}}, spec) is None,
           "a wiki page, a query or a bare title is no official list")
    expect(rules.proven({"seed": {"source": "https://list", "minority": True}, "entity": {}}, spec) is None,
           "a minority stake on the list proves nothing")
    expect(rules.proven({"seed": None, "entity": ent(P31=["Q900800"])}, spec) == "form", "a state-only form proves it")
    expect(rules.proven({"seed": None, "entity": ent(P31=["Q900801"])}, spec) is None, "another form does not")
    expect(rules.proven({"seed": None, "entity": ent(P31=["Q900800"])}, spec, "enterprise") is None,
           "an authority's form proves no enterprise")
    listed = {**base, "answer": silent}
    rows = rules.control_rows(listed, ent(), None, state, {}, country="Q900001", proof="list",
                              seed={"source": "https://list"})
    expect([(r["property"], r["value"]["id"], r["_rule"], r["qualifiers"]["_sources"]) for r in rows]
           == [("P31", "Q270791", None, [{"reference_url": "https://list"}]),
               ("P127", "Q900001", None, [{"reference_url": "https://list"}])],
           "a listed enterprise is marked and owned by the polity, both cited to the list")
    formed = {**base, "answer": answer(kind="institution", verdict="unstated", owners=(), quote=None)}
    expect(rules.control_rows(formed, ent(), None, state, {}, country="Q900001", proof="form") == [],
           "an institution proven by its form gets seats only, no link")
    ref = propose_refs({"qualifiers": {"_sources": [{"reference_url": "https://list"}]}})
    expect(ref == ["S854", '"https://list"', "S813"], "a list is cited by its URL")
    # The state's stand-in named as owner is written as the polity.
    treasury = {**base, "answer": answer(owners=((1, "owner"),))}
    links = [r for r in rules.control_rows(treasury, ent(), None, state, {}, country="Q900001",
                                           standins=frozenset({"Q900200"})) if r["property"] == "P127"]
    expect([(r["value"]["id"], r["_rule"]) for r in links] == [("Q900001", None)], "the state treasury as owner is the polity")
    # The polity is not added beside a state holder the item already names.
    held = {**base, "answer": answer(owners=((1, "owner"),))}
    links = [r for r in rules.control_rows(held, ent(P127=["Q900100"]), None, state, {}, country="Q900001",
                                           standins=frozenset({"Q900200"})) if r["property"] == "P127"]
    expect([r["_rule"] for r in links] == ["holder_existing"], "no polity beside an existing state holder")
    # Provinces named beside the national holder that leads are co-owners.
    shared = {**base, "offered": ["Q900100", "Q900002"], "answer": answer(owners=((0, "owner"), (1, "owner")))}
    links = [r for r in rules.control_rows(shared, ent(), None, state | {"Q900002"}, {},
                                           polities=frozenset({"Q900001", "Q900002"}), country="Q900001")
             if r["property"] == "P127"]
    expect([(r["value"]["id"], r["_rule"]) for r in links] == [("Q900100", None), ("Q900002", "co_owner")],
           "a province beside a national holder gets no owner link")
    links = [r for r in rules.control_rows(treasury, ent(P127=["Q900200"]), None, state, {}, country="Q900001",
                                           standins=frozenset({"Q900200"})) if r["property"] == "P127"]
    expect([r["_rule"] for r in links] == ["standin_existing"], "an item already owned by the stand-in gets no second owner")
    # A class the check refuses (a registry called a regulator).
    expect([r["_rule"] for r in rules.control_rows(reg, ent(), None, state, {}, refused={("Q900999", "P31", "Q1639780")})
            if r["property"] == "P31"] == ["class_unverified"], "a statutory class the check refuses is not written")
    expect([r["_rule"] for r in rules.control_rows(reg, ent(), None, state, {}) if r["property"] == "P31"] == [None],
           "one it accepts is")
    # A marker whose quote the check refuses.
    expect(rules.control_rows(treasury, ent(), None, state, {}, refused={("Q900999", "P31", "Q270791")})[0]["_rule"]
           == "marker_unverified", "a marker the quote check refuses is not written")


def propose_refs(row: dict) -> list:
    """The reference columns a planned row would carry, without the date's value."""
    from peploop import plan
    cols = qs.references(plan.references(row, {}))
    return [c for c in cols if not c.startswith("+")] if cols else []


def unowned() -> None:
    """An enterprise with no public owner named is not written on, whatever the item already says."""
    import inspect
    src = inspect.getsource(rules.decide)
    expect('kind"] == "enterprise" and not links' in src and "enterprise_unowned" in src,
           "an enterprise whose article names no public owner is gated out")
    expect('if (r["answer"]["kind"] == "enterprise" and links' in src and "no_state_owner" in src,
           "only an enterprise is gated out when no body named over it is the state's; an institution keeps its seats")


def listed() -> None:
    """A body the state's AMLR list names: in scope by the list, seats only, never an owner."""
    for why in ("control:unclear", "control:unstated", "control_unquoted", "level:municipal", "level:foreign",
                "enterprise_unowned", "no_state_owner"):
        expect(rules.listed_scope(why, True), f"a listed body stopped by {why} keeps its seats")
        expect(not rules.listed_scope(why, False), f"an unlisted one stopped by {why} does not")
    for why in ("kind:government", "kind:other", "inactive", "control:private"):
        expect(not rules.listed_scope(why, True), f"the list does not override {why}")
    expect(not rules.listed_scope(None, True), "a body that passes needs no override")
    expect(rules.gate(answer(kind="institution", verdict="unstated", owners=(), quote=None), MESSAGE)
           == "control:unstated" and rules.listed_scope("control:unstated", True),
           "a listed agency or central bank is an institution the list admits")
    import inspect
    src = inspect.getsource(rules.decide)
    expect("listed_seats(" in src and src.count("control_rows(") == 1,
           "a body the list alone admits gets its seats and no marker, link or class")
    expect("(set(passed) - parties - international) | set(actors.kinds)" in src,
           "a body the list alone admits is no state owner of others")
    expect("Q967861" in load.listed("ro"), "the asset's resolved bodies are the lane (National Bank of Romania)")
    expect(all(f.kind == "body" and not any("body" in e for e in f.expansion) for f in load.unresolved("ro")),
           "an unresolved row is a named-body row with no body in its expansion")


def party(kind="party", active=True, seats=()) -> dict:
    return {"kind": kind, "active": active, "seats": list(seats), "notes": ""}


def pseat(name="Erika Muster", role="chair", start="2021", end=None, current=True,
          quote="Erika Muster sits on the supervisory board.") -> dict:
    return {"name": name, "role": role, "start": start, "end": end, "current": current, "quote": quote, "article": "xx"}


def parties() -> None:
    """A party is admitted by its seat-holders, gets its seats only, and its executive organs alone are seats."""
    expect(rules.gate(party(), MESSAGE) is None, "an active party passes with no control question")
    expect(rules.gate(party("regional_branch"), MESSAGE) is None, "a party's regional branch passes")
    expect(rules.gate(party("local_branch"), MESSAGE) == "kind:local_branch", "a local branch waits for the local tier")
    expect(rules.gate(party("other"), MESSAGE) == "kind:other", "a youth wing, foundation or caucus is not written on")
    expect(rules.gate(party(active=False), MESSAGE) == "inactive", "a dissolved party is skipped")
    soe = {**answer(), "statutory": None}
    soe["control"]["ended"] = None
    expect(decide.readable(party(seats=[pseat()])) and decide.readable(soe),
           "the ledger reads a party's answer and a body's alike")
    expect(not decide.readable({**party(), "control": answer()["control"]}), "a party answer carries no control")
    # The seat table, by the idioms party items carry.
    for kind in rules.PARTY:
        for role, want in (("chair", ("P488", None)), ("deputy_chair", ("P3320", "Q1127270")),
                           ("secretary_general", ("P3975", None)), ("treasurer", ("P3320", "Q388338")),
                           ("member", ("P3320", None))):
            got = rules.seat_statement(kind, "*", role, {"member": ("P9999", None)})
            expect(got == want, f"{kind} {role} → {want} (got {got}); a spec's own seats do not reach a party")
    expect(rules.seat_statement("enterprise", "board", "secretary_general") is None
           and rules.seat_statement("party", "*", "head") is None, "party roles and body roles do not mix")
    # Non-governing bodies: the answer has no role for them, the prompt names them, the load drops the satellites.
    roles = set(decide.PartySeat.model_fields["role"].annotation.__args__)
    expect(roles == {"chair", "deputy_chair", "secretary_general", "treasurer", "member"},
           "a party seat is one of the executive organs' five roles")
    text = " ".join(decide.PARTY_PROMPT_PATH.read_text().split())
    expect(all(t in text for t in ("party congress", "council of delegates", "parliamentary group", "honorary chairs")),
           "the party prompt names the bodies that are no governing body")
    expect({"Q2493450", "Q11744698", "Q355844"} <= load.EXCLUDED, "youth wings, caucuses and electoral lists never load")
    expect(set(load.PARTY_LANES) <= set(load.LANES), "the party lanes are lanes")
    expect(load.branch(["Q900600"], {"Q900600", load.POLITICAL_PARTY}, frozenset()),
           "a part of a party typed as a party is a branch")
    expect(load.branch(["Q900601"], {"Q900601"}, frozenset({"Q900601"})),
           "so is one of the country's branch classes")
    expect(not load.branch(["Q900602"], {"Q900602"}, frozenset({"Q900601"})),
           "a working group, a current or an organ is not")
    expect(decide.party_wikis({"sitelinks": {"xxwiki": {}, "enwiki": {}}}, ["xx", "en"]) == ["xx"]
           and decide.party_wikis({"sitelinks": {"enwiki": {}}}, ["xx", "en"]) == ["en"],
           "a party is read in its own language, in English only where it has no other article")
    # Seats run through every seat rule a body's do.
    links = {"xx": {"Erika Muster": "Q900501", "Max Probe": "Q900502", "Old Chair": "Q900503", "Late Chair": "Q900504"}}
    msg = MESSAGE + " Max Probe co-leads it. Old Chair led it. Late Chair led it."
    req = {"qid": "Q900999", "message": msg, "links": links, "articles": [{"lang": "xx", "url": "u", "rev": 1}],
           "offered": [], "answer": party(seats=[
               pseat(), pseat("Max Probe", quote="Max Probe co-leads it.", start="2022"),
               pseat("Old Chair", quote="Old Chair led it.", start="2010", current=False),
               pseat("Late Chair", quote="Late Chair led it.", start="2023", current=True),
               pseat("Erika Muster", role="member", start="1990", end="1994", current=False)])}
    humans = {"Q900501", "Q900502", "Q900503", "Q900504"}
    rows = rules.seat_rows(req, humans, TODAY, dead={"Q900504"})
    got = [(r["property"], r["value"]["id"], r["_rule"]) for r in rows]
    expect(got == [("P488", "Q900501", None), ("P488", "Q900502", None), ("P488", "Q900503", "superseded"),
                   ("P488", "Q900504", "holder_dead"), ("P3320", "Q900501", "tenure_ended")],
           f"co-chairs are two P488; a predecessor left open, a dead holder and an old tenure are skipped (got {got})")
    import inspect
    src = inspect.getsource(rules.decide)
    expect("(set(passed) - parties - international)" in src, "a party or an international body is no state owner of others")
    expect(src.index("if r[\"qid\"] in parties") < src.index("control_rows("),
           "a party gets its seats before any marker, link or class is considered")


def iseat(name="Erika Muster", role="member", heads_body=False, start="2021", end=None, current=True,
          quote="Erika Muster sits on the supervisory board.") -> dict:
    return {"name": name, "role": role, "heads_body": heads_body, "start": start, "end": end, "current": current,
            "quote": quote, "article": "xx"}


def international() -> None:
    """An EU body or an organisation of states passes by being one, gets board seats only, and never its head."""
    body = {"kind": "eu_body", "active": True, "seats": [], "notes": ""}
    expect(rules.gate(body, MESSAGE) is None, "an active EU body passes with no control question")
    expect(rules.gate({**body, "kind": "international_organisation"}, MESSAGE) is None,
           "so does an international organisation")
    expect(rules.gate({**body, "kind": "other"}, MESSAGE) == "kind:other",
           "a parliament, court, college or committee of national officials is not written on")
    expect(rules.gate({**body, "active": False}, MESSAGE) == "inactive", "a wound-up body is skipped")
    expect(decide.readable({**body, "seats": [iseat()]}), "the ledger reads an international body's answer")
    for kind in rules.INTERNATIONAL:
        for role, want in (("chair", ("P5052", "Q140686")), ("deputy_chair", ("P5052", "Q1127270")),
                           ("member", ("P5052", None))):
            got = rules.seat_statement(kind, "*", role, {"member": ("P9999", None)})
            expect(got == want, f"{kind} {role} → {want} (got {got}): a board seat, the chair by role")
        expect(rules.seat_statement(kind, "*", "head") is None, f"{kind}: a head is never a seat")
    roles = set(decide.InternationalSeat.model_fields["role"].annotation.__args__)
    expect(roles == {"chair", "deputy_chair", "member"}, "an international seat is a board seat, never the head")
    # The head is peploop's: a person holding the body's office, or the head's chair where an office exists.
    msg = MESSAGE + " Max Probe chairs the board and heads the bank. Old Chair chairs it."
    links = {"xx": {"Erika Muster": "Q900501", "Max Probe": "Q900502", "Old Chair": "Q900503"}}
    req = {"qid": "Q900999", "message": msg, "links": links, "articles": [{"lang": "xx", "url": "u", "rev": 1}],
           "offered": [], "answer": {**body, "seats": [
               iseat(), iseat("Max Probe", role="chair", heads_body=True,
                              quote="Max Probe chairs the board and heads the bank."),
               iseat("Old Chair", role="chair", quote="Old Chair chairs it.")]}}
    rows = rules.seat_rows(req, {"Q900501", "Q900502", "Q900503"}, TODAY)
    kept = rules.head_excluded(rows, req["answer"]["seats"], set(), {})
    expect([(r["property"], r["_rule"]) for r in kept] == [("P5052", None)] * 3,
           "with no office of the body, every board seat is written, the head's chair too")
    held = rules.head_excluded(rows, req["answer"]["seats"], {"Q900800"}, {"Q900503": {"Q900800"}})
    expect([r["_rule"] for r in held] == [None, "head_office", "position_office"],
           "the head's chair is the head office's where one exists; a seat its holder holds by an office is the office's")
    expect(all(r["qualifiers"].get("P2868") == rules.item("Q140686") for r in rows[1:]), "a chair carries the chair role")
    titled = rules.head_excluded(rows, req["answer"]["seats"], set(), {}, "Chair")
    expect([r["_rule"] for r in titled] == [None, "head_office", "head_office"],
           "where the census titles the head its chair, every chair of the board is the head office's")
    titled = rules.head_excluded(rows, req["answer"]["seats"], set(), {}, "Executive Director")
    expect([r["_rule"] for r in titled] == [None, "head_office", None],
           "where the head is a director, the board's own chair is written, the head's chair is not")
    import inspect
    src = inspect.getsource(rules.decide)
    expect(src.index("if r[\"qid\"] in international") < src.index("control_rows("),
           "an international body gets its seats before any marker, link or class is considered")
    expect("international" in load.LANES and decide.asked_as({"lanes": ["international"]}) == "international",
           "the international lane is asked with its own prompt")
    expect(decide.international_wikis({"sitelinks": {"yywiki": {}, "zzwiki": {}}}, ("xx", "yy", "zz")) == ["yy"]
           and decide.international_wikis({"sitelinks": {"xxwiki": {}, "yywiki": {}}}, ("xx", "yy")) == ["xx"],
           "an international body is read in the first of the spec's wikis it has, one article")
    text = " ".join(decide.INTERNATIONAL_PROMPT_PATH.read_text().split())
    expect(all(t in text for t in ("head of the executive", "advisory", "a court", "heads_body", "honorary",
                                   "full-time officials")),
           "the international prompt leaves out the head, an executive board, advisory groups, courts and honorary seats")
    from peploop.corp import actors, country
    spec = country.get("eu")
    expect(spec.international and spec.tiers == ("international",) and spec.body_classes and spec.wikis,
           "the eu spec writes the international tier alone, with its classes and wikis")
    expect("Q245065" in actors.NOT_GOVERNMENT, "an intergovernmental organisation is never a state actor")


def municipal() -> None:
    """The municipal tier: the size proxy, the marker, a city-state, the correction, the sector lane, associations."""
    tiers = ("national", "regional", "municipal")
    arts = [{"lang": "xx", "url": "https://xx.wikipedia.org/wiki/Q", "rev": 1}]
    units = frozenset({"Q900050", "Q900051"})
    base = {"qid": "Q900999", "offered": ["Q900050", "Q900060"], "articles": arts, "message": MESSAGE, "links": {}}
    muni = {**base, "answer": answer(level="municipal", owners=((0, "owner"),))}
    # The gate, by the size of the controlling unit.
    expect(rules.gate(muni["answer"], MESSAGE, tiers) == "municipal_unit",
           "a municipal body with no unit of 50,000 or more over it is not written (residue)")
    expect(rules.gate(muni["answer"], MESSAGE) == "level:municipal", "a country not writing the tier skips it")
    expect(rules.gate(muni["answer"], MESSAGE, tiers, unit="Q900050") is None, "a large unit's body passes")
    expect(rules.gate(answer(level="municipal", quote="Nobody said this."), MESSAGE, tiers, unit="Q900050")
           == "control_unquoted", "the control quote is still needed")
    # Which unit controls it.
    expect(rules.municipal_unit(muni, ent(), None, units) == "Q900050", "a controller the answer chose that is a unit")
    small = {**base, "answer": answer(level="municipal", owners=((1, "owner"),))}
    expect(rules.municipal_unit(small, ent(P131=["Q900050"]), None, units) is None,
           "a smaller town's body is no large unit's, wherever it sits")
    expect(rules.municipal_unit(small, ent(), ["Q900999", "Q900060", "Q900051"], units) == "Q900051",
           "the chain on Wikidata ends at a unit")
    silent = {**base, "answer": answer(level="municipal", owners=())}
    expect(rules.municipal_unit(silent, ent(P159=["Q900051"]), None, units) == "Q900051",
           "with no controller named, the unit the body sits in")
    expect(rules.municipal_unit({**silent, "articles": []}, ent(P159=["Q900051"]), None, units) is None,
           "no article, no unit: the proxy wants both")
    # An inter-municipal association this run passes lends its unit to what it owns.
    assoc = {**base, "answer": answer(level="municipal", owners=((None, "owner"),))}
    assoc["answer"]["control"]["owners"][0]["name"] = "Water Union"
    expect(rules.municipal_unit(assoc, ent(), None, units, {"Water Union": "Q900070"}, {"Q900070": "Q900051"})
           == "Q900051", "a body an inter-municipal association owns is under the association's unit")
    expect(rules.municipal_unit(assoc, ent(), None, units, {"Water Union": "Q900070"}) is None,
           "an association the run does not pass gives no unit")
    # A city's administration (its jurisdiction the city) or a city's holding stands for its unit.
    admin = {"claims": ent(P1001=["Q900050"])["claims"]}
    holding = ent(P127=["Q900080"])
    entities = {"Q900080": admin, "Q900081": holding, "Q900082": ent(P127=["Q900081"]), "Q900083": ent(P131=["Q900050"])}
    behind = rules.controller_units({"Q900080", "Q900081", "Q900082", "Q900083"}, entities, units, hops=1)
    expect(behind == {"Q900080": "Q900050", "Q900081": "Q900050"},
           "a city's administration and its holding stand for the city; two owner steps or a location do not, at one hop")
    # A city administration named as owner is written as the city, unless the item already names it.
    adm = {**base, "offered": ["Q900080"], "answer": answer(level="municipal", owners=((0, "owner"),))}
    rows = rules.control_rows(adm, ent(), None, {"Q900050", "Q900080"}, {}, polities=units, admins={"Q900080": "Q900050"})
    expect([(r["property"], r["value"]["id"], r["_rule"]) for r in rows][1:] == [("P127", "Q900050", None)],
           "the city administration's ownership is the city's")
    rows = rules.control_rows(adm, ent(P127=["Q900080"]), None, {"Q900050", "Q900080"}, {}, polities=units,
                              admins={"Q900080": "Q900050"})
    expect(rows[1]["_rule"] == "standin_existing", "an item naming the administration as owner keeps it alone")
    # An owner the article does not link, named by its unit's label after one word.
    names = rules.unit_names({"Q900050": {"labels": {"xx": {"value": "Probstadt"}}, "aliases": {}},
                              "Q900051": {"labels": {"xx": {"value": "Hof"}}, "aliases": {"xx": [{"value": "Probstadt"}]}}})
    expect(names.get("probstadt") == "Q900050" and names.get("hof") == "Q900051",
           "a unit's label wins over another unit's alias")
    twice = rules.unit_names({"Q900050": {"labels": {"xx": {"value": "Hof"}}}, "Q900051": {"labels": {"yy": {"value": "Hof"}}}})
    expect(twice.get("hof") is None, "a label two units share stands for neither")
    expect(rules.name_unit("Town of Hof", names) is None and rules.name_unit("Town Hof", names) == "Q900051"
           and rules.name_unit("Hof", names) == "Q900051", "the unit's own label, or after one word, and no more")
    # The marker, as for the state tier, and never over a marker the item has.
    state = {"Q900050"}
    rows = rules.control_rows(muni, ent(), None, state, {}, polities=units)
    expect([(r["property"], r["value"]["id"], r["_rule"]) for r in rows]
           == [("P31", rules.MUNICIPAL, None), ("P127", "Q900050", None)],
           "a municipal enterprise gets the municipal marker and its city as owner")
    for have, rule in ((rules.MARKER, None), (rules.MUNICIPAL, "marked")):
        expect(rules.control_rows(muni, ent(P31=["Q900201"]), None, state, {"Q900201": {"Q900201", have}},
                                  polities=units)[0]["_rule"] == rule,
               f"an item reaching {have} keeps it" + (", and gains the municipal marker beside it" if rule is None else ""))
    expect(rules.control_rows(muni, ent(), None, state, {}, polities=units,
                              refused={("Q900999", "P31", rules.MUNICIPAL)})[0]["_rule"] == "marker_unverified",
           "a municipal marker whose control quote the check refuses is not written")
    inst = {**muni, "answer": answer(kind="institution", level="municipal", owners=((0, "parent"),))}
    expect([(r["property"], r["_rule"]) for r in rules.control_rows(inst, ent(), None, state, {}, polities=units)]
           == [("P749", "parent_polity")], "an institution gets no marker, and a city is never its parent organization")
    # A city's own list of holdings proves the tier, with its unit, cited to the list.
    listed = {**base, "answer": answer(verdict="unstated", level="none", owners=())}
    seed = {"source": "https://city.example/holdings", "level": "municipal", "unit": "Q900050"}
    proof = rules.proven({"seed": seed, "entity": {}}, country.Spec(cc="xx"))
    expect(proof == rules.MUNICIPAL_LIST and rules.gate(listed["answer"], MESSAGE, tiers, proof, "Q900050") is None
           and rules.gate(listed["answer"], MESSAGE, ("national", "regional"), proof, "Q900050") == "control:unstated",
           "a city's holdings list proves the municipal tier, only where it is written")
    rows = rules.control_rows(listed, ent(), None, state, {}, proof=proof, seed=seed)
    expect([(r["property"], r["value"]["id"], r["qualifiers"]["_sources"]) for r in rows]
           == [("P31", rules.MUNICIPAL, [{"reference_url": seed["source"]}]),
               ("P127", "Q900050", [{"reference_url": seed["source"]}])],
           "a listed municipal enterprise is marked and owned by its unit, both cited to the list")
    # A city-state's company is regional; a city's is not.
    citystate = rules.city_state(muni, None, frozenset({"Q900050"}))
    expect(citystate["answer"]["control"]["level"] == "regional" and muni["answer"]["control"]["level"] == "municipal",
           "a company a city-state controls is at the regional tier")
    expect(rules.city_state(muni, None, frozenset({"Q900001"})) is muni, "a city's company stays municipal")
    both = {**base, "offered": ["Q900050", "Q900001"], "answer": answer(level="municipal", owners=((0, "owner"), (1, "owner")))}
    expect(rules.city_state(both, None, frozenset({"Q900001"}), units) is both,
           "a company a city leads with a region beside it stays the city's")
    # Where the tier is written, a municipal body marked a state enterprise is
    # written on, not corrected: the municipal marker goes beside the other.
    marked = {"claims": {"P31": [claim("P31", "Q270791", "Q1$A")]}}
    rows = rules.control_rows(muni, marked, None, state, {"Q270791": {"Q270791"}}, polities=units)
    expect(rules.correction(muni, marked, {"Q270791": {"Q270791"}}, tiers)[0] is None
           and rows[0]["value"]["id"] == rules.MUNICIPAL and rows[0]["_rule"] is None,
           "where the tier is written, a body marked Q270791 gains Q1780371 beside it")
    mmarked = {"claims": {"P31": [claim("P31", rules.MUNICIPAL, "Q1$D")]}}
    expect(rules.control_rows(muni, mmarked, None, state, {rules.MUNICIPAL: {rules.MUNICIPAL}},
                              polities=units)[0]["_rule"] == "marked",
           "a body already marked municipal gets no second marker")
    nat = {**base, "answer": answer()}
    expect(rules.control_rows(nat, mmarked, None, state, {rules.MUNICIPAL: {rules.MUNICIPAL}})[0]["_rule"] == "marked",
           "a body marked municipal is not also marked a state enterprise")
    # The sector lane: located bodies pass the organisation test like the owned
    # lane's; its classes are companies, never sites.
    src = Path(load.__file__).read_text()
    by_type = src.split('bodies = {q for q in lanes if q in orgs or lanes[q] & {', 1)[1].split("}", 1)[0]
    expect("sector" not in by_type and "municipal_category" not in by_type and "municipal_typed" in by_type,
           "a sector or category candidate must be an organisation; a municipal company is one by type")
    expect(not load.MUNICIPAL_CLASSES & {"Q55488", "Q41176", "Q10373565", "Q863915", "Q1154710", "Q16917"},
           "no station, building, waterworks, port, venue or hospital is a municipal-sector class")
    expect(load.located(frozenset(), load.MUNICIPAL_CLASSES) == set(), "no units, no sector candidates")
    expect(set(load.MUNICIPAL_LANES) <= set(load.LANES), "the municipal lanes are reported")
    # The prompt calls inter-municipal and joint control control; the re-ask picks the answers it changes.
    prompt = decide.PROMPT_PATH.read_text()
    expect("several municipalities together" in prompt and "inter-municipal association" in prompt,
           "the prompt names inter-municipal and joint municipal control")
    expect("municipal_uncontrolled" in reask.classes(answer(verdict="unclear", level="municipal")),
           "a municipal body the old answer left uncontrolled is asked again")
    expect(not reask.classes(answer(level="municipal")), "a municipal body already controlled is not")
    a = actors.Actors(state="Q900000", kinds={"Q900000": "state", "Q900001": "subdivision", "Q900050": "municipal"})
    expect(a.units() == {"Q900050"}, "the municipal actors are the units")
    expect("Q900050" not in actors.offered(a, ent(), None) and "Q900050" in actors.offered(a, ent(P127=["Q900050"]), None),
           "a unit is offered only from the item's own links, never as one of the polities")


def historic() -> None:
    def state(types: list[str], end: str | None = None) -> dict:
        e = ent(P31=types)
        if end:
            e["claims"]["P576"] = [{"rank": "normal", "mainsnak": {"datavalue": {"value": {"time": end, "precision": 9}}}}]
        return e
    expect(eras.historical(state(["Q3024240"], "+1945-05-08T00:00:00Z")), "a predecessor state that ended before 1991 is historical")
    expect(not eras.historical(state(["Q3024240"])), "a historical type with no end date counts as current")
    expect(not eras.historical(state(["Q3024240"], "+2011-01-01T00:00:00Z")), "an end after the cutoff counts as current")
    expect(not eras.historical(state(["Q6256"], "+1945-05-08T00:00:00Z")), "an end date alone, without the type, is not enough")


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
    policy()
    unowned()
    listed()
    parties()
    international()
    municipal()
    historic()
    reach()
    filters()


if __name__ == "__main__":
    main()
