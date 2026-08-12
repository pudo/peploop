#!/usr/bin/env python
"""Compare a campaign's verdicts against the committed regression baseline.

    python scripts/diff_verdicts.py --campaign czechia
    python scripts/diff_verdicts.py --campaign ecuador --rename minister_=ecuador_

The engine is changed often, and `recipes/country_sweep.md` requires re-running
the earlier countries and diffing before anything ships. A byte diff cannot do
that job: the record schema itself changes, files get renamed when an office key
changes, and JSON key order is not guaranteed. This compares what the records
*mean* — which (person, position) pairs exist, and what was decided about each —
so a refactor that rewrites every field can still prove it changed no decisions.

The baseline lives in `regression/`, deliberately outside the gitignored `data/`
directory: those verdicts are the only record of prior behaviour, and one
`rm -rf data/` would otherwise make every later change unverifiable.
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wd.http import REPO_ROOT

BASELINE_DIR = REPO_ROOT / "regression"
DATA_DIR = REPO_ROOT / "data"

#: A record's identity for comparison. Deliberately *not* the terms: a changed
#: date on an existing pair is the interesting case, and keying on it would
#: report one deletion plus one addition instead.
Key = Tuple[str, str]


def _dated(terms: List[Tuple[Optional[str], Optional[str]]]) -> list:
    """Drop wholly undated spans.

    v1 recorded "no term information" as an empty list; v2 records it as one
    statement carrying no date qualifiers, which is the more truthful shape —
    an undated P39 is still a statement. They mean the same thing.
    """
    return [t for t in terms if t[0] or t[1]]


def normalise(record: dict) -> dict:
    """One record in the shape this differ compares, whatever schema it is in.

    Records written before the v2 schema carry a single `era` string and a
    top-level verdict; v2 carries a flag list and an explicit decision. Both
    reduce to the same question — what was decided, about which statement, on
    what dates — so a schema migration shows up as an empty diff rather than as
    every record having changed.
    """
    if record.get("schema", 1) >= 2:
        statements = record.get("statements") or [{}]
        terms = []
        extras: List[str] = []
        for statement in statements:
            bounds = {
                q["property"]: q["value"].get("iso")
                for q in statement.get("qualifiers", [])
            }
            terms.append((bounds.get("P580"), bounds.get("P582")))
            # Every qualifier that is not a date, because those are decisions
            # too: whether a spell carries `P2868 = Q4676846` is exactly the kind
            # of change this differ exists to catch, and comparing only P580/P582
            # let it through silently.
            extras += [
                f"{q['property']}={(q['value'] or {}).get('id') or (q['value'] or {}).get('iso')}"
                for q in statement.get("qualifiers", [])
                if q["property"] not in ("P580", "P582")
            ]
        decision = record.get("decision", {})
        flags = sorted(record.get("flags") or [])
        return {
            "qid": (record.get("subject") or {}).get("qid", "?"),
            "label": (record.get("subject") or {}).get("label", ""),
            "position": (statements[0].get("value") or {}).get("id", "-"),
            "outcome": decision.get("action", "?"),
            # The *case*, not the rule that judged it. Comparing rule ids would
            # make every policy change read as a wholesale rewrite; comparing
            # flags asks the question that matters — did the same case get the
            # same outcome?
            "reason": ",".join(flags) or decision.get("rule", ""),
            "terms": _dated(terms),
            "flags": flags,
            "qualifiers": sorted(set(extras)),
        }
    # v1 has no explicit decision. `add` + `modern` is what reached the .qs;
    # `add` on any other era is a statement the engine believed but the era
    # gate held, which is what `hold` means in v2.
    verdict, era = record.get("verdict", "?"), record.get("era", "")
    outcome = {"add": "hold", "unclear": "review"}.get(verdict, verdict)
    if verdict == "add" and era == "modern":
        outcome = "apply"
    return {
        "qid": record.get("qid", "?"),
        "label": record.get("label", ""),
        "position": record.get("position") or "-",
        "outcome": outcome,
        "reason": era,
        "terms": _dated([(t.get("start"), t.get("end")) for t in record.get("terms") or []]),
        "flags": [era] if era else [],
    }


def load(directory: Path, rename: List[Tuple[str, str]]) -> Tuple[Dict[Key, List[dict]], Dict[str, int]]:
    """Every verdict under `directory`, keyed by (person, position).

    `rename` rewrites filename prefixes so an office key change reads as a moved
    file rather than as a wholesale delete-and-add.
    """
    records: Dict[Key, List[dict]] = defaultdict(list)
    per_file: Dict[str, int] = {}
    for path in sorted(directory.glob("*.jsonl")):
        name = path.name
        for old, new in rename:
            if name.startswith(old):
                name = new + name[len(old):]
        count = 0
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            record = normalise(json.loads(line))
            records[(record["qid"], record["position"])].append(record)
            count += 1
        per_file[name] = count
    return records, per_file


def describe(record: dict) -> str:
    terms = ", ".join(
        f"{start or '?'}–{end or ''}" for start, end in record["terms"]
    ) or "no dates"
    extras = record.get("qualifiers") or []
    return (
        f"{record['outcome']}/{record['reason']} [{terms}]"
        + (f" {{{', '.join(extras)}}}" if extras else "")
    )


def compare(
    baseline: Dict[Key, List[dict]], current: Dict[Key, List[dict]], limit: int
) -> int:
    """Print the differences; return the number of pairs that changed."""
    gone = sorted(set(baseline) - set(current))
    new = sorted(set(current) - set(baseline))
    changed: List[Tuple[Key, List[dict], List[dict]]] = []
    for key in sorted(set(baseline) & set(current)):
        before = sorted(describe(r) for r in baseline[key])
        after = sorted(describe(r) for r in current[key])
        if before != after:
            changed.append((key, baseline[key], current[key]))

    for title, keys, source in (
        ("ONLY IN BASELINE (disappeared)", gone, baseline),
        ("ONLY IN CURRENT (appeared)", new, current),
    ):
        if not keys:
            continue
        print(f"\n### {title}: {len(keys)}")
        tally = Counter(
            f"{r['outcome']}/{r['reason']}" for key in keys for r in source[key]
        )
        print(f"    {dict(tally)}")
        for key in keys[:limit]:
            for record in source[key]:
                print(f"    {key[0]:<12} {record['label'][:26]:<26} {key[1]:<12} {describe(record)}")
        if len(keys) > limit:
            print(f"    … {len(keys) - limit} more")

    if changed:
        print(f"\n### CHANGED: {len(changed)} pairs")
        for key, before, after in changed[:limit]:
            print(f"    {key[0]:<12} {before[0]['label'][:26]:<26} {key[1]}")
            for record in before:
                print(f"        - {describe(record)}")
            for record in after:
                print(f"        + {describe(record)}")
        if len(changed) > limit:
            print(f"    … {len(changed) - limit} more")

    return len(gone) + len(new) + len(changed)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", required=True)
    parser.add_argument(
        "--rename", action="append", default=[],
        help="Filename prefix rewrite, old=new — for when an office key changes",
    )
    parser.add_argument("--baseline", type=Path, default=None)
    parser.add_argument("--current", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument(
        "--update", action="store_true",
        help="Overwrite the baseline with the current run once the diff is understood",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Allow --update to overwrite a baseline whose diff is not empty",
    )
    args = parser.parse_args()

    baseline_dir = args.baseline or BASELINE_DIR / args.campaign
    current_dir = args.current or DATA_DIR / args.campaign / "verdicts"
    if not baseline_dir.is_dir():
        raise SystemExit(f"No baseline at {baseline_dir}")
    if not current_dir.is_dir():
        raise SystemExit(f"No verdicts at {current_dir} — run the campaign first")

    rename = [tuple(r.split("=", 1)) for r in args.rename]  # type: ignore[misc]
    baseline, baseline_files = load(baseline_dir, rename)
    current, current_files = load(current_dir, rename)

    print(f"# {args.campaign}: baseline {sum(baseline_files.values())} records "
          f"in {len(baseline_files)} files → current {sum(current_files.values())} "
          f"in {len(current_files)} files")

    # A file present in the baseline but not in the run is how a stale verdict
    # file hides: the renderer globs the directory, so an office key that was
    # renamed leaves its old output behind to be read forever.
    orphans = sorted(set(baseline_files) - set(current_files))
    missing = sorted(set(current_files) - set(baseline_files))
    if orphans:
        print(f"\n### BASELINE FILES NOT WRITTEN BY THIS RUN: {orphans}")
        print("    (a renamed office key, or an office that produced nothing — "
              "if renamed, pass --rename old_=new_)")
    if missing:
        print(f"\n### FILES NEW IN THIS RUN: {missing}")

    changes = compare(baseline, current, args.limit)

    print()
    for name, records in (("baseline", baseline), ("current", current)):
        tally = Counter(f"{r['outcome']}/{r['reason']}" for rs in records.values() for r in rs)
        print(f"{name:<9} {sum(tally.values()):>4} records: {dict(tally.most_common())}")

    if changes == 0 and not orphans and not missing:
        print("\nNo semantic change.")
    else:
        print(f"\n{changes} pair(s) differ.")

    if args.update:
        # A baseline is only worth having if refreshing it is a decision. It used
        # to overwrite whatever the diff said, which turns "the regression net"
        # into "a copy of the last run".
        if (changes or orphans or missing) and not args.force:
            raise SystemExit(
                "Refusing to update a baseline over a non-empty diff — read the "
                "differences above, then pass --force if they are intended."
            )
        for path in baseline_dir.glob("*.jsonl"):
            path.unlink()
        for path in current_dir.glob("*.jsonl"):
            (baseline_dir / path.name).write_text(path.read_text())
        # The committed `.qs` and the manifest are part of the baseline too;
        # leaving them behind let them drift a whole campaign out of date.
        for name in ("manifest.json",):
            source = current_dir / name
            if source.exists():
                (baseline_dir / name).write_text(source.read_text())
        rendered = current_dir.parent / "edit_plan.qs"
        if rendered.exists():
            (baseline_dir / "edit_plan.qs").write_text(rendered.read_text())
        print(f"Baseline updated from {current_dir}")


if __name__ == "__main__":
    main()
