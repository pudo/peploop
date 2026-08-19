"""Decide whether a position item can be found by the OpenSanctions PEP build.

Reach for this before scoping any roster lane. A P39 statement added to an item
`zavod` cannot see produces nothing downstream, and the cheapest thing a
campaign can do for a country is often not harvesting holders but giving the
existing items the handful of properties that make them discoverable at all.

The gates below are a port of `zavod/zavod/shed/wikidata/`, cited per constant,
because the alternative — asking the live API — answers on the dataset's rebuild
cadence rather than immediately, so it cannot verify its own fixes. `verify()`
runs against a `wd.api.fetch_entities` payload and returns at once.

What it deliberately does *not* model: `zavod.stateful.positions.categorise`
reads a review database, so a human can mark any position PEP-conferring and
rescue an item that fails `role.pep` here. That channel is unreadable from this
repo and is not the target anyway — a `Verdict` answers "is this item
discoverable on its own merits", and needing the rescue is the finding.
Calibrate against reality with `scripts/discover_calibrate.py`.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple
import json

from rigour.territories import get_territory_by_qid

from wd.api import claim_qids, fetch_entities
from wd.http import REPO_ROOT

#: `position.py:20`. An item whose P31/P279 closure misses all of these never
#: becomes a candidate, whatever else it carries.
POSITION_BASICS: Set[str] = {
    "Q4164871",  # position
    "Q29645880",  # ambassador of a country
    "Q29645886",  # ambassador to a country
    "Q707492",  # military chief of staff
}

#: `position.py:26-80`. Closure member -> the topics it contributes.
#:
#: `role.pep` in here is a **sentinel, not a topic.** `position.py:278` reads it
#: to compute `default_is_pep`, then discards it at `:284` and again at `:301`, so
#: it never lands on a Position entity — the topics that survive are the `gov.*`,
#: `pol.*` and `role.diplo` ones. Never write `role.pep` onto a position.
SUB_TYPES: Dict[str, Set[str]] = {
    "Q30185": {"role.pep", "gov.executive", "gov.muni"},  # mayor
    "Q17279032": {"role.pep"},  # elective office
    "Q109862464": {"gov.executive", "gov.muni"},  # lord mayor
    "Q2285706": {"role.pep", "gov.head"},  # head of government
    "Q48352": {"role.pep", "gov.head"},  # head of state
    "Q3099723": {"role.pep", "gov.head"},  # minister-president
    "Q4175034": {"gov.legislative"},  # legislator
    "Q486839": {"role.pep", "gov.legislative"},  # member of parliament
    "Q83307": {"role.pep", "gov.executive"},  # minister
    "Q7330070": {"role.pep", "gov.executive"},  # foreign minister
    "Q14212": {"gov.head", "gov.executive"},  # prime minister
    "Q15966511": {"role.pep", "gov.executive", "gov.state"},  # deputy minister
    "Q132050": {"role.pep", "gov.executive"},  # governor
    "Q26204040": {"role.pep", "gov.executive"},  # deputy minister
    "Q46403368": {"role.pep", "gov.national"},  # deputy at the national level
    "Q20086425": {"role.pep", "gov.legislative"},  # shadow minister
    "Q303329": {"role.pep", "gov.legislative"},  # shadow cabinet
    "Q108290289": {"role.pep"},  # senior government officials
    "Q16533": {"gov.judicial"},  # judge
    "Q6635529": {"role.pep", "gov.executive"},  # provincial leader (PRC)
    "Q3526627": {"role.pep", "gov.legislative", "gov.state"},  # MLA (India)
    "Q117826617": {"role.pep", "gov.judicial"},  # supreme court judge
    "Q55736868": {"role.pep", "gov.judicial", "gov.national"},  # national sup court judge
    "Q1501926": {"role.pep", "gov.judicial"},  # attorney general
    "Q3368517": {"role.pep", "gov.judicial"},  # public prosecutor general
    "Q109607046": {"role.pep", "gov.judicial"},  # deputy public prosecutor general
    "Q107363151": {"role.pep", "gov.financial"},  # central bank governor
    "Q1553195": {"role.pep", "pol.party"},  # party leader
    "Q836971": {"pol.party"},  # party secretary
    "Q116182667": {"role.diplo"},  # diplomat
    "Q29645880": {"role.pep", "role.diplo"},  # ambassador of a country
    "Q29645886": {"role.pep", "role.diplo"},  # ambassador to a country
    "Q303618": {"role.diplo"},  # diplomatic rank
    "Q707492": {"role.pep", "gov.national", "gov.security"},  # military chief of staff
}

#: `position.py:88-104`. Silent exclusion, so the bar for reading one of these
#: as a defect rather than a correct answer is high.
EXCLUDE_TYPES: Set[str] = {
    "Q114962596",  # historical position
    "Q193622",  # order
    "Q60754876",  # grade of an order
    "Q618779",  # award
    "Q13424289",  # honorary title
    "Q4240305",  # cross
    "Q120560",  # minor basilica
    "Q2977",  # cathedral
    "Q3320743",  # title of honor
    "Q42603",  # priest
    "Q11773926",  # ecclesiastical occupation
    "Q63187345",  # religious occupation
}

#: `position.py:107-114`. Allow beats exclude.
ALLOW_TYPES: Set[str] = {
    "Q45722",  # cardinal
    "Q1729113",  # cardinal-bishop
    "Q2033341",  # cardinal priest
    "Q2361374",  # cardinal-deacon
    "Q19808790",  # Episcopal Co-Prince
} | set(SUB_TYPES)

#: `position.py:278`. A sentinel, not a topic: read once to seed
#: `categorise(default_is_pep=…)`, then discarded at `position.py:284` and again
#: at `:301`. No Position entity ever carries it, and nothing here should write it.
PEP_SENTINEL = "role.pep"

#: `position.py:84`. A `P576` before this date drops the position outright.
POSITION_ABOLISHED_CUTOFF = "1990-12-26"

#: `position.py:116`, and **not a gate.** The list is a staged rollout of
#: municipal PEPs — `position.py:115` says so — and it is on its way to every
#: country, so a mayoralty outside it is not defective in any way this repo can
#: act on. Kept only to label an expected calibration disagreement, never to fail
#: an item: reporting 60 correctly-typed Lithuanian mayoralties as broken invented
#: a problem that did not exist.
MUNI_COUNTRIES: Set[str] = {
    "au", "be", "br", "by", "ca", "co", "cz", "es", "fr", "gb", "gt", "hu",
    "id", "is", "it", "ke", "kr", "mx", "ni", "nl", "pl", "ro", "ru", "sk",
    "ua", "us", "ve", "za",
}

#: `country.py:_crawl_item_countries`. These are consulted FIRST and, if either
#: yields any country, the fallbacks below are never read — which is why adding
#: `P1001` beside a correct `P17` on an outbound ambassadorship changes nothing.
COUNTRY_PROPS: Tuple[str, ...] = ("P17", "P27")

#: `country.py`, same function. Only reached when `COUNTRY_PROPS` yields nothing.
FALLBACK_PROPS: Tuple[str, ...] = ("P1001", "P1376", "P361", "P749", "P159", "P2389")

#: `country.py:9-20`. Places whose `P17` names every state they span.
SKIP_PLACES: Set[str] = {
    "Q234", "Q210718", "Q4412", "Q52062", "Q7785",
    "Q18348382", "Q2334526", "Q1070529",
}

#: `country.py:is_historical_country`, the type half.
HISTORICAL_TYPES: Set[str] = {
    "Q3024240",  # historical country
    "Q19953632",  # former administrative territorial entity
    "Q839954",  # archeological site
}

CLOSURE_CACHE = REPO_ROOT / "data" / "discover" / "closure.json"

#: `nomenklatura/wikidata/model.py:204` caps the path at 6 hops. Match it, or a
#: deep class chain resolves here and not in the crawler.
CLOSURE_DEPTH = 6

#: Both properties, at every level, and the item's own QID counts as one of its
#: own types — `nomenklatura/wikidata/model.py:_type_props` and `_types`. Reading
#: only `P31` misses the whole chain a position item hangs off its `P279`, which
#: is where every archetype puts the type that decides gate 3.
TYPE_PROPS: Tuple[str, ...] = ("P31", "P279")

#: `_type_props` keeps a historical-country claim even when ended.
ALWAYS_KEPT = "Q3024240"


@dataclass
class Verdict:
    """Which discoverability gate a position item fails, and why.

    `self_sufficient` is the question worth asking: it is true only when the
    item's own claims carry it, with no reviewer vouching for it.
    """

    qid: str
    label: Optional[str] = None
    #: P31/P279 closure hit `POSITION_BASICS` (or `ALLOW_TYPES`).
    basics: bool = False
    #: FtM country codes the crawl reached, and the property that got there.
    countries: List[str] = field(default_factory=list)
    country_via: Optional[str] = None
    topics: Set[str] = field(default_factory=set)
    #: Closure members that conferred something, for explaining the verdict.
    matched: List[str] = field(default_factory=list)
    excluded_by: List[str] = field(default_factory=list)
    abolished: Optional[str] = None
    #: Gate ids, in the order `zavod` applies them. The municipal-rollout check
    #: is deliberately absent — see `MUNI_COUNTRIES`.
    failed: List[str] = field(default_factory=list)

    @property
    def awaits_muni_rollout(self) -> bool:
        """A well-formed municipal position that zavod does not yet emit.

        Not a defect and not actionable here; it explains a calibration
        disagreement and nothing else.
        """
        return "gov.muni" in self.topics and not (
            set(self.countries) & MUNI_COUNTRIES
        )

    @property
    def pep_default(self) -> bool:
        """Whether the type layer defaults this position to PEP-conferring.

        Not "does it carry `role.pep`" — nothing does. The sentinel is read once
        to seed `categorise(default_is_pep=…)` and thrown away, so this says
        which side of the default the item starts on, and a reviewer may still
        decide the other way.
        """
        return PEP_SENTINEL in self.topics

    @property
    def self_sufficient(self) -> bool:
        return not self.failed

    def as_dict(self) -> Dict[str, Any]:
        return {
            "qid": self.qid, "label": self.label, "basics": self.basics,
            "countries": self.countries, "country_via": self.country_via,
            "topics": sorted(self.topics - {PEP_SENTINEL}),
            "matched": self.matched, "pep_default": self.pep_default,
            "excluded_by": self.excluded_by, "abolished": self.abolished,
            "failed": self.failed, "self_sufficient": self.self_sufficient,
            "awaits_muni_rollout": self.awaits_muni_rollout,
        }


def type_targets(entity: Dict[str, Any]) -> List[str]:
    """The `P31` and `P279` values that count as this item's types.

    Ended claims are skipped, because a superseded classification is not what
    the item *is* — the one exception being a historical country, which stays
    historical. Mirrors `nomenklatura/wikidata/model.py:_type_props`.
    """
    out: List[str] = []
    for prop in TYPE_PROPS:
        for claim in entity.get("claims", {}).get(prop, []):
            value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
            if not isinstance(value, dict) or "id" not in value:
                continue
            qid = value["id"]
            ended = bool(claim.get("qualifiers", {}).get("P582"))
            if ended and qid != ALWAYS_KEPT:
                continue
            out.append(qid)
    return out


def type_closure(
    session: Any, qids: Sequence[str], cache: Optional[Path] = CLOSURE_CACHE
) -> Dict[str, Set[str]]:
    """Every type an item has, closing over `P31` and `P279` together.

    Use this instead of a SPARQL property path whenever the question is "does
    this hold *anywhere* among the values": one preferred `P31` hides the
    normal-rank ones and a deprecated one vanishes from `wdt:` entirely, so a
    closure built on truthy values reports real positions as untyped.

    An item's own QID is one of its types, matching the crawler — so asking
    whether a class is a `SUB_TYPES` member answers for the class itself too.

    Batched level by level and cached; the naive shape (one fetch per item per
    level) takes minutes on a few hundred items.
    """
    seeds = set(qids)
    edges: Dict[str, List[str]] = {}
    if cache is not None and cache.exists():
        edges.update(json.loads(cache.read_text()))
    # An audited item's own P31/P279 is *state this engine changes*, so it can
    # never come from the seven-day cache: a run after its own batch read
    # `Q131824331` as untyped and re-proposed a parent already on the item.
    # Ancestor classes above it are stable and stay cached.
    for qid in seeds:
        edges.pop(qid, None)
    fresh = fetch_entities(session, sorted(seeds), max_age=0)
    seed_edges = {qid: type_targets(fresh.get(qid, {})) for qid in seeds}

    frontier = {
        t for targets in seed_edges.values() for t in targets if t not in edges
    }
    for _ in range(CLOSURE_DEPTH):
        if not frontier:
            break
        found = fetch_entities(session, sorted(frontier))
        for qid in frontier:
            edges[qid] = type_targets(found.get(qid, {}))
        frontier = {
            t for qid in frontier for t in edges.get(qid, []) if t not in edges
        }
    for qid in frontier:  # depth-capped: record as leaves, don't lose them
        edges.setdefault(qid, [])

    if cache is not None:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(
            {q: v for q, v in edges.items() if q not in seeds}, sort_keys=True))

    edges = {**edges, **seed_edges}
    out: Dict[str, Set[str]] = {}
    for qid in qids:
        seen: Set[str] = {qid}
        frontier_q = [qid]
        for _ in range(CLOSURE_DEPTH):
            nxt = [t for x in frontier_q for t in edges.get(x, []) if t not in seen]
            seen.update(nxt)
            frontier_q = nxt
            if not frontier_q:
                break
        out[qid] = seen
    return out


def _country_of(session: Any, qid: str, seen: Tuple[str, ...]) -> Set[str]:
    """FtM country codes an item resolves to, mirroring `country.py`'s walk."""
    if qid in SKIP_PLACES:
        return set()
    territory = get_territory_by_qid(qid)
    if territory is not None and territory.ftm_country is not None:
        return {territory.ftm_country}
    entity = fetch_entities(session, [qid]).get(qid)
    if entity is None:
        return set()
    nxt = seen + (qid,)
    out: Set[str] = set()
    for prop in COUNTRY_PROPS:
        for value in claim_qids(entity, prop):
            if value not in nxt:
                out |= _country_of(session, value, nxt)
    if out:
        return out
    for prop in FALLBACK_PROPS:
        for value in claim_qids(entity, prop):
            if value in nxt:
                continue
            out |= _country_of(session, value, nxt)
            if out:
                return out
    return out


def _is_historical(session: Any, qid: str, closure: Dict[str, Set[str]]) -> bool:
    territory = get_territory_by_qid(qid)
    if territory is not None:
        return bool(territory.is_historical)
    types = closure.get(qid)
    if types is None:
        types = type_closure(session, [qid]).get(qid, set())
    return bool(types & HISTORICAL_TYPES)


def _time_value(entity: Dict[str, Any], prop: str) -> Optional[str]:
    """The first day-or-coarser ISO date on a property, or None."""
    for claim in entity.get("claims", {}).get(prop, []):
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(value, dict) and isinstance(value.get("time"), str):
            return value["time"].lstrip("+")[:10]
    return None


def verify(
    session: Any,
    entity: Dict[str, Any],
    closure: Dict[str, Set[str]],
    label: Optional[str] = None,
) -> Verdict:
    """Score one position item against every gate, in `zavod`'s own order.

    `closure` comes from `type_closure` over the whole candidate set at once;
    passing it in is what keeps a country-wide audit to one pass.
    """
    qid = entity.get("id", "")
    types = closure.get(qid, set())
    verdict = Verdict(qid=qid, label=label)

    verdict.basics = bool(types & POSITION_BASICS)
    allowed = bool(types & ALLOW_TYPES)
    verdict.excluded_by = sorted(types & EXCLUDE_TYPES)
    if not allowed:
        if not verdict.basics:
            verdict.failed.append("basics")
        elif verdict.excluded_by:
            verdict.failed.append("excluded")

    via: Optional[str] = None
    countries: Set[str] = set()
    for prop in COUNTRY_PROPS + FALLBACK_PROPS:
        for value in claim_qids(entity, prop):
            if _is_historical(session, value, closure):
                continue
            got = _country_of(session, value, (qid,))
            if got:
                countries |= got
                via = via or prop
        if countries and prop in COUNTRY_PROPS:
            break  # the short-circuit: fallbacks are never read
        if countries and via == prop:
            break
    verdict.countries = sorted(countries)
    verdict.country_via = via
    if not countries:
        verdict.failed.append("country")

    for sub_type in types & set(SUB_TYPES):
        verdict.topics |= SUB_TYPES[sub_type]
        verdict.matched.append(sub_type)
    verdict.matched.sort()
    if not verdict.pep_default:
        verdict.failed.append("no_pep_default")

    verdict.abolished = _time_value(entity, "P576")
    if verdict.abolished and verdict.abolished < POSITION_ABOLISHED_CUTOFF:
        verdict.failed.append("abolished")

    return verdict


def verify_all(
    session: Any, qids: Sequence[str], labels: Optional[Dict[str, str]] = None
) -> List[Verdict]:
    """Verify a whole country's position items in one pass."""
    closure = type_closure(session, qids)
    entities = fetch_entities(session, list(qids))
    labels = labels or {}
    return [
        verify(session, entity, closure, label=labels.get(qid))
        for qid, entity in sorted(entities.items())
    ]
