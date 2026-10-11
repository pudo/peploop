#!/usr/bin/env python
"""Render verification verdicts into a reviewable edit plan.

    python scripts/render_edit_plan.py --retrieved 2026-08-04
    python scripts/render_edit_plan.py --retrieved 2026-08-05 --campaign ecuador

Reads <campaign>/verdicts/*.jsonl and writes edit_plan.md (the record of every
verdict), edit_plan.qs (QuickStatements V1) and — for the statements
QuickStatements cannot express — edit_plan_claims.json.

**Two write paths, because QuickStatements can only say some of this.** QS
matches an incoming line on subject, property and value alone and merges the
line's qualifiers into whatever statement it finds, so a person's two spells in
one office become a single P39 carrying both starts and both ends. Those groups
(`wd.validate.collapsing_groups`) are partitioned out into a wikibase-edit
payload per person, applied by `scripts/apply_claims.py`; everything else stays
in the one reviewable `.qs`. Neither file is written to Wikidata here.

**One batch per campaign, not one per concern.** This used to shard the `.qs` by
`decision.concern` so a bad rule could be reverted alone. It no longer does: the
review that matters happens in the QuickStatements importer, which is fed one
file, and a per-concern split meant the thing the reviewer approved was never
the thing they had read end to end. `concern` survives on the record as metadata
and still groups the `.md`; it just no longer decides how many files exist.

Only `apply` verdicts reach the `.qs`. Everything else is grouped by rule in the
`.md` as an account of what was decided against and why — not as a queue, which
is what `dispositions` in a campaign is for.

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
from wd.validate import check, collapsing_groups, conflicting_tenures

DATA_DIR = REPO_ROOT / "data"

#: Decision rules that edit a statement already on the item. QuickStatements
#: matches on subject, property and value and folds the qualifiers in; the API
#: has no such behaviour, so none of these may ever be routed to it.
MERGE_RULES = frozenset({
    "dates_existing_statement", "closes_existing_statement",
    "qualifies_existing_statement",
})

#: QuickStatements writes a reference property as "S" + number; the API wants
#: the property itself.
QS_REFERENCE = re.compile(r"^S(\d+)$")


def api_time(iso: str) -> dict:
    """A partial ISO date as a wikibase-edit time value.

    The precision has to be explicit. Left to infer, wikibase-edit reads a bare
    "1991" as a year and "1991-06-26" as a day, which happens to be right — but
    the roster's own precision is the thing being asserted here, so it is stated
    rather than re-derived.
    """
    return {"time": iso, "precision": {1: 9, 2: 10, 3: 11}[min(len(iso.split("-")), 3)]}


def api_value(value: dict):
    """A record's snak value in wikibase-edit form."""
    if value.get("type") == "time":
        return api_time(value["iso"])
    if value.get("type") == "item":
        return value["id"]
    return value.get("text") or ""


def api_claims(record: dict, retrieved: str) -> dict:
    """One person's statements as a wikibase-edit claims blob.

    Every tenure is listed separately and the API creates each one, which is the
    whole point of routing here: it is the behaviour QuickStatements does not
    have.
    """
    claims: dict[str, list[dict]] = {}
    for statement in record["statements"]:
        claim: dict = {"value": api_value(statement["value"])}
        qualifiers = {
            q["property"]: api_value(q["value"])
            for q in statement.get("qualifiers", [])
        }
        if qualifiers:
            claim["qualifiers"] = qualifiers
        references = {}
        for reference in statement.get("references", []):
            match = QS_REFERENCE.match(reference["property"])
            prop = f"P{match.group(1)}" if match else reference["property"]
            references[prop] = html.unescape(reference["value"]["text"])
        if references:
            references["P813"] = api_time(retrieved)
            claim["references"] = [references]
        claims.setdefault(statement["property"], []).append(claim)
    return claims


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


def withheld_keys(record: dict) -> set[tuple[str, str, str, str]]:
    """Lines the *source* left open, keyed as `conflicting_tenures` reads them.

    A start-only line is normally half of a tenure whose other half another
    source dates, and the validator vetoes the batch over it. Where the roster
    offered an end column for that row and left it blank, it is a spell whose
    end is unknown — see `wd.roster.RosterRow.end_withheld`.
    """
    keys = set()
    subject = record["subject"]["qid"]
    for statement in record["statements"]:
        if not statement.get("end_withheld"):
            continue
        bounds = {q["property"]: q["value"] for q in statement.get("qualifiers", [])}
        start = bounds.get("P580")
        if start and "P582" not in bounds:
            keys.add((subject, statement["property"],
                      snak_value(statement["value"]), qs_time(start["iso"])))
    return keys


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
    parser.add_argument("--campaign", required=True,
                        help="Subdirectory of data/ to read and write")
    args = parser.parse_args()

    campaign_dir = DATA_DIR / args.campaign
    verdict_dir = campaign_dir / "verdicts"
    plan_md = campaign_dir / "edit_plan.md"
    plan_qs = campaign_dir / "edit_plan.qs"
    plan_claims = campaign_dir / "edit_plan_claims.json"

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
    withheld_ends: set[tuple[str, str, str, str]] = set()
    by_position: dict[str, list[dict]] = {}
    for record in records:
        target = record["statements"][0]["value"].get("id") if record["statements"] else None
        by_position.setdefault(target, []).append(record)

    counts = {"add": 0, "add_held": 0, "reject": 0, "unclear": 0,
              "byproduct": 0}
    applied: list[dict] = []
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
            # `byproduct` was in `wd/record.py:ACTIONS` from the start and no
            # producer had ever emitted one, so it rendered as nothing at all —
            # which for the enrichment loop meant 87 of 117 records vanished,
            # including every office needing an item and every undated statement
            # needing a human's removal before it can be dated.
            ("byproduct", "Byproduct — a list for a human, not statements",
             "byproduct"),
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
                if bucket == "byproduct" and v.get("byproduct"):
                    payload = ", ".join(
                        f"{k}={val}" for k, val in sorted(v["byproduct"].items())
                        if val and k != "quote"
                    )
                    md.append(f"  * {payload}")
                if bucket == "add":
                    applied.append(v)
                    qs.extend(qs_lines(v, args.retrieved))
                    withheld_ends |= withheld_keys(v)
            md.append("")

    # One person can be reached through two offices — a party membership the
    # roster proves in both — and the same line then appears twice. QuickStatements
    # would collapse them, but a reviewer counting statements should not have to.
    qs = list(dict.fromkeys(qs))

    # Split off what QuickStatements cannot say. The key is the claim QS would
    # match on — subject, property, value — so every line touching a contested
    # claim has to leave the `.qs` together with the rest of its group, or the
    # part left behind merges into the statement the API is about to create.
    # Merged per person, not per record: a member of four Assembly terms is four
    # offices and so four records, and left unmerged they would be four separate
    # edits to one item. One payload per person makes each person's tenures land
    # atomically, which is the guarantee worth having when the API — unlike
    # QuickStatements — has no batch to revert.
    # A group that shares a bound between its lines is one tenure two sources
    # date differently, not two tenures (`conflicting_tenures`). It must not be
    # routed to the API either: QuickStatements at least collapses the
    # contradiction, whereas the API would write it out as two overlapping
    # statements. It stays in the `.qs` where `check` raises it as a defect, so
    # the render stops and a human reads the sources.
    contested = set(collapsing_groups(qs)) - set(conflicting_tenures(qs, withheld_ends))
    by_subject: dict[str, dict] = {}
    for record in applied:
        keys = {
            (record["subject"]["qid"], s["property"], snak_value(s["value"]))
            for s in record["statements"]
        }
        if not keys & contested:
            continue
        # A record that *edits an existing statement* must never come here. The
        # API creates rather than merges, so routing a merge to it writes a
        # second statement instead of qualifying the first — which is how five
        # duplicate Polish tenures reached a rendered claims payload. The
        # producer is supposed to have made this combination a byproduct
        # (`wd/policy.py:mixed_write_paths`); this is the structural backstop, so
        # a future rule cannot reintroduce it silently.
        if MERGE_RULES & {record["decision"].get("rule")}:
            raise SystemExit(
                f"! {record['subject']['qid']} would send a merge "
                f"({record['decision'].get('rule')}) to the API, which creates "
                "rather than merges. Refusing to render."
            )
        qid = record["subject"]["qid"]
        payload = by_subject.setdefault(
            qid, {"id": qid, "label": record["subject"].get("label"), "claims": {}}
        )
        for prop, claims in api_claims(record, args.retrieved).items():
            for claim in claims:
                if claim not in payload["claims"].setdefault(prop, []):
                    payload["claims"][prop].append(claim)
    claims_payloads = [by_subject[qid] for qid in sorted(by_subject)]
    qs = [line for line in qs if tuple(line.split("\t")[:3]) not in contested]

    # The checks `recipes/country_sweep.md` has prescribed since Ecuador, run
    # here rather than typed out again per campaign. A defect stops the render:
    # the point of a mechanical check is that it cannot be skipped on a late
    # night.
    validation = check(qs, withheld_ends)
    md[2:2] = validation.lines()

    tenures = sum(len(c) for p in claims_payloads for c in p["claims"].values())
    summary = (
        f"{counts['add']} applied ({len(qs)} statements via QuickStatements, "
        f"{tenures} via the API for {len(claims_payloads)} people with several "
        f"tenures in one office), {counts['add_held']} held, "
        f"{counts['reject']} skipped, {counts['unclear']} to review"
        # Only when there are any, so a campaign that emits none renders
        # byte-identically to before this bucket existed.
        + (f", {counts['byproduct']} byproduct" if counts["byproduct"] else "")
    )
    md.insert(1, summary)
    plan_md.write_text("\n".join(md) + "\n")
    plan_qs.write_text("\n".join(qs) + "\n")
    print(summary)
    print(f"Wrote {plan_md}")
    print(f"Wrote {plan_qs} ({len(qs)} statements)")
    if claims_payloads:
        plan_claims.write_text(
            json.dumps(claims_payloads, ensure_ascii=False, indent=2) + "\n"
        )
        print(f"Wrote {plan_claims} ({tenures} statements for "
              f"{len(claims_payloads)} people — run scripts/apply_claims.py)")
    elif plan_claims.exists():
        plan_claims.unlink()

    for warning in validation.warnings:
        print(f"⚠ {warning}")
    if not validation.ok:
        for defect in validation.defects:
            print(f"✗ {defect}")
        raise SystemExit(
            f"{len(validation.defects)} defect(s) in {plan_qs} — not fit to run"
        )


if __name__ == "__main__":
    main()
