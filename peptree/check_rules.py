"""Pin the rule table and the channels it reads, offline.

    .venv/bin/python -m peptree.check_rules
"""

from peptree import rules, signals
from peptree.check_filter import ent, expect
from peptree.check_fixture import PLACES, XX


def item(qid: str, kind: str, e: dict, holders: int = 0, by: dict | None = None) -> dict:
    return {"qid": qid, "kind": kind, "entity": e, "holders": holders, "holder_countries": by or {},
            "lastrevid": 1}


DISTRICTS = [
    item("Q10", "subnational", ent({"xa": "chairman of the Lindau District Council"}, P279=["Q900060"], P31=["Q294414"])),
    item("Q11", "subnational", ent({"xa": "chairman of the Zenda District Council"}, P279=["Q900060"], P31=["Q294414"])),
    item("Q12", "subnational", ent({"xa": "chairman of the Karelia District Council"}, P17=["Q900001"])),
]
SIB = signals.siblings(DISTRICTS, PLACES, XX.official)


def facts(it: dict, detected: set[str] | None = None) -> signals.Facts:
    return signals.Facts(item=it, country=XX, places=PLACES, sib=SIB, detected=detected or set(),
                         cat_classes={"prosecutor_general": {"Q3368517"}}, value_types={"Q3368517": {"Q3368517"}})


def slot(it: dict, prop: str, cands: list[str], choice: int | None, conf: str = "high", quote: str = "",
         live_rev: int = 1, live: dict | None = None, detected: set[str] | None = None) -> rules.Slot:
    message = "## Labels\n" + "\n".join(o["value"] for o in it["entity"]["labels"].values())
    return rules.Slot(qid=it["qid"], prop=prop, gap="missing", candidates=cands,
                      answer={"choice": choice, "confidence": conf, "quote": quote},
                      message=message, facts=facts(it, detected), load_rev=1, live_rev=live_rev,
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
    expect(rules.decide(slot(raion, "P1001", ["Q900001", "R1"], 1, quote=quote, live_rev=2)) == ("skip", "revision_moved"),
           "an item edited since load is not touched")
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
    nat_quote = "Minister of Culture of the Republic of Ruritania"
    expect(rules.decide(slot(nat, "P31", ["Q294414", "Q4164871"], 0, quote=nat_quote)) == ("skip", "p31_weak_channel"),
           "a P31 backed only by state_office is skipped")
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


if __name__ == "__main__":
    main()
