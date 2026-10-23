"""Ask a model which of the offered position items an office title names.

Retrieval ranks and a model decides; this is the deciding half. `positions.py`
hands over a shortlist it ordered, this module renders each candidate as the
whole item, asks one closed-set question about it, and turns the answer into a
QID or a recorded refusal.

Three properties are the design, and each one is here because the workbench
has paid for its absence somewhere:

* **The shortlist is a closed set.** The pick is constrained to the offered
  QIDs by the schema the API enforces, and `settle` refuses an off-list QID
  again afterwards, because a schema is a request and a gate is a guarantee.
* **Every signal that moved a row is shown.** A candidate's line carries the
  tags the ranking derived, so a model reading the list sees the same
  evidence the ordering used instead of an order it must take on trust.
* **The offline half is pure.** `candidate_line`, `render_mention` and
  `settle` touch nothing but their arguments, so `check_reconcile` pins the
  whole decision path without a key, a request or a token.

Nothing here writes to Wikidata, and nothing here writes a proposal: a
verdict is a row for a later increment to act on.
"""

import logging
from collections import Counter
import os
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Literal, Optional, Sequence

from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict

from peploop import db, llm, positions, titles, wikidata
from peploop.verdict import Confidence

_log = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "reconcile.md"

MODEL = os.environ.get("PEPLOOP_MODEL", "claude-sonnet-5")
MAX_TOKENS = 4000
EFFORT = "medium"

#: What the model is shown, apart from the prompt. Bumped whenever the
#: candidate line, the per-office message or the request shape changes
#: without a prompt edit, because a verdict is keyed by what the model saw
#: and the prompt hash alone does not cover the rendering.
RENDER_VERSION = 3

#: The renderings whose verdicts still count. 3 moved the article ahead of the
#: office, as a cached block of its own, so a person's later mentions read it
#: from the prompt cache; the model is shown the same text in another order,
#: so a verdict under 2 is still an answer to the question.
ANSWERING_RENDERS = (3, 2)

#: The longest article that goes into the request whole, in characters. The
#: median article behind a mention is under 3,000 characters and the longest
#: is over 130,000; the cap bounds the tail and a mention over it is asked on
#: its quotes alone, with the omission stated in the message.
ARTICLE_CAP = 20_000

#: How many candidates the model reads. Retrieval's own measurement puts the
#: answer inside the top fifteen for 84% of gold rows and inside the top
#: hundred for barely more, so a longer list buys recall the re-ranking
#: already has and costs every request the reading of it.
SHORTLIST = 15

#: The two verdicts that mean an item was found. Everything else names a way
#: the shortlist tried to mislead, and is recorded rather than resolved.
MATCH_KINDS = ("same-office", "renamed")

#: The closed verdict set, in the order the prompt introduces them.
KINDS = MATCH_KINDS + ("generic-class", "body-not-seat", "wrong-office", "none")

#: Every tag `positions.tags_for` can derive. The prompt has to explain each
#: one, because a signal that moved a row and was not shown is a silent
#: re-ordering — and `check_reconcile` pins the two lists against each other
#: so a tag added to the ranking cannot ship without an explanation.
TAGS = (
    "not-office",
    "abstract",
    "generic-by-convention",
    "unheld",
    "abolished",
    "date-conflict",
    "date-fit",
    "diplomatic",
    "inbound-diplomatic",
    "foreign-scoped",
)



class Strict(BaseModel):
    """Base for the verdict shape: the API rejects unknown keys."""

    model_config = ConfigDict(extra="forbid")


@lru_cache(maxsize=1)
def system_prompt() -> tuple[str, str]:
    """Read the frozen system prompt and return it with its sha256 hash.

    The hash is what a stored verdict is keyed by, so a prompt edit makes the
    old answers re-askable instead of silently mixing two instructions.
    """
    return llm.system_prompt(PROMPT_PATH)


@dataclass
class Candidate:
    """One position item as the model reads it.

    Every field is shown. The dataclass exists rather than a dict so that
    building a shortlist by hand — which is what the offline check does — is
    the same code path as building one from the table.
    """

    qid: str
    label: str | None = None
    description: str | None = None
    #: `P279` parents by label: the *kind* of office, which is how a seat is
    #: told from the body it sits in and from an occupation.
    kinds: list[str] = field(default_factory=list)
    #: `P361`/`P2389`, by label where the table knows one and by QID where it
    #: does not. Naming it matters: the body/seat rule is unusable when the
    #: body is an opaque identifier.
    body: str | None = None
    #: The polity the office governs, by label, where it is narrower than the
    #: state: an undescribed "Governor of X" is otherwise judged on its label.
    governs: str | None = None
    inception: str | None = None
    abolished: str | None = None
    #: Counted where the search is, so `None` means "nobody has counted for
    #: this state" and renders as `uncounted`, never as zero.
    holders: int | None = None
    tags: tuple[str, ...] = ()
    #: The property that makes a `generic-by-convention` office concrete.
    scope_qualifier: str | None = None
    #: The name the retrieval matched on, which is often not the item's own.
    matched: str | None = None

    @property
    def qualifier_in_use(self) -> bool:
        """Whether the state's community records people on this item with a qualifier.

        Either the ranking said so (`generic-by-convention`) or enough of the
        state's own holders sit on the item to clear the same floor. The second
        clause exists because a country-generic office with no subclasses is
        not class-like, earns no tag, and was refused by a model that had been
        told to fear generics and never shown the qualifier that makes this one
        concrete.
        """
        if "generic-by-convention" in self.tags:
            return True
        return self.holders is not None and self.holders >= positions.CONVENTION_FLOOR

    def line(self) -> str:
        """One line for the shortlist, in the order the prompt documents."""
        parts = [f"{self.qid} | {self.label or '(no label)'}"]
        parts.append(self.description or "(no description)")
        if self.kinds:
            parts.append("kind: " + ", ".join(self.kinds))
        if self.body:
            parts.append("part of: " + self.body)
        if self.governs:
            parts.append("governs: " + self.governs)
        span = "–".join([self.inception or "", self.abolished or ""]).strip("–")
        if span:
            parts.append("exists: " + span)
        parts.append(
            "holders: " + ("uncounted" if self.holders is None else str(self.holders))
        )
        if self.tags:
            parts.append("tags: " + ", ".join(self.tags))
        if self.scope_qualifier and self.qualifier_in_use:
            parts.append("used with: " + self.scope_qualifier)
        if self.matched:
            parts.append("matched: " + self.matched)
        return " | ".join(parts)


@dataclass
class Mention:
    """An office as extraction wrote it, with what attests to it."""

    title: str
    jurisdiction: str | None = None
    start: str | None = None
    end: str | None = None
    quotes: list[str] = field(default_factory=list)
    lang: str | None = None
    #: The article the quotes came from, whole, when it fits under `ARTICLE_CAP`.
    article: str | None = None


@dataclass
class Verdict:
    """What the model and the mechanical gate together made of one office."""

    title: str
    #: The item, set only when the verdict is a match and nothing objected.
    qid: str | None = None
    kind: str = "none"
    confidence: str = "low"
    evidence: str = ""
    reason: str = ""
    #: Every QID the model was shown, so a wrong answer can be re-read
    #: against what it actually saw rather than against what we assume.
    shortlist: list[str] = field(default_factory=list)
    #: The model's pick, kept even where the gate refused it.
    chosen: str | None = None
    veto: str | None = None
    prompt_hash: str | None = None
    model: str | None = None
    #: The request's token counts, so a pass can be costed from its ledger.
    usage: dict[str, int] | None = None

    @property
    def resolved(self) -> bool:
        return self.qid is not None

    def as_dict(self) -> dict[str, Any]:
        return {
            "title": self.title, "qid": self.qid, "kind": self.kind,
            "confidence": self.confidence, "evidence": self.evidence,
            "reason": self.reason, "shortlist": list(self.shortlist),
            "chosen": self.chosen, "veto": self.veto,
            "prompt_hash": self.prompt_hash, "model": self.model,
            "usage": self.usage,
        }


class OfficeVerdict(Strict):
    """Which offered position item the office names, or why none does."""

    qid: Optional[str]
    kind: Literal[KINDS]
    confidence: Confidence
    evidence: str
    reason: str


def verdict_schema() -> type[OfficeVerdict]:
    """The answer shape, the same for every request.

    The closed set is `settle`'s guarantee and not the schema's: a schema
    closing `qid` over the offered QIDs would put the shortlist inside the
    cached prefix and defeat the prompt cache, while one shape for all
    requests reads the prompt back from cache from the second request on.
    """
    return OfficeVerdict


def render_shortlist(candidates: Sequence[Candidate]) -> str:
    """The candidates as the model sees them, one whole item per line."""
    lines = [f"- {candidate.line()}" for candidate in candidates]
    return "\n".join(lines) or "- (nothing retrieved)"


def article_block(mention: Mention) -> str | None:
    """The article as its own block, when it goes in whole: the part a person's mentions share."""
    if mention.article is None or len(mention.article) > ARTICLE_CAP:
        return None
    return f"# The article ({mention.lang or 'unknown language'})\n\n{mention.article}"


def render_mention(mention: Mention, candidates: Sequence[Candidate], with_article: bool = True) -> str:
    """The per-office half of the request: the evidence, then the candidates.

    `with_article=False` leaves out an article that goes in whole, for a
    request that carries it as a block of its own (`request_for`).
    """
    parts = ["# The office as written", "", mention.title]
    if mention.jurisdiction:
        parts.append(f"jurisdiction as written: {mention.jurisdiction}")
    span = "–".join([mention.start or "", mention.end or ""]).strip("–")
    parts.append(f"tenure: {span or 'no dates'}")
    if mention.lang:
        parts.append(f"article language: {mention.lang}")
    if mention.quotes:
        parts.append("")
        parts.append("# What the article says")
        parts.append("")
        parts.extend(f"- “{quote}”" for quote in mention.quotes)
    if mention.article is not None and (with_article or article_block(mention) is None):
        parts.extend(["", f"# The article ({mention.lang or 'unknown language'})", ""])
        if len(mention.article) > ARTICLE_CAP:
            parts.append(
                f"article omitted: {len(mention.article):,} characters, over the cap"
            )
        else:
            parts.append(mention.article)
    parts.extend(["", "# Candidate position items", "", render_shortlist(candidates)])
    parts.extend([
        "",
        "Which of these is the office named above? Answer `none` rather than "
        "the closest one.",
    ])
    return "\n".join(parts)


def settle(
    kind: str, chosen: str | None, shortlist: Sequence[str]
) -> tuple[str | None, str | None]:
    """Turn one verdict into an applied QID, or a recorded refusal.

    A pure function on purpose: it is the whole of the mechanical half of the
    decision, so the offline check can pin every path through it. Returns
    `(qid, veto)`, and `qid` is set only when nothing objected.

    Three ways a verdict does not become a QID:

    * the verdict is not a **match** — `generic-class`, `body-not-seat`,
      `wrong-office` and `none` each mean no item on the list is the office,
      however close the nearest candidate came, and the QID they carry names
      what they are describing rather than what to write;
    * a match names **no item**, which is an answer contradicting itself;
    * the pick was **not on the shortlist** it was shown. The schema already
      forbids it, and it is checked again here because the closed set is the
      one guarantee this design rests on and a schema is a request.
    """
    if kind not in MATCH_KINDS:
        return None, None
    if not chosen:
        return None, "match-without-qid"
    if chosen not in set(shortlist):
        return None, "off-shortlist"
    return chosen, None


#: The columns a candidate line is rendered from, fetched with the shortlist
#: rather than per row.
DISPLAY_COLUMNS = (
    "label", "description", "kinds", "body_qid", "inception", "abolished",
    "holders", "holders_by_country", "scope_qualifier", "jurisdiction_qid", "country_qid",
)


def _labels(qids: Sequence[str]) -> dict[str, str]:
    """Name the bodies and polities a shortlist points at.

    A body that is itself a loaded position is named from its own row; the
    rest are fetched by label through the cached item reader, because the
    body/seat rule the prompt rests on is unusable when the body is an opaque
    identifier -- a national upper house printed as `part of: Q389423`. The offline
    check never reaches this: its candidates carry the body as text.
    """
    wanted = sorted({qid for qid in qids if qid})
    if not wanted:
        return {}
    rows = db.conn().execute(
        "SELECT qid, label FROM position WHERE qid = ANY(%s) AND label IS NOT NULL",
        (wanted,),
    ).fetchall()
    labels = {qid: label for qid, label in rows}
    missing = [qid for qid in wanted if qid not in labels]
    if missing:
        for qid, item in wikidata.fetch_items(missing, props="labels").items():
            label = wikidata.best_label(item)
            if label:
                labels[qid] = label
    return labels


def _governs(record: dict[str, Any], state_qid: str | None, labels: dict[str, str]) -> str | None:
    """The office's polity by label, or None where it is the state itself."""
    polity = record.get("jurisdiction_qid")
    if not polity or polity in {state_qid, record.get("country_qid")}:
        return None
    return labels.get(polity, polity)


def candidates_for(
    hits: Sequence[positions.Hit],
    state_qid: str | None = None,
    holder_scope: str = "local",
) -> list[Candidate]:
    """Describe a ranked shortlist from the table, in the ranking's order.

    The holder count shown is the one the ranking scored — `holder_count`
    under the same scope — so the number in front of the model is the number
    that moved the row, and not a second count that happens to be handy.
    """
    if not hits:
        return []
    columns = ", ".join(DISPLAY_COLUMNS)
    rows = db.conn().execute(
        f"SELECT qid, {columns} FROM position WHERE qid = ANY(%s)",
        ([hit.qid for hit in hits],),
    ).fetchall()
    by_qid = {row[0]: dict(zip(DISPLAY_COLUMNS, row[1:])) for row in rows}
    bodies = _labels([q for r in by_qid.values() for q in (r.get("body_qid"), r.get("jurisdiction_qid"))])
    out: list[Candidate] = []
    for hit in hits:
        record = by_qid.get(hit.qid, {})
        body_qid = record.get("body_qid")
        out.append(Candidate(
            qid=hit.qid,
            label=record.get("label"),
            description=record.get("description"),
            kinds=list(record.get("kinds") or []),
            body=bodies.get(body_qid or "", body_qid),
            governs=_governs(record, state_qid, bodies),
            inception=str(record["inception"]) if record.get("inception") else None,
            abolished=str(record["abolished"]) if record.get("abolished") else None,
            holders=positions.holder_count(record, state_qid, holder_scope),
            tags=tuple(hit.tags),
            scope_qualifier=record.get("scope_qualifier"),
            matched=hit.name,
        ))
    return out


#: Everything a replayed shortlist needs: what the row is shown as, plus the
#: columns the tags are derived from. Kept beside `DISPLAY_COLUMNS` rather than
#: folded into it, because the display set is what the *live* pass reads and
#: the tags there come from the search's own `Hit`.
REPLAY_COLUMNS = DISPLAY_COLUMNS + (
    "not_office", "instance_count", "held_subclasses", "diplomatic",
)


def replay_shortlist(resolution_id: int) -> tuple[dict[str, Any], list[Candidate]]:
    """Rebuild what the model was shown for one recorded verdict.

    The `resolution` row keeps every QID it was offered, in rank order, so the
    shortlist can be read back without paying for the search again -- and the
    tags are re-derived from the same columns and the same tenure dates, so a
    reviewer reads the row the model read rather than a fresh one.

    Two things are not replayed and are not worth re-searching for: the score,
    which is comparable only inside one query, and `matched`, the name the text
    index hit. The question a reviewer is answering is whether this office is
    that item, which the label, the kind, the body and the holder count answer.
    """
    row = db.conn().execute(
        "SELECT id, extraction_id, mention_idx, title, jurisdiction, start_text,"
        " end_text, lang, state_qid, shortlist, chosen, qid, kind, confidence,"
        " evidence, reason, veto, model, reopened_for FROM resolution WHERE id = %s",
        (resolution_id,),
    ).fetchone()
    if row is None:
        raise LookupError(f"no resolution {resolution_id}")
    columns = (
        "id", "extraction_id", "mention_idx", "title", "jurisdiction", "start_text",
        "end_text", "lang", "state_qid", "shortlist", "chosen", "qid", "kind",
        "confidence", "evidence", "reason", "veto", "model", "reopened_for",
    )
    record = dict(zip(columns, row))
    offered = list(record["shortlist"] or [])
    if not offered:
        return record, []
    fields = ", ".join(REPLAY_COLUMNS)
    rows = db.conn().execute(
        f"SELECT qid, {fields} FROM position WHERE qid = ANY(%s)", (offered,)
    ).fetchall()
    by_qid = {r[0]: dict(zip(REPLAY_COLUMNS, r[1:])) for r in rows}
    bodies = _labels([q for r in by_qid.values() for q in (r.get("body_qid"), r.get("jurisdiction_qid"))])
    state = record["state_qid"]
    out = []
    for qid in offered:
        item = by_qid.get(qid, {})
        body_qid = item.get("body_qid")
        out.append(Candidate(
            qid=qid,
            label=item.get("label"),
            description=item.get("description"),
            kinds=list(item.get("kinds") or []),
            body=bodies.get(body_qid or "", body_qid),
            governs=_governs(item, state, bodies),
            inception=str(item["inception"]) if item.get("inception") else None,
            abolished=str(item["abolished"]) if item.get("abolished") else None,
            holders=positions.holder_count(item, state),
            tags=tuple(positions.tags_for(
                item, state, record["start_text"], record["end_text"]
            )) if item else (),
            scope_qualifier=item.get("scope_qualifier"),
        ))
    return record, out




def request_for(
    mention: Mention, candidates: Sequence[Candidate]
) -> dict[str, Any]:
    """Assemble one request without sending it.

    Everything up to the call, so the shape can be read, diffed and pinned on
    a host with no credential — which is the host this was written on. The
    system block carries the cache breakpoint and the per-office half follows
    it, because the prompt is the same bytes for every office and the
    shortlist is not.
    """
    text, _hash = system_prompt()
    article = article_block(mention)
    if article is None:
        content: Any = render_mention(mention, candidates)
    else:
        # The article first, with a breakpoint of its own: one person's
        # several mentions share it, and the second on reads it from cache.
        content = [
            {"type": "text", "text": article, "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": render_mention(mention, candidates, with_article=False)},
        ]
    return {
        "model": MODEL,
        "max_tokens": MAX_TOKENS,
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": EFFORT},
        "system": [
            {"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}
        ],
        "messages": [{"role": "user", "content": content}],
    }


def verdict_of(mention: Mention, candidates: Sequence[Candidate], answer: OfficeVerdict,
               usage: dict[str, int], model: str = MODEL) -> Verdict:
    """Settle one answer about one office into a verdict, with the gate's veto."""
    shortlist = [candidate.qid for candidate in candidates]
    _text, prompt_hash = system_prompt()
    verdict = Verdict(
        title=mention.title,
        kind=answer.kind,
        confidence=answer.confidence,
        evidence=answer.evidence,
        reason=answer.reason,
        shortlist=shortlist,
        chosen=answer.qid,
        prompt_hash=prompt_hash,
        model=model,
        usage=usage,
    )
    verdict.qid, verdict.veto = settle(verdict.kind, verdict.chosen, shortlist)
    return verdict


def reconcile(
    mention: Mention,
    candidates: Sequence[Candidate],
    model: str = MODEL,
) -> Verdict:
    """Ask the model about one office and settle its answer.

    One office per request: the shortlists differ per office and batching
    them would put several decisions in one context, which is how a
    judgement pass standardises on whoever answered first.
    """
    request = request_for(mention, candidates)
    request["model"] = model
    response = llm.send(output_format=verdict_schema(), **request)
    answer = response.parsed_output
    if answer is None:
        raise RuntimeError(
            f"{mention.title!r}: no parsed output ({response.stop_reason})"
        )
    return verdict_of(mention, candidates, answer, llm.usage(response), model)


def mention_from(entry: dict[str, Any]) -> Mention:
    """Read one `positions` entry of an extraction as the office it names."""
    return Mention(
        title=entry["title"],
        jurisdiction=entry.get("jurisdiction"),
        start=entry.get("start"),
        end=entry.get("end"),
        quotes=list(entry.get("quotes") or []),
        lang=entry.get("lang"),
    )


LEDGER_COLUMNS = (
    "title", "shortlist", "chosen", "qid", "kind", "confidence", "evidence",
    "reason", "veto", "prompt_hash", "model", "usage_json",
)


def recorded(
    extraction_id: int, mention_idx: int, prompt_hash: str,
    render_version: int = RENDER_VERSION,
    reopened_for: str = "",
) -> Verdict | None:
    """Return the verdict already stored for this mention under this prompt, if any.

    The ledger is the resume point: a mention answered once is never asked
    again, and a prompt edit or a rendering change makes the old answer stop
    counting, because either changes what the model was shown. A re-ask after
    an item was minted is its own entry, found only under the item it was for.
    """
    row = db.conn().execute(
        f"SELECT {', '.join(LEDGER_COLUMNS)} FROM resolution"
        " WHERE extraction_id = %s AND mention_idx = %s AND prompt_hash = %s"
        " AND render_version = ANY(%s) AND reopened_for = %s ORDER BY id DESC LIMIT 1",
        (extraction_id, mention_idx, prompt_hash,
         list(ANSWERING_RENDERS) if render_version == RENDER_VERSION else [render_version], reopened_for),
    ).fetchone()
    if row is None:
        return None
    record = dict(zip(LEDGER_COLUMNS, row))
    record["usage"] = record.pop("usage_json")
    record["shortlist"] = list(record["shortlist"] or [])
    return Verdict(**record)


def store(
    extraction_id: int,
    mention_idx: int,
    mention: Mention,
    state_qid: str | None,
    verdict: Verdict,
    reopened_for: str = "",
    retrieval: str | None = None,
) -> None:
    """Append one verdict to the ledger. Never replaces: the key is what was shown."""
    db.conn().execute(
        "INSERT INTO resolution (extraction_id, mention_idx, title, jurisdiction,"
        " start_text, end_text, lang, state_qid, prompt_hash, render_version, model,"
        " shortlist, chosen, qid, kind, confidence, evidence, reason, veto, usage_json,"
        " reopened_for, retrieval)"
        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,"
        " %s, %s, %s, %s)"
        " ON CONFLICT (extraction_id, mention_idx, prompt_hash, render_version,"
        " reopened_for) DO NOTHING",
        (
            extraction_id, mention_idx, mention.title, mention.jurisdiction,
            mention.start, mention.end, mention.lang, state_qid,
            verdict.prompt_hash, RENDER_VERSION, verdict.model or MODEL, list(verdict.shortlist),
            verdict.chosen, verdict.qid, verdict.kind, verdict.confidence,
            verdict.evidence, verdict.reason, verdict.veto,
            Jsonb(verdict.usage) if verdict.usage is not None else None,
            reopened_for, retrieval,
        ),
    )


#: An abbreviation for a legislator no office item is labelled with.
MP = re.compile(r"(?i)(?<![\w.])m\.?\s?p\.?(?![\w.])")
#: The constituency a seat's title names after the chamber, which no seat item
#: carries: "Member of Parliament for Ashton North" is the seat. Only a
#: chamber's member: a committee "for" something is named by what follows.
CONSTITUENCY = re.compile(
    r"(?i)^(member of\b.*?\b(?:parliament|house|chamber|assembly|senate|congress|legislature)\b.*?)"
    r"\s+for\s+\S.*$")


def search_title(title: str) -> str:
    """The title as the search is asked it: "MP" spelled out, the constituency off.

    Only the search reads this; the model is shown the title as written. The
    constituency comes off a member's title alone, so "Minister for Foreign
    Affairs" keeps its portfolio.
    """
    text = MP.sub("member of parliament", title).strip()
    return CONSTITUENCY.sub(r"\1", text)


#: How many of the fifteen the English-title channel fills before the
#: lexical one. Measured against filling ten from the lexical channel and
#: against fusing the two: canonical first lost no known answer and took the
#: hard set's recall@15 from 62 to 93.
CANON_TOP = 10

#: How deep the English-title search reads before exact-name promotion. An
#: item labelled with the title verbatim can rank below its sibling ministries
#: on coverage alone, and promotion only helps if it was retrieved.
CANON_DEPTH = 100


def shortlist_hits(mention: Mention, state_qid: str | None) -> list[positions.Hit]:
    """Retrieve the ranked shortlist a mention is asked about; see `retrieve`."""
    return retrieve(mention, state_qid)[0]


def retrieve(
    mention: Mention, state_qid: str | None
) -> tuple[list[positions.Hit], str]:
    """Retrieve the ranked shortlist a mention is asked about, and name the retrieval.

    The one search both the live pass and `retrievable` run, so that "would the
    model be shown this item" is answered by the same call that shows it.

    Two channels when the title's English name is cached (`titles`): its
    search, with exact-name hits first, fills the first `CANON_TOP`, and the
    search for the title as written fills the rest. With no cached name it is
    the lexical search alone. Only the cache is
    read, so the shortlist is reproducible and no model is called here.

    The name is stored on the verdict (`resolution.retrieval`): the ledger's
    key does not cover the shortlist, so an audit tells a refusal made from the
    lexical list apart from one made from the two-channel list by this.
    """
    lexical = positions.search(
        search_title(mention.title), mention.jurisdiction, state_qid, limit=SHORTLIST,
        start=mention.start, end=mention.end,
    )
    english = titles.cached(titles.Title(
        mention.title, mention.jurisdiction, mention.lang, state_qid
    ))
    if not english:
        _log.debug("no English title cached for %r; lexical channel only", mention.title)
        return lexical, "lex"
    canonical = positions.promote_exact(positions.search(
        english, mention.jurisdiction, state_qid, limit=CANON_DEPTH,
        start=mention.start, end=mention.end,
    ), english)
    out: list[positions.Hit] = []
    seen: set[str] = set()
    for hits, cap in ((canonical[:CANON_TOP], CANON_TOP), (lexical, SHORTLIST),
                      (canonical[CANON_TOP:], SHORTLIST)):
        for hit in hits:
            if len(out) >= cap:
                break
            if hit.qid not in seen:
                seen.add(hit.qid)
                out.append(hit)
    return out, f"canon{CANON_TOP}+lex:{titles.system_prompt()[1][:8]}"


def retrievable(mention: Mention, state_qid: str | None, qid: str) -> bool:
    """Whether `qid` would be on the shortlist this mention is asked about.

    Reach for this after minting an item and before re-asking its mentions: an
    item the search does not surface cannot be picked, and re-asking would buy
    the same refusal again.
    """
    return any(hit.qid == qid for hit in shortlist_hits(mention, state_qid))


@dataclass
class Asking:
    """One mention retrieved and ready to ask: what the model is shown and how its answer is recorded."""

    extraction_id: int
    mention_idx: int
    mention: Mention
    state_qid: str | None
    candidates: list[Candidate]
    retrieval: str | None
    reopened_for: str = ""
    model: str = MODEL

    def job(self, done: Callable[[Verdict], None]) -> llm.Job:
        """This mention as a job for `llm.run`; `done` receives the recorded verdict."""
        request = request_for(self.mention, self.candidates)
        request["model"] = self.model
        return llm.Job(request, verdict_schema(),
                       lambda answer, usage: done(self.record(verdict_of(
                           self.mention, self.candidates, answer, usage, self.model))))

    def record(self, verdict: Verdict) -> Verdict:
        store(self.extraction_id, self.mention_idx, self.mention, self.state_qid, verdict,
              self.reopened_for, retrieval=self.retrieval)
        return verdict


#: How many earlier answers, all confident and all naming one item, settle a
#: title in its state: the next mention of it gets that item without a call.
#: One legislature's member title was asked 1,527 times, the same item every time.
MEMO_FLOOR = 5

#: The model name a settled verdict is recorded under: no call was made.
MEMO = "memo"


def settled(mention: Mention, state_qid: str | None) -> Verdict | None:
    """The verdict a title's earlier answers settle, when there are enough and none dissents.

    Every earlier answer about this title (and jurisdiction) in this state
    must be a confident match to the same item, unvetoed; a single refusal,
    a lower confidence or another item leaves the mention to the model. The
    verdict is recorded under `MEMO`, so it is never mistaken for a model's
    answer, and peploop's verify still judges the statement it leads to.
    """
    if state_qid is None:
        return None
    rows = db.conn().execute(
        "SELECT qid, kind, confidence, veto FROM resolution WHERE state_qid = %s AND lower(title) = lower(%s)"
        " AND coalesce(lower(jurisdiction), '') = coalesce(lower(%s), '') AND model <> %s",
        (state_qid, mention.title, mention.jurisdiction, MEMO),
    ).fetchall()
    if len(rows) < MEMO_FLOOR:
        return None
    qids = {r[0] for r in rows}
    if len(qids) != 1 or None in qids or any(
            kind not in MATCH_KINDS or confidence != "high" or veto for _q, kind, confidence, veto in rows):
        return None
    qid = qids.pop()
    _text, prompt_hash = system_prompt()
    kind = Counter(r[1] for r in rows).most_common(1)[0][0]
    return Verdict(title=mention.title, qid=qid, kind=kind, confidence="high",
                   evidence=f"{len(rows)} earlier mentions of this title in this state, all resolved to {qid}",
                   reason="settled by earlier answers", shortlist=[qid], chosen=qid,
                   prompt_hash=prompt_hash, model=MEMO)


def prepare_mention(
    extraction_id: int,
    mention_idx: int,
    mention: Mention,
    state_qid: str | None,
    model: str = MODEL,
    reopened_for: str = "",
) -> Verdict | Asking:
    """Everything before the question for one mention: the recorded verdict, or the retrieved shortlist."""
    _text, prompt_hash = system_prompt()
    known = recorded(
        extraction_id, mention_idx, prompt_hash, reopened_for=reopened_for
    )
    if known is not None:
        return known
    if not reopened_for:
        memo = settled(mention, state_qid)
        if memo is not None:
            store(extraction_id, mention_idx, mention, state_qid, memo, retrieval=MEMO)
            return memo
    if mention.article is None and mention.lang:
        row = db.conn().execute(
            "SELECT a.text FROM extraction e JOIN article a ON a.qid = e.qid"
            " AND a.lang = %s WHERE e.id = %s",
            (mention.lang, extraction_id),
        ).fetchone()
        mention.article = None if row is None else row[0]
    hits, retrieval = retrieve(mention, state_qid)
    return Asking(extraction_id, mention_idx, mention, state_qid,
                  list(candidates_for(hits, state_qid)), retrieval, reopened_for, model)


def resolve_mention(
    extraction_id: int,
    mention_idx: int,
    mention: Mention,
    state_qid: str | None,
    model: str = MODEL,
    reopened_for: str = "",
) -> tuple[Verdict, bool]:
    """Run the whole second turn for one office mention, once.

    Retrieve, render, ask, settle, record — or read back what was recorded.
    Returns the verdict and whether a request was made, so a caller can tell
    a resumed pass from a paid one. The shortlist is searched with the
    tenure's dates and the state's holder counts, exactly as the bench ranks
    it, so the model reads the same fifteen rows the retrieval measured. The
    article the quotes came from goes in whole when it is under the cap: the
    sentence that settles a rename or a portfolio is often not among the
    quotes the reader's pass copied.

    `reopened_for` asks again under a key of its own; see `reopen`.
    """
    prepared = prepare_mention(extraction_id, mention_idx, mention, state_qid, model, reopened_for)
    if isinstance(prepared, Verdict):
        return prepared, False
    return prepared.record(reconcile(prepared.mention, prepared.candidates, model=model)), True


def reopen(
    extraction_id: int,
    mention_idx: int,
    mention: Mention,
    state_qid: str | None,
    qid: str,
    model: str = MODEL,
) -> tuple[Verdict, bool]:
    """Ask about one mention again, now that `qid` exists to be offered.

    Use it after minting the item a mention could not be placed on. The new
    verdict is a row beside the original, never in place of it, and being the
    newer row it is the one `propose.placements` reads. Reopening twice for the
    same item reads the first answer back instead of paying again.
    """
    return resolve_mention(
        extraction_id, mention_idx, mention, state_qid, model=model,
        reopened_for=qid,
    )


#: The `reopened_for` a re-ask after a retrieval change is stored under. A
#: retrieval change alters neither the prompt nor the rendering, so the ledger
#: would read every old refusal back; this key asks each refusal whose list
#: gained an item once more, and bumping `RENDER_VERSION` instead would re-ask
#: every placed mention too. The next retrieval change takes the next number.
RETRIEVAL_REASK = "retrieval:2"

#: The refusals a better shortlist can turn into a placement. `body-not-seat`
#: is left out: it names the body it saw, and a longer list does not change
#: that the office is a seat in it.
REASKABLE = ("none", "generic-class", "wrong-office")


def refusals(extraction_ids: Sequence[int]) -> dict[tuple[int, int], list[str]]:
    """Map each mention whose newest verdict is a re-askable refusal to its shortlist.

    Newest over every row of the mention, so a mention already placed by a mint
    reopen is not a refusal any more. A mention already re-asked under
    `RETRIEVAL_REASK` is left out whatever its newest row says: the ledger
    would read that answer back, and leaving it out keeps the count honest.
    """
    if not extraction_ids:
        return {}
    _text, prompt_hash = system_prompt()
    rows = db.conn().execute(
        "SELECT extraction_id, mention_idx, shortlist FROM ("
        "  SELECT DISTINCT ON (extraction_id, mention_idx) extraction_id, mention_idx,"
        "   shortlist, qid, kind FROM resolution WHERE extraction_id = ANY(%s)"
        "  ORDER BY extraction_id, mention_idx, id DESC"
        ") newest WHERE qid IS NULL AND kind = ANY(%s)"
        " AND NOT EXISTS (SELECT 1 FROM resolution done"
        "  WHERE done.extraction_id = newest.extraction_id"
        "  AND done.mention_idx = newest.mention_idx AND done.prompt_hash = %s"
        "  AND done.render_version = ANY(%s) AND done.reopened_for = %s)",
        (list(extraction_ids), list(REASKABLE), prompt_hash, list(ANSWERING_RENDERS),
         RETRIEVAL_REASK),
    ).fetchall()
    return {(r[0], r[1]): list(r[2] or []) for r in rows}


def gained(mention: Mention, state_qid: str | None, offered: Sequence[str]) -> list[str]:
    """The QIDs today's shortlist offers that the stored one did not, in rank order.

    A refusal is worth asking again only if the model would read something it
    has not read: the same fifteen get the same `none`.
    """
    before = set(offered)
    return [hit.qid for hit in shortlist_hits(mention, state_qid) if hit.qid not in before]


def reask_work(
    mentions: dict[tuple[int, int], Mention], state_qid: str | None, threads: int = 1
) -> tuple[int, list[tuple[int, int, Mention]]]:
    """Select the refusals among `mentions` whose shortlist gained an item.

    Returns how many re-askable refusals there were and the ones to ask under
    `RETRIEVAL_REASK`, keyed (extraction, mention index) like the ledger. The
    searches run at `threads` because they are the cost: two per refusal.
    """
    refused = refusals(sorted({eid for eid, _idx in mentions}))
    todo = [(key, offered) for key, offered in sorted(refused.items()) if key in mentions]
    with ThreadPoolExecutor(max_workers=threads) as pool:
        flags = list(pool.map(
            lambda item: bool(gained(mentions[item[0]], state_qid, item[1])), todo
        ))
    work = [(eid, idx, mentions[(eid, idx)]) for ((eid, idx), _o), f in zip(todo, flags) if f]
    return len(todo), work
