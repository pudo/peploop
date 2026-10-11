"""Write and read QuickStatements lines, for both lanes' QS3 batches.

The codec only: a datavalue as a column, qualifiers and references as column
pairs, a command with its edit summary, a new item as `CREATE`/`LAST`, and a
line read back into what it states. Which line a statement becomes is each
lane's own business -- peploop aims every statement of a plan (`route.py`),
peptree writes plain additive lines (`tree/qs.py`).
"""

import re
from typing import Any

GREGORIAN = "http://www.wikidata.org/entity/Q1985727"
#: Why a row closes when a value has no QS form (a Julian date, a quote or tab in a string).
UNRENDERABLE = "unrenderable"
SWITCH = "SWITCH_VALUE"
RANK = re.compile(r"^R[-0+]$")
#: The ` /* summary */` every line carries at its end.
SUMMARY_RE = re.compile(r" /\* [^*]+ \*/$")


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


def snak_value(snak: dict[str, Any]) -> str | None:
    if snak.get("snaktype") != "value":
        return None
    return qs_value(snak.get("datavalue", {}).get("value"))


def qualifiers(snaks: dict[str, Any], order: list[str] | None = None) -> list[str] | None:
    """Qualifier snaks as `P… value` column pairs, in `order` if given."""
    cols: list[str] = []
    for qprop in order or list(snaks):
        for snak in snaks.get(qprop, []):
            value = snak_value(snak)
            if value is None:
                return None
            cols += [qprop, value]
    return cols


def references(references: list[dict[str, Any]]) -> list[str] | None:
    """Reference blocks as columns: the first opens with `S…`, each further one with `!S…`."""
    cols: list[str] = []
    for n, ref in enumerate(references):
        first = True
        for sprop in ref.get("snaks-order") or list(ref["snaks"]):
            for snak in ref["snaks"].get(sprop, []):
                value = snak_value(snak)
                if value is None:
                    return None
                cols += [("!S" if n and first else "S") + sprop[1:], value]
                first = False
    return cols


def line(cols: list[str], summary: str) -> str:
    """Join columns into one command, with the edit summary as its comment."""
    # The summary rides on the last column after a space: as a column of its
    # own, QS reads it as half a qualifier pair and fails the line.
    return "\t".join(cols) + f" /* {summary.replace('*', '')} */"


def create_lines(data: dict[str, Any], summary: str) -> list[str] | None:
    """A new item as QS lines: `CREATE`, then its terms and statements on `LAST`.

    `data` is the entity JSON `offices.entity_data` builds. The `CREATE`
    line comes first, so its command index is where the new QID is read back.
    None if a term or value cannot be written.
    """
    lines = [line(["CREATE"], summary)]
    for code, terms in (("L", data.get("labels") or {}), ("D", data.get("descriptions") or {})):
        for lang, term in terms.items():
            text = qs_value(term["value"])
            if text is None:
                return None
            lines.append(line(["LAST", f"{code}{lang}", text], summary))
    for lang, terms in (data.get("aliases") or {}).items():
        for term in terms:
            text = qs_value(term["value"])
            if text is None:
                return None
            lines.append(line(["LAST", f"A{lang}", text], summary))
    for claim in data.get("claims") or []:
        value = snak_value(claim["mainsnak"])
        quals = qualifiers(claim.get("qualifiers") or {}, claim.get("qualifiers-order"))
        refs = references(claim.get("references") or [])
        if value is None or quals is None or refs is None:
            return None
        lines.append(line(["LAST", claim["mainsnak"]["property"], value, *quals, *refs], summary))
    return lines


# --- reading a line back ----------------------------------------------------------

def columns(line: str) -> list[str]:
    return SUMMARY_RE.sub("", line).split("\t")


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
    if snak_value(claim.get("mainsnak", {})) != value:
        return False
    present = claim.get("qualifiers") or {}
    return all(any(snak_value(s) == v for s in present.get(p, [])) for p, v in pairs)


def live_lines(lines: list[str], entities: dict[str, dict[str, Any]]) -> list[str]:
    """The lines whose statement the live items now hold."""
    out = []
    for line in lines:
        _, item, prop, value = parse(line)
        claims = (entities.get(item) or {}).get("claims", {}).get(prop, [])
        if any(carries(c, value, qualifier_pairs(line)) for c in claims):
            out.append(line)
    return out
