"""Read a country's AMLR asset back as coverage: what its listed functions reach on Wikidata.

This is the AMLR benchmark per member state. A row only counts for
OpenSanctions once its items carry people, so beside the rows and how many
are expanded the report asks, live:

- of the position items, how many have a current holder: a living human
  with a `P39` of it and no end;
- of the units a level rule names (`amlr.units`), how many have a head
  office (their `P1313`, or a position scoped to them or their council that
  is a kind of one of `amlr.HEADS`) and how many name a current head
  (`P6`, no end);
- of the bodies, how many carry any seat statement (`SEATS`).

Tier rules name classes of bodies pepcorp reads, not items; they are
counted, not measured. The report goes to `data/amlr/<cc>-<date>.md`.

    .venv/bin/python -m peploop.cli amlr report <cc>|--all
"""

from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

from peploop import amlr, wikidata

OUT = Path(__file__).resolve().parents[1] / "data" / "amlr"
#: The statements on a body that seat a person on it: director, chair, head, board member, supervisory board.
SEATS = ("P169", "P1037", "P488", "P3320", "P5052")

HELD_SQL = """SELECT DISTINCT ?pos WHERE {{
  VALUES ?pos {{ {values} }}
  ?h p:P39 ?st . ?st ps:P39 ?pos . ?h wdt:P31 wd:Q5 .
  FILTER NOT EXISTS {{ ?st pq:P582 [] }} FILTER NOT EXISTS {{ ?h wdt:P570 [] }}
  FILTER NOT EXISTS {{ ?st wikibase:rank wikibase:DeprecatedRank }}
}}"""

def held(positions: list[str]) -> set[str]:
    """The positions a living person holds now, by a `P39` with no end."""
    rows = wikidata.bisect(lambda chunk: wikidata.sparql(HELD_SQL.format(values=wikidata.values_block(chunk))),
                           positions)
    return {r["pos"] for r in rows}


def _unended(entity: dict[str, Any], prop: str) -> bool:
    return any(c.get("rank") != "deprecated" and not c.get("qualifiers", {}).get("P582")
               for c in entity.get("claims", {}).get(prop, []))


def measure(cc: str) -> dict[str, Any]:
    """A country's numbers: rows by kind and category, expansions, and what their items carry."""
    fns = amlr.functions(cc)
    entries = [(f, e) for f in fns for e in f.expansion]
    positions = sorted({e["position"] for _, e in entries if "position" in e})
    bodies = sorted({e["body"] for _, e in entries if "body" in e})
    levels = sorted({e["level"] for _, e in entries if "level" in e})
    tiers = sorted({f"{e['tier']} {e['bodies']}" for _, e in entries if "tier" in e})
    out: dict[str, Any] = {
        "cc": cc, "rows": len(fns),
        "by_kind": Counter(f.kind for f in fns),
        "expanded": Counter(f.kind for f in fns if f.expansion),
        "by_category": Counter((f.amlr, f.kind) for f in fns),
        "expanded_category": Counter((f.amlr, f.kind) for f in fns if f.expansion),
        "by": Counter(e.get("by", "hand") for _, e in entries),
        "positions": positions, "held": sorted(held(positions)) if positions else [],
        "bodies": bodies, "tiers": tiers, "levels": {},
    }
    ents = wikidata.fetch_items(bodies, props="claims") if bodies else {}
    out["seated"] = sorted(q for q, e in ents.items() if any(
        c.get("rank") != "deprecated" for p in SEATS for c in e.get("claims", {}).get(p, [])))
    if levels:
        units = amlr.units(cc)
        for level in levels:
            mine = sorted(q for q, (lv, _) in units.items() if lv == level)
            unit_ents = wikidata.fetch_items(mine, props="claims") if mine else {}
            linked = {q for q, e in unit_ents.items() if _unended(e, "P1313")}
            office = linked | (amlr.scoped_heads(mine) if mine else set())
            head = {q for q, e in unit_ents.items() if _unended(e, "P6")}
            out["levels"][level] = {"units": len(mine), "office": len(office), "head": len(head)}
    return out


def summary(m: dict[str, Any]) -> str:
    """One line per country."""
    usable = m["rows"] - m["by_kind"].get("unusable", 0)
    parts = [f"{m['cc']}: {sum(m['expanded'].values())}/{usable} usable rows expanded",
             f"positions {len(m['held'])}/{len(m['positions'])} held",
             f"bodies {len(m['seated'])}/{len(m['bodies'])} seated"]
    for level, n in m["levels"].items():
        parts.append(f"{level} {n['units']} units, {n['office']} with office, {n['head']} with head")
    if m["tiers"]:
        parts.append("tiers " + ", ".join(m["tiers"]))
    return "; ".join(parts)


def render(m: dict[str, Any]) -> str:
    """The country's report as Markdown."""
    kinds = [k for k in amlr.KINDS if m["by_kind"].get(k)]
    lines = [f"# AMLR coverage: {m['cc']} ({date.today().isoformat()})", "", summary(m), "",
             "## Rows by kind", "", "| kind | rows | expanded |", "|---|---|---|"]
    lines += [f"| {k} | {m['by_kind'][k]} | {m['expanded'].get(k, 0)} |" for k in kinds]
    lines += ["", "## Rows by category", "", "| category | kind | rows | expanded |", "|---|---|---|---|"]
    for (cat, kind), n in sorted(m["by_category"].items()):
        lines.append(f"| {cat} | {kind} | {n} | {m['expanded_category'].get((cat, kind), 0)} |")
    lines += ["", "Expansion entries by provenance: "
              + (", ".join(f"{k} {v}" for k, v in sorted(m["by"].items())) or "none"), ""]
    lines += ["## Positions", "", f"{len(m['positions'])} position items; {len(m['held'])} with a current holder."]
    unheld = [q for q in m["positions"] if q not in set(m["held"])]
    if unheld:
        lines.append("No current holder: " + " ".join(unheld))
    lines += ["", "## Unit levels", ""]
    if m["levels"]:
        lines += ["| level | units | head office | current head |", "|---|---|---|---|"]
        lines += [f"| {lv} | {n['units']} | {n['office']} | {n['head']} |" for lv, n in m["levels"].items()]
    else:
        lines.append("No row expands to a level.")
    lines += ["", "## Bodies", "", f"{len(m['bodies'])} body items; {len(m['seated'])} carry a seat statement"
              f" ({' '.join(SEATS)})."]
    unseated = [q for q in m["bodies"] if q not in set(m["seated"])]
    if unseated:
        lines.append("No seat: " + " ".join(unseated))
    if m["tiers"]:
        lines += ["", "## Tiers", "", "Body classes for pepcorp: " + ", ".join(m["tiers"])]
    return "\n".join(lines) + "\n"


def write(cc: str) -> tuple[Path, str]:
    """Measure a country, write its report, and return the path and the summary line."""
    m = measure(cc)
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{cc}-{date.today().isoformat()}.md"
    path.write_text(render(m))
    return path, summary(m)
