"""An invented country for the offline checks: no network, no database.

Ruritania (Q900001) succeeded the Ruritanian People's Republic (Q900002), a
constituent republic of the Grand Federation (Q900003). Its words and place
types are given here as `country.config` would derive them from data.
"""

from peptree import country, signals

XX = country.Country(
    cc="xx", qid="Q900001", official=("xa",), langs=("xa", "en", "mul"),
    predecessors={"Q900002": "Q900003"},
    names={"Q900001": ["Ruritania", "Republic of Ruritania", "Рурытанія"],
           "Q900002": ["Ruritanian People's Republic", "Ruritanian PR", "RPR"],
           "Q900003": ["Grand Federation"]},
    local_names={"Q900001": ["Ruritania", "Republic of Ruritania", "Рурытанія"],
                 "Q900002": ["Ruritanian People's Republic", "Ruritanian PR", "RPR"],
                 "Q900003": ["Grand Federation"]},
    words={"deputy": ["deputy", "first deputy", "vice"], "diplomatic": ["ambassador", "посол"],
           "non_state": ["party", "trade union", "federation"]},
    type_words={"Q900010": ["regi"], "Q900011": ["distri"], "Q515": ["city"]},
    type_stems={"Q900010": ["regi"], "Q900011": ["distri"]},
)
REGION, DISTRICT = "Q900010", "Q900011"


def place(qid: str, level: str, names: dict[str, str], types: list[str] = ()) -> dict:
    """A gazetteer row, its stems computed as `country.gazetteer` does."""
    drop = {s for t in types for s in XX.type_stems.get(t, [])}
    return {"qid": qid, "levels": [level], "names": names, "types": list(types), "classes": list(types),
            "stems": [sorted(country.stems(n, drop)) for n in names.values() if country.stems(n, drop)]}


PLACES = signals.Places([
    place("Q900001", "country", {"en": "Ruritania"}),
    place("Q43", "country", {"en": "Turkey", "xa": "Турцыя"}, ["Q3624078"]),
    place("Q900003", "union", {"en": "Grand Federation"}),
    place("Q900002", "predecessor", {"en": "Ruritanian People's Republic"}),
    place("Q900020", "region", {"en": "Strelsau Region"}, [REGION]),
    place("R1", "district", {"en": "Karelia District"}, [DISTRICT]),
    place("R2", "district", {"en": "Lindau District"}, [DISTRICT]),
    place("R3", "district", {"en": "Zenda District"}, [DISTRICT]),
])
