"""Render one person's planned edit as QuickStatements lines, for a QS3 batch.

QS3 cannot be pointed at a statement: a plain line merges into the *first*
statement holding its value, and a `+` line always creates one. So every
statement of the plan becomes the one line that does exactly what was planned:

- a new statement, a further spell of an office, a value beside one somebody
  else sourced: a `+` line (with `R+` when it outranks that one);
- dates or a reference for a statement that is the only one with its value: a
  plain line carrying only what it lacks;
- a coarse imported date sharpened in place: `SWITCH_VALUE`, then a plain line
  adding the new reference to it.

`plan.plan_claim` has already refused what no line can aim (`ambiguous-statement`).
A statement no line can render -- a Julian date, a string with a quote or a tab --
closes its rows as `unrenderable`. A `+` line for a value a plain line of the
same person also names waits for the next send, by when the merge has landed and
the plan sees the statement it made.
"""

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from peploop import ledger, plan

GREGORIAN = "http://www.wikidata.org/entity/Q1985727"
UNRENDERABLE = "unrenderable"
SWITCH = "SWITCH_VALUE"
RANK = re.compile(r"^R[-0+]$")


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


def qs_value(value: dict[str, Any] | str) -> str | None:
    """A datavalue as a QS column, or None for a shape this path does not write.

    Only the Gregorian calendar is written: QS's Julian marker is not one any
    run has needed, and a date it misreads is worse than one left unwritten.
    """
    if isinstance(value, str):
        return None if '"' in value or "\t" in value else f'"{value}"'
    if "id" in value:
        return value["id"]
    if "time" in value:
        if value.get("calendarmodel", GREGORIAN) != GREGORIAN:
            return None
        return f"{value['time']}/{value['precision']}"
    return None


def _snak_value(snak: dict[str, Any]) -> str | None:
    if snak.get("snaktype") != "value":
        return None
    return qs_value(snak.get("datavalue", {}).get("value"))


def _qualifiers(qualifiers: dict[str, Any], order: list[str] | None = None) -> list[str] | None:
    cols: list[str] = []
    for qprop in order or list(qualifiers):
        for snak in qualifiers.get(qprop, []):
            value = _snak_value(snak)
            if value is None:
                return None
            cols += [qprop, value]
    return cols


def _references(references: list[dict[str, Any]]) -> list[str] | None:
    """Reference blocks as columns: the first opens with `S…`, each further one with `!S…`."""
    cols: list[str] = []
    for n, ref in enumerate(references):
        first = True
        for sprop in ref.get("snaks-order") or list(ref["snaks"]):
            for snak in ref["snaks"].get(sprop, []):
                value = _snak_value(snak)
                if value is None:
                    return None
                cols += [("!S" if n and first else "S") + sprop[1:], value]
                first = False
    return cols


def _line(cols: list[str], summary: str) -> str:
    # The summary rides on the last column after a space: as a column of its
    # own, QS reads it as half a qualifier pair and fails the line.
    return "\t".join(cols) + f" /* {summary.replace('*', '')} */"


def _live(entity: dict[str, Any], prop: str, guid: str) -> dict[str, Any] | None:
    return next((c for c in entity.get("claims", {}).get(prop, []) if c.get("id") == guid), None)


def render(qid: str, entity: dict[str, Any], statement: dict[str, Any], summary: str) -> tuple[str, list[str]] | None:
    """(route, lines) for one planned statement, or None if a value cannot be written."""
    prop = statement["mainsnak"]["property"]
    value = _snak_value(statement["mainsnak"])
    if value is None:
        return None
    guid = statement.get("id")
    if guid is None:
        quals = _qualifiers(statement.get("qualifiers") or {}, statement.get("qualifiers-order"))
        refs = _references(statement.get("references") or [])
        if quals is None or refs is None:
            return None
        rank = ["R+"] if statement.get("rank") == "preferred" else []
        route = "preferred" if rank else "create"
        return route, [_line([f"+{qid}", prop, value, *rank, *quals, *refs], summary)]
    live = _live(entity, prop, guid)
    if live is None:
        return None
    present = live.get("qualifiers") or {}
    added = {p: s for p, s in (statement.get("qualifiers") or {}).items() if p not in present}
    quals = _qualifiers(added)
    refs = _references((statement.get("references") or [])[len(live.get("references") or []):])
    if quals is None or refs is None:
        return None
    merge = _line([qid, prop, value, *quals, *refs], summary)
    old = _snak_value(live.get("mainsnak", {}))
    if old is None:
        return None
    if old == value:
        return "merge", [merge]
    return "switch", [_line([SWITCH, qid, prop, old, value], summary), merge]


def route(qid: str, entity: dict[str, Any], rows: list[dict[str, Any]]) -> Routed:
    """Plan one person's accepted rows against their live item, and render the plan."""
    planned = plan.plan_person(qid, entity, rows)
    out = Routed(qid=qid, skipped=list(planned.skipped))
    out.routes.update({r: n for r, n in planned.routes.items() if r not in ("new", "refine", "preferred", "merged")})
    rendered: list[tuple[str, list[str], list[int]]] = []
    for statement, ids in zip(planned.data.get("claims", []), planned.members):
        found = render(qid, entity, statement, planned.summary)
        if found is None:
            out.skipped += [(i, UNRENDERABLE) for i in ids]
            out.routes[UNRENDERABLE] += 1
            continue
        rendered.append((found[0], found[1], ids))
    # A value a plain line names: a `+` line for it in the same batch could be
    # what the plain line merges into, so the `+` waits for the next send.
    merged = {parse(line)[1:] for kind, lines, _ in rendered if kind in ("merge", "switch") for line in lines}
    for kind, lines, ids in rendered:
        if kind in ("create", "preferred") and parse(lines[0])[1:] in merged:
            out.deferred += ids
            out.routes["deferred"] += 1
            continue
        out.routes[kind] += 1
        for line in lines:
            out.lines.append(line)
            out.edits.append((line, ids))
    return out


def create_lines(data: dict[str, Any], summary: str) -> list[str] | None:
    """A new item as QS lines: `CREATE`, then its terms and statements on `LAST`.

    `data` is the `wbeditentity` blob `offices.entity_data` builds. The `CREATE`
    line comes first, so its command index is where the new QID is read back.
    None if a term or value cannot be written.
    """
    lines = [_line(["CREATE"], summary)]
    for code, terms in (("L", data.get("labels") or {}), ("D", data.get("descriptions") or {})):
        for lang, term in terms.items():
            text = qs_value(term["value"])
            if text is None:
                return None
            lines.append(_line(["LAST", f"{code}{lang}", text], summary))
    for lang, terms in (data.get("aliases") or {}).items():
        for term in terms:
            text = qs_value(term["value"])
            if text is None:
                return None
            lines.append(_line(["LAST", f"A{lang}", text], summary))
    for claim in data.get("claims") or []:
        value = _snak_value(claim["mainsnak"])
        quals = _qualifiers(claim.get("qualifiers") or {}, claim.get("qualifiers-order"))
        refs = _references(claim.get("references") or [])
        if value is None or quals is None or refs is None:
            return None
        lines.append(_line(["LAST", claim["mainsnak"]["property"], value, *quals, *refs], summary))
    return lines


# --- reading a line back ----------------------------------------------------------

def columns(line: str) -> list[str]:
    return ledger.SUMMARY_RE.sub("", line).split("\t")


def parse(line: str) -> tuple[str, str, str, str]:
    """(kind, item, property, value) of a line: kind `+`, `merge` or `switch` (value: the new one)."""
    cols = columns(line)
    if cols[0] == SWITCH:
        return "switch", cols[1], cols[2], cols[4]
    if cols[0].startswith("+"):
        return "+", cols[0][1:], cols[1], cols[2]
    return "merge", cols[0], cols[1], cols[2]


def qualifier_pairs(line: str) -> list[tuple[str, str]]:
    """The (property, value) qualifier pairs of a statement line, rank and references left out."""
    cols = columns(line)
    if cols[0] == SWITCH:
        return []
    rest = [c for c in cols[3:] if not RANK.match(c)]
    out = []
    for i in range(0, len(rest) - 1, 2):
        if not rest[i].startswith("P"):
            break
        out.append((rest[i], rest[i + 1]))
    return out


def carries(claim: dict[str, Any], value: str, pairs: list[tuple[str, str]]) -> bool:
    """Whether a live claim holds this value and every one of these qualifiers, as QS columns."""
    if _snak_value(claim.get("mainsnak", {})) != value:
        return False
    present = claim.get("qualifiers") or {}
    return all(any(_snak_value(s) == v for s in present.get(p, [])) for p, v in pairs)


def live_lines(lines: list[str], entities: dict[str, dict[str, Any]]) -> list[str]:
    """The lines whose statement the live items now hold."""
    out = []
    for line in lines:
        _, item, prop, value = parse(line)
        claims = (entities.get(item) or {}).get("claims", {}).get(prop, [])
        if any(carries(c, value, qualifier_pairs(line)) for c in claims):
            out.append(line)
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
        cols = columns(text)
        if cols[0].startswith("-"):
            errors.append(f"{n}: removal in an add batch")
            continue
        kind = "switch" if cols[0] == SWITCH else "statement"
        body = cols[1:] if kind == "switch" else cols
        if kind == "switch" and len(body) != 4 or kind == "statement" and (
                len(cols) < 3 or not cols[0].lstrip("+").startswith("Q") or not cols[1].startswith("P")):
            errors.append(f"{n}: malformed: {text!r}")
            continue
        if kind == "statement":
            rest = [c for c in cols[3:] if not RANK.match(c)]
            if len(rest) % 2:
                errors.append(f"{n}: malformed: {text!r}")
                continue
        bare = "\t".join(cols)
        if bare in seen:
            errors.append(f"{n}: duplicate line")
        seen.add(bare)
        what, item, prop, value = parse(text)
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
