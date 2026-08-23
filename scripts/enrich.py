#!/usr/bin/env python
"""Enrich the people one PETScan category sweeps in, one person per request.

    python scripts/enrich.py --spec en:ICC_prosecutors --dossiers
    python scripts/enrich.py --spec en:... --backtest --limit 3
    python scripts/enrich.py --spec en:... --limit 5

Three modes, in the order they should be run:

* `--dossiers` assembles the evidence and writes it to disk without calling the
  API. Read one before spending anything: every mechanical matcher this
  workbench has built was too loose on its first pass.
* `--backtest` runs the loop over the people who **already** hold the office,
  with those tenures hidden from the dossier, and scores what comes back against
  what Wikidata records. Those people are a labelled test set that costs nothing
  to label, and this number is the only honest answer to "is this better than a
  campaign".
* the default runs the gap and writes verdicts plus a report.

Nothing here writes to Wikidata. Verdicts land in a ledger, so re-running is
free for anyone already judged and a widened cohort costs only what is new.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rigour.territories import lookup_territory  # noqa: E402

from wd.campaign import resolve_titles
from wd.backtest import COARSER, CONTAINED, NEAR, SAME_TERM, ExistingTerm, compare
from wd.cohort import build as build_cohort
from wd.dossier import build as build_dossier
from wd.dossier import build_roster_index
from wd.enrich import (VERDICT_SCHEMA, check, flag_summary, records,
                      unresolved_offices)
from wd.gazetteer import for_country, for_target
from wd.http import REPO_ROOT, make_session
from wd.record import dumps
from wd.shape import verify_all
from wd.specs import BUCKET, load_specs, roster_pages
from wd.verdicts import EFFORT, MODEL, Ledger, classify

OUT_DIR = REPO_ROOT / "data" / "enrich"
PROMPT = REPO_ROOT / "prompts" / "person_enrichment.md"


def slug(key: str) -> str:
    return key.replace(":", "_").replace("/", "_").replace(" ", "_")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True, help="spec key, '<lang>:<Category>'")
    parser.add_argument("--limit", type=int, help="only the first N people")
    parser.add_argument("--backtest", action="store_true",
                        help="run the already-recorded holders as a test set")
    parser.add_argument("--dossiers", action="store_true",
                        help="write dossiers and stop, no API call")
    parser.add_argument("--no-rosters", action="store_true",
                        help="skip the shared officeholder-list channel")
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--effort", default=EFFORT,
                        choices=["low", "medium", "high", "xhigh", "max"])
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--prompt", type=Path, default=PROMPT)
    args = parser.parse_args()

    specs = {s.key: s for s in load_specs()}
    spec = specs.get(args.spec)
    if spec is None:
        raise SystemExit(f"no such spec: {args.spec}")
    if spec.granularity != BUCKET and not spec.target:
        raise SystemExit(f"{spec.key} has no resolved wikidata_id — see "
                         "tasks/category_positions.md")

    out = OUT_DIR / slug(spec.key)
    out.mkdir(parents=True, exist_ok=True)
    session = make_session()

    # The office's own shape, first: `topics` decides the after-office window,
    # and it belongs to the position rather than the person. Without it every
    # ex-minister reads as dropped, in one direction only, so it looks like a
    # finding.
    topics = {}
    if spec.target:
        shape = verify_all(session, [spec.target])[0]
        topics = {spec.target: shape.topics}
        print(f"{spec.target} {shape.label}: topics={sorted(shape.topics)} "
              f"defects={shape.defects} os_notes={shape.os_notes}", file=sys.stderr)
        if shape.os_notes:
            print("  note: wd_peps would not emit this position as it stands, so "
                  "this spec cannot be retired by enrichment alone.", file=sys.stderr)

    if spec.granularity == BUCKET:
        # A bucket spec names a class of offices, so the gazetteer is the whole
        # country. `rigour` turns the spec's ISO code into the QID; nothing here
        # ever asks a model for one.
        territory = lookup_territory(spec.position_country or "", fuzzy=True)
        if territory is None or not territory.qid:
            raise SystemExit(
                f"{spec.key} is a bucket spec and its country "
                f"{spec.position_country!r} does not resolve"
            )
        gazetteer = for_country(session, territory.qid)
    else:
        gazetteer = for_target(session, spec.target)
    print(f"gazetteer: {len(gazetteer.entries)} offices ({gazetteer.scope})",
          file=sys.stderr)

    cohort = build_cohort(session, spec)
    print(f"cohort: {cohort.sizes} dropped={cohort.reasons()}", file=sys.stderr)
    people = cohort.held if args.backtest else cohort.todo
    if args.limit:
        people = people[: args.limit]
    if not people:
        raise SystemExit("nothing to do")

    # Shared evidence, fetched once: a roster page names dozens of people, and
    # a roster row states a term where a biography usually does not. Absent for
    # many categories (there is no list article for the Supreme People's
    # Assembly), which is a fallback rather than a failure.
    index = None
    if not args.no_rosters:
        pages = roster_pages(session, spec)
        if pages:
            index = build_roster_index(session, pages, resolve=resolve_titles)
            print(f"rosters: {len(index.rows)} rows from {len(pages)} page(s), "
                  f"{len(index.by_qid)} linked to an item", file=sys.stderr)
        else:
            print("rosters: no list article for this category", file=sys.stderr)

    withhold = [spec.target] if (args.backtest and spec.target) else []
    items = []
    for member in people:
        dossier = build_dossier(session, member.qid, topics=topics,
                                withhold=withhold, rosters=index)
        if dossier.empty:
            print(f"  skip {member.qid}: no article to read", file=sys.stderr)
            continue
        items.append({"qid": member.qid, "label": dossier.label or member.qid,
                      "_dossier": dossier})
        (out / f"dossier_{member.qid}.md").write_text(dossier.render())
    print(f"{len(items)} dossiers written to {out}", file=sys.stderr)
    if args.dossiers:
        return

    name = "backtest" if args.backtest else "verdicts"
    ledger = Ledger(out / f"{name}.jsonl").load()
    usage = classify(
        [{"qid": i["qid"], "label": i["label"]} for i in items],
        prompt=args.prompt.read_text(),
        item_schema=VERDICT_SCHEMA,
        ledger=ledger,
        extra_system=[gazetteer.render()],
        render=lambda batch: next(
            i["_dossier"].render() for i in items if i["qid"] == batch[0]["qid"]
        ),
        batch_size=1,          # evidence length varies by an order of magnitude
        workers=args.workers,
        model=args.model,
        effort=args.effort,
        log=lambda m: print(m, file=sys.stderr),
    )
    print(usage.line())

    # --- the mechanical channel ------------------------------------------- #
    dossiers = {i["qid"]: i["_dossier"] for i in items}
    rows = [json.loads(line) for line in
            (out / f"{name}.jsonl").read_text().splitlines() if line.strip()]
    checks, report = [], []
    for row in rows:
        dossier = dossiers.get(row.get("qid"))
        if dossier is None:
            continue
        recorded = None
        if args.backtest:
            # The dossier hid these on purpose; the checker needs them back, or
            # every rediscovered tenure reads as a new proposal.
            recorded = build_dossier(
                session, row["qid"], topics=topics, body=False
            ).item["tenures"]
        found = check(row, dossier, gazetteer, recorded=recorded)
        checks.extend(found)
        report.append((row, found, recorded))

    (out / f"{name}_checked.json").write_text(json.dumps(
        [c.as_dict() for c in checks], indent=1, ensure_ascii=False))

    # Edit records, in the one schema every renderer reads. Written even in
    # backtest mode, where every rule should fire `already_recorded` — a
    # backtest that produced applyable statements would mean the loop is
    # re-proposing what it was scored against.
    produced = []
    for row, found, _ in report:
        dossier = dossiers.get(row.get("qid"))
        if dossier is not None:
            produced.extend(records(spec.key, dossier, found,
                                    campaign=f"enrich_{slug(spec.key)}"))
    verdicts = out / "verdicts"
    verdicts.mkdir(parents=True, exist_ok=True)
    stem = f"enrich_{name}.jsonl"
    (verdicts / stem).write_text(dumps(produced))
    # `render_edit_plan.py` renders only what the manifest owns, which is what
    # stopped a superseded office key contributing 91 records to a batch.
    (verdicts / "manifest.json").write_text(
        json.dumps({"files": [stem]}, indent=1) + "\n")
    actions: dict = {}
    for record in produced:
        key = f"{record.decision.action}/{record.decision.rule}"
        actions[key] = actions.get(key, 0) + 1
    print(f"\n{len(produced)} records -> {verdicts / stem}")
    for key, count in sorted(actions.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {count:>4}  {key}")
    print(f"\n  render with: scripts/render_edit_plan.py --campaign "
          f"enrich/{slug(spec.key)} --retrieved <YYYY-MM-DD>")
    print(f"\n{len(checks)} proposals, {sum(1 for c in checks if c.ok)} passing "
          f"every check")
    for flag, count in flag_summary(checks).items():
        print(f"  {count:>4}  {flag}")

    pending = unresolved_offices(checks)
    if pending:
        (out / "unresolved.json").write_text(
            json.dumps(pending, indent=1, ensure_ascii=False))
        print(f"\n{len(pending)} offices named with no item — {out/'unresolved.json'}")
        for entry in pending[:8]:
            print(f"    {entry['office_name']}  ({entry['holder']})")

    if not args.backtest:
        return

    # --- backtest scoring -------------------------------------------------- #
    #
    # Three different questions, kept apart. Conflating them is what made a
    # clean run read as 13/72: `Comparison.target_agrees` is False whenever the
    # recorded statement is *undated*, because `ExistingTerm.covers` needs two
    # dates to overlap anything — and most legislature seats are recorded
    # undated. That is not a disagreement, it is an absence of anything to
    # disagree with, and it is also the single biggest thing this loop can fix.
    print("\n## Backtest — proposals against the statements that were hidden\n")
    recorded_total = matched = 0
    dated_total = dated_ok = 0
    new_terms = undatable = 0
    for row, found, recorded in report:
        on_target = [t for t in (recorded or [])
                     if t.get("position") == spec.target]
        proposals = [c for c in found
                     if c.proposal.get("property") == "P39"
                     and c.proposal.get("position_qid") == spec.target]
        recorded_total += len(on_target)
        terms = [
            ExistingTerm(position=t["position"], start=t.get("start"),
                         end=t.get("end"),
                         precision=11 if (t.get("start") or "").count("-") == 2
                         else 9 if t.get("start") else 0)
            for t in on_target
        ]
        for tenure in on_target:
            if not tenure.get("start"):
                undatable += 1
        # Recall: was each recorded tenure re-proposed at all? The loop is only
        # allowed to have found the office, never the specific statement.
        matched += min(len(proposals), len(on_target))
        for c in proposals:
            comparison = compare(
                campaign="enrich", office=spec.key, qid=row["qid"],
                label=row.get("label", ""), target=spec.target or "",
                row_start=c.proposal.get("start"), row_end=c.proposal.get("end"),
                period_raw=c.proposal.get("quote", "")[:80], terms=terms,
                acting_predicted=bool(c.proposal.get("acting")),
            )
            if comparison.recorded_start:
                dated_total += 1
                dated_ok += comparison.verdict in (SAME_TERM, CONTAINED, NEAR,
                                                   COARSER)
                print(f"  {row['qid']:>11} {c.proposal.get('start')}–"
                      f"{c.proposal.get('end')} vs recorded "
                      f"{comparison.recorded_start}–{comparison.recorded_end} "
                      f"| {comparison.verdict}")
            else:
                new_terms += 1
    print(f"\n  recorded tenures on target       {recorded_total}")
    print(f"  ...of which recorded undated     {undatable}"
          f"   <- what a dated proposal would fix")
    print(f"  recall: recorded tenures re-found {matched}/{recorded_total}")
    if dated_total:
        print(f"  dates agree where there was a date {dated_ok}/{dated_total}")
    print(f"  proposals with no matching record  {new_terms}"
          f"   <- new dated terms, unscoreable here")
    print(f"  proposals for other offices        "
          f"{sum(1 for _, f, _ in report for c in f
                 if c.proposal.get('property') == 'P39'
                 and c.proposal.get('position_qid') != spec.target)}"
          f"   <- out of this gazetteer, NOT all creation candidates")


if __name__ == "__main__":
    main()
