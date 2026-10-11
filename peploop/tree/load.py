"""Load one country's position items, and drop what is not an office.

Five discovery lanes, unioned:

- descent: typed into the position tree, scoped `P17`/`P1001` to the state;
- usage: scoped to the state and held by someone, typed or not;
- orphan: held by a citizen and scoped to nothing at all;
- outbound: the state's own posts abroad (the "ambassador of <state>" class);
- predecessor: scoped to a predecessor state, or to its federation and naming
  the country (the country's data says which states those are).

Every dropped item keeps its reason. The filter reads *declared* types and a
closure over them: the hierarchy is polluted, so a `P279*` walk alone never
decides that something is an office.
"""

import re
from collections import Counter
from typing import Any, Callable

import requests
from psycopg.types.json import Jsonb

from peploop import memo, positions, typegraph
from peploop.tree import country as countries
from peploop.tree import wd

POSITION_METAS = {"Q4164871", "Q294414", "Q17279032"}
GENERIC_META = "Q136649946"  # type of position
LIST_ARTICLES = {"Q13406463", "Q19692233"}

#: Declared types that say the item is an honour, a rank, an award or a list.
#: A subset of peploop's NOT_AN_OFFICE plus what the pilot's baseline met.
NOT_OFFICE = {
    "Q5",  # human: "oldest living person in Finland" is a subclass of people, not a seat
    "Q3320743",  # title of honor
    "Q13424289",  # honorary title
    "Q618779",  # award
    "Q4192699",  # badge of distinction
    "Q1499804",  # grade of an order
    "Q38593919",  # medal of an order
    "Q799000",  # breast badge
    "Q4189293",  # rank
    "Q56019",  # military rank
    "Q4226220",  # naval officer rank
    "Q19476593",  # police rank
    "Q303618",  # diplomatic rank
    "Q486983",  # academic rank
    "Q3529618",  # academic title
    "Q4121104",  # sports title
    "Q55956975",  # honorary sporting title
    "Q414528",  # academician
    "Q2625729",  # corresponding member
    *LIST_ARTICLES,
}
#: A seat whose class reaches head of state, or that is declared a public office,
#: is an office whatever else its `P31` reaches: a throne is typed "noble title"
#: (→ rank), a presidency "President of the Republic" (→ organization), a vice
#: presidency carries a stray "Wikimedia list" (→ written work). The closure
#: drops took the King of Jordan, the President of Namibia and the Prime
#: Minister of Seychelles; what an item declares directly still drops it.
HEAD_OF_STATE = "Q48352"
PUBLIC_OFFICE = "Q294414"
#: Declared directly (`p:P31/ps:P31`, any rank): the item is an occupation,
#: not a seat. Not through the closure: "member of parliament" is itself typed
#: an occupation, so every MP seat reaches it.
OCCUPATION = {"Q12737077", "Q28640"}  # occupation, profession
#: Reached through the closure of a declared non-metaclass P31: the item is a
#: thing, not an office. (reason, roots); first match wins.
NOT_A_SEAT: list[tuple[str, set[str]]] = [
    ("place", {"Q56061", "Q486972", "Q618123", "Q2221906"}),  # admin unit, settlement, geographic feature/location
    ("legal_case", {"Q2334719", "Q83267"}),  # legal case, crime
    ("estate", {"Q12292478"}),
    ("non_office", {"Q1656682", "Q47461344", "Q49848", "Q14660", "Q14659"}),  # event, written work, document, flag, arms
]
#: Occurrence (coups, accidents, trials, crafts and techniques), time interval
#: (historical periods), product. Read over a closure that stops at
#: occupation and position (`event_closure`): "occupation" is itself a
#: characterization, an action and so an occurrence, so every mufti and dean
#: reaches it, while a handicraft reaches "position" by its own route.
EVENT_LIKE = {"Q1190554", "Q186081", "Q2424752"}
EVENT_STOP = {"Q12737077", "Q28640", "Q4164871", "Q294414", "Q17279032", "Q136649946"}
#: Reached through a declared P31 (not a metaclass), these mean "a body".
BODY_ROOTS = {"Q43229", "Q495430", "Q6813432"}  # organization, general staff, military staff
DIPLOMATIC = "Q121998"
SENDER_CLASS = "Q29645880"
CONSULAR = {"Q207978", "Q1075179", "Q107427486"}  # consul, honorary consul, honorary consul to a country
#: A body of one of these kinds is private unless it is also one of `STATE_BODY`
#: or owned (`P127`) by the state: its offices are no one's public office.
#: Not companies: a state bank or a pension fund's holding is typed "public
#: company" or "business" and rarely says who owns it, and its head is a PEP.
PRIVATE_BODY = {"Q988108", "Q79913"}  # club, NGO
#: SOE, party, agency, government organisation, central bank, university, academy of sciences
#: (an academy is a "learned society", hence a club, by the hierarchy).
STATE_BODY = {"Q270791", "Q7278", "Q327333", "Q2659904", "Q66344", "Q3918", "Q414147"}
#: A `P1001` value of one of these kinds is a territory: anything else (a
#: ministry, a corps, a party) says nothing about the office's level.
TERRITORY = {"Q56061", "Q486972", "Q515", "Q7275", "Q6256", "Q3024240", "Q82794", "Q1048835"}
CITY = "Q515"


def values(entity: dict[str, Any], prop: str, any_rank: bool = False) -> list[str]:
    """Item-valued targets of `prop`, deprecated ones only with `any_rank`."""
    return wd.claim_qids(entity, prop, include_deprecated=any_rank)


def has(entity: dict[str, Any], prop: str) -> bool:
    """Whether any statement for `prop` exists, at any rank, novalue included."""
    return bool(entity.get("claims", {}).get(prop))


def all_labels(entity: dict[str, Any]) -> str:
    return " | ".join(o["value"] for o in entity.get("labels", {}).values())


# --- discovery ------------------------------------------------------------------

DESCENT = """SELECT DISTINCT ?pos WHERE { ?pos p:P31/ps:P31/wdt:P279* wd:Q4164871 .
  { ?pos p:P17/ps:P17 wd:%(c)s } UNION { ?pos p:P1001/ps:P1001 wd:%(c)s } }"""
USAGE = """SELECT DISTINCT ?pos WHERE { { ?pos p:P17/ps:P17 wd:%(c)s } UNION { ?pos p:P1001/ps:P1001 wd:%(c)s }
  ?h wdt:P31 wd:Q5 ; p:P39/ps:P39 ?pos }"""
ORPHAN = """SELECT DISTINCT ?pos WHERE { ?h wdt:P27 wd:%(c)s ; wdt:P31 wd:Q5 ; p:P39/ps:P39 ?pos .
  FILTER NOT EXISTS { ?pos p:P17 [] } FILTER NOT EXISTS { ?pos p:P1001 [] } }"""
OUTBOUND = """SELECT DISTINCT ?pos WHERE { ?cls wdt:P279 wd:Q29645880 ; wdt:P17 wd:%(c)s .
  { ?pos p:P279/ps:P279 ?cls } UNION { ?pos p:P31/ps:P31 ?cls } }"""
#: Two simple shapes: a predecessor's own scope, and the federation's offices
#: whose label names the country. One query with both and a typed-or-held join 504s.
#: A predecessor's scope is read three times, once per shape the filter keeps:
#: typed a position, a subclass of one, or held. Unfiltered, Austria-Hungary's
#: scope is 27,380 villages, newspapers and censuses around 129 offices.
PREDECESSOR = """SELECT DISTINCT ?pos WHERE { VALUES ?r { %(r)s }
  { ?pos p:P17/ps:P17 ?r } UNION { ?pos p:P1001/ps:P1001 ?r } %(shape)s }"""
PREDECESSOR_SHAPES = ("?pos p:P31/ps:P31/wdt:P279* wd:Q4164871 .",
                      "?pos p:P279/ps:P279/wdt:P279* wd:Q4164871 .",
                      "?h p:P39/ps:P39 ?pos .")
PREDECESSOR_UNION = """SELECT DISTINCT ?pos WHERE { ?pos p:P17/ps:P17 wd:%(u)s .
  ?pos p:P31/ps:P31/wdt:P279* wd:Q4164871 . ?pos rdfs:label ?l . FILTER(REGEX(?l, "%(re)s", "i")) }"""


ITEM = re.compile(r"Q\d+")


def discover(c: countries.Country, log: Callable[[str], None]) -> dict[str, list[str]]:
    """Run the lanes; return each item with the lanes that found it."""
    queries = [(lane, q, {"c": state}) for state in (c.qid, *c.realm)
               for lane, q in (("descent", DESCENT), ("usage", USAGE), ("orphan", ORPHAN), ("outbound", OUTBOUND))]
    if c.predecessors:
        for shape in PREDECESSOR_SHAPES:
            queries.append(("predecessor", PREDECESSOR, {"r": wd.values_block(sorted(c.predecessors)), "shape": shape}))
        regex = countries.sparql_name_regex(c)
        for u in sorted(c.unions):
            if regex:
                queries.append(("predecessor_union", PREDECESSOR_UNION, {"u": u, "re": regex}))
    found: dict[str, list[str]] = {}
    for lane, query, extra in queries:
        rows = wd.sparql(query % {"c": c.qid, **extra})
        skipped = [r["pos"] for r in rows if not ITEM.fullmatch(r["pos"])]
        if skipped:  # a somevalue P39 binds a blank node, which no query can pin
            log(f"lane {lane}: skipped {len(skipped)} non-item values")
        for row in rows:
            if not ITEM.fullmatch(row["pos"]):
                continue
            lanes = found.setdefault(row["pos"], [])
            if lane.split("_")[0] not in lanes:
                lanes.append(lane.split("_")[0])
        log(f"lane {lane}: {len(rows)}")
    return found


HOLDERS = """SELECT ?pos (COUNT(DISTINCT ?h) AS ?n) WHERE { VALUES ?pos { %s }
  ?h p:P39/ps:P39 ?pos ; wdt:P31 wd:Q5 } GROUP BY ?pos"""
HOLDER_COUNTRIES = """SELECT ?pos ?c (COUNT(DISTINCT ?h) AS ?n) WHERE { VALUES ?pos { %s }
  ?h p:P39/ps:P39 ?pos ; wdt:P31 wd:Q5 ; wdt:P27 ?c } GROUP BY ?pos ?c"""
#: One row per holder: the tenure's bounds and the life's, for the era rule.
HOLDER_DATES = """SELECT ?pos ?h (MIN(?s) AS ?s0) (MAX(?e) AS ?e0) (MIN(?b) AS ?b0) (MAX(?d) AS ?d0) WHERE {
  VALUES ?pos { %s } ?h p:P39 ?st . ?st ps:P39 ?pos . ?h wdt:P31 wd:Q5 .
  OPTIONAL { ?st pq:P580 ?s } OPTIONAL { ?st pq:P582 ?e } OPTIONAL { ?h wdt:P569 ?b } OPTIONAL { ?h wdt:P570 ?d }
  } GROUP BY ?pos ?h"""
HOLDER_CITIZENSHIP = """SELECT DISTINCT ?pos ?h ?c WHERE { VALUES ?pos { %s }
  ?h p:P39/ps:P39 ?pos ; wdt:P31 wd:Q5 ; wdt:P27 ?c }"""


def _grouped(query: str, qids: list[str], size: int = 60) -> list[dict[str, str]]:
    """Run a VALUES-pinned query in chunks of `size`, halving a chunk the service cannot answer."""
    return wd.bisect(lambda chunk: wd.sparql(query % wd.values_block(chunk)), qids, size)


def holders(qids: list[str]) -> tuple[dict[str, int], dict[str, dict[str, int]], dict[str, list[dict[str, Any]]]]:
    """(holder count, holders per citizenship, one row per holder) of each office.

    A row is `{"h", "s", "e", "b", "d", "c"}`: the first tenure start and last
    tenure end, birth and death years, and the citizenships.
    """
    total = {r["pos"]: int(r["n"]) for r in _grouped(HOLDERS, qids)}
    by: dict[str, dict[str, int]] = {}
    for r in _grouped(HOLDER_COUNTRIES, qids):
        by.setdefault(r["pos"], {})[r["c"]] = int(r["n"])
    cit: dict[tuple[str, str], list[str]] = {}
    for r in _grouped(HOLDER_CITIZENSHIP, qids):
        cit.setdefault((r["pos"], r["h"]), []).append(r["c"])
    rows: dict[str, list[dict[str, Any]]] = {}
    for r in _grouped(HOLDER_DATES, qids):
        if not ITEM.fullmatch(r["h"]):
            continue
        y = countries.time_year
        rows.setdefault(r["pos"], []).append({
            "h": r["h"], "s": y(r.get("s0")), "e": y(r.get("e0")), "b": y(r.get("b0")), "d": y(r.get("d0")),
            "c": sorted(cit.get((r["pos"], r["h"]), []))})
    for v in rows.values():
        v.sort(key=lambda x: x["h"])
    return total, by, rows


# --- the filter -------------------------------------------------------------------

def home_countries(c: countries.Country, by: dict[str, int]) -> int:
    """Distinct holder citizenships, counting the state and its predecessors as one."""
    return len({("home" if k in c.home else k) for k in by})


def outbound_post(c: countries.Country, entity: dict[str, Any], lanes: list[str], by: dict[str, int]) -> bool:
    """Whether the item is the state's own post abroad.

    The outbound lane says so by class. An unclassed post ("Ambassador of X
    to Turkey", no P31 or P279 at all) says so by its label: a diplomatic or
    consular word and the state's name, no `P17` of the state (an inbound
    post carries the receiving state there), and holders, if any, mostly the
    state's citizens.
    """
    if "outbound" in lanes:
        return True
    if SENDER_CLASS in values(entity, "P279") and c.qid in values(entity, "P17"):
        return True  # the state's own "ambassador of <state>" class
    labels = all_labels(entity)
    if not (countries.says(c.words.get("diplomatic", []), labels) or consular_label(c, labels)) \
            or not countries.names_country(c, labels):
        return False
    # An inbound post carries the receiving state in P17; a mission to the UN or
    # UNESCO has no receiving state, so its P17 is the sender's own.
    if c.qid in values(entity, "P17") and not countries.says(c.words.get("mission", []), labels):
        return False
    total = sum(by.values())
    return total == 0 or sum(n for k, n in by.items() if k in c.home) / total >= 2 / 3


def consular_label(c: countries.Country, labels: str) -> bool:
    """Whether a label leads with a consul's title ("Consul General of X in Y", "honorary consul to X")."""
    return any(countries.leads_with(c.words.get("consular", []), part) for part in labels.split(" | "))


def body_label(c: countries.Country, entity: dict[str, Any]) -> str | None:
    """The label, in English or the country's languages, that leads with a body's name ("Office of …")."""
    for lg in dict.fromkeys(("en", *c.langs)):
        text = entity.get("labels", {}).get(lg, {}).get("value")
        if text and countries.leads_with(c.words.get("body", []), text):
            return text
    return None


def private_body(entity: dict[str, Any], bodies: dict[str, dict[str, Any]], home: set[str]) -> str | None:
    """The body (`P361`/`P2389`) that makes the office a private one: a club, a
    company or an NGO that is neither a state body nor owned by the state."""
    for b in values(entity, "P361") + values(entity, "P2389"):
        info = bodies.get(b)
        if not info:
            continue
        types = set(info["types"])
        if types & PRIVATE_BODY and not types & STATE_BODY and not set(info.get("owners", [])) & home:
            return b
    return None


def classify(c: countries.Country, qid: str, entity: dict[str, Any], lanes: list[str],
             types: set[str], p31_types: set[str], by: dict[str, int],
             generic: dict[str, str] | None = None, holders: int | None = None,
             bodies: dict[str, dict[str, Any]] | None = None, territorial: set[str] | None = None,
             cities: list[dict[str, Any]] | None = None,
             event_types: set[str] | None = None, inside: set[str] | None = None) -> tuple[str | None, str, str]:
    """Return (drop reason or None, detail, kind) for one item.

    `types` is the item's whole closure; `p31_types` the closure of its
    declared non-metaclass `P31` values (any rank) only. `generic` is the
    generic-class list (`positions.GENERIC_LABELS`). `holders` is the item's holder
    count (from `by` when not given); `bodies` maps the body QIDs it names to
    their types and owners; `territorial` is the set of its `P1001` values
    that are territories (all of them when not given); `cities` the
    gazetteer's city places; `event_types` the closure of the declared
    non-metaclass `P31` that stops at occupation and position (`p31_types`
    when not given); `inside` the states and places that are the country's
    (`inside_places()`), without which no item is dropped as scoped elsewhere.
    """
    p31_any = set(values(entity, "P31", any_rank=True))
    p279 = set(values(entity, "P279"))
    labels = all_labels(entity)
    held = sum(by.values()) if holders is None else holders
    hit = (p31_any | p279) & NOT_OFFICE
    if hit:
        return "non_office", "declared " + ",".join(sorted(hit)), ""
    hit = p31_any & OCCUPATION
    if hit:
        return "occupation", "P31 " + ",".join(sorted(hit)), ""
    seat = HEAD_OF_STATE in types or PUBLIC_OFFICE in p31_any
    for reason, roots in NOT_A_SEAT:
        hit = p31_types & roots
        if hit and not seat:
            return reason, "P31 reaches " + ",".join(sorted(hit)), ""
    hit = p31_types & {"Q618779", "Q3320743", "Q4189293", "Q13406463"}
    if hit and not seat:
        return "non_office", "P31 reaches " + ",".join(sorted(hit)), ""
    hit = (p31_types if event_types is None else event_types) & EVENT_LIKE
    if hit and not seat:
        return "non_office", "P31 reaches " + ",".join(sorted(hit)) + " (not through occupation)", ""
    # A label naming the state or a predecessor is a country-scoped office,
    # whatever its holders' spread or a list says.
    scoped_label = countries.names_country(c, labels) or bool(countries.named_states(c, labels))
    if GENERIC_META in p31_any:
        return "generic_class", "P31 Q136649946", ""
    if generic and qid in generic and not scoped_label:
        return "generic_class", f"listed in generic_positions.csv ({generic[qid]})", ""
    if not has(entity, "P17") and not has(entity, "P1001") and home_countries(c, by) >= 3 and not scoped_label:
        return "generic_class", f"unscoped, holders from {home_countries(c, by)} countries", ""
    hit = p31_types & BODY_ROOTS
    if hit and not seat:
        return "body", "P31 reaches " + ",".join(sorted(hit)), ""
    lead = body_label(c, entity)
    if lead:
        return "body", f"label leads with a body's name: {lead}", ""
    private = private_body(entity, bodies or {}, c.home)
    if private:
        return "private_body", f"office of {private}, a private body", ""
    if set(lanes) <= {"predecessor"} and not held and not (types | p31_any) & POSITION_METAS:
        return "non_office", "predecessor scope only, held by no one and not typed a position", ""
    diplomatic = DIPLOMATIC in types or SENDER_CLASS in types
    consular = bool(CONSULAR & types) or consular_label(c, labels)
    outbound = outbound_post(c, entity, lanes, by)
    if diplomatic and not outbound:
        return "inbound_ambassador", "diplomatic, sender is not the state", ""
    if consular and not outbound:
        return "inbound_consul", "consular, sender is not the state", ""
    scope = set(values(entity, "P17")) | set(values(entity, "P1001"))
    # The citizenship lane brings in another country's offices: "Mayor of Peshawar"
    # under India, a Venezuelan ministry under Argentina. An office whose own scope
    # names only other states and their places is theirs; an unscoped one stays.
    if inside is not None and scope and not outbound and not scope & inside:
        return "scoped_elsewhere", "P17/P1001 " + ",".join(sorted(scope)), ""
    p1001 = set(values(entity, "P1001"))
    local = p1001 - {c.qid} if territorial is None else (p1001 & territorial) - {c.qid}
    if outbound:
        kind = "ambassador"
    # The state's own scope wins: Prime Minister of Slovakia names Czechoslovakia
    # for 1969-1992 beside Slovakia, and is the state's office, not a predecessor's.
    elif c.qid not in scope and (scope & (set(c.predecessors) | c.unions) or countries.named_predecessor(c, labels)):
        kind = "predecessor"
    elif local - c.home or countries.label_level(c, labels) or countries.is_mayor(c, labels) \
            or names_city(c, own_labels(c, entity), cities or []):
        kind = "subnational"
    else:
        kind = "national"
    return None, "", kind


def own_labels(c: countries.Country, entity: dict[str, Any]) -> str:
    """The labels in English and the country's languages (a city's name is read in these only)."""
    return " | ".join(o["value"] for lg, o in entity.get("labels", {}).items() if lg in ("en", *c.langs))


def names_city(c: countries.Country, labels: str, cities: list[dict[str, Any]]) -> bool:
    """Whether a label names one of the country's cities and not the state ("äkim of <city>")."""
    if countries.names_country(c, labels):
        return False
    return any(countries.mentions(p, labels) for p in cities)


def load(cc: str, log: Callable[[str], None] = print) -> dict[str, int]:
    """Discover, fetch and store a country's items live, then filter them."""
    wd.init()
    c = countries.get(cc)
    found = discover(c, log)
    qids = sorted(found)
    log(f"union: {len(qids)} items; fetching live")
    items = wd.fetch_items(qids)
    total, by, dated = holders(qids)
    log(f"holders read for {len(total)} items")
    rows = [(cc, q, found[q], items[q].get("lastrevid"), Jsonb(items[q]), total.get(q, 0), Jsonb(by.get(q, {})),
             Jsonb(dated.get(q, [])))
            for q in qids if q in items]
    con = wd.conn()
    with con.transaction():
        con.execute("DELETE FROM ptree_item WHERE country = %s", (cc,))
        with con.cursor() as cur:
            cur.executemany(
                "INSERT INTO ptree_item (country, qid, lanes, lastrevid, entity, holders, holder_countries, holder_rows)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", rows)
    log(f"stored {len(rows)} ({len(qids) - len(rows)} missing or deleted)")
    return refilter(cc, log)


def refilter(cc: str, log: Callable[[str], None] = print) -> dict[str, int]:
    """Run the filter over the stored items again (no live reads but the class edges)."""
    c = countries.get(cc)
    stored = items(cc, kept_only=False)
    seeds = {it["qid"]: _seed_edges(it["entity"]) for it in stored}
    types = typegraph.close(seeds)
    p31_seeds = {f"p31:{it['qid']}": [t for t in values(it["entity"], "P31", any_rank=True)
                                      if t not in POSITION_METAS] for it in stored}
    p31_types = typegraph.close(p31_seeds)
    events = event_closure(p31_seeds)
    generic = positions.GENERIC_LABELS
    log(f"generic classes listed: {len(generic)}")
    places = learn(c, stored)
    cities = [p for p in places if CITY in p.get("classes", []) and set(p["levels"]) & countries.SUBNATIONAL]
    bodies = body_info(stored)
    scopes = sorted({v for it in stored for v in values(it["entity"], "P1001")})
    scope_types = typegraph.close(_cached_edges(scopes)) if scopes else {}
    territorial = {q for q, ts in scope_types.items() if ts & TERRITORY} | c.home
    inside = inside_places(c, stored)
    tally: Counter[str] = Counter()
    rows = []
    for it in stored:
        q = it["qid"]
        drop, detail, kind = classify(c, q, it["entity"], it["lanes"], types[q],
                                      p31_types[f"p31:{q}"] - {f"p31:{q}"}, it["holder_countries"], generic,
                                      holders=it["holders"], bodies=bodies, territorial=territorial, cities=cities,
                                      event_types=events[f"p31:{q}"], inside=inside)
        tally[drop or "kept"] += 1
        rows.append((kind or None, drop, detail or None, cc, q))
    with wd.conn().cursor() as cur:
        cur.executemany("UPDATE ptree_item SET kind = %s, dropped = %s, drop_detail = %s"
                        " WHERE country = %s AND qid = %s", rows)
    log(f"filtered: {dict(tally)}")
    return dict(tally)


def event_closure(seeds: dict[str, list[str]], depth: int = 8) -> dict[str, set[str]]:
    """Each seed's types over `P31`/`P279`, never walking on from occupation or position."""
    edges: dict[str, list[str]] = {}
    out = {}
    for key, start in seeds.items():
        seen, level = set(start), list(start)
        for _ in range(depth):
            todo = sorted({t for t in level if t not in edges and t not in EVENT_STOP})
            if todo:
                edges.update(typegraph.edges(todo))
            level = [y for x in level if x not in EVENT_STOP for y in edges.get(x, []) if y not in seen]
            seen.update(level)
            if not level:
                break
        out[key] = seen
    return out


def inside_places(c: countries.Country, stored: list[dict[str, Any]]) -> set[str]:
    """The states and places that are this country's, for the `scoped_elsewhere` drop.

    The home states, the fixed gazetteer's subdivisions and cities (not the
    sovereign states it also lists), and any `P17`/`P1001` value the stored
    offices name whose own `P17` is a home state or whose `P131` is one of
    those places. The gazetteer's own extras cannot answer this: it adds every
    place an office points at, Peshawar included.
    """
    fixed = {p["qid"] for p in countries.gazetteer(c) if p["levels"] != ["country"]}
    inside = set(c.home) | fixed
    scopes = sorted({v for it in stored for p in ("P17", "P1001") for v in values(it["entity"], p)} - inside)
    for chunk in wd.values_chunks(scopes, 50):
        found = memo.cached("scope_up:" + "|".join(chunk), lambda chunk=chunk: _scope_up(chunk))
        inside |= {q for q, up in found.items() if set(up["P17"]) & c.home or set(up["P131"]) & inside}
    return inside


def _scope_up(qids: list[str]) -> dict[str, dict[str, list[str]]]:
    """`P17` and `P131` of each place, halving a request whose response is cut off.

    Fifty places can include Jerusalem, Israel and the West Bank, whose claims
    together outgrow what the API finishes sending: the same chunk fails every time.
    """
    try:
        return {q: {"P17": values(e, "P17"), "P131": values(e, "P131")}
                for q, e in wd.fetch_items(qids, props="claims").items()}
    except requests.exceptions.ChunkedEncodingError:
        if len(qids) == 1:
            raise
        half = len(qids) // 2
        return {**_scope_up(qids[:half]), **_scope_up(qids[half:])}


def _cached_edges(qids: list[str]) -> dict[str, list[str]]:
    """`P31`/`P279` edges of referenced items (bodies, jurisdictions), cached like class edges."""
    return typegraph.edges(qids)


def body_info(stored: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Body QID → its type closure and owners (`P127`), for the private-body rule (cached a month)."""
    bodies = sorted({b for it in stored for b in values(it["entity"], "P361") + values(it["entity"], "P2389")})
    if not bodies:
        return {}
    owners: dict[str, list[str]] = {}
    for chunk in wd.values_chunks(bodies, 50):
        owners.update(memo.cached("owners:" + "|".join(chunk), lambda chunk=chunk: {
            q: values(e, "P127") for q, e in wd.fetch_items(chunk, props="claims").items()}))
    closure = typegraph.close(_cached_edges(bodies))
    return {b: {"types": sorted(closure.get(b, {b})), "owners": owners.get(b, [])} for b in bodies}


def learn(c: countries.Country, stored: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Learn the level words from the offices that already name their place; return the gazetteer."""
    places = countries.gazetteer(c, place_refs(stored))
    countries.learn_level_words(c, stored, places)
    return places


def place_refs(items: list[dict[str, Any]]) -> list[str]:
    """The places the loaded offices already point at: local jurisdictions for the gazetteer."""
    return sorted({v for it in items for p in ("P1001", "P131") for v in values(it["entity"], p, any_rank=True)})


def _seed_edges(entity: dict[str, Any]) -> list[str]:
    return values(entity, "P31") + values(entity, "P279")


def items(cc: str, kept_only: bool = True) -> list[dict[str, Any]]:
    """The stored items of a country, as dicts."""
    wd.init()
    cur = wd.conn().execute(
        "SELECT qid, lanes, lastrevid, entity, holders, holder_countries, holder_rows, kind, dropped, drop_detail"
        " FROM ptree_item WHERE country = %s" + (" AND dropped IS NULL" if kept_only else "") + " ORDER BY qid",
        (cc,))
    cols = [d.name for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]
