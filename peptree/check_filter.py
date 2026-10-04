"""Pin the load-time filter: one case per drop reason, and the kinds that survive.

    .venv/bin/python -m peptree.check_filter
"""

from peptree.check_fixture import XX
from peptree.load import classify


def ent(labels: dict[str, str], **claims: list[str]) -> dict:
    return {"labels": {lg: {"value": v} for lg, v in labels.items()},
            "claims": {p: [{"rank": "normal", "mainsnak": {"datavalue": {"value": {"id": q}}}} for q in qs]
                       for p, qs in claims.items()}}


def expect(cond: bool, what: str) -> None:
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        raise SystemExit(1)


def drop(e: dict, p31_types: set[str] = frozenset(), lanes: tuple = ("descent",), types: set[str] = frozenset(),
         by: dict | None = None, generic: dict | None = None) -> tuple:
    return classify(XX, "Q1", e, list(lanes), set(types), set(p31_types), by or {}, generic)


def main() -> None:
    expect(drop(ent({"en": "Hero of Ruritania"}, P31=["Q3320743"], P17=["Q900001"]), {"Q3320743"})[0] == "non_office",
           "a title of honour is dropped as non_office")
    expect(drop(ent({"en": "list of ministers"}, P31=["Q4164871"], P279=["Q13406463"]))[0] == "non_office",
           "a list article is dropped")
    expect(drop(ent({"en": "member of parliament"}, P31=["Q4164871", "Q136649946"]), lanes=("orphan",))[0]
           == "generic_class", "a direct P31 type-of-position is a generic class")
    unscoped = ent({"en": "first deputy"}, P31=["Q4164871"])
    expect(drop(unscoped, lanes=("orphan",), by={"Q900001": 2, "Q900003": 2, "Q159": 1, "Q212": 1})[0]
           == "generic_class", "unscoped and held by citizens of three states (the federation counted as home) is generic")
    expect(drop(unscoped, lanes=("orphan",), by={"Q900001": 2, "Q900003": 2, "Q159": 1})[0] is None,
           "two states after merging the predecessors is not generic")
    mayor = ent({"en": "mayor"}, P31=["Q4164871"], P17=["Q900001"])
    expect(drop(mayor, generic={"Q1": "mayor"})[:2] == ("generic_class", "listed in generic_positions.csv (mayor)"),
           "an item listed in generic_positions.csv is a generic class")
    expect(drop(mayor, generic={"Q2": "president"})[0] is None, "an item not listed there is not")
    body = ent({"en": "General Staff of Ruritania"}, P31=["Q495430", "Q4164871"], P17=["Q900001"])
    expect(drop(body, {"Q495430", "Q43229"})[0] == "body", "a general staff typed as a position is a body")
    # Declared-type leaks, read from p:P31/ps:P31 at any rank.
    expect(drop(ent({"en": "bodyguard"}, P31=["Q28640"]))[0] == "occupation", "a profession is an occupation")
    mp_seat = ent({"en": "member of the Ruritanian Diet"}, P31=["Q4164871", "Q486839"], P17=["Q900001"])
    expect(drop(mp_seat, {"Q486839", "Q12737077"})[0] is None,
           "a seat whose class is typed an occupation (member of parliament) is not one")
    council = ent({"xa": "Zenda rural council"}, P31=["Q900030"])
    expect(drop(council, {"Q900030", "Q56061"})[0] == "place", "a rural council (an administrative unit) is a place")
    expect(drop(ent({"en": "Zenda"}, P31=["Q900031"]), {"Q900031", "Q486972"})[0] == "place", "a settlement is a place")
    case = ent({"xa": "Ruritanian branch of the Labour Party"}, P31=["Q16738832"])
    expect(drop(case, {"Q16738832", "Q2334719"})[0] == "legal_case", "a criminal case is a legal case")
    expect(drop(ent({"en": "treason"}, P31=["Q83267"]), {"Q83267"})[0] == "legal_case", "a crime is a legal case")
    expect(drop(ent({"en": "Zenda manor"}, P31=["Q12292478"]), {"Q12292478"})[0] == "estate", "an estate is dropped")
    expect(drop(ent({"en": "flag of the RPR"}, P31=["Q186516"]), {"Q186516", "Q14660"})[0] == "non_office",
           "a flag is not an office")
    deprecated = ent({"en": "Zenda"}, P17=["Q900001"])
    deprecated["claims"]["P31"] = [{"rank": "deprecated", "mainsnak": {"datavalue": {"value": {"id": "Q28640"}}}}]
    expect(drop(deprecated)[0] == "occupation", "a deprecated declared type still counts")
    # Diplomatic posts.
    inbound = ent({"en": "Ambassador of Turkey to Ruritania"}, P31=["Q4164871"], P17=["Q900001"])
    expect(drop(inbound, types={"Q121998"})[0] == "inbound_ambassador", "a foreign ambassador to the state is dropped")
    outbound = ent({"xa": "посол Рурытаніі ў Турцыі"})
    expect(drop(outbound, lanes=("orphan",), by={"Q900001": 6}) == (None, "", "ambassador"),
           "an unclassed post naming the state and a diplomat, held by its citizens, is its own post abroad")
    expect(drop(outbound, lanes=("orphan",), by={"Q43": 6})[2] != "ambassador",
           "the same label held by foreigners is not")
    sender = ent({"en": "ambassador of Ruritania"}, P279=["Q29645880"], P17=["Q900001"])
    expect(drop(sender, types={"Q29645880", "Q121998"})[2] == "ambassador", "the state's sender class is its own post")
    # Kinds.
    minister = ent({"en": "Minister of Internal Affairs of the Republic of Ruritania"}, P31=["Q294414"], P17=["Q900001"])
    expect(drop(minister)[2] == "national", "a minister of the state is national")
    expect(drop(ent({"xa": "minister of health of the RPR"}, P31=["Q294414"]), lanes=("predecessor",))[2]
           == "predecessor", "an office the label puts in the predecessor republic is a predecessor office")
    expect(drop(ent({"en": "minister of health of the RPR"}, P31=["Q294414"], P1001=["Q900001"]))[2] == "national",
           "the state's own P1001 wins over a predecessor's name in the label")
    expect(drop(ent({"en": "x"}, P31=["Q294414"], P17=["Q900003"]))[2] == "predecessor",
           "an office scoped to the federation is a predecessor office")
    raion = ent({"en": "chairman of the Zenda District Executive Committee"}, P17=["Q900001"])
    expect(drop(raion)[2] == "subnational", "a district office is subnational by its label's level word")


if __name__ == "__main__":
    main()
