"""An invented country for the offline checks: no network, no database.

Ruritania (Q900001, since 1991) succeeded the Ruritanian People's Republic
(Q900002, 1950–1991), a constituent republic of the Grand Federation
(Q900003, 1922–1991). Its words and place types are given here as
`country.config` would derive them from data.
"""

from peploop.tree import country, signals

XX = country.Country(
    cc="xx", qid="Q900001", official=("xa",), langs=("xa", "en", "mul"),
    predecessors={"Q900002": "Q900003"},
    names={"Q900001": ["Ruritania", "Republic of Ruritania", "Рурытанія"],
           "Q900002": ["Ruritanian People's Republic", "Ruritanian PR", "RPR"],
           "Q900003": ["Grand Federation"]},
    local_names={"Q900001": ["Ruritania", "Republic of Ruritania", "Рурытанія"],
                 "Q900002": ["Ruritanian People's Republic", "Ruritanian PR", "RPR"],
                 "Q900003": ["Grand Federation"]},
    words={"deputy": ["deputy", "first deputy", "vice"], "diplomatic": ["ambassador", "посол", "permanent representative"],
           "mission": ["permanent representative"],
           "non_state": ["party", "trade union", "federation"], "consular": ["consul", "consul general", "honorary consul"],
           "mayor": ["mayor", "мэр"], "body": ["office", "staff", "ministry", "administration"]},
    type_words={"Q900010": ["region"], "Q900011": ["district"], "Q515": ["city"], "Q900012": ["county"]},
    type_terms={"Q900010": ["region"], "Q900011": ["district"], "Q900012": ["county"], "Q515": ["city"]},
    spans={"Q900001": [1991, None], "Q900002": [1950, 1991], "Q900003": [1922, 1991]},
    admin_words=["administrative", "territorial", "entity"],
)
REGION, DISTRICT = "Q900010", "Q900011"


def place(qid: str, level: str, names: dict[str, str], types: list[str] = ()) -> dict:
    """A gazetteer row, its words computed as `country.gazetteer` does."""
    drop = {w for t in types for w in XX.type_terms.get(t, [])}
    found = [country.words(n, set() if ":" in key else drop) for key, n in names.items()]
    return {"qid": qid, "levels": [level], "names": names, "types": list(types), "classes": list(types),
            "words": [sorted(w) for w in found if w]}


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

#: The state's cities (gazetteer level `local`, class city).
CITY_PLACES = [place("C1", "local", {"en": "Zendaborg"}, ["Q515"]),
               place("C2", "local", {"en": "Faithton", "en:Faith City": "Faith City"}, ["Q515"])]
