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

from wd.backtest import COARSER, CONTAINED, NEAR, SAME_TERM, ExistingTerm, compare
from wd.cohort import build as build_cohort
from wd.dossier import build as build_dossier
from wd.enrich import VERDICT_SCHEMA, check, flag_summary, unresolved_offices
from wd.gazetteer import for_country, for_target
from wd.http import REPO_ROOT, make_session
from wd.shape import verify_all
from wd.specs import BUCKET, load_specs
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

    withhold = [spec.target] if (args.backtest and spec.target) else []
    items = []
    for member in people:
        dossier = build_dossier(session, member.qid, topics=topics,
                                withhold=withhold)
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
    print("\n## Backtest — proposals against the statements that were hidden\n")
    # Only proposals naming the office under test are scoreable. A proposal for
    # some *other* office the article mentions is not a wrong answer — it is a
    # creation candidate, and counting it as a target disagreement makes a
    # perfect run read as 50%.
    agree = dates_ok = total = 0
    elsewhere = 0
    for row, found, recorded in report:
        terms = [
            ExistingTerm(position=t["position"], start=t.get("start"),
                         end=t.get("end"),
                         precision=11 if (t.get("start") or "").count("-") == 2
                         else 9 if t.get("start") else 0)
            for t in (recorded or [])
        ]
        for c in found:
            if c.proposal.get("property") != "P39":
                continue
            if c.proposal.get("position_qid") != spec.target:
                elsewhere += 1
                continue
            total += 1
            comparison = compare(
                campaign="enrich", office=spec.key, qid=row["qid"],
                label=row.get("label", ""), target=spec.target or "",
                row_start=c.proposal.get("start"), row_end=c.proposal.get("end"),
                period_raw=c.proposal.get("quote", "")[:80], terms=terms,
                acting_predicted=bool(c.proposal.get("acting")),
            )
            agree += comparison.target_agrees
            dates_ok += comparison.verdict in (SAME_TERM, CONTAINED, NEAR, COARSER)
            print(f"  {row['qid']:>11} proposed {c.proposal.get('position_qid')} "
                  f"{c.proposal.get('start')}–{c.proposal.get('end')} | "
                  f"recorded {comparison.target_actual} "
                  f"{comparison.recorded_start}–{comparison.recorded_end} | "
                  f"{comparison.verdict} | target_agrees={comparison.target_agrees}")
    if total:
        print(f"\n  target agreement          {agree}/{total}")
        print(f"  dates not contradicting   {dates_ok}/{total}")
    print(f"  proposals for other offices {elsewhere} "
          f"(creation candidates, not scored)")
    missed = [
        (row["qid"], t)
        for row, found, recorded in report
        for t in (recorded or [])
        if t.get("position") == spec.target
        and not any(c.proposal.get("position_qid") == spec.target for c in found)
    ]
    # The number that actually matters: a recorded tenure the loop never
    # proposed at all. A high target agreement over a handful of proposals is
    # not recall.
    print(f"  recorded tenures missed     {len(missed)}")
    for qid, tenure in missed:
        print(f"    {qid} {tenure.get('start')}–{tenure.get('end')}")


if __name__ == "__main__":
    main()
