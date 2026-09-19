"""Render stored proposals as QuickStatements v1 lines.

Nothing here talks to Wikidata: the output is a file a human reads and pastes
into the QuickStatements importer. Only `new` and `refine` proposals can be
rendered — an `exists` adds nothing, a `conflict` is the human's list, and an
`unresolved` has no value to write.
"""

import datetime
import re
from typing import Any

from peploop import db

WRITABLE = ("new", "refine")
QUALIFIER_ORDER = ("P580", "P582")
TIME_RE = re.compile(r"^[+-]\d{4,}-\d{2}-\d{2}T00:00:00Z$")
LABEL_PREFIX = "label:"
ALIAS_PREFIX = "alias:"


def today() -> str:
    """Render today as the day-precision time QuickStatements wants for P813."""
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    return now.strftime("+%Y-%m-%dT00:00:00Z/11")


def qs_time(value: dict[str, Any]) -> str:
    """Render a time datavalue in QuickStatements' `<time>/<precision>` form."""
    return f"{value['time']}/{value['precision']}"


def qs_string(text: str) -> str:
    """Quote a string value the way QuickStatements parses it."""
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def qs_value(value: dict[str, Any]) -> str:
    """Render any datavalue peploop proposes as one QuickStatements field."""
    if "time" in value:
        return qs_time(value)
    if "id" in value:
        return value["id"]
    if "text" in value:
        return qs_string(value["text"])
    raise ValueError(f"no QuickStatements form for {value}")


def line(row: dict[str, Any]) -> str:
    """Render one proposal as one tab-separated QuickStatements line.

    A term goes out bare: QuickStatements takes no reference on a label or an
    alias, because neither is a statement.
    """
    prop = row["property"]
    for prefix, code in ((LABEL_PREFIX, "L"), (ALIAS_PREFIX, "A")):
        if prop.startswith(prefix):
            lang = prop[len(prefix) :]
            return "\t".join([row["person_qid"], f"{code}{lang}", qs_value(row["value"])])
    fields = [row["person_qid"], prop, qs_value(row["value"])]
    qualifiers = row.get("qualifiers") or {}
    for qualifier in QUALIFIER_ORDER:
        if qualifier in qualifiers:
            fields.extend([qualifier, qs_time(qualifiers[qualifier])])
    if row.get("source_url"):
        fields.extend(["S854", qs_string(row["source_url"]), "S813", today()])
    return "\t".join(fields)


def check(lines: list[str]) -> list[str]:
    """Report what is wrong with a rendered batch, before a human reads it.

    QuickStatements merges a repeated line into the statement it already
    matched, so a duplicate is not harmless: it is a qualifier landing twice.
    """
    problems = []
    seen: set[str] = set()
    for text in lines:
        if text in seen:
            problems.append(f"duplicate line: {text}")
        seen.add(text)
        for field in text.split("\t"):
            head = field.split("/")[0]
            if head.startswith(("+", "-")) and not TIME_RE.match(head):
                problems.append(f"malformed time {field!r} in: {text}")
    return problems


def render(statuses: list[str], properties: list[str]) -> tuple[list[str], list[str]]:
    """Render the selected proposals, returning the lines and what is wrong with them."""
    bad = [status for status in statuses if status not in WRITABLE]
    if bad:
        raise ValueError(f"only {', '.join(WRITABLE)} may be rendered, not {', '.join(bad)}")
    rows = db.conn().execute(
        "SELECT person_qid, property, value, qualifiers, source_url FROM proposal"
        " WHERE status = ANY(%s) AND (%s OR property = ANY(%s))"
        " ORDER BY person_qid, property, id",
        (statuses, not properties, properties),
    )
    columns = ("person_qid", "property", "value", "qualifiers", "source_url")
    lines = [line(dict(zip(columns, row))) for row in rows]
    return lines, check(lines)
