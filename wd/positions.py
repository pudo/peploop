"""Resolve a position name + country to Wikidata position items.

Reach for this whenever some external source names an office ("Minister of
Finance" + by, "Deputy of the Kursk Oblast Duma") and you need the actual
Wikidata item behind it — config normalization, per-person office narrowing,
checking whether an item must be created. Matching is two-signal: a
candidate counts as strong only when its label/alias matches a query variant
AND its own P17/P1001 resolves to the expected country (directly, or one
P17 hop up — regional bodies carry the subdivision, not the state).
"""

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Dict, List, Optional, Sequence, Set, Tuple

from normality import ascii_text
from requests import Session
from rigour.territories import get_territories

from wd.api import best_description, best_label, claim_qids, fetch_entities, sparql
from wd.http import get_text

WD_API = "https://www.wikidata.org/w/api.php"
LIST_ARTICLE = "Q13406463"

# Wikidata prefers "member of the X" phrasing for seats; sources often say
# "Deputy of" / "Senator of" / plurals:
SYNONYMS = [
    (re.compile(r"^deputy of the\b", re.I), "member of the"),
    (re.compile(r"^senator of (?:the )?(?:republic of )?", re.I),
     "member of the Senate of "),
    (re.compile(r"^members of\b", re.I), "member of"),
    (re.compile(r"\bjudge at the\b", re.I), "judge of the"),
]


@dataclass
class Candidate:
    qid: str
    label: str
    description: Optional[str]
    types: List[str]
    country_qids: List[str]
    label_match: bool
    country_match: bool
    is_list: bool


@dataclass
class Lookup:
    #: matched | label-only | ambiguous | unmatched
    status: str
    #: the unique strong (or unique label-only) candidate's QID
    resolved_qid: Optional[str] = None
    candidates: List[Candidate] = field(default_factory=list)
    queries: List[str] = field(default_factory=list)


@lru_cache(maxsize=1)
def _territory_maps() -> Tuple[Dict[str, str], Dict[str, Tuple[str, ...]]]:
    qids: Dict[str, str] = {}
    names: Dict[str, Set[str]] = {}
    for t in get_territories():
        if t.qid is None:
            continue
        qids.setdefault(t.code, t.qid)
        bucket = names.setdefault(t.code, set())
        for n in {t.name, t.full_name}:
            if n:
                bucket.add(n.casefold())
    return qids, {c: tuple(sorted(ns)) for c, ns in names.items()}


def country_qid(code: Optional[str]) -> Optional[str]:
    return _territory_maps()[0].get(code or "")


def country_names(code: Optional[str]) -> Tuple[str, ...]:
    return _territory_maps()[1].get(code or "", ())


def fold(text: str) -> str:
    """Casefolded ASCII, so a diacritic or a dash cannot break a comparison.

    Reach for this before comparing any two office names. The plain
    `[^a-z0-9]` strip that used to do this job deleted every non-ASCII
    character rather than transliterating it, so `Łódź Voivodeship` normalised
    to `d voivodeship` and could never equal `Lodz Voivodeship`.
    """
    return (ascii_text(text) or "").casefold()


def norm_label(text: str) -> str:
    text = fold(text)
    text = re.sub(r"\b(the|of)\b", " ", text)
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def query_variants(name: str, country: Optional[str]) -> List[str]:
    """Search strings for an office name: synonym rewrites, plus
    country-suffixed forms when the name doesn't mention the country
    ("Minister of Finance" + by → "Minister of Finance of Belarus")."""
    queries = [name]
    for regex, repl in SYNONYMS:
        variant = regex.sub(repl, name)
        if variant != name:
            queries.append(variant)
    cnames = country_names(country)
    if cnames and not any(c in name.casefold() for c in cnames):
        shortest = min(cnames, key=len)
        queries.extend(f"{q} of {shortest.title()}" for q in list(queries))
    return queries


def _search(session: Session, query: str, limit: int) -> List[str]:
    raw = get_text(
        session,
        WD_API,
        params={
            "action": "wbsearchentities", "format": "json", "type": "item",
            "language": "en", "uselang": "en", "limit": str(limit),
            "search": query,
        },
    )
    return [r["id"] for r in json.loads(raw).get("search", [])]


def lookup_position(
    session: Session,
    name: str,
    country: Optional[str] = None,
    extra_names: Tuple[str, ...] = (),
    # Generic office labels ("Minister of Health") exist for dozens of
    # countries; the right country's item often sits deep in the ranking:
    limit: int = 30,
    max_candidates: int = 40,
) -> Lookup:
    """Find the Wikidata item for an office named in text.

    `country` is an ISO code used both to expand the search ("of Belarus")
    and as the agreement gate. `extra_names` adds source-specific aliases to
    the query set. Items typed ONLY as Wikimedia list articles never match
    strongly; dual-typed ones do, but carry `is_list=True` for review.
    """
    queries = list(dict.fromkeys(query_variants(name, country) + list(extra_names)))
    expected = country_qid(country)
    qids: List[str] = []
    for q in queries:
        qids.extend(x for x in _search(session, q, limit) if x not in qids)
    result = Lookup(status="unmatched", queries=queries)
    if not qids:
        return result

    entities = fetch_entities(
        session, qids[:max_candidates], props="labels|aliases|descriptions|claims")
    target_norms = {norm_label(q) for q in queries}
    for qid in qids[:max_candidates]:
        entity = entities.get(qid)
        if entity is None or entity["id"] != qid:
            continue
        label = best_label(entity) or ""
        aliases = {
            a["value"].casefold()
            for lst in entity.get("aliases", {}).values() for a in lst
        }
        cqids = set(claim_qids(entity, "P1001")) | set(claim_qids(entity, "P17"))
        types = claim_qids(entity, "P31")
        result.candidates.append(Candidate(
            qid=qid,
            label=label,
            description=best_description(entity),
            types=types,
            country_qids=sorted(cqids),
            label_match=norm_label(label) in target_norms
            or any(norm_label(a) in target_norms for a in aliases),
            country_match=expected is not None and expected in cqids,
            is_list=LIST_ARTICLE in types,
        ))

    # Second signal, transitive: a regional body's P1001 is the subdivision
    # (Kursk Oblast), whose own P17 is the country.
    if expected is not None:
        indirect: Set[str] = set()
        for c in result.candidates:
            if not c.country_match:
                indirect.update(q for q in c.country_qids if q != expected)
        if indirect:
            parents = {
                qid: set(claim_qids(e, "P17"))
                for qid, e in fetch_entities(session, indirect, props="claims").items()
            }
            for c in result.candidates:
                if not c.country_match:
                    c.country_match = any(
                        expected in parents.get(q, set()) for q in c.country_qids
                    )

    pure_list = lambda c: c.is_list and c.types == [LIST_ARTICLE]  # noqa: E731
    strong = [c for c in result.candidates
              if c.label_match and c.country_match and not pure_list(c)]
    label_only = [c for c in result.candidates
                  if c.label_match and not c.country_qids and not pure_list(c)]
    if len(strong) == 1:
        result.status, result.resolved_qid = "matched", strong[0].qid
    elif not strong and len(label_only) == 1:
        result.status, result.resolved_qid = "label-only", label_only[0].qid
    elif result.candidates:
        result.status = "ambiguous"
    return result


def members_holding(
    session: Session, people: Sequence[str], target: str
) -> Set[str]:
    """Which of these people Wikidata already records in this position.

    The member-side counterpart to `holder_counts`: reach for it when a cohort
    is small and the office is not. Asking for the office's holders instead
    would pull 5,497 rows for a national legislature to intersect against a
    forty-person category, and the ones that matter are the intersection.

    Read at `max_age=0` — this is the state our own batches change, and a
    cached answer is how already-existing statements get re-proposed.
    """
    held: Set[str] = set()
    people = list(people)
    # ~150 VALUES items overflow the WDQS GET URI (HTTP 414).
    for start in range(0, len(people), 120):
        chunk = people[start:start + 120]
        values = " ".join(f"wd:{q}" for q in chunk)
        rows = sparql(session, f"""SELECT DISTINCT ?p WHERE {{
          VALUES ?p {{ {values} }} ?p p:P39/ps:P39 wd:{target} .
        }}""", max_age=0)
        held.update(row["p"] for row in rows)
    return held


def subclass_held(
    session: Session, target: str, people: Sequence[str]
) -> Dict[str, int]:
    """Which `P279` children of a target the cohort's own members hold instead.

    Reach for this before scoping any run against a single target, because a
    target that is a *class* of offices rather than a seat produces a gap on
    every member and every property the item audit reads looks right.
    `Q20706330` "United States Supreme Court justice" is `P31 Q4164871`,
    `P1001 Q30`, `P361` the Court, emittable, defect-free — and the `P279`
    parent of `Q11144` Associate Justice, which its members actually hold: the
    category read 1 of 101 held and 12 to enrich, and all 12 held the child.

    Measured against the members rather than by comparing holder counts, so it
    states a fact about this cohort instead of a heuristic about the corpus:
    the answer is "N of the people you are about to pay to read already hold a
    child of your target". An empty dict is the ordinary case.
    """
    counts: Dict[str, int] = {}
    people = list(people)
    # ~150 VALUES items overflow the WDQS GET URI (HTTP 414).
    for start in range(0, len(people), 120):
        values = " ".join(f"wd:{q}" for q in people[start:start + 120])
        rows = sparql(session, f"""SELECT ?child (COUNT(DISTINCT ?p) AS ?n) WHERE {{
          VALUES ?p {{ {values} }}
          ?p p:P39/ps:P39 ?child .
          ?child p:P279/ps:P279 wd:{target} .
        }} GROUP BY ?child""", max_age=0)
        for row in rows:
            counts[row["child"]] = counts.get(row["child"], 0) + int(row["n"])
    return counts


def holder_counts(session: Session, qids: Sequence[str]) -> Dict[str, int]:
    """Holders per item, any rank — the gate that is not in `position.py`.

    `wd_peps` reaches a position through people's P39, so an item nobody holds
    is never emitted however well-formed it is. Counted with `p:P39/ps:P39`
    because `wdt:` would report only best-rank holders.
    """
    counts: Dict[str, int] = {q: 0 for q in qids}
    for start in range(0, len(qids), 120):
        chunk = list(qids)[start:start + 120]
        values = " ".join(f"wd:{q}" for q in chunk)
        rows = sparql(session, f"""SELECT ?pos (COUNT(DISTINCT ?h) AS ?n) WHERE {{
          VALUES ?pos {{ {values} }} OPTIONAL {{ ?h p:P39/ps:P39 ?pos }}
        }} GROUP BY ?pos""", max_age=0)
        for row in rows:
            counts[row["pos"]] = int(row["n"])
    return counts


#: Function words across the languages a country's offices are labelled in.
#: Dropped before scoring so "Minister of Family and Social Policy" and
#: "Minister Rodziny i Polityki Społecznej" are compared on their content.
STOPWORDS = frozenset("""
a an and at by for from in of on or the to with
i w we na do dla oraz z za o po
de del la el las los y en al a
v ve na pro pri se pro pod pri pre
i v na s so po dlya iz
der die das des dem und von zu im
du des le les et aux
""".split())

#: Every label and alias of every position item scoped to one state. `p:P31/
#: ps:P31` and not `wdt:P31`, for the reason `wd/gazetteer.py` gives: one
#: preferred value hides the normal-rank ones and a live office reads as
#: not-a-position.
COUNTRY_NAMES = """SELECT ?pos ?name WHERE {
  ?pos p:P31/ps:P31/wdt:P279* wd:Q4164871 .
  { ?pos wdt:P17 wd:%(country)s } UNION { ?pos wdt:P1001 wd:%(country)s }
  { ?pos rdfs:label ?name } UNION { ?pos skos:altLabel ?name }
}"""


def tokens(text: str) -> Set[str]:
    """An office name as its content tokens, folded and stopword-free.

    Falls back to the un-stripped tokens when stripping would empty the set:
    an office genuinely called "The Speaker" must still be comparable.
    """
    parts = [t for t in re.split(r"[^a-z0-9]+", fold(text)) if t]
    content = {t for t in parts if t not in STOPWORDS}
    return content or set(parts)


@dataclass
class Hit:
    """One indexed office a query reached, with why it scored."""

    qid: str
    #: The label or alias that scored best — what to show a reviewer.
    name: str
    score: float
    #: Does the candidate name *everything* the query names? The asymmetry is
    #: load-bearing: "Mayor of Chełm" against the generic `Q177529 mayor` has
    #: the containment the other way round, and writing a specific mayoralty
    #: onto the occupation class is the trap `resolve_offices` already refuses.
    covers: bool


@dataclass
class OfficeIndex:
    """Every name of every position item in one country, ready to search.

    Reach for this instead of `wbsearchentities` whenever the country is known.
    The API search is an English prefix match capped at 30 hits, which misses a
    renamed office, a natively-labelled one and anything spelled with a
    different dash; this carries ~13 names per item in every language, and the
    country gate is satisfied by construction because the set was selected on
    it.

    It ranks, it does not decide. Precision is the reranker's job — see
    `prompts/office_rerank.md`.
    """

    country_qid: str
    names: Dict[str, List[str]] = field(default_factory=dict)
    #: token -> the QIDs carrying it, so a query touches a few hundred
    #: candidates rather than Spain's 115,551 names.
    postings: Dict[str, Set[str]] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.names)

    def add(self, qid: str, name: str) -> None:
        self.names.setdefault(qid, []).append(name)
        for token in tokens(name):
            self.postings.setdefault(token, set()).add(qid)

    def search(self, queries: Sequence[str], limit: int = 20) -> List[Hit]:
        """The best-scoring offices for any of these query strings.

        `queries` is the office name plus whatever search terms the enrichment
        pass proposed for it — the native form, the bare proper noun, the kind
        on its own. Tuned for recall: a shortlist that omits the right office
        is invisible downstream, because the reranker only sees what it is
        given and a miss reads as "this office needs creating".
        """
        best: Dict[str, Hit] = {}
        for query in queries:
            qt = tokens(query)
            if not qt:
                continue
            reachable: Set[str] = set()
            for token in qt:
                reachable.update(self.postings.get(token, ()))
            for qid in reachable:
                for name in self.names.get(qid, ()):
                    nt = tokens(name)
                    if not nt:
                        continue
                    score = len(qt & nt) / len(qt | nt)
                    hit = best.get(qid)
                    if hit is None or score > hit.score:
                        best[qid] = Hit(qid=qid, name=name, score=score,
                                        covers=qt <= nt)
        ranked = sorted(best.values(),
                        key=lambda h: (h.covers, h.score, h.qid), reverse=True)
        return ranked[:limit]


def index_for_country(
    session: Session, country_qid: str, *, max_age: Optional[int] = 0
) -> OfficeIndex:
    """Build the searchable name index for one country's position items.

    One SPARQL, names only — deliberately *not* `wd/gazetteer.py:describe`,
    which costs an entity fetch, a shape verification and a holder count per
    item. Only the shortlist earns that. Measured: Poland 4,331 names over 322
    items in 19s, Spain 115,551 over 13,197 in 29s.
    """
    index = OfficeIndex(country_qid=country_qid)
    rows = sparql(session, COUNTRY_NAMES % {"country": country_qid},
                  max_age=max_age)
    for row in rows:
        index.add(row["pos"], row["name"])
    return index


def holdings(session: Session, people: Sequence[str]) -> Dict[str, Set[str]]:
    """Every position each of these people is recorded in.

    The bucket counterpart to `members_holding`, which can only ask about one
    office. A `bucket` spec has no single target — the question is "which of
    the country's offices does this person already hold", and the answer is
    three things at once: the backtest set (anyone with at least one), the
    ground truth to score a choice against, and the set to withhold from the
    dossier so the model cannot read the answer.

    `p:P39/ps:P39`, so a normal-rank tenure behind a preferred one still
    counts. Read at `max_age=0`: this is state our own batches change.
    """
    out: Dict[str, Set[str]] = {q: set() for q in people}
    people = list(people)
    # ~150 VALUES items overflow the WDQS GET URI (HTTP 414).
    for start in range(0, len(people), 120):
        values = " ".join(f"wd:{q}" for q in people[start:start + 120])
        rows = sparql(session, f"""SELECT ?p ?pos WHERE {{
          VALUES ?p {{ {values} }} ?p p:P39/ps:P39 ?pos .
        }}""", max_age=0)
        for row in rows:
            out.setdefault(row["p"], set()).add(row["pos"])
    return out
