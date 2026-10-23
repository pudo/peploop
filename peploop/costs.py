"""Tally what every model pass has spent, from the ledgers each one keeps.

Each pass records its own calls with their token usage, in seven tables. This
reads them all into one table of calls, tokens and list-price dollars, so a
pass that has grown heavy, or a run that re-asked more than it meant to, shows
before the next run rather than on the bill.

    .venv/bin/python -m peploop.cli cost [--since 2026-10-01] [--by pass|model|country|week]
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Iterable

from peploop import db, llm

#: One query per ledger, each returning (pass, model, country, usage, created_at).
#: A peploop row carries no country; pepcorp's three passes share one table and
#: are told apart by what their request holds.
SOURCES = (
    "SELECT 'extract', model, NULL, usage_json, created_at FROM extraction",
    "SELECT 'resolve', model, NULL, usage_json, created_at FROM resolution",
    "SELECT 'verify', model, NULL, usage_json, created_at FROM verification",
    "SELECT 'mint:' || pass, model, country, usage_json, created_at FROM mint_call",
    "SELECT 'title_en', model, NULL, usage_json, created_at FROM title_en_call",
    "SELECT 'corp:' || CASE WHEN request ? 'links' THEN 'decide' WHEN request ? 'link' THEN 'verify'"
    " WHEN request ? 'candidate' THEN 'match' ELSE 'other' END, model, country, usage, created_at FROM pcorp_call",
    "SELECT 'tree', model, country, usage, created_at FROM ptree_call",
)

TOKENS = ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens", "output_tokens")

BY = ("pass", "model", "country", "week")


@dataclass
class Tally:
    calls: int = 0
    tokens: dict[str, int] = field(default_factory=lambda: dict.fromkeys(TOKENS, 0))
    dollars: float = 0.0
    #: Calls on a model `llm.PRICES` does not price: counted, never summed as free.
    unpriced: int = 0


def group(row: tuple[str, str, str | None, Any], by: str) -> str:
    """The key a call is tallied under."""
    pass_, model, country, created = row
    if by == "model":
        return model
    if by == "country":
        return country or "-"
    if by == "week":
        iso = created.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"
    return f"{pass_} {model}"


def tally(rows: Iterable[tuple[str, str, str | None, dict[str, int] | None, Any]], by: str) -> dict[str, Tally]:
    """Sum calls, tokens and dollars per group; a row with no usage is skipped."""
    out: dict[str, Tally] = defaultdict(Tally)
    for pass_, model, country, usage, created in rows:
        if not usage:
            continue
        t = out[group((pass_, model, country, created), by)]
        t.calls += 1
        for k in TOKENS:
            t.tokens[k] += usage.get(k) or 0
        dollars = llm.cost(model, usage)
        if dollars is None:
            t.unpriced += 1
        else:
            t.dollars += dollars
    return dict(out)


def read(since: date | datetime | None = None) -> list[tuple[str, str, str | None, dict[str, int] | None, Any]]:
    """Every recorded call of every pass, optionally from a day or a moment on."""
    rows = []
    for sql in SOURCES:
        if since:
            sql = f"SELECT * FROM ({sql}) AS calls(pass, model, country, usage, created_at) WHERE created_at >= %s"
        rows += db.conn().execute(sql, (since,) if since else ()).fetchall()
    return rows


def now() -> datetime:
    """The database's clock, which stamps every ledger row: the start of a run's tally."""
    return db.conn().execute("SELECT now()").fetchone()[0]


def spent(since: datetime, passes: tuple[str, ...]) -> str:
    """One line on what these passes asked and cost since a moment, for the end of a run."""
    tallies = tally((r for r in read(since) if r[0] in passes), "pass")
    calls = sum(t.calls for t in tallies.values())
    dollars = sum(t.dollars for t in tallies.values())
    unpriced = sum(t.unpriced for t in tallies.values())
    return (f"spent: {calls} model calls ({', '.join(passes)}), ${dollars:.2f} at list price"
            + (f", {unpriced} on unpriced models" if unpriced else ""))


def render(tallies: dict[str, Tally]) -> list[str]:
    """A table, the heaviest group first, with per-call averages and a total."""
    lines = [f"{'group':34} {'calls':>8} {'in/call':>8} {'cache_r':>8} {'cache_w':>8} {'out/call':>8}"
             f" {'$':>9} {'$/call':>7}"]
    for key, t in sorted(tallies.items(), key=lambda kv: -kv[1].dollars):
        n = t.calls
        note = f"  ({t.unpriced} unpriced)" if t.unpriced else ""
        lines.append(f"{key:34} {n:8} {t.tokens['input_tokens'] // n:8} {t.tokens['cache_read_input_tokens'] // n:8}"
                     f" {t.tokens['cache_creation_input_tokens'] // n:8} {t.tokens['output_tokens'] // n:8}"
                     f" {t.dollars:9.2f} {t.dollars / n:7.4f}{note}")
    total = sum(t.dollars for t in tallies.values())
    calls = sum(t.calls for t in tallies.values())
    unpriced = sum(t.unpriced for t in tallies.values())
    lines.append(f"{'total':34} {calls:8} {'':8} {'':8} {'':8} {'':8} {total:9.2f}"
                 + (f"  ({unpriced} calls on unpriced models not counted)" if unpriced else ""))
    return lines


#: How many of a pass's newest calls the estimate reads.
ESTIMATE_SAMPLE = 2000


def estimate(pass_: str, model: str, n: int, batched: bool = False) -> float | None:
    """What asking a pass n more questions on a model will cost, from its own history.

    The mean of the pass's recent calls on that model, at the live price
    (a batched call counted at what it would have cost live), times n, and
    the batch discount when it goes out as batches. With no calls on that
    model, the pass's calls on others, scaled by the two models' prices; with
    no history at all, None.
    """
    rows = []
    for sql in SOURCES:
        rows += db.conn().execute(
            f"SELECT model, usage FROM ({sql}) AS calls(pass, model, country, usage, created_at)"
            " WHERE pass = %s AND usage IS NOT NULL ORDER BY created_at DESC LIMIT %s",
            (pass_, ESTIMATE_SAMPLE)).fetchall()
    if not rows or model not in llm.PRICES:
        return None
    mine = [r for r in rows if r[0] == model]
    scale = 1.0
    if not mine:
        mine = [r for r in rows if r[0] in llm.PRICES]
        if not mine:
            return None
        other = llm.PRICES[mine[0][0]]
        scale = (llm.PRICES[model][0] + llm.PRICES[model][1]) / (other[0] + other[1])
        mine = [r for r in mine if r[0] == mine[0][0]]
    each = [llm.cost(m, {k: v for k, v in u.items() if k != "batch"}) for m, u in mine]
    mean = sum(each) / len(each) * scale
    return mean * n * (llm.BATCH_DISCOUNT if batched else 1.0)
