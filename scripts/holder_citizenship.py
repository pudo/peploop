#!/usr/bin/env python
"""Citizenship signal for bare positions whose label names no country.

    python scripts/holder_citizenship.py

For each bare position (census minus the label-country slice), tally the
holders' P27 citizenships via grouped SPARQL. A strong majority country is
the inference prior for the jurisdiction backfill's second wave: it feeds an
LLM verification pass, never a .qs directly (tasks/jurisdictions.md).

Positions are chunked into VALUES queries under a holder budget so the giant
generic classes (diocesan bishop, 18k holders) don't blow the query that the
small target items share.

Output: data/jurisdictions/holder_citizenship.json + signal tiers on stdout.
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rigour.territories import get_territories

from wd.api import best_label, fetch_entities, sparql
from wd.http import REPO_ROOT, make_session

BASE = REPO_ROOT / "data" / "jurisdictions"

CHUNK_QUERY = """
SELECT ?pos ?c (COUNT(DISTINCT ?p) AS ?n) WHERE {{
  VALUES ?pos {{ {values} }}
  ?p wdt:P39 ?pos .
  ?p wdt:P27 ?c .
}} GROUP BY ?pos ?c
"""


def chunked(targets: list[dict], max_holders: int, max_positions: int):
    chunk: list[str] = []
    budget = 0
    for p in targets:
        if chunk and (budget + p["holders"] > max_holders or len(chunk) >= max_positions):
            yield chunk
            chunk, budget = [], 0
        chunk.append(p["qid"])
        budget += p["holders"]
    if chunk:
        yield chunk


def run_chunk(session, qids: list[str], tries: int, wait: float) -> list[dict]:
    query = CHUNK_QUERY.format(values=" ".join(f"wd:{q}" for q in qids))
    for attempt in range(tries):
        try:
            return sparql(session, query)
        except Exception as exc:
            print(f"  chunk of {len(qids)} attempt {attempt + 1}/{tries}: {exc}",
                  file=sys.stderr)
            if attempt + 1 < tries:
                time.sleep(wait)
    raise SystemExit(f"WDQS would not answer for chunk starting {qids[0]}")


def territory_by_qid() -> dict[str, tuple[str, bool]]:
    index: dict[str, tuple[str, bool]] = {}
    for t in get_territories():
        if t.qid and t.qid not in index:
            index[t.qid] = (t.code, t.is_historical)
    return index


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-holders", type=int, default=12000)
    parser.add_argument("--max-positions", type=int, default=300)
    parser.add_argument("--tries", type=int, default=6)
    parser.add_argument("--wait", type=float, default=30.0)
    parser.add_argument("--census", type=Path, default=BASE / "bare_positions.json",
                        help="census to tally, in bare_positions.json's record shape")
    parser.add_argument("--exclude", type=Path,
                        default=BASE / "label_country_candidates.json",
                        help="census rows already answered by another channel; "
                             "pass 'none' to tally the whole census")
    parser.add_argument("--out", type=Path, default=BASE / "holder_citizenship.json")
    args = parser.parse_args()

    census = json.loads(args.census.read_text())
    labelled = set()
    if str(args.exclude) != "none" and args.exclude.exists():
        labelled = {p["qid"] for p in json.loads(args.exclude.read_text())}
    targets = [p for p in census if p["qid"] not in labelled]
    # Ascending by holders keeps each VALUES chunk homogeneous, so one giant
    # position never stalls a chunk of small ones:
    targets.sort(key=lambda p: p["holders"])
    print(f"{len(targets)} positions without a country in the label", file=sys.stderr)

    session = make_session()
    counts: dict[str, dict[str, int]] = {}
    chunks = list(chunked(targets, args.max_holders, args.max_positions))
    for i, qids in enumerate(chunks):
        rows = run_chunk(session, qids, args.tries, args.wait)
        for row in rows:
            counts.setdefault(row["pos"], {})[row["c"]] = int(row["n"])
        print(f"  chunk {i + 1}/{len(chunks)}: {len(qids)} positions, "
              f"{len(rows)} (pos, country) rows", file=sys.stderr)

    territories = territory_by_qid()
    country_qids = {c for dist in counts.values() for c in dist}
    country_labels = {
        qid: best_label(e)
        for qid, e in fetch_entities(session, country_qids, props="labels").items()
    }

    out = []
    for p in targets:
        dist = counts.get(p["qid"], {})
        total = sum(dist.values())
        countries = [
            {
                "qid": c,
                "label": country_labels.get(c),
                "code": territories.get(c, (None, None))[0],
                "historical": territories.get(c, (None, False))[1],
                "n": n,
            }
            for c, n in sorted(dist.items(), key=lambda kv: -kv[1])
        ]
        record = dict(p)
        record["with_p27"] = total
        record["citizenships"] = countries
        if countries:
            top = countries[0]
            record["top"] = {
                "qid": top["qid"],
                "code": top["code"],
                "historical": top["historical"],
                "n": top["n"],
                "share": round(top["n"] / total, 3),
            }
        else:
            record["top"] = None
        out.append(record)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=1, ensure_ascii=False))

    # Signal tiers, for calibrating the shortlist threshold:
    def tier(pred) -> int:
        return sum(1 for r in out if r["top"] and pred(r))

    no_signal = sum(1 for r in out if not r["top"])
    print(f"no P27 data at all: {no_signal}/{len(out)}")
    for min_n, min_share in [(1, 1.0), (2, 1.0), (3, 0.8), (5, 0.8), (10, 0.8)]:
        n = tier(lambda r: r["with_p27"] >= min_n and r["top"]["share"] >= min_share)
        modern = tier(
            lambda r: r["with_p27"] >= min_n
            and r["top"]["share"] >= min_share
            and not r["top"]["historical"]
            and not r["abolished"]
        )
        print(f"n>={min_n:>2} share>={min_share}: {n:>5}  "
              f"(top not historical, not abolished: {modern})")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
