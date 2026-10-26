"""Write each office title as the English name a Wikidata item would carry.

A search channel, never an answer. The lexical search reaches an item only
through words the item shares with the title, and an office whose item is
labelled in English alone shares none with "Ministro de la Juventud" beyond a
prefix of "minist". Asking a small model for "Minister of Youth of <state>"
and searching for that as well is what puts such an item on the shortlist.
The model that decides is still shown the title as written.

Three properties are the design:

* **The cache is the channel.** The model is not deterministic -- two runs
  over the same titles agreed exactly on two thirds -- so a translation is
  asked once, stored under the prompt hash and the model, and only ever read
  back. `reconcile.shortlist_hits` reads this table and never calls the model,
  so a shortlist is reproducible and a missing row means the lexical channel
  alone.
* **Batched, because the answers are independent.** Unlike a verdict, one
  title's English name does not depend on its neighbours', so twenty-five go in
  one request; the answer is a closed list of ids, an id the answer leaves out
  is asked again and an id it invents is dropped.
* **Never written to Wikidata.** The item side (`position.title_en`) is a
  search aid for items with no English or multilingual label. No write path
  reads that column, and `matched:` on a candidate line is drawn from
  `position_name`, which holds only names the item really carries.
"""

import os
import re
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict
from rigour.langs import iso_639_alpha2
from rigour.territories import get_territory_by_qid

from peploop import db, llm, positions, wikidata

PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "title_en.md"

#: A small model, on purpose: this is translation into a house style, and the
#: measurement it rests on was taken with this one.
MODEL = os.environ.get("PEPLOOP_TITLE_MODEL", "claude-haiku-4-5")
MAX_TOKENS = 4000

#: Titles per request. The size the measurement used.
BATCH = 25

#: Concurrent requests.
THREADS = 6

#: How often a title the answer left out is asked again before it is given up
#: on for this run. A title still missing is simply uncached: the search falls
#: back to the lexical channel for it, and the next run asks again.
ROUNDS = 3



@lru_cache(maxsize=1)
def system_prompt() -> tuple[str, str]:
    """Read the frozen prompt and return it with its sha256 hash.

    Every cached translation is keyed by the hash, so a prompt edit makes
    every title re-askable instead of mixing two instructions in one table.
    """
    return llm.system_prompt(PROMPT_PATH)


def fold_key(text: str | None) -> str:
    """The form a title is cached under: NFC, casefolded, whitespace collapsed.

    Deliberately not `text.fold`, which transliterates to ASCII: two
    Cyrillic languages' spellings must not collapse into one key, and nothing about
    the translation depends on case or spacing.
    """
    if not text:
        return ""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip().casefold()


@dataclass(frozen=True)
class Title:
    """One office title as it is sent: what was written, where, by whom."""

    title: str
    jurisdiction: str | None = None
    lang: str | None = None
    #: The state whose politician held it, as a QID; it decides the country
    #: name in the request and is part of the key, because "Minister of
    #: Defence" is a different item in every state.
    state_qid: str | None = None

    @property
    def key(self) -> tuple[str, str, str, str]:
        """(state, lang, folded title, folded jurisdiction); prompt and model complete it."""
        return (self.state_qid or "", self.lang or "", fold_key(self.title),
                fold_key(self.jurisdiction))


class Strict(BaseModel):
    """Base for the answer shape: the API rejects unknown keys."""

    model_config = ConfigDict(extra="forbid")


class Entry(Strict):
    """One title's English name, by the id it was sent under."""

    id: int
    english: str


class TitleAnswer(Strict):
    """The whole answer to one batch."""

    titles: list[Entry]


def country_name(state_qid: str | None) -> str:
    """The state's English name as the request names it, or '' for none."""
    if not state_qid:
        return ""
    return _country_names((state_qid,)).get(state_qid, state_qid)


@lru_cache(maxsize=512)
def _country_names(qids: tuple[str, ...]) -> dict[str, str]:
    out: dict[str, str] = {}
    missing = []
    for qid in qids:
        territory = get_territory_by_qid(qid)
        if territory is not None and territory.name:
            out[qid] = territory.name
        else:
            missing.append(qid)
    if missing:
        for qid, item in wikidata.fetch_items(missing, props="labels").items():
            label = wikidata.best_label(item)
            if label:
                out[qid] = label
    return out


def _clean(text: str | None) -> str:
    """One field of a request line: tabs and newlines would break the columns."""
    return re.sub(r"\s+", " ", text or "").strip()


def render_batch(batch: Sequence[Title]) -> str:
    """The user message for one batch: a header, then one tab-separated row per id."""
    lines = ["id\tcountry\ttitle\tjurisdiction"]
    for index, item in enumerate(batch):
        lines.append(
            f"{index}\t{_clean(country_name(item.state_qid))}\t{_clean(item.title)}"
            f"\t{_clean(item.jurisdiction)}"
        )
    return "\n".join(lines)


def parse_answer(answer: TitleAnswer, size: int) -> dict[int, str]:
    """Read one batch's answer as id -> English name.

    An id outside the batch is dropped, an empty name counts as no answer, and
    a repeated id keeps its first name: a title missing from the result is
    asked again rather than guessed at.
    """
    out: dict[int, str] = {}
    for entry in answer.titles:
        english = _clean(entry.english)
        if 0 <= entry.id < size and english and entry.id not in out:
            out[entry.id] = english
    return out




def request_for(batch: Sequence[Title], model: str = MODEL) -> dict[str, Any]:
    """Assemble one request without sending it."""
    text, _hash = system_prompt()
    return {
        "model": model,
        "max_tokens": MAX_TOKENS,
        "system": text,
        "messages": [{"role": "user", "content": render_batch(batch)}],
    }


def ask(batch: Sequence[Title], model: str = MODEL) -> tuple[dict[int, str], dict[str, int]]:
    """Send one batch and return its parsed answer and token usage."""
    response = llm.send(output_format=TitleAnswer, **request_for(batch, model))
    usage = llm.usage(response)
    answer = response.parsed_output
    if answer is None:
        return {}, usage
    return parse_answer(answer, len(batch)), usage


# --- the cache --------------------------------------------------------------

def cached_many(
    items: Iterable[Title], model: str = MODEL
) -> dict[tuple[str, str, str, str], str]:
    """Every English name the cache holds for these titles, by key."""
    keys = list({item.key for item in items})
    if not keys:
        return {}
    _text, prompt_hash = system_prompt()
    rows = db.conn().execute(
        "SELECT state_qid, lang, title_key, jurisdiction_key, english FROM title_en"
        " WHERE prompt_hash = %s AND model = %s AND (state_qid, lang, title_key,"
        " jurisdiction_key) IN (SELECT * FROM unnest(%s::text[], %s::text[], %s::text[],"
        " %s::text[]))",
        (prompt_hash, model, [k[0] for k in keys], [k[1] for k in keys],
         [k[2] for k in keys], [k[3] for k in keys]),
    ).fetchall()
    return {(s, l, t, j): english for s, l, t, j, english in rows}


def cached(item: Title, model: str = MODEL) -> str | None:
    """The cached English name of one title, or None. Never asks the model."""
    return cached_many([item], model).get(item.key)


def _store(batch: Sequence[Title], answers: dict[int, str], usage: dict[str, int],
           prompt_hash: str, model: str) -> None:
    """Record one request and the names it produced; an existing name is kept."""
    call_id = db.conn().execute(
        "INSERT INTO title_en_call (prompt_hash, model, titles, answered, usage_json)"
        " VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (prompt_hash, model, len(batch), len(answers), Jsonb(usage)),
    ).fetchone()[0]
    if not answers:
        return
    with db.conn().cursor() as cur:
        cur.executemany(
            "INSERT INTO title_en (state_qid, lang, title_key, jurisdiction_key,"
            " prompt_hash, model, title, jurisdiction, english, call_id)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
            [(*batch[i].key, prompt_hash, model, batch[i].title, batch[i].jurisdiction,
              english, call_id) for i, english in answers.items()],
        )


def translate(
    items: Iterable[Title],
    model: str = MODEL,
    dry_run: bool = False,
    threads: int = THREADS,
    log: Callable[[str], None] = lambda _m: None,
    asker: Callable[..., tuple[dict[int, str], dict[str, int]]] | None = None,
) -> dict[str, int]:
    """Fill the cache for every title not in it yet, and report what it cost.

    Resumable from the table: a title cached under this prompt and model is
    never asked again, so a re-run costs only what is new. `asker` replaces
    the request, for the offline check.
    """
    send = asker or ask
    _text, prompt_hash = system_prompt()
    unique: dict[tuple[str, str, str, str], Title] = {}
    for item in items:
        if item.title and item.title.strip():
            unique.setdefault(item.key, item)
    have = cached_many(unique.values(), model)
    todo = [item for key, item in unique.items() if key not in have]
    stats = {"titles": len(unique), "cached": len(have), "todo": len(todo),
             "asked": 0, "answered": 0, "missing": 0, "requests": 0, "failed": 0,
             "input_tokens": 0, "output_tokens": 0}
    log(f"{len(unique)} titles, {len(have)} cached, {len(todo)} to ask")
    if dry_run or not todo:
        return stats
    lock = threading.Lock()

    def one(batch: list[Title]) -> list[Title]:
        """Ask one batch, store what came back, return what did not."""
        for attempt in range(3):
            try:
                answers, usage = send(batch, model)
                break
            except Exception as exc:  # noqa: BLE001 — a failed batch is retried, then left uncached
                log(f"batch failed ({type(exc).__name__}: {str(exc)[:120]}), attempt {attempt + 1}")
                time.sleep(2 * (attempt + 1))
        else:
            with lock:
                stats["failed"] += 1
            return list(batch)
        answers = {i: name for i, name in answers.items() if 0 <= i < len(batch) and name}
        _store(batch, answers, usage, prompt_hash, model)
        with lock:
            stats["requests"] += 1
            stats["asked"] += len(batch)
            stats["answered"] += len(answers)
            stats["input_tokens"] += usage.get("input_tokens", 0)
            stats["output_tokens"] += usage.get("output_tokens", 0)
        return [item for i, item in enumerate(batch) if i not in answers]

    pending = todo
    for round_ in range(ROUNDS):
        if not pending:
            break
        batches = [pending[i:i + BATCH] for i in range(0, len(pending), BATCH)]
        left: list[Title] = []
        if threads > 1:
            with ThreadPoolExecutor(max_workers=threads) as pool:
                for rest in pool.map(one, batches):
                    left.extend(rest)
        else:
            # On the calling thread, so its connection (and any temporary
            # table the offline check shadows the cache with) is the one used.
            for batch in batches:
                left.extend(one(batch))
        log(f"round {round_ + 1}: {len(batches)} requests, {len(left)} left unanswered")
        pending = left
    stats["missing"] = len(pending)
    return stats


# --- what gets translated ----------------------------------------------------

def mention_titles(state_qid: str, country: str) -> list[Title]:
    """Every office title in the newest extraction of each in-scope person of a run.

    The same selection `cli reconcile` works through, so the cache covers
    exactly what a reconcile pass would search for.
    """
    rows = db.conn().execute(
        "SELECT e.response_json->'positions' FROM ("
        "  SELECT DISTINCT ON (qid) id, qid, response_json FROM extraction"
        "  WHERE response_json IS NOT NULL ORDER BY qid, id DESC"
        ") e JOIN person pe ON pe.qid = e.qid"
        " WHERE pe.country = %s AND pe.status <> 'out_of_scope'",
        (country,),
    )
    out = []
    for (mentions,) in rows:
        for entry in mentions or []:
            if entry.get("title"):
                out.append(Title(entry["title"], entry.get("jurisdiction"),
                                 entry.get("lang"), state_qid))
    return out


def unlabelled(labels: dict[str, str], state_qid: str | None) -> tuple[str, str] | None:
    """The (lang, label) to translate for an item with no `en`/`mul` label, else None.

    The label in one of the state's own languages comes first, because it is
    the one written by the community that uses the office; any other is the
    fallback, in a stable order.
    """
    if not labels or "en" in labels or "mul" in labels:
        return None
    territory = get_territory_by_qid(state_qid) if state_qid else None
    own = [iso_639_alpha2(lang) for lang in (territory.langs if territory else [])]
    for lang in own:
        if lang and lang in labels:
            return lang, labels[lang]
    lang = sorted(labels)[0]
    return lang, labels[lang]


def item_title(labels: dict[str, str], state_qid: str | None) -> Title | None:
    """The `Title` an unlabelled item is translated under; no jurisdiction is sent."""
    picked = unlabelled(labels, state_qid)
    if picked is None:
        return None
    lang, label = picked
    return Title(label, None, lang, state_qid)


def item_titles(qids: Sequence[str] | None = None, state_qid: str | None = None
                ) -> dict[str, Title]:
    """The positions with no `en`/`mul` label, as the title each is translated under.

    Selected by `qids`, or by being the state's own (`P17` or `P1001`). An item
    is translated under its own state, so the same item gets the same key
    whichever country's run reaches it.
    """
    where, params = [], []
    if qids is not None:
        where.append("p.qid = ANY(%s)")
        params.append(list(qids))
    if state_qid is not None:
        where.append("(p.country_qid = ANY(%s) OR p.jurisdiction_qid = ANY(%s))")
        params.extend([sorted(positions.state_qids(state_qid))] * 2)
    rows = db.conn().execute(
        "SELECT p.qid, coalesce(p.country_qid, p.jurisdiction_qid),"
        " jsonb_object_agg(n.lang, n.text) FROM position p"
        " JOIN position_name n ON n.qid = p.qid AND NOT n.alias"
        + (" WHERE " + " AND ".join(where) if where else "")
        + " GROUP BY p.qid, p.country_qid, p.jurisdiction_qid",
        params,
    ).fetchall()
    out = {}
    for qid, state, labels in rows:
        item = item_title(labels or {}, state)
        if item is not None:
            out[qid] = item
    return out


def refresh_items(
    found: dict[str, Title],
    model: str = MODEL,
    dry_run: bool = False,
    log: Callable[[str], None] = lambda _m: None,
    threads: int = THREADS,
    asker: Callable[..., tuple[dict[int, str], dict[str, int]]] | None = None,
) -> dict[str, int]:
    """Translate unlabelled items and fold their English names into the search.

    For items already loaded. The tokens are added to `search_text` rather
    than the document rebuilt, which needs every referenced item's names; a
    name that a prompt change later replaces leaves its old tokens until the
    next `load-positions` rebuilds the document from scratch.
    """
    from peploop import positions

    stats = translate(found.values(), model=model, dry_run=dry_run, log=log,
                      threads=threads, asker=asker)
    if dry_run:
        return stats
    names = cached_many(found.values(), model)
    rows = db.conn().execute(
        "SELECT qid, search_text, title_en FROM position WHERE qid = ANY(%s)",
        (list(found),),
    ).fetchall()
    updated = 0
    for qid, search_text, current in rows:
        english = names.get(found[qid].key)
        if not english or english == current:
            continue
        bag = set((search_text or "").split()) | set(positions.token_bag([english]))
        db.conn().execute(
            "UPDATE position SET title_en = %s, search_text = %s WHERE qid = %s",
            (english, " ".join(sorted(bag)), qid),
        )
        updated += 1
    stats["items_updated"] = updated
    log(f"{len(found)} unlabelled items, {updated} given an English search name")
    return stats


def cost(model: str = MODEL, since: Any = None) -> dict[str, Any]:
    """The tokens the ledger records for this model, optionally since a time."""
    row = db.conn().execute(
        "SELECT count(*), coalesce(sum(titles), 0),"
        " coalesce(sum((usage_json->>'input_tokens')::bigint), 0),"
        " coalesce(sum((usage_json->>'output_tokens')::bigint), 0)"
        " FROM title_en_call WHERE model = %s AND (%s::timestamptz IS NULL OR created_at >= %s)",
        (model, since, since),
    ).fetchone()
    return dict(zip(("requests", "titles", "input_tokens", "output_tokens"), row))
