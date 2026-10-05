"""Run peptree over every non-OECD country and territory, five at a time.

The ledger is `peptree/sweep.md`: one row per place, its batch, where it stands
and what its run produced. It is what tells a session which batch is next and
which places wait on a fix, so it is committed while the `.qs` files stay in
`data/`. Status and notes are written by hand in review; every other column is
rewritten from the database by `table`. A batch is the unit of running and
review only: what goes to Wikidata leaves through `outbox`, whatever the batch.

    python -m peptree.cli sweep plan       # (re)build the universe and its batches
    python -m peptree.cli sweep run <n>    # country → load → repair for batch n
    python -m peptree.cli sweep table      # refresh the machine columns
"""

import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from rigour.territories import get_territories

from peptree import qs, repair, wd

LEDGER = Path(__file__).resolve().parent / "sweep.md"
BATCH_SIZE = 5
#: OECD members are out of scope: their PEP coverage comes from other sources.
OECD = frozenset("at au be ca ch cl co cr cz de dk ee es fi fr gb gr hu ie il is it jp kr lt lu lv mx nl no"
                 " nz pl pt se si sk tr us".split())
#: Codes rigour gives places with no government of their own to hold office in: the
#: uninhabited, a military base, a region of an OECD state, and the non-places.
NO_OFFICES = frozenset("aq bv cp dg hm ic ip tf um zz eu un".split())
STEPS = ("country", "load", "repair")
#: Items with a gap above which a place's repair waits for a decision: Brazil's
#: 5,056 would have cost $100-200 before the type/class swap was understood.
LARGE = 300
COLUMNS = ("cc", "name", "region", "batch", "status", "run", "kept", "lines", "by property", "cost", "chunks", "notes")
#: Columns a person writes; `table` and `plan` keep them as found.
HAND = ("status", "notes")


def universe() -> list[dict[str, str]]:
    """Every place in scope, ordered so neighbours share a batch."""
    out = []
    for t in get_territories():
        if t.is_historical or not t.qid or len(t.code) != 2 or t.code in OECD | NO_OFFICES:
            continue
        out.append({"cc": t.code, "name": t.name, "region": t.region or "", "subregion": t.subregion or ""})
    return sorted(out, key=lambda r: (r["region"], r["subregion"], r["name"]))


def read() -> dict[str, dict[str, str]]:
    """The ledger's rows by country code; empty when there is none yet."""
    if not LEDGER.exists():
        return {}
    rows = {}
    for line in LEDGER.read_text().splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != len(COLUMNS) or cells[:2] == ["cc", "name"] or set(cells[0]) <= {"-"}:
            continue
        rows[cells[0]] = dict(zip(COLUMNS, cells))
    return rows


def write(rows: list[dict[str, str]]) -> Path:
    done = Counter(r["status"].split(":")[0] for r in rows)
    head = ["# peptree sweep", "",
            "Every non-OECD country and territory, in batches of five by region. Status is "
            "`pending → run → reviewed → submitted`, or `blocked: <why>`; `status` and `notes` are "
            "written by hand and survive `sweep table`; `chunks` are the outbox chunks its lines went out in.", "",
            "Progress: " + ", ".join(f"{k} {n}" for k, n in sorted(done.items())), "",
            "| " + " | ".join(COLUMNS) + " |", "|" + "---|" * len(COLUMNS)]
    body = ["| " + " | ".join(r.get(c, "").replace("|", "/") for c in COLUMNS) + " |" for r in rows]
    LEDGER.write_text("\n".join(head + body) + "\n")
    return LEDGER


def plan() -> Path:
    """Assign batches: places already in the ledger keep theirs, new ones fill batches within a region."""
    old = read()
    places = universe()
    rows, fresh = [], []
    for p in places:
        row = {"cc": p["cc"], "name": p["name"], "region": f"{p['region']} / {p['subregion']}",
               "status": "pending", **{c: "" for c in COLUMNS if c not in ("cc", "name", "region", "status")}}
        if p["cc"] in old:
            row.update({c: old[p["cc"]][c] for c in (*HAND, "batch")})
        elif qs.latest(p["cc"]) is not None:
            row.update({"batch": "0", "status": "run"})  # run before the sweep existed
        else:
            fresh.append((p, row))
        rows.append(row)
    taken = [int(r["batch"]) for r in rows if r["batch"].isdigit()]
    n = max(taken, default=0)
    group: str | None = None
    filled = BATCH_SIZE
    for p, row in fresh:
        if p["region"] != group or filled == BATCH_SIZE:
            n, filled, group = n + 1, 0, p["region"]
        row["batch"] = str(n)
        filled += 1
    return write(fill(rows))


def stats(cc: str) -> dict[str, str]:
    """The machine columns for one place, from its latest run."""
    path = qs.latest(cc)
    if path is None:
        return {}
    lines = path.read_text().splitlines()
    by = Counter(p for _, p, _ in qs.statements(lines))
    kept = wd.conn().execute("SELECT count(*) FROM ptree_item WHERE country = %s AND dropped IS NULL", (cc,)).fetchone()[0]
    usd, _ = repair.cost(cc)
    chunks = [c for (c,) in wd.conn().execute(
        "SELECT DISTINCT chunk FROM ptree_emitted WHERE country = %s ORDER BY 1", (cc,)).fetchall()]
    return {"run": path.stem[len(cc) + 1:], "kept": str(kept), "lines": str(len(lines)),
            "by property": " ".join(f"{p} {n}" for p, n in sorted(by.items())), "cost": f"${usd:.2f}",
            "chunks": " ".join(f"{c:03d}" for c in chunks)}


def fill(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    for row in rows:
        row.update(stats(row["cc"]))
    return rows


def table() -> Path:
    old = read()
    rows = [dict(old[p["cc"]]) for p in universe() if p["cc"] in old]
    return write(fill(rows))


def members(batch: int) -> list[str]:
    return [cc for cc, r in read().items() if r["batch"] == str(batch)]


def asked(cc: str) -> int:
    """How many items the repair would ask the model about."""
    return wd.conn().execute("SELECT count(DISTINCT qid) FROM ptree_gap WHERE country = %s", (cc,)).fetchone()[0]


def run(batch: int, log: Any = print) -> list[str]:
    """Run every pending place of a batch in sequence; return the places run."""
    ccs = members(batch)
    if not ccs:
        sys.exit(f"batch {batch} has no places; run `sweep plan` first")
    rows, done = read(), []
    for cc in ccs:
        if rows[cc]["status"] != "pending" and not rows[cc]["status"].startswith("blocked: crash"):
            log(f"{cc}: {rows[cc]['status']}, not re-run")
            continue
        out = qs.OUT_DIR / cc
        out.mkdir(parents=True, exist_ok=True)
        failed, large = None, 0
        for step in STEPS:
            if step == "repair":
                large = asked(cc)
                if large > LARGE:
                    break
            with open(out / f"{step}-{cc}.log", "w") as fh:
                code = subprocess.call([sys.executable, "-m", "peptree.cli", step, cc], stdout=fh, stderr=subprocess.STDOUT)
            if code:
                failed = step
                break
        rows = read()  # the ledger may have been edited by hand while this place ran
        rows[cc]["status"] = (f"blocked: crash in {failed}" if failed else
                              f"blocked: large ({large} items to ask)" if large > LARGE else "run")
        log(f"{cc}: {rows[cc]['status']}")
        write(fill([rows[p["cc"]] for p in universe() if p["cc"] in rows]))
        done.append(cc)
    return done


def main(args: list[str]) -> None:
    if args[:1] == ["plan"]:
        print(plan())
    elif args[:1] == ["table"]:
        print(table())
    elif args[:1] == ["run"] and len(args) == 2:
        done = run(int(args[1]), log=lambda m: print(m, file=sys.stderr, flush=True))
        lines = sum(len(p.read_text().splitlines()) for cc in done if (p := qs.latest(cc)))
        print(f"batch {args[1]}: ran {' '.join(done) or 'nothing'}, {lines} lines proposed; export with `outbox`")
    else:
        sys.exit("usage: sweep plan | table | run <batch>")
