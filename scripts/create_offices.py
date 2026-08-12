#!/usr/bin/env python
"""Create the position items a campaign's offices are missing.

    python scripts/create_offices.py --country cz            # dry run
    python scripts/create_offices.py --country cz --apply

An office declared with an `archetype` instead of a `target` has no item on
Wikidata, so every one of its holders is unwritable — the Czech run found 45
supreme-court judges in exactly that state, and recorded them as a byproduct
list nobody worked through. This mints the item, records it in the campaign's
ledger, and prints the `target=` line to paste back into the country script,
after which the office runs like any other.

Dry by default. Creation is the least reversible thing the workbench does, so
a spec must clear `wd.create.guard` — a duplicate search plus a floor on
attested holders — before `--apply` will write anything.
"""

import argparse
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wd.api import best_label, fetch_entities
from wd.campaign import office_rows
from wd.create import CreateSpec, guard, payload, summary
from wd.http import make_session
from wd.petscan import category_members
from wd.positions import lookup_position
from wd.write import Ledger, create_entity, log

#: Country code → the module holding its `CAMPAIGN`.
SCRIPTS = {
    "cz": "cz_ministers",
    "by": "by_ministers",
    "ec": "ec_ministers",
    "es": "es_offices",
    "ae": "ae_offices",
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--country", required=True, choices=sorted(SCRIPTS))
    parser.add_argument("--office", nargs="*", default=None)
    parser.add_argument(
        "--apply", action="store_true",
        help="actually create the items (default is a dry run)",
    )
    args = parser.parse_args()

    module = importlib.import_module(SCRIPTS[args.country])
    campaign = module.CAMPAIGN
    out_dir = module.OUT_DIR
    session = make_session()
    ledger = Ledger.load(out_dir / "created.json")

    pending = [
        o for o in campaign.offices
        if not o.target and o.archetype
        and (args.office is None or o.key in args.office)
    ]
    if not pending:
        print(f"No office in {campaign.name} is awaiting creation.")
        return

    for office in pending:
        ref = f"{campaign.name}:{office.key}"
        rows, _skipped, sources = office_rows(session, office)
        # What attests the office exists is whoever is documented as holding
        # it, and that is not always a roster: the two Czech supreme courts
        # have no list article, only a category of 25 and 20 judges. Count both
        # channels, and cite whichever supplied the evidence.
        members = set()
        for lang, category in office.categories:
            try:
                members |= {qid for qid, _ in category_members(session, category, lang)}
            except Exception as exc:  # noqa: BLE001 — a missing category is data
                print(f"   ! {lang}:{category}: {exc}")
        starts = sorted(r.start for r in rows if r.start)
        attested = office.rosters[0].page if rows and office.rosters else (
            ", ".join(f"{lang}:{cat}" for lang, cat in office.categories)
        )
        spec = CreateSpec(
            ref=ref,
            archetype=office.archetype,
            labels=dict(office.create_labels),
            country_qid=campaign.country_qid,
            body=office.body,
            inception=starts[0] if starts else None,
            attested_by=attested,
            holders=max(len(rows), len(members)),
        )
        problems = guard(
            spec,
            lambda name, country: _existing(session, name, args.country),
            label_of=lambda qid: _label(session, qid),
        )
        print(f"\n## {office.label}  ({ref})")
        print(f"   {len(rows)} roster rows"
              + (f", earliest {starts[0]}" if starts else "")
              + (f", roster {sources[0]}" if sources else ""))
        if problems:
            print("   SKIPPED — " + "; ".join(problems))
            continue

        body = payload(spec)
        print(f"   labels: {body['labels']}")
        print(f"   claims: {body['claims']}")
        qid = create_entity(body, summary(spec), ledger, ref, apply=args.apply)
        if qid:
            print(f"   created {qid} — set target=\"{qid}\" on office "
                  f"{office.key!r} in scripts/{SCRIPTS[args.country]}.py")
            log(out_dir / "applied.jsonl", {
                "ref": ref, "qid": qid, "payload": body,
            })
        else:
            print("   dry run OK — re-run with --apply to create")


def _existing(session, name: str, country: str):
    """A QID already carrying this office's name, if one does."""
    found = lookup_position(session, name, country)
    return found.resolved_qid if found.status == "matched" else None


def _label(session, qid: str):
    entity = fetch_entities(session, [qid], props="labels").get(qid)
    return best_label(entity) if entity else None


if __name__ == "__main__":
    main()
