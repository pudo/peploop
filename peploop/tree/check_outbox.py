"""Pin the outbox's arithmetic, offline: keys, what one batch may carry, and the ledger's transitions.

    .venv/bin/python -m peploop.tree.check_outbox
"""

from peploop import ledger, send
from peploop.tree import outbox
from peploop.tree.check_filter import expect

REF = 'Q1\tP17\tQ9\tS854\t"https://x.org/a"\tS813\t+2026-10-04T00:00:00Z/11 /* peptree repair xx 2026-10-04 */'


def main() -> None:
    again = REF.replace("2026-10-04T", "2026-10-05T").replace("2026-10-04 */", "2026-10-05 */")
    expect(ledger.key(REF) == ledger.key(again) == 'Q1\tP17\tQ9\tS854\t"https://x.org/a"',
           "a key drops the edit summary and the retrieval date, so a re-run is the same statement")
    expect(ledger.key("Q1\tP17\tQ9 /* a */") != ledger.key("Q1\tP17\tQ8 /* a */"), "a different value is another key")
    two = ["Q1\tP1001\tQ8 /* a */", "Q1\tP1001\tQ9 /* b */", "Q1\tP279\tQ5 /* a */", "Q1\tP279\tQ6 /* b */"]
    now, later = outbox.separable(two)
    expect(len(now) == 3 and later == ["Q1\tP1001\tQ9 /* b */"],
           "a second value for one (item, single-valued property) waits a batch; two P279s may share one")
    moved = send.landed({"a": "sent", "b": "sent", "c": "failed", "d": "landed"}, {"a", "c", "d"})
    expect(moved == {"a": "landed"}, "live lands a sent line; a failed or landed line keeps its status")
    check_dispatch()


def check_dispatch() -> None:
    """`dispatch` holds the lock, runs `before`, the additions, `after`, then the removals -- and no `after` without additions."""
    calls: list[str] = []
    real = send.send, send.pending_removals, send.writer_lock

    class Lock:
        def __init__(self, who: str) -> None:
            calls.append(f"lock {who}")

        def __enter__(self) -> None:
            return None

        def __exit__(self, *exc: object) -> None:
            calls.append("unlock")

    send.writer_lock = Lock  # type: ignore[assignment]
    send.send = lambda tool, op, rows, *a, **k: calls.append(f"{op} {len(rows)}") or len(calls)  # type: ignore[assignment]
    send.pending_removals = lambda tool, log: [("xx", "g", "-STATEMENT\tg", [])]  # type: ignore[assignment]
    try:
        ids = send.dispatch("t", [("xx", "k", "Q1\tP17\tQ9", [])], print,
                            before=lambda: calls.append("before"), after=lambda: calls.append("after"))
        expect(calls == ["lock t send", "before", "add 1", "after", "remove 1", "unlock"] and len(ids) == 2,
               "additions go out between before and after, removals last, all under the lock")
        calls.clear()
        send.dispatch("t", [], print, after=lambda: calls.append("after"))
        expect(calls == ["lock t send", "remove 1", "unlock"], "no additions: no add batch and no after, removals still go")
    finally:
        send.send, send.pending_removals, send.writer_lock = real


if __name__ == "__main__":
    main()
