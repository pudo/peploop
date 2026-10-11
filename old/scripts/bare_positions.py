#!/usr/bin/env python
"""Census of P39 position items with no country/jurisdiction on Wikidata.

    python scripts/bare_positions.py --floor 1

These positions are invisible to the OpenSanctions wikidata crawlers (zavod
skips positions it cannot link to a country), so they are candidates for a
P1001/P17 backfill — see tasks/jurisdictions.md.

Strategy: one grouped SPARQL query (retried patiently; WDQS times out under
load) yields every P39 target lacking direct P17/P1001 plus its holder count.
The item details needed for classification — labels, P31 ancestry, the
traversal properties zavod could still rescue a country from, abolition
dates, sitelinks — come from batched wbgetentities calls, filtered locally.

Output: data/jurisdictions/bare_positions.json + a tier summary on stdout.
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wd.api import best_description, best_label, claim_qids, fetch_entities, sparql
from wd.http import REPO_ROOT, make_session

OUT_DIR = REPO_ROOT / "data" / "jurisdictions"

# Properties zavod's item_countries() traversal can pull a country out of;
# their presence means the position may still resolve despite missing
# P17/P1001 (first-order check only - we don't follow the links here).
TRAVERSAL_PROPS = ["P27", "P361", "P749", "P159", "P1376", "P2389"]

CENSUS_QUERY = """
SELECT ?pos ?holders WHERE {{
  {{ SELECT ?pos (COUNT(DISTINCT ?p) AS ?holders) WHERE {{
       ?p wdt:P39 ?pos .
     }} GROUP BY ?pos HAVING(?holders >= {floor}) }}
  FILTER NOT EXISTS {{ ?pos wdt:P17 [] }}
  FILTER NOT EXISTS {{ ?pos wdt:P1001 [] }}
}}
"""


def first_year(entity: dict, prop: str) -> str | None:
    for claim in entity.get("claims", {}).get(prop, []):
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(value, dict) and "time" in value:
            if value.get("precision", 11) >= 9:
                return value["time"].lstrip("+")[:4]
    return None


def fetch_census(session, floor: int, tries: int, wait: float) -> list[dict]:
    query = CENSUS_QUERY.format(floor=floor)
    for attempt in range(tries):
        try:
            return sparql(session, query)
        except Exception as exc:
            print(f"census query attempt {attempt + 1}/{tries} failed: {exc}",
                  file=sys.stderr)
            if attempt + 1 < tries:
                time.sleep(wait)
    raise SystemExit("WDQS would not answer the census query; try again later")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--floor", type=int, default=1, help="Minimum P39 holders")
    parser.add_argument("--tries", type=int, default=6, help="Census query attempts")
    parser.add_argument("--wait", type=float, default=45.0, help="Seconds between attempts")
    parser.add_argument("--out", type=Path, default=OUT_DIR / "bare_positions.json")
    args = parser.parse_args()

    session = make_session()
    rows = fetch_census(session, args.floor, args.tries, args.wait)
    holders = {row["pos"]: int(row["holders"]) for row in rows}
    print(f"{len(holders)} bare positions (holders >= {args.floor})", file=sys.stderr)

    entities = fetch_entities(session, sorted(holders, key=lambda q: -holders[q]))

    # Resolve labels for the P31 types in one extra batch, so the output is
    # readable without another round of lookups:
    type_qids: set[str] = set()
    for entity in entities.values():
        type_qids.update(claim_qids(entity, "P31"))
    type_labels = {
        qid: best_label(e)
        for qid, e in fetch_entities(session, type_qids, props="labels").items()
    }

    positions = []
    for qid, count in sorted(holders.items(), key=lambda kv: -kv[1]):
        entity = entities.get(qid)
        if entity is None:
            continue  # deleted since the query ran
        if entity["id"] != qid:
            continue  # redirect; the target will carry its own claims
        traversal = [p for p in TRAVERSAL_PROPS if entity.get("claims", {}).get(p)]
        sitelinks = entity.get("sitelinks", {})
        positions.append(
            {
                "qid": qid,
                "label": best_label(entity),
                "description": best_description(entity),
                "holders": count,
                "instance_of": [
                    {"qid": t, "label": type_labels.get(t)}
                    for t in claim_qids(entity, "P31")
                ],
                "traversal_props": traversal,
                "inception": first_year(entity, "P571"),
                "abolished": first_year(entity, "P576"),
                "sitelinks": len(sitelinks),
                "enwiki": (sitelinks.get("enwiki") or {}).get("title"),
            }
        )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(positions, indent=2, ensure_ascii=False))

    hard = [p for p in positions if not p["traversal_props"]]
    print(f"total bare: {len(positions)}  "
          f"no traversal props at all (definitely skipped): {len(hard)}  "
          f"maybe rescued: {len(positions) - len(hard)}")
    for p in hard[:20]:
        types = ", ".join(t["label"] or t["qid"] for t in p["instance_of"][:3])
        print(f"  {p['qid']:<12} {p['holders']:>6}  {p['label']}  [{types}]")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
