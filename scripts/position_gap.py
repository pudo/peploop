#!/usr/bin/env python
"""Find people in a Wikipedia category who lack the corresponding P39 on Wikidata.

    python scripts/position_gap.py Q18507240 --category Seimo_nariai --lang lt

Members of the category (candidate holders) are diffed against everyone
Wikidata already records as holding the position — the P39 inverse lookup
(all ranks, so an existing-but-deprecated statement doesn't look like a gap)
plus the position item's own P1308 officeholder claims. The remaining
candidates get a per-person snapshot (label, description, dates, existing
P39s with labels) written to data/positions/<position>.json for LLM review.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wd.api import (
    best_description,
    best_label,
    claim_qids,
    fetch_entities,
    sparql,
)
from wd.http import REPO_ROOT, make_session
from wd.petscan import category_members

OUT_DIR = REPO_ROOT / "data" / "positions"


def year_of(entity: dict, prop: str) -> str | None:
    for claim in entity.get("claims", {}).get(prop, []):
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(value, dict) and "time" in value:
            # Precision coarser than a year (e.g. 7 = century) renders as a
            # misleading year number ("+2000/7" is the 20th century, not the
            # year 2000), so skip those.
            if value.get("precision", 11) < 9:
                continue
            return value["time"].lstrip("+")[:4]
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("position", help="Position QID, e.g. Q18507240")
    parser.add_argument("--category", required=True, help="Wikipedia category name")
    parser.add_argument("--lang", required=True, help="Wikipedia language code")
    parser.add_argument("--depth", type=int, default=0, help="Subcategory depth (default 0)")
    parser.add_argument("--out", type=Path, default=None, help="Output JSON path")
    args = parser.parse_args()

    session = make_session()

    members = category_members(session, args.category, args.lang, depth=args.depth)
    member_qids = {qid for qid, _ in members}
    titles = dict(members)

    # All ranks on purpose: wdt:P39 only yields best-rank statements, and a
    # deprecated statement still means "don't propose adding this".
    holder_rows = sparql(
        session,
        f"SELECT DISTINCT ?p WHERE {{ ?p p:P39 ?st . ?st ps:P39 wd:{args.position} . }}",
    )
    holders = {row["p"] for row in holder_rows}

    position_entities = fetch_entities(session, [args.position])
    position = next(iter(position_entities.values()), None)
    if position is None:
        raise SystemExit(f"No such position item: {args.position}")
    if position["id"] != args.position:
        raise SystemExit(
            f"{args.position} redirects to {position['id']} - use the target QID"
        )
    holders.update(claim_qids(position, "P1308"))
    position_label = best_label(position)

    candidate_qids = sorted(member_qids - holders, key=lambda q: int(q[1:]))
    entities = fetch_entities(session, candidate_qids)

    # Labels for the candidates' existing P39 positions, one batch:
    other_positions: set[str] = set()
    for entity in entities.values():
        other_positions.update(claim_qids(entity, "P39"))
    position_labels = {
        qid: best_label(entity)
        for qid, entity in fetch_entities(
            session, other_positions, props="labels"
        ).items()
    }

    candidates = []
    for qid in candidate_qids:
        entity = entities.get(qid)
        if entity is None:
            continue
        if entity["id"] != qid and entity["id"] in holders:
            continue  # merged into an item that already holds the position
        # PETScan's "uses Q5" filter also passes non-person pages whose item
        # merely references Q5 (e.g. Category: items via P4224), so enforce
        # instance-of-human ourselves:
        if "Q5" not in claim_qids(entity, "P31"):
            continue
        candidates.append(
            {
                "qid": entity["id"],
                "title": titles.get(qid),
                "label": best_label(entity),
                "description": best_description(entity),
                "birth": year_of(entity, "P569"),
                "death": year_of(entity, "P570"),
                "positions_held": [
                    {"qid": p, "label": position_labels.get(p)}
                    for p in claim_qids(entity, "P39")
                ],
            }
        )

    report = {
        "position": {"qid": args.position, "label": position_label},
        "category": {"name": args.category, "lang": args.lang, "depth": args.depth},
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "members": len(member_qids),
        "holders": len(holders),
        "candidates": candidates,
    }

    out_path = args.out or OUT_DIR / f"{args.position}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    print(
        f"{position_label} ({args.position}): {len(member_qids)} in category, "
        f"{len(holders)} holders on Wikidata, {len(candidates)} candidates missing P39"
    )
    for c in candidates[:15]:
        held = "; ".join(p["label"] or p["qid"] for p in c["positions_held"]) or "-"
        print(f"  {c['qid']:<12} {c['label'] or c['title']}  [holds: {held}]")
    if len(candidates) > 15:
        print(f"  ... and {len(candidates) - 15} more")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
