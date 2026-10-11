#!/usr/bin/env python
"""Write the statements QuickStatements cannot express, through the API.

    python scripts/apply_claims.py --campaign kuwait          # dry, prints each edit
    python scripts/apply_claims.py --campaign kuwait --apply

Reads `data/<campaign>/edit_plan_claims.json`, which `render_edit_plan.py` fills
with exactly one kind of thing: a person holding **several tenures in one
office**. QuickStatements matches an incoming line on subject, property and
value alone and merges its qualifiers into the statement it finds, so two lines
for two spells become one P39 carrying both starts and both ends — unreadable,
and already live on Wikidata from the Ecuador batch (Q1368615 holds one
ministerial statement whose starts are fourteen years apart). The API creates
every claim it is given, which is why these come here instead.

That difference cuts both ways, and it is why this script is the more dangerous
of the two paths:

* **Nothing de-duplicates.** Run it twice without the ledger and every tenure
  exists twice. `data/<campaign>/claims_written.json` is keyed by the person and
  the exact claim signature, so a second run is a no-op.
* **It is not one revertable batch.** A QuickStatements batch appears in
  EditGroups and can be rolled back whole; these are ordinary edits, one per
  person. `data/<campaign>/applied.jsonl` is the record to undo them from.
* **Dry by default**, so the payload is read before it is sent.

Review `edit_plan.qs` and this file as one deliverable: they are two halves of a
single campaign's batch, and the split is a property of the write path rather
than of the evidence.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wd.http import REPO_ROOT
from wd.write import Ledger, WriteError, edit_entity, log

DATA_DIR = REPO_ROOT / "data"


def signature(payload: dict) -> str:
    """A stable ref for the ledger: the person plus every claim being written.

    Keyed on the claims themselves rather than on the person, so re-rendering a
    campaign that gained a *third* tenure for someone writes the new set rather
    than silently skipping them as already done.
    """
    return json.dumps(
        {"id": payload["id"], "claims": payload["claims"]},
        ensure_ascii=False, sort_keys=True,
    )


def describe(payload: dict) -> str:
    parts = []
    for prop, claims in sorted(payload["claims"].items()):
        for claim in claims:
            bounds = claim.get("qualifiers", {})
            span = "–".join(
                str(bounds[key]["time"]) if isinstance(bounds.get(key), dict)
                else str(bounds.get(key, ""))
                for key in ("P580", "P582")
            )
            parts.append(f"{prop}={claim['value']} [{span.strip('–') or 'no dates'}]")
    return "; ".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", required=True, help="Subdirectory of data/")
    parser.add_argument("--apply", action="store_true",
                        help="Actually write (default is a dry run)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Write at most this many people, for a first pass")
    args = parser.parse_args()

    campaign_dir = DATA_DIR / args.campaign
    claims_path = campaign_dir / "edit_plan_claims.json"
    if not claims_path.exists():
        raise SystemExit(
            f"No {claims_path} — either the campaign has no multi-tenure people "
            "or render_edit_plan.py has not been run"
        )

    payloads = json.loads(claims_path.read_text())
    ledger = Ledger.load(campaign_dir / "claims_written.json")
    log_path = campaign_dir / "applied.jsonl"
    summary = f"{args.campaign} campaign: tenures QuickStatements cannot express"

    written = skipped = failed = 0
    for payload in payloads[: args.limit]:
        label = payload.get("label") or payload["id"]
        ref = signature(payload)
        if ledger.qid(ref):
            skipped += 1
            continue
        body = {"id": payload["id"], "claims": payload["claims"]}
        try:
            did = edit_entity(body, summary, ledger, ref, apply=args.apply)
        except WriteError as exc:
            failed += 1
            print(f"✗ {payload['id']} {label}: {exc}")
            continue
        if did:
            written += 1
            log(log_path, {"qid": payload["id"], "payload": body})
            print(f"✓ {payload['id']} {label} — {describe(payload)}")
        else:
            print(f"· would write {payload['id']} {label} — {describe(payload)}")

    verb = "wrote" if args.apply else "would write"
    print(f"\n{verb} {written if args.apply else len(payloads[:args.limit]) - skipped} "
          f"people, {skipped} already in the ledger, {failed} failed")
    if not args.apply:
        print("Dry run — pass --apply to write.")


if __name__ == "__main__":
    main()
