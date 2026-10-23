"""Pin the load-time filter: one case per drop reason, and the kinds that survive.

    .venv/bin/python -m peploop.tree.check_filter
"""

from peploop.checks import ent, expect
from peploop.tree.check_fixture import XX
from peploop.tree.load import classify


def drop(e: dict, p31_types: set[str] = frozenset(), lanes: tuple = ("descent",), types: set[str] = frozenset(),
         by: dict | None = None, generic: dict | None = None, holders: int | None = None, bodies: dict | None = None,
         territorial: set[str] | None = None, cities: list | None = None, inside: set[str] | None = None) -> tuple:
    return classify(XX, "Q1", e, list(lanes), set(types), set(p31_types), by or {}, generic, holders=holders,
                    bodies=bodies, territorial=territorial, cities=cities, inside=inside)


def main() -> None:
    # Another country's office comes in through its holders' citizenship; its own scope says whose it is.
    ours = {"Q900001", "Q900002", "Q900003", "Q900020"}  # the state, its predecessor and federation, a region
    abroad = ent({"en": "Mayor of Zendaburg"}, P31=["Q4164871"], P17=["Q900099"], P1001=["Q900098"])
    expect(drop(abroad, inside=ours)[0] == "scoped_elsewhere", "an office scoped only to another state is dropped")
    expect(drop(abroad)[0] is None, "without an inside set nothing is dropped as scoped elsewhere")
    expect(drop(ent({"en": "Minister of the Grand Federation"}, P31=["Q4164871"], P17=["Q900003"]), inside=ours)[0]
           is None, "a federation's office is the country's predecessor, not another state's")
    expect(drop(ent({"en": "Governor of Strelsau Region"}, P31=["Q4164871"], P1001=["Q900020"]), inside=ours)[0]
           is None, "an office scoped to one of the country's places stays")
    expect(drop(ent({"en": "Chief Rabbi"}, P31=["Q4164871"]), inside=ours)[0] is None,
           "an unscoped office still loads by its holders")
    post = ent({"en": "Ambassador of Ruritania to Turkey"}, P31=["Q4164871"], P17=["Q43"])
    expect(drop(post, lanes=("outbound",), inside=ours) == (None, "", "ambassador"),
           "an outbound post names the receiving state and stays")
    king = ent({"en": "King of Ruritania"}, P31=["Q355567"], P279=["Q116"], P17=["Q900001"])
    expect(drop(king, {"Q355567", "Q4189293"}, types={"Q116", "Q48352"})[0] is None,
           "a throne typed noble title (→ rank) is kept when its class reaches head of state")
    chancellor = ent({"en": "Chancellor of Ruritania", "xa": "Stadtkanzler"}, P31=["Q4164871"], P1001=["Q900001", "Q900077"])
    expect(drop(chancellor, territorial={"Q900001", "Q900077"})[2] == "national",
           "an office scoped to the state itself is national, whatever else its P1001 or label names")
    see = ent({"en": "Roman Catholic Archbishop of Strelsau"}, P31=["Q138024519"], P17=["Q900001"])
    expect(drop(see, {"Q138024519", "Q21114371", "Q3320743"}, types={"Q138024519", "Q21114371", "Q3320743"})[0]
           is None, "a bishop's see is kept though its class reaches title of honor (through 'style')")
    opposition = ent({"en": "Leader of the Opposition"}, P31=["Q4164871", "Q1193702"], P17=["Q900001"])
    expect(drop(opposition, {"Q1193702", "Q1190554"})[0] is None,
           "an item declared a position is no event, whatever else its P31 reaches")
    expect(drop(ent({"en": "Baron of Ruritania"}, P31=["Q355567"], P17=["Q900001"]), {"Q355567", "Q4189293"})[0]
           == "non_office", "a noble title that heads nothing is still a rank")
    potus = ent({"en": "President of the Republic of Ruritania"}, P31=["Q248577"], P17=["Q900001"])
    expect(drop(potus, {"Q248577", "Q43229"}, types={"Q248577", "Q43229", "Q48352"})[0] is None,
           "a presidency typed by a title class that reaches organization is still an office")
    vp = ent({"en": "Vice President of Ruritania"}, P31=["Q294414", "Q80096233"], P17=["Q900001"])
    expect(drop(vp, {"Q80096233", "Q47461344"})[0] is None,
           "a declared public office with a stray list type is still an office")
    expect(drop(ent({"en": "Constitution of Ruritania"}, P31=["Q7755"], P17=["Q900001"]), {"Q7755", "Q47461344"})[0]
           == "non_office", "a written work that declares no office still drops")
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
    expect(drop(ent({"en": "oldest living person in Ruritania"}, P31=["Q4164871"], P279=["Q5"]))[0] == "non_office",
           "a subclass of human is not an office")
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
    mission = ent({"en": "Permanent Representative of Ruritania to UNESCO"}, P31=["Q4164871"], P17=["Q900001"])
    expect(drop(mission, lanes=("orphan",), by={"Q900001": 3})[2] == "ambassador",
           "a mission to an organisation with the state's own P17 is its post abroad, not an inbound one")
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
    expect(drop(ent({"en": "x"}, P31=["Q294414"], P17=["Q900001", "Q900003"]))[2] == "national",
           "an office scoped to the state and the federation is the state's")
    raion = ent({"en": "chairman of the Zenda District Executive Committee"}, P17=["Q900001"])
    expect(drop(raion)[2] == "subnational", "a district office is subnational by its label's level word")
    fixes()


def fixes() -> None:
    """The defects the first country runs found, one case each."""
    from peploop.tree.check_fixture import CITY_PLACES

    # Consular posts of another state are inbound, like its ambassadors.
    cg = ent({"en": "Consul General of Turkey in Strelsau"}, P31=["Q4164871"], P17=["Q900001"])
    expect(drop(cg, by={"Q43": 5})[0] == "inbound_consul", "a foreign consul general in the state is dropped")
    hon = ent({"en": "honorary consul to Ruritania"}, P31=["Q4164871"], P279=["Q107427486"], P17=["Q900001"])
    expect(drop(hon, types={"Q107427486"})[0] == "inbound_consul", "an honorary consul to the state is dropped")
    own = ent({"en": "Consul General of Ruritania in Istanbul"}, P31=["Q4164871"])
    expect(drop(own, by={"Q900001": 4})[:3] == (None, "", "ambassador"), "the state's own consul abroad is its post")
    # Offices of private bodies.
    club = {"Q800": {"types": ["Q800", "Q988108", "Q43229"], "owners": []}}
    yacht = ent({"xa": "presidente del Strelsau Yacht Club"}, P31=["Q4164871"], P2389=["Q800"])
    expect(drop(yacht, by={"Q900001": 3}, bodies=club)[0] == "private_body", "a club's president is a private office")
    party = {"Q801": {"types": ["Q801", "Q7278", "Q163740", "Q43229"], "owners": []}}
    leader = ent({"en": "Chairman of the Ruritanian Patriotic Party"}, P31=["Q4164871"], P361=["Q801"])
    expect(drop(leader, bodies=party)[0] is None, "a party is not a private body, whatever else it is")
    soe = {"Q802": {"types": ["Q802", "Q783794", "Q43229"], "owners": ["Q900001"]}}
    expect(drop(ent({"en": "CEO of Ruritanian Rail"}, P31=["Q4164871"], P2389=["Q802"]), bodies=soe)[0] is None,
           "a company the state owns is not private")
    academy = {"Q804": {"types": ["Q804", "Q414147", "Q955824", "Q48204", "Q988108", "Q79913"], "owners": []}}
    expect(drop(ent({"en": "President of the Academy of Sciences of Ruritania"}, P31=["Q4164871"], P2389=["Q804"]),
                bodies=academy)[0] is None, "an academy of sciences is not a club, whatever its class chain says")
    bank = {"Q803": {"types": ["Q803", "Q891723", "Q783794", "Q43229"], "owners": []}}
    expect(drop(ent({"en": "Managing Director of the Export Bank"}, P31=["Q4164871"], P2389=["Q803"]), bodies=bank)[0]
           is None, "a company that does not say who owns it is not judged private")
    # Bodies typed as offices.
    office = ent({"en": "Office of the President of Ruritania"})
    expect(drop(office, by={"Q900001": 1})[0] == "body", "an 'Office of …' is a body, typed or not")
    staff = ent({"en": "Staff of the President of Ruritania"}, P31=["Q4164871"])
    expect(drop(staff, by={"Q900001": 5})[0] == "body", "the president's staff is a body even with holders")
    expect(drop(ent({"en": "Chief of Staff of the President"}, P31=["Q4164871"]))[0] is None,
           "a chief of staff is a seat")
    # Things that are not offices.
    period = ent({"en": "Dictatorship of General Zenda"}, P31=["Q11514315"], P17=["Q900002"])
    expect(drop(period, {"Q11514315", "Q186081"}, lanes=("predecessor",))[0] == "non_office", "a historical period")
    coup = ent({"en": "Coup d'état in Ruritania in 1934"}, P31=["Q45382"], P17=["Q900002"])
    expect(drop(coup, {"Q45382", "Q1190554"}, lanes=("predecessor",))[0] == "non_office", "a coup")
    mufti = ent({"en": "Grand Mufti of Ruritania"}, P31=["Q900090"], P17=["Q900001"])
    expect(classify(XX, "Q1", mufti, ["descent"], set(), {"Q900090", "Q12737077", "Q1190554"}, {}, None, holders=5,
                        event_types={"Q900090", "Q12737077"})[0] is None,
           "an office whose class reaches 'occurrence' only through 'occupation' is still an office")
    craft = ent({"en": "Strelsau inlay"}, P31=["Q877729"], P17=["Q900001"])
    expect(drop(craft, {"Q877729", "Q1190554", "Q4164871"})[0] == "non_office",
           "a handicraft, even one whose class reaches 'position'")
    crash = ent({"en": "Grand Federation Airlines Flight 9"}, P31=["Q744913"], P17=["Q900003"])
    expect(drop(crash, {"Q744913"}, lanes=("predecessor",), holders=0)[0] == "non_office",
           "a predecessor-scoped item held by no one and typed no position")
    held = ent({"en": "Chamberlain of the RPR"}, P17=["Q900002"])
    expect(drop(held, lanes=("predecessor",), holders=2, by={"Q900003": 2})[0] is None,
           "a predecessor-scoped item someone held stays")
    # Never a generic class when the label names the state or a predecessor.
    speaker = ent({"xa": "speaker of the House of Representatives of Ruritania"}, P31=["Q4164871"])
    expect(drop(speaker, lanes=("orphan",), by={"Q900001": 1, "Q43": 1, "Q159": 1})[0] is None,
           "an unscoped office held by three citizenships that names the state is not generic")
    # Kinds.
    irgc = ent({"en": "Commander of the Ruritanian Guard"}, P31=["Q4164871"], P1001=["Q900070"])
    expect(drop(irgc, territorial=set())[2] == "national", "a P1001 naming a body does not make an office subnational")
    expect(drop(ent({"en": "Mayor of Zendaborg"}, P31=["Q4164871"], P17=["Q900001"]))[2] == "subnational",
           "a mayor is subnational")
    akim = ent({"en": "chief of Zendaborg"}, P31=["Q4164871"], P17=["Q900001"])
    expect(drop(akim, cities=CITY_PLACES)[2] == "subnational", "an office naming one of the state's cities is subnational")
    guard = ent({"en": "Commander of the Faith Guard"}, P31=["Q4164871"], P1001=["Q900001"])
    expect(drop(guard, cities=CITY_PLACES)[2] == "national",
           "an alias keeps its type word: 'Faith City' does not name the 'Faith Guard'")


if __name__ == "__main__":
    main()
