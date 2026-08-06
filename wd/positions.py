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
from typing import Dict, List, Optional, Set, Tuple

from requests import Session
from rigour.territories import get_territories

from wd.api import best_description, best_label, claim_qids, fetch_entities
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


def norm_label(text: str) -> str:
    text = text.casefold()
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
