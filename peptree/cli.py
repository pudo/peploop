"""peptree: repair one country's position items.

    python -m peptree.cli country <cc>  # derive the country's config from data (no model calls)
    python -m peptree.cli load <cc>     # discover, filter, store items and gaps
    python -m peptree.cli repair <cc>   # ask, decide, render and parse-check the .qs
    python -m peptree.cli report <cc>   # funnel, matrix and skips; written beside the .qs

Every run writes one file per country and day, `data/peptree/<cc>/<cc>-<date>.qs`,
holding every lane's statements, with its report as `<cc>-<date>.md` beside it.
That file is what the country would add now; it is never pasted itself.
    python -m peptree.cli sweep plan|table|run <n>   # the batched sweep, ledger in peptree/sweep.md
    python -m peptree.cli audit <n>                  # every line of batch n with labels, and what to look at
    python -m peptree.cli outbox [--status]          # what has not gone out yet, as ≤300-command chunks
    python -m peptree.cli status <batch_id>          # read a pasted QS batch back: status and errors

Nothing here edits Wikidata. The outbox's chunks in `data/peptree/outbox/` are
pasted into the QuickStatements importer by hand.
"""

import argparse
import sys

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
    ok, detail = qs.parse("\n".join(lines)) if lines else (True, "empty batch")
    wd.conn().execute("INSERT INTO ptree_run (country, qs_path, lines, parse_ok, parse_detail) VALUES (%s,%s,%s,%s,%s)",
                      (cc, str(path), len(lines), ok and not errors, detail))
    log(f"{path}: {len(lines)} lines; QS parse {'OK' if ok else 'FAILED'}: {detail}")
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


def show(result: dict) -> None:
    print(f"status: {result['status']}  counts: {result['counts']}  {result['editgroup']}")
    for e in result["errors"]:
        print(f"  ERROR #{e.get('num')}: {e.get('message')}  {e.get('json')}")


def cmd_status(batch_id: int) -> None:
    status, counts, _ = qs.batch_info(batch_id)
    errs = qs.errors(batch_id)
    show({"status": status, "counts": counts, "errors": errs, "editgroup": qs.EDITGROUPS.format(batch_id)})


def main() -> None:
    if sys.argv[1:2] in (["sweep"], ["audit"], ["outbox"]):
        wd.init()
        from peptree import audit, outbox, sweep
        {"sweep": sweep, "audit": audit, "outbox": outbox}[sys.argv[1]].main(sys.argv[2:])
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
