#!/usr/bin/env python
"""Which PETScan queries can be deleted, accumulated as a PR checklist.

    python scripts/retirable.py [--limit N] [--key <spec key>]

Runs after `scripts/spec_report.py`, over the specs that pass its cheap pass:
those whose target is a position `wd_peps` emits today. For each, it builds the
real cohort and asks the only question that matters for deletion —

    is every member either already holding the office, or someone no PEP
    dataset would emit anyway?

`spec_report.py`'s `gap` cannot answer that, because it is measured before the
relevance gate. `Presidents_of_the_Senate_of_Spain` reads gap 3 and has nothing
to do: all three were born before 1920.

**The honest part.** Deleting a whole spec removes its `topic:` too, so people
it currently carries who are *not* emittable from their own statements drop out
of OpenSanctions. For a `removable` spec those are exactly the long-dead and the
pre-1920 — whom `wd_peps` declines by design, and whom no reading of FATF
guidance calls exposed. That is a correction rather than a loss, but it is a
dataset change and every row below states its size. It is the reviewer's call,
not this script's.

State accumulates in `coverage/petscan_retirable.json`: a spec keeps its
`first_measured` date, so the checklist is a growing record rather than a
snapshot that forgets. `coverage/petscan_retirable.md` is rendered from it.
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wd.cohort import build
from wd.http import REPO_ROOT, make_session
from wd.specs import load_specs

SPECS = REPO_ROOT / "data" / "enrich" / "specs.json"
STATE = REPO_ROOT / "coverage" / "petscan_retirable.json"
LEDGER = REPO_ROOT / "coverage" / "petscan_retirable.md"

#: Dispositions worth the deeper pass. Both mean "the target emits today"; they
#: differ only in whether the cheap pre-gate count saw a gap.
CANDIDATES = ("retirable", "enrich")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--key", action="append")
    parser.add_argument("--specs", type=Path, default=SPECS)
    args = parser.parse_args()

    if not args.specs.exists():
        raise SystemExit(f"run scripts/spec_report.py first — no {args.specs}")
    cheap = {r["key"]: r for r in json.loads(args.specs.read_text())}
    specs = {s.key: s for s in load_specs()}

    keys = [k for k, r in cheap.items() if r["disposition"] in CANDIDATES]
    if args.key:
        keys = [k for k in keys if k in set(args.key)]
    if args.limit:
        keys = keys[: args.limit]
    print(f"{len(keys)} specs whose target emits today", file=sys.stderr)

    state = {}
    if STATE.exists():
        state = {r["key"]: r for r in json.loads(STATE.read_text())}
    session = make_session()
    today = date.today().isoformat()

    for index, key in enumerate(sorted(keys), 1):
        spec = specs.get(key)
        if spec is None:
            continue
        try:
            cohort = build(session, spec)
        except Exception as exc:
            print(f"  [{index}/{len(keys)}] {key}: {exc}", file=sys.stderr)
            continue
        reasons = cohort.reasons()
        row = {
            "key": key,
            "category": spec.category,
            "language": spec.language,
            "target": spec.target,
            "target_label": cheap[key].get("target_label"),
            "position_name": spec.position_name,
            "members": len(cohort.members),
            "held": len(cohort.held),
            "todo": len(cohort.todo),
            "not_human": len(cohort.not_human),
            "dropped": reasons,
            # Everyone the spec currently carries who would not survive on their
            # own statements. Deleting the spec drops them from the dataset.
            "drops_from_dataset": sum(reasons.values()),
            "removable": not cohort.todo,
            "last_confirmed": today,
        }
        # A spec that has ever been removable keeps the date it first was, so
        # the checklist accumulates instead of forgetting.
        prior = state.get(key, {})
        row["first_measured"] = (
            (prior.get("first_measured") or today) if row["removable"] else None
        )
        state[key] = row
        flag = "REMOVABLE" if row["removable"] else ""
        print(f"  [{index}/{len(keys)}] {key[:56]:56} held={row['held']:>4} "
              f"todo={row['todo']:>4} drops={row['drops_from_dataset']:>4} {flag}",
              file=sys.stderr)

    rows = sorted(state.values(),
                  key=lambda r: (not r["removable"], -r["held"], r["key"]))
    STATE.write_text(json.dumps(rows, indent=1, ensure_ascii=False) + "\n")

    removable = [r for r in rows if r["removable"]]
    waiting = [r for r in rows if not r["removable"]]
    md = [
        "# PETScan queries that can be deleted",
        "",
        "The checklist for a PR against",
        "`opensanctions/datasets/_wikidata/categories/wd_categories.yml`. A query",
        "belongs here when its target is a position `wd_peps` emits **and** every",
        "member of its category either already holds that position or is someone no",
        "PEP dataset would emit anyway.",
        "",
        f"Maintained by `scripts/retirable.py`; {len(removable)} removable, "
        f"{len(waiting)} still carrying work. Rows accumulate — a spec keeps its",
        "`first measured` date, so this is a record rather than a snapshot.",
        "",
        "**What deletion costs.** Removing a whole spec removes its `topic:`, so the",
        "people in the `drops` column leave OpenSanctions: they are the long-dead and",
        "the pre-1920, whom `wd_peps` declines by design. That is a correction, not a",
        "regression — but it is a dataset change, and the number is stated per row so",
        "a reviewer can weigh it rather than discover it.",
        "",
        "## Removable",
        "",
        "| category | lang | members | hold it | drops | target | first measured |",
        "|---|---|---:|---:|---:|---|---|",
    ]
    for r in removable:
        md.append(
            f"| `{r['category']}` | {r['language']} | {r['members']} | {r['held']} "
            f"| {r['drops_from_dataset']} | {r['target']} {r['target_label'] or ''} "
            f"| {r['first_measured']} |"
        )
    md += [
        "",
        f"Total: **{len(removable)} queries**, "
        f"{sum(r['held'] for r in removable)} people already covered by real P39 "
        f"statements, {sum(r['drops_from_dataset'] for r in removable)} leaving the "
        "dataset.",
        "",
        "### The categories to delete",
        "",
        "```",
    ]
    md += [f"{r['language']}:{r['category']}" for r in removable]
    md += [
        "```",
        "",
        "## Still carrying work",
        "",
        "The target emits, but members are missing the statement. These are the",
        "enrichment loop's queue; each becomes removable when `todo` reaches zero.",
        "",
        "| category | lang | hold it | todo | target |",
        "|---|---|---:|---:|---|",
    ]
    for r in waiting:
        md.append(
            f"| `{r['category']}` | {r['language']} | {r['held']} | {r['todo']} "
            f"| {r['target']} {r['target_label'] or ''} |"
        )
    LEDGER.write_text("\n".join(md) + "\n")
    print(f"{len(removable)} removable, {len(waiting)} with work")
    print(f"Wrote {LEDGER} and {STATE}")


if __name__ == "__main__":
    main()
