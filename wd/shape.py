"""Score a position item against how Wikidata models political offices.

Reach for this at phase A of a sweep, before any roster. The defects it reports
are Wikidata's own — an item typed as a position that is really an occupation, an
office scoped to no jurisdiction, an office that says "position" and never says
what *kind* of office — and each is worth fixing whether or not a consumer
notices. `recipes/position_items.md` is the method; this module is its checker.

Three answers, kept apart on purpose and never mixed — the same split as
`wd/human.py`, for the same reason:

- **`defects`** — Wikidata modelling errors. An occupation typed as an office, an
  office scoped to no polity, an office that says "position" and never says what
  kind. Wrong statements, or missing ones the item cannot do without.
- **`gaps`** — properties the measured convention puts on an office and this item
  does not carry. Not errors, and never a reason to call an item defective: they
  are the additive data entry a campaign can do, each one sized off a real cluster
  in `research/position_items.md` so a lane can be scoped before it is run.
- **`os_notes`** — what the OpenSanctions PEP build makes of the item.

The gap tier is why it exists: a hand review of Qatar and the UAE found eleven
Qatari offices carrying no `P17` at all and twenty-one minted ambassadorships with
no `P137`, and every one of them passed the defect tests. `well_modelled` means
"no defects"; `complete` means the convention is fully expressed.

The secondary question, kept separate and clearly labelled, is whether the
OpenSanctions PEP build can currently read the item. That half is a port of
`zavod/zavod/shed/wikidata/`, cited per constant, because asking the live API
answers on the dataset's rebuild cadence and so cannot verify its own fixes.
It is reported as notes, never as defects: a correctly-modelled office that a
consumer does not yet emit is not defective, and distorting the model to make it
emit is how you corrupt the data while appearing to improve it.

`verify()` runs against a `wd.api.fetch_entities` payload and returns at once.
Calibrate against reality with `scripts/position_metadata.py --calibrate`.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple
import json
import re

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


#: Metaclasses that say "this is an office" and nothing about which kind.
#: An item declaring only these is under-modelled: it cannot be grouped, queried
#: by kind, or inherited from, and every consumer is left guessing.
#:
#: `Q4164871` is *not* the modal choice, measured: of 5,211 items with
#: `P279 = Q83307` minister, 4,428 (85%) use `P31 = Q294414` public office and 738
#: use `Q4164871`; `Q11696` President of the United States uses `Q17279032`
#: elective office. All of them reach `Q4164871` through `P279`, which is why the
#: closure rule matters — a check demanding a literal `P31 = Q4164871` misses
#: ~17,800 offices that people actually hold.
POSITION_METACLASSES: Set[str] = {
    "Q4164871",  # position
    "Q294414",  # public office
    "Q17279032",  # elective office
    "Q114962596",  # historical position
    "Q83856136",  # legal position
    "Q136649946",  # type of position
}

#: Wikidata's own answer to "what is a position not", read off `Q4164871`'s
#: `P1889 different from` — the first five below are its literal values — plus the
#: rank and organisation classes that measurement turned up. Needed because the
#: closure cannot answer this: within six hops `Q28640` profession and
#: `Q4189293` rank both reach `Q4164871`, so `dievdirbys` (a wood-carving trade)
#: and `flotilla admiral` (a naval rank) look like offices to a closure test.
NOT_AN_OFFICE: Set[str] = {
    "Q480319",  # title of authority
    "Q12737077",  # occupation
    "Q28640",  # profession
    "Q11348",  # function
    "Q192581",  # job activity
    "Q4189293",  # rank
    "Q56019",  # military rank
    "Q4226220",  # naval officer rank
    "Q43229",  # organization
    "Q495430",  # general staff — a body, not a seat in one
    # The sibling of the above, and its absence cost a real statement: `Q5942489`
    # "General Staff of Armed Forces of the Islamic Republic of Iran" declares
    # `P31 = Q6813432` and nothing else, so it read as a sound position and the gap
    # tier offered it `P1001 = Iran`. Its own description gives it away — "Highest
    # ranked officer of the Iranian Armed Forces" — the label names the body and
    # the description names the seat, which is the `Q12663357` Defence Staff
    # (Lithuania) case exactly.
    "Q6813432",  # military staff — also a body
    # Honours, distinctions and non-military ranks. Added 2026-08-19 off Belarus,
    # where 723 position items include a whole stratum of state honorifics —
    # "Honored Architect of the Republic of Belarus", "People's Poet of Belarus",
    # "Candidate for Master of Sports" — that declare one of these classes and no
    # position metaclass at all. Fourteen of fifty proposed Belarusian statements
    # were jurisdiction claims on an honour.
    #
    # Safe against the closure trap the recipe warns about, because `not_a_position`
    # tests *declared* types and stands down for anything that also declares an
    # office: `Q618779` award sits in the closure of `Q117826617` supreme court
    # judge, and a judgeship declaring that parent is untouched.
    "Q3320743",  # title of honor
    "Q13424289",  # honorary title
    "Q618779",  # award
    "Q4192699",  # badge of distinction
    "Q486983",  # academic rank
    "Q4121104",  # sports title
}

#: `Q4164871`'s own `P1963` "properties for this type": the community's answer to
#: which properties belong on a position item. Quoted in the recipe, not enforced.
TYPE_PROPERTIES: Tuple[str, ...] = ("P1308", "P2098", "P2389", "P571", "P17")

#: `wd.create.LIST_ARTICLE`. A position item typed as a Wikimedia list article is
#: two things at once, and every consumer has to guess which.
LIST_ARTICLE = "Q13406463"

#: The two class layers that make an item a bilateral diplomatic post. Which one
#: an item reaches decides what `P17` *means* on it — sender among `Q29645880`'s
#: subclasses, receiver among `Q29645886`'s — and it inverts the whole gap set:
#: a post wants a sender and an embassy, and specifically wants **no** `P1001`.
BILATERAL_CLASSES: Set[str] = {"Q29645880", "Q29645886"}

#: Gaps for an ordinary office -> the share of the reference cluster carrying it.
#:
#: Measured over the 5,211-item minister cluster (`P279 = Q83307`);
#: `research/position_items.md` holds the tallies. Only conventions strong enough
#: to act on unreviewed are here — `P2389` at 32.9% and `P571` at 8.5% are real
#: properties and not gaps, because asserting either on the strength of a third of
#: a cluster is the mass-assertion the recipe forbids.
OFFICE_GAPS: Dict[str, Tuple[str, float]] = {
    "no_P17": ("P17", 81.6),
    "no_P1001": ("P1001", 94.4),
    "no_P361": ("P361", 92.6),
}

#: Gaps for a bilateral post -> share of the 5,206-item bilateral cluster.
#:
#: `P1001` and `P361` are deliberately absent rather than forgotten: 29.6% and
#: 1.2%, and `P1001` copies the receiver when it is there at all, so asserting it
#: would be writing the 2.5% minority idiom. `P17` is here at 93.0% and means the
#: *receiving* state.
BILATERAL_GAPS: Dict[str, Tuple[str, float]] = {
    "no_P17": ("P17", 93.0),
    "no_sender": ("P137", 78.3),
    "no_embassy": ("P2389", 74.9),
}


@dataclass
class Verdict:
    """How well one position item is modelled, and what a reader makes of it.

    `defects` are Wikidata modelling errors, `gaps` are properties the measured
    convention puts on an office and this item does not carry, and `os_notes` are
    observations about a downstream consumer that are never either — see the
    module docstring.
    """

    qid: str
    label: Optional[str] = None
    #: P31/P279 closure hit `POSITION_BASICS` (or `ALLOW_TYPES`).
    basics: bool = False
    #: The item's own `P31`/`P279` targets, before any closure walk. What makes
    #: `untyped` answerable: the closure would reach `Q4164871` from anywhere.
    declared: List[str] = field(default_factory=list)
    #: FtM country codes the crawl reached, and the property that got there.
    countries: List[str] = field(default_factory=list)
    country_via: Optional[str] = None
    topics: Set[str] = field(default_factory=set)
    #: Closure members that conferred something, for explaining the verdict.
    matched: List[str] = field(default_factory=list)
    excluded_by: List[str] = field(default_factory=list)
    abolished: Optional[str] = None
    #: Wikidata modelling errors: `not_a_position`, `untyped`,
    #: `also_a_list_article`, `no_polity`.
    defects: List[str] = field(default_factory=list)
    #: Unasserted conventions: `no_P17`, `no_P1001`, `no_P361`, `no_P279`, and on
    #: a bilateral post `no_sender` / `no_embassy` in place of the jurisdiction
    #: pair. Additive every one of them. `no_office_polity` is the exception and
    #: names a gap the gap tier deliberately declines to close: the item has the
    #: `no_polity` defect, and which polity it belongs to is a decision, not a
    #: convention.
    gaps: List[str] = field(default_factory=list)
    #: Closure reaches `Q29645880`/`Q29645886`, so `P17` means a state at one end
    #: of a posting rather than the polity governed.
    bilateral: bool = False

    @property
    def well_modelled(self) -> bool:
        return not self.defects

    @property
    def complete(self) -> bool:
        """Every convention `recipes/position_items.md` measures is on the item."""
        return not self.defects and not self.gaps

    @property
    def os_notes(self) -> List[str]:
        """What a downstream reader currently makes of this item. Not defects.

        Each entry is a reason the OpenSanctions PEP build would skip an item
        that may be perfectly well modelled. `pep_default_off` is the sharpest:
        it means the honest parent for this office is not one zavod treats as
        PEP-conferring, which is a gap to file upstream and never a reason to
        retype the office.
        """
        notes: List[str] = []
        if PEP_SENTINEL not in self.topics:
            notes.append("pep_default_off")
        # `ALLOW_TYPES` beats `EXCLUDE_TYPES` (`position.py:107-114`), and every
        # `SUB_TYPES` key is allowed. Without that, `Q618779` "award" sits in the
        # closure of `Q117826617` supreme court judge and every judgeship in the
        # world reads as an excluded award.
        if self.excluded_by and not self.matched:
            notes.append("excluded_type")
        if self.abolished and self.abolished < POSITION_ABOLISHED_CUTOFF:
            notes.append("abolished_before_cutoff")
        return notes

    def as_dict(self) -> Dict[str, Any]:
        return {
            "qid": self.qid, "label": self.label,
            "declared": self.declared, "basics": self.basics,
            "bilateral": self.bilateral,
            "countries": self.countries, "country_via": self.country_via,
            "topics": sorted(self.topics - {PEP_SENTINEL}),
            "matched": self.matched, "excluded_by": self.excluded_by,
            "abolished": self.abolished,
            "defects": self.defects, "gaps": self.gaps,
            "well_modelled": self.well_modelled, "complete": self.complete,
            "os_notes": self.os_notes,
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


def _scoped_to_history(entity: Dict[str, Any]) -> bool:
    """Does this office name a polity at all, all of them historical?

    Distinguishes "nobody said which polity this office belongs to" — a real
    modelling defect — from "this office belonged to the Grand Duchy of
    Lithuania", which is complete and correct and resolves to no country.
    """
    named = [
        value
        for prop in COUNTRY_PROPS + FALLBACK_PROPS
        for value in claim_qids(entity, prop)
    ]
    return bool(named)


def verify(
    session: Any,
    entity: Dict[str, Any],
    closure: Dict[str, Set[str]],
    label: Optional[str] = None,
) -> Verdict:
    """Score one position item: modelling defects first, reader notes second.

    `closure` comes from `type_closure` over the whole candidate set at once;
    passing it in is what keeps a country-wide audit to one pass.
    """
    qid = entity.get("id", "")
    types = closure.get(qid, set())
    verdict = Verdict(qid=qid, label=label)
    verdict.declared = type_targets(entity)

    verdict.basics = bool(types & POSITION_BASICS)
    verdict.excluded_by = sorted(types & EXCLUDE_TYPES)

    # Modelling defect 1: this is a kind of work, a rank or a body, not an office.
    #
    # Tested on the *declared* types, because the closure cannot answer it: within
    # six hops `Q28640` profession reaches `Q4164871` position, so `dievdirbys`
    # (a folk wood-carving trade) and `flotilla admiral` (a naval rank) both look
    # like positions to a closure test and neither is one. An item earns "position"
    # by declaring a position root outright, or by declaring a specific kind of
    # office that `SUB_TYPES` recognises.
    #
    # Conservative by construction: it fires only on positive evidence that the
    # item is something else, never on the absence of evidence that it is an
    # office. `Q138024519` "Roman Catholic episcopal title" declares no metaclass
    # and no known kind, yet its own `P279` reaches `Q4164871` — flagging the
    # Lithuanian bishoprics off that was a false positive, and under-reporting
    # beats proposing a wrong retype.
    declared = set(verdict.declared)
    looks_like_office = bool(declared & (POSITION_METACLASSES | set(SUB_TYPES)))
    if (declared & NOT_AN_OFFICE) and not looks_like_office:
        verdict.defects.append("not_a_position")

    # Modelling defect 2: the item says "position" and never says what kind.
    # Read the item's *own* P31/P279 here too — a closure test could never answer
    # it, since every position reaches `Q4164871` from somewhere.
    elif not (declared - POSITION_METACLASSES - {LIST_ARTICLE}):
        verdict.defects.append("untyped")

    # Modelling defect 3: an office and a list of its holders are different items.
    if LIST_ARTICLE in declared:
        verdict.defects.append("also_a_list_article")

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
    # Modelling defect 3: an office belongs to a polity. Note that an office
    # scoped only to a *historical* polity legitimately resolves to nothing —
    # `_is_historical` drops those claims — and that is `absent`, not a defect
    # to backfill: naming the modern republic on a Grand Duchy office would be
    # a wrong statement in the lane that looks safest.
    if not countries and not _scoped_to_history(entity):
        verdict.defects.append("no_polity")

    # Everything below is the reader's view, surfaced through `os_notes`.
    for sub_type in types & set(SUB_TYPES):
        verdict.topics |= SUB_TYPES[sub_type]
        verdict.matched.append(sub_type)
    verdict.matched.sort()
    verdict.abolished = _time_value(entity, "P576")

    _add_gaps(verdict, entity, types, declared, looks_like_office)
    return verdict


#: "ambassador of X to Y" / "Ambassador of X to the Y" and the `Permanent
#: Representative` form. Matched on the label because the class layer is not
#: reliable: `Q112662216` "Ambassador of the Netherlands to Saudi Arabia" declares
#: `Q303618` diplomatic rank and reaches neither bilateral class, so it took the
#: ordinary-office gap set and was offered the `P1001` this recipe forbids on a
#: post. A label is weaker evidence than a class, which is why it only ever *adds*
#: to the bilateral set and never removes an item from it.
BILATERAL_LABEL = re.compile(
    r"\b(ambassador|permanent representative|nuncio|high commissioner)\b.*\bto\b",
    re.IGNORECASE,
)


def _reads_bilateral(label: Optional[str]) -> bool:
    return bool(label and BILATERAL_LABEL.search(label))


def _add_gaps(
    verdict: Verdict, entity: Dict[str, Any], types: Set[str],
    declared: Set[str], looks_like_office: bool,
) -> None:
    """The conventions this office does not express. Additive, never errors.

    Computed for every item, held or not: whether an unheld office is worth the
    data entry is a *policy* question, and `scripts/position_metadata.py` answers
    it. A checker that pre-filtered would hide the sizing a lane is scoped from.

    Every suppression below is a bug that was written first; `scripts/check_shape.py`
    pins each one.
    """
    verdict.bilateral = bool(types & BILATERAL_CLASSES) or _reads_bilateral(
        verdict.label)
    # An item that is not an office gets no office conventions proposed on it.
    # A rank or an occupation needs a *retype*, which is destructive-adjacent and
    # goes on the surgical list; adding `P279`/`P1001`/`P361` to it in the
    # meantime entrenches the mis-type, the same way adding metadata to the empty
    # twin of a duplicate entrenches the duplicate.
    if "not_a_position" in verdict.defects:
        return
    wanted = BILATERAL_GAPS if verdict.bilateral else OFFICE_GAPS
    # Named a polity, and none of them resolved: the office belongs to a
    # historical state, which is complete as it stands. **Not**
    # `_scoped_to_history` on its own — that returns true for *any* polity claim,
    # so one `P17` suppressed both jurisdiction gaps and `Q955006` President of the
    # UAE reported as complete while carrying no `P1001` at all. This is the
    # predicate `verify` pairs it with, and the only one that means "historical".
    # An ordinary office that resolves to no polity at all is a *defect*, and the
    # defect path is gated on a decided list for exactly this reason: `Q1837782`
    # Supreme Burgrave of the Kingdom of Bohemia and `Q3254084` King of Iraq name no
    # polity and were handed `P1001` to the modern republic by the label rule,
    # because "Bohemia" is an alias of Czechia and the tail of "King of Iraq" is
    # "Iraq". Which polity such an office belongs to is a decision, not a
    # convention, and the gap tier must not route around the defect tier's guard.
    #
    # Narrowed to the ordinary office on purpose. A **bilateral post** with the same
    # defect keeps its gaps, because both ends come off the item's own `P279` class
    # layer rather than off its label — `Q65262135` ambassador of Qatar to Estonia
    # carries no polity and its receiver class answers `Estonia` outright. Killing
    # that would have thrown away the strongest channel in the tier to fix a bug in
    # the weakest.
    stateless = "no_polity" in verdict.defects and not verdict.bilateral
    if stateless:
        verdict.gaps.append("no_office_polity")
    historical = not verdict.countries and _scoped_to_history(entity)
    for gap, (prop, _share) in wanted.items():
        if (historical or stateless) and prop in ("P17", "P1001"):
            continue
        if not claim_qids(entity, prop):
            verdict.gaps.append(gap)

    # The gap `untyped` cannot see. `untyped` fires when an item declares a
    # metaclass and *nothing else*, so it misses the item that declares something
    # else which still never names a kind of office: `Q726872` King of Bahrain
    # declares `P31 = Q355567` noble title, no `P279` at all, and is a head of
    # state that passes every defect test.
    #
    # Tested as "carries no `P279`", not as "carries no `P279` this repo
    # recognises". The recognised-kind version was written first and was wrong:
    # `Q166382` Amir is absent from `SUB_TYPES` — a list ported from a *consumer* —
    # so it reported all seven UAE emirate rulers as naming no kind of office when
    # each one names its kind precisely. Judging Wikidata's model by what a reader
    # happens to enumerate is the inversion the recipe exists to prevent. `P279` is
    # 100% of the reference cluster and needs no such list.
    #
    # A gap and not a defect, on measurement: `Q355567` and `Q138024519` "Roman
    # Catholic episcopal title" — the documented Lithuanian false positive — both
    # hit `NOT_AN_OFFICE` in closure *and* reach a position metaclass, so nothing
    # in the closure separates a mis-typed monarchy from a correctly-modelled
    # bishopric. Proposing an additive `P279` is safe where a retype is not.
    reads_as_office = looks_like_office or verdict.basics
    untyped = "untyped" in verdict.defects
    if reads_as_office and not untyped and not claim_qids(entity, "P279"):
        verdict.gaps.append("no_P279")
    verdict.gaps.sort()


def verify_all(
    session: Any, qids: Sequence[str], labels: Optional[Dict[str, str]] = None
) -> List[Verdict]:
    """Verify a whole country's position items in one pass."""
    closure = type_closure(session, qids)
    # `max_age=0` for the same reason `type_closure` refetches its seeds: these
    # are the audited items' own claims, which are precisely the state this
    # engine's batches change. It read fresh before only because `type_closure`
    # happened to run first and warm the cache — and the gap tier reads four more
    # properties off this payload, so the accident is no longer good enough.
    entities = fetch_entities(session, list(qids), max_age=0)
    labels = labels or {}
    return [
        verify(session, entity, closure, label=labels.get(qid))
        for qid, entity in sorted(entities.items())
    ]
