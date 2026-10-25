"""Find the state actors of a country, and what their ownership and parenthood reach.

A body is state-controlled when a chain of `P127` (owned by) or `P749`
(parent organization) links ends at the state: the country itself, one of its
first-level subdivisions, or a government body of either (a ministry, an
agency, a government). Where a country's spec writes the municipal tier, its
governed units of 50,000 or more (`amlr.units`) are actors too, and a chain
ending at one is municipal control. Wikidata writes that chain many ways --
straight to the country, through a ministry or a state holding, through
another state body -- so the walk follows both links up to `HOPS` steps
rather than asking for one shape.

The links come from QLever: the query service cannot list every `P127` and
`P749` of a country inside its time limit, and a dump days old is good enough
to find candidates whose state is then read live. Links are read from the
country's items and into them, so a state group's foreign subsidiaries come
in too.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable

from peploop import amlr, policy, typegraph
from peploop.corp import country as countries
from peploop.corp import wd

#: How many link steps a chain may take from a body to a state actor.
HOPS = 3
#: The links a chain follows: owned by, parent organization.
LINKS = ("P127", "P749")
#: Classes that make a linked body a government body, when it belongs to the country.
GOVERNMENT = frozenset({
    "Q2659904",  # government organization
    "Q327333",  # government agency
    "Q192350",  # ministry
    "Q7188",  # government
    "Q35798",  # executive branch
})
#: Classes that disqualify a body whatever else it is, in every country: the
#: type tree makes every municipality and district a government organization,
#: and public research institutions and state enterprises too. Polities are
#: actors by name, municipal units by the AMLR unit set, and a research institution
#: or a state enterprise is an owner once a run decides the state controls it.
#: A country adds its own misfiled classes in its spec (`not_government`).
NOT_GOVERNMENT = frozenset({
    "Q56061",  # administrative territorial entity
    "Q31855",  # research institute
    "Q270791",  # state-owned enterprise
    "Q1780371",  # municipal company
    "Q245065",  # intergovernmental organization: of several states, never one's
})

#: The two sides a link is read from: the country's items, and links into
#: them (a state group's foreign subsidiaries). Two plain queries each, as one
#: UNION is more than QLever answers in time.
SIDES = ("?i wdt:P17 wd:%(s)s .", "?o wdt:P17 wd:%(s)s .")
PAIRS = """SELECT DISTINCT ?i ?o WHERE { %(side)s ?i p:%(p)s ?st . ?st ps:%(p)s ?o . }"""
TARGET_TYPES = """SELECT DISTINCT ?o ?t WHERE { %(side)s ?i p:%(p)s ?st . ?st ps:%(p)s ?o . ?o wdt:P31 ?t . }"""
TARGET_PLACES = """SELECT DISTINCT ?o ?c WHERE { %(side)s ?i p:%(p)s ?st . ?st ps:%(p)s ?o . ?o wdt:P17 ?c . }"""
TARGET_JURISDICTIONS = """SELECT DISTINCT ?o ?c WHERE { %(side)s ?i p:%(p)s ?st . ?st ps:%(p)s ?o . ?o wdt:P1001 ?c . }"""
TARGET_ENDED = """SELECT DISTINCT ?o WHERE { %(side)s ?i p:%(p)s ?st . ?st ps:%(p)s ?o . ?o wdt:P576 ?d . }"""


@dataclass
class Actors:
    """A country's state actors and the links read for it."""

    state: str
    #: actor QID → "state", "subdivision", "government" or "municipal".
    kinds: dict[str, str] = field(default_factory=dict)
    #: link property → target → the items linking to it.
    links: dict[str, dict[str, set[str]]] = field(default_factory=dict)
    polities: frozenset[str] = frozenset()
    not_government: frozenset[str] = NOT_GOVERNMENT

    def reach(self, hops: int = HOPS) -> dict[str, list[str]]:
        """Every item a state actor reaches within `hops` steps, with its chain (the item first, the actor last)."""
        chains: dict[str, list[str]] = {}
        frontier = {a: [a] for a in self.kinds}
        for _ in range(hops):
            nxt: dict[str, list[str]] = {}
            for target, path in sorted(frontier.items()):
                for item in sorted(set().union(*(self.links.get(p, {}).get(target, set()) for p in LINKS))):
                    if item in chains or item in self.kinds:
                        continue
                    chains[item] = [item, *path]
                    nxt[item] = chains[item]
            frontier = nxt
        return chains

    def units(self) -> frozenset[str]:
        """The governed units of 50,000 or more whose bodies are the municipal tier: empty unless the spec writes it."""
        return frozenset(q for q, k in self.kinds.items() if k == "municipal")

    def parented(self) -> set[str]:
        """Items whose parent organization is a state actor: the bodies a ministry or government runs."""
        return {i for a in self.kinds for i in self.links.get("P749", {}).get(a, set())}

    def is_government(self, qids: Iterable[str]) -> set[str]:
        """Which of these items, read live, are the country's polities or government bodies."""
        wanted = [q for q in dict.fromkeys(qids) if q]
        if not wanted:
            return set()
        ents = wd.fetch_items(wanted, props="claims")
        types = {q: set(wd.values(e, "P31")) for q, e in ents.items()}
        places = {q: set(wd.values(e, "P17")) for q, e in ents.items()}
        jurisdictions = {q: set(wd.values(e, "P1001")) for q, e in ents.items()}
        closure = typegraph.of_classes({t for ts in types.values() for t in ts})
        found = classify(self.state, set(self.polities), types, places, closure, self.not_government, jurisdictions)
        return {q for q in wanted if q in found}


def classify(state: str, polities: set[str], types: dict[str, set[str]], places: dict[str, set[str]],
             closure: dict[str, set[str]], not_government: frozenset[str] = NOT_GOVERNMENT,
             jurisdictions: dict[str, set[str]] | None = None) -> dict[str, str]:
    """Which linked bodies are state actors: the polities, and the government bodies placed in one of them.

    A body's own jurisdiction (`P1001`) decides where it has one: a town's
    administration names its country as `P17` but governs the town, and is
    no state actor.
    """
    kinds = {q: ("state" if q == state else "subdivision") for q in polities}
    for target, ts in types.items():
        if target in kinds:
            continue
        reached = set().union(*(closure.get(t, {t}) for t in ts)) if ts else set()
        where = (jurisdictions or {}).get(target) or places.get(target, set())
        if reached & GOVERNMENT and not reached & not_government and where & polities:
            kinds[target] = "government"
    return kinds


def read(cc: str) -> Actors:
    """Read a country's ownership and parent links and work out its state actors."""
    state = countries.state_qid(cc)
    spec = countries.get(cc)
    if spec.international:
        # The Union's bodies and the organisations seated in it are holdings,
        # never state actors: no links are read, and nothing is owned through them.
        return Actors(state=state, kinds={state: "state"}, polities=frozenset({state}))
    polities = set(policy.polities_of(state))
    links: dict[str, dict[str, set[str]]] = {}
    types: dict[str, set[str]] = defaultdict(set)
    places: dict[str, set[str]] = defaultdict(set)
    jurisdictions: dict[str, set[str]] = defaultdict(set)
    # A dissolved ministry or agency (a predecessor state's) is no actor now.
    ended: set[str] = set()
    # A state treasury stands in the state's place: its links are read like the state's.
    names = [*countries.current_qids(cc), *sorted(q for q, k in spec.actors.items() if k == "state")]
    for prop in LINKS:
        pairs: dict[str, set[str]] = defaultdict(set)
        for side, name in ((side, name) for side in SIDES for name in names):
            args = {"side": side % {"s": name}, "p": prop}
            for r in wd.qlever(PAIRS % args):
                pairs[r["o"]].add(r["i"])
            for r in wd.qlever(TARGET_TYPES % args):
                types[r["o"]].add(r["t"])
            for r in wd.qlever(TARGET_PLACES % args):
                places[r["o"]].add(r["c"])
            for r in wd.qlever(TARGET_JURISDICTIONS % args):
                jurisdictions[r["o"]].add(r["c"])
            ended.update(r["o"] for r in wd.qlever(TARGET_ENDED % args))
        links[prop] = dict(pairs)
    closure = typegraph.of_classes({t for ts in types.values() for t in ts})
    not_government = NOT_GOVERNMENT | spec.not_government
    # Every current QID of the country is the state; the polity is the one
    # whose subdivisions are the regional tier.
    polities |= set(names)
    kinds = classify(state, polities, {q: ts for q, ts in types.items() if q not in ended}, places, closure,
                     not_government, jurisdictions)
    kinds.update({q: "state" for q in names})
    kinds.update(spec.actors)
    if "municipal" in spec.tiers:
        # A city that is also a first-level subdivision (a city-state) stays one.
        for unit in amlr.units(cc):
            kinds.setdefault(unit, "municipal")
    return Actors(state=state, kinds=kinds, links=links, polities=frozenset(polities), not_government=not_government)


def offered(actors: Actors, entity: dict[str, Any], chain: list[str] | None) -> list[str]:
    """The controllers a decision may choose among: the item's own owners, parents and chain, then the polities.

    A municipal unit is offered only from the item's own links or chain:
    every city of a country would swamp the list.
    """
    first = [*wd.values(entity, "P127"), *wd.values(entity, "P749"), *(chain[1:] if chain else [])]
    polities = sorted((q for q, k in actors.kinds.items() if k in ("state", "subdivision")),
                      key=lambda q: (actors.kinds[q] != "state", q))
    return list(dict.fromkeys([*first, *polities]))
