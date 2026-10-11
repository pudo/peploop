"""Remember slow-moving reads for a while: class labels, place gazetteers, article leads.

Reach for this for context that changes on the scale of weeks, never for the
items being judged or edited -- those are state, read live through
`wikidata.fetch_items`, because our own writes change them. Each read is kept
under a key its caller names, in `memo`, for as long as the caller allows.
"""

from collections.abc import Callable, Iterable, Sequence
from typing import Any

from psycopg.types.json import Jsonb

from peploop import db, http
from peploop.wikidata import fetch_items, values_chunks

DAY = 24 * 3600


def cached(key: str, fn: Callable[[], Any], max_age: int = 30 * DAY) -> Any:
    """Return `fn()`, kept in `memo` under `key` for `max_age` seconds."""
    row = db.conn().execute(
        "SELECT body FROM memo WHERE key = %s AND fetched_at > now() - make_interval(secs => %s)",
        (key, max_age)).fetchone()
    if row is not None:
        return row[0]
    body = fn()
    db.conn().execute(
        "INSERT INTO memo (key, body) VALUES (%s, %s) ON CONFLICT (key)"
        " DO UPDATE SET body = EXCLUDED.body, fetched_at = now()", (key, Jsonb(body)))
    return body


def labels_of(qids: Iterable[str], langs: Sequence[str]) -> dict[str, dict[str, Any]]:
    """Labels in `langs` and the English description of class/place items, kept a month."""
    wanted = sorted({q for q in qids if q and q.startswith("Q")})
    out: dict[str, dict[str, Any]] = {}
    for chunk in values_chunks(wanted, 50):
        def fetch(chunk=chunk) -> dict[str, Any]:
            found = fetch_items(chunk, props="labels|descriptions")
            return {q: {"labels": {lg: o["value"] for lg, o in e.get("labels", {}).items() if lg in langs},
                        "description": e.get("descriptions", {}).get("en", {}).get("value")}
                    for q, e in found.items()}
        out.update(cached("labels:" + ",".join(langs) + ":" + "|".join(chunk), fetch))
    return out


def names_of(qids: Iterable[str], langs: Sequence[str] | None = None) -> dict[str, list[str]]:
    """Every label and alias of each item in `langs` (all languages if None), kept a month.

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


def lead(lang: str, title: str, limit: int = 1500) -> str:
    """The plain-text lead of a Wikipedia article, kept a week."""
    def fetch() -> str:
        data = http.get_json(f"https://{lang}.wikipedia.org/w/api.php", params={
            "action": "query", "prop": "extracts", "exintro": 1, "explaintext": 1,
            "redirects": 1, "titles": title, "format": "json"}, max_age=0)
        for page in data.get("query", {}).get("pages", {}).values():
            return (page.get("extract") or "")[:limit]
        return ""
    return cached(f"lead:{lang}:{title}", fetch, 7 * DAY)
