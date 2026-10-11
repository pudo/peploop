"""Send one tool's edits to Wikidata as QuickStatements 3.0 batches, and read them back.

The one write path of peploop and peptree. A tool says what it would add now
and how to tell that a line of its own is live; this module turns that into a
batch, records it in the ledger (`ledger.py`) before the request, waits for
QS3, and settles every edit as `landed` or `failed`. Removals go the same way,
by GUID, after a live pre-flight. Additions, removals and creations never share
a batch.
"""

import re
import sys
from collections import Counter, defaultdict
from contextlib import contextmanager
from typing import Any, Callable, Iterator

from peploop import db, ledger, qs3
from peploop.wikidata import fetch_items

Log = Callable[[str], None]
#: Which of these lines are live now, as their ledger keys.
IsLive = Callable[[list[str]], set[str]]
#: QS3 batch status code → our batch status.
FINISHED = {qs3.DONE: "done", qs3.BLOCKED: "stopped", qs3.STOPPED: "stopped"}
LOCK = "wd-send"
GUID_RE = re.compile(r"^[Qq]\d+\$[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$")


@contextmanager
def writer_lock(who: str) -> Iterator[None]:
    """Hold the one-sender lock: `recover` reads every unbound batch as lost, which only holds with one sender."""
    conn = db.conn()
    if not conn.execute("SELECT pg_try_advisory_lock(hashtext(%s))", (LOCK,)).fetchone()[0]:
        raise RuntimeError(f"{who}: another send holds the lock ({LOCK})")
    try:
        yield
    finally:
        conn.execute("SELECT pg_advisory_unlock(hashtext(%s))", (LOCK,))


# --- removal lines -------------------------------------------------------------------

def removal_line(guid: str, reason: str) -> str:
    """Remove one statement by its GUID: never by value, which takes only the first match."""
    return f"-STATEMENT\t{guid} /* {reason.replace('*', '')} */"


def validate_removals(lines: list[str]) -> list[str]:
    """A removal batch carries `-STATEMENT` lines with a well-formed GUID, each once, and nothing else."""
    errors, seen = [], set()
    for n, text in enumerate(lines, 1):
        cols = ledger.SUMMARY_RE.sub("", text).split("\t")
        if len(cols) != 2 or cols[0] != "-STATEMENT" or not GUID_RE.match(cols[1]):
            errors.append(f"{n}: not a removal by GUID: {text!r}")
        elif cols[1] in seen:
            errors.append(f"{n}: {cols[1]} twice")
        seen.add(cols[1])
    return errors


# --- the batch -----------------------------------------------------------------------

def landed(sent: dict[str, str], live: set[str]) -> dict[str, str]:
    """New status per sent key: live → landed."""
    return {k: "landed" for k, status in sent.items() if status == "sent" and k in live}


def live_guids(guids: list[str]) -> set[str]:
    """Which of these statement GUIDs Wikidata still holds (read live)."""
    ents = fetch_items(sorted({g.split("$")[0].upper() for g in guids}), props="claims")
    held = {c["id"] for e in ents.values() for cs in e.get("claims", {}).values() for c in cs}
    return {g for g in guids if g in held}


def reconcile(tool: str, is_live: IsLive, log: Log) -> None:
    """Mark every sent addition of the tool's that is now live, and every sent removal now gone, as landed."""
    adds = ledger.edits("add", tool)
    sent = [line for _, _, line, _, s in adds if s == "sent"]
    moved = landed({k: s for k, _, _, _, s in adds}, is_live(sent) if sent else set())
    ledger.set_status("add", moved, "landed")
    removes = [k for k, _, _, _, s in ledger.edits("remove", tool) if s == "sent"]
    gone = set(removes) - live_guids(removes) if removes else set()
    ledger.set_status("remove", gone, "landed")
    log(f"reconciled: {len(moved)} additions landed, {len(gone)} removals landed")


def recover(tool: str, username: str, log: Log) -> None:
    """Bind a batch whose submit answer was lost to its QS3 id, found by its unique name."""
    for batch_id, name in ledger.stuck(tool):
        found = qs3.find(name, username) if username else None
        if found is None:
            ledger.close_batch(batch_id, "unknown")
            log(f"batch #{batch_id} {name!r}: no QS3 batch found; marked unknown, its lines stay sent")
        else:
            ledger.bind_qs3(batch_id, found)
            log(f"batch #{batch_id} recovered as QS3 {found}")


def send(tool: str, op: str, name: str, rows: list[tuple[str, str, str, list[int]]], is_live: IsLive,
         log: Log) -> int:
    """Send (country, key, line, refs) rows as one QS3 batch and wait for it; returns the QS3 id.

    The batch and its edits are recorded before the request: if the answer is
    lost, `recover` binds the batch by its name, which carries the local id.
    """
    batch_id = ledger.open_batch(tool, op, name)
    name = f"{name} #{batch_id}"
    ledger.rename_batch(batch_id, name)
    ledger.record_edits(batch_id, op, rows)
    qs_id = qs3.submit([line for _, _, line, _ in rows], name)
    ledger.bind_qs3(batch_id, qs_id)
    log(f"sent as QS3 batch {qs_id}: {qs3.link(qs_id)}  {qs3.EDITGROUPS.format(qs_id)}")
    row = qs3.wait(qs_id, log)
    ledger.close_batch(batch_id, FINISHED.get(row["status"]["code"], "unknown"))
    failed = {raw.strip() for raw in qs3.failed(qs_id)}
    bad = {k for _, k, line, _ in rows if line.strip() in failed}
    ledger.set_status(op, bad, "failed")
    if bad:
        log(f"{len(bad)} lines failed; see send --status")
    reconcile(tool, is_live, log)
    return qs_id


# --- removals ------------------------------------------------------------------------

def preflight(rows: list[dict[str, Any]], ents: dict[str, dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Sort approved removals by live state: `send`, `gone` (absent) or `moved` (value changed)."""
    out: dict[str, list[dict[str, Any]]] = {"send": [], "gone": [], "moved": []}
    for r in rows:
        claims = (ents.get(r["qid"]) or {}).get("claims", {})
        live = next((c for cs in claims.values() for c in cs if c["id"] == r["guid"]), None)
        if live is None:
            out["gone"].append(r)
        elif ledger.value_id(live.get("mainsnak", {})) != r["value"]:
            out["moved"].append(r)
        else:
            out["send"].append(r)
    return out


def pending_removals(tool: str, log: Log) -> list[tuple[str, str, str, list[int]]]:
    """Pre-flight every approved, unsent removal of the tool's against live state; rows for what survives."""
    rows = [r for r in ledger.removals("approved", tool) if r["sent"] is None]
    if not rows:
        return []
    sorted_ = preflight(rows, fetch_items(sorted({r["qid"] for r in rows}), props="claims"))
    for r in sorted_["gone"]:
        ledger.mark_gone(r["guid"])
        log(f"gone already: {r['guid']}")
    for r in sorted_["moved"]:
        log(f"held: {r['guid']} no longer holds {r['prop']} {r['value']}")
    out = [(r["country"] or "", r["guid"], removal_line(r["guid"], r["reason"]), []) for r in sorted_["send"]]
    errors = validate_removals([line for _, _, line, _ in out])
    if errors:
        sys.exit("refused: " + "; ".join(errors[:5]))
    return out


def removals_listing(tool: str) -> str:
    rows = ledger.removals(tool=tool)
    out = []
    for status in ("approved", "proposed", "rejected", "gone"):
        here = [r for r in rows if r["status"] == status]
        if not here:
            continue
        out += [f"## {status} ({len(here)})", ""]
        for r in here:
            sent = f" [sent: {r['sent']}]" if r["sent"] else ""
            out.append(f"- {r['guid']} {r['prop']} {r['value']} ({r['country'] or '-'}, {r['origin']}"
                       f"{', ours' if r['ours'] else ''}): {r['reason']}{sent}")
        out.append("")
    return "\n".join(out) or "no removals"


def removals_main(tool: str, args: list[str]) -> None:
    """`removals [list | approve <guid…> | reject <guid…>]`; approved ones go out with `send --submit`."""
    if not args or args == ["list"]:
        print(removals_listing(tool))
    elif args[0] in ("approve", "reject") and len(args) > 1:
        n = ledger.decide(args[1:], "approved" if args[0] == "approve" else "rejected")
        print(f"{n} of {len(args) - 1} {args[0]}d (only proposed removals change)")
    else:
        sys.exit("usage: removals [list | approve <guid…> | reject <guid…>]")


# --- status --------------------------------------------------------------------------

def status(tool: str) -> str:
    """The tool's batches with their edits by status, what is stuck, the strikes and the open removals."""
    con = db.conn()
    rows = con.execute(
        "SELECT b.id, b.kind, b.op, coalesce(b.qs3_id, b.paste_chunk), b.status, e.status, count(e.key)"
        " FROM wd_batch b LEFT JOIN wd_edit e ON e.batch_id = b.id WHERE b.tool = %s"
        " GROUP BY 1, 2, 3, 4, 5, 6 ORDER BY 1", (tool,)).fetchall()
    by: dict[tuple, Counter] = defaultdict(Counter)
    for bid, kind, op, ext, bstatus, estatus, n in rows:
        by[(bid, kind, op, ext, bstatus)][estatus] += n
    out = ["| # | kind | op | QS id | batch | sent | landed | failed | reverted |", "|---|---|---|---|---|---|---|---|---|"]
    for (bid, kind, op, ext, bstatus), c in by.items():
        out.append(f"| {bid} | {kind} | {op} | {ext or ''} | {bstatus} | {c['sent']} | {c['landed']} | "
                   f"{c['failed']} | {c['reverted']} |")
    stuck = con.execute("SELECT e.op, e.status, e.line FROM wd_edit e JOIN wd_batch b ON b.id = e.batch_id"
                        " WHERE b.tool = %s AND e.status IN ('sent', 'failed') ORDER BY 1, 2, 3", (tool,)).fetchall()
    out += ["", f"## Sent but not landed ({len(stuck)})", ""] + [f"- {o} {s}: {line}" for o, s, line in stuck]
    vetoes = ledger.strikes()
    out += ["", f"## Strikes ({len(vetoes)})", ""]
    out += [f"- {s.country} {s.qid} {s.prop} {s.value}: {s.reason}" for s in vetoes]
    open_ = [r for r in ledger.removals(tool=tool) if r["status"] in ("proposed", "approved") and r["sent"] is None]
    out += ["", f"## Open removals ({len(open_)})", ""]
    out += [f"- {r['status']} {r['guid']} ({r['prop']} {r['value']}): {r['reason']}" for r in open_]
    return "\n".join(out)
