"""The pieces every model pass shares: one client, a prompt read with its hash, token usage, and spending.

Each pass keeps its own ledger and its own content key, because what makes two
requests "the same question" differs per pass. What does not differ lives here:
the process-wide client, the rule that a stored answer is keyed by the sha256
of the prompt file's text (so an edit makes the old answers re-askable instead
of mixing two instructions), the four token counts a ledger row records, the
run's spending against its budget, and the one way a pass's many independent
questions go out -- live under a pool, or as Message Batches at half price.
"""

import hashlib
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import anthropic
from anthropic.lib._parse._transform import transform_schema
from psycopg.types.json import Jsonb
from pydantic import BaseModel, TypeAdapter

from peploop import db

_client: anthropic.Anthropic | None = None
_client_lock = threading.Lock()


def client() -> anthropic.Anthropic:
    """Return the process-wide Anthropic client, built on first use."""
    global _client
    with _client_lock:
        if _client is None:
            _client = anthropic.Anthropic()
        return _client


def system_prompt(path: Path) -> tuple[str, str]:
    """Read a frozen prompt file and return it with the sha256 of its text."""
    text = path.read_text()
    return text, hashlib.sha256(text.encode("utf-8")).hexdigest()


def usage(response: Any) -> dict[str, int]:
    """The token counts of one response, as every ledger row stores them."""
    return {
        "input_tokens": response.usage.input_tokens,
        "cache_creation_input_tokens": response.usage.cache_creation_input_tokens or 0,
        "cache_read_input_tokens": response.usage.cache_read_input_tokens or 0,
        "output_tokens": response.usage.output_tokens,
    }


#: List prices per million tokens: input, output, cache read, cache write. A
#: model not listed is reported in tokens only, never priced by a guess.
PRICES: dict[str, tuple[float, float, float, float]] = {
    "claude-sonnet-5": (2.0, 10.0, 0.20, 2.50),
    "claude-sonnet-5-5": (2.0, 10.0, 0.20, 2.50),
    "claude-opus-5": (5.0, 25.0, 0.50, 6.25),
    "claude-opus-5-5": (4.0, 20.0, 0.20, 5.00),
    "claude-haiku-4-5": (1.0, 5.0, 0.10, 1.25),
}

#: What a batched request costs against the same request sent live.
BATCH_DISCOUNT = 0.5


def cost(model: str, usage: dict[str, int]) -> float | None:
    """Dollars for one usage tally at list price, or None for an unpriced model.

    A usage marked `batch` (stored so by `run` in batch mode) was billed at
    the batch discount.
    """
    price = PRICES.get(model)
    if price is None:
        return None
    p_in, p_out, p_read, p_write = price
    dollars = (usage.get("input_tokens", 0) * p_in + usage.get("output_tokens", 0) * p_out
               + usage.get("cache_read_input_tokens", 0) * p_read
               + usage.get("cache_creation_input_tokens", 0) * p_write) / 1e6
    return dollars * BATCH_DISCOUNT if usage.get("batch") else dollars


# --- the run's spending -------------------------------------------------------
#
# One process is one run. Everything it pays for goes through `charge`, and a
# budget set for the run (`--budget`, or PEPLOOP_RUN_BUDGET) stops it from
# asking once spent: what was answered is in the ledgers, so the next run
# carries on where this one stopped. A cap rather than a question, so an
# unattended sweep still runs to its end.


class BudgetSpent(RuntimeError):
    """The run's budget is spent; nothing more is asked in this process."""


_spend_lock = threading.Lock()
_spent = 0.0
_budget: float | None = float(os.environ["PEPLOOP_RUN_BUDGET"]) if os.environ.get("PEPLOOP_RUN_BUDGET") else None


def set_budget(dollars: float | None) -> None:
    """Cap what this process may spend, in list-price dollars; None lifts the cap."""
    global _budget
    _budget = dollars


def spent() -> float:
    """What this process has spent so far, at list price."""
    return _spent


def left() -> float | None:
    """What is left of the budget, or None when there is no cap."""
    return None if _budget is None else max(0.0, _budget - _spent)


def charge(model: str, tally: dict[str, int]) -> None:
    """Count one answered (or cut-off) call against the run's spending."""
    global _spent
    with _spend_lock:
        _spent += cost(model, tally) or 0.0


def guard() -> None:
    """Refuse to ask once the run's budget is spent."""
    if _budget is not None and _spent >= _budget:
        raise BudgetSpent(f"the run's budget of ${_budget:.2f} is spent (${_spent:.2f})")


def send(**request: Any) -> Any:
    """Send one Messages request, live, against the budget; `output_format` makes it a parse.

    Every pass's single calls go through here, so each is counted in the
    run's spending and none goes out past its budget.
    """
    guard()
    if "output_format" in request:
        response = client().messages.parse(**request)
    else:
        response = client().messages.create(**request)
    charge(request["model"], usage(response))
    return response


# --- many questions at once -----------------------------------------------------


@dataclass
class Job:
    """One question of a pass: the request, the shape of its answer, and where the answer goes.

    `params` is a Messages request without its output format; `done` stores
    the parsed answer and its usage in the pass's own ledger. `stream` is for
    answers too long for a non-streamed live request (mint's categorize).
    """

    params: dict[str, Any]
    schema: type[BaseModel]
    done: Callable[[BaseModel, dict[str, int]], None]
    stream: bool = False
    #: Called with the error when no answer could be had, after the run gave up on it.
    failed: Callable[[Exception], None] | None = None

    def request(self) -> dict[str, Any]:
        """The request as it goes out, with the answer's schema as its output format."""
        config = {**self.params.get("output_config", {}),
                  "format": {"type": "json_schema", "schema": transform_schema(TypeAdapter(self.schema).json_schema())}}
        return {**self.params, "output_config": config}

    @property
    def id(self) -> str:
        """The request's content hash: a batch's custom id, and how a resumed run finds its result."""
        return hashlib.sha256(json.dumps(self.request(), sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class Unparsed(RuntimeError):
    """An answer that did not parse into its schema, with what it cost."""

    def __init__(self, stop_reason: str | None, tally: dict[str, int], body: str):
        super().__init__(f"answer not parseable (stop_reason={stop_reason}, {len(body)} chars)")
        self.stop_reason = stop_reason
        self.usage = tally
        self.body = body


def parse(schema: type[BaseModel], body: str, stop_reason: str | None, tally: dict[str, int]) -> BaseModel:
    """Read an answer's text as its schema, or raise `Unparsed` carrying its usage."""
    try:
        return schema.model_validate_json(body)
    except ValueError:
        raise Unparsed(stop_reason, tally, body) from None


def text_of(content: Any) -> str:
    """The text an answer's content blocks carry, its thinking left out."""
    return "".join(getattr(block, "text", "") for block in content if getattr(block, "type", "") == "text")


@dataclass
class Outcome:
    """What `run` did: answered, failed, left unasked by the budget, and how."""

    answered: int = 0
    failed: int = 0
    unasked: int = 0
    batched: int = 0
    estimate: float | None = None
    errors: list[str] = field(default_factory=list)


#: Below this many requests a pass goes live: a batch is worth its wait only in bulk.
BATCH_MIN = int(os.environ.get("PEPLOOP_BATCH_MIN", "50"))
#: Whether bulk passes batch at all; `--live` (or PEPLOOP_LIVE=1) sends everything live.
_batching = os.environ.get("PEPLOOP_LIVE", "") not in ("1", "true", "yes")
#: Requests per Message Batch: far under the API's limits even for long articles.
BATCH_SIZE = 2000
#: Seconds between looks at a submitted batch.
POLL_SECONDS = 30


def set_batching(enabled: bool) -> None:
    """Let bulk passes go out as Message Batches, or send everything live."""
    global _batching
    _batching = enabled


def batches(n: int) -> bool:
    """Whether n jobs go out as Message Batches by default."""
    return _batching and n >= BATCH_MIN


def run(pass_: str, jobs: list[Job], log: Callable[[str], None] = print, workers: int = 4,
        batch: bool | None = None) -> Outcome:
    """Ask every job once and hand each answer to its `done`; live, or as batches at half price.

    The pass has already dropped what its ledger answered. The count and its
    estimate are printed first; a batch goes out when there are at least
    `BATCH_MIN` jobs and batching is on, unless `batch` says otherwise. A
    job that fails in a batch is asked again live; one that fails live is a
    line of output and is asked by the next run. Past the budget nothing more
    is asked, and the jobs left are counted as `unasked`.
    """
    from peploop import costs  # costs reads the ledgers through llm's prices

    out = Outcome()
    if not jobs:
        return out
    model = jobs[0].params["model"]
    batched = batch if batch is not None else batches(len(jobs))
    out.estimate = costs.estimate(pass_, model, len(jobs), batched=batched)
    shown = f"~${out.estimate:.2f}" if out.estimate is not None else "cost unknown (no history)"
    budget = left()
    log(f"{pass_}: {len(jobs)} to ask on {model}, {shown}, {'as batches' if batched else 'live'}"
        + (f"; ${budget:.2f} of the budget left" if budget is not None else ""))
    if batched:
        retry = _run_batches(pass_, jobs, out, log)
        if retry:
            log(f"{pass_}: {len(retry)} batch results failed; asking them live")
            _run_live(retry, out, log, workers)
    else:
        _run_live(jobs, out, log, workers)
    log(f"{pass_}: {out.answered} answered" + (f" ({out.batched} in batches)" if out.batched else "")
        + (f", {out.failed} failed" if out.failed else "")
        + (f", {out.unasked} left unasked by the budget" if out.unasked else ""))
    return out


def _run_live(jobs: list[Job], out: Outcome, log: Callable[[str], None], workers: int) -> None:
    stop = threading.Event()

    def one(job: Job) -> str:
        if stop.is_set():
            return "unasked"
        try:
            guard()
        except BudgetSpent as exc:
            if not stop.is_set():
                log(str(exc))
            stop.set()
            return "unasked"
        request = job.request()
        if job.stream:
            with client().messages.stream(**request) as streamed:
                response = streamed.get_final_message()
        else:
            response = client().messages.create(**request)
        tally = usage(response)
        charge(request["model"], tally)
        job.done(parse(job.schema, text_of(response.content), response.stop_reason, tally), tally)
        return "answered"

    def count(job: Job, fut: Any) -> None:
        try:
            status = fut.result()
        except Exception as exc:  # noqa: BLE001 -- one failed question is a line, not a dead run
            out.failed += 1
            out.errors.append(f"{type(exc).__name__}: {str(exc).splitlines()[0][:120]}")
            log(f"  failed: {out.errors[-1]}")
            if job.failed:
                job.failed(exc)
            return
        if status == "answered":
            out.answered += 1
        else:
            out.unasked += 1

    if workers <= 1:
        # On this thread's connection: a pool thread opens its own, which
        # cannot see a caller's temporary tables.
        for job in jobs:
            fut = _Ran(one, job)
            count(job, fut)
        return
    with ThreadPoolExecutor(workers) as pool:
        futures = {pool.submit(one, job): job for job in jobs}
        for i, fut in enumerate(as_completed(futures), 1):
            count(futures[fut], fut)
            if i % 100 == 0:
                log(f"  asked {i}/{len(jobs)}")


class _Ran:
    """A call made inline, read like a finished future."""

    def __init__(self, fn: Callable[..., Any], *args: Any):
        try:
            self._value, self._error = fn(*args), None
        except Exception as exc:  # noqa: BLE001 -- re-raised by result()
            self._value, self._error = None, exc

    def result(self) -> Any:
        if self._error is not None:
            raise self._error
        return self._value


# --- Message Batches ------------------------------------------------------------
#
# A batch is recorded before it is submitted and bound to the API's id after,
# as the send ledger does for QuickStatements: a run that dies after paying
# finds its batch again (`_bind_lost`, `_collect`) and stores what it bought.
# Results are kept whole in `llm_batch_result`, keyed by the job's content
# hash, so a job a later run builds identically is served from there.


def _run_batches(pass_: str, jobs: list[Job], out: Outcome, log: Callable[[str], None]) -> list[Job]:
    """Answer jobs through Message Batches; return the jobs a batch could not answer."""
    by_id: dict[str, Job] = {}
    for job in jobs:
        by_id.setdefault(job.id, job)
    _bind_lost(pass_, log)
    for row in db.conn().execute("SELECT id FROM llm_batch WHERE pass = %s AND status = 'submitted'", (pass_,)):
        _collect(row[0], log)
    retry: list[Job] = []
    _apply(by_id, out, retry)
    todo = list(by_id.values())
    if not todo:
        return retry
    budget = left()
    if budget is not None and out.estimate:
        fits = int(budget / (out.estimate / len(jobs))) if out.estimate > 0 else len(todo)
        if fits < len(todo):
            log(f"{pass_}: the budget covers about {fits} of {len(todo)}; submitting those")
            out.unasked += len(todo) - fits
            todo = todo[:fits]
    model = todo[0].params["model"]
    submitted = []
    for start in range(0, len(todo), BATCH_SIZE):
        chunk = todo[start:start + BATCH_SIZE]
        share = out.estimate * len(chunk) / len(jobs) if out.estimate is not None else None
        local = db.conn().execute(
            "INSERT INTO llm_batch (pass, model, custom_ids, estimate, status) VALUES (%s, %s, %s, %s, 'sending')"
            " RETURNING id", (pass_, model, [j.id for j in chunk], share)).fetchone()[0]
        created = client().messages.batches.create(
            requests=[{"custom_id": j.id, "params": j.request()} for j in chunk])
        db.conn().execute("UPDATE llm_batch SET api_id = %s, status = 'submitted' WHERE id = %s", (created.id, local))
        submitted.append(local)
        log(f"{pass_}: batch {created.id} submitted with {len(chunk)} requests")
    for local in submitted:
        _collect(local, log)
    _apply(by_id, out, retry)
    return retry + list(by_id.values())


def _apply(by_id: dict[str, Job], out: Outcome, retry: list[Job]) -> None:
    """Hand every stored result of these jobs to its job; drop the jobs that are settled."""
    if not by_id:
        return
    rows = db.conn().execute(
        "SELECT DISTINCT ON (r.custom_id) r.custom_id, r.type, r.body, r.stop_reason, r.usage, r.error"
        " FROM llm_batch_result r JOIN llm_batch b ON b.id = r.batch_id"
        " WHERE r.custom_id = ANY(%s) ORDER BY r.custom_id, (r.type = 'succeeded') DESC, b.id DESC",
        (list(by_id),)).fetchall()
    for custom_id, kind, body, stop_reason, tally, error in rows:
        job = by_id.pop(custom_id)
        if kind != "succeeded":
            retry.append(job)
            continue
        try:
            job.done(parse(job.schema, body or "", stop_reason, tally or {}), tally or {})
        except Exception as exc:  # noqa: BLE001 -- a bad answer is a failure of its own, not the run's
            out.failed += 1
            out.errors.append(f"{type(exc).__name__}: {str(exc).splitlines()[0][:120]}")
            if job.failed:
                job.failed(exc)
            continue
        out.answered += 1
        out.batched += 1


def _collect(local: int, log: Callable[[str], None]) -> None:
    """Wait for one submitted batch to end, then store every result and charge for them."""
    api_id, model, pass_ = db.conn().execute(
        "SELECT api_id, model, pass FROM llm_batch WHERE id = %s", (local,)).fetchone()
    last = 0.0
    while True:
        batch = client().messages.batches.retrieve(api_id)
        if batch.processing_status == "ended":
            break
        if time.monotonic() - last > 300:
            c = batch.request_counts
            log(f"{pass_}: batch {api_id} processing ({c.succeeded + c.errored} done, {c.processing} to go)")
            last = time.monotonic()
        time.sleep(POLL_SECONDS)
    n = 0
    for result in client().messages.batches.results(api_id):
        kind = result.result.type
        body = stop_reason = tally = error = None
        if kind == "succeeded":
            message = result.result.message
            body, stop_reason = text_of(message.content), message.stop_reason
            tally = {**usage(message), "batch": 1}
            charge(model, tally)
        elif kind == "errored":
            error = str(result.result.error)[:500]
        db.conn().execute(
            "INSERT INTO llm_batch_result (batch_id, custom_id, type, body, stop_reason, usage, error)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
            (local, result.custom_id, kind, body, stop_reason, Jsonb(tally) if tally else None, error))
        n += 1
    db.conn().execute("UPDATE llm_batch SET status = 'collected', collected_at = now() WHERE id = %s", (local,))
    log(f"{pass_}: batch {api_id} collected, {n} results")


def _bind_lost(pass_: str, log: Callable[[str], None]) -> None:
    """Find the API's id for a batch recorded but never bound: the run died in between.

    Matched by size among the batches the API created after the record; a
    record with no such batch was never submitted and is dropped.
    """
    lost = db.conn().execute("SELECT id, custom_ids, created_at FROM llm_batch WHERE pass = %s AND status = 'sending'",
                             (pass_,)).fetchall()
    if not lost:
        return
    known = {r[0] for r in db.conn().execute("SELECT api_id FROM llm_batch WHERE api_id IS NOT NULL")}
    recent = [b for b in client().messages.batches.list(limit=100) if b.id not in known]
    for local, ids, created in lost:
        match = next((b for b in recent if b.created_at >= created
                      and _size(b) == len(ids)), None)
        if match is None:
            db.conn().execute("DELETE FROM llm_batch WHERE id = %s", (local,))
            log(f"{pass_}: a batch recorded at {created:%H:%M} was never submitted; dropped")
            continue
        recent.remove(match)
        db.conn().execute("UPDATE llm_batch SET api_id = %s, status = 'submitted' WHERE id = %s", (match.id, local))
        log(f"{pass_}: batch {match.id}, submitted by a run that stopped, found again")


def _size(batch: Any) -> int:
    c = batch.request_counts
    return c.processing + c.succeeded + c.errored + c.canceled + c.expired


# --- the content-keyed answer ledgers ------------------------------------------


class Ledger:
    """A table of answers keyed by model, prompt and message: pepcorp's and peptree's.

    A re-run pays only for a request whose material changed; the key is the
    whole of what was asked, so any change to the message, the prompt file or
    the model is a new question.
    """

    def __init__(self, table: str):
        self.table = table

    @staticmethod
    def key(model: str, prompt_hash: str, message: str) -> str:
        return hashlib.sha256(f"{model}\n{prompt_hash}\n{message}".encode()).hexdigest()

    def recorded(self, key: str) -> dict[str, Any] | None:
        row = db.conn().execute(f"SELECT answer FROM {self.table} WHERE key = %s", (key,)).fetchone()
        return None if row is None else row[0]

    def store(self, key: str, country: str, qid: str, model: str, prompt_hash: str,
              request: dict[str, Any], answer: dict[str, Any], tally: dict[str, int]) -> None:
        db.conn().execute(
            f"INSERT INTO {self.table} (key, country, qid, model, prompt_hash, request, answer, usage)"
            " VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (key) DO NOTHING",
            (key, country, qid, model, prompt_hash, Jsonb(request), Jsonb(answer), Jsonb(tally)))

    def cost(self, country: str) -> tuple[float, int]:
        """Total spend on a country's rows at list price, and the number of calls.

        A call on a model `PRICES` does not list adds no dollars: an unknown
        price is left out, not guessed.
        """
        rows = db.conn().execute(f"SELECT model, usage FROM {self.table} WHERE country = %s", (country,)).fetchall()
        return sum((cost(model, tally) or 0.0 for model, tally in rows), 0.0), len(rows)
