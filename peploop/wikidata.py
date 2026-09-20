"""Read items, revisions and query results from Wikidata.

Items are state, so nothing here is cached by age: `fetch_items` always goes
to the network and the caller stores what comes back in the `item` table,
keyed by revision. Two API quirks are handled rather than worked around: a
transient error can arrive inside an HTTP 200 body, and a merged item comes
back under the QID it was merged into. The query service has a third of its
own, and `sparql` handles that one.
"""

import json
from collections.abc import Iterable, Sequence
from typing import Any
import time

from peploop import db, http

WD_API = "https://www.wikidata.org/w/api.php"
SPARQL_API = "https://query.wikidata.org/sparql"
CHUNK_SIZE = 50
MAX_ATTEMPTS = 3
ENTITY_PROPS = "info|sitelinks/urls|aliases|labels|descriptions|claims"

#: A grouped query over a whole country's offices runs for a minute or two,
#: which is longer than any action-API call is allowed to take. Measured: the
#: class descent for a 200-office country took 98 s from this host.
SPARQL_TIMEOUT = 300

#: About 150 `VALUES` items overflow the WDQS GET URI (HTTP 414), so anything
#: that pins a query to a list of QIDs asks in batches of this size.
VALUES_CHUNK = 120

ENTITY_URI = "http://www.wikidata.org/entity/"


def _chunks(qids: Iterable[str]) -> Iterable[list[str]]:
    todo = list(dict.fromkeys(qids))
    for i in range(0, len(todo), CHUNK_SIZE):
        yield todo[i : i + CHUNK_SIZE]


def values_chunks(qids: Iterable[str], size: int = VALUES_CHUNK) -> Iterable[list[str]]:
    """Split QIDs into batches small enough for a `VALUES` block in a GET."""
    todo = list(dict.fromkeys(qids))
    for i in range(0, len(todo), size):
        yield todo[i : i + size]


def values_block(qids: Sequence[str]) -> str:
    """Render QIDs as the body of a `VALUES` clause."""
    return " ".join(f"wd:{qid}" for qid in qids)


def sparql(query: str, max_age: int = 0) -> list[dict[str, str]]:
    """Run a SPARQL query, returning string bindings with entity URIs shortened.

    Reach for this when the question is about the corpus rather than about one
    item — every office a country scopes, how many people hold each. Answers
    are uncached by default because they are state; pass a `max_age` for the
    things that are not, such as a class hierarchy.

    Counts arrive as strings, so a caller reading `COUNT(...)` wants `int()`.
    """
    params = {"query": " ".join(query.split()), "format": "json"}
    raw = http.get_text(SPARQL_API, params=params, max_age=max_age,
                        timeout=SPARQL_TIMEOUT)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # WDQS reports a timeout as an "upstream request timeout" body under
        # HTTP 200, which raise_for_status cannot see; evict it or the retry
        # is served the same failure out of the cache for a week.
        db.cache_drop(SPARQL_API, params)
        raise RuntimeError(f"SPARQL non-JSON response: {raw[:80]!r}") from None
    rows: list[dict[str, str]] = []
    for binding in data["results"]["bindings"]:
        row = {}
        for var, val in binding.items():
            value = val["value"]
            if val["type"] == "uri" and value.startswith(ENTITY_URI):
                value = value.rsplit("/", 1)[1]
            row[var] = value
        rows.append(row)
    return rows


def fetch_items(qids: Iterable[str], props: str = ENTITY_PROPS) -> dict[str, dict[str, Any]]:
    """Fetch entity JSON for many QIDs, keyed by the QID that was asked for.

    A merged item is returned under the id it was requested with, while its
    `id` field names the redirect target; a missing or deleted item is absent
    from the result.
    """
    out: dict[str, dict[str, Any]] = {}
    for chunk in _chunks(qids):
        params = {
            "format": "json",
            "action": "wbgetentities",
            "ids": "|".join(chunk),
            "props": props,
        }
        for attempt in range(MAX_ATTEMPTS):
            data = http.get_json(WD_API, params=params, max_age=0)
            entities = data.get("entities")
            if entities is not None:
                # The API keys redirected items under the target id, so match
                # the request back up by both keys.
                by_id = {ent.get("id", key): ent for key, ent in entities.items()}
                for qid in chunk:
                    entity = entities.get(qid) or by_id.get(qid)
                    if entity is not None and "missing" not in entity:
                        out[qid] = entity
                break
            error = data.get("error", {})
            if error.get("code") == "no-such-entity":
                # Permanent, and one bad id fails the whole chunk in this API.
                if len(chunk) > 1:
                    for qid in chunk:
                        out.update(fetch_items([qid], props=props))
                break
            time.sleep(2.0 * (2**attempt))
        else:
            raise RuntimeError(f"Wikidata API kept failing for: {chunk}")
    return out


def lastrevids(qids: Iterable[str]) -> dict[str, int]:
    """Return the current revision id of each item, 50 items per request."""
    out: dict[str, int] = {}
    for chunk in _chunks(qids):
        params = {
            "format": "json",
            "action": "query",
            "prop": "info",
            "titles": "|".join(chunk),
        }
        data = http.get_json(WD_API, params=params, max_age=0)
        query = data.get("query", {})
        by_title: dict[str, int] = {}
        for page in query.get("pages", {}).values():
            if "missing" not in page and "lastrevid" in page:
                by_title[page["title"]] = page["lastrevid"]
        for redirect in query.get("redirects", []):
            if redirect["to"] in by_title:
                by_title[redirect["from"]] = by_title[redirect["to"]]
        for qid in chunk:
            if qid in by_title:
                out[qid] = by_title[qid]
    return out


def best_label(entity: dict[str, Any], langs: Iterable[str] = ("en", "mul")) -> str | None:
    """Pick a label, falling back en → mul → whatever the item has.

    Wikidata is moving language-independent names to the `mul` code, so many
    items no longer carry an `en` label at all.
    """
    labels = entity.get("labels", {})
    for lang in langs:
        if lang in labels:
            return labels[lang]["value"]
    for obj in labels.values():
        return obj["value"]
    return None


def claim_qids(entity: dict[str, Any], prop: str, include_deprecated: bool = True) -> list[str]:
    """List the item-valued targets of a property, in statement order.

    Every rank is read, not just the best one: a preferred statement hides the
    normal-rank ones from `wdt:`, which is how a `P31 = Q5` goes missing.
    """
    qids: list[str] = []
    for claim in entity.get("claims", {}).get(prop, []):
        if not include_deprecated and claim.get("rank") == "deprecated":
            continue
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(value, dict) and "id" in value:
            qids.append(value["id"])
    return qids


def claim_time(
    entity: dict[str, Any], prop: str, include_deprecated: bool = True
) -> list[tuple[str, int]]:
    """List the time values of a property as (ISO string, precision) pairs.

    Precision below 9 means the value is coarser than a year: "+2000-00-00T…"
    at precision 7 is the 20th century, not the year 2000.
    """
    times: list[tuple[str, int]] = []
    for claim in entity.get("claims", {}).get(prop, []):
        if not include_deprecated and claim.get("rank") == "deprecated":
            continue
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(value, dict) and "time" in value:
            times.append((value["time"], value.get("precision", 0)))
    return times


def sitelink_articles(entity: dict[str, Any]) -> list[tuple[str, str]]:
    """List (language, title) for the item's Wikipedia sitelinks only."""
    out: list[tuple[str, str]] = []
    for site, link in entity.get("sitelinks", {}).items():
        if not site.endswith("wiki") or site in NON_WIKIPEDIA_SITES:
            continue
        out.append((site[:-4].replace("_", "-"), link["title"]))
    return out


NON_WIKIPEDIA_SITES = {
    "commonswiki",
    "specieswiki",
    "metawiki",
    "mediawikiwiki",
    "wikidatawiki",
    "sourceswiki",
    "foundationwiki",
    "incubatorwiki",
    "outreachwiki",
}
