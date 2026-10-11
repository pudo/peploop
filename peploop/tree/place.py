"""Repair one place's position items: derive its country, load its offices, decide their gaps, report.

Every run writes one file per day, `data/peptree/<cc>/<cc>-<date>.qs`, holding
every lane's statements, with its report as `<cc>-<date>.md` beside it. That
file is what the place would add now; it is never sent itself. Only
`peploop.cli tree send --submit` edits Wikidata.
"""

import sys

from peploop.tree import country as countries
from peploop.tree import gaps, load, qs, repair, report, rules, sweep, wd


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def load_place(cc: str) -> None:
    load.load(cc, log)
    ctx = gaps.Context(cc, load.items(cc))
    log(f"gaps: {gaps.store_gaps(cc, ctx)} slots")


def repair_place(cc: str, limit: int | None, no_ask: bool = False) -> None:
    state = repair.Run(cc)
    if no_ask:
        reqs = [r for r in repair.from_ledger(cc) if r["qid"] in state.gaps and r["qid"] in state.by_qid]
        # A stale ledger row may ask about a gap that has since closed.
        for r in reqs:
            r["candidates"] = {p: c for p, c in r["candidates"].items() if p in state.gaps[r["qid"]]}
    else:
        reqs = repair.repair(cc, limit=limit, log=log)
    decisions = rules.run_rules(cc, reqs, state, log)
    lines = qs.render(decisions, qs.batch_name(cc))
    errors = qs.validate(lines)
    if errors:
        log("local validation failed:\n  " + "\n  ".join(errors[:20]))
    path = qs.write(cc, lines)
    log(f"{path}: {len(lines)} lines; {len(errors)} local errors")
    md = report.write(cc)
    log(f"{md}: report")


def show_country(cc: str) -> None:
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


def run(cc: str, limit: int | None, no_ask: bool, large_ok: bool) -> None:
    """Derive the place's config, load it, and repair it -- unless it is large and nobody said so."""
    show_country(cc)
    load_place(cc)
    asked = sweep.asked(cc)
    if asked > sweep.LARGE and not (large_ok or no_ask or limit):
        log(f"{cc}: {asked} items to ask, above {sweep.LARGE}; pass --large to repair it anyway")
        sys.exit(sweep.LARGE_EXIT)
    repair_place(cc, limit, no_ask)
