"""Pin the shared model layer: prices, the run's budget, live and batched runs, and a batch found again after a crash.

A fake client stands in for the API and the batch tables are shadowed by
temporary ones, so nothing is sent and nothing stored.

    .venv/bin/python -m peploop.check_llm
"""

import hashlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import psycopg
from pydantic import BaseModel

from peploop import costs, db, llm
from peploop.checks import expect

NOW = datetime(2026, 10, 22, 12, tzinfo=timezone.utc)
USAGE = SimpleNamespace(input_tokens=1000, output_tokens=100, cache_read_input_tokens=0,
                        cache_creation_input_tokens=0)


class Answer(BaseModel):
    n: int


def message(body: str) -> SimpleNamespace:
    return SimpleNamespace(content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=body)],
                           stop_reason="end_turn", usage=USAGE)


class Batches:
    """The batch half of the fake client: answers each request with its own number, one errored."""

    def __init__(self, errored: set[str] = frozenset(), crash: bool = False):
        self.created: list[list[dict[str, Any]]] = []
        self.errored = errored
        self.crash = crash
        self.listed: list[Any] = []

    def create(self, requests: list[dict[str, Any]]) -> Any:
        self.created.append(requests)
        return SimpleNamespace(id=f"msgbatch_{len(self.created)}")

    def retrieve(self, api_id: str) -> Any:
        if self.crash:
            self.crash = False
            raise RuntimeError("the run died while waiting")
        return SimpleNamespace(processing_status="ended")

    def results(self, api_id: str) -> Any:
        for req in self.created[int(api_id.split("_")[1]) - 1]:
            n = int(req["params"]["messages"][0]["content"])
            if req["custom_id"] in self.errored:
                yield SimpleNamespace(custom_id=req["custom_id"], result=SimpleNamespace(type="errored", error="overloaded"))
            else:
                yield SimpleNamespace(custom_id=req["custom_id"], result=SimpleNamespace(
                    type="succeeded", message=message(f'{{"n": {n}}}')))

    def list(self, limit: int = 100) -> list[Any]:
        return self.listed


class Client:
    def __init__(self, batches: Batches):
        self.live: list[dict[str, Any]] = []
        self.messages = SimpleNamespace(create=self.create, batches=batches)

    def create(self, **request: Any) -> Any:
        self.live.append(request)
        return message(f'{{"n": {int(request["messages"][0]["content"])}}}')


def jobs(numbers: range, got: dict[int, int]) -> list[llm.Job]:
    def done(n: int) -> Any:
        return lambda answer, usage: got.__setitem__(n, answer.n)

    return [llm.Job({"model": "claude-sonnet-5-5", "max_tokens": 100, "output_config": {"effort": "low"},
                     "messages": [{"role": "user", "content": str(n)}]}, Answer, done(n)) for n in numbers]


def check_prices() -> None:
    tally = {"input_tokens": 1_000_000, "output_tokens": 100_000}
    expect(llm.cost("claude-sonnet-5-5", tally) == 3.0, "a live call at list price")
    expect(llm.cost("claude-sonnet-5-5", {**tally, "batch": 1}) == 1.5, "a batched call at half")
    expect(llm.cost("claude-unknown", tally) is None, "an unpriced model is not priced by a guess")
    old = hashlib.sha256("claude-sonnet-5-5\nabc\nhello".encode()).hexdigest()
    expect(llm.Ledger.key("claude-sonnet-5-5", "abc", "hello") == old,
           "the ledger key is the one every stored pepcorp and peptree answer carries")


def check_live(client: Client) -> None:
    llm.set_budget(None)
    got: dict[int, int] = {}
    out = llm.run("check", jobs(range(5), got), log=lambda _: None, workers=1, batch=False)
    expect(got == {n: n for n in range(5)} and out.answered == 5, "a live run hands each answer to its job")
    request = client.live[0]
    expect(request["output_config"]["format"]["type"] == "json_schema" and request["output_config"]["effort"] == "low",
           "the answer's schema goes out as the output format, beside the job's own config")
    llm.set_budget(llm.spent() + 0.0035)
    got.clear()
    out = llm.run("check", jobs(range(10), got), log=lambda _: None, workers=1, batch=False)
    expect(out.answered == 2 and out.unasked == 8, f"past the budget nothing more is asked: {out}")
    llm.set_budget(None)


def check_batches(conn: psycopg.Connection) -> None:
    batches = Batches()
    client = Client(batches)
    llm._client = client
    got: dict[int, int] = {}
    work = jobs(range(60), got)
    batches.errored = {work[3].id}
    out = llm.run("check", work, log=lambda _: None, batch=True)
    expect(len(batches.created) == 1 and len(batches.created[0]) == 60, "sixty jobs go out as one batch")
    expect(got == {n: n for n in range(60)} and out.batched == 59,
           f"every answer reaches its job, the errored one asked again live: {out}")
    expect(len(client.live) == 1, "only the errored request is sent live")
    row = conn.execute("SELECT status, api_id FROM llm_batch").fetchone()
    expect(tuple(row) == ("collected", "msgbatch_1"), f"the batch is recorded and collected: {row}")
    usage = conn.execute("SELECT usage FROM llm_batch_result LIMIT 1").fetchone()[0]
    expect(usage.get("batch") == 1, "a batch result's usage is marked, so it is priced at the discount")

    got2: dict[int, int] = {}
    llm.run("check", jobs(range(60), got2), log=lambda _: None, batch=True)
    expect(len(batches.created) == 1 and len(got2) == 60,
           f"the same jobs again are served from the stored results, nothing submitted: {len(got2)}")

    batches.crash = True
    got3: dict[int, int] = {}
    try:
        llm.run("check", jobs(range(100, 160), got3), log=lambda _: None, batch=True)
    except RuntimeError:
        pass
    expect(len(batches.created) == 2 and not got3, "a run that dies after submitting has stored nothing")
    llm.run("check", jobs(range(100, 160), got3), log=lambda _: None, batch=True)
    expect(len(batches.created) == 2 and len(got3) == 60,
           "the next run collects the submitted batch instead of paying again")

    lost = jobs(range(200, 260), {})
    conn.execute("INSERT INTO llm_batch (pass, model, custom_ids, status, created_at) VALUES"
                 " ('check', 'claude-sonnet-5-5', %s, 'sending', %s)", ([j.id for j in lost], NOW))
    batches.created.append([{"custom_id": j.id, "params": j.request()} for j in lost])
    batches.listed = [SimpleNamespace(id="msgbatch_3", created_at=NOW + timedelta(seconds=2), request_counts=SimpleNamespace(
        processing=0, succeeded=60, errored=0, canceled=0, expired=0))]
    got4: dict[int, int] = {}
    llm.run("check", jobs(range(200, 260), got4), log=lambda _: None, batch=True)
    expect(len(batches.created) == 3 and len(got4) == 60,
           "a batch recorded but never bound is found by its size and collected, not sent again")


def main() -> None:
    check_prices()
    real = llm._client, costs.estimate
    costs.estimate = lambda *_a, **_k: 0.01  # type: ignore[assignment]
    try:
        client = Client(Batches())
        llm._client = client
        check_live(client)
        try:
            conn = db.conn()
            db.init_schema()
        except psycopg.OperationalError as exc:
            print(f"  skip batches: no database ({exc.__class__.__name__})")
            return
        for table in ("llm_batch", "llm_batch_result"):
            conn.execute(f"CREATE TEMP TABLE {table} (LIKE public.{table} INCLUDING DEFAULTS INCLUDING INDEXES)")
        conn.execute("CREATE TEMP SEQUENCE llm_batch_seq")
        conn.execute("ALTER TABLE pg_temp.llm_batch ALTER COLUMN id SET DEFAULT nextval('pg_temp.llm_batch_seq')")
        check_batches(conn)
    finally:
        llm._client, costs.estimate = real
        llm.set_budget(None)


if __name__ == "__main__":
    main()
