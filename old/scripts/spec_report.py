#!/usr/bin/env python
"""What it would actually take to delete each PETScan category query.

    python scripts/spec_report.py [--limit N] [--key <spec key>] [--refresh]

`wd_categories.yml` mass-includes people as PEPs because their Wikidata items
lack the P39 that would find them properly. 284 of its 594 specs paper over that
with a synthetic position (`wd-cat` hash id, no Wikidata identity), and the goal
is to delete the query outright — not just its `position:` block — once the
people it catches are PEPs on their own Wikidata merits.

That makes retirement a stronger claim than "every member holds the target",
and this report exists to say which of four different things is actually in the
way. Read `disposition`:

* `retirable`  — the target is a position `wd_peps` emits and every member holds
                 it. Delete the spec.
* `enrich`     — same, but members are missing the statement. The enrichment
                 loop's work.
* `fix-item`   — the target carries a Wikidata modelling defect (`untyped`, no
                 real `P279`). Fix the item, then it becomes `enrich`.
* `os-policy`  — the target is well modelled and `wd_peps` still would not emit
                 it: `pep_default_off` (no PEP-conferring parent) or
                 `excluded_type`. **Keep the spec.** No amount of Wikidata
                 enrichment replaces it; it needs a decision in the
                 OpenSanctions position review, or a `SUB_TYPES` change upstream.
* `bucket` / `unresolved` / `broken-query` — no single target to verify against,
                 no `wikidata_id` yet, or a category that matches no page at all.

Writes the committed ledger `coverage/wd_categories.md` plus
`data/enrich/specs.json`. Measured counts are reused across runs unless
`--refresh`, so re-running is cheap. No LLM, no writes to Wikidata.
"""

import argparse
import json
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wd.cohort import size
from wd.http import REPO_ROOT, make_session
from wd.specs import BUCKET, load_specs

OUT_DIR = REPO_ROOT / "data" / "enrich"
#: Not `coverage/wd_categories.md` — that is the *target items*' ledger, written
#: by `scripts/audit_os_positions.py`. This one is the *queries*' ledger, and the
#: two compose: that file says whether an office can be emitted, this one says
#: how many of a category's members hold it.
LEDGER = REPO_ROOT / "coverage" / "petscan_specs.md"

#: Order the ledger and the summary read in: what to do first, first.
ORDER = [
    "retirable", "enrich", "fix-item", "os-policy",
    "bucket", "unresolved", "broken-query", "unaudited",
]

BLURB = {
    "retirable": (
        "The target is a position `wd_peps` emits, and every human member already "
        "holds it. **Delete these specs from `wd_categories.yml`.**"
    ),
    "enrich": (
        "The target is emittable and members are missing the statement. This is "
        "the enrichment loop's queue; `gap` is the upper bound before the cohort "
        "relevance gate."
    ),
    "fix-item": (
        "The target carries a Wikidata modelling defect, so `wd_peps` skips it "
        "however good the P39s are. Fix the item first (`recipes/position_items.md`), "
        "then the spec becomes `enrich`."
    ),
    "os-policy": (
        "**Keep these specs.** The target is well-modelled Wikidata that "
        "`wd_peps` still declines: `pep_default_off` means no PEP-conferring "
        "parent in `zavod`'s `SUB_TYPES`, `excluded_type` means the type closure "
        "reaches an award or title of honour with nothing to rescue it. Enriching "
        "Wikidata cannot retire these — they need a decision in the OpenSanctions "
        "position review, or a `SUB_TYPES` change upstream. This is the class the "
        "PETScan workaround genuinely exists for."
    ),
    "bucket": (
        "The position names a *class* of offices, not one seat, so there is no "
        "single item to verify against. Needs the per-person gazetteer pass."
    ),
    "unresolved": (
        "No `wikidata_id` resolved yet — see `tasks/category_positions.md`."
    ),
    "broken-query": (
        "The category matches no page at all: a wrong wiki, or a title whose case "
        "is wrong after the first letter. `scripts/category_langcheck.py` found "
        "these. The fix is the query, not the position — and until it is fixed the "
        "spec contributes nobody, so it cannot be called retirable."
    ),
    "unaudited": (
        "The target item is not in the audit passed via `--os-audit`, so whether "
        "`wd_peps` would emit it is unknown. Re-run "
        "`scripts/audit_os_positions.py --json` and pass it."
    ),
}


#: `scripts/audit_os_positions.py`'s `lever` — the one thing that would make a
#: target item discoverable — mapped onto what it means for the *query*.
LEVERS = {
    "": None,                  # emits today; the gap decides
    "surgical": "fix-item",    # two things at once, or not an office
    "no_polity": "fix-item",
    "igo_link": "fix-item",    # additive, and the highest-value lane there
    "untyped": "fix-item",
    "upstream": "os-policy",   # correct Wikidata, non-conferring `SUB_TYPES`
    "review": "os-policy",     # enters the OS review UI undecided
}


def disposition(spec, counts: dict, target: dict) -> str:
    """Which obstacle is in the way of deleting this query, or none.

    `target` is a row from `scripts/audit_os_positions.py --json`, which replays
    `zavod/shed/wikidata/position.py`'s own gates in their own order. Do not
    substitute `wd/shape.py` here: its `excluded_by` is documented unreliable
    (`coverage/wd_categories.md` — `type_targets` keeps deprecated claims where
    nomenklatura drops them, and `CLOSURE_CACHE` is lossy, and the two errors
    cancel), so an emit/no-emit call taken from it is a coin toss with a
    plausible face.
    """
    if spec.granularity == BUCKET:
        return "bucket"
    if not spec.target:
        return "unresolved"
    if not counts.get("members"):
        return "broken-query"
    if not target:
        return "unaudited"
    if target.get("status") != "ok":
        return "fix-item"
    blocked = LEVERS.get(target.get("lever", ""), "os-policy")
    if blocked:
        return blocked
    return "retirable" if not counts.get("gap") else "enrich"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, help="size only the first N specs")
    parser.add_argument("--key", action="append", help="only these spec keys")
    parser.add_argument("--refresh", action="store_true",
                        help="re-measure specs already in specs.json")
    parser.add_argument("--os-audit", type=Path,
                        default=REPO_ROOT / "data" / "os_positions" / "audit.json",
                        help="scripts/audit_os_positions.py --json output; it "
                             "owns the emit/no-emit call")
    args = parser.parse_args()

    specs = load_specs()
    if args.key:
        specs = [s for s in specs if s.key in set(args.key)]
    if args.limit:
        specs = specs[: args.limit]

    session = make_session()

    # Resume, the way every other pass here does: a measured spec is not
    # re-measured, so growing the report costs only what is new.
    known: dict = {}
    cache = OUT_DIR / "specs.json"
    if cache.exists() and not args.refresh:
        for row in json.loads(cache.read_text()):
            known[row["key"]] = row

    # The emit/no-emit call comes from the position audit, not from here. It is
    # the measurement that separates `os-policy` from `enrich`, and it is the
    # difference between a retirement plan and a wish.
    audited: dict = {}
    if args.os_audit and args.os_audit.exists():
        for row in json.loads(args.os_audit.read_text()):
            audited[row["qid"]] = row
        print(f"read {len(audited)} audited targets from {args.os_audit}",
              file=sys.stderr)
    else:
        print(f"no target audit at {args.os_audit} — every spec will read "
              "`unaudited`. Run scripts/audit_os_positions.py --json first.",
              file=sys.stderr)

    rows = []
    for index, spec in enumerate(specs, 1):
        prior = known.get(spec.key, {})
        counts = {k: prior[k] for k in ("members", "human", "held", "gap")
                  if k in prior}
        if len(counts) != 4 and spec.granularity != BUCKET:
            try:
                counts = size(session, spec)
            except Exception as exc:      # one bad spec must not end the sweep
                print(f"  [{index}/{len(specs)}] {spec.key}: {exc}", file=sys.stderr)
                counts = {"members": 0, "human": 0, "held": 0, "gap": 0,
                          "error": str(exc)[:120]}
        counts = {**{"members": 0, "human": 0, "held": 0, "gap": 0}, **counts}
        target = audited.get(spec.target or "", {})
        verdict = disposition(spec, counts, target)
        rows.append({
            **{k: v for k, v in asdict(spec).items() if k != "negcats"},
            **counts,
            "target_label": target.get("label"),
            "target_lever": target.get("lever"),
            "target_cohort": target.get("cohort"),
            "target_defects": target.get("defects", []),
            "disposition": verdict,
        })
        print(f"  [{index}/{len(specs)}] {spec.key[:54]:54} "
              f"members={counts['members']:>5} held={counts['held']:>5} "
              f"gap={counts['gap']:>5} {verdict}", file=sys.stderr)

    rows.sort(key=lambda r: (ORDER.index(r["disposition"]), r["gap"], -r["held"]))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(rows, indent=1, ensure_ascii=False) + "\n")

    grouped: dict = {}
    for row in rows:
        grouped.setdefault(row["disposition"], []).append(row)

    md = [
        "# Retiring the PETScan category queries",
        "",
        f"Measured {date.today().isoformat()} by `scripts/spec_report.py`. "
        f"{len(rows)} of the 594 specs in `wd_categories.yml` carry a synthetic",
        "`position:` block; this is what it would take to **delete each query**.",
        "",
        "The crawler applies a spec's `topic:` to its members independently of the",
        "`position:` block, so deleting a whole spec removes the PEP topic, the",
        "country and the synthetic occupancy together. The replacement therefore has",
        "to be `wd_peps` emitting those people from their own statements — which is a",
        "stronger condition than every member holding the target, and the reason this",
        "report audits the *target item* as well as the members.",
        "",
        "| disposition | specs | people in the gap |",
        "|---|---:|---:|",
    ]
    for name in ORDER:
        group = grouped.get(name, [])
        if group:
            md.append(f"| `{name}` | {len(group)} | {sum(r['gap'] for r in group)} |")
    md += [
        "",
        "**Only the first two rows are reachable by enriching Wikidata.** `os-policy`",
        "is the class the workaround genuinely exists for, and it does not shrink no",
        "matter how many P39 statements this workbench writes.",
        "",
    ]
    for name in ORDER:
        group = grouped.get(name, [])
        if not group:
            continue
        md += [f"## `{name}` ({len(group)} specs)", "", BLURB[name], ""]
        md += ["| category | lang | members | holds | gap | target | why |",
               "|---|---|---:|---:|---:|---|---|"]
        for r in group:
            why = ", ".join(
                filter(None, [r.get("target_lever")] + list(r["target_defects"]))
            )
            target = f"{r['target']} {r['target_label'] or ''}".strip()
            md.append(
                f"| `{r['category']}` | {r['language']} | {r['human']} | "
                f"{r['held']} | {r['gap']} | {target} | {why} |"
            )
        md.append("")

    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text("\n".join(md) + "\n")
    print(" ".join(f"{k}={len(grouped.get(k, []))}" for k in ORDER))
    print(f"Wrote {LEDGER} and {cache}")


if __name__ == "__main__":
    main()
