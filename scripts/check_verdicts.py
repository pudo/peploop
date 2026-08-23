#!/usr/bin/env python
"""Assert the verdict helper's ledger arithmetic against a stand-in client.

    python scripts/check_verdicts.py

Reach for this before and after touching `wd.verdicts`. The API call in the
middle is the least interesting part of that module — what matters is that a
re-run costs nothing and a widened candidate set costs only its new items,
because those two properties are the whole reason the pass is resumable. Both
are cheap to get subtly wrong and expensive to discover live, at Opus prices.

Offline by construction: the client is a stand-in that echoes the batch back as
verdicts, so this never spends a token and needs no key. A pin that costs money
to run is a pin nobody runs.
"""

import json
import re
import sys
import tempfile
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wd.verdicts import Ledger, classify  # noqa: E402

SCHEMA = {
    "type": "object",
    "properties": {"qid": {"type": "string"}, "verdict": {"type": "string"}},
    "required": ["qid", "verdict"],
    "additionalProperties": False,
}


class _Usage:
    input_tokens = 100
    output_tokens = 200
    cache_read_input_tokens = 1500
    cache_creation_input_tokens = 0


class _Message:
    stop_reason = "end_turn"
    usage = _Usage()

    def __init__(self, text: str) -> None:
        # A thinking block precedes the answer on every current model; the
        # helper must skip it rather than read `content[0]`.
        self.content = [
            types.SimpleNamespace(type="thinking"),
            types.SimpleNamespace(type="text", text=text),
        ]


class _Stream:
    def __init__(self, kwargs):
        self.kwargs = kwargs

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        content = self.kwargs["messages"][0]["content"]
        try:
            qids = [i["qid"] for i in json.loads(content)]
        except json.JSONDecodeError:
            # A custom renderer's user turn is prose, not JSON. Recover the
            # subjects the way a model would: they are named in the text.
            qids = re.findall(r"\bQ\d+\b", content)
        return _Message(json.dumps(
            {"verdicts": [{"qid": q, "verdict": "skip"} for q in qids]}))


class _Canned:
    """A stream that returns exactly the text it was given."""

    def __init__(self, text: str) -> None:
        self.text = text

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return _Message(self.text)


class FakeClient:
    """Echoes each batch back as verdicts, and records what it was asked."""

    def __init__(self) -> None:
        self.requests = []
        outer = self

        class _Messages:
            def stream(self, **kwargs):
                outer.requests.append(kwargs)
                return _Stream(kwargs)

        self.messages = _Messages()


def main() -> None:
    bad = 0
    items = [{"qid": f"Q{i}", "label": f"office {i}"} for i in range(25)]
    out = Path(tempfile.mkdtemp()) / "verdicts.jsonl"

    def run(pool, client):
        return classify(pool, prompt="PROMPT", item_schema=SCHEMA,
                        ledger=Ledger(out).load(), batch_size=10, workers=3,
                        client=client, log=lambda m: None)

    first = FakeClient()
    usage = run(items, first)
    rows = out.read_text().splitlines()
    if len(rows) != 25 or usage.requests != 3:
        bad += 1
        print(f"FAIL first run: want 25 verdicts in 3 batches, "
              f"got {len(rows)} in {usage.requests}")

    # The property the whole ledger exists for: a re-run judges nothing.
    if run(items, FakeClient()).requests != 0:
        bad += 1
        print("FAIL resume: a re-run must not send a request")

    # ...and widening the candidate set pays only for what is new.
    widened = run(items + [{"qid": "Q99", "label": "new"}], FakeClient())
    if widened.requests != 1 or len(out.read_text().splitlines()) != 26:
        bad += 1
        print(f"FAIL widen: want 1 request and 26 rows, got "
              f"{widened.requests} and {len(out.read_text().splitlines())}")

    request = first.requests[0]
    # The instructions are byte-identical across every request in a pass, so
    # they are the breakpoint; dropping it re-bills the prompt ~190 times.
    if (request["system"][0].get("cache_control") or {}).get("type") != "ephemeral":
        bad += 1
        print("FAIL: the system prompt must carry a cache breakpoint")

    fmt = request["output_config"].get("format") or {}
    if fmt.get("type") != "json_schema":
        bad += 1
        print("FAIL: verdicts must be schema-enforced, not parsed out of prose")
    root = fmt.get("schema", {})
    if (list(root.get("properties", {})) != ["verdicts"]
            or root.get("additionalProperties") is not False):
        bad += 1
        print("FAIL: structured outputs need an object root with "
              "additionalProperties false")

    # Provenance: a ledger holding rows from two prompt revisions must be
    # distinguishable from a clean one without an out-of-band copy of the file.
    row = json.loads(out.read_text().splitlines()[0])
    stamp = row.get("_pass") or {}
    if not stamp.get("model") or not stamp.get("prompt_sha"):
        bad += 1
        print(f"FAIL provenance: every row needs a _pass stamp, got {stamp}")
    other = FakeClient()
    fresh_sha = Path(tempfile.mkdtemp()) / "v.jsonl"
    classify(items[:1], prompt="A DIFFERENT PROMPT", item_schema=SCHEMA,
             ledger=Ledger(fresh_sha).load(), client=other, log=lambda m: None)
    if (json.loads(fresh_sha.read_text().splitlines()[0])["_pass"]["prompt_sha"]
            == stamp["prompt_sha"]):
        bad += 1
        print("FAIL provenance: a different prompt must hash differently")

    # Reference material stable within a run but not across runs is cached
    # separately from the instructions, so switching corpus does not re-bill the
    # prompt every run shares.
    two = FakeClient()
    classify(items[:1], prompt="P", item_schema=SCHEMA, extra_system=["GAZETTEER"],
             ledger=Ledger(Path(tempfile.mkdtemp()) / "v.jsonl").load(),
             client=two, log=lambda m: None)
    blocks = two.requests[0]["system"]
    marked = [i for i, b in enumerate(blocks) if b.get("cache_control")]
    if len(blocks) != 2 or marked != [0, 1]:
        bad += 1
        print(f"FAIL extra_system: want 2 blocks both marked, got "
              f"{len(blocks)} blocks marked at {marked}")

    # A per-item renderer replaces the JSON user turn, for items whose evidence
    # is long-form text. JSON-escaping an article wastes tokens, and one large
    # item inflates the context of every other item in its batch.
    three = FakeClient()
    classify(items[:3], prompt="P", item_schema=SCHEMA, batch_size=1,
             render=lambda batch: f"# dossier for {batch[0]['qid']}\n\nprose",
             ledger=Ledger(Path(tempfile.mkdtemp()) / "v.jsonl").load(),
             client=three, log=lambda m: None)
    turns = [r["messages"][0]["content"] for r in three.requests]
    if len(turns) != 3 or not all(t.startswith("# dossier for Q") for t in turns):
        bad += 1
        print(f"FAIL render: want 3 rendered single-item turns, got {turns[:2]}")

    # The schema constrains every field's shape and no field's value, so it
    # cannot see a dropped or transposed subject. A batch whose verdicts do not
    # answer the items asked must fail and be re-sent, not be written.
    class Dropping(FakeClient):
        def __init__(self):
            super().__init__()
            outer = self

            class _Messages:
                def stream(self, **kwargs):
                    outer.requests.append(kwargs)
                    batch = json.loads(kwargs["messages"][0]["content"])
                    return _Canned(json.dumps({"verdicts": [
                        {"qid": i["qid"], "verdict": "skip"} for i in batch[:-1]]}))

            self.messages = _Messages()

    dropped_out = Path(tempfile.mkdtemp()) / "v.jsonl"
    dropped = classify(items, prompt="P", item_schema=SCHEMA,
                       ledger=Ledger(dropped_out).load(), batch_size=10, workers=3,
                       client=Dropping(), log=lambda m: None)
    if dropped.failures != 3 or dropped_out.exists():
        bad += 1
        print(f"FAIL count check: a batch missing a verdict must fail, got "
              f"{dropped.failures} failures, exists={dropped_out.exists()}")

    # A failing batch must cost its own items, not the run.
    class Broken(FakeClient):
        def __init__(self):
            super().__init__()
            outer = self

            class _Messages:
                def stream(self, **kwargs):
                    outer.requests.append(kwargs)
                    raise RuntimeError("boom")

            self.messages = _Messages()

    fresh = Path(tempfile.mkdtemp()) / "verdicts.jsonl"
    failed = classify(items, prompt="P", item_schema=SCHEMA,
                      ledger=Ledger(fresh).load(), batch_size=10, workers=3,
                      client=Broken(), log=lambda m: None)
    if failed.failures != 3 or fresh.exists():
        bad += 1
        print(f"FAIL error path: want 3 recorded failures and no ledger, "
              f"got {failed.failures} and exists={fresh.exists()}")

    if bad:
        raise SystemExit(f"\n{bad} check(s) failed")
    print("10 verdict-helper checks pass (batching, resume, widen, cache, "
          "schema, provenance, extra_system, render, count check, "
          "failure isolation)")


if __name__ == "__main__":
    main()
