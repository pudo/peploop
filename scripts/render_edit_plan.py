#!/usr/bin/env python
"""Render verification verdicts into a reviewable edit plan.

    python scripts/render_edit_plan.py --retrieved 2026-08-04

Reads data/positions/verdicts/*.jsonl and writes:
  data/positions/edit_plan.md  - human review document, all verdicts
  data/positions/edit_plan.qs  - QuickStatements V1 for the approved shape
                                 (era=modern "add" verdicts only; interwar
                                 stays in the .md until a policy call is made)

Nothing here talks to Wikidata; applying the plan is a separate, human step.
"""

import argparse
import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wd.http import REPO_ROOT

VERDICT_DIR = REPO_ROOT / "data" / "positions" / "verdicts"
PLAN_MD = REPO_ROOT / "data" / "positions" / "edit_plan.md"
PLAN_QS = REPO_ROOT / "data" / "positions" / "edit_plan.qs"


def qs_time(date: str) -> str | None:
    """Render a partial ISO date as a QuickStatements time token."""
    if not date:
        return None
    parts = date.split("-")
    year = parts[0]
    if not year.isdigit():
        return None
    precision = {1: 9, 2: 10, 3: 11}[min(len(parts), 3)]
    month = parts[1] if len(parts) > 1 else "01"
    day = parts[2] if len(parts) > 2 else "01"
    return f"+{year}-{month}-{day}T00:00:00Z/{precision}"


def qs_lines(verdict: dict, retrieved: str) -> list[str]:
    """One P39 statement per term (or one bare statement without terms)."""
    lines = []
    terms = verdict.get("terms") or [{}]
    for term in terms:
        columns = [verdict["qid"], "P39", verdict["position"]]
        start = qs_time(term.get("start") or "")
        end = qs_time(term.get("end") or "")
        if start:
            columns += ["P580", start]
        if end:
            columns += ["P582", end]
        url = verdict.get("source_url")
        if url:
            columns += ["S854", f'"{url}"', "S813", qs_time(retrieved)]
        lines.append("\t".join(columns))
    return lines


def term_str(verdict: dict) -> str:
    terms = verdict.get("terms") or []
    spans = []
    for term in terms:
        spans.append(f"{term.get('start') or '?'}–{term.get('end') or ''}")
    return ", ".join(spans) or "no dates"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retrieved", required=True, help="S813 retrieved date, YYYY-MM-DD")
    args = parser.parse_args()

    verdicts: list[dict] = []
    for path in sorted(VERDICT_DIR.glob("*.jsonl")):
        for line in path.read_text().splitlines():
            if line.strip():
                verdict = json.loads(line)
                if verdict.get("source_url"):
                    # URLs quoted out of wikitext refs arrive HTML-escaped:
                    verdict["source_url"] = html.unescape(verdict["source_url"])
                verdicts.append(verdict)

    md: list[str] = ["# P39 edit plan (Lithuania pilot)", ""]
    qs: list[str] = []
    by_position: dict[str, list[dict]] = {}
    for v in verdicts:
        by_position.setdefault(v["position"], []).append(v)

    counts = {"add": 0, "add_interwar": 0, "reject": 0, "unclear": 0}
    for position, items in sorted(by_position.items()):
        md.append(f"## Position {position}")
        for bucket, title in [
            ("add", "Add (modern era) — goes into edit_plan.qs"),
            ("add_interwar", "Add (interwar) — held back pending policy"),
            ("reject", "Rejected"),
            ("unclear", "Unclear — needs a human look"),
        ]:
            if bucket == "add":
                rows = [v for v in items if v["verdict"] == "add" and v.get("era") == "modern"]
            elif bucket == "add_interwar":
                rows = [v for v in items if v["verdict"] == "add" and v.get("era") != "modern"]
            else:
                rows = [v for v in items if v["verdict"] == bucket]
            if not rows:
                continue
            md.append(f"### {title}")
            for v in rows:
                counts[bucket] += 1
                md.append(f"* **{v['qid']} {v.get('label')}** — {term_str(v)}")
                md.append(f"  * evidence: {v.get('evidence')}")
                if v.get("source_url"):
                    md.append(f"  * source: {v['source_url']}")
                if v.get("notes"):
                    md.append(f"  * notes: {v['notes']}")
                if bucket == "add":
                    qs.extend(qs_lines(v, args.retrieved))
            md.append("")

    summary = (
        f"{counts['add']} modern adds ({len(qs)} statements), "
        f"{counts['add_interwar']} interwar adds held back, "
        f"{counts['reject']} rejected, {counts['unclear']} unclear"
    )
    md.insert(1, summary)
    PLAN_MD.write_text("\n".join(md) + "\n")
    PLAN_QS.write_text("\n".join(qs) + "\n")
    print(summary)
    print(f"Wrote {PLAN_MD}")
    print(f"Wrote {PLAN_QS}")


if __name__ == "__main__":
    main()
