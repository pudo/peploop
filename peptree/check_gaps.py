"""Pin the gap step: what counts as missing, the ambassador convention, the class fix.

    .venv/bin/python -m peptree.check_gaps
"""

from peptree import country, gaps
from peptree.check_filter import ent, expect
from peptree.check_fixture import XX
from peptree.check_rules import item

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
    meta = item("Q2", "national", ent({"en": "x"}, P31=["Q17279032"], P17=["Q900001"], P1001=["Q900001"], P279=["Q83307"]))
    expect(ctx.gaps(meta, {"Q83307"}) == [], "elective office counts as a position metaclass")
    judge = item("Q3", "national", ent({"xa": "judge of the Supreme Court of Ruritania"}, P31=["Q4164871"],
                                       P17=["Q900001"], P1001=["Q900001"], P279=["Q16533"], P361=["Q900040"]))
    expect(ctx.gaps(judge, {"Q16533"}) == [("P279", "classfix", "apex_judge")],
           "a Supreme Court judge typed plain 'judge' gets a class fix (body route)")
    expect(ctx.gaps(judge, {"Q16533", "Q117826617"}) == [], "once it reaches the class, no fix")
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

    from peptree.check_fixture import DISTRICT, PLACES

    xx = replace(XX)
    offices = [item(f"Q7{i}", "subnational", ent({"xa": f"chairman of the {name} Raionic Executive Committee"},
                                                 P1001=[r]))
               for i, (name, r) in enumerate((("Karelia", "R1"), ("Lindau", "R2"), ("Zenda", "R3")))]
    from peptree.check_fixture import place
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
    two = country.learn_level_words(replace(XX), offices[:2], list(PLACES.places.values()))
    expect(two == {}, "two offices teach nothing")
    expect(country.stems("Ruritanian PR") == {"ruritani", "pr"} and country.stems("pr of x") == set(),
           "an all-capital short word is kept whole; a short lowercase one is not")
    matching()
    chain()
    discovery()


def matching() -> None:
    """Places and level words are whole words, inflected at most at the end."""
    from dataclasses import replace

    from peptree import signals
    from peptree.check_fixture import place

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
    from peptree.check_fixture import PLACES
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


def discovery() -> None:
    """A somevalue P39 binds a blank node; discovery keeps items only."""
    from peptree import load, wd

    real = wd.sparql
    wd.sparql = lambda q, max_age=0: [{"pos": "Q1"}, {"pos": "http://www.wikidata.org/.well-known/genid/abc"}]
    try:
        found = load.discover(XX, lambda m: None)
    finally:
        wd.sparql = real
    expect(set(found) == {"Q1"}, "discover keeps only Q-ids")


if __name__ == "__main__":
    main()
