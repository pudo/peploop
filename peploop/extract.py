"""Ask the model one structured question about one person, and store the answer.

The schema here is the machine-readable half of `prompts/extract.md`: every
field the prompt describes, and nothing it does not. Positions and birthplaces
are stored raw; a position becomes a proposal once reconciliation gives it a
QID, and birthplaces wait for a reconciler of their own.
"""

import json
import os
import time
from dataclasses import dataclass
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints

from peploop import db, evidence, llm, prompt, wikidata

MODEL = os.environ.get("PEPLOOP_MODEL", "claude-sonnet-5")
MAX_TOKENS = 16000
EFFORT = "low"
#: `adaptive`, or `disabled` through PEPLOOP_EXTRACT_THINKING.
THINKING = os.environ.get("PEPLOOP_EXTRACT_THINKING", "adaptive")

DateStr = Annotated[str, StringConstraints(pattern=r"^\d{4}(-\d{2}(-\d{2})?)?$")]



class Strict(BaseModel):
    """Base for every extracted shape: the API rejects unknown keys."""

    model_config = ConfigDict(extra="forbid")


class Dated(Strict):
    """A date at the precision the articles state, with its evidence."""

    value: DateStr
    quotes: list[str]
    lang: str


class Citizenship(Strict):
    """A country the person is or was a citizen of, named as the article names it."""

    name: str
    basis: Literal["explicit", "demonym"]
    start: DateStr | None
    end: DateStr | None
    quotes: list[str]
    lang: str


class NameForm(Strict):
    """The label and aliases Wikidata should carry for one language."""

    lang: str
    label: str
    aliases: list[str]


class Position(Strict):
    """One tenure of one office, in the words of the article reporting it."""

    title: str
    jurisdiction: str | None
    start: DateStr | None
    end: DateStr | None
    acting: bool
    quotes: list[str]
    lang: str


class Placed(Strict):
    """A place of birth as written, with whatever parent chain the article gives."""

    name: str
    quotes: list[str]
    lang: str


class Extraction(Strict):
    """Everything one person's articles say, in the shape Wikidata records it."""

    is_human: bool
    is_human_quote: str | None
    birth_date: list[Dated]
    death_date: list[Dated]
    gender: Literal["male", "female", "other"] | None
    gender_quotes: list[str]
    gender_lang: str | None
    citizenships: list[Citizenship]
    names: list[NameForm]
    positions: list[Position]
    birth_places: list[Placed]
    notes: str | None


@dataclass
class ExtractionRow:
    """What one `extract_person` call did, for the run's per-person line."""

    qid: str
    label: str | None
    articles: int
    dropped: list[str]
    input_tokens: int = 0
    cache_creation: int = 0
    cache_read: int = 0
    output_tokens: int = 0
    bad_quotes: int = 0
    positions: int = 0
    seconds: float = 0.0
    skipped: bool = False




def all_quotes(extraction: Extraction) -> list[str]:
    """List every quote the model returned, across all fields that carry one."""
    quotes: list[str] = []
    if extraction.is_human_quote:
        quotes.append(extraction.is_human_quote)
    quotes.extend(extraction.gender_quotes)
    for group in (
        extraction.birth_date,
        extraction.death_date,
        extraction.citizenships,
        extraction.positions,
        extraction.birth_places,
    ):
        for entry in group:
            quotes.extend(entry.quotes)
    return quotes


def check_quotes(extraction: Extraction, articles: list[prompt.Article]) -> list[str]:
    """Return the quotes that are not in the text that was sent.

    The gate is the one every lane shares (`evidence`). Only a sex may be
    quoted as one character ("男" in a Chinese infobox); any other quote that
    short is a failed answer, not evidence.
    """
    shown = " ".join(article.text for article in articles)
    gender = set(extraction.gender_quotes)
    rest = [quote for quote in all_quotes(extraction) if quote not in gender]
    return evidence.missing(list(gender), shown, min_length=1) + evidence.missing(rest, shown)


def _seed_lang(qid: str) -> str | None:
    row = db.conn().execute(
        "SELECT lang FROM membership WHERE qid = %s ORDER BY seen_at, lang LIMIT 1", (qid,)
    ).fetchone()
    return None if row is None else row[0]


def user_message(entity: dict[str, Any], articles: list[prompt.Article]) -> str:
    """The user turn one person's request carries: the item's state, then the articles."""
    labels = {
        target: wikidata.best_label(item)
        for target, item in wikidata.fetch_items(prompt.state_qids(entity), props="labels").items()
    }
    return prompt.render_user_message(prompt.render_state(entity, labels), articles)


def stored_articles(qid: str) -> tuple[dict[str, Any], list[prompt.Article], list[str]]:
    """The item and the articles a request about this person would read, and those dropped."""
    row = db.conn().execute("SELECT json FROM item WHERE qid = %s", (qid,)).fetchone()
    if row is None:
        raise LookupError(f"no item stored for {qid}")
    entity = row[0]
    articles, dropped = prompt.select_articles(qid, _seed_lang(qid), entity)
    if not articles:
        raise LookupError(f"no articles stored for {qid}")
    return entity, articles, dropped


@dataclass
class Prepared:
    """One person's request, built and not yet asked: what `store` needs to record its answer."""

    row: ExtractionRow
    articles: list[prompt.Article]
    revs: list[str]
    prompt_hash: str
    user: str
    started: float


def params(user: str) -> dict[str, Any]:
    """The extraction request for one person's user turn, without its output format."""
    text, _ = prompt.system_prompt()
    return {
        "model": MODEL,
        "max_tokens": MAX_TOKENS,
        "thinking": {"type": THINKING},
        "output_config": {"effort": EFFORT},
        "system": [{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user", "content": user}],
    }


def prepare(qid: str) -> Prepared | ExtractionRow:
    """Build one person's request, or return the skipped row when these articles were read under this prompt."""
    started = time.monotonic()
    entity, articles, dropped = stored_articles(qid)
    row = ExtractionRow(qid, wikidata.best_label(entity), len(articles), dropped)
    _text, prompt_hash = prompt.system_prompt()
    revs = sorted(article.key for article in articles)
    done = db.conn().execute(
        "SELECT 1 FROM extraction WHERE qid = %s AND prompt_hash = %s AND article_revs = %s",
        (qid, prompt_hash, revs),
    ).fetchone()
    if done is not None:
        row.skipped = True
        row.seconds = time.monotonic() - started
        return row
    return Prepared(row, articles, revs, prompt_hash, user_message(entity, articles), started)


def store(prep: Prepared, extraction: Extraction, usage: dict[str, int]) -> ExtractionRow:
    """Record one person's answer with its quote check, and return the run's row for them."""
    bad = check_quotes(extraction, prep.articles)
    payload: dict[str, Any] = json.loads(extraction.model_dump_json())
    payload["_bad_quotes"] = bad
    request = {k: v for k, v in params(prep.user).items() if k != "system"}
    db.insert_extraction(
        qid=prep.row.qid,
        prompt_hash=prep.prompt_hash,
        model=MODEL,
        article_langs=[article.lang for article in prep.articles],
        article_revs=prep.revs,
        dropped_langs=prep.row.dropped,
        bad_quotes=len(bad),
        request=request,
        response=payload,
        usage=usage,
    )
    result = prep.row
    result.input_tokens = usage["input_tokens"]
    result.cache_creation = usage["cache_creation_input_tokens"]
    result.cache_read = usage["cache_read_input_tokens"]
    result.output_tokens = usage["output_tokens"]
    result.bad_quotes = len(bad)
    result.positions = len(extraction.positions)
    result.seconds = time.monotonic() - prep.started
    return result


def extract_person(qid: str) -> ExtractionRow:
    """Extract one person, unless the same prompt already read the same articles."""
    prep = prepare(qid)
    if isinstance(prep, ExtractionRow):
        return prep
    response = llm.send(output_format=Extraction, **params(prep.user))
    if response.parsed_output is None:
        raise RuntimeError(f"{qid}: model returned no parsed output ({response.stop_reason})")
    return store(prep, response.parsed_output, llm.usage(response))
