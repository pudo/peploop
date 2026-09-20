#!/usr/bin/env python
"""Score position retrieval against the silver test set.

    python scripts/position_bench.py --country cz

The number this prints is what every later ranking change is a delta
against, so it is measured before any ranking signal exists. Retrieval is
the half that cannot be recovered downstream: a model only ever sees the
shortlist, so the right item at rank 40 and no right item at all are the
same failure.

Three scores, because the test set has two kinds of label and two grains. A
*gold* row pairs a title to one P39 by date agreement and is scored on rank;
the same numbers are reported again **per tenure**, deduplicated by
`(person, tenure_id)`, because one office named in six wikis is six titles
and one answer, and the per-title aggregate counts it six times. Per tenure
is the number that means "tenures reconciled". A *weak* row
knows only the person's whole P39 set and is scored on whether any of it
appears -- which is a ceiling, not an accuracy. Gold rows are reported
macro-averaged over distinct answers as well as in aggregate, because one
office is nearly half of them and the aggregate is otherwise a statement
about that office.

The last number is about the test set rather than the search. Pairing by
date agreement is cheap and wrong a quarter of the time: a party post and
a parliamentary seat that begin on the same day pair to each other, and no
retrieval could ever find such an answer. The fixture writes that judgement
onto each gold row as `vocab_overlap` -- does the title share any content
token with any name or indexed token of its own answer -- and never uses it
to select a pair, because a silver set chosen by token overlap cannot
measure a token-based retriever. Here it only splits the report, so the
share that is the heuristic's fault is visible apart from the index's.
"""

import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from peploop import db, positions

FIXTURES = Path(__file__).resolve().parents[1] / "peploop" / "fixtures"


def name_tokens() -> dict[str, set[str]]:
    """Every content token of every name, per position, for the label check."""
    out: dict[str, set[str]] = defaultdict(set)
    for qid, text in db.conn().execute("SELECT qid, text FROM position_name"):
        out[qid] |= positions.tokens(text)
    return out


def rank_of(hits: list[Any], wanted: set[str]) -> int | None:
    """One-based rank of the first wanted QID in the shortlist, or None."""
    for index, hit in enumerate(hits, 1):
        if hit.qid in wanted:
            return index
    return None


def summarise(name: str, ranks: list[int | None], limit: int) -> None:
    """Print recall and MRR for one slice of the test set."""
    if not ranks:
        return
    found = [r for r in ranks if r is not None]
    recall = len(found) / len(ranks)
    mrr = sum(1 / r for r in found) / len(ranks)
    top1 = len([r for r in found if r == 1]) / len(ranks)
    print(f"  {name:<34} n={len(ranks):<5} recall@{limit}={recall:6.1%}"
          f"  MRR={mrr:.3f}  top1={top1:6.1%}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--country", default="cz")
    parser.add_argument("--limit", type=int, default=15)
    parser.add_argument("--pool", type=int, default=positions.CANDIDATE_POOL,
                        help="How deep the text index retrieves before the "
                             "signals re-order and the shortlist is cut.")
    parser.add_argument("--no-jurisdiction", action="store_true",
                        help="Score the title channel alone.")
    parser.add_argument("--global-scope", action="store_true",
                        help="Do not try the run's country first.")
    parser.add_argument("--signals", default="all",
                        help="Comma-separated ranking signals, 'all', or "
                             "'none' for the text order alone.")
    parser.add_argument("--held-subclass-floor", type=int,
                        default=positions.HELD_SUBCLASS_FLOOR)
    parser.add_argument("--convention-floor", type=int,
                        default=positions.CONVENTION_FLOOR)
    parser.add_argument("--json", action="store_true",
                        help="Print the four headline slices as one JSON line.")
    args = parser.parse_args()
    if args.signals == "all":
        signals = positions.SIGNALS
    elif args.signals in ("none", ""):
        signals = ()
    else:
        signals = tuple(args.signals.split(","))
        unknown = set(signals) - set(positions.SIGNALS)
        if unknown:
            parser.error(f"unknown signals: {sorted(unknown)}")

    path = FIXTURES / f"{args.country}_positions.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    country_qid = None if args.global_scope else positions.country_qid(args.country)

    gold_ranks: list[int | None] = []
    weak_ranks: list[int | None] = []
    per_answer: dict[str, list[int | None]] = defaultdict(list)
    by_lang: dict[str, list[int | None]] = defaultdict(list)
    by_juris: dict[str, list[int | None]] = defaultdict(list)
    empty = 0
    unpairable = 0
    valid_ranks: list[int | None] = []
    known = name_tokens()
    seen: dict[tuple[str, str | None], int | None] = {}
    per_tenure: dict[tuple[str, Any], int | None] = {}

    for row in rows:
        title = row["title"]
        jurisdiction = None if args.no_jurisdiction else row["jurisdiction"]
        hits = positions.search(
            title, jurisdiction, country_qid, limit=args.limit,
            start=row.get("start"), end=row.get("end"), signals=signals,
            held_subclass_floor=args.held_subclass_floor,
            convention_floor=args.convention_floor,
            pool=args.pool,
        )
        if not hits:
            empty += 1
        if row["gold_qid"]:
            rank = rank_of(hits, {row["gold_qid"]})
            gold_ranks.append(rank)
            per_answer[row["gold_qid"]].append(rank)
            by_lang[row["lang"]].append(rank)
            by_juris["with jurisdiction" if row["jurisdiction"]
                     else "without jurisdiction"].append(rank)
            seen.setdefault((title.casefold(), row["gold_qid"]), rank)
            # A tenure scores once, on its best-ranked title: several wikis
            # naming one office is one answer to get right, not six.
            key = (row["person_qid"], row.get("tenure_id", title.casefold()))
            if per_tenure.get(key) is None or (rank is not None and rank < per_tenure[key]):
                per_tenure[key] = rank
            overlap = row.get("vocab_overlap")
            if overlap is None:
                overlap = bool(positions.tokens(title) & known.get(row["gold_qid"], set()))
            if overlap:
                valid_ranks.append(rank)
            else:
                unpairable += 1
        elif row["p39"]:
            weak_ranks.append(rank_of(hits, {c["qid"] for c in row["p39"]}))

    if args.json:
        def slice_of(ranks: list[int | None]) -> dict[str, float]:
            found = [r for r in ranks if r is not None]
            return {
                "n": len(ranks),
                "recall": len(found) / len(ranks),
                "mrr": sum(1 / r for r in found) / len(ranks),
                "top1": len([r for r in found if r == 1]) / len(ranks),
            }
        macro = {
            "n": len(per_answer),
            "recall": statistics.mean(
                len([r for r in rs if r is not None]) / len(rs)
                for rs in per_answer.values()),
            "mrr": statistics.mean(
                sum(1 / r for r in rs if r is not None) / len(rs)
                for rs in per_answer.values()),
        }
        print(json.dumps({
            "signals": list(signals),
            "pool": args.pool,
            "held_subclass_floor": args.held_subclass_floor,
            "convention_floor": args.convention_floor,
            "aggregate": slice_of(gold_ranks),
            "tenure": slice_of(list(per_tenure.values())),
            "macro": macro,
            "overlap": slice_of(valid_ranks),
        }))
        return

    print(f"fixture: {path.name}, {len(rows)} titles, limit {args.limit}, "
          f"pool {args.pool}, "
          f"signals {list(signals) or 'none'}, "
          f"country {'global' if country_qid is None else country_qid}, "
          f"jurisdiction {'off' if args.no_jurisdiction else 'on'}")
    print(f"titles retrieving nothing at all: {empty} ({empty / len(rows):.1%})\n")

    print("gold rows (one dated P39 pairs the title):")
    summarise("aggregate", gold_ranks, args.limit)
    summarise("deduplicated by title", list(seen.values()), args.limit)
    summarise("deduplicated by tenure", list(per_tenure.values()), args.limit)
    recalls = [len([r for r in rs if r is not None]) / len(rs)
               for rs in per_answer.values()]
    mrrs = [sum(1 / r for r in rs if r is not None) / len(rs)
            for rs in per_answer.values()]
    print(f"  {'macro over ' + str(len(per_answer)) + ' answers':<34} "
          f"recall@{args.limit}={statistics.mean(recalls):6.1%}"
          f"  MRR={statistics.mean(mrrs):.3f}")

    total_gold = len(gold_ranks)
    print(f"\n  of {total_gold} gold rows, {unpairable} have vocab_overlap false "
          f"({unpairable / total_gold:.1%}): the title shares no token with any")
    print("  name of its own answer, so the date heuristic paired them wrongly")
    summarise("excluding those", valid_ranks, args.limit)

    print("\nweak rows (any of the person's P39):")
    summarise("aggregate", weak_ranks, args.limit)

    print("\ngold rows by title language:")
    for lang, ranks in sorted(by_lang.items(), key=lambda kv: -len(kv[1])):
        summarise(lang, ranks, args.limit)

    print("\ngold rows by whether a jurisdiction was extracted:")
    for label, ranks in sorted(by_juris.items()):
        summarise(label, ranks, args.limit)

    worst = Counter()
    for qid, ranks in per_answer.items():
        misses = len([r for r in ranks if r is None])
        if misses:
            worst[qid] = misses
    if worst:
        print("\nanswers missed most often:")
        for qid, misses in worst.most_common(10):
            print(f"  {qid:<12} missed {misses} of {len(per_answer[qid])}")


if __name__ == "__main__":
    main()
