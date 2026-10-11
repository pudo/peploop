"""peptree: repair one country's position items.

    python -m peptree.cli country <cc>  # derive the country's config from data (no model calls)
    python -m peptree.cli load <cc>     # discover, filter, store items and gaps
    python -m peptree.cli repair <cc>   # ask, decide, render and check the .qs
    python -m peptree.cli report <cc>   # funnel, matrix and skips; written beside the .qs

Every run writes one file per country and day, `data/peptree/<cc>/<cc>-<date>.qs`,
holding every lane's statements, with its report as `<cc>-<date>.md` beside it.
That file is what the country would add now; it is never sent itself.
    python -m peptree.cli sweep plan|table|run <n>   # the batched sweep, ledger in peptree/sweep.md
    python -m peptree.cli audit <n>                  # every line of batch n with labels, and what to look at
    python -m peptree.cli outbox [--submit] [--batch n]  # what has not gone out yet; --submit sends it
    python -m peptree.cli outbox --status            # the send ledger, failures, revert candidates
    python -m peptree.cli strike <qid> <prop> [value] --reason "…"  # never send it; undo it if it landed
    python -m peptree.cli removals [approve|reject <guid…> | submit]  # statements to take back off Wikidata
    python -m peptree.cli status <batch_id>          # read a QS3 batch back: status and failed lines

Only `outbox --submit` and `removals submit` edit Wikidata, each as one QuickStatements 3.0 batch.
"""

import argparse
import sys

from peploop import qs3
from peptree import country as countries
from peptree import gaps, load, qs, repair, report, rules, wd


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def cmd_load(cc: str) -> None:
    load.load(cc, log)
    ctx = gaps.Context(cc, load.items(cc))
    log(f"gaps: {gaps.store_gaps(cc, ctx)} slots")


def cmd_repair(cc: str, limit: int | None, no_ask: bool = False) -> None:
    run = repair.Run(cc)
    if no_ask:
        reqs = [r for r in repair.from_ledger(cc) if r["qid"] in run.gaps and r["qid"] in run.by_qid]
        # A stale ledger row may ask about a gap that has since closed.
        for r in reqs:
            r["candidates"] = {p: c for p, c in r["candidates"].items() if p in run.gaps[r["qid"]]}
    else:
        reqs = repair.repair(cc, limit=limit, log=log)
    decisions = rules.run_rules(cc, reqs, run, log)
    lines = qs.render(decisions, qs.batch_name(cc))
    errors = qs.validate(lines)
    if errors:
        log("local validation failed:\n  " + "\n  ".join(errors[:20]))
    path = qs.write(cc, lines)
    detail = f"{len(errors)} local errors"
    wd.conn().execute("INSERT INTO ptree_run (country, qs_path, lines, parse_ok, parse_detail) VALUES (%s,%s,%s,%s,%s)",
                      (cc, str(path), len(lines), not errors, detail))
    log(f"{path}: {len(lines)} lines; {detail}")
    md = report.write(cc)
    log(f"{md}: report")


def cmd_country(cc: str) -> None:
    c = countries.get(cc)
    cfg = countries.config(cc)
    info = wd.labels_of(sorted(c.home) + sorted(c.type_words))
    print(f"{cc}: {c.qid} {wd.name(info.get(c.qid))}; languages {', '.join(c.langs)}")
    for p, u in sorted(c.predecessors.items()):
        fed = f"; P17 = {u} {wd.name(info.get(u))}" if u != p else "; P17 = itself"
        print(f"  predecessor {p} {wd.name(info.get(p))} ({c.provenance.get(p)}){fed}; "
              f"{len(countries.distinctive(c, p))} distinctive names")
    sub = cfg["subdivisions"]
    print(f"  places: {len(sub['l1'])} first-level, {len(sub['l2'])} second-level units")
    for t, ws in sorted(c.type_words.items()):
        print(f"  level words {t} {wd.name(info.get(t))}: {' '.join(ws)}")
    print(f"  union-lane name regex: {countries.sparql_name_regex(c) or '(none)'}")


def cmd_status(batch_id: int) -> None:
    row = qs3.info(batch_id)
    print(f"status: {row['status']['display']}  counts: {row.get('summary')}  {qs3.EDITGROUPS.format(batch_id)}")
    for raw in qs3.failed(batch_id):
        print(f"  FAILED: {raw}")


def main() -> None:
    if sys.argv[1:2] in (["sweep"], ["audit"], ["outbox"], ["removals"], ["strike"]):
        wd.init()
        from peptree import audit, outbox, removals, sweep
        {"sweep": sweep.main, "audit": audit.main, "outbox": outbox.main, "removals": removals.main,
         "strike": removals.strike_main}[sys.argv[1]](sys.argv[2:])
        return
    parser = argparse.ArgumentParser(prog="peptree")
    parser.add_argument("command", choices=["country", "load", "repair", "report", "status"])
    parser.add_argument("cc", help="country code, or the batch id for `status`")
    parser.add_argument("--no-ask", action="store_true", help="repair: re-decide from the ledger, no model calls")
    parser.add_argument("--limit", type=int, default=None, help="repair: ask about the first N items only")
    args = parser.parse_args()
    wd.init()
    if args.command == "country":
        cmd_country(args.cc)
    elif args.command == "load":
        cmd_load(args.cc)
    elif args.command == "repair":
        cmd_repair(args.cc, args.limit, args.no_ask)
    elif args.command == "status":
        cmd_status(int(args.cc))
    else:
        print(report.report(args.cc))
        log(f"{report.write(args.cc)}: report")


if __name__ == "__main__":
    main()
