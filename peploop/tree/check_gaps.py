"""Pin the gap step: what counts as missing, the ambassador convention, the class fix.

    .venv/bin/python -m peploop.tree.check_gaps
"""

from peploop.tree import country, gaps
from peploop.checks import ent, expect
from peploop.tree.check_fixture import XX
from peploop.tree.check_rules import item

#: Class names as `gaps.class_names` would read them from the category classes.
NAMES = {key: [country.seq(n) for n in names] for key, names in {
    "head_of_state": ["president", "head of state"],
    "prosecutor_general": ["prosecutor general", "public prosecutor general"],
    "minister": ["minister", "deputy minister"],
    "legislator": ["deputy", "member of parliament"],
    "apex_judge": ["supreme court judge"],
}.items()}


def context() -> gaps.Context:
    ctx = object.__new__(gaps.Context)  # no live reads: closures are given
    ctx.cc = "xx"
    ctx.country = XX
    ctx.cats = gaps.categories()
    ctx.by_key = {c["key"]: c for c in ctx.cats}
    ctx.names = NAMES
    ctx.body_types = {"Q900040": {"Q900040", "Q190752"}}  # the Supreme Court of Ruritania: a supreme court
    ctx.types = {}
    return ctx


def main() -> None:
    expect(not country.is_name("to") and not country.is_name("IN") and not country.is_name("РФ")
           and country.is_name("中") and country.is_name("UAE"),
           "a two-letter code is never read as a state's name; a CJK character or a three-letter name is")
    up = {"Q900010": {"Q900010", "Q56061"}, "Q900070": {"Q900070", "Q56061", "Q473972"}, "Q515": {"Q515"}}
    expect(country.dominant({"Q900010": 6, "Q900070": 4}, 10, up) == ["Q900010"],
           "a park is never a level, though the tree files it under administrative units")
    expect(country.dominant({"Q900010": 8, "Q515": 1}, 9, up) == ["Q900010"] and
           country.dominant({"Q515": 1}, 2, up) == [], "one place cannot make its type a level")
    ctx = context()
    amb = item("Q1", "ambassador", ent({"xa": "посол Рурытаніі ў Турцыі"}, P31=["Q294414"], P279=["Q900050"]))
    expect(ctx.gaps(amb, {"Q29645880"}) == [("P17", "missing", None)],
           "an ambassador post misses P17 only: no P1001 is asked")
    # A dependent territory's own offices take it in P1001 and no P17; a predecessor's keep P17.
    from dataclasses import replace
    terr = context()
    terr.country = replace(XX, is_state=False)
    bare = ent({"en": "Speaker of the House of Assembly of Ruritania"}, P31=["Q294414"], P279=["Q83307"])
    expect(terr.gaps(item("Q4", "national", bare), {"Q83307"}) == [("P1001", "missing", None)],
           "a territory's office is asked P1001 and never P17")
    expect(("P17", "missing", None) in terr.gaps(item("Q5", "predecessor", bare), {"Q83307"}),
           "a predecessor's office in a territory is still asked P17")
    expect(("P17", "missing", None) in ctx.gaps(item("Q6", "national", bare), {"Q83307"}),
           "a state's office is asked P17")
    national = ent({"en": "Speaker of the House of Assembly of Ruritania"}, P31=["Q294414"], P279=["Q83307"],
                   P1001=[XX.qid])
    expect(ctx.gaps(item("Q8", "national", national), {"Q83307"}) == [],
           "an office whose P1001 is the state is not asked P17")
    regional = ent({"en": "Governor of Zenda"}, P31=["Q294414"], P279=["Q83307"], P1001=["Q900098"])
    expect(ctx.gaps(item("Q9", "subnational", regional), {"Q83307"}) == [("P17", "missing", None)],
           "one whose P1001 is narrower than the state still is")
    swapped = item("Q7", "subnational", ent({"en": "mayor of Zenda"}, P31=["Q30185"], P279=["Q17279032", "Q294414"]))
    expect(ctx.gaps(swapped, {"Q30185"}) == [("P17", "missing", None), ("P1001", "missing", None)],
           "a type/class-swapped item is asked P17/P1001 and never P31/P279")
    expect(not gaps.inverted(ent({"en": "Minister of Health"}, P31=["Q4164871"], P279=["Q294414"])),
           "a stray metaclass in P279 beside a position type in P31 is not the swap: its class is still repaired")
    meta = item("Q2", "national", ent({"en": "x"}, P31=["Q17279032"], P17=["Q900001"], P1001=["Q900001"], P279=["Q83307"]))
    expect(ctx.gaps(meta, {"Q83307"}) == [], "elective office counts as a position metaclass")
    judge = item("Q3", "national", ent({"xa": "judge of the Supreme Court of Ruritania"}, P31=["Q4164871"],
                                       P17=["Q900001"], P1001=["Q900001"], P279=["Q16533"], P361=["Q900040"]))
    expect(ctx.gaps(judge, {"Q16533"}) == [("P279", "classfix", "apex_judge")],
           "a Supreme Court judge typed plain 'judge' gets a class fix (body route)")
    expect(ctx.gaps(judge, {"Q16533", "Q117826617"}) == [], "once it reaches the class, no fix")
    chief = item("Q9", "national", ent({"en": "Minister of Health"}, P31=["Q4164871"], P17=["Q900001"],
                                       P1001=["Q900001"], P279=["Q900099"]))
    nuncio = item("Q10", "ambassador", ent({"en": "apostolic nuncio to Ruritania"}, P31=["Q4164871"], P17=["Q900001"],
                                          P279=["Q157037"]))
    expect(ctx.gaps(nuncio, {"Q157037", "Q740369"}) == [],
           "an office in a category's excluded subtree (nuncio under papal legate) gets no class fix into it")
    # Soft exclusion: a class under papal legate (soft) and also "ambassador of a country" is in;
    # one only under papal legate is out; a hard exclusion (mayor) keeps out whatever else is reached.
    edges = {"Q900081": ["Q740369", "Q29645880"], "Q900082": ["Q740369"], "Q740369": ["Q121998"],
             "Q900083": ["Q30185", "Q14212"], "Q30185": ["Q2285706"]}
    real = gaps.typegraph.edges
    gaps.typegraph.edges = lambda qs: {q: edges.get(q, []) for q in qs}
    try:
        amb, hog = ctx.by_key["ambassador"], ctx.by_key["head_of_government"]
        expect(gaps.reaches(amb, {"Q900081", "Q740369", "Q29645880", "Q121998"}, ["Q900081"]),
               "a nuncio-like class (soft-excluded legate, also ambassador of a country) is an ambassador")
        expect(not gaps.reaches(amb, {"Q900082", "Q740369", "Q121998"}, ["Q900082"]),
               "a class reaching ambassador only through the soft-excluded legate is not")
        expect(not gaps.reaches(amb, {"Q900081", "Q740369", "Q29645880", "Q121998"}),
               "without seeds a soft exclusion still keeps the item out")
        expect(not gaps.reaches(hog, {"Q900083", "Q30185", "Q14212", "Q2285706"}, ["Q900083"]),
               "a hard exclusion (mayor) keeps out an item that also reaches prime minister")
    finally:
        gaps.typegraph.edges = real
    expect(ctx.gaps(chief, {"Q900099", "Q14212"}) == [],
           "a title read as minister whose class is already a head of government gets no minister class fix")
    head = ent({"en": "President of the Republic of Ruritania"})
    expect(gaps.name_categories(XX, NAMES, head) == {"head_of_state"},
           "a head category: the class name, then nothing but the state's name")
    expect(gaps.name_categories(XX, NAMES, ent({"en": "President of the Supreme Court of Ruritania"})) == set(),
           "the president of a court is not a head of state")
    deputy = ent({"en": "Deputy Prosecutor General of the Republic of Ruritania"})
    expect(gaps.name_categories(XX, NAMES, deputy) == set(), "a deputy is never put in a head category")
    # A deputy phrase is stripped whole: "deputy chief" does not make "chief" a deputy word.
    from dataclasses import replace as _replace
    chiefs = _replace(XX, words={**XX.words, "deputy": [*XX.words["deputy"], "deputy chief"]})
    expect(gaps.name_categories(chiefs, NAMES, ent({"en": "Chief Minister of Ruritania"})) == set(),
           "a chief minister is not read as a minister when 'deputy chief' is a deputy phrase")
    expect(gaps.name_categories(chiefs, NAMES, ent({"en": "First Deputy Minister of Health"})) == {"minister"},
           "a two-word deputy phrase is still stripped")
    expect(gaps.name_categories(XX, NAMES, ent({"en": "Deputy Minister of Health"})) == {"minister"},
           "a deputy minister is in the minister category, and 'deputy' alone names no legislator")
    expect(gaps.name_categories(XX, NAMES, ent({"en": "Head of the Culture Department"})) == set(),
           "a label must lead with the class name")
    local = item("Q5", "subnational", ent({"en": "Minister of Health of Strelsau"}, P31=["Q294414"], P17=["Q900001"],
                                          P1001=["Q900020"], P279=["Q30185"]))
    expect(ctx.gaps(local, {"Q30185"}) == [], "a subnational office gets no national class fix")
    learned()


def learned() -> None:
    """The level words a country's own offices teach, and what they do not."""
    from dataclasses import replace

    from peploop.tree.check_fixture import DISTRICT, PLACES

    xx = replace(XX)
    offices = [item(f"Q7{i}", "subnational", ent({"xa": f"chairman of the {name} Raionic Executive Committee"},
                                                 P1001=[r]))
               for i, (name, r) in enumerate((("Karelia", "R1"), ("Lindau", "R2"), ("Zenda", "R3")))]
    from peploop.tree.check_fixture import place
    aliased = [place(r, "district", {"en": f"{n} District", "en:x": f"{n} District"}, [DISTRICT])
               for n, r in (("Karelia", "R1"), ("Lindau", "R2"), ("Zenda", "R3"))]
    councils = [item(f"Q6{i}", "subnational", ent({"en": f"chairman of the {n} District Council"}, P1001=[r]))
                for i, (n, r) in enumerate((("Karelia", "R1"), ("Lindau", "R2"), ("Zenda", "R3")))]
    expect(country.learn_level_words(replace(XX), councils, aliased) == {DISTRICT: ["district"]},
           "a whole alias's type word is not the place's name: 'Council' after 'District' is not learned")
    words = country.learn_level_words(xx, offices, list(PLACES.places.values()))
    expect(words == {DISTRICT: ["raionic"]}, "the word after the place's name, in three offices of one type, is learned, whole")
    expect(country.level_types(xx, "deputy chairman of the Zenda Raionic Council") >= {DISTRICT},
           "and then names that level in another label")
    federal = replace(XX, type_words={**XX.type_words, "Q900010": ["region", "federal"]})
    heads = [item(f"Q5{i}", "national", ent({"en": f"Federal {t} of Ruritania"}, P1001=[XX.qid]))
             for i, t in enumerate(("President", "Chancellor", "Minister of Finance"))]
    country.learn_level_words(federal, heads + offices, list(PLACES.places.values()))
    expect(country.level_types(federal, "Federal President of Ruritania") == set()
           and country.level_types(federal, "Governor of the Zenda Region") == {"Q900010"},
           "a word three of the state's own offices use is not a level word ('federal state')")
    premiers = [item(f"Q4{i}", "subnational", ent({"sv": f"{name}s premiärminister"}, P1001=[r]))
                for i, (name, r) in enumerate((("Karelia", "R1"), ("Lindau", "R2"), ("Zenda", "R3")))]
    expect(country.learn_level_words(replace(XX), premiers, list(PLACES.places.values())) == {},
           "another language's labels teach nothing: Swedish puts the place first, the office's noun after")
    two = country.learn_level_words(replace(XX), offices[:2], list(PLACES.places.values()))
    expect(two == {}, "two offices teach nothing")
    expect(country.stems("Ruritanian PR") == {"ruritani", "pr"} and country.stems("pr of x") == set(),
           "an all-capital short word is kept whole; a short lowercase one is not")
    matching()
    chain()
    spans()
    discovery()
    bisection()


def matching() -> None:
    """Places and level words are whole words, inflected at most at the end."""
    from dataclasses import replace

    from peploop.tree import signals
    from peploop.tree.check_fixture import place

    expect(not country.word_match("zendaborg", "zendel") and not country.word_match("marine", "zendel"),
           "a place's name is never matched by a shared prefix ('Zendel' is not 'Zendaborg')")
    expect(country.level_types(XX, "Secretary of the Guardian Council") == set()
           and country.level_types(XX, "governor of Strelsau County") == {"Q900012"},
           "a level word is a whole word: 'county' is not 'Council'")
    expect(country.word_match("турцыі", "турцыя") and country.word_match("zendaskaga", "zendaska")
           and country.word_match("strelsaus", "strelsau"), "a case ending or a suffix is still the same name")
    expect(country.words("شهردار شهر ری") == {"شهردار", "شهر", "ری"} and country.words("mayor of Rey") == {"mayor", "rey"},
           "short words count in Arabic script; three letters elsewhere")
    fa = replace(XX, type_words={**XX.type_words, "Q900013": ["شهر"]})
    expect(country.level_types(fa, "شهردار شهر ری") == {"Q900013"}, "a two-letter-short level word works in Arabic script")
    places = signals.Places([place("A1", "region", {"xa": "Zendasu Region"}, ["Q900010"]),
                             place("A2", "district", {"xa": "Zendasai District"}, ["Q900011"]),
                             place("A3", "region", {"xa": "Abai Region"}, ["Q900010"]),
                             place("A4", "district", {"xa": "Abai District"}, ["Q900011"]),
                             place("A5", "region", {"xa": "Strelsau", "xa:old": "Old Strelsau"}, ["Q900010"])])
    expect(places.mentioned("akim of Zendasu Region", {"region", "district"}) == ["A1"],
           "an inflected match yields to a whole one on the same words")
    expect(places.of_type("akim of Abai Region", country.level_types(XX, "akim of Abai Region")) == ["A3"],
           "the level word picks the region, not the district of the same name")
    expect(places.mentioned("governor of Old Strelsau", {"region"}) == ["A5"], "an alias (a former name) is a name")
    xx = replace(XX, type_words={**XX.type_words, "Q900010": ["administrative", "region"]})
    country.prune_type_words(xx, list(places.places.values()))
    expect(xx.type_words["Q900010"] == ["region"], "a type word none of its places is named with is dropped")
    offices = [{"qid": f"Q8{i}", "entity": ent({"xa": f"chairman of the {n} administrative committee"}, P1001=[r])}
               for i, (n, r) in enumerate((("Karelia", "R1"), ("Lindau", "R2"), ("Zenda", "R3")))]
    from peploop.tree.check_fixture import PLACES
    expect(country.learn_level_words(replace(XX), offices, list(PLACES.places.values())) == {},
           "an 'administrative' word is never learned as a level word")


def chain() -> None:
    """The predecessor chain: two steps back, exclusive, never through a federation or an umbrella."""
    def e(p31: str = "Q3024240", start: int | None = None, end: int | None = None, **claims: list[str]) -> dict:
        out = ent({"en": "x"}, P31=[p31], **claims)
        for prop, y in (("P571", start), ("P576", end)):
            if y is not None:
                out["claims"][prop] = [{"rank": "normal", "mainsnak": {"datavalue": {"value": {"time": f"{y:+05d}-00-00T00:00:00Z"}}}}]
        return out
    world = {
        "Q900001": e("Q6256", 1979, P1365=["Q900002"]),
        "Q900002": e(start=1925, end=1979, P1365=["Q900005"], P1366=["Q900001"]),  # the last dynasty's state
        "Q900005": e(start=1789, end=1925, P1366=["Q900002"], P1365=["Q900006"]),  # the one before it
        "Q900006": e(start=1736, end=1796, P1366=["Q900005"]),  # gone before the PEP era
        "Q900007": e(start=-550, end=1979, P1366=["Q900001"]),  # an umbrella over all of them
        "Q900008": e(start=1700, end=1917, P1366=["Q900005", "Q900009"]),  # an empire two states succeeded
        "Q900010": e(start=641, P1366=["Q900001"]),  # a medieval period, typed a historical country, no end
    }
    inverse = {"Q900001": ["Q900007", "Q900010"], "Q900005": ["Q900008"]}
    out, how = country.walk_chain("Q900001", {}, {}, lambda qs: {q: world[q] for q in qs if q in world},
                                  lambda q: inverse.get(q, []),
                                  lambda ents: {q: {q, *x["claims"]["P31"][0]["mainsnak"]["datavalue"]["value"]["id"].split()}
                                                | {"Q3024240"} for q, x in ents.items()})
    expect(set(out) == {"Q900002", "Q900005"}, "the dynasty two steps back is a predecessor; "
           "the pre-1900 one, the undated medieval period, the umbrella and the shared empire are not")
    expect(how["Q900005"] == "wikidata P1365 of Q900002", "and its provenance says how it was reached")


def spans() -> None:
    """Which predecessors' ends move the state's start: only a form the state replaced."""
    def e(p31: str = "Q3024240", start: int | None = None, end: int | None = None, **claims: list[str]) -> dict:
        out = ent({"en": "x"}, P31=[p31], **claims)
        for prop, y in (("P571", start), ("P576", end)):
            if y is not None:
                out["claims"][prop] = [{"rank": "normal", "mainsnak": {"datavalue": {"value": {"time": f"{y:+05d}-00-00T00:00:00Z"}}}}]
        return out
    state = "Q900001"
    ents = {
        state: e("Q6256", 1960),
        "Q900020": e(start=1890, end=1960, P1366=[state]),  # the colony it replaced
        "Q900021": e(start=1970, end=1997, P1366=[state]),  # a regime period of the state itself
        "Q900022": e("Q3624078", 1971, 1997, P1366=[state]),  # a sovereign regime that replaced it
        "Q900023": e("Q1790360", 1583, 1997),  # the colony's empire, ending elsewhere
        "Q900024": e(start=1415, end=1999, P156=["Q900029"]),  # an empire succeeded by another state
        "Q900025": e(start=1962, end=1999, P1366=[state]),  # a sideline it administered
        "Q900026": e(start=1890, end=1958, P156=["Q900027"]),  # succeeded by a regime item within the state
        "Q900027": e("Q1307214", P17=[state]),
    }
    preds = {q: q for q in ("Q900020", "Q900021", "Q900022", "Q900024", "Q900025", "Q900026")} | {"Q900020": "Q900023"}
    push = lambda q: country.pushes(state, q, ents, preds)  # noqa: E731
    expect(push("Q900020") and push("Q900022") and push("Q900026"),
           "a replaced colony, a sovereign successor regime, and one succeeded within the state push the start")
    expect(not push("Q900023"), "a federation's end (the British Empire's 1997) never dates the state")
    expect(not push("Q900024"), "an empire whose successor is another state does not date this one")
    expect(not push("Q900021") and not push("Q900025"),
           "a period of the state, or a sideline it ran, begun after its own inception, does not push")
    old = {**ents, state: e("Q6256", 1727)}
    expect(country.pushes(state, "Q900021", old, preds),
           "a state whose recorded inception predates the PEP era keeps every predecessor's push")


def discovery() -> None:
    """A somevalue P39 binds a blank node; discovery keeps items only."""
    from peploop.tree import load, wd

    real = wd.sparql
    wd.sparql = lambda q, max_age=0: [{"pos": "Q1"}, {"pos": "http://www.wikidata.org/.well-known/genid/abc"}]
    try:
        found = load.discover(XX, lambda m: None)
    finally:
        wd.sparql = real
    expect(set(found) == {"Q1"}, "discover keeps only Q-ids")

    def cut_off(q: str, max_age: int = 0) -> list[dict[str, str]]:
        if "Q4164871" in q and "UNION" in q and "?t" in q:
            raise RuntimeError("SPARQL non-JSON response")
        return []
    real_q = wd.qlever
    wd.sparql, wd.qlever = cut_off, lambda q: [{"pos": "Q2"}]
    try:
        found = load.discover(XX, lambda m: None)
    finally:
        wd.sparql, wd.qlever = real, real_q
    expect(found.get("Q2") == ["descent"], "a descent the query service cuts off is asked of QLever")
    wd.sparql, wd.qlever = (lambda q, max_age=0: (_ for _ in ()).throw(RuntimeError("cut off"))), lambda q: [{"pos": "Q3"}]
    try:
        found = load.discover(XX, lambda m: None)
    finally:
        wd.sparql, wd.qlever = real, real_q
    expect(set(found["Q3"]) >= {"descent", "usage", "orphan"}, "so is any other lane")


def bisection() -> None:
    """A chunk the service cannot answer is halved until it can; one QID that still fails raises."""
    import requests

    from peploop import wikidata

    asked: list[int] = []

    def ask(chunk: list[str]) -> list[dict[str, str]]:
        asked.append(len(chunk))
        if len(chunk) > 3:
            raise RuntimeError("SPARQL non-JSON response")
        if "Q13" in chunk:
            raise requests.HTTPError("504")
        return [{"pos": q} for q in chunk]

    qids = [f"Q{i}" for i in range(20)]
    rows = wikidata.bisect(ask, [q for q in qids if q != "Q13"], size=10)
    expect(sorted(r["pos"] for r in rows) == sorted(q for q in qids if q != "Q13") and max(asked) == 10,
           "every QID is answered exactly once, from chunks halved below what the service refused")
    try:
        wikidata.bisect(ask, ["Q12", "Q13"])
        expect(False, "a single QID that keeps failing raises")
    except requests.HTTPError:
        expect(True, "a single QID that keeps failing raises")


if __name__ == "__main__":
    main()
