"""Ask the model one structured question about one person, and store the answer.

The schema here is the machine-readable half of `prompts/extract.md`: every
field the prompt describes, and nothing it does not. Positions and birthplaces
are stored raw; a position becomes a proposal once reconciliation gives it a
QID, and birthplaces wait for a reconciler of their own.
"""

import json
import os
import re
import time
from dataclasses import dataclass
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints

from peploop import db, llm, prompt, wikidata

MODEL = os.environ.get("PEPLOOP_MODEL", "claude-sonnet-5")
MAX_TOKENS = 16000
EFFORT = "low"
WHITESPACE = re.compile(r"\s+")

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




def _norm(text: str) -> str:
    return WHITESPACE.sub(" ", text).strip()


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

    Whitespace is normalised on both sides, because the reduction that built
    the article text is the only thing either side could disagree about and
    still be quoting honestly. Anything left is paraphrase or fabrication.
    """
    haystack = _norm(" ".join(article.text for article in articles))
    return [quote for quote in all_quotes(extraction) if _norm(quote) not in haystack]


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


def extract_person(qid: str) -> ExtractionRow:
    """Extract one person, unless the same prompt already read the same articles."""
    started = time.monotonic()
    entity, articles, dropped = stored_articles(qid)
    result = ExtractionRow(qid, wikidata.best_label(entity), len(articles), dropped)

    text, prompt_hash = prompt.system_prompt()
    revs = sorted(article.key for article in articles)
    done = db.conn().execute(
        "SELECT 1 FROM extraction WHERE qid = %s AND prompt_hash = %s AND article_revs = %s",
        (qid, prompt_hash, revs),
    ).fetchone()
    if done is not None:
        result.skipped = True
        result.seconds = time.monotonic() - started
        return result

    user = user_message(entity, articles)
    response = llm.client().messages.parse(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        thinking={"type": "adaptive"},
        output_config={"effort": EFFORT},
        output_format=Extraction,
        system=[{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user}],
    )
    extraction = response.parsed_output
    if extraction is None:
        raise RuntimeError(f"{qid}: model returned no parsed output ({response.stop_reason})")

    bad = check_quotes(extraction, articles)
    payload: dict[str, Any] = json.loads(extraction.model_dump_json())
    payload["_bad_quotes"] = bad
    usage = llm.usage(response)
    request = {
        "model": MODEL,
        "max_tokens": MAX_TOKENS,
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": EFFORT},
        "messages": [{"role": "user", "content": user}],
    }
    db.insert_extraction(
        qid=qid,
        prompt_hash=prompt_hash,
        model=MODEL,
        article_langs=[article.lang for article in articles],
        article_revs=revs,
        dropped_langs=dropped,
        bad_quotes=len(bad),
        request=request,
        response=payload,
        usage=usage,
    )
    result.input_tokens = usage["input_tokens"]
    result.cache_creation = usage["cache_creation_input_tokens"]
    result.cache_read = usage["cache_read_input_tokens"]
    result.output_tokens = usage["output_tokens"]
    result.bad_quotes = len(bad)
    result.positions = len(extraction.positions)
    result.seconds = time.monotonic() - started
    return result
