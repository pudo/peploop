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

import hashlib
import json
import os
import threading
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, Optional, Sequence

import anthropic
from pydantic import BaseModel, ConfigDict, create_model

from peploop import db, positions

PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "reconcile.md"

MODEL = os.environ.get("PEPLOOP_MODEL", "claude-sonnet-5")
MAX_TOKENS = 4000
EFFORT = "medium"

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

_client_lock = threading.Lock()
_client: anthropic.Anthropic | None = None


class Strict(BaseModel):
    """Base for the verdict shape: the API rejects unknown keys."""

    model_config = ConfigDict(extra="forbid")


@lru_cache(maxsize=1)
def system_prompt() -> tuple[str, str]:
    """Read the frozen system prompt and return it with its sha256 hash.

    The hash is what a stored verdict is keyed by, so a prompt edit makes the
    old answers re-askable instead of silently mixing two instructions.
    """
    text = PROMPT_PATH.read_text()
    return text, hashlib.sha256(text.encode("utf-8")).hexdigest()


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

    def line(self) -> str:
        """One line for the shortlist, in the order the prompt documents."""
        parts = [f"{self.qid} | {self.label or '(no label)'}"]
        parts.append(self.description or "(no description)")
        if self.kinds:
            parts.append("kind: " + ", ".join(self.kinds))
        if self.body:
            parts.append("part of: " + self.body)
        span = "–".join([self.inception or "", self.abolished or ""]).strip("–")
        if span:
            parts.append("exists: " + span)
        parts.append(
            "holders: " + ("uncounted" if self.holders is None else str(self.holders))
        )
        if self.tags:
            parts.append("tags: " + ", ".join(self.tags))
        # Shown only where it means something: the qualifier column is filled
        # for many items, and the one case it changes an answer is the office
        # a state records generically on purpose.
        if "generic-by-convention" in self.tags and self.scope_qualifier:
            parts.append("used with: " + self.scope_qualifier)
        if self.matched:
            parts.append("matched: " + self.matched)
        return " | ".join(parts)


@dataclass
class Mention:
    """An office as round one wrote it, with what attests to it."""

    title: str
    jurisdiction: str | None = None
    start: str | None = None
    end: str | None = None
    quotes: list[str] = field(default_factory=list)
    lang: str | None = None


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

    @property
    def resolved(self) -> bool:
        return self.qid is not None

    def as_dict(self) -> dict[str, Any]:
        return {
            "title": self.title, "qid": self.qid, "kind": self.kind,
            "confidence": self.confidence, "evidence": self.evidence,
            "reason": self.reason, "shortlist": list(self.shortlist),
            "chosen": self.chosen, "veto": self.veto,
            "prompt_hash": self.prompt_hash,
        }


def verdict_schema(qids: Sequence[str]) -> type[Strict]:
    """Build the answer shape for one shortlist, with `qid` closed over it.

    The enum is per request because that is the only place the closed set
    exists: a schema naming every QID in the table would constrain nothing.
    An empty shortlist yields a schema whose only legal `qid` is null, which
    is the honest shape for "there was nothing to choose from".
    """
    offered = tuple(dict.fromkeys(qids))
    qid_type: Any = Optional[Literal[offered]] if offered else type(None)
    return create_model(
        "OfficeVerdict",
        __base__=Strict,
        __doc__="Which offered position item the office names, or why none does.",
        qid=(qid_type, ...),
        kind=(Literal[KINDS], ...),
        confidence=(Literal["high", "medium", "low"], ...),
        evidence=(str, ...),
        reason=(str, ...),
    )


def render_shortlist(candidates: Sequence[Candidate]) -> str:
    """The candidates as the model sees them, one whole item per line."""
    lines = [f"- {candidate.line()}" for candidate in candidates]
    return "\n".join(lines) or "- (nothing retrieved)"


def render_mention(mention: Mention, candidates: Sequence[Candidate]) -> str:
    """The per-office half of the request: the evidence, then the candidates."""
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
    "holders", "holders_by_country", "scope_qualifier",
)


def _body_labels(qids: Sequence[str]) -> dict[str, str]:
    """Name the bodies a shortlist points at, where the table knows a name.

    Local only, and no request: a body that is itself a loaded item is named
    from its own row, and one that is not stays a QID. The alternative is a
    network round trip in the middle of rendering, which would put the
    offline check out of reach for the sake of a nicer line.
    """
    wanted = sorted({qid for qid in qids if qid})
    if not wanted:
        return {}
    rows = db.conn().execute(
        "SELECT qid, label FROM position WHERE qid = ANY(%s) AND label IS NOT NULL",
        (wanted,),
    ).fetchall()
    return {qid: label for qid, label in rows}


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
    bodies = _body_labels([r.get("body_qid") for r in by_qid.values()])
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
            inception=str(record["inception"]) if record.get("inception") else None,
            abolished=str(record["abolished"]) if record.get("abolished") else None,
            holders=positions.holder_count(record, state_qid, holder_scope),
            tags=tuple(hit.tags),
            scope_qualifier=record.get("scope_qualifier"),
            matched=hit.name,
        ))
    return out


def client() -> anthropic.Anthropic:
    """Return the process-wide Anthropic client, built on first use."""
    global _client
    with _client_lock:
        if _client is None:
            _client = anthropic.Anthropic()
        return _client


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
    return {
        "model": MODEL,
        "max_tokens": MAX_TOKENS,
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": EFFORT},
        "system": [
            {"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}
        ],
        "messages": [
            {"role": "user", "content": render_mention(mention, candidates)}
        ],
    }


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
    shortlist = [candidate.qid for candidate in candidates]
    _text, prompt_hash = system_prompt()
    request = request_for(mention, candidates)
    request["model"] = model
    response = client().messages.parse(
        output_format=verdict_schema(shortlist), **request
    )
    answer = response.parsed_output
    if answer is None:
        raise RuntimeError(
            f"{mention.title!r}: no parsed output ({response.stop_reason})"
        )
    verdict = Verdict(
        title=mention.title,
        kind=answer.kind,
        confidence=answer.confidence,
        evidence=answer.evidence,
        reason=answer.reason,
        shortlist=shortlist,
        chosen=answer.qid,
        prompt_hash=prompt_hash,
    )
    verdict.qid, verdict.veto = settle(verdict.kind, verdict.chosen, shortlist)
    return verdict


def as_jsonl(verdict: Verdict) -> str:
    """Render one verdict as the ledger line a later increment appends."""
    return json.dumps(verdict.as_dict(), ensure_ascii=False, sort_keys=True)
