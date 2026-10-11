"""Read Wikidata and Wikipedia for peptree, with a cache of its own.

Live state (the items being repaired, their holders) goes through peploop's
`wikidata` module, which never caches. What is cached here is the slow-moving
context: class edges, labels of classes and places, and article leads. That
cache is `ptree_cache`/`ptree_type_edge`, never peploop's `http_cache` or
`type_edge`, so nothing here writes to peploop's tables.
"""

import json
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from psycopg.types.json import Jsonb

from peploop import db as pdb
from peploop import http
from peploop.wikidata import (  # noqa: F401  (re-exported for peptree modules)
    best_label, claim_qids, fetch_items, sparql, values_block, values_chunks,
)

SCHEMA = Path(__file__).resolve().parent / "schema.sql"
DAY = 24 * 3600
#: Label languages, best first. English and `mul` until a country is chosen;
#: `country.get` puts the country's own languages between them.
LANGS: tuple[str, ...] = ("en", "mul")


def set_langs(langs: Sequence[str]) -> None:
    """Make `langs` the label languages for this process (one country per run)."""
    global LANGS
    LANGS = tuple(dict.fromkeys(langs))


def conn():
    return pdb.conn()


_ready = False


def init() -> None:
    """Create the `ptree_` tables if they are missing, and peploop's (the send ledger among them)."""
    global _ready
    if not _ready:
        pdb.init_schema()
        conn().execute(SCHEMA.read_text())
        _ready = True


def cached(key: str, fn: Callable[[], Any], max_age: int = 30 * DAY) -> Any:
    """Return `fn()`, memoised in `ptree_cache` for `max_age` seconds."""
    init()
    row = conn().execute(
        "SELECT body FROM ptree_cache WHERE key = %s AND fetched_at > now() - make_interval(secs => %s)",
        (key, max_age)).fetchone()
    if row is not None:
        return row[0]
    body = fn()
    conn().execute(
        "INSERT INTO ptree_cache (key, body) VALUES (%s, %s) ON CONFLICT (key)"
        " DO UPDATE SET body = EXCLUDED.body, fetched_at = now()", (key, Jsonb(body)))
    return body


def label(entity: dict[str, Any]) -> str:
    return best_label(entity, LANGS) or ""


def labels_of(qids: Iterable[str]) -> dict[str, dict[str, Any]]:
    """Labels and the English description of class/place items, cached a month."""
    wanted = sorted({q for q in qids if q and q.startswith("Q")})
    out: dict[str, dict[str, Any]] = {}
    for chunk in values_chunks(wanted, 50):
        def fetch(chunk=chunk) -> dict[str, Any]:
            found = fetch_items(chunk, props="labels|descriptions")
            return {q: {"labels": {lg: o["value"] for lg, o in e.get("labels", {}).items() if lg in LANGS},
                        "description": e.get("descriptions", {}).get("en", {}).get("value")}
                    for q, e in found.items()}
        out.update(cached("labels:" + ",".join(LANGS) + ":" + "|".join(chunk), fetch))
    return out


def names_of(qids: Iterable[str], langs: Sequence[str] | None = None) -> dict[str, list[str]]:
    """Every label and alias of each item in `langs` (all languages if None), cached a month.

    Reach for this when a word list must come from data: the names of a class
    in the country's languages are what its offices' labels say.
    """
    wanted = sorted({q for q in qids if q and q.startswith("Q")})
    key_langs = "*" if langs is None else ",".join(langs)
    out: dict[str, list[str]] = {}
    for chunk in values_chunks(wanted, 50):
        def fetch(chunk=chunk) -> dict[str, list[str]]:
            found = fetch_items(chunk, props="labels|aliases")
            res = {}
            for q, e in found.items():
                names = [o["value"] for lg, o in e.get("labels", {}).items() if langs is None or lg in langs]
                names += [a["value"] for lg, al in e.get("aliases", {}).items() if langs is None or lg in langs
                          for a in al]
                res[q] = list(dict.fromkeys(names))
            return res
        out.update(cached(f"names:{key_langs}:" + "|".join(chunk), fetch))
    return out


def name(info: dict[str, Any] | None) -> str:
    if not info:
        return ""
    labels = info.get("labels", {})
    for lg in LANGS:
        if lg in labels:
            return labels[lg]
    return next(iter(labels.values()), "")


# --- type closure -------------------------------------------------------------
# Copied from peploop.positions.type_closure (that one stores edges in
# peploop's `type_edge` table, which peptree must not write).

CLOSURE_DEPTH = 6


def _targets(entity: dict[str, Any]) -> list[str]:
    out = []
    for prop in ("P31", "P279"):
        for claim in entity.get("claims", {}).get(prop, []):
            if claim.get("rank") == "deprecated":
                continue
            value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
            if isinstance(value, dict) and "id" in value and not claim.get("qualifiers", {}).get("P582"):
                out.append(value["id"])
    return out


def _edges(qids: Sequence[str]) -> dict[str, list[str]]:
    init()
    rows = conn().execute(
        "SELECT qid, targets FROM ptree_type_edge WHERE qid = ANY(%s) AND fetched_at > now() - interval '30 days'",
        (list(qids),)).fetchall()
    known = {q: list(t) for q, t in rows}
    missing = [q for q in qids if q not in known]
    if missing:
        found = fetch_items(missing, props="claims")
        fresh = {q: _targets(found.get(q, {})) for q in missing}
        with conn().cursor() as cur:
            cur.executemany(
                "INSERT INTO ptree_type_edge (qid, targets) VALUES (%s, %s) ON CONFLICT (qid)"
                " DO UPDATE SET targets = EXCLUDED.targets, fetched_at = now()", list(fresh.items()))
        known.update(fresh)
    return known


def closure(seeds: dict[str, list[str]]) -> dict[str, set[str]]:
    """Every type each seed reaches over `P31`/`P279`, from given seed edges.

    The seeds' own edges are passed in (read live, with the item); everything
    above them is class structure and comes from the edge cache. A seed counts
    as one of its own types.
    """
    edges: dict[str, list[str]] = {}
    frontier = {t for ts in seeds.values() for t in ts}
    for _ in range(CLOSURE_DEPTH):
        frontier -= set(edges)
        if not frontier:
            break
        edges.update(_edges(sorted(frontier)))
        frontier = {t for q in frontier for t in edges.get(q, [])}
    edges.update(seeds)
    out = {}
    for qid in seeds:
        seen, level = {qid}, [qid]
        for _ in range(CLOSURE_DEPTH):
            level = [t for x in level for t in edges.get(x, []) if t not in seen]
            seen.update(level)
            if not level:
                break
        out[qid] = seen
    return out


def class_closure(qids: Iterable[str]) -> dict[str, set[str]]:
    """The closure of classes (not of the items being judged)."""
    qs = sorted(set(qids))
    return closure(_edges(qs)) if qs else {}


# --- Wikipedia ----------------------------------------------------------------

def lead(lang: str, title: str, limit: int = 1500) -> str:
    """The plain-text lead of an article, cached a week."""
    def fetch() -> str:
        data = http.get_json(f"https://{lang}.wikipedia.org/w/api.php", params={
            "action": "query", "prop": "extracts", "exintro": 1, "explaintext": 1,
            "redirects": 1, "titles": title, "format": "json"}, max_age=0)
        for page in data.get("query", {}).get("pages", {}).values():
            return (page.get("extract") or "")[:limit]
        return ""
    return cached(f"lead:{lang}:{title}", fetch, 7 * DAY)


def dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)
