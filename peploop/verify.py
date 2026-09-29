"""Ask a second model whether one proposed edit is what the article says.

Reach for this after the policy has run and before `apply` writes: it is the
last gate, and the only one that reads. The extractor read the article and
wrote a value; the reconciler placed an office; the policy ruled out what a
rule could rule out. What is left is a proposal that looks right by every
measure a rule can take, and the failure that survives all of that is a
value the article does not quite say -- a year written as a day, a state
secretary placed on the generic item, a demonym read as a predecessor state.
A second reading, by a model that never saw the first one's reasoning, is
the cheapest check there is on that.

Three properties are the design:

* **The verifier sees the edit, not the extraction.** It is shown what would
  land on Wikidata -- property, value with its label, qualifiers with their
  precision spelled out -- beside the article and the item's own claims.
  Never the extractor's JSON, its notes, or the reconciler's reason: a second
  opinion is worth only its uncorrelated error.
* **One proposal per request.** Several decisions in one context is how a
  pass standardises on whoever it answered first.
* **The ledger is keyed on content.** A verdict is stored under a hash of the
  person, the property, the value, the qualifiers and the sources -- not the
  proposal's row id, which a re-propose replaces. So a re-run finds its
  answers by what they were about, and pays only for what is new.

The offline half -- rendering, the fixed answer shape, the key -- is pure, and
`check_verify` pins it without a key, a request or a token.
"""

import hashlib
import json
import os
import threading
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, Sequence

import anthropic
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict

from peploop import db, prompt, propose, reconcile, wikidata

PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "verify.md"

#: A different family from the extractor's on purpose: the same model
#: re-asked reproduced 95% of its own verdicts, which is the noise floor of
#: re-asking and not an independent reading.
MODEL = os.environ.get("PEPLOOP_VERIFY_MODEL", "claude-opus-5")
MAX_TOKENS = 4000
EFFORT = "high"

#: What the model is shown apart from the prompt. Bumped whenever the
#: rendering changes without a prompt edit, because a verdict is keyed by
#: what the model saw.
RENDER_VERSION = 1

#: The same cap the reconciler uses: an article under it goes in whole.
ARTICLE_CAP = reconcile.ARTICLE_CAP

SUPPORTED = "supported"
#: The closed verdict set, in the order the prompt introduces them.
VERDICTS = (
    SUPPORTED,
    "unsupported",
    "contradicted",
    "imprecise",
    "already-recorded",
    "wrong-item",
    "wrong-person",
)
CONFIDENCES = ("high", "medium", "low")

_client_lock = threading.Lock()
_client: anthropic.Anthropic | None = None


class Strict(BaseModel):
    """Base for the answer shape: the API rejects unknown keys."""

    model_config = ConfigDict(extra="forbid")


class Answer(Strict):
    """What the verifier makes of one edit. One shape for every request."""

    verdict: Literal[VERDICTS]
    confidence: Literal[CONFIDENCES]
    evidence: str
    reason: str


@lru_cache(maxsize=1)
def system_prompt() -> tuple[str, str]:
    """Read the frozen system prompt and return it with its sha256 hash."""
    text = PROMPT_PATH.read_text()
    return text, hashlib.sha256(text.encode("utf-8")).hexdigest()


def client() -> anthropic.Anthropic:
    """Return the process-wide Anthropic client, built on first use."""
    global _client
    with _client_lock:
        if _client is None:
            _client = anthropic.Anthropic()
        return _client


@dataclass
class Edit:
    """One proposal as it would land on Wikidata, with everything that attests it.

    Built from the tables by `edit_for`, or by hand in the offline check; the
    rendering is the same code path either way.
    """

    person_qid: str
    person_label: str | None
    property: str
    value: dict[str, Any]
    #: Label and description of an item value, when it has one.
    value_label: str | None = None
    value_description: str | None = None
    #: The real qualifiers: `P580`, `P582`, and any scoping qualifier.
    qualifiers: dict[str, Any] = field(default_factory=dict)
    #: For a position, the placed office as the reconciler rendered it.
    office: reconcile.Candidate | None = None
    #: For a position, the office as the article wrote it.
    mention: dict[str, Any] | None = None
    #: What the item already records for the property, one line per value.
    existing: list[str] = field(default_factory=list)
    #: (language, quote) for every sentence that attested the value.
    quotes: list[tuple[str | None, str]] = field(default_factory=list)
    article_lang: str | None = None
    article: str | None = None


@dataclass
class Verification:
    """The verifier's answer to one edit, as the ledger stores it."""

    verdict: str
    confidence: str
    evidence: str = ""
    reason: str = ""
    prompt_hash: str | None = None
    model: str | None = None
    usage: dict[str, int] | None = None

    @property
    def passed(self) -> bool:
        return self.verdict == SUPPORTED


def content_key(
    person_qid: str, prop: str, value: dict[str, Any], qualifiers: dict[str, Any] | None
) -> str:
    """Identify what a verdict was about, independently of any row id.

    The proposal's own key -- property, value, the qualifiers that reach
    Wikidata -- plus the person and the articles behind it, as (language,
    revision) pairs: the same value read from a re-fetched article is a new
    question, and the same value in a re-inserted row is not.
    """
    attested = (qualifiers or {}).get("_sources") or []
    sources = sorted(
        (str(source.get("lang") or ""), str(source.get("rev") or ""))
        for source in attested
    )
    proposal = propose.proposal_key(prop, value, qualifiers)
    blob = "\n".join([person_qid, proposal, json.dumps(sources)])
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# --- rendering ---------------------------------------------------------------


def _value_text(edit: Edit) -> str:
    value = edit.value
    if "time" in value:
        return prompt.format_time(value["time"], value.get("precision", 11))
    if "id" in value:
        text = value["id"]
        if edit.value_label:
            text += f" {edit.value_label}"
        if edit.value_description:
            text += f" -- {edit.value_description}"
        return text
    return json.dumps(value, ensure_ascii=False)


def _qualifier_text(prop: str, value: Any) -> str:
    name = {"P580": "start", "P582": "end"}.get(prop, prop)
    if isinstance(value, dict) and "time" in value:
        return f"{name}: {prompt.format_time(value['time'], value.get('precision', 11))}"
    if isinstance(value, dict) and "id" in value:
        return f"{name}: {value['id']}"
    return f"{name}: {value}"


def render_edit(edit: Edit) -> str:
    """The per-edit half of the request, in the order the prompt documents."""
    name = wikidata.PROPERTY_NAMES.get(edit.property, edit.property)
    parts = ["# The edit as it would land", ""]
    parts.append(f"item: {edit.person_qid} {edit.person_label or '(no label)'}")
    parts.append(f"property: {edit.property} {name}")
    parts.append(f"value: {_value_text(edit)}")
    qualifiers = [
        _qualifier_text(prop, value) for prop, value in edit.qualifiers.items()
        if prop.startswith("P")
    ]
    parts.append("qualifiers: " + ("; ".join(qualifiers) or "none"))
    if edit.office is not None:
        parts.extend(["", "# The office, as an item", "", edit.office.line()])
    if edit.mention is not None:
        parts.extend(["", "# The office, as the article wrote it", ""])
        parts.append(edit.mention.get("title") or "(no title)")
        if edit.mention.get("jurisdiction"):
            parts.append(f"jurisdiction as written: {edit.mention['jurisdiction']}")
        span = "–".join([edit.mention.get("start") or "", edit.mention.get("end") or ""])
        parts.append(f"tenure as written: {span.strip('–') or 'no dates'}")
    parts.extend(["", f"# What the item already records for {edit.property}", ""])
    if edit.existing:
        parts.extend(f"- {line}" for line in edit.existing)
    else:
        parts.append("- nothing")
    parts.extend(["", "# The quotes", ""])
    if edit.quotes:
        parts.extend(f"- ({lang or '?'}) “{quote}”" for lang, quote in edit.quotes)
    else:
        parts.append("- none")
    parts.extend(["", f"# The article ({edit.article_lang or 'unknown language'})", ""])
    if edit.article is None:
        parts.append("article not available")
    elif len(edit.article) > ARTICLE_CAP:
        parts.append(f"article omitted: {len(edit.article):,} characters, over the cap")
    else:
        parts.append(edit.article)
    parts.extend([
        "",
        "Does this article support exactly this edit, about this person, at this"
        " precision? Answer with the verdict that names what is wrong, or `supported`.",
    ])
    return "\n".join(parts)


def request_for(edit: Edit) -> dict[str, Any]:
    """Assemble one request without sending it."""
    text, _hash = system_prompt()
    return {
        "model": MODEL,
        "max_tokens": MAX_TOKENS,
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": EFFORT},
        "system": [{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user", "content": render_edit(edit)}],
    }


def verify(edit: Edit, model: str = MODEL) -> Verification:
    """Ask the model about one edit and return its answer."""
    _text, prompt_hash = system_prompt()
    request = request_for(edit)
    request["model"] = model
    response = client().messages.parse(output_format=Answer, **request)
    answer = response.parsed_output
    if answer is None:
        raise RuntimeError(
            f"{edit.person_qid} {edit.property}: no parsed output ({response.stop_reason})"
        )
    return Verification(
        verdict=answer.verdict,
        confidence=answer.confidence,
        evidence=answer.evidence,
        reason=answer.reason,
        prompt_hash=prompt_hash,
        model=model,
        usage={
            "input_tokens": response.usage.input_tokens,
            "cache_creation_input_tokens": response.usage.cache_creation_input_tokens or 0,
            "cache_read_input_tokens": response.usage.cache_read_input_tokens or 0,
            "output_tokens": response.usage.output_tokens,
        },
    )


# --- the ledger ---------------------------------------------------------------


LEDGER_COLUMNS = (
    "verdict", "confidence", "evidence", "reason", "prompt_hash", "model", "usage_json",
)


def recorded_many(keys: Sequence[str]) -> dict[str, Verification]:
    """The verdicts already stored for these content keys under the current prompt.

    Any model's answer counts, newest first: the key says what was asked and
    the prompt hash says how, and a model swap is a reason to re-ask by hand
    rather than to forget what was answered.
    """
    if not keys:
        return {}
    _text, prompt_hash = system_prompt()
    rows = db.conn().execute(
        f"SELECT DISTINCT ON (proposal_key) proposal_key, {', '.join(LEDGER_COLUMNS)}"
        " FROM verification WHERE proposal_key = ANY(%s) AND prompt_hash = %s"
        " AND render_version = %s ORDER BY proposal_key, id DESC",
        (list(keys), prompt_hash, RENDER_VERSION),
    ).fetchall()
    out = {}
    for row in rows:
        record = dict(zip(LEDGER_COLUMNS, row[1:]))
        record["usage"] = record.pop("usage_json")
        out[row[0]] = Verification(**record)
    return out


def store(
    key: str, proposal_id: int, person_qid: str, prop: str, verification: Verification
) -> None:
    """Append one verdict to the ledger. Never replaces: the key is what was asked."""
    db.conn().execute(
        "INSERT INTO verification (proposal_key, proposal_id, person_qid, property,"
        " prompt_hash, render_version, model, verdict, confidence, evidence, reason,"
        " usage_json) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
        " ON CONFLICT (proposal_key, prompt_hash, render_version, model) DO NOTHING",
        (
            key, proposal_id, person_qid, prop, verification.prompt_hash, RENDER_VERSION,
            verification.model or MODEL, verification.verdict, verification.confidence,
            verification.evidence, verification.reason,
            Jsonb(verification.usage) if verification.usage is not None else None,
        ),
    )


# --- from the tables ------------------------------------------------------


def _labels(qids: Sequence[str]) -> dict[str, tuple[str | None, str | None]]:
    """Label and description per item, through the cached item reader."""
    wanted = sorted({qid for qid in qids if qid})
    if not wanted:
        return {}
    out = {}
    for qid, item in wikidata.fetch_items(wanted, props="labels|descriptions").items():
        descriptions = item.get("descriptions") or {}
        described = next(
            (descriptions[lang]["value"] for lang in ("en", "mul") if lang in descriptions),
            None,
        )
        out[qid] = (wikidata.best_label(item), described)
    return out


def existing_lines(
    entity: dict[str, Any], prop: str, labels: dict[str, tuple[str | None, str | None]]
) -> list[str]:
    """What the item already records for one property, one line per statement."""
    lines = []
    for claim in entity.get("claims", {}).get(prop, []):
        if claim.get("rank") == "deprecated":
            continue
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(value, dict) and "time" in value:
            lines.append(prompt.format_time(value["time"], value.get("precision", 0)))
        elif isinstance(value, dict) and "id" in value:
            label = labels.get(value["id"], (None, None))[0]
            text = f"{value['id']} {label}" if label else value["id"]
            span = propose.span_of(claim)
            if span:
                text += f" [{propose.span_text(span)}]"
            lines.append(text)
        else:
            lines.append("(unknown value)")
    return lines


def _office(resolution_id: int | None, qid: str) -> tuple[reconcile.Candidate | None, dict | None]:
    """Replay the reconciler's rendering of the placed office, and the mention."""
    if resolution_id is None:
        return None, None
    record, candidates = reconcile.replay_shortlist(resolution_id)
    office = next((c for c in candidates if c.qid == qid), None)
    mention = {
        "title": record.get("title"), "jurisdiction": record.get("jurisdiction"),
        "start": record.get("start_text"), "end": record.get("end_text"),
        "lang": record.get("lang"),
    }
    return office, mention


def edit_for(row: dict[str, Any]) -> Edit:
    """Build the edit one proposal row would make, from the tables."""
    qid, prop, value = row["person_qid"], row["property"], row["value"]
    qualifiers = dict(row.get("qualifiers") or {})
    item = db.conn().execute("SELECT json FROM item WHERE qid = %s", (qid,)).fetchone()
    entity = item[0] if item else {}
    wanted = [value.get("id")] if "id" in value else []
    wanted.extend(wikidata.claim_qids(entity, prop, include_deprecated=False))
    labels = _labels(wanted)
    sources = qualifiers.get("_sources") or [
        {"lang": row.get("source_lang"), "quote": row.get("quote")}
    ]
    quotes = [(s.get("lang"), s["quote"]) for s in sources if s.get("quote")]
    lang = next((s.get("lang") for s in sources if s.get("lang")), row.get("source_lang"))
    article = None
    if lang:
        found = db.conn().execute(
            "SELECT text FROM article WHERE qid = %s AND lang = %s", (qid, lang)
        ).fetchone()
        article = found[0] if found else None
    office, mention = (None, None)
    if prop == "P39":
        office, mention = _office(row.get("resolution_id"), value.get("id", ""))
    label, description = labels.get(value.get("id", ""), (None, None))
    return Edit(
        person_qid=qid,
        person_label=wikidata.best_label(entity),
        property=prop,
        value=value,
        value_label=label,
        value_description=description,
        qualifiers={k: v for k, v in qualifiers.items() if k.startswith("P")},
        office=office,
        mention=mention,
        existing=existing_lines(entity, prop, labels),
        quotes=quotes,
        article_lang=lang,
        article=article,
    )


ROW_COLUMNS = (
    "id", "person_qid", "property", "value", "qualifiers", "quote", "source_lang",
    "resolution_id",
)


def pending_rows(qid: str) -> list[dict[str, Any]]:
    """The proposals of one person the policy has held for the verifier."""
    rows = db.conn().execute(
        f"SELECT {', '.join(ROW_COLUMNS)} FROM proposal WHERE person_qid = %s"
        " AND status = 'pending' ORDER BY id",
        (qid,),
    )
    return [dict(zip(ROW_COLUMNS, row)) for row in rows]


def verify_proposal(row: dict[str, Any], model: str = MODEL) -> tuple[Verification, bool]:
    """Verify one proposal once: read the ledger, or render, ask and record.

    Returns the verdict and whether a request was made.
    """
    key = content_key(row["person_qid"], row["property"], row["value"], row.get("qualifiers"))
    known = recorded_many([key]).get(key)
    if known is not None:
        return known, False
    verification = verify(edit_for(row), model=model)
    store(key, row["id"], row["person_qid"], row["property"], verification)
    return verification, True
