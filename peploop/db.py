"""Talk to the Postgres database that holds every bit of peploop state.

Connections are per thread: the driver runs stages under a thread pool and a
psycopg connection is not safe to share. Everything is autocommit, because a
stage is idempotent and there is no cross-row invariant worth a transaction.
"""

import hashlib
import json
import os
import threading
from pathlib import Path
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

DATABASE_URL = os.environ.get("PEPLOOP_DATABASE_URL", "postgresql:///peploop")
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

_local = threading.local()


def conn() -> psycopg.Connection:
    """Return this thread's connection, opening it on first use."""
    existing = getattr(_local, "conn", None)
    if existing is None or existing.closed:
        existing = psycopg.connect(DATABASE_URL, autocommit=True)
        _local.conn = existing
    return existing


#: The advisory lock schema.sql is applied under: its `ALTER`s each take an
#: `AccessExclusiveLock`, and two commands started together would deadlock.
SCHEMA_LOCK = "peploop-schema"


def init_schema() -> None:
    """Apply schema.sql once per change to it, under a lock.

    Every command calls this, so the common case must take no lock at all: the
    file's hash is compared with the one recorded when it was last applied,
    and only a changed file is applied -- by one process, while any other
    waits on the advisory lock and then finds the hash already recorded.
    """
    text = SCHEMA_PATH.read_text()
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if _schema_hash() == digest:
        return
    connection = conn()
    with connection.transaction():
        connection.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (SCHEMA_LOCK,))
        if _schema_hash() == digest:
            return
        connection.execute(text)
        connection.execute(
            "INSERT INTO schema_version (id, hash, applied_at) VALUES (true, %s, now())"
            " ON CONFLICT (id) DO UPDATE SET hash = EXCLUDED.hash, applied_at = now()",
            (digest,),
        )


def _schema_hash() -> str | None:
    """The hash of the schema.sql last applied, or None on a database that has none."""
    row = conn().execute(
        "SELECT to_regclass('schema_version') IS NOT NULL"
    ).fetchone()
    if not row[0]:
        return None
    found = conn().execute("SELECT hash FROM schema_version").fetchone()
    return None if found is None else found[0]


def params_hash(params: dict[str, Any] | None) -> str:
    """Hash a query's parameters into the second half of the cache key."""
    blob = json.dumps(params or {}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()


def cache_get(url: str, params: dict[str, Any] | None, max_age: int) -> str | None:
    """Return a cached response body younger than `max_age` seconds, if any."""
    if max_age <= 0:
        return None
    row = conn().execute(
        "SELECT body FROM http_cache WHERE url = %s AND params_hash = %s"
        " AND fetched_at > now() - make_interval(secs => %s)",
        (url, params_hash(params), max_age),
    ).fetchone()
    return None if row is None else row[0]


def cache_put(url: str, params: dict[str, Any] | None, body: str) -> None:
    """Store a response body under (url, params)."""
    conn().execute(
        "INSERT INTO http_cache (url, params_hash, params, body, fetched_at)"
        " VALUES (%s, %s, %s, %s, now()) ON CONFLICT (url, params_hash)"
        " DO UPDATE SET body = EXCLUDED.body, fetched_at = now(),"
        " params = EXCLUDED.params",
        (url, params_hash(params), Jsonb(params or {}), body),
    )


def cache_drop(url: str, params: dict[str, Any] | None = None) -> None:
    """Forget a cached response, e.g. one that turned out not to be JSON."""
    conn().execute(
        "DELETE FROM http_cache WHERE url = %s AND params_hash = %s",
        (url, params_hash(params)),
    )


def upsert_person(qid: str, country: str | None = None) -> bool:
    """Queue a person, and report whether the row was new.

    A person already past `queued` keeps their status: re-seeding must not
    send someone back through the pipeline. The country is filled only where
    it is still null, so someone two countries both claim stays with the run
    that found them first rather than flipping on every re-seed.
    """
    row = conn().execute(
        "INSERT INTO person (qid, country) VALUES (%s, %s)"
        " ON CONFLICT (qid) DO NOTHING RETURNING qid",
        (qid, country),
    ).fetchone()
    if row is None and country is not None:
        conn().execute(
            "UPDATE person SET country = %s WHERE qid = %s AND country IS NULL",
            (country, qid),
        )
    return row is not None


def upsert_membership(qid: str, category: str, lang: str) -> None:
    """Record that a seed category admitted a person."""
    conn().execute(
        "INSERT INTO membership (qid, category, lang) VALUES (%s, %s, %s)"
        " ON CONFLICT (qid, category, lang) DO UPDATE SET seen_at = now()",
        (qid, category, lang),
    )


def set_person_status(qid: str, status: str, error: str | None = None) -> None:
    """Move a person to a new pipeline status, recording any failure text."""
    conn().execute(
        "UPDATE person SET status = %s, error = %s, updated_at = now() WHERE qid = %s",
        (status, error, qid),
    )


def upsert_item(qid: str, lastrevid: int | None, entity: dict[str, Any]) -> None:
    """Store a Wikidata entity as the item state for `qid`."""
    conn().execute(
        "INSERT INTO item (qid, lastrevid, json, fetched_at) VALUES (%s, %s, %s, now())"
        " ON CONFLICT (qid) DO UPDATE SET lastrevid = EXCLUDED.lastrevid,"
        " json = EXCLUDED.json, fetched_at = now()",
        (qid, lastrevid, Jsonb(entity)),
    )


def upsert_article(
    qid: str, lang: str, title: str, rev_id: int | None, url: str, text: str
) -> None:
    """Store the plain text of one Wikipedia article for a person."""
    conn().execute(
        "INSERT INTO article (qid, lang, title, rev_id, url, text, fetched_at)"
        " VALUES (%s, %s, %s, %s, %s, %s, now()) ON CONFLICT (qid, lang)"
        " DO UPDATE SET title = EXCLUDED.title, rev_id = EXCLUDED.rev_id,"
        " url = EXCLUDED.url, text = EXCLUDED.text, fetched_at = now()",
        (qid, lang, title, rev_id, url, text),
    )


def insert_extraction(
    qid: str,
    prompt_hash: str,
    model: str,
    article_langs: list[str],
    article_revs: list[str],
    dropped_langs: list[str],
    bad_quotes: int,
    request: dict[str, Any],
    response: dict[str, Any],
    usage: dict[str, Any],
) -> int:
    """Store one model answer and return its id.

    Rows are never replaced: a person extracted again under a new prompt or a
    new article revision is a new row, and the old answer stays readable.
    """
    row = conn().execute(
        "INSERT INTO extraction (qid, prompt_hash, model, article_langs, article_revs,"
        " dropped_langs, bad_quotes, request_json, response_json, usage_json)"
        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (
            qid,
            prompt_hash,
            model,
            article_langs,
            article_revs,
            dropped_langs,
            bad_quotes,
            Jsonb(request),
            Jsonb(response),
            Jsonb(usage),
        ),
    ).fetchone()
    return row[0]
