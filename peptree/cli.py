"""peptree: repair one country's position items.

    python -m peptree.cli country <cc>  # derive the country's config from data (no model calls)
    python -m peptree.cli load <cc>     # discover, filter, store items and gaps
    python -m peptree.cli repair <cc>   # ask, decide, render and parse-check the .qs
    python -m peptree.cli report <cc>   # funnel, matrix and skips; written beside the .qs

Every run writes one file per country and day, `data/peptree/<cc>/<cc>-<date>.qs`,
holding every lane's statements, with its report as `<cc>-<date>.md` beside it.
    python -m peptree.cli write <cc>    # pre-flight and parse-check the latest .qs (dry)
    python -m peptree.cli write <cc> --submit   # ...then upload it once and poll to the end
    python -m peptree.cli status <batch_id> [--wait]
    python -m peptree.cli sweep plan|table|run <n>   # the batched sweep, ledger in peptree/sweep.md
    python -m peptree.cli audit <n>                  # every line of batch n with labels, and what to look at

Only `write --submit` edits Wikidata, through QuickStatements under the
account in QS_USERNAME / QS_TOKEN.
"""

import argparse
import sys
from collections import Counter
from pathlib import Path

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


def cmd_write(cc: str, submit: bool) -> None:
    path = qs.latest(cc)
    if path is None:
        sys.exit(f"no run file for {cc}; run `repair {cc}` first")
    row = wd.conn().execute("SELECT parse_ok FROM ptree_run WHERE qs_path = %s ORDER BY id DESC LIMIT 1",
                            (str(path),)).fetchone()
    if row is None or not row[0]:
        sys.exit(f"{path} was not parse-checked OK; re-run `repair {cc}`")
    text = path.read_text()
    lines = text.splitlines()
    if not lines:
        sys.exit(f"{path} is empty: nothing to write")
    day = __import__("datetime").date.fromisoformat(path.stem[len(cc) + 1:])
    names = {m.group(0)[4:-3] for line in lines if (m := qs.SUMMARY_RE.search(line))}
    if len(names) != 1:
        sys.exit(f"{path}: lines carry {len(names)} batch names, expected one")
    name = names.pop()
    if not name.startswith("peptree ") or not name.endswith(f" {cc} {day.isoformat()}"):
        sys.exit(f"{path}: batch name {name!r} does not match the file")
    by_prop = Counter(p for _, p, _ in qs.statements(lines))
    log(f"{path}: {len(lines)} lines on {len({q for q, _, _ in qs.statements(lines)})} items; {dict(by_prop)}")
    errors = qs.validate(lines)
    if errors:
        sys.exit("local validation failed:\n  " + "\n  ".join(errors[:20]))
    problems = qs.preflight(cc, lines)
    if problems:
        sys.exit(f"pre-flight against live state failed ({len(problems)}):\n  " + "\n  ".join(problems[:30]))
    ok, detail, _ = qs.parse_commands(text)
    log(f"QS parse {'OK' if ok else 'FAILED'}: {detail}")
    if not ok:
        sys.exit(1)
    previous = qs.submitted(name)
    if previous is not None:
        sys.exit(f"{name!r} was already submitted as batch {previous}; see `status {previous}`")
    if not submit:
        log(f"dry run: would submit {name!r}; credentials {'present' if qs.credentials() else 'MISSING'}")
        return
    if qs.credentials() is None:
        sys.exit("QS_USERNAME / QS_TOKEN are not set")
    batch_id = qs.submit(cc, path, text, name)
    log(f"submitted batch {batch_id}: {qs.EDITGROUPS.format(batch_id)}")
    show(qs.poll(batch_id, log=log))


def show(result: dict) -> None:
    print(f"status: {result['status']}  counts: {result['counts']}  {result['editgroup']}")
    for e in result["errors"]:
        print(f"  ERROR #{e.get('num')}: {e.get('message')}  {e.get('json')}")


def cmd_status(batch_id: int, wait: bool) -> None:
    if wait:
        show(qs.poll(batch_id, log=log))
        return
    status, counts, _ = qs.batch_info(batch_id)
    errs = qs.errors(batch_id)
    qs.record(batch_id, status, counts, errs)
    show({"status": status, "counts": counts, "errors": errs, "editgroup": qs.EDITGROUPS.format(batch_id)})


def main() -> None:
    if sys.argv[1:2] in (["sweep"], ["audit"]):
        wd.init()
        from peptree import audit, sweep
        (sweep if sys.argv[1] == "sweep" else audit).main(sys.argv[2:])
        return
    parser = argparse.ArgumentParser(prog="peptree")
    parser.add_argument("command", choices=["country", "load", "repair", "report", "write", "status"])
    parser.add_argument("cc", help="country code, or the batch id for `status`")
    parser.add_argument("--submit", action="store_true", help="write: actually upload (default is dry)")
    parser.add_argument("--wait", action="store_true", help="status: poll until the batch finishes")
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
    elif args.command == "write":
        cmd_write(args.cc, args.submit)
    elif args.command == "status":
        cmd_status(int(args.cc), args.wait)
    else:
        print(report.report(args.cc))
        log(f"{report.write(args.cc)}: report")


if __name__ == "__main__":
    main()
