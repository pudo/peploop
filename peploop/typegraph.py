"""Close items' types over `P31` and `P279`, the way OpenSanctions reads them.

Reach for this instead of a SPARQL property path whenever the question is
"does this reach X anywhere among its values": one preferred `P31` hides the
normal-rank ones from `wdt:`, so a closure built on truthy values reports real
offices as untyped. Both lanes share one edge table, `type_edge`, so a class
walked for one country is not fetched again for the next, by either lane.

The rule for which claims count is nomenklatura's `WikidataClient._type_props`,
which types these items downstream: a deprecated claim is skipped, an ended
claim is skipped unless it is "historical country", and the walk stops at six
hops.
"""

from collections.abc import Iterable, Sequence
from typing import Any

from peploop import db, wikidata

TYPE_PROPS = ("P31", "P279")

#: An ended type claim is dropped, except this one: an office scoped to a
#: state that no longer exists is still an office of that state.
ALWAYS_KEPT = "Q3024240"  # historical country

#: Six hops, matching `nomenklatura.wikidata.model.Item.types`. A deeper walk
#: resolves types here that the consumer of these items will never see.
DEPTH = 6

#: Class edges change slowly but do change: a class gains a parent, or a
#: wrong one is deprecated. A month keeps a sweep from re-reading them.
MAX_AGE_DAYS = 30


def targets(entity: dict[str, Any]) -> list[str]:
    """The item's own `P31` and `P279` targets that count, in statement order."""
    out: list[str] = []
    for prop in TYPE_PROPS:
        for claim in entity.get("claims", {}).get(prop, []):
            if claim.get("rank") == "deprecated":
                continue
            value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
            if not isinstance(value, dict) or "id" not in value:
                continue
            if claim.get("qualifiers", {}).get("P582") and value["id"] != ALWAYS_KEPT:
                continue
            out.append(value["id"])
    return out


def edges(qids: Iterable[str]) -> dict[str, list[str]]:
    """The type edges of these items: from `type_edge` while fresh, fetched and stored otherwise."""
    wanted = list(dict.fromkeys(qids))
    if not wanted:
        return {}
    rows = db.conn().execute(
        "SELECT qid, targets FROM type_edge WHERE qid = ANY(%s)"
        " AND fetched_at > now() - make_interval(days => %s)", (wanted, MAX_AGE_DAYS)).fetchall()
    known = {qid: list(found) for qid, found in rows}
    missing = [qid for qid in wanted if qid not in known]
    if missing:
        found = wikidata.fetch_items(missing, props="claims")
        fresh = {qid: targets(found.get(qid, {})) for qid in missing}
        with db.conn().cursor() as cur:
            cur.executemany(
                "INSERT INTO type_edge (qid, targets, fetched_at) VALUES (%s, %s, now())"
                " ON CONFLICT (qid) DO UPDATE SET targets = EXCLUDED.targets, fetched_at = now()",
                list(fresh.items()))
        known.update(fresh)
    return known


def close(seeds: dict[str, list[str]]) -> dict[str, set[str]]:
    """Every type each seed reaches, from the seeds' own edges as given.

    The seeds' edges are passed in because they are usually the items being
    judged, read live with the rest of the item; everything above them is
    class structure and comes from `edges`. A seed counts as one of its own
    types, so asking whether a class is in some set answers for the class too.
    """
    known: dict[str, list[str]] = {}
    frontier = {t for found in seeds.values() for t in found}
    for _ in range(DEPTH):
        frontier -= set(known)
        if not frontier:
            break
        known.update(edges(sorted(frontier)))
        frontier = {t for qid in frontier for t in known.get(qid, [])}
    for qid in frontier:  # depth-capped: keep them as leaves, do not lose them
        known.setdefault(qid, [])
    known.update(seeds)
    out: dict[str, set[str]] = {}
    for qid in seeds:
        seen, level = {qid}, [qid]
        for _ in range(DEPTH):
            level = [t for x in level for t in known.get(x, []) if t not in seen]
            seen.update(level)
            if not level:
                break
        out[qid] = seen
    return out


def of_items(qids: Sequence[str]) -> dict[str, set[str]]:
    """The closure of items being judged: their own edges are re-read live, never cached."""
    seeds = list(dict.fromkeys(qids))
    fresh = wikidata.fetch_items(seeds, props="claims") if seeds else {}
    return close({qid: targets(fresh.get(qid, {})) for qid in seeds})


def of_classes(qids: Iterable[str]) -> dict[str, set[str]]:
    """The closure of classes, whose own edges may come from the cache too."""
    wanted = sorted(set(qids))
    return close(edges(wanted)) if wanted else {}
