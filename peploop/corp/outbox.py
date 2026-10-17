"""Send a country's latest run file to Wikidata, once per line, through the joint send ledger.

    python -m peploop.cli corp send de             # reconcile; write what would go out to send/pending.qs
    python -m peploop.cli corp send de --submit    # additions as one QS3 batch, then approved removals
    python -m peploop.cli corp send de --qid Q9322 --submit   # only these enterprises' lines
    python -m peploop.cli corp send --status       # batches, failures, strikes, open removals

The run file says what a country's run would write *now*; the ledger
(`peploop/ledger.py`) says what has gone out and what a reviewer struck. A line
already sent, struck, or whose statement is live is not sent again. Lines
include `+` lines, which always create a statement: the ledger is what keeps
one from going out twice.
"""

import sys
from typing import Callable

from peploop import ledger, send
from peploop import qs as peploop_qs
from peploop.corp import qs

TOOL = "pepcorp"
DIR = qs.OUT_DIR / "send"
PENDING = DIR / "pending.qs"


def pending(cc: str, log: Callable[[str], None], qids: set[str] | None = None) -> list[str]:
    """The country's run-file lines not yet sent, not struck and not live; only on these items if given."""
    path = qs.latest(cc)
    lines = [line for line in (path.read_text().splitlines() if path else []) if line.strip()]
    if qids:
        lines = [line for line in lines if peploop_qs.parse(line)[1] in qids]
    taken = {k for k, *_ in ledger.edits("add")}
    todo = [line for line in lines if ledger.key(line) not in taken]
    vetoes = ledger.strikes()
    struck = [line for line in todo if ledger.struck(line, vetoes)]
    todo = [line for line in todo if line not in struck]
    live_now = send.live_keys(todo)
    todo = [line for line in todo if ledger.key(line) not in live_now]
    log(f"{cc}: proposed {len(lines)}, already out {len(lines) - len(todo) - len(struck) - len(live_now)}, "
        f"struck {len(struck)}, live {len(live_now)}, pending {len(todo)}")
    return todo


def run(cc: str, log: Callable[[str], None] = print, submit: bool = False, qids: set[str] | None = None) -> list[int]:
    """Reconcile, write the pending lines to `pending.qs`; with `submit`, send them and the approved removals.

    `qids` limits the batch to these enterprises: a first send of a few reviewed ones.
    """
    send.prepare(TOOL, log)
    lines = [peploop_qs.stamp(TOOL, line) for line in pending(cc, log, qids)]
    errors = qs.validate(lines)
    if errors:
        sys.exit("refused: " + "; ".join(errors[:5]))
    DIR.mkdir(parents=True, exist_ok=True)
    PENDING.write_text("\n".join(lines) + "\n" if lines else "")
    log(f"{PENDING}: {len(lines)} lines")
    if not submit:
        return []
    # Uncombined: an enterprise gets many statements at once, and QS3 failed
    # whole items of 6 to 11 lines when it folded them into one edit, with no
    # reason given; each line on its own landed.
    return send.dispatch(TOOL, [(cc, ledger.key(line), line, []) for line in lines], log, combine=False)
