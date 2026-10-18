"""Run one country end to end: load, decide, rules, link check, person match, run file, report."""

from typing import Callable

from peploop.corp import actors as actormod
from peploop.corp import country as countries
from peploop.corp import decide, load, match, qs, report, rules, verify


def run(cc: str, limit: int | None = None, no_ask: bool = False, reload: bool = True,
        only: set[str] | None = None, log: Callable[[str], None] = print) -> str:
    """Write the country's run file and report; returns the report's path.

    `no_ask` re-decides from the answer ledger without model calls (and
    without reloading); `only` limits the asking to these enterprises.
    """
    if reload and not no_ask:
        load.load(cc, log)
    answered = decide.from_ledger(cc) if no_ask else decide.decide(cc, limit=limit, log=log, only=only)
    if not no_ask:
        # Every answer on the ledger counts, not only this pass's: a limited
        # pass must not drop what an earlier one decided.
        answered = decide.from_ledger(cc)
    items = {it["qid"]: it for it in load.items(cc)}
    actors = actormod.read(cc)
    lines, decisions, removals = rules.decide(cc, answered, items, actors)
    # Every link the rules would write is checked against its quote, and the
    # body planned again without the ones the check refuses.
    refused = verify.refused(cc, decisions, answered, log)
    if refused:
        lines, decisions, removals = rules.decide(cc, answered, items, actors, refused=refused)
    # A seat the rules would write but for a link to its person: the name is
    # searched, and the candidate's own page checked against the seat.
    seats = match.unlinked(decisions, answered)
    if seats:
        found = match.resolve(cc, seats, load.langs(countries.state_qid(cc)), log,
                              citizens=frozenset(countries.current_qids(cc)))
        matched = {k: o["qid"] for k, o in found.items() if o["qid"]}
        if matched:
            lines, decisions, removals = rules.decide(cc, answered, items, actors, refused=refused, matched=matched)
    errors = qs.validate(lines)
    if errors:
        raise SystemExit("refused: " + "; ".join(errors[:5]))
    rules.store(cc, decisions)
    queued = rules.queue_removals(cc, removals)
    path = qs.write(cc, lines)
    log(f"{path}: {len(lines)} lines from {len(answered)} answered bodies; {queued} contradicted markers proposed for removal")
    return report.write(cc)
