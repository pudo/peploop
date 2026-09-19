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
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rigour.territories import lookup_territory  # noqa: E402

from wd.api import best_label, fetch_entities
from wd.campaign import resolve_titles
from wd.backtest import COARSER, CONTAINED, NEAR, SAME_TERM, ExistingTerm, compare
from wd.cohort import build as build_cohort
from wd.dossier import build as build_dossier
from wd.dossier import build_roster_index, territory_langs
from wd.enrich import (VERDICT_SCHEMA, check, flag_summary, records,
                      resolve_offices, unresolved_offices)
from wd.gazetteer import (describe, for_country, for_qualifier,
                          for_target, render_qualifiers)
from wd.http import REPO_ROOT, make_session
from wd.positions import index_for_country, subclass_held
from wd.rerank import Mention, place_offices
from wd.record import dumps
from wd.shape import verify_all
from wd.specs import BUCKET, load_specs, roster_pages
from wd.verdicts import EFFORT, MODEL, Ledger, classify

OUT_DIR = REPO_ROOT / "data" / "enrich"
PROMPT = REPO_ROOT / "prompts" / "person_enrichment.md"
RERANK_PROMPT = REPO_ROOT / "prompts" / "office_rerank.md"


def slug(key: str) -> str:
    return key.replace(":", "_").replace("/", "_").replace(" ", "_")


def score_bucket(report, cohort, placed, mentions) -> None:
    """Score a bucket backtest: did the loop pick the office the record uses?

    Three numbers, kept apart, because they fail for different reasons and a
    single percentage hides which one did.

    * **retrieval recall** — was the true office reachable at all, either in
      the gazetteer the model read or in a shortlist the placement pass built?
      This is the ceiling on everything below it, and its failure is the
      invisible one: an office the loop never saw comes back as a name, and a
      name with no item reads as a *finding* rather than as a miss.
    * **choice accuracy** — of the tenures that were hidden, how many came back
      pointing at the same item.
    * **refusal** — how often the loop declined to name a QID. Declining when
      the office was unreachable is the right answer; declining when it was
      right there is the cost of a shortlist that buried it.

    A single-target backtest cannot ask any of this: with one item in the
    gazetteer the only available answer is that item.
    """
    proposed: dict = {}
    named: dict = {}
    for row, found, _ in report:
        person = row.get("qid")
        for c in found:
            if c.proposal.get("property") != "P39":
                continue
            qid = c.proposal.get("position_qid")
            if qid:
                proposed.setdefault(person, set()).add(qid)
            elif c.proposal.get("office_name"):
                named.setdefault(person, set()).add(c.proposal["office_name"])

    judged = [r[0].get("qid") for r in report]
    truth = {q: set(cohort.holdings.get(q, ())) for q in judged}
    hidden = sum(len(v) for v in truth.values())
    hit = sum(len(truth[q] & proposed.get(q, set())) for q in truth)
    # An office the placement pass resolved counts as reached even when the
    # model could only name it in prose — that is the lane working.
    reached = set(placed.values()) if placed else set()
    recalled = sum(
        len(truth[q] & (proposed.get(q, set()) | reached)) for q in truth
    )
    people_silent = sum(
        1 for q in truth if truth[q] and not proposed.get(q) and not named.get(q)
    )

    print("\n## Bucket backtest — did it pick the office the record uses?\n")
    print(f"  people scored                    {len(judged)}")
    print(f"  in-scope tenures hidden          {hidden}")
    print(f"  ...reachable (gazetteer|placed)  {recalled}/{hidden}"
          f"   <- the ceiling; a miss here looks like a creation candidate")
    print(f"  choice: same office re-proposed  {hit}/{hidden}")
    print(f"  people who named nothing at all  {people_silent}")
    print(f"  offices named but not placed     {len(mentions) - len(placed)}"
          f" of {len(mentions)}")
    wrong = {
        q: sorted(proposed.get(q, set()) - truth[q]) for q in truth
        if proposed.get(q, set()) - truth[q]
    }
    if wrong:
        print(f"\n  proposals for an office the record does not have "
              f"({sum(len(v) for v in wrong.values())}):")
        for person, qids in sorted(wrong.items())[:20]:
            print(f"    {person} -> {', '.join(qids)} "
                  f"(record: {', '.join(sorted(truth[person])) or 'none'})")


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
    parser.add_argument("--allow-class-target", action="store_true",
                        help="run even when the gap is explained by the "
                             "target being a superclass of the office the "
                             "members actually hold")
    parser.add_argument("--no-resolve", action="store_true",
                        help="skip placing offices the gazetteer did not offer")
    parser.add_argument("--no-qualifiers", action="store_true",
                        help="skip the P768/P4100 qualifier sets")
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--effort", default=EFFORT,
                        choices=["low", "medium", "high", "xhigh", "max"])
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--prompt", type=Path, default=PROMPT)
    parser.add_argument("--rerank-prompt", type=Path, default=RERANK_PROMPT,
                        help="prompt for the office-placement pass")
    parser.add_argument("--depth", type=int,
                        help="override the spec's category recursion depth. A "
                             "bucket category is often a shelf of per-portfolio "
                             "subcategories with almost no articles of its own.")
    parser.add_argument("--language",
                        help="override the spec's wiki language. Six Czech "
                             "specs in wd_categories.yml declare `en` and name "
                             "a cs.wikipedia category, so they sweep in nobody "
                             "and read as an empty category rather than a "
                             "broken query.")
    args = parser.parse_args()

    specs = {s.key: s for s in load_specs()}
    spec = specs.get(args.spec)
    if spec is None:
        raise SystemExit(f"no such spec: {args.spec}")
    if args.depth is not None and args.depth != spec.depth:
        print(f"depth: {spec.depth} -> {args.depth} (override)", file=sys.stderr)
        spec = replace(spec, depth=args.depth)
    if args.language and args.language != spec.language:
        print(f"language: {spec.language} -> {args.language} (override)",
              file=sys.stderr)
        spec = replace(spec, language=args.language,
                       key=f"{args.language}:{spec.category}")
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

    # `rigour` turns the spec's ISO code into a QID; nothing here ever asks a
    # model for one. Resolved once — the bucket gazetteer, the qualifier sets
    # and the office-placement index all want it.
    territory = lookup_territory(spec.position_country or "", fuzzy=True)
    country_qid = territory.qid if territory else None

    if spec.granularity == BUCKET:
        # A bucket spec names a class of offices, so the gazetteer is the whole
        # country.
        if country_qid is None:
            raise SystemExit(
                f"{spec.key} is a bucket spec and its country "
                f"{spec.position_country!r} does not resolve"
            )
        gazetteer = for_country(session, country_qid,
                                log=lambda m: print(f"  {m}", file=sys.stderr))
    else:
        gazetteer = for_target(session, spec.target)
    print(f"gazetteer: {len(gazetteer.entries)} offices ({gazetteer.scope})",
          file=sys.stderr)

    # Qualifier sets, per country and closed. Empty is a normal answer: it means
    # the value cannot be asserted here — Guatemala has no electoral-district and
    # no parliamentary-group items at all.
    quals: dict = {}
    if country_qid and not args.no_qualifiers:
        for prop in ("P768", "P4100"):
            quals[prop] = for_qualifier(session, prop, country_qid)
        print("qualifiers: " + ", ".join(
            f"{p}={len(g.entries)}" for p, g in sorted(quals.items())),
            file=sys.stderr)

    # A bucket spec has no single target, so the backtest set is "holds any of
    # the country's offices". Without this every member lands in `todo` and
    # there is nothing to score the office choice against.
    bucket_targets = sorted(gazetteer.qids) if spec.granularity == BUCKET else []
    cohort = build_cohort(session, spec, targets=bucket_targets)
    print(f"cohort: {cohort.sizes} dropped={cohort.reasons()}", file=sys.stderr)
    # Is the gap real, or is the target a *class* and not a seat? A superclass
    # target produces a gap on every member while every property the item audit
    # reads looks right, so nothing upstream of here can catch it: `Q20706330`
    # "United States Supreme Court justice" is defect-free, emittable, scoped to
    # Q30 and attached to the Court, and is the `P279` parent of the seat its
    # members hold. Asked of the gap's own statements, before anything is spent.
    if spec.target and cohort.todo:
        children = subclass_held(session, spec.target,
                                 [m.qid for m in cohort.todo])
        worst = max(children.items(), key=lambda kv: kv[1], default=None)
        if worst and worst[1] * 2 >= len(cohort.todo):
            labels = fetch_entities(session, list(children), props="labels")
            print(f"\n! the gap holds a subclass of the target. Of "
                  f"{len(cohort.todo)} people to enrich:", file=sys.stderr)
            for qid, n in sorted(children.items(), key=lambda kv: -kv[1]):
                print(f"    {n:>4} already hold {qid} "
                      f"{best_label(labels.get(qid, {}))} (P279 -> {spec.target})",
                      file=sys.stderr)
            print("  The spec's target names a class of offices and its members "
                  "hold the seat. Point the\n  `position:` block at the child "
                  "and re-measure — proposing the parent would write a\n  "
                  "superclass P39 onto people who already hold the child. "
                  "--allow-class-target overrides.", file=sys.stderr)
            if not args.allow_class_target:
                raise SystemExit(1)

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

    # Which wikis to read, and it is not the global size ordering `pick_langs`
    # falls back to: `cs` sits 14th there, so three of the first five Czech
    # ministers were about to be judged on their Polish, German and Ukrainian
    # articles with the Czech one unread. The spec's own wiki first — its
    # category swept the person in, so an article exists there by construction
    # — then the country's own languages, then English as the widest net.
    wikis = tuple(dict.fromkeys(
        [spec.language, *territory_langs(spec.position_country), "en"]
    ))
    print(f"wikis, preferred first: {', '.join(wikis)}", file=sys.stderr)

    items = []
    for member in people:
        # Withhold what this person is being tested on. For a single-office
        # spec that is the target; for a bucket it is every in-scope office
        # they hold, or the dossier hands the model the answer.
        if not args.backtest:
            withhold = []
        elif bucket_targets:
            withhold = cohort.holdings.get(member.qid, [])
        else:
            withhold = [spec.target] if spec.target else []
        dossier = build_dossier(session, member.qid, topics=topics,
                                withhold=withhold, rosters=index,
                                prefer=wikis)
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
    prompt = args.prompt.read_text()
    if ledger.stale_for(prompt):
        print(f"! {ledger.path.name} was judged under a different prompt "
              f"({', '.join(sorted(ledger.seen_prompts))} vs this one). Those "
              "rows will not be re-asked and may lack fields this run expects — "
              "move the file aside to re-judge.", file=sys.stderr)
    usage = classify(
        [{"qid": i["qid"], "label": i["label"]} for i in items],
        prompt=prompt,
        item_schema=VERDICT_SCHEMA,
        ledger=ledger,
        extra_system=[b for b in (gazetteer.render(), render_qualifiers(quals)) if b],
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
    # A single-target gazetteer makes every *other* office the person held read
    # as unresolved by construction, so place those names before judging them:
    # a creation candidate that already has an item is not a creation candidate.
    mentions: dict = {}
    for row in rows:
        for proposal in row.get("proposals") or []:
            office = (proposal.get("office_name") or "").strip()
            if proposal.get("property") != "P39" or proposal.get("position_qid"):
                continue
            if not office:
                continue
            mention = mentions.setdefault(office, Mention(name=office))
            for term in proposal.get("search_terms") or []:
                if term and term not in mention.terms:
                    mention.terms.append(term)
            mention.holders.append({
                "qid": row.get("qid"), "start": proposal.get("start"),
                "end": proposal.get("end"), "quote": proposal.get("quote", ""),
            })
    placed: dict = {}
    if mentions and not args.no_resolve:
        print(f"\nplacing {len(mentions)} named offices", file=sys.stderr)
        if country_qid is None:
            # No country means no index to build, so fall back to the label
            # search. Weaker on every axis — English prefixes, 30 hits, one
            # literal query — but a spec with no country has nothing better.
            print("  no country QID; falling back to the label search",
                  file=sys.stderr)
            legacy = resolve_offices(session, list(mentions), None,
                                     log=lambda m: print(f"  {m}", file=sys.stderr))
            placed = {n: v["qid"] for n, v in legacy.items() if v["qid"]}
            (out / f"{name}_offices.json").write_text(
                json.dumps(legacy, indent=1, ensure_ascii=False))
        else:
            office_index = index_for_country(session, country_qid)
            print(f"  index: {len(office_index)} offices in {country_qid}",
                  file=sys.stderr)
            found = place_offices(
                session, office_index,
                sorted(mentions.values(), key=lambda m: m.name),
                prompt=args.rerank_prompt.read_text(),
                ledger_path=out / f"{name}_offices.jsonl",
                model=args.model, effort=args.effort, workers=args.workers,
                log=lambda m: print(f"  {m}", file=sys.stderr),
            )
            placed = {n: p.qid for n, p in found.items() if p.qid}
            (out / f"{name}_offices.json").write_text(json.dumps(
                {n: p.as_dict() for n, p in sorted(found.items())},
                indent=1, ensure_ascii=False))
            for kind in sorted({p.kind for p in found.values()}):
                n = sum(1 for p in found.values() if p.kind == kind)
                print(f"    {kind}: {n}", file=sys.stderr)
            vetoed = [p for p in found.values() if p.veto]
            for p in vetoed:
                print(f"    vetoed {p.office} -> {p.chosen} ({p.veto})",
                      file=sys.stderr)
            if placed:
                # Keep the invariant that every applied QID is in the gazetteer.
                gazetteer.entries.extend(
                    describe(session, sorted(set(placed.values()) - gazetteer.qids)))
            print(f"  placed {len(placed)} of {len(found)} names; gazetteer now "
                  f"{len(gazetteer.entries)} offices", file=sys.stderr)

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
        found = check(row, dossier, gazetteer, recorded=recorded,
                      resolved=placed, qualifiers=quals)
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
    if bucket_targets:
        # The single-target block below is meaningless here and actively
        # misleading: a bucket's `spec.target` is the generic class item
        # (`Q68081922` ministr vlády) that nobody actually holds, so it reports
        # 0 recorded tenures and files every real answer under "other offices".
        score_bucket(report, cohort, placed, mentions)
        return

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
