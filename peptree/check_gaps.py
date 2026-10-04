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
    ctx = context()
    amb = item("Q1", "ambassador", ent({"xa": "посол Рурытаніі ў Турцыі"}, P31=["Q294414"], P279=["Q900050"]))
    expect(ctx.gaps(amb, {"Q29645880"}) == [("P17", "missing", None)],
           "an ambassador post misses P17 only: no P1001 is asked")
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
    words = country.learn_level_words(xx, offices, list(PLACES.places.values()))
    expect(words == {DISTRICT: ["raion"]}, "the word after the place's name, in three offices of one type, is learned")
    expect(country.level_types(xx, "deputy chairman of the Zenda Raionic Council") >= {DISTRICT},
           "and then names that level in another label")
    two = country.learn_level_words(replace(XX), offices[:2], list(PLACES.places.values()))
    expect(two == {}, "two offices teach nothing")
    expect(country.stems("Ruritanian PR") == {"ruritani", "pr"} and country.stems("pr of x") == set(),
           "an all-capital short word is kept whole; a short lowercase one is not")


if __name__ == "__main__":
    main()
