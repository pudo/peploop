#!/usr/bin/env python
"""Replace an undated P39 with the several dated statements it should have been.

    python scripts/apply_replacements.py --campaign enrich/pl_...        # dry
    python scripts/apply_replacements.py --campaign enrich/pl_... --apply

Reads the `undated_needs_removal` byproducts a run left behind. Those are the
people whose item carries **one `P39` with no dates at all** while the evidence
says they served several terms — a statement that looks recorded and emits no
PEP, because `zavod` refuses an Occupancy when nothing is dated anywhere.

Neither ordinary path fixes it. QuickStatements matches on subject, property and
value, so the dated lines fold into that one statement and leave it carrying
every start and every end; the API creates, so it would leave the undated one
standing beside the new ones. This sends **one `wbeditentity`** carrying the
removal and the replacements together: one revision, whole or nothing, and one
undo restores the item.

This is the most dangerous script here, so it refuses more than it writes:

* **Removal is the last resort, not the plan.** Eleven of Poland's fourteen turn
  out to carry `P2937` naming a parliamentary term whose own item is dated, so
  the statement is dated by reference and the honest fix is a QuickStatements
  merge with no removal at all. Those are reported and skipped.
* **Nothing is dropped silently.** Every qualifier and reference on the old
  statement is copied onto the replacements, and a snak that cannot be expressed
  is a refusal rather than a loss.
* **A term-specific qualifier stops a split.** "9th term of the Sejm" cannot be
  attributed across two replacements.
* **`--baserevid`.** The edit is rejected if the item moved since the revision
  the plan was built from, rather than applied to state nobody inspected.
* **Dry by default**, a ledger so a re-run cannot write twice, and the removed
  statement's full JSON in `applied.jsonl` so a bad edit can be undone by hand.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wd.http import REPO_ROOT, make_session
from wd.replace import Plan, payload, plan
from wd.write import Ledger, WriteError, edit_entity, log

RULE = "undated_needs_removal"


def spans_for(records: list) -> list:
    """The dated spans a person's byproduct records propose, deduplicated."""
    out = []
    for record in records:
        for statement in record.get("statements") or []:
            quals = {q["property"]: q["value"].get("iso")
                     for q in statement.get("qualifiers", [])}
            span = (quals.get("P580"), quals.get("P582"))
            if (span[0] or span[1]) and span not in out:
                out.append(span)
    return sorted(out, key=lambda s: s[0] or "")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", required=True,
                        help="subdirectory of data/ holding the run")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    base = REPO_ROOT / "data" / args.campaign
    verdicts = sorted((base / "verdicts").glob("*.jsonl"))
    if not verdicts:
        raise SystemExit(f"no verdicts under {base}")
    manifest = base / "verdicts" / "manifest.json"
    owned = None
    if manifest.exists():
        owned = set(json.loads(manifest.read_text())["files"])

    by_person: dict = {}
    for path in verdicts:
        if owned is not None and path.name not in owned:
            continue
        for line in path.read_text().splitlines():
            record = json.loads(line)
            if record["decision"].get("rule") != RULE:
                continue
            key = (record["subject"]["qid"],
                   (record["statements"] or [{}])[0].get("value", {}).get("id"))
            by_person.setdefault(key, []).append(record)
    if not by_person:
        raise SystemExit(f"nothing with rule {RULE} in {base}")

    session = make_session()
    ledger = Ledger.load(base / "replacements_written.json")
    items = sorted(by_person.items())[: args.limit] if args.limit \
        else sorted(by_person.items())
    print(f"{len(items)} people with an undated statement to consider\n")

    plans: list = []
    for (qid, position), records in items:
        if not position:
            continue
        result: Plan = plan(session, qid, position, spans_for(records))
        plans.append((result, records))
        print(f"  {'·' if not result.ok else '→'} {result.describe()}")

    ok = [p for p, _ in plans if p.ok]
    datable = [p for p, _ in plans if p.dates]
    refused = [p for p, _ in plans if not p.ok and not p.dates]
    print(f"\n  {len(ok)} to replace, {len(datable)} datable from their own term "
          f"(merge instead — no removal), {len(refused)} refused")
    if datable:
        out = base / "datable_from_term.json"
        out.write_text(json.dumps(
            [{"qid": p.qid, "guid": p.guid, "start": p.dates[0], "end": p.dates[1]}
             for p in datable], indent=1) + "\n")
        print(f"  the datable ones are in {out} — they want a QuickStatements "
              "merge, not this script")
    if not args.apply:
        print("\nDry run — pass --apply to write.")
        return

    written = failed = 0
    for result, _ in plans:
        if not result.ok:
            continue
        ref = f"{result.qid}:{result.guid}"
        try:
            done = edit_entity(
                payload(result),
                summary=(f"replace an undated [[Property:P39]] statement with "
                         f"{len(result.claims)} dated ones, carrying its "
                         f"qualifiers and references"),
                ledger=ledger, ref=ref, apply=True, baserevid=result.baserevid,
            )
        except WriteError as exc:
            failed += 1
            print(f"  ! {result.qid}: {exc}")
            continue
        if done:
            written += 1
            # The removed statement in full, so a bad edit is undoable by hand.
            log(base / "applied.jsonl", {
                "script": "apply_replacements", "qid": result.qid,
                "baserevid": result.baserevid, "removed": result.removing,
                "added": result.claims,
            })
    print(f"\nwrote {written} people, {failed} failed")


if __name__ == "__main__":
    main()
