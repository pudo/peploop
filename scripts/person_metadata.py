#!/usr/bin/env python
"""Audit the *holders* of a country's positions: modelling first, reader second.

The person-side sibling of `scripts/position_metadata.py`. Run it at phase A
beside that one, and again after a roster lane lands. It answers three separate
questions per person — is the item well modelled, which recommended properties
are missing, and what does the OpenSanctions PEP build make of it —
and `recipes/person_items.md` says what each one costs.

    python scripts/person_metadata.py --country Q794
    python scripts/person_metadata.py --country Q794 --limit 400
    python scripts/person_metadata.py --qids Q42,Q76 --calibrate

The candidate query is deliberately *wider* than the gates it measures: the
crawler finds holders with `?person wdt:P39 ?pos . ?person wdt:P31 wd:Q5`, so
asking the same thing here would hide every person that query misses — which is
one of the findings. This one reads `p:P39/ps:P39` and no type constraint, then
reports who the narrower query would never reach.
"""

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Set

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from wd.api import best_label, fetch_entities, sparql  # noqa: E402
from wd.shape import verify_all as verify_positions  # noqa: E402
from wd.http import make_session  # noqa: E402
from wd.human import Verdict, verify_all  # noqa: E402

#: WDQS via GET overflows the URI past roughly 150 `VALUES` items, and a
#: statement-node scan over more than this times out before it overflows.
POSITION_CHUNK = 80


def country_positions(session, country_qid: str) -> List[str]:
    """Position items the country owns, by the two claims that actually scope one.

    `wdt:` is right here and nowhere else in this script: this is candidate
    generation, and the gates below re-read every item's claims in full.
    """
    query = f"""
    SELECT DISTINCT ?position WHERE {{
      {{ ?position wdt:P17 wd:{country_qid} }}
      UNION
      {{ ?position wdt:P1001 wd:{country_qid} }}
      ?position wdt:P31/wdt:P279* wd:Q4164871 .
    }}
    """
    return sorted({row["position"] for row in sparql(session, query)})


def position_holders(session, positions: List[str]) -> Dict[str, Set[str]]:
    """Every person with a P39 to one of these positions, at any rank.

    Not `wdt:P39`: one preferred P39 statement hides all the normal-rank ones,
    so a holder whose main office is flagged preferred is invisible to a truthy
    read of their *other* offices. The crawler has that blind spot; an audit of
    the crawler must not share it.
    """
    out: Dict[str, Set[str]] = {}
    for i in range(0, len(positions), POSITION_CHUNK):
        chunk = positions[i : i + POSITION_CHUNK]
        values = " ".join(f"wd:{qid}" for qid in chunk)
        query = f"""
        SELECT ?person ?position WHERE {{
          VALUES ?position {{ {values} }}
          ?person p:P39/ps:P39 ?position .
        }}
        """
        for row in sparql(session, query):
            out.setdefault(row["person"], set()).add(row["position"])
    return out


def calibrate(verdicts: List[Verdict]) -> None:
    """Check each verdict against the live API, and say which way it disagreed.

    The only regression net this reader has. A verdict that says emitted and an
    API that says absent is usually the position layer — the person is fine and
    every office they hold has a modelling defect in `wd/shape.py` — so read that
    before suspecting a port bug here.
    """
    table: Counter = Counter()
    disagree: List[str] = []
    for verdict in verdicts:
        proc = subprocess.run(
            ["yente-cli", "fetch", verdict.qid, "-f", "json"],
            capture_output=True, text=True,
        )
        present = False
        if proc.returncode == 0 and proc.stdout.strip():
            try:
                present = json.loads(proc.stdout).get("schema") == "Person"
            except json.JSONDecodeError:
                present = False
        table[(verdict.emitted, present)] += 1
        if verdict.emitted != present:
            # The expected class, and the reason to read the notes before the
            # port: a position whose honest parent leaves the PEP default off,
            # rescued by the review database this repo cannot see.
            why = ("review layer, via a position this audit did not accept"
                   if "no_accepted_tenures" in verdict.os_notes
                   else "the position layer, then a port bug")
            disagree.append(
                f"  {verdict.qid:12} emitted={verdict.emitted} in_os={present}  "
                f"({why})  notes={verdict.os_notes}  {verdict.label}"
            )
    print("\n## Calibration")
    print(f"  agree           : {table[(True, True)] + table[(False, False)]}")
    print(f"  passes, absent  : {table[(True, False)]}")
    print(f"  fails, present  : {table[(False, True)]}")
    for line in disagree[:40]:
        print(line)
    if len(disagree) > 40:
        print(f"  … and {len(disagree) - 40} more")


def check_spec() -> int:
    """Fail if the recipe no longer enumerates every gate the code applies.

    The recipe restates constants that live in `wd/human.py`, which is the kind
    of duplication that rots quietly: a threshold changed upstream and ported
    here would leave the documented list wrong with nothing to notice it.
    """
    from wd import human

    recipe = (REPO_ROOT / "recipes" / "person_items.md").read_text()
    missing: List[str] = []
    qids = {
        "HUMAN_TYPE": {human.HUMAN_TYPE},
        "POSITION_TYPE": {human.POSITION_TYPE},
        "FICTIONAL_TYPE": {human.FICTIONAL_TYPE},
        "BLOCKED_PERSONS": human.BLOCKED_PERSONS,
        "COUNTRY_FALLBACKS": set(human.COUNTRY_FALLBACKS),
    }
    for name, values in qids.items():
        absent = sorted(v for v in values if v not in recipe)
        if absent:
            missing.append(f"  {name}: {absent}")
    windows = {
        "RELEVANCE_MIN": human.RELEVANCE_MIN,
        "MAX_AGE": f"{human.MAX_AGE.days // human.YEAR_DAYS}",
        "AFTER_DEATH": f"{human.AFTER_DEATH.days // human.YEAR_DAYS}",
        "MAX_OFFICE": f"{human.MAX_OFFICE.days // human.YEAR_DAYS}",
    }
    for name, value in windows.items():
        if value not in recipe:
            missing.append(f"  {name}: {value}")
    if missing:
        print("recipes/person_items.md is missing gates or thresholds:")
        print("\n".join(missing))
        return 1
    print("recipes/person_items.md enumerates every gate, class and threshold.")
    return 0


def report(verdicts: List[Verdict], out_dir: Path) -> None:
    """Print the three answers separately, and write every verdict out.

    Never one score. A person item can be flawlessly modelled and still absent
    from OpenSanctions, and the count that mixes the two is the one that sends a
    campaign to repair records that were never broken.
    """
    defects = Counter(d for v in verdicts for d in v.defects)
    gaps = Counter(g for v in verdicts for g in v.gaps)
    notes = Counter(n for v in verdicts for n in v.os_notes)
    tenures = [t for v in verdicts for t in v.tenures]
    dropped = Counter(t.dropped for t in tenures if t.dropped)

    print(f"  people             : {len(verdicts)}")
    print(f"  well modelled      : {sum(1 for v in verdicts if v.well_modelled)}"
          f"   complete: {sum(1 for v in verdicts if v.complete)}")
    print("\n### Modelling defects")
    for name, count in defects.most_common() or [("none", 0)]:
        print(f"  {name:22} {count}")

    print("\n### Gaps (recommended properties absent)")
    for name, count in gaps.most_common() or [("none", 0)]:
        print(f"  {name:22} {count}")

    print("\n### What OpenSanctions makes of them")
    print(f"  emitted as PEPs    : {sum(1 for v in verdicts if v.emitted)}")
    for name, count in notes.most_common():
        print(f"  {name:22} {count}")
    print(f"  P39 statements     : {len(tenures)}, "
          f"{sum(1 for t in tenures if t.emitted)} become occupancies")
    for name, count in dropped.most_common():
        print(f"    dropped {name:14} {count}")

    # The two halves of the birthdate lane, which is the one place a gap and a
    # note line up: one edit moves a person across, and the same edit missing is
    # what keeps the others out.
    print("\n### The birth-date hinge")
    print(f"  emitted only because a P569 is present : "
          f"{sum(1 for v in verdicts if v.dob_carries)}")
    print(f"  absent, and a P569 alone would fix it  : "
          f"{sum(1 for v in verdicts if v.dob_would_rescue)}")

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "person_metadata.jsonl"
    path.write_text("\n".join(json.dumps(v.as_dict()) for v in verdicts) + "\n")
    print(f"\n  wrote {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--country", help="country item, e.g. Q794")
    parser.add_argument("--qids", help="comma-separated person QIDs instead")
    parser.add_argument("--name", help="output slug; defaults to the country label")
    parser.add_argument("--limit", type=int, help="cap the candidate people")
    parser.add_argument("--strict", action="store_true",
                        help="model the categories crawler's gates, not wd_peps'")
    parser.add_argument("--calibrate", action="store_true",
                        help="check every verdict against a live yente-cli fetch")
    parser.add_argument("--check-spec", action="store_true",
                        help="assert recipes/person_items.md enumerates every gate")
    args = parser.parse_args()

    if args.check_spec:
        raise SystemExit(check_spec())
    if not args.country and not args.qids:
        parser.error("one of --country or --qids is required")

    session = make_session()
    topics: Dict[str, Set[str]] = {}
    accepted: Optional[Set[str]] = None
    slug = args.name

    if args.qids:
        people = [q.strip() for q in args.qids.split(",") if q.strip()]
        slug = slug or "adhoc"
    else:
        country = fetch_entities(session, [args.country]).get(args.country, {})
        label = best_label(country) or args.country
        slug = slug or label.lower().replace(" ", "-")
        positions = country_positions(session, args.country)
        accepted = set()
        print(f"## {label}: {len(positions)} position items")

        # The position layer decides two things about a person: whether their
        # tenure counts at all, and — through the office's topics — how long
        # after leaving it they stay a PEP. Judging a tenure without it reads
        # every ex-minister on the 5-year default and reports them dropped.
        for verdict in verify_positions(session, positions):
            topics[verdict.qid] = verdict.topics
            if not verdict.os_notes:
                accepted.add(verdict.qid)
        print(f"  readable by OS  : {len(accepted)}")

        holders = position_holders(session, positions)
        people = sorted(holders)
        print(f"  holders         : {len(people)}")
        if args.limit:
            people = people[: args.limit]
            print(f"  capped at       : {len(people)}  (--limit)")

    verdicts = verify_all(session, people, topics=topics, accepted=accepted,
                          strict=args.strict)
    report(verdicts, REPO_ROOT / "data" / "persons" / slug)

    if args.calibrate:
        calibrate(verdicts)


if __name__ == "__main__":
    main()
