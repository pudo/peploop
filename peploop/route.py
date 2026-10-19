"""Turn one person's planned edit into QuickStatements lines, for a QS3 batch.

QS3 cannot be pointed at a statement: a plain line merges into the *first*
statement holding its value, and a `+` line always creates one. So every
statement of the plan becomes the one line that does exactly what was planned:

- a new statement, a further spell of an office, a value beside one somebody
  else sourced: a `+` line (with `R+` when it outranks that one);
- dates or a reference for a statement that is the only one with its value: a
  plain line carrying only what it lacks;
- a coarse imported date sharpened in place: `SWITCH_VALUE`, then a plain line
  carrying the dates or reference it still lacks, if any.

`plan.plan_claim` has already refused what no line can aim (`ambiguous-statement`).
A statement no line can render -- a Julian date, a string with a quote or a tab --
closes its rows as `unrenderable`. A `+` line for a value a plain line of the
same person also names waits for the next send, by when the merge has landed and
the plan sees the statement it made.
"""

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from peploop import plan, qs

TOOL = "peploop"


@dataclass
class Routed:
    """One person's lines, and what became of each accepted row."""

    qid: str
    lines: list[str] = field(default_factory=list)
    #: (line, the proposal ids it writes), in line order.
    edits: list[tuple[str, list[int]]] = field(default_factory=list)
    #: (proposal id, route) for every row closed without a line.
    skipped: list[tuple[int, str]] = field(default_factory=list)
    #: Rows left accepted for the next send.
    deferred: list[int] = field(default_factory=list)
    routes: Counter[str] = field(default_factory=Counter)


def _live(entity: dict[str, Any], prop: str, guid: str) -> dict[str, Any] | None:
    return next((c for c in entity.get("claims", {}).get(prop, []) if c.get("id") == guid), None)


def render(qid: str, entity: dict[str, Any], statement: dict[str, Any]) -> tuple[str, list[str]] | None:
    """(route, lines) for one planned statement, or None if a value cannot be written."""
    prop = statement["mainsnak"]["property"]
    value = qs.snak_value(statement["mainsnak"])
    if value is None:
        return None
    guid = statement.get("id")
    if guid is None:
        quals = qs.qualifiers(statement.get("qualifiers") or {}, statement.get("qualifiers-order"))
        refs = qs.references(statement.get("references") or [])
        if quals is None or refs is None:
            return None
        rank = ["R+"] if statement.get("rank") == "preferred" else []
        route = "preferred" if rank else "create"
        return route, [qs.described(TOOL, [f"+{qid}", prop, value, *rank, *quals, *refs])]
    live = _live(entity, prop, guid)
    if live is None:
        return None
    present = live.get("qualifiers") or {}
    added = {p: s for p, s in (statement.get("qualifiers") or {}).items() if p not in present}
    quals = qs.qualifiers(added)
    refs = qs.references((statement.get("references") or [])[len(live.get("references") or []):])
    if quals is None or refs is None:
        return None
    # A statement already referenced takes no reference of ours, so a switch
    # may leave nothing for the plain line to carry: then there is none.
    merge = [qs.described(TOOL, [qid, prop, value, *quals, *refs])] if quals or refs else []
    old = qs.snak_value(live.get("mainsnak", {}))
    if old is None:
        return None
    if old == value:
        return ("merge", merge) if merge else ("exists", [])
    return "switch", [qs.described(TOOL, [qs.SWITCH, qid, prop, old, value]), *merge]


def route(qid: str, entity: dict[str, Any], rows: list[dict[str, Any]]) -> Routed:
    """Plan one person's accepted rows against their live item, and render the plan."""
    planned = plan.plan_person(qid, entity, rows)
    out = Routed(qid=qid, skipped=list(planned.skipped))
    out.routes.update({r: n for r, n in planned.routes.items() if r not in ("new", "refine", "preferred", "merged")})
    rendered: list[tuple[str, list[str], list[int]]] = []
    for statement, ids in zip(planned.data.get("claims", []), planned.members):
        found = render(qid, entity, statement)
        if found is None:
            out.skipped += [(i, qs.UNRENDERABLE) for i in ids]
            out.routes[qs.UNRENDERABLE] += 1
            continue
        if not found[1]:
            out.skipped += [(i, found[0]) for i in ids]
            out.routes[found[0]] += 1
            continue
        rendered.append((found[0], found[1], ids))
    # A value a plain line names: a `+` line for it in the same batch could be
    # what the plain line merges into, so the `+` waits for the next send.
    merged = {qs.parse(line)[1:] for kind, lines, _ in rendered if kind in ("merge", "switch") for line in lines}
    for kind, lines, ids in rendered:
        if kind in ("create", "preferred") and qs.parse(lines[0])[1:] in merged:
            out.deferred += ids
            out.routes["deferred"] += 1
            continue
        out.routes[kind] += 1
        for line in lines:
            out.lines.append(line)
            out.edits.append((line, ids))
    return out


# --- a batch ----------------------------------------------------------------------

def validate(lines: list[str]) -> list[str]:
    """Local checks before a batch goes out.

    Well-formed lines, no line twice, no statement both created and merged into
    (the merge could land on the statement the `+` makes), and one switch per
    statement.
    """
    errors = []
    seen: set[str] = set()
    created: set[tuple[str, str, str]] = set()
    merged: set[tuple[str, str, str]] = set()
    switched: set[tuple[str, str, str]] = set()
    for n, text in enumerate(lines, 1):
        cols = qs.columns(text)
        if cols[0].startswith("-"):
            errors.append(f"{n}: removal in an add batch")
            continue
        kind = "switch" if cols[0] == qs.SWITCH else "statement"
        body = cols[1:] if kind == "switch" else cols
        if kind == "switch" and len(body) != 4 or kind == "statement" and (
                len(cols) < 3 or not cols[0].lstrip("+").startswith("Q") or not cols[1].startswith("P")):
            errors.append(f"{n}: malformed: {text!r}")
            continue
        if kind == "statement":
            rest = [c for c in cols[3:] if not qs.RANK.match(c)]
            if len(rest) % 2:
                errors.append(f"{n}: malformed: {text!r}")
                continue
        bare = "\t".join(cols)
        if bare in seen:
            errors.append(f"{n}: duplicate line")
        seen.add(bare)
        what, item, prop, value = qs.parse(text)
        key = (item, prop, value)
        if what == "switch":
            old = (item, prop, cols[3])
            if old in switched:
                errors.append(f"{n}: {item} {prop} {cols[3]} switched twice")
            switched.add(old)
        (created if what == "+" else merged).add(key)
    for item, prop, value in sorted(created & merged):
        errors.append(f"{item} {prop} {value} both created and merged into")
    return errors
