"""A country's funnel, its category × state matrix before and after the batch, and its skips.

Written beside the run's `.qs` as `<cc>-<date>.md`, so the batch and its
account are reviewed together.
"""

from collections import Counter
from pathlib import Path

from peploop.tree import gaps as gapmod
from peploop.tree import qs, repair, wd
from peploop.tree.load import items as load_items


def funnel(cc: str) -> list[str]:
    con = wd.conn()
    out = ["## Funnel", ""]
    loaded = con.execute("SELECT count(*) FROM ptree_item WHERE country = %s", (cc,)).fetchone()[0]
    out.append(f"- loaded: {loaded}")
    lanes = con.execute("SELECT l, count(*) FROM ptree_item, unnest(lanes) l WHERE country = %s GROUP BY 1 ORDER BY 2 DESC",
                        (cc,)).fetchall()
    out.append("  - by lane (overlapping): " + ", ".join(f"{l} {n}" for l, n in lanes))
    for reason, n in con.execute("SELECT dropped, count(*) FROM ptree_item WHERE country = %s AND dropped IS NOT NULL"
                                 " GROUP BY 1 ORDER BY 2 DESC", (cc,)).fetchall():
        out.append(f"- dropped {reason}: {n}")
    kinds = con.execute("SELECT kind, count(*) FROM ptree_item WHERE country = %s AND dropped IS NULL GROUP BY 1 ORDER BY 2 DESC",
                        (cc,)).fetchall()
    out.append("- kept: " + ", ".join(f"{k} {n}" for k, n in kinds))
    kept = con.execute("SELECT entity FROM ptree_item WHERE country = %s AND dropped IS NULL", (cc,)).fetchall()
    swapped = sum(1 for (e,) in kept if gapmod.inverted(e))
    if swapped:
        out.append(f"- inverted (a position type in P279; P31/P279 not repaired): {swapped}")
    with_gap = con.execute("SELECT count(DISTINCT qid) FROM ptree_gap WHERE country = %s", (cc,)).fetchone()[0]
    asked = con.execute("SELECT count(DISTINCT g.qid) FROM ptree_gap g JOIN ptree_call c ON c.qid = g.qid AND c.country = g.country"
                        " WHERE g.country = %s", (cc,)).fetchone()[0]
    if asked < with_gap:
        out.append(f"- asked only held or categorised offices: {asked} of {with_gap} with a gap")
    g = con.execute("SELECT prop, gap, count(*) FROM ptree_gap WHERE country = %s GROUP BY 1,2 ORDER BY 1,2", (cc,)).fetchall()
    items_with = con.execute("SELECT count(DISTINCT qid) FROM ptree_gap WHERE country = %s", (cc,)).fetchone()[0]
    out.append(f"- items with a gap: {items_with}; slots: " + ", ".join(f"{p} {gp} {n}" for p, gp, n in g))
    calls = con.execute("SELECT count(*) FROM ptree_decision d WHERE country = %s", (cc,)).fetchone()[0]
    answered = con.execute("SELECT count(*) FROM ptree_decision WHERE country = %s AND value IS NOT NULL", (cc,)).fetchone()[0]
    out.append(f"- slots decided: {calls}; model gave a value on {answered}")
    for disp, rule, n in con.execute("SELECT disposition, rule, count(*) FROM ptree_decision WHERE country = %s"
                                     " GROUP BY 1,2 ORDER BY 1, 3 DESC", (cc,)).fetchall():
        out.append(f"  - {disp}:{rule}: {n}")
    by_prop = con.execute("SELECT prop, count(*) FROM ptree_decision WHERE country = %s AND disposition = 'apply'"
                          " GROUP BY 1 ORDER BY 1", (cc,)).fetchall()
    out.append("- applied by property: " + ", ".join(f"{p} {n}" for p, n in by_prop))
    usd, n = repair.cost(cc)
    out.append(f"- LLM: {n} calls in the ledger, ${usd:.2f}")
    return out


def added(cc: str) -> dict[str, dict[str, list[str]]]:
    out: dict[str, dict[str, list[str]]] = {}
    for qid, prop, value in wd.conn().execute(
            "SELECT qid, prop, value FROM ptree_decision WHERE country = %s AND disposition = 'apply'", (cc,)).fetchall():
        out.setdefault(qid, {}).setdefault(prop, []).append(value)
    return out


def matrix_lines(cc: str) -> list[str]:
    ctx = gapmod.Context(cc, load_items(cc))
    before = gapmod.matrix(ctx)
    after = gapmod.matrix(ctx, added(cc))
    out = ["## Matrix (current national offices; ambassadors = own posts abroad)", "",
           "| category | before | after | members before→after | ok before→after |", "|---|---|---|---|---|"]
    tally: Counter[tuple[str, str]] = Counter()
    for cat in ctx.cats:
        b, a = before[cat["key"]], after[cat["key"]]
        state_after = "repaired" if b["state"] != "ok" and a["state"] == "ok" else a["state"]
        tally[(b["state"], state_after)] += 1
        flag = " (unsettled)" if b["unsettled"] else ""
        out.append(f"| {cat['key']}{flag} | {b['state']} | {state_after} | {b['members']}→{a['members']} | {b['ok']}→{a['ok']} |")
    out += ["", "Transitions: " + ", ".join(f"{b}→{a} {n}" for (b, a), n in sorted(tally.items()))]
    return out


def skip_lines(cc: str, per_rule: int = 8) -> list[str]:
    """Every skipped slot, grouped by the rule that skipped it, a few shown per rule."""
    rows = wd.conn().execute(
        "SELECT d.rule, d.qid, d.prop, d.value, d.confidence, d.evidence, i.entity->'labels'"
        " FROM ptree_decision d JOIN ptree_item i USING (country, qid)"
        " WHERE d.country = %s AND d.disposition = 'skip' ORDER BY d.rule, d.qid, d.prop", (cc,)).fetchall()
    by_rule: dict[str, list] = {}
    for r in rows:
        by_rule.setdefault(r[0], []).append(r)
    out = ["## Skips by rule", ""]
    for rule, rs in sorted(by_rule.items(), key=lambda kv: -len(kv[1])):
        out.append(f"### {rule} ({len(rs)})")
        for _, qid, prop, value, conf, quote, labels in rs[:per_rule]:
            label = wd.label({"labels": labels or {}})
            out.append(f"- {qid} {prop} → {value or '—'} ({conf or '?'}): {label}")
        if len(rs) > per_rule:
            out.append(f"- … and {len(rs) - per_rule} more")
        out.append("")
    return out


def report(cc: str) -> str:
    return "\n".join([f"# peptree: {cc}", ""] + funnel(cc) + [""] + matrix_lines(cc) + [""] + skip_lines(cc))


def write(cc: str) -> Path:
    """Write the report beside today's run file and return its path."""
    path = qs.run_path(cc, suffix=".md")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report(cc) + "\n")
    return path
