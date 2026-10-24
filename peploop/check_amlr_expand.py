"""Fail when the AMLR expansion would accept a wrong item, or refuse a clear one.

Each refusal class seen on real rows is a case here: a namesake shown beside
the pick, an item of another state, a building, a ministry matched for the
enterprise it owns. The rules run on fabricated items and answers: no
network, no database, no model. Run it as `python -m peploop.check_amlr_expand`
from the repository root.
"""

import sys

from peploop import amlr, amlr_expand as ax, offices, positions
from peploop.amlr_expand import Candidate, ClassAnswer, Match, admit, class_entry, fixes, row_names, settle
from peploop.checks import ent, expect

STATE = "Q1"
ORG = {"Q43229"}
OFFICE = {"Q4164871"}


def row(kind: str, position: str, **extra: object) -> dict:
    return {"row": 1, "kind": kind, "position": position, "amlr": extra.pop("amlr", "vii_soe"),
            "checked": extra.pop("checked", False), "expansion": [], **extra}


def match(pick: int | None, kind: str = "body", verdict: str = "supported", confidence: str = "high",
          category: str = "vii_soe") -> Match:
    return Match(kind=kind, amlr=category, pick=pick, verdict=verdict, confidence=confidence, reason="")


def cand(qid: str, label: str, ministry: bool = False, placed: bool = True) -> Candidate:
    return Candidate(qid=qid, label=label, lines=[f"{qid}: {label}"], ministry=ministry,
                     words=frozenset(offices.label_key(label).split()), placed=placed)


def check_admit() -> None:
    current = {STATE}
    names = ["Ruritania"]

    def body(e: dict, closure: set, io: bool = False) -> str | None:
        return admit("body", e, closure, current, {}, io, names)

    def office(e: dict, closure: set, scopes: dict | None = None, io: bool = False) -> str | None:
        return admit("position", e, closure, current, scopes or {}, io, names)

    expect(body(ent({"en": "Ruritanian Rail"}, P31=["Q4830453"], P17=[STATE]), ORG) is None,
           "an enterprise of the state is shown")
    expect(body(ent({"en": "Ruritanian Rail"}, P31=["Q4830453"], P17=["Q2"]), ORG) == "other_country",
           "a namesake enterprise of another state is refused")
    expect(body(ent({"en": "Bank building"}, P31=["Q41176"], P17=[STATE]), {"Q41176", "Q811979"}) == "not_organisation",
           "a building is refused: it is no organisation")
    expect(body(ent({"en": "Jan Novak"}, P31=["Q5"]), ORG) == "person", "a person is refused")
    expect(body(ent({"en": "Town"}, P31=["Q15284"], P17=[STATE]), ORG | {"Q56061"}) == "place",
           "a municipality is a place, not a body")
    expect(body(ent({"en": "Chair of the board"}, P31=["Q4164871"], P17=[STATE]), ORG | OFFICE) == "office",
           "an office typed as an organisation too is refused as a body")
    expect(body(ent({"en": "UN agency"}, P31=["Q4830453"], P17=["Q2"]), ORG, io=True) is None,
           "an international organisation's body is not held to the state")
    expect(body(ent({"en": "Old Rail"}, P31=["Q4830453"]), ORG) is None,
           "a body that states no country is left to the model")
    expect(office(ent({"en": "Minister of Finance of Ruritania"}, P31=["Q4164871"], P17=[STATE]), OFFICE) is None,
           "an office of the state is shown")
    expect(office(ent({"en": "Mayor of Upton"}, P31=["Q4164871"], P1001=["Q9"]), OFFICE, {"Q9": [STATE]}) is None,
           "an office scoped to one of the state's units is the state's")
    expect(office(ent({"en": "Mayor of Upton"}, P31=["Q4164871"], P1001=["Q9"]), OFFICE, {"Q9": ["Q2"]})
           == "other_country", "an office scoped to another state's unit is refused")
    expect(office(ent({"en": "justitieråd"}, P31=["Q4164871"], P17=[STATE, "Q2"]), OFFICE) == "several_states",
           "an office several states share is none of theirs")
    pm = ent({"en": "Prime Minister of Ruritania"}, P31=["Q4164871"], P17=[STATE])
    pm["claims"]["P17"].append({"rank": "normal", "mainsnak": {"datavalue": {"value": {"id": "Q2"}}},
                                "qualifiers": {"P582": [{"datavalue": {"value": {"time": "+1992-12-31T00:00:00Z"}}}]}})
    expect(office(pm, OFFICE) is None, "a predecessor state's ended country is no second state")
    expect(office(ent({"en": "Minister of Finance"}, P31=["Q4164871"]), OFFICE) == "stateless",
           "an office that states no country and does not name the state is refused")
    expect(office(ent({"en": "Speaker of the Ruritania parliament"}, P31=["Q4164871"]), OFFICE) is None,
           "an office that names the state is shown though it states no country")
    expect(office(ent({"en": "Secretary General of OPEC"}, P31=["Q4164871"]), OFFICE, io=True) is None,
           "an international organisation's office needs no state")
    expect(office(ent({"en": "ambassador of Ruritania"}, P31=["Q29918328", "Q4164871"], P279=["Q29645880"],
                      P17=[STATE]), OFFICE) == "class_of_offices",
           "a class of ambassadors is every embassy's head, not one office")
    expect(office(ent({"en": "Deputy Minister (Ruritania)"}, P31=["Q136649946"], P17=[STATE]), OFFICE)
           == "class_of_offices", "a type of position is no office")
    expect(office(ent({"en": "Ruritanian Rail"}, P31=["Q4830453"], P17=[STATE]), ORG) == "not_position",
           "a body is not an office")
    e = ent({"en": "minister"}, P31=["Q4164871"])
    e["id"] = "Q83307"
    expect(office(e, OFFICE) == "generic", "a generic class of office is refused")
    ended = ent({"en": "Ruritanian Rail"}, P31=["Q4830453"], P17=[STATE])
    ended["claims"]["P576"] = [{"rank": "normal", "mainsnak": {"datavalue": {"value": {"time": "+2001-01-01T00:00:00Z"}}}}]
    expect(body(ended, ORG) == "dissolved", "a dissolved body is refused")


def check_settle() -> None:
    bank = row("body", "Board of Directors", organisation="Central Bank of Ruritania", amlr="v_audit_cb")
    entry, why = settle(bank, [cand("Q10", "Central Bank of Ruritania"), cand("Q11", "Bank of Ruritania")], match(0))
    expect(entry == {"body": "Q10", "by": "model"} and why == "matched", "a single clear match is accepted")
    entry, why = settle(bank, [cand("Q10", "Central Bank of Ruritania"), cand("Q12", "Central Bank of Ruritania")],
                        match(0))
    expect(entry is None and why == "homonym", "a pick with a namesake shown beside it is refused")
    entry, _ = settle(bank, [cand("Q13", "central bank", placed=False), cand("Q10", "Central Bank")], match(1))
    expect(entry == {"body": "Q10", "by": "model"}, "a namesake that states no country (a class) is no rival")
    entry, why = settle(bank, [cand("Q13", "central bank"), cand("Q10", "Central Bank", placed=False)], match(1))
    expect(entry is None and why == "homonym", "a pick that states no country beside a placed namesake is refused")
    entry, why = settle(bank, [cand("Q10", "Central Bank of Ruritania")], match(0, confidence="low"))
    expect(entry is None and why == "no_match", "a pick at low confidence is refused")
    entry, why = settle(bank, [cand("Q10", "Central Bank of Ruritania")], match(0, verdict="wrong-item"))
    expect(entry is None and why == "no_match", "a pick the model calls the wrong item is refused")
    entry, why = settle(bank, [cand("Q10", "Central Bank of Ruritania")], match(3))
    expect(entry is None and why == "off_list", "a pick off the list is refused")
    factory = row("body", "Member of the Management Board",
                  organisation="Gunpowder Factory Company (Societatea Fabrica de Pulberi S.A.) Făgăraș (MEEMA)")
    entry, why = settle(factory, [cand("Q20", "Ministry of Economy", ministry=True)], match(0))
    expect(entry is None and why == "parent_ministry", "a ministry matched for the enterprise it owns is refused")
    ministry = row("body", "Secretary-General", organisation="Ministry of Economy", amlr="i_executive")
    entry, _ = settle(ministry, [cand("Q20", "Ministry of Economy", ministry=True)], match(0, category="i_executive"))
    expect(entry == {"body": "Q20", "by": "model"}, "a ministry the row names is accepted")
    minister = row("position", "Federal ministers", amlr="i_executive")
    entry, why = settle(minister, [cand("Q30", "Minister of Finance")], match(None, kind="body_class"))
    expect(entry is None and why == "kind_differs", "a row naming several offices expands to none of them")
    unhcr = [cand("Q50", "United Nations High Commissioner for Refugees")]
    head = row("position", "High Commissioner, United Nations High Commissioner for Refugees (UNHCR)", amlr="ix_io")
    entry, _ = settle(head, unhcr, match(0, kind="position", category="ix_io"))
    expect(entry == {"position": "Q50", "by": "model"}, "an organisation's head office the row names is accepted")
    local = row("position", "Head of office of the United Nations High Commissioner for Refugees, UNHCR Prague",
                amlr="ix_io")
    entry, why = settle(local, unhcr, match(0, kind="position", category="ix_io"))
    expect(entry is None and why == "io_title", "the head of an organisation's local office is not its head")
    lesser = row("position", "Secretary for Ibero-American Cooperation, SGI Ibero-American General Secretariat",
                 amlr="ix_io")
    entry, why = settle(lesser, [cand("Q51", "Ibero-American Secretary-General")],
                        match(0, kind="position", category="ix_io"))
    expect(entry is None and why == "io_title", "a lesser secretary is not the secretary-general")
    reviewed = row("body", "Board", organisation="Ruritanian Rail", checked=True)
    entry, _ = settle(reviewed, [cand("Q40", "Ruritanian Rail")], match(0, kind="position"))
    expect(entry == {"body": "Q40", "by": "model"}, "a reviewed row's kind stands over the model's reading")
    expect(fixes(minister, "body_class", "i_executive", "high") == {"kind": "body_class"},
           "a sure reading corrects an unreviewed row's kind")
    expect(fixes(minister, "body_class", "i_executive", "medium") == {}, "an unsure reading corrects nothing")
    expect(fixes(reviewed, "position", "agency", "high") == {}, "a reviewed row is never corrected")


def check_classes() -> None:
    mayors = row("body_class", "Mayors of municipalities over 50 000 inhabitants", amlr="viii_local")

    def answer(target: str, level: str | None = None, tier: str | None = None, bodies: str | None = None,
               confidence: str = "high", kind: str = "body_class") -> ClassAnswer:
        return ClassAnswer(kind=kind, amlr="viii_local", target=target, level=level, tier=tier, bodies=bodies,
                           confidence=confidence, reason="")

    entry, _ = class_entry(mayors, {"municipal", "grouping"}, answer("level", level="municipal"))
    expect(entry == {"level": "municipal", "office": "head", "by": "model"},
           "a body class of mayors becomes the municipal level's head office")
    entry, why = class_entry(mayors, {"municipal"}, answer("level", level="grouping"))
    expect(entry is None and why == "no_such_level", "a level the state's file lists no units for gives no rule")
    entry, why = class_entry(mayors, {"municipal"}, answer("level", level="municipal", confidence="low"))
    expect(entry is None and why == "low_confidence", "a low-confidence reading gives no rule")
    boards = row("body_class", "Members of the boards of state-owned enterprises")
    entry, _ = class_entry(boards, set(), answer("tier", tier="national", bodies="enterprise"))
    expect(entry == {"tier": "national", "bodies": "enterprise", "by": "model"},
           "a body class of state enterprises becomes pepcorp's national enterprise tier")
    entry, why = class_entry(boards, set(), answer("none"))
    expect(entry is None and why == "no_rule", "a party or court class gives no rule")


def check_shapes() -> None:
    ok = [{"position": "Q1"}, {"body": "Q2", "by": "model"}, {"level": "municipal", "office": "head", "by": "hand"},
          {"tier": "regional", "bodies": "institution"}]
    bad = [{"position": "Q1", "by": "guess"}, {"level": "region", "office": "head"}, {"level": "municipal", "office": "council"},
           {"tier": "national", "bodies": "party"}, {"body": "Q2", "position": "Q1"}, {"position": "X1"}]
    expect(all(amlr.entry_ok(e) for e in ok), "every shape of entry, with and without `by`, is valid")
    expect(not any(amlr.entry_ok(e) for e in bad), "an unknown provenance, level, office, tier or mixed shape is not")


def check_names() -> None:
    names = row_names(row("body", "Member", organisation="National Air Transport Company (Compania Naţională de"
                          " Transporturi Aeriene Române ‘TAROM’) S.A. (MTIC)", lang="RUM"))
    texts = [n for n, _ in names]
    expect(texts[0].startswith("Compania Națională") and names[0][1], "the local name in parentheses comes first, in commas")
    expect("MTIC" not in " ".join(texts), "a bare acronym (a ministry's, often) is no name")
    names = row_names(row("body", "members of the Board of Directors of the Central Bank of Ruritania"))
    expect(names[0] == ("Central Bank of Ruritania", False), "a body named after a role phrase is searched by itself")
    expect(ax.query_words("President of the Republic", frozenset({"republic", "ruritania"})) == "President",
           "a query within the state's items drops the state's name")


def main() -> int:
    saved = positions.is_generic
    positions.is_generic = lambda qid: qid == "Q83307"  # type: ignore[assignment]
    try:
        check_admit()
    finally:
        positions.is_generic = saved  # type: ignore[assignment]
    check_settle()
    check_classes()
    check_shapes()
    check_names()
    return 0


if __name__ == "__main__":
    sys.exit(main())
