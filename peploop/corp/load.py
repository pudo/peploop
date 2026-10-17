"""Find a country's candidate state bodies and keep the ones worth a decision.

Six lanes, each going wide on purpose: what the decision stage and, after
it, OpenSanctions' position classification filter out costs less than a body
never found.

- `typed`: the item is a state-owned enterprise by `P31` or `P1454` (legal
  form), through any subclass of `Q270791`, and `P17` is the country.
- `formed`: its `P31` or `P1454` is one of the country's state-only legal
  forms (the spec's `forms`), matched exactly: an authority, a public-law
  institution or foundation, which carries no SOE marker and often no owner.
- `owned`: a chain of `P127` or `P749` links reaches a state actor
  (`actors.py`).
- `parented`: its parent organization is a state actor: a body a ministry or
  a government runs.
- `category`: a Wikipedia category for the country's state enterprises or
  government agencies lists it; the category is found through Wikidata
  (`P971` combining the class with the country), so the lane needs no
  country's names, and reaches bodies with no links on Wikidata at all;
- `seed`: an official list of holdings (the spec's `holdings`) names it;
  this is what finds a body neither Wikidata nor Wikipedia records as state.

Only the municipal tier's marker (`Q1780371`) stays out of the typed lane for
now: municipal enterprises are a later tier.
"""

from typing import Any, Callable

from psycopg.types.json import Jsonb
from rigour.langs import iso_639_alpha2
from rigour.territories import get_territory_by_qid

from peploop import positions, typegraph, wikipedia
from peploop.corp import actors as actormod
from peploop.corp import country as countries
from peploop.corp import wd

#: The markers whose subclass trees the typed lane reads.
TYPED_ROOTS = ("Q270791",)
TYPED = """SELECT DISTINCT ?i WHERE { ?c wdt:P279* wd:%s . { ?i wdt:P31 ?c } UNION { ?i wdt:P1454 ?c } ?i wdt:P17 wd:%s . }"""
#: Classes that are never a candidate, in any country: their leaders are
#: peploop's (officers, ambassadors, judges, mayors, ministers), they are no body at all,
#: or they are sports clubs, whose boards are no state function even when a
#: state enterprise owns the club. A country adds its own in its spec (`exclude`).
EXCLUDED = frozenset({
    "Q176799",  # military unit
    "Q3917681",  # embassy
    "Q7843791",  # diplomatic mission
    "Q41487",  # court
    "Q56061",  # administrative territorial entity
    "Q476028",  # association football club
    "Q847017",  # sports club
    "Q192350",  # ministry
    "Q7188",  # government
})
#: The classes whose country categories the category lane reads.
CATEGORY_TOPICS = ("Q270791", "Q327333")  # state-owned enterprise, government agency
CATEGORIES = """SELECT DISTINCT ?cat WHERE { VALUES ?x { %s } ?cat wdt:P31 wd:Q4167836 ; wdt:P971 wd:%s ; wdt:P971 ?x . }"""
FORMED = """SELECT DISTINCT ?i WHERE { VALUES ?f { %s } { ?i wdt:P31 ?f } UNION { ?i wdt:P1454 ?f } ?i wdt:P17 wd:%s . }"""


#: Wikipedias whose code is not the label language Wikidata uses for them.
LABEL_LANGS = {"no": "nb", "simple": "en", "be-tarask": "be"}


def label_langs(wikis: list[str]) -> tuple[str, ...]:
    """The label languages for these wikis, best first, with `mul` and English to fall back on."""
    return tuple(dict.fromkeys([*(LABEL_LANGS.get(w, w) for w in wikis), "mul", "en"]))


def langs(state: str) -> list[str]:
    """The languages whose articles a decision reads: the state's own, then English."""
    territory = get_territory_by_qid(state)
    own = [iso_639_alpha2(lang) for lang in (territory.langs if territory else [])]
    return list(dict.fromkeys([*(lang for lang in own if lang), "en"]))


def categorised(state: str, wikis: list[str]) -> set[str]:
    """The items the country's state-enterprise and agency categories list, one level down, in these wikis."""
    cats = [r["cat"] for r in wd.sparql(CATEGORIES % (wd.values_block(CATEGORY_TOPICS), state))]
    found: set[str] = set()
    for cat, ent in wd.fetch_items(cats, props="sitelinks").items():
        for lang in wikis:
            site = ent.get("sitelinks", {}).get(f"{lang}wiki")
            if site is None:
                continue
            title = site["title"].split(":", 1)[-1]
            found.update(q for _, q in wikipedia.walk_category(title, lang, 1))
    return found


def classify(entity: dict[str, Any] | None, organisation: bool, wikis: list[str]) -> str | None:
    """Why a candidate is dropped, or None to keep it."""
    if entity is None:
        return "missing"
    if wd.values(entity, "P576"):
        return "dissolved"
    if not organisation:
        return "not_organisation"
    links = entity.get("sitelinks", {})
    if not any(f"{lang}wiki" in links for lang in wikis):
        return "no_article"
    return None


def load(cc: str, log: Callable[[str], None] = print) -> dict[str, int]:
    """Read every lane, fetch the candidates live, filter them, and store them in `pcorp_item`."""
    wd.init()
    state = countries.state_qid(cc)
    actors = actormod.read(cc)
    lanes: dict[str, set[str]] = {}
    names = countries.current_qids(cc)
    for root in TYPED_ROOTS:
        for name in names:
            for r in wd.sparql(TYPED % (root, name)):
                lanes.setdefault(r["i"], set()).add("typed")
    spec = countries.get(cc)
    if spec.forms:
        for name in names:
            for r in wd.sparql(FORMED % (wd.values_block(sorted(spec.forms)), name)):
                lanes.setdefault(r["i"], set()).add("formed")
    chains = actors.reach()
    for qid in chains:
        lanes.setdefault(qid, set()).add("owned")
    for qid in actors.parented():
        lanes.setdefault(qid, set()).add("parented")
    for qid in set().union(*(categorised(name, langs(state)) for name in names)):
        lanes.setdefault(qid, set()).add("category")
    seeded = spec.seeded()
    for qid in seeded:
        lanes.setdefault(qid, set()).add("seed")
    count = lambda lane: sum(lane in v for v in lanes.values())  # noqa: E731
    log(f"{cc}: {len(actors.kinds)} state actors; {len(lanes)} candidates "
        + ", ".join(f"{lane} {count(lane)}" for lane in ("typed", "formed", "owned", "parented", "category", "seed")))
    # Owned is the wide lane: stations, buildings and artworks a state body
    # owns come with it, and the organisation test is what drops them.
    typed = wd.fetch_items(sorted(lanes), props="claims")
    own = {q: typegraph.targets(typed.get(q, {})) for q in lanes}
    closure = typegraph.close(own)
    # An office is an item whose own type is a position class. Whether some
    # ancestor of its type is one says nothing: the type tree takes "business"
    # up to "position", which made every railway and grid operator an office.
    orgs = {q for q in lanes if positions.ORGANISATION in closure.get(q, set())
            and not set(own[q]) & positions.POSITION_METACLASSES}
    excluded = EXCLUDED | spec.exclude
    for qid in lanes:
        if closure.get(qid, set()) & excluded:
            orgs.discard(qid)
            lanes[qid].add("excluded")
    # A category lists buildings and brands too, so its members pass the
    # organisation test like the owned lane's; a typed, formed or listed item
    # is a body by its type or by the list.
    keep = [q for q in sorted(lanes) if "excluded" not in lanes[q] and (q in orgs or lanes[q] & {"seed", "typed", "formed"})]
    entities = wd.fetch_items(keep)
    wikis = langs(state)
    counts: dict[str, int] = {}
    conn = wd.conn()
    with conn.transaction():
        conn.execute("DELETE FROM pcorp_item WHERE country = %s", (cc,))
        for qid in sorted(lanes):
            entity = entities.get(qid)
            reason = ("excluded" if "excluded" in lanes[qid]
                      else classify(entity, qid in orgs, wikis) if qid in keep else "not_organisation")
            counts[reason or "kept"] = counts.get(reason or "kept", 0) + 1
            if reason == "not_organisation" and "owned" in lanes[qid] and len(lanes[qid]) == 1:
                continue  # the wide lane's buildings and artworks: not worth a row
            conn.execute(
                "INSERT INTO pcorp_item (country, qid, lanes, entity, chain, seed, dropped)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (cc, qid, sorted(lanes[qid]), Jsonb(entity or {}), Jsonb(chains.get(qid)),
                 Jsonb(seeded.get(qid)), reason))
    log(f"{cc}: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    return counts


def items(cc: str) -> list[dict[str, Any]]:
    """The kept candidates of a country, as loaded."""
    rows = wd.conn().execute(
        "SELECT qid, lanes, entity, chain, seed FROM pcorp_item WHERE country = %s AND dropped IS NULL ORDER BY qid",
        (cc,)).fetchall()
    return [{"qid": q, "lanes": la, "entity": e, "chain": c, "seed": s} for q, la, e, c, s in rows]
