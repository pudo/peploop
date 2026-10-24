"""Pin pepcorp's rules: the gates, the seat table, name resolution, the dates, and the share's rendering.

    .venv/bin/python -m peploop.corp.check_rules
"""

from datetime import date

from peploop import eras, evidence, qs
from peploop.dates import time_value
from peploop.corp import actors, country, decide, load, rules
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
    expect(rules.gate(answer(level="municipal"), MESSAGE, ("national", "regional", "municipal")) is None,
           "a country that writes the municipal tier passes it")
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
    expect(rules.correction(priv, marked, {"Q270791": {"Q270791"}}, ("national", "regional"))[0] is None,
           "a private body whose article does not date the sale keeps its marker untouched")
    priv["answer"]["control"]["ended"] = "1998-05"
    kind, add, wrong = rules.correction(priv, marked, {"Q270791": {"Q270791"}}, ("national", "regional"))
    expect(kind == "private" and not wrong and [(a["value"]["id"], a["qualifiers"]["P582"]["time"]) for a in add]
           == [("Q270791", "+1998-05-00T00:00:00Z")], "a privatised body's marker is ended, never removed")
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
    historic()
    reach()
    filters()


if __name__ == "__main__":
    main()
