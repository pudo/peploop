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


if __name__ == "__main__":
    main()
