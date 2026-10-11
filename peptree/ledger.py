"""What peptree has sent to Wikidata, what it must never send, and what it should take back.

Four tables, one module that writes them:

- `ptree_batch`: one QuickStatements batch, opened before the request so a
  lost answer can be found again rather than sent twice.
- `ptree_edit`: one statement sent in a batch, added or removed.
- `ptree_strike`: a reviewer's veto on an addition. The outbox never sends a
  struck line, whatever a later run proposes.
- `ptree_removal`: a statement, by GUID, that should leave Wikidata. Removing a
  statement is the human gate, so a removal is `proposed` until approved --
  except the undo of our own edit, where the strike was the approval.
"""

from dataclasses import dataclass
from typing import Any, Callable, Iterable

from peptree import qs, wd

ANY = "*"


@dataclass(frozen=True)
class Strike:
    qid: str
    prop: str
    value: str
    country: str
    reason: str

    def matches(self, qid: str, prop: str, value: str) -> bool:
        return self.qid == qid and self.prop == prop and self.value in (ANY, value)


# --- batches and edits ---------------------------------------------------------------

def open_batch(op: str, name: str, kind: str = "qs3") -> int:
    row = wd.conn().execute(
        "INSERT INTO ptree_batch (kind, op, name, status) VALUES (%s, %s, %s, 'sending') RETURNING id",
        (kind, op, name)).fetchone()
    return row[0]


def bind_qs3(batch_id: int, qs3_id: int) -> None:
    wd.conn().execute("UPDATE ptree_batch SET qs3_id = %s, status = 'running' WHERE id = %s", (qs3_id, batch_id))


def close_batch(batch_id: int, status: str) -> None:
    wd.conn().execute("UPDATE ptree_batch SET status = %s, finished_at = now() WHERE id = %s", (status, batch_id))


def record_edits(batch_id: int, op: str, rows: Iterable[tuple[str, str, str]]) -> None:
    """Record (country, key, line) as sent in a batch."""
    con = wd.conn()
    with con.transaction():
        for country, key, line in rows:
            con.execute("INSERT INTO ptree_edit (op, key, country, line, batch_id) VALUES (%s,%s,%s,%s,%s)",
                        (op, key, country, line, batch_id))


def set_status(op: str, keys: Iterable[str], status: str) -> None:
    con = wd.conn()
    for k in keys:
        con.execute("UPDATE ptree_edit SET status = %s, status_at = now() WHERE op = %s AND key = %s",
                    (status, op, k))


def edits(op: str) -> list[tuple[str, str, str, int, str]]:
    """(key, country, line, batch_id, status) of every edit of one op."""
    return wd.conn().execute(
        "SELECT key, country, line, batch_id, status FROM ptree_edit WHERE op = %s", (op,)).fetchall()


# --- strikes -------------------------------------------------------------------------

def strikes() -> list[Strike]:
    rows = wd.conn().execute("SELECT qid, prop, value, country, reason FROM ptree_strike").fetchall()
    return [Strike(*r) for r in rows]


def struck(line: str, found: list[Strike]) -> Strike | None:
    """The strike that vetoes a line, if any."""
    qid, prop, value = qs.statements([line])[0]
    return next((s for s in found if s.matches(qid, prop, value)), None)


def strike(qid: str, prop: str, value: str, country: str, reason: str,
           origin: str = "cli", log: Callable[[str], None] = print) -> list[str]:
    """Veto an addition; if one we sent already landed, queue its removal. Returns the GUIDs queued."""
    wd.conn().execute(
        "INSERT INTO ptree_strike (qid, prop, value, country, reason, origin) VALUES (%s,%s,%s,%s,%s,%s)"
        " ON CONFLICT (qid, prop, value) DO NOTHING", (qid, prop, value, country, reason, origin))
    rule = Strike(qid, prop, value, country, reason)
    sent = [(line, status) for _, _, line, _, status in edits("add") if struck(line, [rule])]
    landed = [line for line, status in sent if status == "landed"]
    if not landed:
        return []
    claims = wd.fetch_items([qid], props="claims").get(qid, {}).get("claims", {})
    queued = []
    for line in landed:
        _, _, v = qs.statements([line])[0]
        for guid, ours in candidates(claims.get(prop, []), v, ours_urls(line)):
            propose_removal(guid, qid, prop, v, country, reason, "strike", ours,
                            "approved" if ours else "proposed")
            log(f"removal of {guid} ({prop} {v}) {'approved: our own edit' if ours else 'proposed'}")
            queued.append(guid)
    return queued


# --- removals ------------------------------------------------------------------------

def ours_urls(line: str) -> set[str]:
    """The S854 URLs a line of ours cites."""
    cols = qs.SUMMARY_RE.sub("", line).split("\t")
    return {cols[i + 1].strip('"') for i in range(3, len(cols) - 1, 2) if cols[i] == "S854"}


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
        cited = [{_url(s) for s in r.get("snaks", {}).get("P854", [])} for r in refs]
        ours = len(found) == 1 and all(cite and cite <= urls for cite in cited)
        out.append((c["id"], ours))
    return out


def _url(snak: dict[str, Any]) -> str:
    return str((snak.get("datavalue") or {}).get("value", ""))


def propose_removal(guid: str, qid: str, prop: str, value: str, country: str | None, reason: str,
                    origin: str, ours: bool, status: str = "proposed") -> None:
    wd.conn().execute(
        "INSERT INTO ptree_removal (guid, qid, prop, value, country, reason, origin, ours, status, decided_at)"
        " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s, CASE WHEN %s = 'proposed' THEN NULL ELSE now() END)"
        " ON CONFLICT (guid) DO NOTHING",
        (guid, qid, prop, value, country, reason, origin, ours, status, status))


def decide(guids: Iterable[str], status: str) -> int:
    """Approve or reject removals; returns how many changed."""
    n = 0
    for g in guids:
        n += wd.conn().execute(
            "UPDATE ptree_removal SET status = %s, decided_at = now() WHERE guid = %s AND status = 'proposed'",
            (status, g)).rowcount
    return n


def removals(status: str | None = None) -> list[dict[str, Any]]:
    cur = wd.conn().execute(
        "SELECT r.guid, r.qid, r.prop, r.value, r.country, r.reason, r.origin, r.ours, r.status, e.status"
        " FROM ptree_removal r LEFT JOIN ptree_edit e ON e.op = 'remove' AND e.key = r.guid"
        + (" WHERE r.status = %s" if status else "") + " ORDER BY r.created_at",
        (status,) if status else ())
    cols = ("guid", "qid", "prop", "value", "country", "reason", "origin", "ours", "status", "sent")
    return [dict(zip(cols, r)) for r in cur.fetchall()]
