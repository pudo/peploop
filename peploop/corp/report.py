"""Write a country's run report: the funnel, what each enterprise gets, and the residue.

The residue is what a run cannot write and does not ask about: listed holdings
without an item, seats whose person has no item the article links, and
enterprises whose control the articles leave unclear.
"""

from collections import Counter, defaultdict
from typing import Any

from peploop import memo, positions
from peploop.corp import country as countries
from peploop.corp import decide, load, qs, wd


def report(cc: str) -> str:
    conn = wd.conn()
    loaded = conn.execute("SELECT coalesce(dropped, 'kept'), count(*) FROM pcorp_item WHERE country = %s"
                          " GROUP BY 1 ORDER BY 2 DESC", (cc,)).fetchall()
    rows = conn.execute("SELECT qid, prop, value, detail, disposition, rule FROM pcorp_decision"
                        " WHERE country = %s ORDER BY qid, n", (cc,)).fetchall()
    spent, calls = decide.cost(cc)
    kinds = {r["qid"]: r["answer"]["kind"] for r in decide.from_ledger(cc)}
    by_qid: dict[str, list[tuple[Any, ...]]] = defaultdict(list)
    for r in rows:
        by_qid[r[0]].append(r)
    gates = Counter(r[5] for r in rows if r[1] == "-")
    applied = Counter(r[1] for r in rows if r[4] == "apply")
    skipped = Counter(r[5] for r in rows if r[1] != "-" and r[4] == "skip")
    refs = {r[0] for r in rows} | {r[2] for r in rows if r[2]}
    info = memo.labels_of(sorted(refs), load.label_langs(load.langs(positions.country_qid(cc))))
    name = lambda q: next(iter((info.get(q) or {}).get("labels", {}).values()), "")  # noqa: E731
    path = qs.latest(cc)
    n_lines = len(path.read_text().splitlines()) if path else 0
    out = [f"# pepcorp {cc}", "",
           "## Funnel", "",
           "- loaded: " + ", ".join(f"{k} {v}" for k, v in loaded),
           f"- decided: {len(by_qid)} enterprises, {calls} model calls, ${spent:.2f}",
           "- not written on: " + ", ".join(f"{k} {v}" for k, v in gates.most_common()),
           f"- written on: {len(by_qid) - sum(gates.values())} enterprises",
           "- statements applied: " + ", ".join(f"{k} {v}" for k, v in applied.most_common()),
           "- statements skipped: " + ", ".join(f"{k} {v}" for k, v in skipped.most_common()),
           f"- run file: {path} ({n_lines} lines)", ""]
    out += ["## Enterprises written on", ""]
    for qid, rs in by_qid.items():
        if any(r[1] == "-" for r in rs):
            continue
        out.append(f"### {qid} {name(qid)} ({kinds.get(qid, '?')})")
        for _, prop, value, detail, disp, rule in rs:
            what = f"{value} {name(value)}" if value else detail.get("name", "")
            extra = "; ".join(f"{k} {v.get('id') or v.get('time', '')[1:11] or v.get('amount')}"
                              for k, v in detail.items() if isinstance(v, dict))
            out.append(f"- {'✓' if disp == 'apply' else '·'} {prop} {what}" + (f" ({extra})" if extra else "")
                       + ("" if disp == "apply" else f" — {rule}"))
        out.append("")
    out += ["## Residue", "", "### Seats whose person has no linked item", ""]
    for qid, rs in by_qid.items():
        for r in rs:
            if r[5] == "person_unlinked":
                out.append(f"- {qid} {name(qid)}: {r[3].get('name')} ({r[1]})")
    out += ["", "### Control unclear in the articles", ""]
    out += [f"- {qid} {name(qid)}" for qid, rs in by_qid.items() if any(r[5] == "control:unclear" for r in rs)]
    out += ["", "### Listed holdings without an item", ""]
    out += [f"- {e.get('name')} ({e.get('holder')})" for e in countries.get(cc).unmatched()]
    return "\n".join(out) + "\n"


def write(cc: str) -> str:
    path = qs.run_path(cc, suffix=".md")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report(cc))
    return str(path)
