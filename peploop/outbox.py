"""Send one country's accepted proposals to Wikidata, and settle each row by what landed.

The peploop side of `send.py`. Each person with accepted rows is pre-flighted
against their live item and planned (`plan.py`); the plan is rendered as QS3
lines (`route.py`); the lines go out as one batch, and approved removals as another.

    python -m peploop.cli send --country jp            # dry: write send/<cc>.qs, print the routes
    python -m peploop.cli send --country jp --submit   # send it, wait, settle the rows
    python -m peploop.cli send --status

A row moves `accepted` → `sent` when its line is recorded, before the request,
so a lost answer never sends it twice; then `applied` once every line it rode on
is live, or `failed` when QS3 reports one failed. A row the plan closes without
a line (`exists`, `conflict`, `ambiguous-statement`, …) is `skipped` under
`plan:<route>`, which a re-propose keeps for as long as the route still holds.
"""

import datetime as dt
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

from peploop import db, ledger, plan, route, send

TOOL = "peploop"
OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "peploop" / "send"
SENT, FAILED, APPLIED = "sent", "failed", "applied"
Log = Callable[[str], None]


def settle(log: Log) -> None:
    """Move `sent` rows to `applied` when every line they rode on landed, or to `failed` when one failed."""
    by_row: dict[int, set[str]] = defaultdict(set)
    rows = db.conn().execute(
        "SELECT e.status, unnest(e.refs) FROM wd_edit e JOIN wd_batch b ON b.id = e.batch_id"
        " WHERE b.tool = %s AND e.op = 'add'", (TOOL,)).fetchall()
    for status, row_id in rows:
        by_row[row_id].add(status)
    applied = [r for r, s in by_row.items() if s == {"landed"}]
    failed = [r for r, s in by_row.items() if "failed" in s]
    con = db.conn()
    n_applied = con.execute("UPDATE proposal SET status = %s WHERE id = ANY(%s) AND status = %s",
                            (APPLIED, applied, SENT)).rowcount
    n_failed = con.execute("UPDATE proposal SET status = %s WHERE id = ANY(%s) AND status = %s",
                           (FAILED, failed, SENT)).rowcount
    log(f"settled: {n_applied} rows applied, {n_failed} failed")


def routed(country: str, qids: list[str], log: Log, threads: int) -> list[route.Routed]:
    """Pre-flight and route every person; a person whose pre-flight fails is left for the next send."""
    def one(qid: str) -> route.Routed | None:
        try:
            entity, rows, _moved = plan.preflight(qid)
        except Exception as exc:  # noqa: BLE001 -- one item must not end the send
            log(f"{qid}: pre-flight failed, left accepted: {exc}")
            return None
        return route.route(qid, entity, rows)

    with ThreadPoolExecutor(threads) as pool:
        people = [r for r in pool.map(one, qids) if r is not None]
    vetoes = ledger.strikes()
    taken = {k for k, *_ in ledger.edits("add")}
    for person in people:
        keep = []
        for line, ids in person.edits:
            why = "struck" if ledger.struck(line, vetoes) else "already-sent" if ledger.key(line) in taken else None
            if why is None:
                keep.append((line, ids))
            else:
                person.skipped += [(i, why) for i in ids]
                person.routes[why] += 1
        person.edits = keep
        person.lines = [line for line, _ in keep]
    return people


def close(people: list[route.Routed]) -> int:
    """Record every row the plan closed without a line as `skipped` under its route."""
    n = 0
    for person in people:
        n += plan.retire(plan.Plan(qid=person.qid, skipped=person.skipped))
    return n


def mark_sent(ids: list[int], batch_name: str) -> None:
    db.conn().execute("UPDATE proposal SET status = %s, applied_batch = %s WHERE id = ANY(%s) AND status = 'accepted'",
                      (SENT, batch_name, ids))


def retry(country: str, log: Log) -> int | None:
    """Send this tool's failed lines again, one edit each, and settle their rows."""
    failed = [r for r, in db.conn().execute(
        "SELECT p.id FROM proposal p JOIN person pe ON pe.qid = p.person_qid"
        " WHERE pe.country = %s AND p.status = %s", (country, FAILED)).fetchall()]

    def requeue(name: str) -> None:
        db.conn().execute("UPDATE proposal SET status = %s, applied_batch = %s WHERE id = ANY(%s)",
                          (SENT, name, failed))

    with send.writer_lock(f"peploop send {country} --retry"):
        qs_id = send.retry(TOOL, "add", f"peploop retry {country} {dt.date.today().isoformat()}", send.live_keys, log,
                           on_recorded=requeue, country=country)
        settle(log)
    return qs_id


def run(country: str, log: Log, submit: bool = False, qids: list[str] | None = None,
        threads: int = 8) -> list[int]:
    """Settle what went out before, route what is accepted now, write it to a file; with `submit`, send it.

    Returns the QS3 batch ids sent.
    """
    send.prepare(TOOL, log)
    settle(log)
    people = routed(country, plan.people(list(qids or []), country), log, threads)
    routes: Counter[str] = Counter()
    for person in people:
        routes.update(person.routes)
    lines = [line for person in people for line in person.lines]
    errors = route.validate(lines)
    log(f"{len(people)} people: " + " ".join(f"{k}={v}" for k, v in sorted(routes.items())))
    log(f"{len(lines)} lines, {sum(len(p.skipped) for p in people)} rows closed without one, "
        f"{sum(len(p.deferred) for p in people)} rows wait for the next send")
    if errors:
        raise SystemExit("refused: " + "; ".join(errors[:5]))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{country}.qs"
    path.write_text("\n".join(lines) + "\n" if lines else "")
    log(f"{path}: {len(lines)} lines")
    if not submit:
        return []
    rows = [(country, ledger.key(line), line, ids) for person in people for line, ids in person.edits]
    ids = sorted({i for _, _, _, refs in rows for i in refs})
    # Uncombined: a combined edit fails whole when one of its commands
    # does, and QS3 says neither which nor why.
    return send.dispatch(TOOL, f"peploop send {country} {dt.date.today().isoformat()}", rows, log, combine=False,
                         on_recorded=lambda name: mark_sent(ids, name),
                         before=lambda: log(f"closed {close(people)} rows without a line"),
                         after=lambda: settle(log))
