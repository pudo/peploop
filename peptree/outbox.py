"""Send every reviewed country's latest proposals to Wikidata as one QS3 batch, once each.

This is peptree's one write path for additions. A country's run file says what
it would add *now*; the ledger (`ledger.py`) says what has gone out already and
what a reviewer struck. A fix that re-renders twenty countries therefore costs
only its new statements.

    python -m peptree.cli outbox                     # reconcile; write what would go out to outbox/pending.qs
    python -m peptree.cli outbox --batch 7           # the same, for one reviewed sweep batch only
    python -m peptree.cli outbox --submit [--batch 7]  # send it as one QuickStatements 3.0 batch, wait, reconcile
    python -m peptree.cli outbox --status            # batches, failures, strikes, open removals
    python -m peptree.cli outbox --propose-reverts   # queue removals for what landed on items the load now drops

- An addition is `sent`, then `landed` once its statement is live (any rank), or
  `failed` when QS3 reports its command failed. A failed line is listed by
  `--status` and not sent again on its own.
- Every line is additive and plain (no `+`), so QS3 merges a line into a
  statement that already holds its value: a line that went out twice changes
  nothing. The ledger is still what keeps a statement from being sent twice.
- A struck line is never sent. Striking one that already landed queues its
  removal (`peptree.cli strike`), which goes out through `removals`, never here.
- A landed statement on an item the load now drops (a fix found it is no office)
  is a revert candidate. `--propose-reverts` queues it as a proposed removal;
  approving it is the human gate. "No longer proposed" is no signal here: a
  landed statement closes its own gap, so no run re-decides it.
- Only a place the sweep ledger marks reviewed (or submitted) goes out: a batch
  is audited before any of it is sent.
"""

import datetime as dt
import os
import re
import sys
from collections import Counter, defaultdict
from typing import Callable

from peploop import qs3
from peptree import ledger, qs, sweep, wd

DIR = qs.OUT_DIR / "outbox"
PENDING = DIR / "pending.qs"
#: Ledger statuses whose proposals may go out.
CLEARED = ("reviewed", "submitted")
RETRIEVED = re.compile(r"\tS813\t\+\S+")
#: QS3 batch status code → our batch status.
FINISHED = {qs3.DONE: "done", qs3.BLOCKED: "stopped", qs3.STOPPED: "stopped"}


def key(line: str) -> str:
    """The statement a line adds, without the parts that vary run to run (summary, retrieval date)."""
    return RETRIEVED.sub("", qs.SUMMARY_RE.sub("", line)).strip()


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


def landed(sent: dict[str, str], live: set[str]) -> dict[str, str]:
    """New status per sent key: live → landed."""
    return {k: "landed" for k, status in sent.items() if status == "sent" and k in live}


# --- live state ----------------------------------------------------------------------

def live_keys(lines: list[str]) -> set[str]:
    """Keys of the lines whose statement Wikidata holds now, at any rank (read live)."""
    stmts = qs.statements(lines)
    ents = wd.fetch_items(sorted({q for q, _, _ in stmts}), props="claims")
    out = set()
    for line, (q, prop, value) in zip(lines, stmts):
        for claim in (ents.get(q) or {}).get("claims", {}).get(prop, []):
            v = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
            if isinstance(v, dict) and v.get("id") == value:
                out.add(key(line))
    return out


def live_guids(guids: list[str]) -> set[str]:
    """Which of these statement GUIDs Wikidata still holds (read live)."""
    ents = wd.fetch_items(sorted({g.split("$")[0].upper() for g in guids}), props="claims")
    held = {c["id"] for e in ents.values() for cs in e.get("claims", {}).values() for c in cs}
    return {g for g in guids if g in held}


def proposals() -> dict[str, tuple[str, str]]:
    """key → (country, line) over every place's latest run file; the first country to propose wins."""
    out: dict[str, tuple[str, str]] = {}
    for cc in sorted(sweep.read()):
        path = qs.latest(cc)
        for line in path.read_text().splitlines() if path else []:
            if line.strip():
                out.setdefault(key(line), (cc, line))
    return out


# --- the run ----------------------------------------------------------------------

def reconcile(log: Callable[[str], None]) -> None:
    """Mark every sent addition that is now live, and every sent removal now gone, as landed."""
    adds = ledger.edits("add")
    moved = landed({k: s for k, _, _, _, s in adds}, live_keys([line for _, _, line, _, s in adds if s == "sent"]))
    ledger.set_status("add", moved, "landed")
    removes = [k for k, _, _, _, s in ledger.edits("remove") if s == "sent"]
    gone = set(removes) - live_guids(removes) if removes else set()
    ledger.set_status("remove", gone, "landed")
    log(f"reconciled: {len(moved)} additions landed, {len(gone)} removals landed")


def recover(log: Callable[[str], None]) -> None:
    """Bind a batch whose submit answer was lost to its QS3 id, found by its unique name."""
    stuck = wd.conn().execute("SELECT id, name FROM ptree_batch WHERE kind = 'qs3' AND qs3_id IS NULL "
                              "AND status = 'sending'").fetchall()
    user = os.environ.get("QS_USERNAME", "")
    for batch_id, name in stuck:
        found = qs3.find(name, user) if user else None
        if found is None:
            ledger.close_batch(batch_id, "unknown")
            log(f"batch #{batch_id} {name!r}: no QS3 batch found; marked unknown, its lines stay sent")
        else:
            ledger.bind_qs3(batch_id, found)
            log(f"batch #{batch_id} recovered as QS3 {found}")


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


def send(op: str, name: str, rows: list[tuple[str, str, str]], log: Callable[[str], None]) -> int:
    """Send (country, key, line) rows as one QS3 batch and wait for it; returns the QS3 id.

    The batch and its edits are recorded before the request: if the answer is
    lost, `recover` binds the batch by its name, which carries the local id.
    """
    batch_id = ledger.open_batch(op, name)
    name = f"{name} #{batch_id}"
    wd.conn().execute("UPDATE ptree_batch SET name = %s WHERE id = %s", (name, batch_id))
    ledger.record_edits(batch_id, op, rows)
    qs_id = qs3.submit([line for _, _, line in rows], name)
    ledger.bind_qs3(batch_id, qs_id)
    log(f"sent as QS3 batch {qs_id}: {qs3.link(qs_id)}  {qs3.EDITGROUPS.format(qs_id)}")
    row = qs3.wait(qs_id, log)
    ledger.close_batch(batch_id, FINISHED.get(row["status"]["code"], "unknown"))
    failed = {raw.strip() for raw in qs3.failed(qs_id)}
    bad = {k for k, _, line in rows if line.strip() in failed}
    ledger.set_status(op, bad, "failed")
    if bad:
        log(f"{len(bad)} lines failed; see --status")
    reconcile(log)
    return qs_id


def run(log: Callable[[str], None] = print, batch: int | None = None, submit: bool = False) -> int | None:
    """Reconcile, then write the pending lines to `pending.qs`, or send them and wait.

    Returns the QS3 batch id when something was sent.
    """
    recover(log)
    reconcile(log)
    todo = pending(log, batch)
    lines = [line for _, line in todo]
    errors = qs.validate(lines)
    if errors:
        sys.exit("refused: " + "; ".join(errors[:5]))
    DIR.mkdir(parents=True, exist_ok=True)
    PENDING.write_text("\n".join(lines) + "\n" if lines else "")
    log(f"{PENDING}: {len(lines)} lines, from {', '.join(sorted({cc for cc, _ in todo})) or 'nowhere'}")
    if not submit or not lines:
        return None
    name = f"peptree outbox {dt.date.today().isoformat()}" + (f" batch {batch}" if batch is not None else "")
    return send("add", name, [(cc, key(line), line) for cc, line in todo], log)


def propose_reverts(log: Callable[[str], None] = print) -> int:
    """Queue a proposed removal for each landed addition on an item the load now drops."""
    dropped = set(wd.conn().execute("SELECT country, qid FROM ptree_item WHERE dropped IS NOT NULL").fetchall())
    gone = [(cc, line) for _, cc, line, _, s in ledger.edits("add")
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
                ledger.propose_removal(guid, qid, prop, value, cc, "landed on an item the load now drops",
                                       "revert", ours)
                n += 1
    log(f"{n} revert removals proposed")
    return n


def status() -> str:
    con = wd.conn()
    rows = con.execute(
        "SELECT b.id, b.kind, b.op, coalesce(b.qs3_id, b.paste_chunk), b.status, e.status, count(e.key)"
        " FROM ptree_batch b LEFT JOIN ptree_edit e ON e.batch_id = b.id"
        " GROUP BY 1, 2, 3, 4, 5, 6 ORDER BY 1").fetchall()
    by: dict[tuple, Counter] = defaultdict(Counter)
    for bid, kind, op, ext, bstatus, estatus, n in rows:
        by[(bid, kind, op, ext, bstatus)][estatus] += n
    out = ["| # | kind | op | QS id | batch | sent | landed | failed | reverted |", "|---|---|---|---|---|---|---|---|---|"]
    for (bid, kind, op, ext, bstatus), c in by.items():
        out.append(f"| {bid} | {kind} | {op} | {ext or ''} | {bstatus} | {c['sent']} | {c['landed']} | "
                   f"{c['failed']} | {c['reverted']} |")
    stuck = con.execute("SELECT op, status, line FROM ptree_edit WHERE status IN ('sent', 'failed') "
                        "ORDER BY op, status, line").fetchall()
    out += ["", f"## Sent but not landed ({len(stuck)})", ""] + [f"- {o} {s}: {line}" for o, s, line in stuck]
    vetoes = ledger.strikes()
    out += ["", f"## Strikes ({len(vetoes)})", ""]
    out += [f"- {s.country} {s.qid} {s.prop} {s.value}: {s.reason}" for s in vetoes]
    open_ = [r for r in ledger.removals() if r["status"] in ("proposed", "approved") and r["sent"] is None]
    out += ["", f"## Open removals ({len(open_)})", ""]
    out += [f"- {r['status']} {r['guid']} ({r['prop']} {r['value']}): {r['reason']}" for r in open_]
    return "\n".join(out)


def main(args: list[str]) -> None:
    log = lambda m: print(m, file=sys.stderr, flush=True)  # noqa: E731
    if args == ["--status"]:
        print(status())
        return
    if args == ["--propose-reverts"]:
        propose_reverts(log)
        return
    submit = "--submit" in args
    rest = [a for a in args if a != "--submit"]
    if rest and not (len(rest) == 2 and rest[0] == "--batch" and rest[1].isdigit()):
        sys.exit("usage: outbox [--status | --propose-reverts | [--submit] [--batch <n>]]")
    sent = run(log, int(rest[1]) if rest else None, submit=submit)
    print(f"QS3 batch {sent}" if sent else f"nothing sent; review {PENDING}")
