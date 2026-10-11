"""peptree: repair every country's position items, and send the repairs to Wikidata.

    python -m peptree.cli place <cc>                 # country → load → repair → report for one place
    python -m peptree.cli sweep plan|table|run <n>   # the batched sweep, ledger in peptree/sweep.md
    python -m peptree.cli audit <n>                  # every line of batch n with labels, and what to look at
    python -m peptree.cli send [--submit] [--batch n]  # what has not gone out yet; --submit sends it
    python -m peptree.cli send --status              # the send ledger, failures, strikes, open removals
    python -m peptree.cli strike <qid> <prop> [value] --reason "…"  # never send it; undo it if it landed
    python -m peptree.cli removals [approve|reject <guid…>]         # statements to take back off Wikidata

Every place's run writes one file per day, `data/peptree/<cc>/<cc>-<date>.qs`,
holding every lane's statements, with its report as `<cc>-<date>.md` beside it.
That file is what the place would add now; it is never sent itself. Only
`send --submit` edits Wikidata, as QuickStatements 3.0 batches.
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


def cmd_place(cc: str, limit: int | None, no_ask: bool, large_ok: bool) -> None:
    """Derive the place's config, load it, and repair it -- unless it is large and nobody said so."""
    from peptree import sweep
    cmd_country(cc)
    cmd_load(cc)
    asked = sweep.asked(cc)
    if asked > sweep.LARGE and not (large_ok or no_ask or limit):
        log(f"{cc}: {asked} items to ask, above {sweep.LARGE}; pass --large to repair it anyway")
        sys.exit(sweep.LARGE_EXIT)
    cmd_repair(cc, limit, no_ask)


def main() -> None:
    if sys.argv[1:2] in (["sweep"], ["audit"], ["send"], ["removals"], ["strike"]):
        wd.init()
        from peptree import audit, outbox, sweep
        {"sweep": sweep.main, "audit": audit.main, "send": outbox.main, "removals": outbox.removals_main,
         "strike": outbox.strike_main}[sys.argv[1]](sys.argv[2:])
        return
    parser = argparse.ArgumentParser(prog="peptree")
    parser.add_argument("command", choices=["place"])
    parser.add_argument("cc", help="country code")
    parser.add_argument("--no-ask", action="store_true", help="re-decide from the ledger, no model calls")
    parser.add_argument("--limit", type=int, default=None, help="ask about the first N items only")
    parser.add_argument("--large", action="store_true", help="repair a large place too")
    args = parser.parse_args()
    wd.init()
    cmd_place(args.cc, args.limit, args.no_ask, args.large)


if __name__ == "__main__":
    main()
