#!/usr/bin/env python
"""Aggregate jurisdiction-classification verdicts into a reviewable fix plan.

    python scripts/render_jurisdiction_plan.py

Reads data/jurisdictions/verdicts/chunk_*.jsonl and writes:
  data/jurisdictions/fix_plan.md   - full breakdown for human review
  data/jurisdictions/fix_plan.qs   - P1001/P17 statements for fix-current
                                     verdicts at high confidence
Lower-confidence and fix-historical rows stay in the .md only. The country
inference comes from the position's own label, so statements go out
unreferenced (like most structural P1001s on Wikidata).
"""

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wd.http import REPO_ROOT

BASE = REPO_ROOT / "data" / "jurisdictions"


def main() -> None:
    verdicts = []
    for path in sorted(BASE.glob("verdicts/chunk_*.jsonl")):
        for line in path.read_text().splitlines():
            if line.strip():
                verdicts.append(json.loads(line))

    # Holder counts from the census give the review list its sort order:
    holders = {
        p["qid"]: p["holders"]
        for p in json.loads((BASE / "label_country_candidates.json").read_text())
    }
    for v in verdicts:
        v["holders"] = holders.get(v["qid"], 0)

    by_verdict = Counter(v["verdict"] for v in verdicts)
    md = ["# Jurisdiction fix plan", "", f"verdicts: {dict(by_verdict)}", ""]
    qs = []

    fix_current = sorted(
        (v for v in verdicts if v["verdict"] == "fix-current"),
        key=lambda v: -v["holders"],
    )
    md.append("## fix-current")
    for v in fix_current:
        line = (
            f"* {v['qid']} **{v['label']}** → {v['prop']} "
            f"{v['country_qid']} ({v.get('country_code')}) — {v['holders']} holders, "
            f"{v.get('kind')}, {v['confidence']}: {v.get('reason')}"
        )
        # Diplomatic posts stay out of the auto-batch: the classifiers were
        # not consistent on sender vs receiver for sender-named posts, so the
        # convention gets decided once, in review.
        if v.get("kind") == "diplomatic":
            line += "  ⟵ NOT in .qs (diplomatic: sender/receiver review)"
        elif v["confidence"] != "high":
            line += "  ⟵ NOT in .qs (confidence)"
        else:
            qs.append(f"{v['qid']}\t{v['prop']}\t{v['country_qid']}")
        md.append(line)

    for bucket in ("fix-historical", "unclear"):
        rows = sorted(
            (v for v in verdicts if v["verdict"] == bucket),
            key=lambda v: -v["holders"],
        )
        md.append(f"\n## {bucket}")
        for v in rows:
            md.append(
                f"* {v['qid']} {v['label']} — {v['holders']} holders: {v.get('reason')}"
            )

    skips = Counter(
        (v.get("kind") or "?") for v in verdicts if v["verdict"] == "skip"
    )
    md.append(f"\n## skip ({by_verdict.get('skip', 0)}, by kind: {dict(skips)})")

    (BASE / "fix_plan.md").write_text("\n".join(md) + "\n")
    (BASE / "fix_plan.qs").write_text("\n".join(qs) + "\n")
    high = sum(1 for v in fix_current if v["confidence"] == "high")
    print(f"{len(verdicts)} verdicts: {dict(by_verdict)}")
    print(f"fix-current: {len(fix_current)} ({high} high-confidence → {len(qs)} QS lines)")
    print(f"holders covered by QS lines: {sum(v['holders'] for v in fix_current if v['confidence'] == 'high')}")
    print(f"Wrote {BASE / 'fix_plan.md'} and {BASE / 'fix_plan.qs'}")


if __name__ == "__main__":
    main()
