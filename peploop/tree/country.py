"""What peptree needs to know about one country, read from data.

Nothing here names a country. The languages come from rigour; the predecessor
states from rigour's historical territories and the `P1365`/`P155` chain
(either direction); the place gazetteer from `P150` and `P131`; and every word
a label is read for (a level of government, a deputy, an ambassador, a party)
is the label of a Wikidata class in the country's languages. A country whose
data is thin gets fewer matches, never a wrong rule written for another country.
"""

import re
from dataclasses import dataclass, field
from typing import Any

from rigour.langs import iso_639_alpha2
from rigour.territories import get_territories, get_territory

from peploop import eras, memo, typegraph
from peploop.eras import (  # noqa: F401  (re-exported for peptree modules)
    PEP_ERA, PRED_PROPS, SOVEREIGN, SUCC_PROPS, entity_span, pushes, years,
)
from peploop.eras import qids as _qids
from peploop.eras import year as _year
from peploop.classes import CITY
from peploop.text import strip_marks
from peploop.tree import wd

#: Classes that make an item a state, for a predecessor or a federation.
STATE_CLASSES = {"Q7275", "Q3024240", "Q6256", "Q3624078"}  # state, historical country, country, sovereign state
ADMIN_ENTITY, SETTLEMENT = "Q56061", "Q486972"
#: Second-level and local place types: those making up this share of a level.
TYPE_SHARE = 0.2
FORMER = "Q19953632"  # former administrative territorial entity
ELECTORAL = "Q192611"  # electoral unit: its words ("Assembly", "district") name the legislature, not a level
#: Places a gazetteer meets that are never a level of government, though the class
#: tree files both under administrative units: a fort's words include "military"
#: and a national park's "national", which made a military chief and a national
#: assembly read as subnational.
NOT_A_LEVEL = {FORMER, ELECTORAL, "Q57821", "Q473972"}  # fortification, protected area
#: A level's type needs this many places: one stray place cannot speak for a level.
TYPE_MIN = 2
#: City and town: the words every country's city offices use, whatever its own city classes.
GENERIC_PLACE_TYPES = ("Q515", "Q3957")
#: A state whose offices name the constituent country, not the realm rigour gives:
#: Danish positions put Q35 Denmark in P17 578 times and the Kingdom of Denmark 45;
#: Dutch ones Q55 the Netherlands 5,382 times and the Kingdom 95.
#: The realm stays a home state (Greenland's offices are its), never a predecessor.
REALM = {"dk": ("Q35", "Q756617"), "nl": ("Q55", "Q29999")}
#: A predecessor the country's own item names and whose offices are none of its own:
#: Australia "follows" the United Kingdom of Great Britain and Ireland (P155, 1901),
#: but federated from six colonies: the UK's own offices loaded as Australia's.
#: The State of Scott, a Civil War county's secession claim, names the US as
#: its successor; its one name, "Scott", would make any Scott's office a predecessor's.
NOT_PREDECESSOR = {"au": {"Q174193"}, "us": {"Q7603795"}}
LIST_CLASS = "Q13406463"  # Wikimedia list article: "list of districts of X" is an alias, not a word
#: Concepts whose names, in the country's languages, are the words a label is read for.
CONCEPTS = {
    "deputy": ("Q3250324", "Q21814496"),  # deputy, first deputy
    "diplomatic": ("Q121998", "Q19356884", "Q11051391"),  # ambassador, permanent representative, envoy
    # party, union, company, association, sports body, university, hospital, sports club
    "non_state": ("Q7278", "Q178790", "Q783794", "Q15911314", "Q2485448", "Q3918", "Q16917", "Q847017"),
    "consular": ("Q207978", "Q1075179"),  # consul, honorary consul
    "mission": ("Q19356884",),  # permanent representative: accredited to an organisation, not a state
    "mayor": ("Q30185",),  # mayor
    # office, department, secretariat, executive office, administration, ministry, government agency
    "body": ("Q182060", "Q2366457", "Q859482", "Q24886529", "Q5283295", "Q192350", "Q327333"),
}
#: English is every item's second language on Wikidata, so its words ride
#: along with the derived ones: a party office labelled only in English still
#: says "party".
ENGLISH = {
    "deputy": ("deputy", "vice", "first deputy"),
    "diplomatic": ("ambassador", "permanent representative", "envoy"),
    "non_state": ("party", "trade union", "company", "association", "federation", "transitional",
                  "university", "hospital", "club"),
    "consular": ("consul", "consul general", "honorary consul", "vice consul"),
    "mission": ("permanent representative",),
    "mayor": ("mayor",),
    "body": ("office", "staff", "administration", "secretariat", "ministry", "department", "executive office",
             "chancellery", "apparatus"),
}
#: Concepts read by their labels only: an alias like "minister" (for an envoy)
#: would make every minister a diplomat, "presidente municipal" (for a mayor)
#: every president a mayor, and "service" (for a department) every service a body.
LABELS_ONLY = {"diplomatic", "consular", "mission", "mayor", "body"}
#: The class whose names are the "administrative" words a level's class name
#: carries ("administrative region"): never a level word of their own.
ADMIN_WORDS_CLASS = "Q56061"
#: Cities of at least this population join the gazetteer as local places, so a
#: mayor's office can name its city even where the city is a third-level unit.
CITY_POPULATION = 100_000


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
    #: Subnational place type → the word its labels lead with (whole, folded).
    type_words: dict[str, list[str]] = field(default_factory=dict)
    #: Place type → every word of its labels: what a place's name is not.
    type_terms: dict[str, list[str]] = field(default_factory=dict)
    #: Place type → words its offices use, learned from the load (`learn_level_words`).
    learned_words: dict[str, list[str]] = field(default_factory=dict)
    #: Where each predecessor came from, for the report.
    provenance: dict[str, str] = field(default_factory=dict)
    #: State → (first year, last year or None): when it existed, for the era rule.
    spans: dict[str, list[int | None]] = field(default_factory=dict)
    #: The "administrative" words of the country's languages (never a level word).
    admin_words: list[str] = field(default_factory=list)
    #: False for a dependent territory: its own offices take it in `P1001` and no `P17`.
    is_state: bool = True
    #: The sovereign realm the state belongs to, where offices also name it (see REALM).
    realm: tuple[str, ...] = ()

    @property
    def unions(self) -> set[str]:
        return {u for p, u in self.predecessors.items() if u != p}

    @property
    def home(self) -> set[str]:
        """The state and every predecessor and federation: one country for holder counts."""
        return {self.qid, *self.realm} | set(self.predecessors) | self.unions

    @property
    def p17_values(self) -> list[str]:
        """What `P17` may say for an office of this country, the state first."""
        return list(dict.fromkeys([self.qid, *self.realm, *sorted(set(self.predecessors.values()))]))

    @property
    def p1001_values(self) -> list[str]:
        return [self.qid, *self.realm, *sorted(self.predecessors)]


# --- tokens and stems --------------------------------------------------------------

TOKEN = re.compile(r"\w+", re.U)


def stems(text: str, drop: set[str] | frozenset[str] = frozenset()) -> set[str]:
    """Inflection-tolerant prefixes of a name's words, minus `drop`.

    For class names and the concept words (`says`), where a prefix is what
    lets "Minister" find "Ministra". Places and levels use `words` instead: a
    prefix of a place name is another place's name ("Zend" in "Zendaborg").
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


def deputy_lead(c: "Country", stems_: list[str]) -> int:
    """How many leading stems are deputy phrases ("First Deputy Minister" → 2).

    Whole phrases only: "deputy chief" is a deputy phrase, and "chief" on its
    own is not, so "Chief Minister" keeps its first word.
    """
    phrases = [p for p in (seq(w) for w in c.words.get("deputy", [])) if p]
    k, moved = 0, True
    while moved:
        moved = False
        for p in sorted(phrases, key=len, reverse=True):
            here = stems_[k:k + len(p)]
            if len(here) == len(p) and all(t.startswith(n) or n.startswith(t) for t, n in zip(here, p)):
                k, moved = k + len(p), True
                break
    return k


def tokens(text: str) -> list[str]:
    return TOKEN.findall(strip_marks(text))


def has_stems(need: set[str], toks: list[str]) -> bool:
    return bool(need) and all(any(t.startswith(s) for t in toks) for s in need)


def says(phrases: list[str], text: str) -> bool:
    """Whether `text` contains one of the phrases, word by word, in any inflection."""
    toks = [t.lower() for t in TOKEN.findall(text)]
    return any(has_stems(stems(p), toks) for p in phrases)


def _short_script(tok: str) -> bool:
    """Arabic-script words are short ("شهر", "ری"); Latin and Cyrillic ones are not."""
    return any("\u0600" <= ch <= "\u06ff" for ch in tok)


def words(text: str, drop: set[str] | frozenset[str] | list[str] = frozenset()) -> set[str]:
    """The whole words of a name, folded, minus `drop` (compared as whole words).

    A word counts from three letters (two in Arabic script); a short
    all-capital word is an abbreviation and counts at two ("PR", "ССР").
    """
    out = set()
    for tok in TOKEN.findall(text):
        low = strip_marks(tok)
        if low.isdigit():
            continue
        if len(low) >= (2 if _short_script(low) else 3) or (len(tok) == 2 and tok.isalpha() and tok.isupper()):
            out.add(low)
    return {w for w in out if not any(word_match(w, d) or word_match(d, w) for d in drop)}


#: A name's word may carry an inflection: up to `SUFFIX` letters added to a
#: word of `SUFFIX_FROM` letters ("Strelsau" → "Strelsauskaga"), and, for a
#: place or state name, its last letter changed in a word of `SUFFIX_FROM`
#: ("Турцыя" → "Турцыі") or its last two in a word of `ENDING_FROM`
#: ("Zendaska" → "Zendaskaga"). Never a prefix: "Zendel" is not "Zendaborg",
#: "county" is not "Council".
SUFFIX_FROM, ENDING_FROM, SUFFIX, INFLECTION = 5, 7, 5, 4


def match_kind(tok: str, word: str, ending: bool = True) -> int:
    """0: no match; 1: the word itself; 2: with a suffix; 3: with its ending changed."""
    if tok == word:
        return 1
    if len(tok) > len(word) + SUFFIX:
        return 0
    if len(word) >= SUFFIX_FROM and tok.startswith(word):
        return 2
    if len(tok) > len(word) + INFLECTION:
        return 0
    if not ending:
        return 0
    if len(word) >= SUFFIX_FROM and len(tok) >= len(word) - 1 and tok.startswith(word[:-1]):
        return 3
    if len(word) >= ENDING_FROM and len(tok) >= len(word) - 2 and tok.startswith(word[:-2]):
        return 3
    return 0


def tightest(found: dict[str, tuple[int, frozenset[int]]]) -> set[str]:
    """The keys whose match no other key's tighter match beats on a shared token.

    "Ruritanian" read as a suffixed "Ruritan" yields to the whole word the
    state's own name is, just as an inflected place name yields to another
    place's name spelled out.
    """
    return {k for k, (kind, used) in found.items()
            if not any(o != k and okind < kind and oused & used for o, (okind, oused) in found.items())}


def word_match(tok: str, word: str, ending: bool = True) -> bool:
    """Whether a label's token is `word`, whole or inflected; never a prefix of it."""
    return match_kind(tok, word, ending) > 0


def has_words(need: set[str] | list[str], toks: list[str], ending: bool = True) -> bool:
    return bool(need) and all(any(word_match(t, w, ending) for t in toks) for w in need)


def name_match(need: set[str] | list[str], toks: list[str]) -> tuple[int, frozenset[int]] | None:
    """(worst match kind, the token positions used) when every word of a name is in `toks`."""
    if not need:
        return None
    worst, used = 1, set()
    for w in need:
        best = None
        for i, t in enumerate(toks):
            k = match_kind(t, w)
            if k and (best is None or k < best[0]):
                best = (k, i)
        if best is None:
            return None
        worst = max(worst, best[0])
        used.add(best[1])
    return worst, frozenset(used)


def lead_word(name: str, drop: set[str]) -> str | None:
    """The first real word of a class name ("district of X" → "district")."""
    for tok in TOKEN.findall(name):
        w = words(tok, drop)
        if w:
            return next(iter(w))
    return None


def place_match(place: dict[str, Any], toks: list[str]) -> tuple[int, frozenset[int]] | None:
    """The best way one of the place's names is in `toks` (see `name_match`), if any."""
    found = [m for m in (name_match(need, toks) for need in place["words"]) if m]
    return min(found, key=lambda m: (m[0], -len(m[1]))) if found else None


def mentions(place: dict[str, Any], text: str) -> bool:
    """Whether `text` names the place: every word of one of its names is a word of the text."""
    return place_match(place, tokens(text)) is not None


def leads_with(phrases: list[str], text: str) -> bool:
    """Whether `text` begins with one of the phrases, word for word and uninflected."""
    toks = tokens(text)
    for phrase in phrases:
        need = tokens(phrase)
        if need and toks[: len(need)] == need:
            return True
    return False


# --- the country ---------------------------------------------------------------------

def _official(cc: str) -> tuple[str, ...]:
    territory = get_territory(cc)
    if territory is None:
        raise KeyError(f"rigour knows no territory {cc!r}")
    return tuple(dict.fromkeys(a for a in (iso_639_alpha2(lang) for lang in territory.langs) if a))



#: How many `replaces`/`follows` steps the predecessor chain is walked.
CHAIN_DEPTH = 4


def _inverse(qid: str) -> list[str]:
    """Items that name `qid` as their successor (`P1366` replaced by / `P156` followed by)."""
    rows = wd.sparql(f"SELECT DISTINCT ?y WHERE {{ {{ ?y wdt:P1366 wd:{qid} }} UNION {{ ?y wdt:P156 wd:{qid} }} }}",
                     max_age=30 * wd.DAY)
    return sorted({r["y"] for r in rows if re.fullmatch(r"Q\d+", r["y"])})


def derive_predecessors(cc: str, qid: str) -> tuple[dict[str, str], dict[str, str]]:
    """(predecessor → its P17 state, predecessor → where it was found).

    Sources: rigour's historical territories that name this country as a
    successor (with their parent as the federation); the country item's own
    `P1365` replaces / `P155` follows; and the chain beyond (`walk_chain`).
    """
    found: dict[str, str] = {}
    parents: dict[str, str] = {}
    for t in get_territories():
        if t.is_historical and t.qid and any(s.code == cc for s in t.successors):
            found.setdefault(t.qid, "rigour")
            if t.parent is not None and t.parent.qid:
                parents[t.qid] = t.parent.qid

    def entities(qids: list[str]) -> dict[str, dict[str, Any]]:
        return wd.fetch_items(qids, props="claims")

    def states(ents: dict[str, dict[str, Any]]) -> dict[str, set[str]]:
        return typegraph.close({q: _qids(e, "P31") for q, e in ents.items()})

    preds, provenance = walk_chain(qid, found, parents, entities, _inverse, states)
    drop = NOT_PREDECESSOR.get(cc, set())
    return ({q: v for q, v in preds.items() if q not in drop},
            {q: v for q, v in provenance.items() if q not in drop})


def walk_chain(qid: str, seeds: dict[str, str], parents: dict[str, str],
               entities: Any, inverse: Any, states: Any) -> tuple[dict[str, str], dict[str, str]]:
    """Walk the `replaces`/`follows` chain back from a state; see `derive_predecessors`.

    The country's own `P1365`/`P155` and `seeds` are taken as they are; the
    chain beyond them is walked in both directions (`P1365`/`P155` of a
    predecessor, and items whose `P1366`/`P156` name one), so a dynasty's
    state two changes back is found. A candidate must be a state and must
    have lasted into the PEP era. Past the country's own statements a step
    must also be *exclusive*: every successor the candidate names is already
    in the chain, which keeps out an empire several states succeeded (and its
    own long ancestry). A candidate whose span encloses another
    predecessor's is an era or a dynasty series, not a state an office
    belonged to, and is dropped. A predecessor that another one names in its
    `P17` (a federation, for one of its constituent republics) is that one's
    federation, not a predecessor of its own, and the chain is not walked
    through it. `entities`, `inverse` and `states` read Wikidata (passed in,
    so the walk is checked offline).
    """
    found = dict(seeds)
    country = entities([qid]).get(qid, {})
    for prop in PRED_PROPS:
        for v in _qids(country, prop):
            found.setdefault(v, f"wikidata {prop}")
    exclusive: set[str] = set()  # found by a step that must be exclusive
    for v in inverse(qid):
        if v not in found:
            found[v] = "wikidata P1366/P156 (inverse)"
            exclusive.add(v)
    accepted: dict[str, dict[str, Any]] = {}
    frontier = sorted(found)
    for _ in range(CHAIN_DEPTH):
        frontier = [q for q in frontier if q != qid and q not in accepted]
        if not frontier:
            break
        ents = entities(frontier)
        types = states(ents)
        level = []
        for q in frontier:
            e = ents.get(q)
            if e is None:
                continue
            dissolved = _year(e, "P576")
            # With no end recorded, the inception dates it: "Medieval Egypt" (641, no
            # end) is a period of the country's history, not a state its offices had.
            founded = _year(e, "P571")
            if not types.get(q, set()) & STATE_CLASSES or (dissolved is not None and dissolved < PEP_ERA) \
                    or (dissolved is None and founded is not None and founded < PEP_ERA):
                continue
            if q in exclusive and not set(_qids(e, "P1366") + _qids(e, "P156")) <= set(accepted) | {qid} | set(level):
                continue
            accepted[q] = e
            level.append(q)
        feds = set(parents.values()) | {v for q, e in accepted.items() for v in _qids(e, "P17")[:1] if v not in (q, qid)}
        nxt = []
        for q in level:
            if q in feds:
                continue  # a federation's other predecessors are not this country's
            steps = [(v, f"wikidata {prop} of {q}") for prop in PRED_PROPS for v in _qids(accepted[q], prop)]
            steps += [(v, f"wikidata P1366/P156 of {q} (inverse)") for v in inverse(q)]
            for v, how in steps:
                if v not in found:
                    found[v] = how
                    exclusive.add(v)
                    nxt.append(v)
        frontier = nxt
    out: dict[str, str] = {}
    for q, e in accepted.items():
        p17 = [v for v in _qids(e, "P17") if v not in (q, qid)]
        out[q] = parents.get(q) or (p17[0] if p17 else q)
    # The federation of one predecessor is not a predecessor of its own.
    for fed in {u for p, u in out.items() if u != p}:
        out.pop(fed, None)
    spans = {q: entity_span(accepted[q]) for q in out}

    def encloses(a: str, b: str) -> bool:
        (s1, e1), (s2, e2) = spans[a], spans[b]
        return None not in (s1, e1, s2, e2) and s1 <= s2 and e1 >= e2 and (s1, e1) != (s2, e2)

    for q in [q for q in out if any(encloses(q, o) for o in out if o != q)]:
        out.pop(q)
    return out, {q: found[q] for q in out}


def state_spans(qid: str, preds: dict[str, str], realm: list[str] = ()) -> dict[str, list[int | None]]:
    """When the state, its predecessors and their federations existed.

    A predecessor or federation spans its `P571`-`P576`; the state starts at
    `eras.state_start` over the whole derived chain, not only its own
    `P1365`/`P155`, which is all `eras.span_of` reads for another state.
    """
    home = [qid, *preds, *{u for p, u in preds.items() if u != p}]
    ents = wd.fetch_items(home, props="claims")
    spans = {q: entity_span(e) for q, e in ents.items()}
    succ = {x for p in preds for x in _qids(ents.get(p, {}), "P1366") + _qids(ents.get(p, {}), "P156")} - set(ents)
    found = {**ents, **(wd.fetch_items(sorted(succ), props="claims") if succ else {})}
    spans[qid] = [eras.state_start(qid, preds, found), None]
    spans.update({q: entity_span(e) for q, e in wd.fetch_items(list(realm), props="claims").items()} if realm else {})
    return spans


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
        up = typegraph.of_classes(types)
        wanted = [t for t in types if not up.get(t, set()) & {FORMER, ELECTORAL} and (
            CITY in up.get(t, set()) or (ADMIN_ENTITY in up.get(t, set()) and SETTLEMENT not in up.get(t, set())))]
        # One unit at a time: a whole chunk times out mid-answer. The types are a
        # FILTER, not VALUES: VALUES makes the planner start from the types
        # (city, town), and New South Wales' 46,000 P131 children 504 that way.
        for x in chunk:
            cand += wd.bisect(lambda ts, x=x: rows(f"""SELECT DISTINCT ?y ?t WHERE {{
              ?y wdt:P131 wd:{x} ; wdt:P31 ?t . FILTER(?t IN ({", ".join(f"wd:{t}" for t in ts)}))
              FILTER NOT EXISTS {{ ?y wdt:P576 [] }} }}"""), wanted)
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
    """The types that make up a level: a fifth of its places and at least
    `TYPE_MIN` of them, each an administrative unit or a city (never a street,
    a building, a former unit, an electoral district, a fort or a park)."""
    out = []
    for t, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        closure = up.get(t, {t})
        if closure & NOT_A_LEVEL or not (ADMIN_ENTITY in closure or CITY in closure):
            continue
        if n >= TYPE_MIN and n / max(total, 1) >= TYPE_SHARE:
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
        rest = [n for n in rest if any(len(x) >= 5 for x in words(n))]
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
        qid, *realm = REALM.get(cc, (territory.qid,))
        official = _official(cc)
        item = wd.fetch_items([qid], props="labels")[qid]
        variants = sorted(lg for lg in item.get("labels", {}) if any(lg.startswith(o + "-") for o in official))
        langs = [x for o in official for x in [o, *[v for v in variants if v.startswith(o + "-")]]]
        langs = list(dict.fromkeys([*langs, "en", "mul"]))
        preds, provenance = derive_predecessors(cc, qid)
        home = [qid, *preds, *{u for p, u in preds.items() if u != p}]
        names, local_names = home_names(home, langs)
        words_: dict[str, list[str]] = {}
        for concept, qids in CONCEPTS.items():
            if concept in LABELS_ONLY:
                ents = wd.fetch_items(qids, props="labels")
                found = [o["value"] for e in ents.values() for lg, o in e.get("labels", {}).items() if lg in langs]
            else:
                found = [n for ns in memo.names_of(qids, langs).values() for n in ns]
            words_[concept] = list(dict.fromkeys([*found, *ENGLISH[concept]]))
        admin_ent = wd.fetch_items([ADMIN_WORDS_CLASS], props="labels").get(ADMIN_WORDS_CLASS, {})
        admin = sorted(set().union(*(words(o["value"]) for lg, o in admin_ent.get("labels", {}).items()
                                     if lg in langs)) if admin_ent.get("labels") else set())
        sub = _subdivisions(qid)
        types = sub["types"]
        up = typegraph.of_classes({t for level in types.values() for t in level})
        totals = {"region": len(sub["l1"]), "district": len(sub["l2"]), "local": sum(types["local"].values())}
        lead_types = {t for level in ("region", "district", "local") for t in dominant(types[level], totals[level], up)}
        lead_types |= set(GENERIC_PLACE_TYPES)
        all_types = lead_types | {t for ts in sub["place_types"].values() for t in ts}
        type_names = memo.names_of(sorted(all_types | {LIST_CLASS}), langs)
        own = set().union(*(words(n) for n in local_names[qid])) if local_names.get(qid) else set()
        junk = {lead_word(n, own | set(admin)) for n in type_names.get(LIST_CLASS, [])}
        type_words = {}
        for t in sorted(lead_types):
            ws = {lead_word(n, own | set(admin)) for n in type_names.get(t, [])} - junk
            type_words[t] = sorted(w for w in ws if w)
        type_terms = {t: sorted(set().union(*(words(n) for n in ns)) if ns else set())
                      for t, ns in type_names.items() if t != LIST_CLASS}
        return {"cc": cc, "qid": qid, "official": list(official), "langs": langs, "predecessors": preds,
                "provenance": provenance, "names": names, "local_names": local_names, "words": words_,
                "type_words": type_words, "type_terms": type_terms, "subdivisions": sub,
                "spans": state_spans(qid, preds), "admin_words": admin, "realm": realm}

    return memo.cached(f"country6:{cc}", fetch)


_loaded: dict[str, Country] = {}


def is_state(entity: dict[str, Any]) -> bool:
    """Whether an item is typed a state: the only kind of value `P17` may hold."""
    return bool(set(_qids(entity, "P31")) & STATE_CLASSES)


def typed_state(qid: str) -> bool:
    """Whether the country itself is typed a state, rather than a dependent territory.

    An overseas territory is not part of its sovereign, so neither the sovereign
    nor the territory belongs in its offices' `P17`.
    """
    return memo.cached(f"typed_state:{qid}",
                     lambda: is_state(wd.fetch_items([qid], props="claims").get(qid, {})))


def is_name(name: str) -> bool:
    """Whether a name may be read for in a label: not a two-letter code.

    Wikidata gives every state its ISO codes as aliases, and many are words:
    "to" named Tonga in "Ambassador of the Czech Republic to Australia", and
    "in", "my" and "do" name three more states the same way. A short
    CJK name (中, 台) is a real name and stays.
    """
    n = name.strip()
    return not (len(n) <= 2 and all(ch.isalpha() and ord(ch) < 0x500 for ch in n))


def _names(by_qid: dict[str, list[str]]) -> dict[str, list[str]]:
    return {q: [n for n in ns if is_name(n)] for q, ns in by_qid.items()}


def get(cc: str) -> Country:
    """The country for a run; also makes its languages the label languages."""
    cc = cc.lower()
    if cc not in _loaded:
        wd.init()
        cfg = config(cc)
        _loaded[cc] = Country(cc=cc, qid=cfg["qid"], official=tuple(cfg["official"]), langs=tuple(cfg["langs"]),
                              predecessors=dict(cfg["predecessors"]), names=_names(cfg["names"]),
                              local_names=_names(cfg["local_names"]), words=cfg["words"],
                              type_words=cfg["type_words"], type_terms=cfg["type_terms"],
                              provenance=cfg["provenance"], admin_words=cfg["admin_words"],
                              spans=memo.cached(f"spans3:{cc}", lambda: state_spans(cfg["qid"], dict(cfg["predecessors"]),
                                                                                 cfg.get("realm", []))),
                              realm=tuple(cfg.get("realm", [])),
                              is_state=typed_state(cfg["qid"]))
    c = _loaded[cc]
    wd.set_langs(("en", *[lg for lg in c.langs if lg not in ("en", "mul")], "mul"))
    return c


# --- what a label names ------------------------------------------------------------

def _name_words(c: Country, qid: str, local: bool = False) -> list[set[str]]:
    source = c.local_names if local else c.names
    return [w for w in (words(n) for n in source.get(qid, [])) if w]


def names_country(c: Country, text: str) -> bool:
    toks = tokens(text)
    return any(has_words(w, toks) for w in _name_words(c, c.qid))


def named_states(c: Country, text: str) -> set[str]:
    """Every home state (the country, a predecessor, a federation) one of whose names the text uses.

    A state named only by a looser reading of words another state's name
    matches more tightly is not named.
    """
    toks = tokens(text)
    found = {}
    for q in c.home:
        ms = [m for m in (name_match(w, toks) for w in _name_words(c, q)) if m]
        if ms:
            found[q] = min(ms, key=lambda m: (m[0], -len(m[1])))
    return tightest(found)


def distinctive(c: Country, qid: str) -> list[set[str]]:
    """The names of a predecessor that cannot be read as the state's own name.

    A republic's "<name> SSR" is distinctive by its "SSR"; a "Republic of
    <name>" that preceded today's republic is not, and is never matched. Only
    names in the country's own languages: the long tail of foreign labels
    holds one where "Republic" is the only word that differs.
    """
    own = set().union(*_name_words(c, c.qid)) if _name_words(c, c.qid) else set()
    out = []
    for need in _name_words(c, qid, local=True):
        if any(not any(word_match(w, o) or word_match(o, w) for o in own) for w in need):
            out.append(need)
    return out


def named_predecessor(c: Country, text: str) -> str | None:
    """The predecessor a label names by one of its distinctive names, if any."""
    toks = tokens(text)
    for q in sorted(c.predecessors):
        for need in distinctive(c, q):
            if has_words(need, toks):
                return q
    return None


def level_types(c: Country, text: str) -> set[str]:
    """The subnational place types whose words a label uses ("District", "Regional"), as whole words."""
    toks = tokens(text)
    found = {t: set(c.type_words.get(t, [])) | set(c.learned_words.get(t, []))
             for t in set(c.type_words) | set(c.learned_words)}
    return {t for t, ws in found.items() if any(word_match(tok, w, ending=False) for w in ws for tok in toks)}


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
    them of one type, is that type's word. Never an "administrative" word or
    the state's own name. Only the country's languages are read: in Swedish
    the place comes first ("Victorias premiärminister"), so the word after it
    is the office's own noun, and the Prime Minister read as a state office.
    Sets `c.learned_words`.
    """
    prune_type_words(c, places)
    by_qid = {p["qid"]: p for p in places}
    own = {w for q in c.home for n in c.names.get(q, []) for w in words(n)} | set(c.admin_words)
    seen: dict[str, dict[str, set[str]]] = {}  # word → place type → offices using it
    for it in items:
        scope = _qids(it["entity"], "P1001")
        if len(scope) != 1 or scope[0] not in by_qid or not set(by_qid[scope[0]]["levels"]) & SUBNATIONAL:
            continue
        place = by_qid[scope[0]]
        # The place's own name, not its type word (an alias keeps "District").
        kinds = {w for t in place.get("types", []) for w in c.type_terms.get(t, [])}
        names = {w for need in place["words"] for w in need
                 if not any(word_match(w, k, ending=False) for k in kinds)}
        found = set()
        for o in own_language_labels(c, it["entity"]):
            toks = tokens(o)
            at = [i for i, t in enumerate(toks) if any(word_match(t, n) for n in names)]
            # the level word itself is whole: what follows the place's name verbatim
            if at and at[-1] + 1 < len(toks):
                found |= words(toks[at[-1] + 1], own)
        for w in found:
            for t in place.get("types", []):
                seen.setdefault(w, {}).setdefault(t, set()).add(it["qid"])
    learned: dict[str, set[str]] = {}
    for w, by_type in seen.items():
        total = len(set().union(*by_type.values()))
        for t, qs in by_type.items():
            if len(qs) >= LEARN_MIN and len(qs) / total >= LEARN_SHARE:
                learned.setdefault(t, set()).add(w)
    c.learned_words = {t: sorted(ws) for t, ws in learned.items()}
    # A word the state's own offices use names the state's level, not a lower one:
    # "federal" comes with "federal state of Austria", and the Federal President
    # and Chancellor read as provincial offices until it goes.
    by_office = [[tokens(o) for o in own_language_labels(c, it["entity"])]
                 for it in items if _qids(it["entity"], "P1001") == [c.qid]]

    def national_word(w: str) -> bool:
        return sum(any(word_match(t, w, ending=False) for toks in labels for t in toks)
                   for labels in by_office) >= LEARN_MIN
    c.type_words = {t: [w for w in ws if not national_word(w)] for t, ws in c.type_words.items()}
    c.learned_words = {t: [w for w in ws if not national_word(w)] for t, ws in c.learned_words.items()}
    c.learned_words = {t: ws for t, ws in c.learned_words.items() if ws}
    return c.learned_words


def own_language_labels(c: Country, entity: dict[str, Any]) -> list[str]:
    """The item's labels in the country's languages (and English, `mul`)."""
    return [o["value"] for lg, o in entity.get("labels", {}).items() if lg in ("en", *c.langs)]


def prune_type_words(c: Country, places: list[dict[str, Any]]) -> None:
    """Keep a type's words only where its own places' names use them.

    A class name may lead with a word no place carries ("administrative
    units of X" in a script whose "administrative" the admin class never
    spells): a level word is one at least one place of the type is named
    with ("Strelsau Region"). A type the gazetteer holds no place of keeps
    every word, and so does a generic city or town type.
    """
    used: dict[str, set[str]] = {}
    for p in places:
        for t in p.get("types", []):
            used.setdefault(t, set()).update(tokens(" ".join(p["names"].values())))
    # A city is named without the word "city": the generic types keep theirs.
    c.type_words = {t: ([w for w in ws if any(word_match(tok, w, ending=False) for tok in used[t])]
                        if t in used and t not in GENERIC_PLACE_TYPES else ws)
                    for t, ws in c.type_words.items()}


def label_level(c: Country, text: str) -> bool:
    """Whether a label names a level of government below the state by its words."""
    return bool(level_types(c, text))


def is_mayor(c: Country, text: str) -> bool:
    """Whether a label names a mayor (the mayor class's name, in the country's languages or English)."""
    toks = tokens(text)
    return any(has_words(words(p), toks) for p in c.words.get("mayor", []) if words(p))


def sparql_name_regex(c: Country) -> str:
    """One XPath regex for a label naming the state or a predecessor (for WDQS)."""
    parts = set()
    for name in c.local_names.get(c.qid, []):
        need = stems(name)
        if len(need) == 1:
            parts |= need
    own = set().union(*(stems(n) for n in c.names.get(c.qid, []))) if c.names.get(c.qid) else set()
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
    first- and second-level units, cities of `CITY_POPULATION` or more) is
    cached a month; `extra` adds the places the loaded offices already point
    at (their `P1001`/`P131`), as level `local` unless they are one of the
    above. A place's names are its labels and its aliases in the country's
    languages: an alias holds the former names a label still uses.
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
        alias = f"?x skos:altLabel ?l . BIND(LANG(?l) AS ?lang) FILTER(?lang IN ({lang_list}))"
        for row in wd.sparql(f"SELECT ?x ?l ?lang WHERE {{ ?x p:P31/ps:P31 wd:Q3624078 . "
                             f"FILTER NOT EXISTS {{ ?x wdt:P576 [] }} {lab} }}", max_age=30 * wd.DAY):
            add(row["x"], "country", {row["lang"]: row["l"]}, ["Q3624078"])
        sub = cfg["subdivisions"]
        cities = wd.sparql(f"""SELECT DISTINCT ?x ?t WHERE {{ ?x wdt:P17 wd:{c.qid} ; wdt:P1082 ?p .
          FILTER(?p >= {CITY_POPULATION}) ?x wdt:P31/wdt:P279* wd:{CITY} . FILTER NOT EXISTS {{ ?x wdt:P576 [] }}
          ?x wdt:P31 ?t }}""", max_age=30 * wd.DAY)
        city_types: dict[str, list[str]] = {}
        for r in cities:
            city_types.setdefault(r["x"], []).append(r["t"])
        for level, qids, types in (("region", sub["l1"], sub["place_types"]), ("district", sub["l2"], sub["place_types"]),
                                   ("local", sorted(set(city_types) - set(sub["l1"]) - set(sub["l2"])), city_types)):
            for chunk in wd.values_chunks(qids, 100):
                for shape in (lab, alias):
                    for row in wd.sparql(f"SELECT ?x ?l ?lang WHERE {{ VALUES ?x {{ {wd.values_block(chunk)} }} {shape} }}",
                                         max_age=30 * wd.DAY):
                        key = row["lang"] if shape is lab else f"{row['lang']}:{row['l']}"
                        add(row["x"], level, {key: row["l"]}, types.get(row["x"], []))
        return sorted(places.values(), key=lambda p: p["qid"])

    places = {p["qid"]: {**p, "levels": list(p["levels"])} for p in memo.cached(f"gazetteer3:{c.cc}", fetch)}
    for q in c.home:
        level = "country" if q == c.qid else ("union" if q in c.unions else "predecessor")
        places[q] = {"qid": q, "levels": [level], "types": [],
                     "names": {str(i): n for i, n in enumerate(c.names.get(q, []))}}
    wanted = sorted(set(extra or []) - set(places))
    if wanted:
        ents = {}
        for chunk in wd.values_chunks(wanted, 50):
            ents.update(memo.cached("place2:" + ",".join(c.langs) + ":" + "|".join(chunk),
                                  lambda chunk=chunk: {q: {"names": {**{lg: o["value"] for lg, o in e.get("labels", {}).items()
                                                                        if lg in c.langs},
                                                                     **{f"{lg}:{a['value']}": a["value"]
                                                                        for lg, al in e.get("aliases", {}).items()
                                                                        if lg in c.langs for a in al}},
                                                           "types": _qids(e, "P31")}
                                                       for q, e in wd.fetch_items(chunk, props="labels|aliases|claims").items()}))
        for q, e in ents.items():
            places[q] = {"qid": q, "levels": ["local"], "names": e["names"], "types": e["types"]}
    type_terms = dict(c.type_terms)
    missing = sorted({t for p in places.values() for t in p["types"]} - set(type_terms))
    for t, ns in memo.names_of(missing, c.langs).items():
        type_terms[t] = sorted(set().union(*(words(n) for n in ns))) if ns else []
    up = typegraph.of_classes({t for p in places.values() for t in p["types"]})
    out = []
    for p in places.values():
        p["classes"] = sorted(set().union(*(up.get(t, {t}) for t in p["types"]))) if p["types"] else []
        drop = set().union(*(set(type_terms.get(t, [])) for t in p["types"])) if p["types"] else set()
        if p["levels"] in (["country"], ["union"], ["predecessor"]):
            drop = set()
        # A label loses its type word ("Strelsau Region" → "Strelsau"); an alias
        # is kept whole, or "<Islam> City" would name every "Islamic" office.
        p["words"] = [sorted(w) for w in (words(n, set() if ":" in key else drop) for key, n in p["names"].items()
                                          if is_name(n)) if w]
        out.append(p)
    return sorted(out, key=lambda p: p["qid"])
