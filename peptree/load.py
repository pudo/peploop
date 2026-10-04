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

import csv
from collections import Counter
from pathlib import Path
from typing import Any, Callable

from psycopg.types.json import Jsonb

from peptree import country as countries
from peptree import wd

POSITION_METAS = {"Q4164871", "Q294414", "Q17279032"}
GENERIC_META = "Q136649946"  # type of position
LIST_ARTICLES = {"Q13406463", "Q19692233"}

#: Declared types that say the item is an honour, a rank, an award or a list.
#: A subset of peploop's NOT_AN_OFFICE plus what the pilot's baseline met.
NOT_OFFICE = {
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
#: Generic position classes (`generic_positions.csv`, one never-use class per row).
GENERIC_PATH = Path(__file__).resolve().parent / "generic_positions.csv"
#: Reached through a declared P31 (not a metaclass), these mean "a body".
BODY_ROOTS = {"Q43229", "Q495430", "Q6813432"}  # organization, general staff, military staff
DIPLOMATIC = "Q121998"
SENDER_CLASS = "Q29645880"


def generic_positions() -> dict[str, str]:
    """qid → label of every listed generic class; empty when the list is absent."""
    if not GENERIC_PATH.exists():
        return {}
    with GENERIC_PATH.open(newline="") as f:
        return {row["qid"]: row.get("label") or "" for row in csv.DictReader(f) if row.get("qid")}


def _rank_ok(claim: dict[str, Any]) -> bool:
    return claim.get("rank") != "deprecated"


def values(entity: dict[str, Any], prop: str, any_rank: bool = False) -> list[str]:
    out = []
    for claim in entity.get("claims", {}).get(prop, []):
        if not any_rank and not _rank_ok(claim):
            continue
        v = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(v, dict) and "id" in v:
            out.append(v["id"])
    return out


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
PREDECESSOR = """SELECT DISTINCT ?pos WHERE { VALUES ?r { %(r)s }
  { ?pos p:P17/ps:P17 ?r } UNION { ?pos p:P1001/ps:P1001 ?r } }"""
PREDECESSOR_UNION = """SELECT DISTINCT ?pos WHERE { ?pos p:P17/ps:P17 wd:%(u)s .
  ?pos p:P31/ps:P31/wdt:P279* wd:Q4164871 . ?pos rdfs:label ?l . FILTER(REGEX(?l, "%(re)s", "i")) }"""


def discover(c: countries.Country, log: Callable[[str], None]) -> dict[str, list[str]]:
    """Run the lanes; return each item with the lanes that found it."""
    queries = [("descent", DESCENT, {}), ("usage", USAGE, {}), ("orphan", ORPHAN, {}), ("outbound", OUTBOUND, {})]
    if c.predecessors:
        queries.append(("predecessor", PREDECESSOR, {"r": wd.values_block(sorted(c.predecessors))}))
        regex = countries.sparql_name_regex(c)
        for u in sorted(c.unions):
            if regex:
                queries.append(("predecessor_union", PREDECESSOR_UNION, {"u": u, "re": regex}))
    found: dict[str, list[str]] = {}
    for lane, query, extra in queries:
        rows = wd.sparql(query % {"c": c.qid, **extra})
        for row in rows:
            lanes = found.setdefault(row["pos"], [])
            if lane.split("_")[0] not in lanes:
                lanes.append(lane.split("_")[0])
        log(f"lane {lane}: {len(rows)}")
    return found


HOLDERS = """SELECT ?pos (COUNT(DISTINCT ?h) AS ?n) WHERE { VALUES ?pos { %s }
  ?h p:P39/ps:P39 ?pos ; wdt:P31 wd:Q5 } GROUP BY ?pos"""
HOLDER_COUNTRIES = """SELECT ?pos ?c (COUNT(DISTINCT ?h) AS ?n) WHERE { VALUES ?pos { %s }
  ?h p:P39/ps:P39 ?pos ; wdt:P31 wd:Q5 ; wdt:P27 ?c } GROUP BY ?pos ?c"""


def _grouped(query: str, qids: list[str], size: int = 60) -> list[dict[str, str]]:
    """Run a VALUES-pinned query, halving a chunk the service cannot answer."""
    out = []
    for chunk in wd.values_chunks(qids, size):
        try:
            out += wd.sparql(query % wd.values_block(chunk))
        except Exception:
            if len(chunk) == 1:
                raise
            out += _grouped(query, chunk, max(1, len(chunk) // 2))
    return out


def holders(qids: list[str]) -> tuple[dict[str, int], dict[str, dict[str, int]]]:
    total = {r["pos"]: int(r["n"]) for r in _grouped(HOLDERS, qids)}
    by: dict[str, dict[str, int]] = {}
    for r in _grouped(HOLDER_COUNTRIES, qids):
        by.setdefault(r["pos"], {})[r["c"]] = int(r["n"])
    return total, by


# --- the filter -------------------------------------------------------------------

def home_countries(c: countries.Country, by: dict[str, int]) -> int:
    """Distinct holder citizenships, counting the state and its predecessors as one."""
    return len({("home" if k in c.home else k) for k in by})


def outbound_post(c: countries.Country, entity: dict[str, Any], lanes: list[str], by: dict[str, int]) -> bool:
    """Whether the item is the state's own post abroad.

    The outbound lane says so by class. An unclassed post ("Ambassador of X
    to Turkey", no P31 or P279 at all) says so by its label: a diplomatic word
    and the state's name, no `P17` of the state (an inbound post carries the
    receiving state there), and holders, if any, mostly the state's citizens.
    """
    if "outbound" in lanes:
        return True
    if SENDER_CLASS in values(entity, "P279") and c.qid in values(entity, "P17"):
        return True  # the state's own "ambassador of <state>" class
    labels = all_labels(entity)
    if not countries.says(c.words.get("diplomatic", []), labels) or not countries.names_country(c, labels):
        return False
    if c.qid in values(entity, "P17"):
        return False
    total = sum(by.values())
    return total == 0 or sum(n for k, n in by.items() if k in c.home) / total >= 2 / 3


def classify(c: countries.Country, qid: str, entity: dict[str, Any], lanes: list[str],
             types: set[str], p31_types: set[str], by: dict[str, int],
             generic: dict[str, str] | None = None) -> tuple[str | None, str, str]:
    """Return (drop reason or None, detail, kind) for one item.

    `types` is the item's whole closure; `p31_types` the closure of its
    declared non-metaclass `P31` values (any rank) only. `generic` is the
    generic-class list (`generic_positions()`).
    """
    p31_any = set(values(entity, "P31", any_rank=True))
    p279 = set(values(entity, "P279"))
    labels = all_labels(entity)
    hit = (p31_any | p279) & NOT_OFFICE
    if hit:
        return "non_office", "declared " + ",".join(sorted(hit)), ""
    hit = p31_any & OCCUPATION
    if hit:
        return "occupation", "P31 " + ",".join(sorted(hit)), ""
    for reason, roots in NOT_A_SEAT:
        hit = p31_types & roots
        if hit:
            return reason, "P31 reaches " + ",".join(sorted(hit)), ""
    hit = p31_types & {"Q618779", "Q3320743", "Q4189293", "Q13406463"}
    if hit:
        return "non_office", "P31 reaches " + ",".join(sorted(hit)), ""
    if GENERIC_META in p31_any:
        return "generic_class", "P31 Q136649946", ""
    if generic and qid in generic:
        return "generic_class", f"listed in generic_positions.csv ({generic[qid]})", ""
    if not has(entity, "P17") and not has(entity, "P1001") and home_countries(c, by) >= 3:
        return "generic_class", f"unscoped, holders from {home_countries(c, by)} countries", ""
    hit = p31_types & BODY_ROOTS
    if hit:
        return "body", "P31 reaches " + ",".join(sorted(hit)), ""
    diplomatic = DIPLOMATIC in types or SENDER_CLASS in types
    outbound = outbound_post(c, entity, lanes, by)
    if diplomatic and not outbound:
        return "inbound_ambassador", "diplomatic, sender is not the state", ""
    scope = set(values(entity, "P17")) | set(values(entity, "P1001"))
    if outbound:
        kind = "ambassador"
    elif scope & (set(c.predecessors) | c.unions) or (
            c.qid not in scope and countries.named_predecessor(c, labels)):  # the state's own scope wins
        kind = "predecessor"
    elif set(values(entity, "P1001")) - {c.qid} or countries.label_level(c, labels):
        kind = "subnational"
    else:
        kind = "national"
    return None, "", kind


def load(cc: str, log: Callable[[str], None] = print) -> dict[str, int]:
    """Discover, fetch and store a country's items live, then filter them."""
    wd.init()
    c = countries.get(cc)
    found = discover(c, log)
    qids = sorted(found)
    log(f"union: {len(qids)} items; fetching live")
    items = wd.fetch_items(qids)
    total, by = holders(qids)
    log(f"holders read for {len(total)} items")
    rows = [(cc, q, found[q], items[q].get("lastrevid"), Jsonb(items[q]), total.get(q, 0), Jsonb(by.get(q, {})))
            for q in qids if q in items]
    con = wd.conn()
    with con.transaction():
        con.execute("DELETE FROM ptree_item WHERE country = %s", (cc,))
        with con.cursor() as cur:
            cur.executemany(
                "INSERT INTO ptree_item (country, qid, lanes, lastrevid, entity, holders, holder_countries)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s)", rows)
    log(f"stored {len(rows)} ({len(qids) - len(rows)} missing or deleted)")
    return refilter(cc, log)


def refilter(cc: str, log: Callable[[str], None] = print) -> dict[str, int]:
    """Run the filter over the stored items again (no live reads but the class edges)."""
    c = countries.get(cc)
    stored = items(cc, kept_only=False)
    seeds = {it["qid"]: _seed_edges(it["entity"]) for it in stored}
    types = wd.closure(seeds)
    p31_types = wd.closure({f"p31:{it['qid']}": [t for t in values(it["entity"], "P31", any_rank=True)
                                                  if t not in POSITION_METAS] for it in stored})
    generic = generic_positions()
    log(f"generic classes listed: {len(generic)}")
    learn(c, stored)
    tally: Counter[str] = Counter()
    rows = []
    for it in stored:
        q = it["qid"]
        drop, detail, kind = classify(c, q, it["entity"], it["lanes"], types[q],
                                      p31_types[f"p31:{q}"] - {f"p31:{q}"}, it["holder_countries"], generic)
        tally[drop or "kept"] += 1
        rows.append((kind or None, drop, detail or None, cc, q))
    with wd.conn().cursor() as cur:
        cur.executemany("UPDATE ptree_item SET kind = %s, dropped = %s, drop_detail = %s"
                        " WHERE country = %s AND qid = %s", rows)
    log(f"filtered: {dict(tally)}")
    return dict(tally)


def learn(c: countries.Country, stored: list[dict[str, Any]]) -> None:
    """Learn the level words from the offices that already name their place."""
    places = countries.gazetteer(c, place_refs(stored))
    countries.learn_level_words(c, stored, places)


def place_refs(items: list[dict[str, Any]]) -> list[str]:
    """The places the loaded offices already point at: local jurisdictions for the gazetteer."""
    return sorted({v for it in items for p in ("P1001", "P131") for v in values(it["entity"], p, any_rank=True)})


def _seed_edges(entity: dict[str, Any]) -> list[str]:
    return values(entity, "P31") + values(entity, "P279")


def items(cc: str, kept_only: bool = True) -> list[dict[str, Any]]:
    """The stored items of a country, as dicts."""
    wd.init()
    cur = wd.conn().execute(
        "SELECT qid, lanes, lastrevid, entity, holders, holder_countries, kind, dropped, drop_detail"
        " FROM ptree_item WHERE country = %s" + (" AND dropped IS NULL" if kept_only else "") + " ORDER BY qid",
        (cc,))
    cols = [d.name for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]
