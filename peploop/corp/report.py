"""Write a country's run report: the funnel, what each enterprise gets, and the residue.

The residue is what a run cannot write and does not ask about: listed holdings
without an item, seats whose person neither the article links nor the match
by name finds, enterprises whose control the articles leave unclear, and the
named-body rows of the state's AMLR list that no item resolves.
"""

from collections import Counter, defaultdict
from typing import Any

from peploop import memo
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
    seats = [r for r in rows if r[4] == "apply" and r[1] not in ("P31", "P127", "P749")]
    undated_total = Counter(r[1] for r in seats)
    undated = Counter(r[1] for r in seats if "P580" not in r[3] and "P582" not in r[3])
    via = Counter(r[3].get("via", "?") for r in seats)
    refs = {r[0] for r in rows} | {r[2] for r in rows if r[2]}
    info = memo.labels_of(sorted(refs), load.label_langs(load.langs(countries.state_qid(cc))))
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
           "- seats written, by how the person was found: " + ", ".join(
               f"{k} {via[k]}" for k in ("link", "anchor", "matched", "?") if via[k]),
           f"- seats written without a start or end: " + ", ".join(
               f"{p} {n}/{undated_total[p]}" for p, n in sorted(undated.items())),
           f"- contradicted markers proposed for removal: {sum(1 for r in rows if r[4] == 'remove')}",
           f"- run file: {path} ({n_lines} lines)", ""]
    out += listed(cc, rows, loaded_listed(cc))
    out += ["## Enterprises written on", ""]
    for qid, rs in by_qid.items():
        if any(r[1] == "-" for r in rs) and not any(r[4] in ("apply", "remove") for r in rs):
            continue
        out.append(f"### {qid} {name(qid)} ({kinds.get(qid, '?')})")
        for _, prop, value, detail, disp, rule in rs:
            what = f"{value} {name(value)}" if value else detail.get("name", "")
            if detail.get("via") == "matched":
                what += f" (matched by name: {detail.get('name')})"
            extra = "; ".join(f"{k} {v.get('id') or v.get('time', '')[1:11]}"
                              for k, v in detail.items() if isinstance(v, dict))
            mark = {"apply": "✓", "remove": "✗"}.get(disp, "·")
            out.append(f"- {mark} {prop} {what}" + (f" ({extra})" if extra else "")
                       + ("" if disp == "apply" else f" — {rule}"))
        out.append("")
    out += ["## Residue", "", "### Seats whose person has no linked or matched item", ""]
    for qid, rs in by_qid.items():
        for r in rs:
            if r[5] == "person_unlinked":
                out.append(f"- {qid} {name(qid)}: {r[3].get('name')} ({r[1]})")
    out += ["", "### Control unclear in the articles", ""]
    out += [f"- {qid} {name(qid)}" for qid, rs in by_qid.items() if any(r[5] == "control:unclear" for r in rs)]
    out += ["", "### Listed holdings without an item", ""]
    out += [f"- {e.get('name')} ({e.get('holder')})" for e in countries.get(cc).unmatched()]
    out += ["", "### Named bodies of the AMLR list without an item", ""]
    out += [f"- row {f.row}: {f.organisation or f.position}" for f in load.unresolved(cc)]
    return "\n".join(out) + "\n"


def loaded_listed(cc: str) -> dict[str, str]:
    """QID → why the load dropped it, or `kept`, for each listed body the load stored."""
    return dict(wd.conn().execute("SELECT qid, coalesce(dropped, 'kept') FROM pcorp_item"
                                  " WHERE country = %s AND 'listed' = ANY(lanes)", (cc,)).fetchall())


def listed(cc: str, rows: list[tuple[Any, ...]], loaded: dict[str, str]) -> list[str]:
    """The funnel of the bodies the state's AMLR list names: loaded, passed, seats written."""
    named = load.listed(cc)
    if not named:
        return []
    mine = [r for r in rows if r[0] in named]
    gated = {r[0] for r in mine if r[1] == "-"}
    by_list = {r[0] for r in mine if r[1] == "-" and r[3].get("scope") == "listed"}
    decided = {r[0] for r in mine}
    seats = [r for r in mine if r[4] == "apply" and r[1] not in ("P31", "P127", "P749")]
    return ["## Bodies the AMLR list names", "",
            f"- in the list: {len(named)}; loaded: " + ", ".join(
                f"{k} {v}" for k, v in Counter(loaded.values()).most_common())
            + f"; not stored {len(named - set(loaded))}",
            f"- decided: {len(decided)}; passed: {len(decided - gated) + len(by_list)},"
            f" of them by the list alone {len(by_list)}",
            f"- seats written: {len(seats)}, of them by the list alone {sum(r[3].get('scope') == 'listed' for r in seats)}",
            f"- named-body rows without an item: {len(load.unresolved(cc))}", ""]


def write(cc: str) -> str:
    path = qs.run_path(cc, suffix=".md")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report(cc))
    return str(path)
