"""Run one country end to end: load, decide, rules, run file, report."""

from typing import Callable

from peploop.corp import actors as actormod
from peploop.corp import decide, load, qs, report, rules


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
    lines, decisions = rules.decide(cc, answered, items, actormod.read(cc))
    errors = qs.validate(lines)
    if errors:
        raise SystemExit("refused: " + "; ".join(errors[:5]))
    rules.store(cc, decisions)
    path = qs.write(cc, lines)
    log(f"{path}: {len(lines)} lines from {len(answered)} answered enterprises")
    return report.write(cc)
