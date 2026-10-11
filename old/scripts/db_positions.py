#!/usr/bin/env python
"""Partition the positions DB's country-less rows into what can be fixed.

    python scripts/db_positions.py --input ~/tmp/pos_no_country.jsonl

`zavod/shed/wikidata/position.py` drops a position it cannot link to a
country, taking the holders' occupancies with it, so every row in an export
of the positions table with an empty `countries` array is a position
OpenSanctions tried and failed to emit. That export is a better driver for a
jurisdiction backfill than a SPARQL census of bare P39 targets
(`bare_positions.py`): it is four times smaller and every row in it
demonstrably costs coverage.

The partition is `wd.shape.verify`'s, not a hand-written P31 list, because it
already runs zavod's own country walk and already separates the four answers
this question has:

* **resolves** — the item carries a country today and the DB row is merely
  stale. Wants a re-crawl, never an edit.
* **not a position** — a profession, a rank, an honour, a Wikimedia list
  article. Country-less by nature; the defect is the `P39` usage pointing at
  it, and asserting a jurisdiction here would entrench the mis-type.
* **bilateral** — a diplomatic post, where `P17` means the receiving state
  and `P1001` is not asserted at all. Routes to `render_diplomatic_plan.py`.
* **no polity** — an office that owes a jurisdiction and does not name one.
  The fixable pool, written in `bare_positions.json`'s record shape so the
  citizenship pipeline consumes it unchanged.

An office scoped only to a *historical* polity is a fifth answer and is not a
defect — naming the modern republic on a Grand Duchy office is a wrong
statement in the lane that looks safest — so it is partitioned out too, by
`scoped_to_dead_polity` below rather than by `wd.shape`'s wider test.
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wd.api import best_description, best_label, claim_qids, fetch_entities
from wd.http import REPO_ROOT, make_session
from wd.labels import match_place, territory_index
from wd.positions import holder_counts
from wd.shape import Verdict, type_closure, verify

BASE = REPO_ROOT / "data" / "jurisdictions"
DEFAULT_INPUT = Path.home() / "tmp" / "pos_no_country.jsonl"

# Properties zavod's item_countries() traversal can pull a country out of.
# Kept for the census record's `traversal_props` field, which is what
# `bare_positions.json` carries and the downstream chunks display.
TRAVERSAL_PROPS = ["P27", "P361", "P749", "P159", "P1376", "P2389"]


#: The only two properties that can put an office *inside* a polity. `wd.shape`
#: suppresses its `no_polity` defect whenever any of `COUNTRY_PROPS +
#: FALLBACK_PROPS` names something, which reads a `P361` into a country-less
#: body ("part of the Catholic Church") as "scoped to history" and hides a
#: fixable office: 232 of the 493 items that landed there on the first run were
#: of that kind. Scoped-to-history is tested here on the jurisdiction pair
#: alone — the office says which polity it belongs to, and that polity is gone.
POLITY_PROPS = ("P17", "P1001")


def scoped_to_dead_polity(entity: Dict[str, Any]) -> bool:
    """The item names its polity through P17/P1001 and none of them resolved.

    Called only where `verify` already found no country, so "named and did not
    resolve" means the polity is historical or itself country-less. That is
    complete and correct modelling — naming the modern successor on a Grand
    Duchy office would be a wrong statement in the lane that looks safest.
    """
    return any(claim_qids(entity, prop) for prop in POLITY_PROPS)


def first_year(entity: Dict[str, Any], prop: str) -> Optional[str]:
    for claim in entity.get("claims", {}).get(prop, []):
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(value, dict) and "time" in value:
            if value.get("precision", 11) >= 9:
                return value["time"].lstrip("+")[:4]
    return None


def read_rows(path: Path) -> List[str]:
    """QIDs from the positions-table export, first occurrence wins."""
    qids: List[str] = []
    seen = set()
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        qid = row.get("entity_id")
        if qid and qid.startswith("Q") and qid not in seen:
            seen.add(qid)
            qids.append(qid)
    return qids


def record(
    entity: Dict[str, Any], verdict: Verdict, holders: int,
    type_labels: Dict[str, str], place: Any,
) -> Dict[str, Any]:
    """One census row, in the shape `bare_positions.json` uses.

    `label_place` is the extra field: the territory the item's own label
    names, which is the second channel for a candidate whose holders carry no
    citizenship signal. A candidate generator and never a fact — the audited
    output is full of list articles and academies naming a country.
    """
    sitelinks = entity.get("sitelinks", {})
    return {
        "qid": verdict.qid,
        "label": verdict.label,
        "description": best_description(entity),
        "holders": holders,
        "instance_of": [
            {"qid": t, "label": type_labels.get(t)}
            for t in claim_qids(entity, "P31")
        ],
        "declared": verdict.declared,
        "traversal_props": [
            p for p in TRAVERSAL_PROPS if entity.get("claims", {}).get(p)
        ],
        "inception": first_year(entity, "P571"),
        "abolished": verdict.abolished,
        "sitelinks": len(sitelinks),
        "enwiki": (sitelinks.get("enwiki") or {}).get("title"),
        "label_place": None if place is None else {
            "qid": place.qid,
            "code": place.code,
            "name": place.name,
            "is_country": place.is_country,
            "is_historical": place.is_historical,
        },
        "defects": verdict.defects,
        "gaps": verdict.gaps,
    }


def write(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=1, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT,
                        help="positions-table export (JSONL, one row per position)")
    parser.add_argument("--out-dir", type=Path, default=BASE)
    parser.add_argument("--limit", type=int, default=0, help="debug: first N QIDs")
    args = parser.parse_args()

    qids = read_rows(args.input)
    if args.limit:
        qids = qids[:args.limit]
    print(f"{len(qids)} distinct position QIDs in {args.input}", file=sys.stderr)

    session = make_session()
    # `max_age=0` throughout: this reads Wikidata's *state*, which is exactly
    # what this engine's own batches change. A cached read is how a previous
    # run offered twenty statements that already existed.
    closure = type_closure(session, qids)
    entities = fetch_entities(session, qids, max_age=0)
    print(f"{len(entities)} live items ({len(qids) - len(entities)} deleted)",
          file=sys.stderr)

    holders = holder_counts(session, sorted(entities))
    places = territory_index(session)

    type_qids = {t for e in entities.values() for t in claim_qids(e, "P31")}
    type_labels = {
        qid: best_label(e) or qid
        for qid, e in fetch_entities(session, type_qids, props="labels").items()
    }

    buckets: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for qid in qids:
        entity = entities.get(qid)
        if entity is None:
            buckets["gone"].append({"qid": qid})
            continue
        if entity["id"] != qid:
            # Merged away: the redirect target carries the claims and will have
            # been audited under its own QID if the export lists it.
            buckets["merged"].append({"qid": qid, "into": entity["id"]})
            continue
        label = best_label(entity)
        verdict = verify(session, entity, closure, label=label)
        row = record(entity, verdict, holders.get(qid, 0), type_labels,
                     match_place(places, label))
        row["countries"] = verdict.countries
        row["country_via"] = verdict.country_via

        # Priority chain, most-answered first. An item that already resolves
        # needs no statement whatever else is wrong with it, and an item that
        # is not an office needs none either.
        if verdict.countries:
            buckets["resolves"].append(row)
        elif {"not_a_position", "also_a_list_article"} & set(verdict.defects):
            buckets["not_positions"].append(row)
        elif verdict.bilateral:
            buckets["bilateral"].append(row)
        elif scoped_to_dead_polity(entity):
            buckets["historical"].append(row)
        else:
            buckets["census"].append(row)

    for name in ("census", "bilateral", "not_positions", "resolves", "historical"):
        buckets[name].sort(key=lambda r: -r["holders"])
    write(args.out_dir / "db_census.json", buckets["census"])
    write(args.out_dir / "db_bilateral.json", buckets["bilateral"])
    write(args.out_dir / "db_not_positions.json", buckets["not_positions"])
    write(args.out_dir / "db_resolves.json", buckets["resolves"])
    write(args.out_dir / "db_historical.json", buckets["historical"])

    md = report(args.input, len(qids), buckets, type_labels)
    (args.out_dir / "db_report.md").write_text(md)

    for name, rows in sorted(buckets.items(), key=lambda kv: -len(kv[1])):
        held = sum(r.get("holders", 0) for r in rows)
        print(f"  {name:<14} {len(rows):>5} items, {held:>7} P39 holders")
    print(f"Wrote {args.out_dir}/db_report.md and four JSON slices")


def report(
    source: Path, total: int, buckets: Dict[str, List[Dict[str, Any]]],
    type_labels: Dict[str, str],
) -> str:
    def held(name: str) -> int:
        return sum(r.get("holders", 0) for r in buckets[name])

    md = [
        "# Positions the DB records as country-less",
        "",
        f"Source: `{source}` — {total} distinct QIDs.",
        "",
        "Partitioned by `wd.shape.verify`, which runs zavod's own country walk.",
        "Re-run this after applying a batch: the `no polity` row shrinking is the",
        "coverage gain, and the batch size is not.",
        "",
        "| Slice | Items | P39 holders | What it wants |",
        "| --- | ---: | ---: | --- |",
        f"| deleted / merged away | {len(buckets['gone']) + len(buckets['merged'])} | — | nothing |",
        f"| **resolves today** — DB row is stale | {len(buckets['resolves'])} | {held('resolves')} | a `wd_peps` re-crawl |",
        f"| **not a position** — profession, rank, honour, list article | {len(buckets['not_positions'])} | {held('not_positions')} | a retype, or `is_pep=false` in the DB |",
        f"| **bilateral** — diplomatic post | {len(buckets['bilateral'])} | {held('bilateral')} | `P17`=receiver / `P137`=sender |",
        f"| **scoped to a historical polity** | {len(buckets['historical'])} | {held('historical')} | nothing; correctly country-less |",
        f"| **no polity** — the fixable pool | {len(buckets['census'])} | {held('census')} | `P1001` / `P17` |",
        "",
    ]

    by_via = Counter(r["country_via"] for r in buckets["resolves"])
    md += [
        "## resolves today",
        "",
        "These carry a country on Wikidata now and the positions row was written",
        "before that, or by a crawl that read a lag. No edit is correct here.",
        "",
        f"Reached through: {dict(by_via)}",
        "",
    ]
    for row in buckets["resolves"][:40]:
        md.append(f"* {row['qid']} {row['label']} — {row['holders']} holders, "
                  f"{'/'.join(row['countries'])} via {row['country_via']}")

    declared = Counter(
        type_labels.get(t, t)
        for row in buckets["not_positions"] for t in row["declared"]
    )
    md += [
        "",
        "## not a position",
        "",
        "Country-less by nature. The `P39` statements pointing at these are the",
        "defect — an occupation belongs in `P106`, and an office and the list of",
        "its holders are different items. A jurisdiction claim here would",
        "entrench the mis-type, so none is proposed.",
        "",
        f"Declared types: {dict(declared.most_common(15))}",
        "",
    ]
    for row in buckets["not_positions"][:40]:
        md.append(f"* {row['qid']} {row['label']} — {row['holders']} holders, "
                  f"{row['defects']}, declared {row['declared']}")

    named = [r for r in buckets["census"] if r["label_place"]]
    md += [
        "",
        "## no polity — the fixable pool",
        "",
        f"{len(buckets['census'])} items, {held('census')} P39 holders between them.",
        f"{len(named)} name a territory in their own label; the rest need the",
        "holder-citizenship prior. Both are candidate generators and neither is",
        "a fact — every one is verified before a statement is proposed.",
        "",
    ]
    for row in buckets["census"][:60]:
        place = row["label_place"]
        hint = f" [label: {place['code'] or place['qid']}]" if place else ""
        md.append(f"* {row['qid']} {row['label']} — {row['holders']} holders{hint}")
    return "\n".join(md) + "\n"


if __name__ == "__main__":
    main()
