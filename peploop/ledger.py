"""What peploop and peptree have sent to Wikidata, what they must never send, and what to take back.

Both tools write through QuickStatements 3.0 (`send.py`), and both keep their
account here, so a statement one tool sent or a reviewer struck is settled for
the other too. Four tables (`peploop/schema.sql`), one module that writes them:

- `wd_batch`: one QuickStatements batch, opened before the request so a lost
  answer can be found again rather than sent twice.
- `wd_edit`: one statement sent in a batch, added, removed or created.
- `wd_strike`: a reviewer's veto on an addition. No send carries a struck
  line, whatever a later run proposes.
- `wd_removal`: a statement, by GUID, that should leave Wikidata. Removing a
  statement is the human gate, so a removal is `proposed` until approved --
  except the undo of our own edit, where the strike was the approval.
"""

import re
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from peploop import db, qs
from peploop.wikidata import fetch_items

ANY = "*"
#: The reference properties that name a URL we read: every lane cites the
#: revision (`P4656`); peptree's earlier sends cited the page (`P854`).
URL_PROPS = ("P854", "P4656")
RETRIEVED = re.compile(r"\tS813\t\+\S+")


@dataclass(frozen=True)
class Strike:
    qid: str
    prop: str
    value: str
    country: str
    reason: str

    def matches(self, qid: str, prop: str, value: str) -> bool:
        return self.qid == qid and self.prop == prop and self.value in (ANY, value)


# --- lines ---------------------------------------------------------------------------

def statement(line: str) -> tuple[str, str, str]:
    """(item, property, value) of a V1 line; a leading `+` (always create) is not part of the item."""
    cols = qs.SUMMARY_RE.sub("", line).split("\t")
    return cols[0].lstrip("+"), cols[1], cols[2]


def key(line: str) -> str:
    """The statement a line adds, without the parts that vary run to run (summary, retrieval date)."""
    return RETRIEVED.sub("", qs.SUMMARY_RE.sub("", line)).strip()


# --- batches and edits ---------------------------------------------------------------

def open_batch(tool: str, op: str, name: str, kind: str = "qs3") -> int:
    row = db.conn().execute(
        "INSERT INTO wd_batch (tool, kind, op, name, status) VALUES (%s, %s, %s, %s, 'sending') RETURNING id",
        (tool, kind, op, name)).fetchone()
    return row[0]


def bind_qs3(batch_id: int, qs3_id: int) -> None:
    db.conn().execute("UPDATE wd_batch SET qs3_id = %s, status = 'running' WHERE id = %s", (qs3_id, batch_id))


def close_batch(batch_id: int, status: str) -> None:
    db.conn().execute("UPDATE wd_batch SET status = %s, finished_at = now() WHERE id = %s", (status, batch_id))


def rename_batch(batch_id: int, name: str) -> None:
    db.conn().execute("UPDATE wd_batch SET name = %s WHERE id = %s", (name, batch_id))


def record_edits(batch_id: int, op: str, rows: Iterable[tuple[str, str, str, list[int]]]) -> None:
    """Record (country, key, line, refs) as sent in a batch."""
    con = db.conn()
    with con.transaction():
        for country, k, line, refs in rows:
            con.execute("INSERT INTO wd_edit (op, key, country, line, batch_id, refs) VALUES (%s,%s,%s,%s,%s,%s)",
                        (op, k, country, line, batch_id, list(refs)))


def move_edits(batch_id: int, op: str, keys: Iterable[str]) -> None:
    """Move failed edits onto a new batch, to be sent again: the statement keeps its key, never a second row."""
    con = db.conn()
    with con.transaction():
        for k in keys:
            con.execute("UPDATE wd_edit SET batch_id = %s, status = 'sent', status_at = now()"
                        " WHERE op = %s AND key = %s AND status = 'failed'", (batch_id, op, k))


def set_status(op: str, keys: Iterable[str], status: str) -> None:
    con = db.conn()
    for k in keys:
        con.execute("UPDATE wd_edit SET status = %s, status_at = now() WHERE op = %s AND key = %s",
                    (status, op, k))


def edits(op: str, tool: str | None = None) -> list[tuple[str, str, str, int, str]]:
    """(key, country, line, batch_id, status) of every edit of one op, of one tool's batches or all."""
    return db.conn().execute(
        "SELECT e.key, e.country, e.line, e.batch_id, e.status FROM wd_edit e JOIN wd_batch b ON b.id = e.batch_id"
        " WHERE e.op = %s AND (%s::text IS NULL OR b.tool = %s)", (op, tool, tool)).fetchall()


def stuck(tool: str) -> list[tuple[int, str]]:
    """(id, name) of the tool's batches sent but never bound to a QS3 id: the answer was lost."""
    return db.conn().execute("SELECT id, name FROM wd_batch WHERE tool = %s AND kind = 'qs3' AND qs3_id IS NULL "
                             "AND status = 'sending'", (tool,)).fetchall()


# --- strikes -------------------------------------------------------------------------

def strikes() -> list[Strike]:
    rows = db.conn().execute("SELECT qid, prop, value, country, reason FROM wd_strike").fetchall()
    return [Strike(*r) for r in rows]


def struck(line: str, found: list[Strike]) -> Strike | None:
    """The strike that vetoes a line, if any."""
    qid, prop, value = statement(line)
    return next((s for s in found if s.matches(qid, prop, value)), None)


def strike(tool: str, qid: str, prop: str, value: str, country: str, reason: str,
           origin: str = "cli", log: Callable[[str], None] = print) -> list[str]:
    """Veto an addition; if one we sent already landed, queue its removal. Returns the GUIDs queued."""
    db.conn().execute(
        "INSERT INTO wd_strike (qid, prop, value, tool, country, reason, origin) VALUES (%s,%s,%s,%s,%s,%s,%s)"
        " ON CONFLICT (qid, prop, value) DO NOTHING", (qid, prop, value, tool, country, reason, origin))
    rule = Strike(qid, prop, value, country, reason)
    landed = [line for _, _, line, _, status in edits("add") if status == "landed" and struck(line, [rule])]
    if not landed:
        return []
    claims = fetch_items([qid], props="claims").get(qid, {}).get("claims", {})
    queued = []
    for line in landed:
        _, _, v = statement(line)
        for guid, ours in candidates(claims.get(prop, []), v, ours_urls(line)):
            propose_removal(tool, guid, qid, prop, v, country, reason, "strike", ours,
                            "approved" if ours else "proposed")
            log(f"removal of {guid} ({prop} {v}) {'approved: our own edit' if ours else 'proposed'}")
            queued.append(guid)
    return queued


# --- removals ------------------------------------------------------------------------

def ours_urls(line: str) -> set[str]:
    """The URLs a line of ours cites."""
    cols = [c for c in qs.SUMMARY_RE.sub("", line).split("\t") if c not in ("R+", "R0", "R-")]
    sources = {"S" + p[1:] for p in URL_PROPS}
    return {cols[i + 1].strip('"') for i in range(3, len(cols) - 1, 2) if cols[i].lstrip("!") in sources}


def value_id(snak: dict[str, Any]) -> str | None:
    value = (snak.get("datavalue") or {}).get("value")
    return value.get("id") if isinstance(value, dict) else None


def candidates(claims: list[dict[str, Any]], value: str, urls: set[str]) -> list[tuple[str, bool]]:
    """(GUID, ours) of each live statement holding `value`.

    A statement is ours when it is the only one with that value and every
    reference on it cites a URL we cited: anyone else's source means someone
    else stands behind it too.
    """
    found = [c for c in claims if value_id(c.get("mainsnak", {})) == value]
    out = []
    for c in found:
        refs = c.get("references") or []
        cited = [{_url(s) for p in URL_PROPS for s in r.get("snaks", {}).get(p, [])} for r in refs]
        ours = len(found) == 1 and all(cite and cite <= urls for cite in cited)
        out.append((c["id"], ours))
    return out


def _url(snak: dict[str, Any]) -> str:
    return str((snak.get("datavalue") or {}).get("value", ""))


def propose_removal(tool: str, guid: str, qid: str, prop: str, value: str, country: str | None, reason: str,
                    origin: str, ours: bool, status: str = "proposed") -> None:
    db.conn().execute(
        "INSERT INTO wd_removal (guid, tool, qid, prop, value, country, reason, origin, ours, status, decided_at)"
        " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, CASE WHEN %s = 'proposed' THEN NULL ELSE now() END)"
        " ON CONFLICT (guid) DO NOTHING",
        (guid, tool, qid, prop, value, country, reason, origin, ours, status, status))


def decide(guids: Iterable[str], status: str) -> int:
    """Approve or reject removals; returns how many changed."""
    n = 0
    for g in guids:
        n += db.conn().execute(
            "UPDATE wd_removal SET status = %s, decided_at = now() WHERE guid = %s AND status = 'proposed'",
            (status, g)).rowcount
    return n


def mark_gone(guid: str) -> None:
    db.conn().execute("UPDATE wd_removal SET status = 'gone' WHERE guid = %s", (guid,))


def removals(status: str | None = None, tool: str | None = None) -> list[dict[str, Any]]:
    cur = db.conn().execute(
        "SELECT r.guid, r.qid, r.prop, r.value, r.country, r.reason, r.origin, r.ours, r.status, e.status, r.tool"
        " FROM wd_removal r LEFT JOIN wd_edit e ON e.op = 'remove' AND e.key = r.guid"
        " WHERE (%s::text IS NULL OR r.status = %s) AND (%s::text IS NULL OR r.tool = %s)"
        " ORDER BY r.created_at", (status, status, tool, tool))
    cols = ("guid", "qid", "prop", "value", "country", "reason", "origin", "ours", "status", "sent", "tool")
    return [dict(zip(cols, r)) for r in cur.fetchall()]
