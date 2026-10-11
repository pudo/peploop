#!/usr/bin/env python
"""Remove the statements `iq_removals.py` proposed, one `wb remove-claim` each.

    python scripts/apply_removals.py --campaign iraq            # dry, the default
    python scripts/apply_removals.py --campaign iraq --apply    # HUMAN GATE

**Run the campaign's additive batch first.** Every removal here has a replacement
named in `removals.md`, and the point of the ordering is that the replacement
already exists: a removal that lands first leaves a real officeholder with no
`P39` at all. This script refuses to guess whether that has happened, so the
check is yours — the `.qs` in the QuickStatements importer, then this.

Removals are the destructive half of the write path and are guarded accordingly:
dry by default, one statement per call so a failure stops at that statement, a
ledger (`removals_written.json`) so a re-run cannot turn an already-removed GUID
into an error storm, and every proposal skipped unless it names a replacement.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wd.api import fetch_entities
from wd.campaign import STATE_MAX_AGE
from wd.http import REPO_ROOT, make_session
from wd.write import Ledger, WriteError, log, remove_claim


def holds(session, people: list) -> dict:
    """Every `P39` value each person currently holds, read live.

    The replacement is named per *item* — "these all belong on the real central
    bank governorship" — but safety is a fact about a *person*: it is no comfort
    that some other holder has the right statement. Checked here rather than in
    `iq_removals.py` because the additive batch lands in between, so the only
    answer that counts is the one true at the moment of removal, and it must come
    from live state (`STATE_MAX_AGE`) and never the seven-day cache.

    This check refused 14 of 27 removals on its first run: six MPs whose Council
    of Representatives membership this campaign never covered, and eight
    municipal ministers whose office had no correct statement at all. Every one
    of them would have been left holding nothing for that office.
    """
    out = {}
    entities = fetch_entities(session, sorted(set(people)), max_age=STATE_MAX_AGE)
    for qid, entity in entities.items():
        out[qid] = {
            (claim["mainsnak"].get("datavalue") or {}).get("value", {}).get("id")
            for claim in entity.get("claims", {}).get("P39", [])
        }
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", required=True,
                        help="Subdirectory of data/ holding removals.json")
    parser.add_argument("--apply", action="store_true",
                        help="Actually remove; without it nothing is written")
    parser.add_argument("--limit", type=int, default=None,
                        help="Stop after this many statements")
    parser.add_argument("--force-unreplaced", action="store_true",
                        help="Also remove statements with no replacement named. "
                             "Leaves the holder with no P39 for that office.")
    args = parser.parse_args()

    out_dir = REPO_ROOT / "data" / args.campaign
    source = out_dir / "removals.json"
    if not source.exists():
        raise SystemExit(f"No {source} — run scripts/iq_removals.py first")

    removals = json.loads(source.read_text())["removals"]
    ledger = Ledger.load(out_dir / "removals_written.json")
    current = holds(make_session(), [row["person"] for row in removals])

    written = skipped = held = unsafe = 0
    for row in removals:
        if args.limit is not None and written >= args.limit:
            break
        ref = row["guid"]
        if ledger.qid(ref):
            held += 1
            continue
        if not row.get("replacement") and not args.force_unreplaced:
            print(f"  skip {row['person']} {row['person_label']!r} → "
                  f"{row['value']} ({row['value_label']}): no replacement named")
            skipped += 1
            continue
        if (row.get("replacement")
                and row["replacement"] not in current.get(row["person"], set())
                and not args.force_unreplaced):
            print(f"  REFUSED {row['person']} {row['person_label']!r} → "
                  f"{row['value']} ({row['value_label']}): this person does not "
                  f"hold the replacement {row['replacement']}, so removing would "
                  f"leave them with no P39 for the office")
            unsafe += 1
            continue
        summary = (
            f"remove P39 = {row['value']} ({row['value_label']}): "
            f"{row['reason']}, which cannot be held"
            + (f"; the office is {row['replacement']}"
               if row.get("replacement") else "")
        )
        try:
            did = remove_claim(ref, summary, ledger, ref, apply=args.apply)
        except WriteError as exc:
            print(f"  FAILED {ref} ({row['person_label']}): {exc}")
            break
        verb = "removed" if did else "would remove"
        print(f"  {verb} {row['person']} {row['person_label']!r} → "
              f"{row['value']} ({row['value_label']})")
        if did:
            written += 1
            log(out_dir / "applied.jsonl", {
                "action": "remove-claim", "guid": ref,
                "person": row["person"], "value": row["value"],
                "reason": row["reason"], "replacement": row.get("replacement"),
            })

    print(f"\n{len(removals)} proposed · {written} removed · {skipped} skipped "
          f"for want of a replacement · {unsafe} refused because the holder does "
          f"not have the replacement · {held} already done per the ledger")
    if not args.apply:
        print("Dry run — nothing was written. Re-run with --apply, "
              "after the additive batch is in.")


if __name__ == "__main__":
    main()
