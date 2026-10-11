"""Send every reviewed country's latest proposals to Wikidata, once each, and take back what a reviewer strikes.

A country's run file says what it would add *now*; the joint ledger
(`peploop/ledger.py`) says what has gone out already and what a reviewer
struck. A fix that re-renders twenty countries therefore costs only its new
statements. The batch itself goes out through `peploop/send.py`.

    python -m peptree.cli send                     # reconcile; write what would go out to send/pending.qs
    python -m peptree.cli send --batch 7           # the same, for one reviewed sweep batch only
    python -m peptree.cli send --submit [--batch 7]  # additions as one QS3 batch, then approved removals as another
    python -m peptree.cli send --status            # batches, failures, strikes, open removals
    python -m peptree.cli send --propose-reverts   # queue removals for what landed on items the load now drops
    python -m peptree.cli strike <qid> <prop> [value] --reason "…" [--country cc]
    python -m peptree.cli removals [approve|reject <guid…>]

- An addition is `sent`, then `landed` once its statement is live (any rank), or
  `failed` when QS3 reports its command failed. A failed line is listed by
  `--status` and not sent again on its own.
- Every line is additive and plain (no `+`), so QS3 merges a line into a
  statement that already holds its value: a line that went out twice changes
  nothing. The ledger is still what keeps a statement from being sent twice.
- A struck line is never sent. Striking one that already landed queues its
  removal; removing a statement is the human gate, so a removal waits for
  `removals approve` unless it undoes our own edit.
- A landed statement on an item the load now drops (a fix found it is no office)
  is a revert candidate. `--propose-reverts` queues it as a proposed removal.
  "No longer proposed" is no signal here: a landed statement closes its own gap,
  so no run re-decides it.
- Only a place the sweep ledger marks reviewed (or submitted) goes out: a batch
  is audited before any of it is sent.
"""

import argparse
import datetime as dt
import os
import sys
from collections import defaultdict
from typing import Callable

from peploop import ledger, send
from peptree import qs, sweep, wd

TOOL = "peptree"
DIR = qs.OUT_DIR / "send"
PENDING = DIR / "pending.qs"
#: Ledger statuses whose proposals may go out.
CLEARED = ("reviewed", "submitted")


def separable(lines: list[str]) -> tuple[list[str], list[str]]:
    """Split lines into what one batch may carry and what waits for the next.

    A second value for one single-valued (item, property) waits, so every batch
    passes `qs.validate`. Two countries may both propose a value for one item,
    as with a board shared by two islands.
    """
    now, later, seen = [], [], set()
    for line in lines:
        item, prop, _ = qs.statements([line])[0]
        if prop != "P279" and (item, prop) in seen:
            later.append(line)
            continue
        now.append(line)
        seen.add((item, prop))
    return now, later


def live_keys(lines: list[str]) -> set[str]:
    """Keys of the lines whose statement Wikidata holds now, at any rank (read live)."""
    stmts = qs.statements(lines)
    ents = wd.fetch_items(sorted({q for q, _, _ in stmts}), props="claims")
    out = set()
    for line, (q, prop, value) in zip(lines, stmts):
        for claim in (ents.get(q) or {}).get("claims", {}).get(prop, []):
            if ledger.value_id(claim.get("mainsnak", {})) == value:
                out.add(ledger.key(line))
    return out


def proposals() -> dict[str, tuple[str, str]]:
    """key → (country, line) over every place's latest run file; the first country to propose wins."""
    out: dict[str, tuple[str, str]] = {}
    for cc in sorted(sweep.read()):
        path = qs.latest(cc)
        for line in path.read_text().splitlines() if path else []:
            if line.strip():
                out.setdefault(ledger.key(line), (cc, line))
    return out


def pending(log: Callable[[str], None], batch: int | None = None) -> list[tuple[str, str]]:
    """(country, line) of every cleared proposal not yet sent, not struck and not live, one batch's worth."""
    props = proposals()
    taken = {k for k, *_ in ledger.edits("add")}
    cleared = {cc for cc, r in sweep.read().items() if r["status"] in CLEARED}
    held = {v[0] for k, v in props.items() if k not in taken and v[0] not in cleared}
    if batch is not None:
        cleared &= set(sweep.members(batch))
    if held:
        log(f"held back, not yet reviewed: {', '.join(sorted(held))}")
    todo = {k: v for k, v in props.items() if k not in taken and v[0] in cleared}
    vetoes = ledger.strikes()
    struck = {k for k, (_, line) in todo.items() if ledger.struck(line, vetoes)}
    todo = {k: v for k, v in todo.items() if k not in struck}
    live_now = live_keys([line for _, line in todo.values()])
    todo = {k: v for k, v in todo.items() if k not in live_now}
    # Sorted by country, then line: a country's lines on one item sit together,
    # which is what lets QS3 combine them into one edit.
    order = sorted(todo.values())
    now, later = separable([line for _, line in order])
    by_line = {line: cc for cc, line in order}
    log(f"proposed {len(props)}, already out {len(taken & set(props))}, struck {len(struck)}, "
        f"live {len(live_now)}, pending {len(now)}" + (f", {len(later)} wait for a second batch" if later else ""))
    return [(by_line[line], line) for line in now]


def run(log: Callable[[str], None] = print, batch: int | None = None, submit: bool = False) -> list[int]:
    """Reconcile, write the pending lines to `pending.qs`; with `submit`, send them and the approved removals.

    Returns the QS3 batch ids sent.
    """
    user = os.environ.get("QS_USERNAME", "")
    send.recover(TOOL, user, log)
    send.reconcile(TOOL, live_keys, log)
    todo = pending(log, batch)
    lines = [line for _, line in todo]
    errors = qs.validate(lines)
    if errors:
        sys.exit("refused: " + "; ".join(errors[:5]))
    DIR.mkdir(parents=True, exist_ok=True)
    PENDING.write_text("\n".join(lines) + "\n" if lines else "")
    log(f"{PENDING}: {len(lines)} lines, from {', '.join(sorted({cc for cc, _ in todo})) or 'nowhere'}")
    if not submit:
        n = len([r for r in ledger.removals("approved", TOOL) if r["sent"] is None])
        log(f"{n} approved removals would go out after them")
        return []
    sent = []
    day = dt.date.today().isoformat()
    with send.writer_lock("peptree send"):
        if lines:
            name = f"peptree send {day}" + (f" batch {batch}" if batch is not None else "")
            sent.append(send.send(TOOL, "add", name, [(cc, ledger.key(line), line, []) for cc, line in todo],
                                  live_keys, log))
        removals = send.pending_removals(TOOL, log)
        if removals:
            sent.append(send.send(TOOL, "remove", f"peptree removals {day}", removals, live_keys, log))
    return sent


def propose_reverts(log: Callable[[str], None] = print) -> int:
    """Queue a proposed removal for each landed addition on an item the load now drops."""
    dropped = set(wd.conn().execute("SELECT country, qid FROM ptree_item WHERE dropped IS NOT NULL").fetchall())
    gone = [(cc, line) for _, cc, line, _, s in ledger.edits("add", TOOL)
            if s == "landed" and (cc, qs.statements([line])[0][0]) in dropped]
    by_qid: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for cc, line in gone:
        by_qid[qs.statements([line])[0][0]].append((cc, line))
    ents = wd.fetch_items(sorted(by_qid), props="claims")
    n = 0
    for qid, rows in by_qid.items():
        claims = (ents.get(qid) or {}).get("claims", {})
        for cc, line in rows:
            _, prop, value = qs.statements([line])[0]
            for guid, ours in ledger.candidates(claims.get(prop, []), value, ledger.ours_urls(line)):
                ledger.propose_removal(TOOL, guid, qid, prop, value, cc, "landed on an item the load now drops",
                                       "revert", ours)
                n += 1
    log(f"{n} revert removals proposed")
    return n


def country_of(qid: str) -> str | None:
    """The country whose run proposed something for this item, from the ledger."""
    row = wd.conn().execute("SELECT country FROM wd_edit WHERE op = 'add' AND key LIKE %s LIMIT 1",
                            (qid + "\t%",)).fetchone()
    return row[0] if row else None


def strike_main(args: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="peptree strike")
    parser.add_argument("qid")
    parser.add_argument("prop")
    parser.add_argument("value", nargs="?", default=ledger.ANY)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--country")
    a = parser.parse_args(args)
    cc = a.country or country_of(a.qid)
    if cc is None:
        sys.exit(f"no country has proposed anything for {a.qid}; pass --country")
    queued = ledger.strike(TOOL, a.qid, a.prop, a.value, cc, a.reason, log=lambda m: print(m, file=sys.stderr))
    print(f"struck {a.qid} {a.prop} {a.value} ({cc})" + (f"; {len(queued)} removals queued" if queued else ""))


def removals_main(args: list[str]) -> None:
    send.removals_main(TOOL, args)


def main(args: list[str]) -> None:
    log = lambda m: print(m, file=sys.stderr, flush=True)  # noqa: E731
    if args == ["--status"]:
        print(send.status(TOOL))
        return
    if args == ["--propose-reverts"]:
        propose_reverts(log)
        return
    submit = "--submit" in args
    rest = [a for a in args if a != "--submit"]
    if rest and not (len(rest) == 2 and rest[0] == "--batch" and rest[1].isdigit()):
        sys.exit("usage: send [--status | --propose-reverts | [--submit] [--batch <n>]]")
    sent = run(log, int(rest[1]) if rest else None, submit=submit)
    print(f"QS3 batches {' '.join(map(str, sent))}" if sent else f"nothing sent; review {PENDING}")
