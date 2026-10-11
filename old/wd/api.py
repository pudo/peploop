"""Thin readers for the Wikidata action API and SPARQL endpoint.

Returns raw entity JSON rather than an object model — scripts pick out what
they need, and the condensed rendering for LLM review happens elsewhere.
"""

import json
import time
from typing import Any, Dict, Iterable, List, Optional

from requests import Session

from wd.http import drop_cache, get_text

WD_API = "https://www.wikidata.org/w/api.php"
SPARQL_API = "https://query.wikidata.org/sparql"

# wbgetentities accepts at most 50 ids per call.
CHUNK_SIZE = 50
# Wikidata hides transient errors (DB lag, rate limits) inside HTTP 200
# bodies, so status-code retries never see them; retry in-band.
MAX_ATTEMPTS = 3

ENTITY_PROPS = "info|sitelinks/urls|aliases|labels|descriptions|claims|datatype"


def fetch_entities(
    session: Session,
    qids: Iterable[str],
    props: str = ENTITY_PROPS,
    max_age: Optional[int] = None,
) -> Dict[str, Dict[str, Any]]:
    """Fetch entity JSON for many QIDs, chunked. Missing/deleted QIDs are
    absent from the result; merged items appear under their redirect target's
    id (callers can detect this via entity["id"] != requested qid)."""
    out: Dict[str, Dict[str, Any]] = {}
    todo = list(dict.fromkeys(qids))
    for i in range(0, len(todo), CHUNK_SIZE):
        chunk = todo[i : i + CHUNK_SIZE]
        params = {
            "format": "json",
            "action": "wbgetentities",
            "ids": "|".join(chunk),
            "props": props,
        }
        kwargs = {} if max_age is None else {"max_age": max_age}
        for attempt in range(MAX_ATTEMPTS):
            raw = get_text(session, WD_API, params=params, **kwargs)
            data = json.loads(raw)
            entities = data.get("entities")
            if entities is not None:
                for qid, entity in entities.items():
                    if "missing" in entity:
                        continue
                    out[entity.get("id", qid)] = entity
                break
            error = data.get("error", {})
            if error.get("code") == "no-such-entity":
                # Permanent: one bad QID fails the whole chunk in this API;
                # drop to per-id fetches so the rest of the chunk survives.
                if len(chunk) > 1:
                    for qid in chunk:
                        out.update(fetch_entities(session, [qid], props=props))
                break
            time.sleep(2.0 * (2**attempt))
        else:
            raise RuntimeError(f"Wikidata API kept failing for: {chunk}")
    return out


def sparql(session: Session, query: str, max_age: Optional[int] = None) -> List[Dict[str, str]]:
    """Run a SPARQL query, returning plain-string bindings with entity URIs
    shortened to bare QIDs."""
    params = {"query": " ".join(query.split()), "format": "json"}
    kwargs = {} if max_age is None else {"max_age": max_age}
    raw = get_text(session, SPARQL_API, params=params, **kwargs)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # WDQS can return "upstream request timeout" style bodies; make sure
        # they don't get served from cache on the retry.
        drop_cache(SPARQL_API, params)
        raise RuntimeError(f"SPARQL non-JSON response: {raw[:80]!r}")
    rows: List[Dict[str, str]] = []
    for binding in data["results"]["bindings"]:
        row = {}
        for var, val in binding.items():
            value = val["value"]
            if val["type"] == "uri" and value.startswith("http://www.wikidata.org/entity/"):
                value = value.rsplit("/", 1)[1]
            row[var] = value
        rows.append(row)
    return rows


def best_label(entity: Dict[str, Any], langs: Iterable[str] = ("en", "mul")) -> Optional[str]:
    """Pick a label with en → mul fallback (Wikidata is migrating
    language-independent names to the `mul` code; many items no longer have
    an `en` label at all)."""
    labels = entity.get("labels", {})
    for lang in langs:
        if lang in labels:
            return labels[lang]["value"]
    for obj in labels.values():
        return obj["value"]
    return None


def best_description(entity: Dict[str, Any], langs: Iterable[str] = ("en", "mul")) -> Optional[str]:
    descriptions = entity.get("descriptions", {})
    for lang in langs:
        if lang in descriptions:
            return descriptions[lang]["value"]
    return None


def claim_qids(entity: Dict[str, Any], prop: str, include_deprecated: bool = True) -> List[str]:
    """Item-valued claim targets for a property, in statement order."""
    qids: List[str] = []
    for claim in entity.get("claims", {}).get(prop, []):
        if not include_deprecated and claim.get("rank") == "deprecated":
            continue
        snak = claim.get("mainsnak", {})
        value = snak.get("datavalue", {}).get("value")
        if isinstance(value, dict) and "id" in value:
            qids.append(value["id"])
    return qids


def qualifier_time(claim: Dict[str, Any], prop: str) -> Optional[str]:
    """First time-qualifier value (e.g. P580/P582) as the raw +ISO string."""
    for snak in claim.get("qualifiers", {}).get(prop, []):
        value = snak.get("datavalue", {}).get("value")
        if isinstance(value, dict) and "time" in value:
            return value["time"]
    return None
