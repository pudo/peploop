"""Read items and revisions from the Wikidata action API.

Items are state, so nothing here is cached by age: `fetch_items` always goes
to the network and the caller stores what comes back in the `item` table,
keyed by revision. Two API quirks are handled rather than worked around: a
transient error can arrive inside an HTTP 200 body, and a merged item comes
back under the QID it was merged into.
"""

import time
from collections.abc import Iterable
from typing import Any

from peploop import http

WD_API = "https://www.wikidata.org/w/api.php"
CHUNK_SIZE = 50
MAX_ATTEMPTS = 3
ENTITY_PROPS = "info|sitelinks/urls|aliases|labels|descriptions|claims"


def _chunks(qids: Iterable[str]) -> Iterable[list[str]]:
    todo = list(dict.fromkeys(qids))
    for i in range(0, len(todo), CHUNK_SIZE):
        yield todo[i : i + CHUNK_SIZE]


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
