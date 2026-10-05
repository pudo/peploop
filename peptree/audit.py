"""Read a sweep batch the way a reviewer has to: every line, labelled, with what to look at first.

A flag is a pointer, not a rule. Each one names a shape that has hidden a
defect before (a territory in `P17`, an empire in `P17`, a head of government
given "minister" beside its own class); a flag that turns out to be a real
defect becomes a rule in `rules.py` with a case in `check_rules.py`, and stops
being something a reviewer has to catch.

    python -m peptree.cli audit <batch>
"""

import re
import sys
from collections import defaultdict
from typing import Any

from peptree import country as countries
from peptree import qs, sweep, wd
from peptree.load import values

#: Categories every state has an office for: absent after the run means the load missed it.
EXPECTED = ("head_of_state", "head_of_government", "minister", "legislator")
MATRIX_ROW = re.compile(r"^\| (\w+)(?: \(unsettled\))? \| (\w+) \| (\w+) \|")


def items(cc: str) -> dict[str, dict[str, Any]]:
    rows = wd.conn().execute("SELECT qid, kind, entity FROM ptree_item WHERE country = %s", (cc,)).fetchall()
    return {q: {"kind": k, "entity": e} for q, k, e in rows}


def absent(cc: str) -> list[str]:
    """Expected categories the latest report still shows absent."""
    path = qs.latest(cc)
    md = path.with_suffix(".md") if path else None
    if md is None or not md.exists():
        return []
    out = []
    for line in md.read_text().splitlines():
        m = MATRIX_ROW.match(line)
        if m and m.group(1) in EXPECTED and m.group(3) == "absent":
            out.append(m.group(1))
    return out


def audit(batch: int) -> str:
    ccs = sweep.members(batch)
    per: dict[str, list[tuple[str, str, str]]] = {}
    for cc in ccs:
        path = qs.latest(cc)
        per[cc] = qs.statements(path.read_text().splitlines()) if path else []
    seen: dict[tuple[str, str], dict[str, str]] = defaultdict(dict)
    for cc, sts in per.items():
        for s, p, v in sts:
            seen[(s, p)][cc] = v
    out = [f"# audit: batch {batch} ({', '.join(ccs)})", ""]
    total = 0
    for cc in ccs:
        c = countries.get(cc)  # also makes its languages the label languages
        known = set(c.p1001_values) | {p["qid"] for p in countries.gazetteer(c)}
        its = items(cc)
        info = wd.labels_of({q for s, _, v in per[cc] for q in (s, v.split()[0])}
                            | {q for s, _, _ in per[cc] for q in values(its.get(s, {}).get("entity", {}), "P279")})

        def name(q: str) -> str:
            labels = its.get(q, {}).get("entity", {}).get("labels", {})
            any_label = next((o["value"] for o in labels.values()), "")
            return wd.name(info.get(q)) or any_label or "(no label)"
        flags_here, body = 0, []
        by_prop: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for s, p, v in per[cc]:
            by_prop[p].append((s, v.split()[0]))
        for p in sorted(by_prop):
            body.append(f"### {p} ({len(by_prop[p])})")
            for s, v in sorted(by_prop[p], key=lambda sv: (sv[1], sv[0])):
                it = its.get(s, {"kind": "?", "entity": {}})
                flags = []
                if name(s) == "(no label)":
                    flags.append("unlabelled subject")
                if p == "P17" and it["kind"] != "ambassador" and v not in c.p17_values:
                    flags.append("P17 is not the country or a predecessor's state")
                if p == "P1001" and v not in known:
                    flags.append("P1001 is no known place of the country")
                if p == "P279" and (old := values(it["entity"], "P279")):
                    flags.append("beside " + ", ".join(f"{q} {name(q)}" for q in old))
                others = {o: ov for o, ov in seen[(s, p)].items() if o != cc}
                differ = sorted(o for o, ov in others.items() if ov.split()[0] != v)
                if differ:
                    flags.append("conflicts with " + ", ".join(differ))
                # The same line in another country is one line in the batch file: a note, not a flag.
                note = f"   (also in {', '.join(sorted(set(others) - set(differ)))})" if set(others) - set(differ) else ""
                mark = "!" if flags else " "
                flags_here += bool(flags)
                body.append(f"{mark} {s} {name(s)[:60]} [{it['kind']}] → {v} {name(v)}"
                            + (f"   ⟵ {'; '.join(flags)}" if flags else "") + note)
            body.append("")
        gone = absent(cc)
        total += flags_here + len(gone)
        out.append(f"## {cc} — {len(per[cc])} lines, {flags_here} flagged"
                   + (f"; absent: {', '.join(gone)}" if gone else ""))
        out += [""] + body
    out.insert(1, f"{total} things to look at")
    return "\n".join(out)


def main(args: list[str]) -> None:
    if len(args) != 1 or not args[0].isdigit():
        sys.exit("usage: audit <batch>")
    text = audit(int(args[0]))
    path = sweep.BATCH_DIR / f"batch-{int(args[0]):02d}-audit.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + "\n")
    print(text)
    print(f"\n{path}", file=sys.stderr)
