#!/usr/bin/env python
"""Render court-judge verification verdicts into a reviewable P39 edit plan.

    python scripts/render_court_plan.py --retrieved 2026-08-06

Reads data/courts/verdicts/*.jsonl (the flat per-person verdict schema the
workbench's verification agents emit) and writes data/courts/edit_plan.md —
every verdict, grouped so a reviewer can see what was rejected and why — plus
data/courts/edit_plan.qs, which contains ONLY `add` verdicts with
`era: modern`. Anything else (predecessor-polity service, undatable spells,
unclear calls) is a convention question and waits for a human.

Kept separate from `render_edit_plan.py`: that one drives the long-running
positions campaign off a manifest and a richer record schema, and this
campaign should not be able to disturb its pending plan.

Nothing here writes to Wikidata.
"""

import argparse
import html
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wd.http import REPO_ROOT

CAMPAIGN_DIR = REPO_ROOT / "data" / "courts"
VERDICT_DIR = CAMPAIGN_DIR / "verdicts"


def qs_time(date: str) -> Optional[str]:
    """A partial ISO date as a QuickStatements time token.

    Precision follows how specific the source actually was: year-only stays
    year-precision rather than being padded to 1 January, which would assert
    a day nobody verified.
    """
    if not date:
        return None
    parts = str(date).split("-")
    year = parts[0]
    if not year.lstrip("-").isdigit():
        return None
    precision = {1: 9, 2: 10, 3: 11}[min(len(parts), 3)]
    month = parts[1] if len(parts) > 1 else "01"
    day = parts[2] if len(parts) > 2 else "01"
    return f"+{int(year):04d}-{month:0>2}-{day:0>2}T00:00:00Z/{precision}"


def qs_lines(v: Dict[str, Any], retrieved: str) -> List[str]:
    """QuickStatements V1 lines for one verdict: one statement per term.

    A source URL becomes S854 + S813 (retrieved). Wikipedia permalinks are
    imports rather than sources, so they are deliberately not emitted as
    S854 — linters reject wiki URLs there.
    """
    out = []
    terms = v.get("terms") or [{}]
    url = v.get("source_url")
    if url and "wikipedia.org" in url:
        url = None
    for term in terms:
        cols = [v["qid"], "P39", v["position"]]
        start, end = qs_time(term.get("start") or ""), qs_time(term.get("end") or "")
        if start:
            cols += ["P580", start]
        if end:
            cols += ["P582", end]
        if url:
            cols += ["S854", f'"{html.unescape(url)}"', "S813", qs_time(retrieved)]
        out.append("\t".join(cols))
    return out


def term_str(v: Dict[str, Any]) -> str:
    terms = v.get("terms") or []
    spans = [f"{t.get('start') or '?'}–{t.get('end') or ''}" for t in terms]
    return ", ".join(spans) or "no dates"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retrieved", required=True, help="S813 date, YYYY-MM-DD")
    args = parser.parse_args()

    verdicts: List[Dict[str, Any]] = []
    for path in sorted(VERDICT_DIR.glob("*.jsonl")):
        for line in path.read_text().splitlines():
            if line.strip():
                verdicts.append(json.loads(line))

    by_position: Dict[str, List[dict]] = defaultdict(list)
    for v in verdicts:
        by_position[v.get("position_name") or v.get("position")].append(v)

    counts: Counter = Counter(v["verdict"] for v in verdicts)
    qs: List[str] = []
    batched = 0
    md: List[str] = [
        "# P39 edit plan — apex court judgeships",
        "",
        f"{len(verdicts)} verified candidates: {dict(counts)}",
        "",
        "The `.qs` carries only `add` verdicts with `era: modern`. Everything "
        "else is listed here for a ruling and is **not** in the batch.",
        "",
    ]

    for position, rows in sorted(by_position.items()):
        target = rows[0].get("position")
        md.append(f"\n## {position} ({target})\n")
        groups: Dict[str, List[dict]] = defaultdict(list)
        for v in rows:
            key = v["verdict"]
            if key == "add" and v.get("era") != "modern":
                key = f"add / era={v.get('era')}"
            elif key == "add" and not (v.get("terms") or []):
                key = "add (undated)"
            groups[key].append(v)
        for key in sorted(groups):
            group = groups[key]
            md.append(f"### {key} ({len(group)})\n")
            for v in sorted(group, key=lambda r: r.get("label") or ""):
                md.append(f"* **{v['qid']} {v.get('label')}** — {term_str(v)}")
                if v.get("evidence"):
                    md.append(f"  * evidence: {v['evidence']}")
                if v.get("source_url"):
                    md.append(f"  * source: {v['source_url']}")
                if v.get("notes"):
                    md.append(f"  * note: {v['notes']}")
                # Gate on the verdict and the era, not on whether dates were
                # found: an undated P39 is still a true statement, and the
                # .md section flags it as undated for the reviewer.
                if v["verdict"] == "add" and v.get("era") == "modern":
                    qs.extend(qs_lines(v, args.retrieved))
                    batched += 1
            md.append("")

    CAMPAIGN_DIR.mkdir(parents=True, exist_ok=True)
    (CAMPAIGN_DIR / "edit_plan.qs").write_text("\n".join(qs) + ("\n" if qs else ""))
    md.insert(3, f"**Batched: {batched} people, {len(qs)} statements.**")
    (CAMPAIGN_DIR / "edit_plan.md").write_text("\n".join(md) + "\n")
    print(f"{len(verdicts)} verdicts: {dict(counts)}")
    print(f"batched {batched} people -> {len(qs)} statements in edit_plan.qs")


if __name__ == "__main__":
    main()
