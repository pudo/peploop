"""Export a country's accepted additions as QuickStatements chunks, pasted by hand.

`apply` writes one person per API edit, ten seconds apart and waiting out every
lag episode, so a country of 1,300 people is an afternoon at the terminal.
QuickStatements runs server-side once a batch is pasted. It is the faster path
for the bulk of a run, and not a safe one for all of it: QS matches a line on
item, property and *value* and folds the line's qualifiers into the statement
it finds. So a statement goes out here only when no such match can happen --
it is new, nothing on the live item has its value, and no other statement in
the person's edit has it either. A refinement of a recorded statement, a second
spell beside one, two spells written together, a preferred-rank value: all of
these stay `accepted` for `apply`, which drains them afterwards.

    python -m peploop.cli export --country my            # write new chunks
    python -m peploop.cli export --country my --landed   # read pasted ones back

An exported row is `exported` until `--landed` finds its statement on the live
item and records it `applied` under the claim id. A row a pasted chunk never
landed stays `exported` and is listed; `--release` hands it back to `apply`.
"""

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from peploop import apply, db, http, wikidata

EXPORTED = "exported"
OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "peploop" / "qs"
API = "https://quickstatements.toolforge.org/api.php"
#: Commands one paste into the QuickStatements importer takes.
CAP = 300
GREGORIAN = "http://www.wikidata.org/entity/Q1985727"
SUMMARY_RE = re.compile(r" /\* [^*]+ \*/$")
CHUNK_RE = re.compile(r"-(\d{3})\.qs$")


@dataclass
class Export:
    """One person's QS-safe statements: the lines, and the rows they write."""

    qid: str
    baserevid: int | None
    lines: list[str] = field(default_factory=list)
    rows: list[int] = field(default_factory=list)
    routes: Counter[str] = field(default_factory=Counter)


def qs_value(value: dict[str, Any] | str) -> str | None:
    """A datavalue as a QS V1 column, or None for a shape this path does not write.

    Only the Gregorian calendar is written: QS's Julian marker is not one any
    run has needed, and a date it misreads is worse than one left to `apply`.
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


def lines_for(qid: str, statement: dict[str, Any], summary: str) -> list[str] | None:
    """The QS lines for one new statement: one per reference, or None if unwritable.

    A statement three wikis attest is three lines naming the same statement
    and qualifiers, each with its own source block; QS lands the first and
    adds the others' references to it.
    """
    prop = statement["mainsnak"]["property"]
    main = _snak_value(statement["mainsnak"])
    if main is None:
        return None
    cols = [qid, prop, main]
    qualifiers = statement.get("qualifiers") or {}
    for qprop in statement.get("qualifiers-order") or list(qualifiers):
        for snak in qualifiers.get(qprop, []):
            value = _snak_value(snak)
            if value is None:
                return None
            cols += [qprop, value]
    sources: list[list[str]] = []
    for ref in statement.get("references") or []:
        block: list[str] = []
        for sprop in ref.get("snaks-order") or list(ref["snaks"]):
            for snak in ref["snaks"].get(sprop, []):
                value = _snak_value(snak)
                if value is None:
                    return None
                block += ["S" + sprop[1:], value]
        sources.append(block)
    # The summary rides on the last column after a space: as a column of its
    # own, QS reads it as half a qualifier pair and fails the line.
    # Two rows citing the same revision merge into one statement carrying that
    # reference twice; as lines they would be one line twice.
    return list(dict.fromkeys(
        "\t".join(cols + block) + f" /* {summary} */" for block in sources or [[]]
    ))


def _value_key(prop: str, value: dict[str, Any]) -> str:
    return prop + "\t" + json.dumps(value.get("id") or value, sort_keys=True)


def route(qid: str, entity: dict[str, Any], rows: list[dict[str, Any]], summary: str) -> Export:
    """Split one person's accepted rows into what QS may write and what stays with `apply`.

    The plan is `apply`'s own, so a row exported here is exactly the statement
    the API path would have sent. The routes name why a statement stays.
    """
    plan = apply.plan_person(qid, entity, rows)
    out = Export(qid=qid, baserevid=plan.baserevid)
    statements = plan.data.get("claims", [])
    planned = Counter(
        _value_key(s["mainsnak"]["property"], s["mainsnak"]["datavalue"]["value"])
        for s in statements
    )
    by_key: dict[str, list[int]] = {}
    for row_id, prop, value, qualifiers in plan.claims:
        key = "\t".join((
            prop,
            json.dumps(value, sort_keys=True, ensure_ascii=False),
            apply._qualifier_fingerprint(qualifiers),
        ))
        by_key.setdefault(key, []).append(row_id)
    for statement in statements:
        prop = statement["mainsnak"]["property"]
        value = statement["mainsnak"]["datavalue"]["value"]
        live = [
            claim.get("mainsnak", {}).get("datavalue", {}).get("value")
            for claim in entity.get("claims", {}).get(prop, [])
            if claim.get("rank") != "deprecated"
        ]
        if statement.get("id"):
            out.routes["api:refine"] += 1
            continue
        if statement.get("rank") == "preferred":
            out.routes["api:preferred"] += 1
            continue
        if any(isinstance(found, dict) and apply.same_value(found, value) for found in live):
            out.routes["api:value-on-item"] += 1
            continue
        if planned[_value_key(prop, value)] > 1:
            out.routes["api:spells-together"] += 1
            continue
        rendered = lines_for(qid, statement, summary)
        ids = by_key.get(apply._statement_key(prop, statement), [])
        if rendered is None or not ids:
            out.routes["api:unrenderable"] += 1
            continue
        out.lines += rendered
        out.rows += ids
        out.routes["qs"] += 1
    return out


def statement_of(line: str) -> tuple[str, str, str, str]:
    """(item, property, value, qualifier columns) of a line, references dropped."""
    cols = SUMMARY_RE.sub("", line).split("\t")
    head, rest = cols[:3], cols[3:]
    quals = []
    for i in range(0, len(rest) - 1, 2):
        if rest[i].startswith("S"):
            break
        quals += rest[i:i + 2]
    return head[0], head[1], head[2], "\t".join(quals)


def validate(lines: list[str]) -> list[str]:
    """Local checks: well-formed, no duplicate line, and no value QS would collapse.

    The last is the one that matters. Two lines naming one (item, property,
    value) with different qualifiers become one statement carrying both sets,
    which is the defect this path exists to route around.
    """
    errors = []
    seen: set[str] = set()
    quals: dict[tuple[str, str, str], str] = {}
    for n, text in enumerate(lines, 1):
        bare = SUMMARY_RE.sub("", text)
        cols = bare.split("\t")
        if (text.startswith("-") or len(cols) < 3 or len(cols) % 2 == 0
                or not cols[0].startswith("Q") or not cols[1].startswith("P")):
            errors.append(f"{n}: malformed: {text!r}")
            continue
        if bare in seen:
            errors.append(f"{n}: duplicate line")
        seen.add(bare)
        item, prop, value, qualifiers = statement_of(text)
        prior = quals.setdefault((item, prop, value), qualifiers)
        if prior != qualifiers:
            errors.append(f"{n}: {item} {prop} {value} twice with different qualifiers")
    return errors


def commands(line: str) -> int:
    """QS commands a line expands to: the statement, one per qualifier, one for its references.

    Measured against QS's own parse: a dated tenure with a source is four.
    """
    cols = SUMMARY_RE.sub("", line).split("\t")[3:]
    keys = cols[::2]
    return 1 + sum(k.startswith("P") for k in keys) + any(k.startswith("S") for k in keys)


def parse(text: str) -> tuple[bool, str]:
    """QuickStatements' own parse of a chunk, sent without `submit` (no auth, no edit)."""
    res = http.post(API, data={"action": "import", "format": "v1", "data": text}, timeout=120)
    try:
        out = res.json()
    except ValueError:
        return False, f"HTTP {res.status_code}: {res.text[:200]}"
    found = (out.get("data") or {}).get("commands") or []
    bad = [c for c in found if c.get("error")]
    if out.get("status") != "OK" or bad:
        return False, f"status={out.get('status')} errors={bad[:3]}"
    return True, f"{len(found)} commands parsed, 0 errors"


def next_chunk(country: str) -> int:
    """The next unused chunk number for a country; numbers are never reused."""
    used = [int(m.group(1)) for p in OUT_DIR.glob(f"{country}-*.qs") if (m := CHUNK_RE.search(p.name))]
    return max(used, default=0) + 1


def chunk_name(country: str, number: int) -> str:
    return f"peploop {country} qs-{number:03d}"


def chunked(exports: list[Export], cap: int = CAP) -> list[list[Export]]:
    """Fill chunks in order up to `cap` commands, never splitting a person."""
    out: list[list[Export]] = [[]]
    used = 0
    for export in exports:
        need = sum(commands(line) for line in export.lines)
        if out[-1] and used + need > cap:
            out.append([])
            used = 0
        out[-1].append(export)
        used += need
    return [chunk for chunk in out if chunk]


def write_chunks(country: str, exports: list[Export], log: Callable[[str], None]) -> list[Path]:
    """Write, check and record the chunks; the rows of a chunk that fails stay `accepted`."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    paths = []
    number = next_chunk(country)
    for chunk in chunked([e for e in exports if e.lines]):
        name = chunk_name(country, number)
        lines = [SUMMARY_RE.sub("", line) + f" /* {name} */" for e in chunk for line in e.lines]
        errors = validate(lines)
        text = "\n".join(lines) + "\n"
        ok, detail = (False, "; ".join(errors[:5])) if errors else parse(text)
        if not ok:
            log(f"{name}: refused, nothing recorded: {detail}")
            continue
        path = OUT_DIR / f"{country}-{number:03d}.qs"
        path.write_text(text)
        record(chunk, name)
        log(f"{name}: {len(chunk)} people, {len(lines)} lines, {detail} -> {path}")
        paths.append(path)
        number += 1
    return paths


def record(chunk: list[Export], name: str) -> None:
    """Mark a written chunk's rows `exported`, so `apply` does not send them too."""
    conn = db.conn()
    with conn.transaction():
        for export in chunk:
            conn.execute(
                "UPDATE proposal SET status = %s, applied_batch = %s, base_rev = %s"
                " WHERE id = ANY(%s) AND status = 'accepted'",
                (EXPORTED, name, export.baserevid, export.rows),
            )


# --- a pasted chunk ---------------------------------------------------------------

def _carries(claim: dict[str, Any], row: dict[str, Any]) -> bool:
    """Whether a live claim is the statement a row exported: its value and every qualifier."""
    found = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
    if not isinstance(found, dict) or not apply.same_value(found, row["value"]):
        return False
    present = claim.get("qualifiers") or {}
    for prop, value in (row.get("qualifiers") or {}).items():
        if not prop.startswith("P"):
            continue
        values = [s.get("datavalue", {}).get("value") for s in present.get(prop, [])]
        if not any(isinstance(v, dict) and apply.same_value(v, value) for v in values):
            return False
    return True


def landed(country: str, release: bool = False) -> Counter[tuple[str, str]]:
    """Record the exported rows whose statement is now live; count by (chunk, outcome).

    A row is `applied` when the live item carries its value with every one of
    its qualifiers. One that is not live stays `exported`, unless `release`
    hands it back to `apply` as `accepted` -- for a chunk QS refused, or one
    that will never be pasted.
    """
    conn = db.conn()
    rows = conn.execute(
        "SELECT p.id, p.person_qid, p.property, p.value, p.qualifiers, p.applied_batch"
        " FROM proposal p JOIN person pe ON pe.qid = p.person_qid"
        " WHERE pe.country = %s AND p.status = %s ORDER BY p.id",
        (country, EXPORTED),
    ).fetchall()
    keys = ("id", "person", "property", "value", "qualifiers", "batch")
    rows = [dict(zip(keys, row)) for row in rows]
    entities = wikidata.fetch_items(sorted({row["person"] for row in rows}), props="claims|info")
    counts: Counter[tuple[str, str]] = Counter()
    with conn.transaction():
        for row in rows:
            entity = entities.get(row["person"]) or {}
            claims = entity.get("claims", {}).get(row["property"], [])
            guid = next((c.get("id") for c in claims if _carries(c, row)), None)
            if guid is not None:
                conn.execute(
                    "UPDATE proposal SET status = 'applied', claim_guid = %s, applied_rev = %s"
                    " WHERE id = %s",
                    (guid, entity.get("lastrevid"), row["id"]),
                )
                counts[(row["batch"], "landed")] += 1
            elif release:
                conn.execute(
                    "UPDATE proposal SET status = 'accepted', applied_batch = NULL WHERE id = %s",
                    (row["id"],),
                )
                counts[(row["batch"], "released")] += 1
            else:
                counts[(row["batch"], "not live")] += 1
    return counts
