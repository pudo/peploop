"""What peptree needs to know about one country, read from data.

Nothing here names a country. The languages come from rigour; the predecessor
states from rigour's historical territories and the country's own `P1365`/
`P155`; the place gazetteer from `P150` and `P131`; and every word a label
is read for (a level of government, a deputy, an ambassador, a party) is the
label of a Wikidata class in the country's languages. A country whose data is
thin gets fewer matches, never a wrong rule written for another country.
"""

import re
from dataclasses import dataclass, field
from typing import Any

from rigour.langs import iso_639_alpha2
from rigour.territories import get_territories, get_territory

from peptree import wd

#: Classes that make an item a state, for a predecessor or a federation.
STATE_CLASSES = {"Q7275", "Q3024240", "Q6256", "Q3624078"}  # state, historical country, country, sovereign state
#: A predecessor dissolved before this year held no office a PEP list asks about.
PEP_ERA = 1900
ADMIN_ENTITY, SETTLEMENT, CITY = "Q56061", "Q486972", "Q515"
#: Second-level and local place types: those making up this share of a level.
TYPE_SHARE = 0.2
FORMER = "Q19953632"  # former administrative territorial entity
ELECTORAL = "Q192611"  # electoral unit: its words ("Assembly", "district") name the legislature, not a level
#: City and town: the words every country's city offices use, whatever its own city classes.
GENERIC_PLACE_TYPES = ("Q515", "Q3957")
LIST_CLASS = "Q13406463"  # Wikimedia list article: "list of districts of X" is an alias, not a word
#: Concepts whose names, in the country's languages, are the words a label is read for.
CONCEPTS = {
    "deputy": ("Q3250324", "Q21814496"),  # deputy, first deputy
    "diplomatic": ("Q121998", "Q19356884", "Q11051391"),  # ambassador, permanent representative, envoy
    "non_state": ("Q7278", "Q178790", "Q783794", "Q15911314", "Q2485448"),  # party, union, company, association, sports body
}
#: English is every item's second language on Wikidata, so its words ride
#: along with the derived ones: a party office labelled only in English still
#: says "party".
ENGLISH = {
    "deputy": ("deputy", "vice", "first deputy"),
    "diplomatic": ("ambassador", "permanent representative", "envoy"),
    "non_state": ("party", "trade union", "company", "association", "federation", "transitional"),
}
#: Concepts read by their labels only: an alias like "minister" (for an envoy)
#: would make every minister a diplomat.
LABELS_ONLY = {"diplomatic"}


@dataclass
class Country:
    cc: str
    qid: str
    #: Official languages as Wikidata codes, from rigour.
    official: tuple[str, ...]
    #: Label languages, best first: official ones with their script variants, en, mul.
    langs: tuple[str, ...]
    #: Predecessor state → the state its offices put in `P17` (its federation, or itself).
    predecessors: dict[str, str] = field(default_factory=dict)
    #: Names (labels and aliases) of the country, its predecessors and their federations.
    names: dict[str, list[str]] = field(default_factory=dict)
    #: The same, in the label languages only.
    local_names: dict[str, list[str]] = field(default_factory=dict)
    #: Concept → phrases (see CONCEPTS).
    words: dict[str, list[str]] = field(default_factory=dict)
    #: Subnational place type → the stems of the word its labels lead with.
    type_words: dict[str, list[str]] = field(default_factory=dict)
    #: Place type → every stem of its labels: what a place's name is not.
    type_stems: dict[str, list[str]] = field(default_factory=dict)
    #: Place type → words its offices use, learned from the load (`learn_level_words`).
    learned_words: dict[str, list[str]] = field(default_factory=dict)
    #: Where each predecessor came from, for the report.
    provenance: dict[str, str] = field(default_factory=dict)

    @property
    def unions(self) -> set[str]:
        return {u for p, u in self.predecessors.items() if u != p}

    @property
    def home(self) -> set[str]:
        """The state and every predecessor and federation: one country for holder counts."""
        return {self.qid} | set(self.predecessors) | self.unions

    @property
    def p17_values(self) -> list[str]:
        """What `P17` may say for an office of this country, the state first."""
        return list(dict.fromkeys([self.qid, *sorted(set(self.predecessors.values()))]))

    @property
    def p1001_values(self) -> list[str]:
        return [self.qid, *sorted(self.predecessors)]


# --- tokens and stems --------------------------------------------------------------

TOKEN = re.compile(r"\w+", re.U)


def stems(text: str, drop: set[str] | frozenset[str] = frozenset()) -> set[str]:
    """Inflection-tolerant prefixes of a name's words, minus `drop`.

    A word of four letters or more is cut by two ("Warszawa" → "warsza"); a short
    all-capital word is kept whole, since it is an abbreviation that tells
    a republic from its state.
    """
    out = set()
    for tok in TOKEN.findall(text):
        low = tok.lower()
        if low.isdigit():
            continue
        if len(low) >= 4:
            out.add(low[: max(4, len(low) - 2)])
        elif 2 <= len(tok) <= 3 and tok.isalpha() and tok.isupper():  # "SSR", "ССР"
            out.add(low)
    return {s for s in out if not any(s.startswith(d) or d.startswith(s) for d in drop)}


def seq(text: str) -> list[str]:
    """The stems of a name's words in order ("Prime Minister of X" → prim, minis, x)."""
    out = []
    for tok in TOKEN.findall(text):
        one = stems(tok)
        if one:
            out.append(next(iter(one)))
    return out


def tokens(text: str) -> list[str]:
    return TOKEN.findall(text.lower())


def has_stems(need: set[str], toks: list[str]) -> bool:
    return bool(need) and all(any(t.startswith(s) for t in toks) for s in need)


def says(phrases: list[str], text: str) -> bool:
    """Whether `text` contains one of the phrases, word by word, in any inflection."""
    toks = tokens(text)
    return any(has_stems(stems(p), toks) for p in phrases)


def lead_word(name: str, drop: set[str]) -> str | None:
    """The stem of the first real word of a class name ("district of X" → "distri")."""
    for tok in TOKEN.findall(name):
        s = stems(tok, drop)
        if s:
            return next(iter(s))
    return None


def mentions(place: dict[str, Any], text: str) -> bool:
    """Whether `text` names the place: every stem of one of its names begins a word."""
    toks = tokens(text)
    return any(has_stems(set(need), toks) for need in place["stems"])


# --- the country ---------------------------------------------------------------------

def _official(cc: str) -> tuple[str, ...]:
    territory = get_territory(cc)
    if territory is None:
        raise KeyError(f"rigour knows no territory {cc!r}")
    return tuple(dict.fromkeys(a for a in (iso_639_alpha2(lang) for lang in territory.langs) if a))


def _year(entity: dict[str, Any], prop: str) -> int | None:
    years = []
    for claim in entity.get("claims", {}).get(prop, []):
        v = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(v, dict) and "time" in v:
            years.append(int(v["time"][: v["time"].index("-", 1)]))
    return max(years) if years else None


def _qids(entity: dict[str, Any], prop: str) -> list[str]:
    out = []
    for claim in entity.get("claims", {}).get(prop, []):
        if claim.get("rank") == "deprecated":
            continue
        v = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(v, dict) and "id" in v:
            out.append(v["id"])
    return out


def derive_predecessors(cc: str, qid: str) -> tuple[dict[str, str], dict[str, str]]:
    """(predecessor → its P17 state, predecessor → where it was found).

    Two sources: rigour's historical territories that name this country as a
    successor (with their parent as the federation), and the country item's
    own `P1365` replaces / `P155` follows. A candidate must be a state and
    must have lasted into the PEP era. A predecessor that another one names in
    its `P17` (a federation, for one of its constituent republics) is that one's federation,
    not a predecessor of its own.
    """
    found: dict[str, str] = {}
    parents: dict[str, str] = {}
    for t in get_territories():
        if t.is_historical and t.qid and any(s.code == cc for s in t.successors):
            found.setdefault(t.qid, "rigour")
            if t.parent is not None and t.parent.qid:
                parents[t.qid] = t.parent.qid
    country = wd.fetch_items([qid], props="claims")[qid]
    for prop in ("P1365", "P155"):
        for v in _qids(country, prop):
            found.setdefault(v, f"wikidata {prop}")
    if not found:
        return {}, {}
    ents = wd.fetch_items(sorted(found), props="claims")
    states = wd.closure({q: _qids(e, "P31") for q, e in ents.items()})
    keep = {}
    for q, e in ents.items():
        dissolved = _year(e, "P576")
        if not states[q] & STATE_CLASSES or (dissolved is not None and dissolved < PEP_ERA) or q == qid:
            continue
        keep[q] = e
    out: dict[str, str] = {}
    for q, e in keep.items():
        p17 = [v for v in _qids(e, "P17") if v not in (q, qid)]
        out[q] = parents.get(q) or (p17[0] if p17 else q)
    # The federation of one predecessor is not a predecessor of its own.
    for fed in {u for p, u in out.items() if u != p}:
        out.pop(fed, None)
    return out, {q: found[q] for q in out}


def _bisect(fn: Any, qids: list[str]) -> list[dict[str, str]]:
    """Run a VALUES-pinned query, halving the list when the service cannot answer it."""
    if not qids:
        return []
    try:
        return fn(qids)
    except RuntimeError:
        if len(qids) == 1:
            raise
        half = len(qids) // 2
        return _bisect(fn, qids[:half]) + _bisect(fn, qids[half:])


def _subdivisions(qid: str) -> dict[str, Any]:
    """First-level units, second-level units and the third level's types."""
    def rows(query: str) -> list[dict[str, str]]:
        return wd.sparql(query, max_age=30 * wd.DAY)

    level1 = rows(f"""SELECT DISTINCT ?x ?t WHERE {{ wd:{qid} p:P150 ?s . ?s ps:P150 ?x .
      FILTER NOT EXISTS {{ ?s pq:P582 [] }} OPTIONAL {{ ?x wdt:P31 ?t }} }}""")
    l1 = sorted({r["x"] for r in level1})
    # Second level: P150 of a first-level unit, or anything P131 in one that is
    # an administrative unit or a city (not a village, a river or a mountain).
    cand = []
    for chunk in wd.values_chunks(l1, 40):
        block = wd.values_block(chunk)
        cand += rows(f"""SELECT DISTINCT ?y ?t WHERE {{ VALUES ?x {{ {block} }} ?x p:P150 ?s . ?s ps:P150 ?y .
          FILTER NOT EXISTS {{ ?s pq:P582 [] }} OPTIONAL {{ ?y wdt:P31 ?t }} }}""")
        by_type = rows(f"""SELECT ?t (COUNT(DISTINCT ?y) AS ?n) WHERE {{ VALUES ?x {{ {block} }}
          ?y wdt:P131 ?x ; wdt:P31 ?t }} GROUP BY ?t""")
        types = [r["t"] for r in by_type]
        up = wd.class_closure(types)
        wanted = [t for t in types if not up.get(t, set()) & {FORMER, ELECTORAL} and (
            CITY in up.get(t, set()) or (ADMIN_ENTITY in up.get(t, set()) and SETTLEMENT not in up.get(t, set())))]
        for x in chunk:  # one unit at a time: a whole chunk times out mid-answer
            cand += _bisect(lambda ts, x=x: rows(f"""SELECT DISTINCT ?y ?t WHERE {{ VALUES ?t {{ {wd.values_block(ts)} }}
              ?y wdt:P131 wd:{x} ; wdt:P31 ?t . FILTER NOT EXISTS {{ ?y wdt:P576 [] }} }}"""), wanted)
    l2 = sorted({r["y"] for r in cand} - set(l1))
    # The third level is not read in full (a country has thousands of
    # villages); only its types, for the words that name a local office.
    l3_types: dict[str, int] = {}
    for chunk in wd.values_chunks(l2, 60):
        for r in rows(f"""SELECT ?t (COUNT(DISTINCT ?z) AS ?n) WHERE {{ VALUES ?y {{ {wd.values_block(chunk)} }}
          {{ ?y wdt:P150 ?z }} UNION {{ ?z wdt:P131 ?y }} ?z wdt:P31 ?t }} GROUP BY ?t"""):
            l3_types[r["t"]] = l3_types.get(r["t"], 0) + int(r["n"])
    types: dict[str, dict[str, int]] = {"region": {}, "district": {}, "local": l3_types}
    place_types: dict[str, list[str]] = {}
    for level, found in (("region", level1), ("district", cand)):
        for r in found:
            if level == "district" and r.get("y") in l1:
                continue
            x = r.get("x") or r.get("y")
            if r.get("t"):
                place_types.setdefault(x, []).append(r["t"])
        counts: dict[str, int] = {}
        for x in (l1 if level == "region" else l2):
            for t in set(place_types.get(x, [])):
                counts[t] = counts.get(t, 0) + 1
        types[level] = counts
    return {"l1": l1, "l2": l2, "types": types, "place_types": place_types}


def dominant(counts: dict[str, int], total: int, up: dict[str, set[str]]) -> list[str]:
    """The types that make up a level: a fifth of its places or more, and an
    administrative unit or a city (never a street, a building, a former unit or
    an electoral district)."""
    out = []
    for t, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        closure = up.get(t, {t})
        if closure & {FORMER, ELECTORAL} or not (ADMIN_ENTITY in closure or CITY in closure):
            continue
        if n / max(total, 1) >= TYPE_SHARE:
            out.append(t)
    return out


def home_names(qids: list[str], langs: list[str]) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """(every name, the names in `langs`) of each state.

    Every language's label, because an item labelled only in Polish still
    names its state, but none whose words are all shorter than five letters
    ("Bela"); aliases only in the country's own languages, because the long
    tail of foreign aliases holds historical and colloquial names.
    """
    every, local = {}, {}
    for q, e in wd.fetch_items(qids, props="labels|aliases").items():
        mine = [o["value"] for lg, o in e.get("labels", {}).items() if lg in langs]
        mine += [a["value"] for lg, al in e.get("aliases", {}).items() if lg in langs for a in al]
        rest = [o["value"] for lg, o in e.get("labels", {}).items() if lg not in langs]
        rest = [n for n in rest if any(len(x) >= 5 for x in stems(n))]
        local[q] = list(dict.fromkeys(mine))
        every[q] = list(dict.fromkeys(mine + rest))
    return every, local


def config(cc: str) -> dict[str, Any]:
    """Everything about a country that comes from data, as plain JSON (cached a month).

    This is the country-config step: it costs Wikidata reads and no model calls.
    """
    cc = cc.lower()

    def fetch() -> dict[str, Any]:
        territory = get_territory(cc)
        if territory is None or not territory.qid:
            raise KeyError(f"rigour knows no state {cc!r}")
        qid = territory.qid
        official = _official(cc)
        item = wd.fetch_items([qid], props="labels")[qid]
        variants = sorted(lg for lg in item.get("labels", {}) if any(lg.startswith(o + "-") for o in official))
        langs = [x for o in official for x in [o, *[v for v in variants if v.startswith(o + "-")]]]
        langs = list(dict.fromkeys([*langs, "en", "mul"]))
        preds, provenance = derive_predecessors(cc, qid)
        home = [qid, *preds, *{u for p, u in preds.items() if u != p}]
        names, local_names = home_names(home, langs)
        words: dict[str, list[str]] = {}
        for concept, qids in CONCEPTS.items():
            if concept in LABELS_ONLY:
                ents = wd.fetch_items(qids, props="labels")
                found = [o["value"] for e in ents.values() for lg, o in e.get("labels", {}).items() if lg in langs]
            else:
                found = [n for ns in wd.names_of(qids, langs).values() for n in ns]
            words[concept] = list(dict.fromkeys([*found, *ENGLISH[concept]]))
        sub = _subdivisions(qid)
        types = sub["types"]
        up = wd.class_closure({t for level in types.values() for t in level})
        totals = {"region": len(sub["l1"]), "district": len(sub["l2"]), "local": sum(types["local"].values())}
        lead_types = {t for level in ("region", "district", "local") for t in dominant(types[level], totals[level], up)}
        lead_types |= set(GENERIC_PLACE_TYPES)
        all_types = lead_types | {t for ts in sub["place_types"].values() for t in ts}
        type_names = wd.names_of(sorted(all_types | {LIST_CLASS}), langs)
        own = set().union(*(stems(n) for n in local_names[qid])) if local_names.get(qid) else set()
        junk = {lead_word(n, own) for n in type_names.get(LIST_CLASS, [])}
        type_words = {}
        for t in sorted(lead_types):
            ws = {lead_word(n, own) for n in type_names.get(t, [])} - junk
            type_words[t] = sorted(w for w in ws if w)
        type_stems = {t: sorted(set().union(*(stems(n) for n in ns)) if ns else set())
                      for t, ns in type_names.items() if t != LIST_CLASS}
        return {"cc": cc, "qid": qid, "official": list(official), "langs": langs, "predecessors": preds,
                "provenance": provenance, "names": names, "local_names": local_names, "words": words,
                "type_words": type_words, "type_stems": type_stems, "subdivisions": sub}

    return wd.cached(f"country:{cc}", fetch)


_loaded: dict[str, Country] = {}


def get(cc: str) -> Country:
    """The country for a run; also makes its languages the label languages."""
    cc = cc.lower()
    if cc not in _loaded:
        wd.init()
        cfg = config(cc)
        _loaded[cc] = Country(cc=cc, qid=cfg["qid"], official=tuple(cfg["official"]), langs=tuple(cfg["langs"]),
                              predecessors=dict(cfg["predecessors"]), names=cfg["names"],
                              local_names=cfg["local_names"], words=cfg["words"],
                              type_words=cfg["type_words"], type_stems=cfg["type_stems"],
                              provenance=cfg["provenance"])
    c = _loaded[cc]
    wd.set_langs(("en", *[lg for lg in c.langs if lg not in ("en", "mul")], "mul"))
    return c


# --- what a label names ------------------------------------------------------------

def _name_stems(c: Country, qid: str) -> list[set[str]]:
    return [s for s in (stems(n) for n in c.names.get(qid, [])) if s]


def names_country(c: Country, text: str) -> bool:
    toks = tokens(text)
    return any(has_stems(s, toks) for s in _name_stems(c, c.qid))


def distinctive(c: Country, qid: str) -> list[set[str]]:
    """The names of a predecessor that cannot be read as the state's own name.

    A republic's "<name> SSR" is distinctive by its "SSR"; a "Republic of
    <name>" that preceded today's republic is not, and is never matched. Only
    names in the country's own languages: the long tail of foreign labels
    holds one where "Republic" is the only word that differs.
    """
    own = set().union(*_name_stems(c, c.qid)) if _name_stems(c, c.qid) else set()
    out = []
    for need in (s for s in (stems(n) for n in c.local_names.get(qid, [])) if s):
        if any(not any(s.startswith(o) or o.startswith(s) for o in own) for s in need):
            out.append(need)
    return out


def named_predecessor(c: Country, text: str) -> str | None:
    """The predecessor a label names by one of its distinctive names, if any.

    Stricter than a place match: each word may run at most four letters past
    its stem, so "Communist" does not match "Communications".
    """
    toks = tokens(text)
    for q in sorted(c.predecessors):
        for need in distinctive(c, q):
            if all(any(t.startswith(s) and len(t) <= len(s) + 4 for t in toks) for s in need):
                return q
    return None


def level_types(c: Country, text: str) -> set[str]:
    """The subnational place types whose words a label uses ("District", "Regional")."""
    toks = tokens(text)
    words = {t: set(c.type_words.get(t, [])) | set(c.learned_words.get(t, []))
             for t in set(c.type_words) | set(c.learned_words)}
    return {t for t, ws in words.items() if any(any(tok.startswith(w) for tok in toks) for w in ws)}


LEARN_MIN, LEARN_SHARE = 3, 0.8
SUBNATIONAL = {"region", "district", "local"}


def learn_level_words(c: Country, items: list[dict[str, Any]], places: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Words the country's own offices use for each type of place they govern.

    The class labels give the noun ("obwód", "district"); the offices give
    the adjectives and compounds a language builds from it ("obwodowego",
    "obwodowy"). For every office whose `P1001` is one place of the
    gazetteer, the word right after the place's name in each label ("Zenda
    *District* Executive Committee") is counted against the place's types; a
    word that follows at least three offices' place names, four in five of
    them of one type, is that type's word. Sets `c.learned_words`.
    """
    by_qid = {p["qid"]: p for p in places}
    own = {s for q in c.home for n in c.names.get(q, []) for s in stems(n)}
    seen: dict[str, dict[str, set[str]]] = {}  # word → place type → offices using it
    for it in items:
        scope = _qids(it["entity"], "P1001")
        if len(scope) != 1 or scope[0] not in by_qid or not set(by_qid[scope[0]]["levels"]) & SUBNATIONAL:
            continue
        place = by_qid[scope[0]]
        names = {s for need in place["stems"] for s in need}
        words = set()
        for o in it["entity"].get("labels", {}).values():
            toks = tokens(o["value"])
            at = [i for i, t in enumerate(toks) if any(t.startswith(n) for n in names)]
            if at and at[-1] + 1 < len(toks):
                words |= {w for w in stems(toks[at[-1] + 1])
                          if not any(w.startswith(o_) or o_.startswith(w) for o_ in own)}
        for w in words:
            for t in place.get("types", []):
                seen.setdefault(w, {}).setdefault(t, set()).add(it["qid"])
    learned: dict[str, set[str]] = {}
    for w, by_type in seen.items():
        total = len(set().union(*by_type.values()))
        for t, qs in by_type.items():
            if len(qs) >= LEARN_MIN and len(qs) / total >= LEARN_SHARE:
                learned.setdefault(t, set()).add(w)
    c.learned_words = {t: sorted(ws) for t, ws in learned.items()}
    return c.learned_words


def label_level(c: Country, text: str) -> bool:
    """Whether a label names a level of government below the state by its words."""
    return bool(level_types(c, text))


def sparql_name_regex(c: Country) -> str:
    """One XPath regex for a label naming the state or a predecessor (for WDQS)."""
    parts = set()
    for name in c.local_names.get(c.qid, []):
        need = stems(name)
        if len(need) == 1:
            parts |= need
    own = set().union(*_name_stems(c, c.qid)) if _name_stems(c, c.qid) else set()
    for q in c.predecessors:
        for name in c.local_names.get(q, []):
            need = stems(name)
            # One-word names only (an abbreviation): the words of a long name
            # ("Socialist", "Republic") name every republic of the federation.
            if len(need) == 1 and not any(s.startswith(o) or o.startswith(s) for s in need for o in own):
                parts |= need
    return "|".join(sorted(re.escape(p) for p in parts if len(p) >= 4))


# --- the gazetteer -------------------------------------------------------------------

def gazetteer(c: Country, extra: list[str] | None = None) -> list[dict[str, Any]]:
    """Every place a label of this country's offices may name, with its level and types.

    The fixed part (sovereign states, the country and its predecessors,
    first- and second-level units) is cached a month; `extra` adds the places
    the loaded offices already point at (their `P1001`/`P131`), as level
    `local` unless they are one of the above.
    """
    cfg = config(c.cc)

    def fetch() -> list[dict[str, Any]]:
        places: dict[str, dict[str, Any]] = {}

        def add(qid: str, level: str, names: dict[str, str], types: list[str] = ()) -> None:
            place = places.setdefault(qid, {"qid": qid, "levels": [], "names": {}, "types": []})
            place["names"].update(names)
            if level not in place["levels"]:
                place["levels"].append(level)
            place["types"] = sorted(set(place["types"]) | set(types))

        lang_list = ",".join(f"'{lg}'" for lg in c.langs)
        lab = f"?x rdfs:label ?l . BIND(LANG(?l) AS ?lang) FILTER(?lang IN ({lang_list}))"
        for row in wd.sparql(f"SELECT ?x ?l ?lang WHERE {{ ?x p:P31/ps:P31 wd:Q3624078 . "
                             f"FILTER NOT EXISTS {{ ?x wdt:P576 [] }} {lab} }}", max_age=30 * wd.DAY):
            add(row["x"], "country", {row["lang"]: row["l"]}, ["Q3624078"])
        sub = cfg["subdivisions"]
        for level, qids in (("region", sub["l1"]), ("district", sub["l2"])):
            for chunk in wd.values_chunks(qids, 100):
                for row in wd.sparql(f"SELECT ?x ?l ?lang WHERE {{ VALUES ?x {{ {wd.values_block(chunk)} }} {lab} }}",
                                     max_age=30 * wd.DAY):
                    add(row["x"], level, {row["lang"]: row["l"]}, sub["place_types"].get(row["x"], []))
        return sorted(places.values(), key=lambda p: p["qid"])

    places = {p["qid"]: {**p, "levels": list(p["levels"])} for p in wd.cached(f"gazetteer2:{c.cc}", fetch)}
    for q in c.home:
        level = "country" if q == c.qid else ("union" if q in c.unions else "predecessor")
        places[q] = {"qid": q, "levels": [level], "types": [],
                     "names": {str(i): n for i, n in enumerate(c.names.get(q, []))}}
    wanted = sorted(set(extra or []) - set(places))
    if wanted:
        ents = {}
        for chunk in wd.values_chunks(wanted, 50):
            ents.update(wd.cached("place:" + ",".join(c.langs) + ":" + "|".join(chunk),
                                  lambda chunk=chunk: {q: {"names": {lg: o["value"] for lg, o in e.get("labels", {}).items()
                                                                     if lg in c.langs},
                                                           "types": _qids(e, "P31")}
                                                       for q, e in wd.fetch_items(chunk, props="labels|claims").items()}))
        for q, e in ents.items():
            places[q] = {"qid": q, "levels": ["local"], "names": e["names"], "types": e["types"]}
    type_stems = dict(c.type_stems)
    missing = sorted({t for p in places.values() for t in p["types"]} - set(type_stems))
    for t, ns in wd.names_of(missing, c.langs).items():
        type_stems[t] = sorted(set().union(*(stems(n) for n in ns))) if ns else []
    up = wd.class_closure({t for p in places.values() for t in p["types"]})
    out = []
    for p in places.values():
        p["classes"] = sorted(set().union(*(up.get(t, {t}) for t in p["types"]))) if p["types"] else []
        drop = set().union(*(set(type_stems.get(t, [])) for t in p["types"])) if p["types"] else set()
        if p["levels"] in (["country"], ["union"], ["predecessor"]):
            drop = set()
        p["stems"] = [sorted(s) for s in (stems(n, drop) for n in p["names"].values()) if s]
        out.append(p)
    return sorted(out, key=lambda p: p["qid"])
