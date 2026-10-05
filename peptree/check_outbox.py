"""Pin the outbox's arithmetic, offline: keys, command counts, chunking and the ledger's transitions.

    .venv/bin/python -m peptree.check_outbox
"""

from peptree import outbox
from peptree.check_filter import expect

REF = 'Q1\tP17\tQ9\tS854\t"https://x.org/a"\tS813\t+2026-10-04T00:00:00Z/11 /* peptree repair xx 2026-10-04 */'


def main() -> None:
    again = REF.replace("2026-10-04T", "2026-10-05T").replace("2026-10-04 */", "2026-10-05 */")
    expect(outbox.key(REF) == outbox.key(again) == 'Q1\tP17\tQ9\tS854\t"https://x.org/a"',
           "a key drops the edit summary and the retrieval date, so a re-run is the same statement")
    expect(outbox.key("Q1\tP17\tQ9 /* a */") != outbox.key("Q1\tP17\tQ8 /* a */"), "a different value is another key")
    expect(outbox.commands(REF) == 2 and outbox.commands("Q1\tP279\tQ5 /* a */") == 1,
           "a referenced line is two QS commands, a bare one is one")
    expect(outbox.renamed(REF, 7).endswith(" /* peptree outbox chunk-007 */") and "repair xx" not in outbox.renamed(REF, 7),
           "a chunk's lines carry the chunk's name as their summary")
    bare = [f"Q{i}\tP279\tQ5 /* a */" for i in range(1, 451)]
    sizes = [sum(map(outbox.commands, c)) for c in outbox.chunked(bare)]
    expect(sizes == [300, 150], "450 one-command lines fill one chunk of 300 and one of 150")
    refd = [f'Q{i}\tP17\tQ9\tS854\t"u"\tS813\t+2026-10-04T00:00:00Z/11 /* a */' for i in range(1, 202)]
    sizes = [sum(map(outbox.commands, c)) for c in outbox.chunked(refd)]
    expect(max(sizes) <= 300 and sum(sizes) == 402, "commands, not lines, fill a chunk")
    two = ["Q1\tP1001\tQ8 /* a */", "Q1\tP1001\tQ9 /* b */", "Q1\tP279\tQ5 /* a */", "Q1\tP279\tQ6 /* b */"]
    expect([len(c) for c in outbox.chunked(two)] == [3, 1],
           "a second value for one (item, single-valued property) waits a chunk; two P279s may share one")
    moved = outbox.transitions({"a": "emitted", "b": "emitted", "c": "emitted", "d": "landed"}, {"a", "d"}, {"b", "d"})
    expect(moved == {"a": "landed", "c": "withdrawn"},
           "live lands a line, no longer proposed and not live withdraws it, a landed line stays")
    expect(outbox.retired([("a", 1, "withdrawn"), ("b", 1, "emitted"), ("c", 2, "withdrawn"), ("d", 2, "landed")]) == {1},
           "a chunk with a withdrawn line is retired only if nothing in it has landed (it was not pasted)")


if __name__ == "__main__":
    main()
