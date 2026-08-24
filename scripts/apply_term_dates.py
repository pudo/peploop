#!/usr/bin/env python
"""Date a P39 from the parliamentary term it already names.

    python scripts/apply_term_dates.py --campaign enrich/pl_...        # dry
    python scripts/apply_term_dates.py --campaign enrich/pl_... --apply

Reads `datable_from_term.json`, which `scripts/apply_replacements.py` writes for
the statements it **refused to touch**. Those are the good case: a `P39` with no
`P580`/`P582` but qualified `P2937` with a parliamentary term whose own item is
dated. The statement is not undated at all — it is dated by reference, and until
someone writes the dates on it `zavod` refuses an Occupancy and the person is not
a PEP.

Eleven of Poland's fourteen were this, so the cheap additive fix covers most of
what looked like a removal problem.

Why `wb add-qualifier` and not `wb edit-entity`:

* `wbeditentity` **replaces** a statement's data with what you send, so a payload
  carrying only the dates would wipe the `P2937` and `P4100` already on it.
  `wbsetqualifier` can only add.
* It targets the statement by **GUID**. QuickStatements would also work here
  (all eleven have exactly one Sejm statement, so its subject-property-value
  match is unambiguous), but exact beats unambiguous, and this keeps the whole
  operation in one process.

The cost of that choice is that a start and an end are two edits rather than one.
Benign — a statement with a start and no end is still better than one with
neither — and the reason this is not the tool for a split.

Guards: the item is re-read before **every** call, the qualifier must still be
absent, `--baserevid` is passed fresh each time, dry by default, and a ledger
keyed per statement-and-property so a re-run cannot append a second start date.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wd.api import fetch_entities
from wd.http import REPO_ROOT, make_session
from wd.write import Ledger, WriteError, add_qualifier, log


def statement(entity: dict, guid: str) -> dict | None:
    for claim in (entity.get("claims") or {}).get("P39", []):
        if claim.get("id") == guid:
            return claim
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    base = REPO_ROOT / "data" / args.campaign
    source = base / "datable_from_term.json"
    if not source.exists():
        raise SystemExit(f"no {source} — run scripts/apply_replacements.py first")
    rows = json.loads(source.read_text())[: args.limit]
    session = make_session()
    ledger = Ledger.load(base / "term_dates_written.json")
    print(f"{len(rows)} statements datable from their own term\n")

    written = skipped = failed = 0
    for row in rows:
        qid, guid = row["qid"], row["guid"]
        wanted = [(prop, row[key]) for prop, key in (("P580", "start"), ("P582", "end"))
                  if row.get(key)]
        for prop, value in wanted:
            ref = f"{guid}:{prop}"
            # Fresh every time: the previous call bumped the revision, and the
            # qualifier being absent is the whole precondition.
            entity = fetch_entities(session, [qid], max_age=0).get(qid) or {}
            claim = statement(entity, guid)
            if claim is None:
                print(f"  · {qid} {prop}: statement {guid} is gone")
                skipped += 1
                continue
            if prop in (claim.get("qualifiers") or {}):
                print(f"  · {qid} {prop}: already present")
                skipped += 1
                continue
            if not args.apply:
                print(f"  → would add {prop}={value} to {guid} "
                      f"(baserevid {entity.get('lastrevid')})")
                continue
            try:
                done = add_qualifier(
                    guid, prop, value,
                    summary=("date a [[Property:P39]] statement from the "
                             "[[Property:P2937]] term it already names"),
                    ledger=ledger, ref=ref, apply=True,
                    baserevid=entity.get("lastrevid"),
                )
            except WriteError as exc:
                failed += 1
                print(f"  ! {qid} {prop}: {exc}")
                continue
            if done:
                written += 1
                print(f"  ✓ {qid} {prop}={value}")
                log(base / "applied.jsonl", {
                    "script": "apply_term_dates", "qid": qid, "guid": guid,
                    "property": prop, "value": value,
                    "baserevid": entity.get("lastrevid"),
                })
    if not args.apply:
        print("\nDry run — pass --apply to write.")
        return
    print(f"\nwrote {written} qualifiers, {skipped} skipped, {failed} failed")


if __name__ == "__main__":
    main()
