"""Take statements back off Wikidata: strike an addition, decide a removal, send the approved ones.

Removing a statement is the human gate. A removal is `proposed` until someone
approves it, except the undo of our own edit, where striking it was the
approval. Every removal goes out by GUID, in a batch of removals only, after a
live pre-flight: a statement already gone is recorded `gone`, one whose value
moved since it was proposed is held back, and only the rest are sent.

    python -m peptree.cli strike <qid> <prop> [value] --reason "…" [--country cc]
    python -m peptree.cli removals                    # open removals, by status
    python -m peptree.cli removals approve <guid…>
    python -m peptree.cli removals reject <guid…>
    python -m peptree.cli removals submit             # pre-flight, then send the approved ones as one QS3 batch
"""

import argparse
import datetime as dt
import sys
from typing import Any, Callable

from peptree import ledger, outbox, qs, wd


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


def submit(log: Callable[[str], None]) -> int | None:
    """Pre-flight every approved, unsent removal against live state and send what survives."""
    rows = [r for r in ledger.removals("approved") if r["sent"] is None]
    if not rows:
        log("no approved removals to send")
        return None
    ents = wd.fetch_items(sorted({r["qid"] for r in rows}), props="claims")
    sorted_ = preflight(rows, ents)
    for r in sorted_["gone"]:
        wd.conn().execute("UPDATE ptree_removal SET status = 'gone' WHERE guid = %s", (r["guid"],))
        log(f"gone already: {r['guid']}")
    for r in sorted_["moved"]:
        log(f"held: {r['guid']} no longer holds {r['prop']} {r['value']}")
    send = sorted_["send"]
    lines = [qs.removal_line(r["guid"], r["reason"]) for r in send]
    errors = qs.validate_removals(lines)
    if errors:
        sys.exit("refused: " + "; ".join(errors[:5]))
    if not lines:
        return None
    name = f"peptree removals {dt.date.today().isoformat()}"
    return outbox.send("remove", name, [(r["country"] or "", r["guid"], line) for r, line in zip(send, lines)], log)


def listing() -> str:
    rows = ledger.removals()
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


def country_of(qid: str) -> str | None:
    """The country whose run proposed something for this item, from the ledger or the proposals."""
    row = wd.conn().execute("SELECT country FROM ptree_edit WHERE op = 'add' AND key LIKE %s LIMIT 1",
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
    queued = ledger.strike(a.qid, a.prop, a.value, cc, a.reason, log=lambda m: print(m, file=sys.stderr))
    print(f"struck {a.qid} {a.prop} {a.value} ({cc})" + (f"; {len(queued)} removals queued" if queued else ""))


def main(args: list[str]) -> None:
    log = lambda m: print(m, file=sys.stderr, flush=True)  # noqa: E731
    if not args or args == ["list"]:
        print(listing())
    elif args[0] in ("approve", "reject") and len(args) > 1:
        n = ledger.decide(args[1:], "approved" if args[0] == "approve" else "rejected")
        print(f"{n} of {len(args) - 1} {args[0]}d (only proposed removals change)")
    elif args == ["submit"]:
        sent = submit(log)
        print(f"QS3 batch {sent}" if sent else "nothing sent")
    else:
        sys.exit("usage: removals [list | approve <guid…> | reject <guid…> | submit]")
