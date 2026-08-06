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


def snak_value(value: dict) -> str:
    """A record's snak value as a QuickStatements literal."""
    if value.get("type") == "time":
        return qs_time(value["iso"])
    if value.get("type") == "item":
        return value["id"]
    return qs_value(value.get("text") or "")


def qs_lines(record: dict, retrieved: str) -> list[str]:
    """One QuickStatements line per statement on the record."""
    lines = []
    subject = record["subject"]
    for statement in record["statements"]:
        columns = [subject["qid"], statement["property"], snak_value(statement["value"])]
        for qualifier in statement.get("qualifiers", []):
            columns += [qualifier["property"], snak_value(qualifier["value"])]
        for reference in statement.get("references", []):
            # A Wikipedia permalink is an import, not a source: S4656 keeps it
            # out of S854, where linters (rightly) reject wiki URLs.
            columns += [reference["property"], f'"{reference["value"]["text"]}"',
                        "S813", qs_time(retrieved)]
        lines.append("\t".join(columns))
    return lines


def term_str(record: dict) -> str:
    spans = []
    for statement in record["statements"]:
        bounds = {q["property"]: q["value"].get("iso") for q in statement.get("qualifiers", [])}
        if bounds.get("P580") or bounds.get("P582"):
            spans.append(f"{bounds.get('P580') or '?'}–{bounds.get('P582') or ''}")
    return ", ".join(spans) or "no dates"


def source_of(record: dict) -> str | None:
    """The first reference URL on the record, unescaped.

    URLs quoted out of wikitext `<ref>`s arrive HTML-escaped (`&amp;`).
    """
    for statement in record["statements"]:
        for reference in statement.get("references", []):
            text = reference["value"].get("text")
            if text:
                return html.unescape(text)
    return None


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

    records: list[dict] = []
    for path in paths:
        for line in path.read_text().splitlines():
            if line.strip():
                records.append(json.loads(line))

    md: list[str] = ["# P39 edit plan", ""]
    qs: list[str] = []
    by_concern: dict[str, list[str]] = {}
    by_position: dict[str, list[dict]] = {}
    for record in records:
        target = record["statements"][0]["value"].get("id") if record["statements"] else None
        by_position.setdefault(target, []).append(record)

    counts = {"add": 0, "add_held": 0, "reject": 0, "unclear": 0}
    # A create subject has no target item yet; sort those last.
    for position, items in sorted(
        by_position.items(), key=lambda kv: (kv[0] is None, kv[0] or "")
    ):
        md.append(f"## Position {position or 'none — no target item exists (creation list)'}")
        for bucket, title, action in [
            ("add", "Apply — goes into edit_plan.qs", "apply"),
            ("add_held", "Held — believed, but no rule releases this tier yet", "hold"),
            ("reject", "Skipped — decided against, with a reason", "skip"),
            ("unclear", "Review — evidence still missing", "review"),
        ]:
            rows = [v for v in items if v["decision"]["action"] == action]
            rows.sort(key=lambda v: (v["decision"].get("rule") or "", v["subject"]["qid"]))
            if not rows:
                continue
            md.append(f"### {title}")
            for v in rows:
                counts[bucket] += 1
                rule = v["decision"].get("rule")
                tag = f" `{rule}`" if bucket != "add" and rule else ""
                md.append(f"* **{v['subject']['qid']} {v['subject'].get('label')}**{tag} — {term_str(v)}")
                md.append(f"  * evidence: {'; '.join(s['detail'] for s in v.get('signals', []))}")
                if source_of(v):
                    md.append(f"  * source: {source_of(v)}")
                if v.get("notes"):
                    md.append(f"  * notes: {v['notes']}")
                if bucket == "add":
                    # One file per concern: CLAUDE.md keeps batches
                    # single-concern so a bad rule can be reverted as one
                    # QuickStatements batch rather than unpicked statement by
                    # statement.
                    concern = v["decision"].get("concern") or "p39"
                    by_concern.setdefault(concern, []).extend(
                        qs_lines(v, args.retrieved)
                    )
                    qs.extend(qs_lines(v, args.retrieved))
            md.append("")

    summary = (
        f"{counts['add']} applied ({len(qs)} statements), "
        f"{counts['add_held']} held, "
        f"{counts['reject']} skipped, {counts['unclear']} to review"
    )
    md.insert(1, summary)
    plan_md.write_text("\n".join(md) + "\n")
    plan_qs.write_text("\n".join(qs) + "\n")
    print(summary)
    print(f"Wrote {plan_md}")
    print(f"Wrote {plan_qs}")
    for concern, lines in sorted(by_concern.items()):
        path = campaign_dir / f"edit_plan_{concern}.qs"
        path.write_text("\n".join(lines) + "\n")
        print(f"Wrote {path} ({len(lines)} statements)")


if __name__ == "__main__":
    main()
