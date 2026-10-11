"""Send every reviewed country's latest proposals to Wikidata, once each, and take back what a reviewer strikes.

A country's run file says what it would add *now*; the joint ledger
(`peploop/ledger.py`) says what has gone out already and what a reviewer
struck. A fix that re-renders twenty countries therefore costs only its new
statements. The batch itself goes out through `peploop/send.py`.

    python -m peploop.cli tree send                       # reconcile; write what would go out to send/pending.qs
    python -m peploop.cli tree send --batch 7             # the same, for one reviewed sweep batch only
    python -m peploop.cli tree send --submit [--batch 7]  # additions as one QS3 batch, then approved removals as another
    python -m peploop.cli tree send --status              # batches, failures, strikes, open removals
    python -m peploop.cli tree send --propose-reverts     # queue removals for what landed on items the load now drops
    python -m peploop.cli tree strike <qid> <prop> [value] --reason "…" [--country cc]
    python -m peploop.cli removals [approve|reject <guid…>]  # both tools' removals

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

import datetime as dt
import sys
from collections import defaultdict
from typing import Callable

from peploop import ledger, send
from peploop.tree import qs, sweep, wd

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
    live_now = send.live_keys([line for _, line in todo.values()])
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
    send.prepare(TOOL, log)
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
    name = f"peptree send {dt.date.today().isoformat()}" + (f" batch {batch}" if batch is not None else "")
    return send.dispatch(TOOL, name, [(cc, ledger.key(line), line, []) for cc, line in todo], log)


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


def strike(qid: str, prop: str, value: str, reason: str, country: str | None, log: Callable[[str], None]) -> str:
    """Never send this statement; queue its removal if it already landed. Returns what was struck."""
    cc = country or country_of(qid)
    if cc is None:
        raise ValueError(f"no country has proposed anything for {qid}; pass --country")
    queued = ledger.strike(TOOL, qid, prop, value, cc, reason, log=log)
    return f"struck {qid} {prop} {value} ({cc})" + (f"; {len(queued)} removals queued" if queued else "")
