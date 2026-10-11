"""Move `ptree_emitted` into the batch/edit/strike/removal ledger, once.

    .venv/bin/python -m peptree.migrate_ledger          # dry: print what it would do
    .venv/bin/python -m peptree.migrate_ledger --apply

Idempotent: a second run finds `ptree_emitted` gone and only re-imports the
strike notes, which are keyed. `ptree_emitted` is renamed, not dropped.
"""

import re
import sys
from collections import Counter

from peptree import ledger, sweep, wd

#: Batch ids above this are QS3's; below, paste-era chunks.
PASTE_MAX = 999
QS3_NAMES = {59044: "peptree outbox 2026-10-11 batch 62", 59046: "peptree outbox 2026-10-11"}
#: An old status → the edit status. Every `emitted` row left is in a pasted chunk
#: and never landed (they are the lines struck by hand while pasting).
STATUS = {"landed": "landed", "reverted": "reverted", "emitted": "failed"}
STRIKE_CLAUSE = re.compile(r"\bstrike ([^;]+)")
STRIKE_ITEM = re.compile(r"(Q\d+) (P\d+)(?: (Q\d+))?(?: \(([^)]*)\))?")


def note_strikes(notes: dict[str, str]) -> list[ledger.Strike]:
    """Strikes written into the sweep ledger's notes: `strike Q1 P17 (why), Q2 P279 Q3 (why)`."""
    out = []
    for cc, text in sorted(notes.items()):
        for clause in STRIKE_CLAUSE.findall(text):
            for qid, prop, value, why in STRIKE_ITEM.findall(clause):
                out.append(ledger.Strike(qid, prop, value or ledger.ANY, cc, why or "struck in review"))
    return out


def main(args: list[str]) -> None:
    apply = args == ["--apply"]
    wd.init()
    con = wd.conn()
    exists = con.execute("SELECT to_regclass('ptree_emitted') IS NOT NULL").fetchone()[0]
    if exists:
        rows = con.execute("SELECT key, country, line, chunk, status FROM ptree_emitted").fetchall()
        print(f"ptree_emitted: {len(rows)} rows, {Counter(s for *_, s in rows)}")
        unknown = {s for *_, s in rows} - set(STATUS)
        if unknown:
            sys.exit(f"unmapped statuses: {unknown}")
        if apply:
            with con.transaction():
                ids = {}
                for chunk in sorted({c for _, _, _, c, _ in rows}):
                    qs3 = chunk > PASTE_MAX
                    ids[chunk] = con.execute(
                        "INSERT INTO ptree_batch (kind, op, name, qs3_id, paste_chunk, status, finished_at)"
                        " VALUES (%s, 'add', %s, %s, %s, 'done', now()) RETURNING id",
                        ("qs3" if qs3 else "paste",
                         QS3_NAMES.get(chunk, f"peptree outbox {chunk}") if qs3 else f"peptree outbox chunk-{chunk:03d}",
                         chunk if qs3 else None, None if qs3 else chunk)).fetchone()[0]
                for key, cc, line, chunk, status in rows:
                    con.execute("INSERT INTO ptree_edit (op, key, country, line, batch_id, status)"
                                " VALUES ('add', %s, %s, %s, %s, %s)", (key, cc, line, ids[chunk], STATUS[status]))
                con.execute("ALTER TABLE ptree_emitted RENAME TO ptree_emitted_old")
            print(f"moved: {len(ids)} batches, {len(rows)} edits; ptree_emitted renamed ptree_emitted_old")
    found = note_strikes({cc: r["notes"] for cc, r in sweep.read().items()})
    for s in found:
        print(f"strike {s.country} {s.qid} {s.prop} {s.value}: {s.reason}")
        if apply:
            ledger.strike(s.qid, s.prop, s.value, s.country, s.reason, origin="note")
    if not apply:
        print("dry run; pass --apply")


if __name__ == "__main__":
    main(sys.argv[1:])
