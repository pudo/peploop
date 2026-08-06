#!/usr/bin/env python
"""Split the unresolved tail into per-agent chunk files.

    python scripts/category_tail_chunks.py tail bucket

Each chunk holds the rows one verification agent adjudicates, with all the
evidence the mechanical pass gathered (candidates + flags, the category
item's topic links, the P39 tally). Agents write JSONL verdicts to
data/categories/verdicts/; the renderer merges them back.
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wd.http import REPO_ROOT

OUT_DIR = REPO_ROOT / "data" / "categories"
CHUNKS = 8
# Trim the candidate list: agents get the plausible ones plus their evidence,
# not the whole search dump.
KEEP_CANDIDATES = 8


def slim(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "key": row["key"],
        "category": row["category"],
        "language": row["language"],
        "category_lang": row.get("category_lang"),
        "language_mismatch": row.get("language_mismatch"),
        "depth": row["depth"],
        "position_name": row["position_name"],
        "position_country": row["position_country"],
        "position_topics": row["position_topics"],
        "granularity": row["granularity"],
        "prior_status": row["status"],
        "mechanical_status": row["tail_status"],
        "mechanical_qid": row["tail_qid"],
        "duplicates": row.get("duplicates", []),
        "category_qid": row.get("category_qid"),
        "category_hints": row.get("category_hints", {}),
        "member_count": row["tally"].get("members"),
        "p39_tally": row["tally"].get("top", []),
        "candidates": [
            {
                k: c[k] for k in (
                    "qid", "label", "description", "types", "subclass_of",
                    "country_qids", "part_of", "holder_count", "is_list",
                    "is_position", "label_match", "country_match",
                    "main_topic", "from_tally", "holder_share",
                )
            }
            for c in row["candidates"][:KEEP_CANDIDATES]
        ],
    }


def main(names: List[str]) -> None:
    rows: List[Dict[str, Any]] = []
    for name in names or ["tail"]:
        rows.extend(json.load((OUT_DIR / f"{name}.json").open()))

    todo = [r for r in rows if r["tail_status"] != "tail-matched"]
    confirmed = [r for r in rows if r["tail_status"] == "tail-matched"]
    # Auto-matches still get a reviewer, just spread across the same chunks:
    # the mechanical rule is new and its false-positive mode was real.
    ordered = todo + confirmed

    chunk_dir = OUT_DIR / "chunks_tail"
    chunk_dir.mkdir(parents=True, exist_ok=True)
    for path in chunk_dir.glob("chunk_*.json"):
        path.unlink()
    buckets: List[List[Dict[str, Any]]] = [[] for _ in range(CHUNKS)]
    for i, row in enumerate(ordered):
        buckets[i % CHUNKS].append(slim(row))
    for i, bucket in enumerate(buckets):
        (chunk_dir / f"chunk_{i}.json").write_text(
            json.dumps(bucket, indent=1, ensure_ascii=False))
    print(f"{len(ordered)} rows ({len(todo)} unresolved, {len(confirmed)} "
          f"auto-matched) → {CHUNKS} chunks in {chunk_dir}")


if __name__ == "__main__":
    main(sys.argv[1:])
