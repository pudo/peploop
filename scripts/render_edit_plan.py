#!/usr/bin/env python
"""Render verification verdicts into a reviewable edit plan.

    python scripts/render_edit_plan.py --retrieved 2026-08-04
    python scripts/render_edit_plan.py --retrieved 2026-08-05 --campaign ecuador

Reads <campaign>/verdicts/*.jsonl and writes edit_plan.md (human review
document, every verdict) plus edit_plan.qs (QuickStatements V1).

Only `add` verdicts with `era: modern` reach the .qs. Any other era — interwar
continuity, acting spells, single-channel candidates — is an open convention
call, so it is grouped by era in the .md and waits for a human ruling.

Nothing here talks to Wikidata; applying the plan is a separate, human step.
"""

import argparse
import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wd.http import REPO_ROOT

DATA_DIR = REPO_ROOT / "data"


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


def qs_value(value: str) -> str:
    """QuickStatements literal syntax: items bare, everything else quoted."""
    if re.fullmatch(r"[QPL]\d+", value) or value.startswith("+"):
        return value
    return f'"{value}"'


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
        # Qualifiers beyond the dates: P2868 acting, P768 electoral district,
        # P2937 parliamentary term, ... Per-term values win over per-verdict.
        qualifiers = {**(verdict.get("qualifiers") or {}), **(term.get("qualifiers") or {})}
        for prop, value in qualifiers.items():
            if value:
                columns += [prop, qs_value(str(value))]
        url = verdict.get("source_url")
        if url:
            # A Wikipedia permalink is an import, not a source: S4656 keeps it
            # out of S854, where linters (rightly) reject wiki URLs.
            prop = verdict.get("source_prop") or "S854"
            columns += [prop, f'"{url}"', "S813", qs_time(retrieved)]
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
    parser.add_argument("--campaign", default="positions",
                        help="Subdirectory of data/ to read and write (default: positions)")
    args = parser.parse_args()

    campaign_dir = DATA_DIR / args.campaign
    verdict_dir = campaign_dir / "verdicts"
    plan_md = campaign_dir / "edit_plan.md"
    plan_qs = campaign_dir / "edit_plan.qs"

    # The campaign records which files it owns. Without that check a verdict
    # file left behind by a renamed office key keeps being rendered — Ecuador's
    # plan carried 91 records from a superseded run this way.
    paths = sorted(verdict_dir.glob("*.jsonl"))
    manifest_path = verdict_dir / "manifest.json"
    if manifest_path.exists():
        owned = set(json.loads(manifest_path.read_text())["files"])
        orphans = [p.name for p in paths if p.name not in owned]
        if orphans:
            print(f"! ignoring verdict files not in the manifest: {', '.join(orphans)}")
        paths = [p for p in paths if p.name in owned]

    verdicts: list[dict] = []
    for path in paths:
        for line in path.read_text().splitlines():
            if line.strip():
                verdict = json.loads(line)
                if verdict.get("source_url"):
                    # URLs quoted out of wikitext refs arrive HTML-escaped:
                    verdict["source_url"] = html.unescape(verdict["source_url"])
                verdicts.append(verdict)

    md: list[str] = ["# P39 edit plan", ""]
    qs: list[str] = []
    by_position: dict[str, list[dict]] = {}
    for v in verdicts:
        by_position.setdefault(v["position"], []).append(v)

    counts = {"add": 0, "add_held": 0, "reject": 0, "unclear": 0}
    # position=None rows come from bucket narrowing where no target item
    # exists yet (the item-creation list); sort them last.
    for position, items in sorted(
        by_position.items(), key=lambda kv: (kv[0] is None, kv[0] or "")
    ):
        md.append(f"## Position {position or 'none — no target item exists (creation list)'}")
        for bucket, title in [
            ("add", "Add — goes into edit_plan.qs"),
            ("add_held", "Add, held back pending a convention call"),
            ("reject", "Rejected"),
            ("unclear", "Unclear — needs a human look"),
        ]:
            if bucket == "add":
                rows = [v for v in items if v["verdict"] == "add" and v.get("era") == "modern"]
            elif bucket == "add_held":
                rows = [v for v in items if v["verdict"] == "add" and v.get("era") != "modern"]
            else:
                rows = [v for v in items if v["verdict"] == bucket]
            rows.sort(key=lambda v: (v.get("era") or "", v["qid"]))
            if not rows:
                continue
            md.append(f"### {title}")
            for v in rows:
                counts[bucket] += 1
                era = v.get("era")
                tag = f" `{era}`" if bucket != "add" and era else ""
                md.append(f"* **{v['qid']} {v.get('label')}**{tag} — {term_str(v)}")
                md.append(f"  * evidence: {v.get('evidence')}")
                if v.get("source_url"):
                    md.append(f"  * source: {v['source_url']}")
                if v.get("notes"):
                    md.append(f"  * notes: {v['notes']}")
                if bucket == "add":
                    qs.extend(qs_lines(v, args.retrieved))
            md.append("")

    summary = (
        f"{counts['add']} adds ({len(qs)} statements), "
        f"{counts['add_held']} adds held back, "
        f"{counts['reject']} rejected, {counts['unclear']} unclear"
    )
    md.insert(1, summary)
    plan_md.write_text("\n".join(md) + "\n")
    plan_qs.write_text("\n".join(qs) + "\n")
    print(summary)
    print(f"Wrote {plan_md}")
    print(f"Wrote {plan_qs}")


if __name__ == "__main__":
    main()
