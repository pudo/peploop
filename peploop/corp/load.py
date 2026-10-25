"""Find a country's candidate state bodies and keep the ones worth a decision.

Eight lanes for state bodies, each going wide on purpose: what the decision stage and, after
it, OpenSanctions' position classification filter out costs less than a body
never found.

- `typed`: the item is a state-owned enterprise by `P31` or `P1454` (legal
  form), through any subclass of `Q270791`, and `P17` is the country.
- `formed`: its `P31` or `P1454` is one of the country's state-only legal
  forms (the spec's `forms`), matched exactly: an authority, a public-law
  institution or foundation, which carries no SOE marker and often no owner.
- `statutory`: its `P31` is a class of statutory body -- public broadcaster,
  central bank, regulator (`rules.STATUTORY_TYPED`), matched exactly --
  which no owner links to the state: it is the state's by law.
- `owned`: a chain of `P127` or `P749` links reaches a state actor
  (`actors.py`).
- `parented`: its parent organization is a state actor: a body a ministry or
  a government runs.
- `category`: a Wikipedia category for the country's state enterprises or
  government agencies lists it; the category is found through Wikidata
  (`P971` combining the class with the country), so the lane needs no
  country's names, and reaches bodies with no links on Wikidata at all;
- `seed`: an official list of holdings (the spec's `holdings`) names it;
  this is what finds a body neither Wikidata nor Wikipedia records as state;
- `listed`: the member state's own list of prominent public functions
  (AMLR Art. 43, `peploop/amlr/<cc>.yml`) names it, resolved to its item in
  a row's expansion. The list puts its seats in PEP scope; it says nothing
  about who owns it.

Two more lanes bring in political parties, whose governing bodies are PEPs
(AMLR Art. 2(1)(34)(iii)) without any state control:

- `party`: a party of the country one of whose living members holds a seat
  now -- a legislator's, or the head office of the state, a first-level
  subdivision or a governed unit of 50,000 or more (`amlr.units`) -- plus
  the spec's `parties`;
- `party_branch`: a body that is part of such a party or has it as parent
  (`P361`, `P749`) and is itself a party by type, or an instance of one of
  the spec's `party_branch_classes` (a federal party's state association is
  typed as an association, a regional federation as a political
  organisation): the parts of a party are mostly its working groups,
  currents and organs, and those classes' other instances sports and
  charity federations. Youth wings, parliamentary groups and electoral lists
  are never a branch (`EXCLUDED`).

Three more lanes bring in a city's or a grouping's bodies, only where the
country's spec writes the municipal tier (AMLR Art. 2(1)(34)(vii)); the
`owned` lane reaches them too, through chains ending at a governed unit of
50,000 or more (`actors.py`):

- `municipal_typed`: the item is a municipal company (`Q1780371`, through
  any subclass) by `P31` or `P1454`;
- `sector`: an organisation located (`P131`, `P159`) in a governed unit of
  50,000 or more whose `P31` is a municipal-sector class
  (`MUNICIPAL_CLASSES` and the spec's `municipal_classes`), matched exactly.
  Being located there proves nothing: the answer must still say a
  municipality controls it, as for any lane;
- `municipal_category`: the spec's Wikipedia categories of municipal
  enterprises list it.

A city owns stations, venues and paintings far more often than a state does;
the organisation test drops them, so only the typed lane is a body by type.

A spec whose tier is `international` (`countries/eu.yml`) reads one lane
instead of all these, beside its `seed` and `listed` ones:

- `international`: an instance of one of the spec's `body_classes`
  (through any subclass), or of its `organisation_classes` with its
  headquarters (`P159`) in a member of the scope (its `P150`). Its board
  seats are PEPs by the AMLR (Art. 2(1)(34)(vi)), whoever controls it; it
  is a holding, never a state actor.
"""

from datetime import date
from typing import Any, Callable

from psycopg.types.json import Jsonb
from rigour.langs import iso_639_alpha2
from rigour.territories import get_territory_by_qid

from peploop import amlr, classes, typegraph, wikipedia
from peploop.corp import actors as actormod
from peploop.corp import country as countries
from peploop.corp import rules, wd

#: The markers whose subclass trees the typed lane reads.
TYPED_ROOTS = ("Q270791",)
#: The municipal company class, whose subclass tree the municipal typed lane reads.
MUNICIPAL_ROOT = "Q1780371"
#: The classes whose instances located in a governed unit of 50,000 or more
#: are municipal-tier candidates, in every country that writes the tier; a
#: spec adds its own (`municipal_classes`). Utilities, transport and housing
#: are what cities run as companies; hospitals and banks are left to a
#: spec, as most of them are no city's.
MUNICIPAL_CLASSES = frozenset({
    "Q740752",  # transport company
    "Q2127330",  # public transport company
    "Q1341478",  # energy company
    "Q1951366",  # public utility
    "Q1534992",  # housing company
    "Q8207109",  # housing association
    "Q1780371",  # municipal company
    "Q17990971",  # public enterprise
})
SECTOR = """SELECT DISTINCT ?i WHERE { VALUES ?u { %s } VALUES ?c { %s } ?i wdt:P31 ?c .
  { ?i wdt:P131 ?u } UNION { ?i wdt:P159 ?u } }"""
TYPED = """SELECT DISTINCT ?i WHERE { ?c wdt:P279* wd:%s . { ?i wdt:P31 ?c } UNION { ?i wdt:P1454 ?c } ?i wdt:P17 wd:%s . }"""
#: Classes that are never a candidate, in any country: their leaders are
#: peploop's (officers, ambassadors, judges, mayors, ministers), they are no body at all,
#: or they are sports clubs, whose boards are no state function even when a
#: state enterprise owns the club. A country adds its own in its spec (`exclude`).
EXCLUDED = frozenset({
    "Q176799",  # military unit
    "Q772547",  # armed forces: its chief is a position, peploop's
    "Q3917681",  # embassy
    "Q7843791",  # diplomatic mission
    "Q41487",  # court
    "Q56061",  # administrative territorial entity
    "Q476028",  # association football club
    "Q847017",  # sports club
    "Q192350",  # ministry
    "Q7188",  # government
    # A party's satellites: none is the party's governing body.
    "Q2493450",  # youth wing
    "Q11744698",  # parliamentary group
    "Q355844",  # electoral list
})
#: The classes whose country categories the category lane reads.
CATEGORY_TOPICS = ("Q270791", "Q327333")  # state-owned enterprise, government agency
CATEGORIES = """SELECT DISTINCT ?cat WHERE { VALUES ?x { %s } ?cat wdt:P31 wd:Q4167836 ; wdt:P971 wd:%s ; wdt:P971 ?x . }"""
FORMED = """SELECT DISTINCT ?i WHERE { VALUES ?f { %s } { ?i wdt:P31 ?f } UNION { ?i wdt:P1454 ?f } ?i wdt:P17 wd:%s . }"""
#: How far back a member's open seat may start and still count as held now:
#: an open statement older than about three terms is more often stale than held.
PARTY_SEAT_SINCE = 12
#: The parties of a country with a living member who holds a legislator's seat
#: now, read from QLever (the `P279*` walk over every member's seats is more
#: than the query service answers in time).
PARTY_MEMBERS = """SELECT DISTINCT ?party WHERE { ?party wdt:P17 wd:%s .
  ?h p:P102 ?m . ?m ps:P102 ?party . FILTER NOT EXISTS { ?m pq:P582 ?me } FILTER NOT EXISTS { ?h wdt:P570 ?d }
  ?h p:P39 ?st . ?st ps:P39 ?pos ; pq:P580 ?s . FILTER(?s >= "%s"^^<http://www.w3.org/2001/XMLSchema#dateTime>)
  FILTER NOT EXISTS { ?st pq:P582 ?e } ?pos wdt:P279* wd:Q4175034 . }"""
#: The same for a head office, with the polity or unit it is scoped to.
PARTY_HEADS = """SELECT DISTINCT ?party ?j WHERE { VALUES ?head { %s } ?party wdt:P17 wd:%s .
  ?h p:P102 ?m . ?m ps:P102 ?party . FILTER NOT EXISTS { ?m pq:P582 ?me } FILTER NOT EXISTS { ?h wdt:P570 ?d }
  ?h p:P39 ?st . ?st ps:P39 ?pos ; pq:P580 ?s . FILTER(?s >= "%s"^^<http://www.w3.org/2001/XMLSchema#dateTime>)
  FILTER NOT EXISTS { ?st pq:P582 ?e } ?pos wdt:P279* ?head ; wdt:P1001 ?j . }"""
#: The international lane: the scope's own bodies, and the organisations
#: headquartered in one of its members (`P150` of the scope).
INTERNATIONAL = """SELECT DISTINCT ?b WHERE {
  { ?b wdt:P31/wdt:P279* ?k . VALUES ?k { %(own)s } }
  UNION
  { ?b wdt:P31/wdt:P279* ?k . VALUES ?k { %(seated)s } wd:%(scope)s wdt:P150 ?c .
    { ?b wdt:P159 ?hq . ?hq wdt:P17 ?c } UNION { ?b wdt:P159 ?c } } }"""
#: A party by type: a part of a party typed so is one of its branches.
POLITICAL_PARTY = "Q7278"
PARTY_PARTS = """SELECT DISTINCT ?b WHERE { VALUES ?p { %s } { ?b wdt:P361 ?p } UNION { ?b wdt:P749 ?p } }"""


#: Every lane, in the order the load reports them.
LANES = ("typed", "formed", "statutory", "owned", "parented", "category", "seed", "listed", "party", "party_branch",
         "municipal_typed", "sector", "municipal_category", "international")
#: The lanes only a country writing the municipal tier reads.
MUNICIPAL_LANES = ("municipal_typed", "sector", "municipal_category")
#: The lanes whose bodies are parties, asked about their governing bodies and never about control.
PARTY_LANES = ("party", "party_branch")


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


def located(units: frozenset[str] | set[str], classes_: frozenset[str] | set[str]) -> set[str]:
    """The items of these classes located in these units: the sector lane's candidates, read from QLever."""
    if not units or not classes_:
        return set()
    cls = wd.values_block(sorted(classes_))
    return {r["i"] for r in wd.bisect(lambda chunk: wd.qlever(SECTOR % (wd.values_block(chunk), cls)),
                                      sorted(units), size=100)}


def municipal_categorised(spec: countries.Spec) -> set[str]:
    """The items the spec's municipal enterprise categories list."""
    return {q for lang, title, depth in spec.categories for _, q in wikipedia.walk_category(title, lang, depth)}


def listed(cc: str) -> set[str]:
    """The bodies the member state's AMLR function list names, as resolved in the asset."""
    return {str(e["body"]) for f in amlr.functions(cc) for e in f.expansion if "body" in e}


def unresolved(cc: str) -> list[amlr.Function]:
    """The list's named-body rows no expansion resolves to an item: residue for the report."""
    return [f for f in amlr.functions(cc) if f.kind == "body" and not any("body" in e for e in f.expansion)]


def parties(cc: str, scope: set[str], today: date | None = None) -> set[str]:
    """The country's parties with a member seated now: in a legislature, or heading a polity or unit in `scope`.

    Reach for this to find whose governing bodies are PEPs. A party counts
    by its members' seats, never by its size or its own statements.
    """
    since = f"{(today or date.today()).year - PARTY_SEAT_SINCE}-01-01T00:00:00Z"
    heads = wd.values_block(sorted(amlr.HEADS))
    found: set[str] = set()
    for name in countries.current_qids(cc):
        found.update(r["party"] for r in wd.qlever(PARTY_MEMBERS % (name, since)))
        found.update(r["party"] for r in wd.qlever(PARTY_HEADS % (heads, name, since)) if r["j"] in scope)
    return found


def branches(found: set[str]) -> set[str]:
    """The parts and subsidiaries of these parties: their branches among them, which the type test picks."""
    out = {r["b"] for r in wd.bisect(lambda chunk: wd.qlever(PARTY_PARTS % wd.values_block(chunk)),
                                     sorted(found), size=100)} if found else set()
    return out - found


def branch(own: list[str], closure: set[str], classes_: frozenset[str]) -> bool:
    """Whether a part of a party is a branch: a party by type, or of one of the country's branch classes."""
    return POLITICAL_PARTY in closure or bool(set(own) & classes_)


def international(spec: countries.Spec, scope: str) -> set[str]:
    """The scope's own bodies and the organisations seated in one of its members, read from the query service."""
    if not spec.body_classes and not spec.organisation_classes:
        return set()
    return {r["b"] for r in wd.sparql(INTERNATIONAL % {
        "own": wd.values_block(list(spec.body_classes)) or "wd:Q0",
        "seated": wd.values_block(list(spec.organisation_classes)) or "wd:Q0", "scope": scope})}


def candidates(cc: str, spec: countries.Spec, actors: actormod.Actors, state: str) -> dict[str, set[str]]:
    """Every lane's candidates for a state: QID → the lanes that found it."""
    lanes: dict[str, set[str]] = {}
    names = countries.current_qids(cc)
    for root in TYPED_ROOTS:
        for name in names:
            for r in wd.sparql(TYPED % (root, name)):
                lanes.setdefault(r["i"], set()).add("typed")
    if spec.forms:
        for name in names:
            for r in wd.sparql(FORMED % (wd.values_block(sorted(spec.forms)), name)):
                lanes.setdefault(r["i"], set()).add("formed")
    for name in names:
        for r in wd.sparql(FORMED % (wd.values_block(sorted(rules.STATUTORY_TYPED)), name)):
            lanes.setdefault(r["i"], set()).add("statutory")
    for qid in actors.reach():
        lanes.setdefault(qid, set()).add("owned")
    for qid in actors.parented():
        lanes.setdefault(qid, set()).add("parented")
    for qid in set().union(*(categorised(name, langs(state)) for name in names)):
        lanes.setdefault(qid, set()).add("category")
    # A party's seats are held at the national or regional level, or heading a governed unit.
    scope = {q for q, k in actors.kinds.items() if k in ("state", "subdivision")} | set(amlr.units(cc))
    found = parties(cc, scope) | spec.parties
    for qid in found:
        lanes.setdefault(qid, set()).add("party")
    for qid in branches(found):
        lanes.setdefault(qid, set()).add("party_branch")
    if "municipal" in spec.tiers:
        for name in names:
            for r in wd.sparql(TYPED % (MUNICIPAL_ROOT, name)):
                lanes.setdefault(r["i"], set()).add("municipal_typed")
        for qid in located(actors.units(), MUNICIPAL_CLASSES | spec.municipal_classes):
            lanes.setdefault(qid, set()).add("sector")
        for qid in municipal_categorised(spec):
            lanes.setdefault(qid, set()).add("municipal_category")
    return lanes


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
    spec = countries.get(cc)
    if spec.international:
        # The Union's bodies and the organisations seated in it: holdings, never state actors.
        lanes = {qid: {"international"} for qid in international(spec, state)}
    else:
        lanes = candidates(cc, spec, actors, state)
    chains = actors.reach()
    seeded = spec.seeded()
    for qid in seeded:
        lanes.setdefault(qid, set()).add("seed")
        if spec.international:
            lanes[qid].add("international")
    for qid in listed(cc):
        lanes.setdefault(qid, set()).add("listed")
        if spec.international:
            lanes[qid].add("international")
    count = lambda lane: sum(lane in v for v in lanes.values())  # noqa: E731
    log(f"{cc}: {len(actors.kinds)} state actors; {len(lanes)} candidates " + ", ".join(
        f"{lane} {count(lane)}" for lane in LANES))
    # Owned is the wide lane: stations, buildings and artworks a state body
    # owns come with it, and the organisation test is what drops them.
    typed = wd.fetch_items(sorted(lanes), props="claims")
    own = {q: typegraph.targets(typed.get(q, {})) for q in lanes}
    closure = typegraph.close(own)
    # An office is an item whose own type is a position class. Whether some
    # ancestor of its type is one says nothing: the type tree takes "business"
    # up to "position", which made every railway and grid operator an office.
    orgs = {q for q in lanes if classes.ORGANISATION in closure.get(q, set())
            and not set(own[q]) & classes.POSITION_METACLASSES}
    excluded = EXCLUDED | spec.exclude
    for qid in lanes:
        if closure.get(qid, set()) & excluded:
            orgs.discard(qid)
            lanes[qid].add("excluded")
    # A part of a party that is no branch (a working group, a current, an
    # organ) is dropped unless another lane brought it in.
    nonbranch = {q for q in lanes if lanes[q] == {"party_branch"}
                 and not branch(own[q], closure.get(q, set()), spec.party_branch_classes)}
    # A category lists buildings and brands too, so its members pass the
    # organisation test like the owned lane's, and so do the sector lane's;
    # a typed, formed, statutory or listed item is a body by its type or by the list.
    # A party is a body by its members' seats, as a listed one is by the list.
    bodies = {q for q in lanes if q in orgs or lanes[q] & {"seed", "typed", "municipal_typed", "formed", "statutory", "listed",
                                                           "party", "international"}}
    keep = [q for q in sorted(lanes) if "excluded" not in lanes[q] and q in bodies and q not in nonbranch]
    entities = wd.fetch_items(keep)
    # An international body is read in the spec's wikis (`decide.international_wikis`).
    wikis = list(spec.wikis) if spec.international else langs(state)
    counts: dict[str, int] = {}
    conn = wd.conn()
    with conn.transaction():
        conn.execute("DELETE FROM pcorp_item WHERE country = %s", (cc,))
        for qid in sorted(lanes):
            entity = entities.get(qid)
            reason = ("excluded" if "excluded" in lanes[qid] else "not_branch" if qid in nonbranch
                      else classify(entity, qid in bodies, wikis) if qid in keep else "not_organisation")
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
