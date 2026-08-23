"""Ask a model to judge the cases mechanics can't, and keep the answers.

Reach for this when a lane has exhausted its mechanical channels and the tail
needs judgement — is this office really Egyptian, or is that just where its
holders happen to come from? The workbench has run four such passes by hand,
each one a fleet of ad-hoc agents whose prompt vanished with the session. That
is the gap this closes: the prompt is a file, the model and effort are
arguments, and the verdicts are a ledger you can re-run against.

Three properties matter more than the API call in the middle:

* **The prompt is committed.** A pass whose instructions live only in a chat
  transcript cannot be audited, re-run, or improved. Earlier chunks converged
  around whoever answered first precisely because nobody could see what the
  others had been asked.
* **The ledger is the resume point.** Verdicts append to one JSONL and already
  answered items are skipped, so an interrupted run costs nothing to restart
  and a widened candidate set only pays for what is new.
* **The schema is enforced at the API.** `output_config.format` constrains the
  reply to the verdict shape, so a renderer never has to parse prose or repair
  a truncated object.

The batch size is the one number worth tuning. Items in a batch share the
cached prompt and one round trip, but they also share a context — too many and
the model starts reasoning about the batch rather than the item, which is the
convergence failure again, one level down.
"""

import hashlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

import anthropic

#: Judgement passes are the expensive, hard-to-redo half of a campaign; they run
#: on the most capable model unless a caller says otherwise.
MODEL = "claude-opus-5"

#: `high` is the floor for intelligence-sensitive work. The corpus-bias traps
#: these prompts are built around are exactly the kind a cheaper pass walks into.
EFFORT = "high"

#: Enough room for a batch of verdicts plus adaptive thinking, which is on by
#: default on this model and shares the budget with the response.
MAX_TOKENS = 32000

#: Per-million-token list prices, for the run's cost line.
PRICE_IN, PRICE_OUT = 5.0, 25.0
PRICE_CACHE_READ, PRICE_CACHE_WRITE = PRICE_IN * 0.1, PRICE_IN * 1.25


@dataclass
class Usage:
    """What a pass cost, accumulated across every request."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read: int = 0
    cache_write: int = 0
    requests: int = 0
    failures: int = 0

    def add(self, usage: Any) -> None:
        self.requests += 1
        self.input_tokens += getattr(usage, "input_tokens", 0) or 0
        self.output_tokens += getattr(usage, "output_tokens", 0) or 0
        self.cache_read += getattr(usage, "cache_read_input_tokens", 0) or 0
        self.cache_write += getattr(usage, "cache_creation_input_tokens", 0) or 0

    @property
    def dollars(self) -> float:
        return (
            self.input_tokens * PRICE_IN
            + self.output_tokens * PRICE_OUT
            + self.cache_read * PRICE_CACHE_READ
            + self.cache_write * PRICE_CACHE_WRITE
        ) / 1_000_000

    def line(self) -> str:
        return (
            f"{self.requests} requests, {self.failures} failed | "
            f"in {self.input_tokens:,} (+{self.cache_read:,} cached, "
            f"{self.cache_write:,} written) out {self.output_tokens:,} | "
            f"${self.dollars:.2f}"
        )


@dataclass
class Ledger:
    """Append-only verdict file, and the set of keys already answered.

    The keys are read back from the file rather than tracked in memory, so a
    resumed run and a fresh one behave identically.
    """

    path: Path
    key: str = "qid"
    done: set = field(default_factory=set)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def load(self) -> "Ledger":
        if self.path.exists():
            for line in self.path.read_text().splitlines():
                if line.strip():
                    try:
                        self.done.add(json.loads(line)[self.key])
                    except (json.JSONDecodeError, KeyError):
                        continue
        return self

    def write(self, rows: Iterable[Dict[str, Any]]) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a") as fh:
                for row in rows:
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                    self.done.add(row.get(self.key))


def envelope(item_schema: Dict[str, Any]) -> Dict[str, Any]:
    """Wrap a per-item schema in the object the API's format parameter needs.

    Structured outputs require an object at the root, so a pass that returns a
    list returns it under one key. `additionalProperties: false` is required on
    every object in the schema, not just the root.
    """
    return {
        "type": "object",
        "properties": {"verdicts": {"type": "array", "items": item_schema}},
        "required": ["verdicts"],
        "additionalProperties": False,
    }


def _chunks(items: Sequence[Any], size: int) -> List[List[Any]]:
    return [list(items[i:i + size]) for i in range(0, len(items), size)]


def as_json(batch: Sequence[Dict[str, Any]]) -> str:
    """Default user turn: the batch as JSON. Right when items are uniform."""
    return json.dumps(list(batch), ensure_ascii=False)


def _system(prompt: str, extra: Sequence[str]) -> List[Dict[str, Any]]:
    """The system blocks, with breakpoints at the stability boundaries.

    Two, not one, and the reason is reuse across runs rather than within one:
    the instructions are identical for every pass of a given kind, while a
    reference corpus (a position gazetteer, a country table) changes per run. A
    breakpoint after the prompt survives switching corpus; a second one after
    the corpus serves every item in the run. Marking only the last block would
    make each run rewrite the prompt it shares with all the others.

    The API allows four breakpoints, so only the prompt and the final extra
    block are marked however many blocks a caller passes.
    """
    blocks: List[Dict[str, Any]] = [{"type": "text", "text": prompt}]
    blocks[0]["cache_control"] = {"type": "ephemeral"}
    for text in extra:
        blocks.append({"type": "text", "text": text})
    if len(blocks) > 1:
        blocks[-1]["cache_control"] = {"type": "ephemeral"}
    return blocks


def classify(
    items: Sequence[Dict[str, Any]],
    *,
    prompt: str,
    item_schema: Dict[str, Any],
    ledger: Ledger,
    extra_system: Sequence[str] = (),
    render: Callable[[Sequence[Dict[str, Any]]], str] = as_json,
    usage: Optional[Usage] = None,
    model: str = MODEL,
    effort: str = EFFORT,
    batch_size: int = 10,
    workers: int = 6,
    max_tokens: int = MAX_TOKENS,
    client: Optional[Any] = None,
    log: Callable[[str], None] = print,
) -> Usage:
    """Judge every unanswered item, writing verdicts to the ledger as they land.

    Returns the run's usage. Items already in the ledger are skipped, so this is
    safe to re-run: widening the candidate set costs only the new items, and an
    interrupted run resumes where it stopped.

    `extra_system` holds reference material that is stable for the whole run but
    not across runs — a position gazetteer, a country table. It is cached
    separately from the prompt; see `_system`.

    `render` turns a batch into its user turn. The default serialises the batch
    as JSON, which is right when items are uniform records. Pass a renderer with
    `batch_size=1` when items carry variable-length evidence: JSON-escaping a
    40 KB article wastes tokens, and one large item in a batch of ten inflates
    the context of the other nine for nothing.

    Every row written carries a `_pass` block naming the model, the effort and a
    hash of the prompt. Without it a ledger holding rows from two prompt
    revisions is indistinguishable from a clean one — which has happened
    (`tasks/jurisdictions.md`), and cost an out-of-band copy of the file.
    """
    usage = usage or Usage()
    todo = [i for i in items if i.get(ledger.key) not in ledger.done]
    log(f"{len(items)} items, {len(items) - len(todo)} already judged, "
        f"{len(todo)} to go")
    if not todo:
        return usage

    client = client or anthropic.Anthropic()
    batches = _chunks(todo, batch_size)
    total = len(batches)
    schema = envelope(item_schema)
    system = _system(prompt, extra_system)
    provenance = {
        "model": model,
        "effort": effort,
        "prompt_sha": hashlib.sha256(prompt.encode()).hexdigest()[:12],
    }
    lock = threading.Lock()

    def run(batch: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        with client.messages.stream(
            model=model,
            max_tokens=max_tokens,
            system=system,
            output_config={"effort": effort,
                           "format": {"type": "json_schema", "schema": schema}},
            messages=[{"role": "user", "content": render(batch)}],
        ) as stream:
            message = stream.get_final_message()
        with lock:
            usage.add(message.usage)
        if message.stop_reason == "refusal":
            raise RuntimeError(f"refused: {getattr(message, 'stop_details', None)}")
        text = next(b.text for b in message.content if b.type == "text")
        verdicts = json.loads(text)["verdicts"]
        # The schema constrains every field's shape and no field's value, so it
        # cannot notice a dropped, duplicated or transposed subject. Checking the
        # keys here rather than after the run means a bad batch fails, is
        # counted, and is re-sent on the next run — instead of writing rows that
        # look judged. `classify_jurisdictions.py` caught strays post-hoc and
        # missing items not at all.
        asked = [i.get(ledger.key) for i in batch]
        answered = [v.get(ledger.key) for v in verdicts]
        if sorted(map(str, answered)) != sorted(map(str, asked)):
            raise RuntimeError(
                f"asked {len(asked)} items, got {len(answered)} verdicts for "
                f"{sorted(set(map(str, answered)) ^ set(map(str, asked)))[:6]}"
            )
        for verdict in verdicts:
            verdict["_pass"] = provenance
        return verdicts

    done = 0
    # Send the first batch alone. A cache entry is readable only once the
    # response that wrote it has begun streaming, so a fan-out that starts
    # every worker at once has each of them write the prompt instead of one
    # writing and the rest reading — measured on this pass as two writes and
    # zero reads across two concurrent requests.
    if len(batches) > 1:
        try:
            ledger.write(run(batches[0]))
            done = 1
            log(f"  [1/{len(batches)}] prompt cached | {usage.line()}")
        except Exception as exc:
            usage.failures += 1
            log(f"  [1/{len(batches)}] first batch failed: {exc}")
        batches = batches[1:]

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(run, b): b for b in batches}
        for future in as_completed(futures):
            done += 1
            try:
                verdicts = future.result()
            except Exception as exc:
                with lock:
                    usage.failures += 1
                first = futures[future][0].get(ledger.key, "?")
                log(f"  [{done}/{total}] batch at {first} failed: {exc}")
                continue
            ledger.write(verdicts)
            log(f"  [{done}/{total}] {len(verdicts)} verdicts | {usage.line()}")
    return usage
