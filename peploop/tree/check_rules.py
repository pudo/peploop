"""Pin the rule table and the channels it reads, offline.

    .venv/bin/python -m peploop.tree.check_rules
"""

from peploop.tree import rules, signals
from peploop.tree.check_filter import ent, expect
from peploop.tree.check_fixture import PLACES, XX


def item(qid: str, kind: str, e: dict, holders: int = 0, by: dict | None = None, rows: list | None = None) -> dict:
    return {"qid": qid, "kind": kind, "entity": e, "holders": holders, "holder_countries": by or {},
            "lastrevid": 1, "holder_rows": rows or []}


def held(n: int, start: int, end: int, cit: str = "Q900001") -> list[dict]:
    """`n` holders, citizens of `cit`, between `start` and `end`."""
    return [{"h": f"Q95{i}", "s": start, "e": end, "b": start - 40, "d": None, "c": [cit]} for i in range(n)]


DISTRICTS = [
    item("Q10", "subnational", ent({"xa": "chairman of the Lindau District Council"}, P279=["Q900060"], P31=["Q294414"])),
    item("Q11", "subnational", ent({"xa": "chairman of the Zenda District Council"}, P279=["Q900060"], P31=["Q294414"])),
    item("Q12", "subnational", ent({"xa": "chairman of the Karelia District Council"}, P17=["Q900001"])),
]
SIB = signals.siblings(DISTRICTS, PLACES, XX.official)


def facts(it: dict, detected: set[str] | None = None, country=XX, bodies: dict | None = None) -> signals.Facts:
    return signals.Facts(item=it, country=country, places=PLACES, sib=SIB, detected=detected or set(),
                         cat_classes={"prosecutor_general": {"Q3368517"}}, value_types={"Q3368517": {"Q3368517"}},
                         bodies=bodies or {}, head_seqs=[["preside"], ["prim", "minis"]])


def slot(it: dict, prop: str, cands: list[str], choice: int | None, conf: str = "high", quote: str = "",
         live_rev: int = 1, live: dict | None = None, detected: set[str] | None = None, country=XX,
         bodies: dict | None = None, message: str | None = None) -> rules.Slot:
    message = message or "## Labels\n" + "\n".join(o["value"] for o in it["entity"]["labels"].values())
    return rules.Slot(qid=it["qid"], prop=prop, gap="missing", candidates=cands,
                      answer={"choice": choice, "confidence": conf, "quote": quote},
                      message=message, facts=facts(it, detected, country, bodies), load_rev=1, live_rev=live_rev,
                      live_entity=live if live is not None else it["entity"])


def main() -> None:
    raion = DISTRICTS[2]
    quote = "chairman of the Karelia District Council"
    expect(signals.convention(SIB, "Q12", "p279") == "Q900060", "siblings agree on a district chairman's class")
    expect(rules.decide(slot(raion, "P279", ["Q30185", "Q900060"], 1, quote=quote)) == ("apply", "two_channels"),
           "model + sibling convention applies a P279")
    expect(rules.decide(slot(raion, "P279", ["Q30185", "Q900060"], 0, quote=quote)) == ("skip", "one_channel"),
           "a P279 no channel supports is skipped")
    expect(rules.decide(slot(raion, "P1001", ["Q900001", "Q900020", "R1"], 2, quote=quote)) == ("apply", "two_channels"),
           "the district the label names applies as P1001")
    expect(rules.decide(slot(raion, "P1001", ["Q900001", "Q900020", "R1"], 0, quote=quote)) == ("skip", "label_conflict"),
           "the state for a district office conflicts with the label")
    expect(rules.decide(slot(raion, "P1001", ["Q900001", "R1"], None, quote=quote)) == ("skip", "declined"), "a decline skips")
    expect(rules.decide(slot(raion, "P1001", ["Q900001", "R1"], 7, quote=quote)) == ("skip", "bad_index"),
           "an index outside the list skips")
    expect(rules.decide(slot(raion, "P1001", ["Q900001", "R1"], 1, conf="low", quote=quote)) == ("skip", "low_confidence"),
           "low confidence skips")
    expect(rules.decide(slot(raion, "P1001", ["Q900001", "R1"], 1, quote="the Karelian chairman")) == ("skip", "no_quote"),
           "a paraphrase is not a quote")
    p17_moved = {**raion["entity"], "claims": {**raion["entity"]["claims"], "P17": [{"mainsnak": {"datavalue": {"value": {"id": "Q9"}}}}]}}
    expect(rules.decide(slot(raion, "P1001", ["Q900001", "R1"], 1, quote=quote, live_rev=2, live=p17_moved))
           == ("skip", "revision_moved"), "an item edited where the slot looks since load is not touched")
    listed = {**raion["entity"], "sitelinks": {"eswiki": {"title": "Anexo:Presidentes del distrito"}}}
    expect(rules.decide(slot(raion, "P31", ["Q294414"], 0, quote=quote, live=listed))[1] == "p31_list_article",
           "a list article's item is not typed an office")
    p31_moved = {**raion["entity"], "claims": {**raion["entity"]["claims"], "P31": [{"mainsnak": {"datavalue": {"value": {"id": "Q9"}}}}]}}
    expect(rules.decide(slot(raion, "P1001", ["Q900001", "Q900020", "R1"], 2, quote=quote, live_rev=2, live=p31_moved))
           == ("apply", "two_channels"), "an edit elsewhere on the item (a landed P31) leaves a P1001 slot standing")
    moved = ent({"xa": quote}, P1001=["R1"])
    expect(rules.decide(slot(raion, "P1001", ["Q900001", "R1"], 1, quote=quote, live=moved)) == ("skip", "present_now"),
           "a property that appeared live is not added")
    pg = item("Q20", "national", ent({"en": "Prosecutor General of the Republic of Ruritania"}, P17=["Q900001"]))
    s = slot(pg, "P279", ["Q3368517"], 0, quote="Prosecutor General of the Republic of Ruritania",
             detected={"prosecutor_general"})
    expect(rules.decide(s) == ("apply", "two_channels"), "a class of the category the name puts it in applies")
    amb = item("Q30", "ambassador", ent({"xa": "посол Рурытаніі ў Турцыі"}), 6, {"Q900001": 6})
    expect(rules.decide(slot(amb, "P17", ["Q43"], 0, quote="посол Рурытаніі ў Турцыі")) == ("apply", "two_channels"),
           "an ambassador's P17 is the receiving state the label names")
    expect(signals.channels("P17", "Q900001", facts(amb)) == ["holders"]
           and signals.conflict("P17", "Q900001", facts(amb)),
           "the sender as an ambassador's P17 conflicts with the label")
    nat = item("Q40", "national", ent({"en": "Minister of Culture of the Republic of Ruritania"}), 4, {"Q900001": 4})
    expect(sorted(signals.channels("P17", "Q900001", facts(nat))) == ["holders", "label"],
           "label and holders agree on P17")
    expect(signals.channels("P31", "Q294414", facts(nat)) == ["state_office"], "a state office is a public office")
    from types import SimpleNamespace
    from peploop.tree import repair
    many = [{"qid": f"Q{i}", "holders": 0} for i in range(repair.LARGE + 1)]
    many[0]["holders"], many[1]["category"] = 2, True
    fake = SimpleNamespace(ctx=SimpleNamespace(detected=lambda it: {"minister"} if it.get("category") else set()))
    expect([it["qid"] for it in repair.focus(fake, many)] == ["Q0", "Q1"],
           "a large place asks only about held or categorised items")
    expect(len(repair.focus(fake, many[:repair.LARGE])) == repair.LARGE, "a place under the gate asks about all")
    unheld = item("Q44", "national", ent({"en": "Minister of Culture of the Republic of Ruritania"}))
    cls = slot(unheld, "P31", ["Q294414", "Q4164871"], 0, quote="Minister of Culture of the Republic of Ruritania")
    cls.facts.classes = {unheld["qid"]}
    expect(rules.decide(cls) == ("skip", "p31_on_a_class"), "a class of office is never typed a public office")
    s = slot(nat, "P17", ["Q900001"], 0, quote="Minister of Culture of the Republic of Ruritania")
    s.facts.non_states = {"Q900001"}
    expect(rules.decide(s) == ("skip", "p17_not_a_state"), "a value not typed a state is never a P17")
    shared = item("Q45", "national", ent({"en": "Justice of the Supreme Court"}, P17=["Q900001", "Q35"]), 4, {"Q900001": 4})
    expect(rules.decide(slot(shared, "P1001", ["Q900001"], 0, quote="Justice of the Supreme Court"))
           == ("skip", "shared_with_another_state"), "an office whose P17 names another state gets no P1001 of ours")
    from dataclasses import replace
    realmed = replace(XX, realm=("Q900050",))
    expect("Q900050" in realmed.p17_values and "Q900050" in realmed.home, "the realm is a home state and a P17 value")
    in_realm = item("Q48", "national", ent({"en": "Justice of the Supreme Court"}, P17=["Q900001", "Q900050"]), 4,
                    {"Q900001": 4})
    expect(rules.decide(slot(in_realm, "P1001", ["Q900001"], 0, quote="Justice of the Supreme Court",
                             country=realmed))[1] != "shared_with_another_state",
           "an office whose P17 names the state's own realm is not shared with another state")
    domestic = item("Q49", "national", ent({"en": "State Auditor"}), 4, {"Q900050": 4})
    expect(rules.decide(slot(domestic, "P17", ["Q900001", "Q900050"], 1, quote="State Auditor", country=realmed))
           == ("skip", "realm_in_p17"), "the realm is never written as P17")
    nat_quote = "Minister of Culture of the Republic of Ruritania"
    meta = ["Q294414", "Q4164871", "Q136649946"]
    expect(rules.decide(slot(nat, "P31", meta[:2], 0, quote=nat_quote)) == ("apply", "two_channels"),
           "an untyped state office takes public office on the state_office channel")
    typed = slot(nat, "P31", meta[:2], 0, quote=nat_quote)
    typed.facts.positioned = {nat["qid"]}
    expect(rules.decide(typed) == ("skip", "p31_typed_elsewhere"),
           "an office whose P31 already reaches position gets no second type")
    expect(rules.decide(slot(nat, "P31", meta[:2], 1, quote=nat_quote)) == ("skip", "p31_weak_channel"),
           "plain position for a state office has no channel and is skipped")
    klass = slot(unheld, "P31", meta, 2, quote=nat_quote)
    klass.facts.classes = {unheld["qid"]}
    expect(rules.decide(klass) == ("skip", "p31_on_a_class"),
           "a class of office is not typed by the repair: no class signal separates it from an office yet")
    seat = item("Q43", "national", ent({"en": "Minister of Culture of the Republic of Ruritania"}), 4, {"Q900001": 4})
    held = slot(seat, "P31", meta[:2], 0, quote=nat_quote)
    held.facts.classes = {seat["qid"]}
    expect(rules.decide(held)[1] != "p31_on_a_class",
           "a subclassed seat people hold directly is an office, not only a class")
    expect(rules.decide(slot(nat, "P31", meta, 2, quote=nat_quote)) == ("skip", "type_of_position_on_an_office"),
           "an office that is no class is never typed a type of position")
    expect(rules.decide(slot(raion, "P31", ["Q294414", "Q4164871"], 0, quote=quote)) == ("apply", "two_channels"),
           "a P31 the siblings agree on still applies")
    party = item("Q41", "national", ent({"en": "Chairman of the Ruritanian Patriotic Party"}))
    expect(signals.channels("P31", "Q294414", facts(party)) == [], "a party office is not a public office")
    pred = item("Q42", "predecessor", ent({"en": "Minister of Health of the RPR"}), 3, {"Q900003": 3})
    expect(signals.expected_label("P17", facts(pred)) == {"Q900003"}
           and signals.expected_label("P1001", facts(pred)) == {"Q900002"},
           "a predecessor republic's office: P17 the federation, P1001 the republic")
    expect(signals.channels("P17", "Q900003", facts(pred)) == ["label", "holders"],
           "holders who are the federation's citizens support the federation as P17")
    eras()


def eras() -> None:
    """The era rule, contemporary holders, shared names, P131, embedded titles, quotes."""
    from dataclasses import replace

    # An office whose holders all served before the state began is not the state's.
    works = item("Q50", "national", ent({"xa": "secretary of Public Works"}, P1001=["Q900001"]), 4, {"Q900001": 4},
                 held(4, 1960, 1975))
    quote = "secretary of Public Works"
    expect(signals.office_span(works) == (1960, 1975), "the office's span comes from its holders' tenures")
    expect(rules.decide(slot(works, "P17", ["Q900001", "Q900003"], 0, quote=quote)) == ("skip", "era_mismatch"),
           "a state that did not exist while the office did is refused")
    expect("holders" not in signals.channels("P17", "Q900001", facts(works)),
           "citizens of the state count for it only when they held the office in its era")
    expect("holders" in signals.channels("P17", "Q900003", facts(item("Q51", "national", ent({"xa": quote}), 4,
                                                                     {"Q900003": 4}, held(4, 1960, 1975, "Q900003")))),
           "contemporary citizens of the federation do count for it")
    across = item("Q52", "national", ent({"en": "Minister of Culture of the Republic of Ruritania"}), 4, {"Q900001": 4},
                  held(2, 1985, 1990) + held(2, 1992, 2000))
    expect(rules.decide(slot(across, "P17", ["Q900001"], 0, quote="Minister of Culture of the Republic of Ruritania"))
           == ("apply", "two_channels"), "an office whose span crosses the transition keeps the current state")
    dated = ent({"en": "Minister of Mines"}, P571=[], P576=[])
    dated["claims"]["P571"] = [{"rank": "normal", "mainsnak": {"datavalue": {"value": {"time": "+1952-00-00T00:00:00Z"}}}}]
    dated["claims"]["P576"] = [{"rank": "normal", "mainsnak": {"datavalue": {"value": {"time": "+1979-00-00T00:00:00Z"}}}}]
    expect(signals.office_span(item("Q53", "national", dated, 2, {}, held(2, 1995, 2000))) == (1952, 1979),
           "P571/P576 win over the holders' dates")
    # A name the state shares with a predecessor names neither, unless the era decides.
    yy = replace(XX, predecessors={**XX.predecessors, "Q900004": "Q900004"},
                 names={**XX.names, "Q900004": ["Republic of Ruritania", "Ruritania"]},
                 local_names={**XX.local_names, "Q900004": ["Republic of Ruritania"]},
                 spans={**XX.spans, "Q900004": [1920, 1950]})
    senate = item("Q54", "national", ent({"en": "President of the Senate of the Republic of Ruritania"},
                                         P2389=["Q810"]), 3, {"Q900001": 3})
    body = {"Q810": {"P17": ["Q900004"], "P1001": []}}
    sq = "President of the Senate of the Republic of Ruritania"
    expect(signals.expected_label("P17", facts(senate, country=yy)) is None,
           "an undated office whose label uses a shared name is ambiguous")
    expect(rules.decide(slot(senate, "P17", ["Q900001", "Q900004"], 1, quote=sq, country=yy, bodies=body))
           == ("apply", "two_channels"), "…so the predecessor is no label conflict, and its body carries it")
    old = {**senate, "holder_rows": held(3, 1930, 1940)}
    expect(signals.expected_label("P17", facts(old, country=yy)) == {"Q900004"},
           "with the holders' dates the era decides the shared name")
    crossing = {**senate, "holder_rows": held(2, 1930, 1940) + held(1, 1995, 2000)}
    expect(signals.expected_label("P17", facts(crossing, country=yy)) == {"Q900001"},
           "an office under a shared name that outlasted the predecessor keeps the current state")
    lives = {**senate, "holder_rows": [{"h": "Q960", "s": None, "e": None, "b": 1900, "d": 1992, "c": ["Q900001"]}]}
    expect(signals.expected_label("P17", facts(lives, country=yy)) is None,
           "…but a holder's long life, with no tenure dates, is no evidence that it did")
    # Where a body sits is not what it governs.
    seated = item("Q55", "subnational", ent({"xa": "chief of the Strelsau Water Board"}, P361=["Q811"]))
    expect("body" not in signals.channels("P1001", "R1", facts(seated, bodies={"Q811": {"P17": [], "P1001": [], "P131": ["R1"]}})),
           "a body's P131 is no evidence for P1001")
    # A state named inside another office's title is not the jurisdiction.
    rector = item("Q56", "national", ent({"xa": "Rector of the Academy under the President of the Republic of Ruritania"}))
    expect("label" not in signals.channels("P1001", "Q900001", facts(rector))
           and "label" in signals.channels("P17", "Q900001", facts(rector)),
           "'… under the President of X' names no jurisdiction, but still the country")
    from peploop.tree import country
    expect(country.named_states(replace(XX, names={**XX.names, "Q900002": ["Ruritan"]}), "Vice President of Ruritania")
           == {"Q900001"}, "a predecessor named 'Ruritan' is not read into 'Ruritania' when the state's name is spelled out")
    vp = item("Q57", "national", ent({"en": "Vice President of the Republic of Ruritania"}))
    expect("label" in signals.channels("P1001", "Q900001", facts(vp)), "a deputy-prefixed head title still leads")
    # A quote the model wrote with JSON escapes or control characters is still verbatim.
    from peploop.tree.check_fixture import CITY_PLACES
    city_facts = facts(item("Q59", "subnational", ent({"en": "Mayor of Zendaborg"})))
    city_facts.places = signals.Places(list(PLACES.places.values()) + CITY_PLACES)
    expect(signals.expected_label("P1001", city_facts) == {"C1"}, "a mayor's label names its city as the jurisdiction")
    union = facts(item("Q60", "subnational", ent({"en": "Chair of the Zendaborg Trade Union"})))
    union.places = city_facts.places
    town = facts(item("Q61", "subnational", ent({"en": "Chair of the Zendaborg Council"})))
    town.places = city_facts.places
    expect(signals.expected_label("P17", town) == {"Q900001"} and signals.expected_label("P17", union) is None,
           "a place puts an office in its state, but not a trade union's or a club's office")
    mayor = item("Q58", "subnational", ent({"en": "Mayor of Zendaborg"}))
    msg = "## Article lead\nThe Äkim (local: әкім) of Zendaborg is the chief authority in the city."
    escaped = "The \\u00c4kim (local: \\u04d9\\u043a\\u0456\\u043c) of Zendaborg\x07 is the chief authority"
    expect(rules.quoted(slot(mayor, "P1001", ["C1"], 0, quote=escaped, message=msg)), "JSON escapes are decoded")


if __name__ == "__main__":
    main()
