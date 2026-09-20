#!/usr/bin/env python
"""Build the silver test set for position reconciliation.

    python scripts/position_fixture.py

One row per extracted title, carrying the person's P39 statements as a weak
label and, where exactly one of them starts when the title does, a
`gold_qid`. Nothing is hand-labelled: the pairing is date agreement at the
coarser of the two precisions, which is why a title whose only date is an end
pairs on the end instead. Output is `peploop/fixtures/cz_positions.jsonl`.
"""

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from peploop.db import conn

OUT_PATH = Path(__file__).resolve().parents[1] / "peploop" / "fixtures" / "cz_positions.jsonl"
PRECISION_LEN = {11: 10, 10: 7, 9: 4}


def claim_date(claim: dict[str, Any], prop: str) -> str | None:
    """Read a P580/P582 qualifier as an ISO date truncated to its precision."""
    quals = claim.get("qualifiers") or {}
    snaks = quals.get(prop) or []
    for snak in snaks:
        value = (snak.get("datavalue") or {}).get("value") or {}
        time, precision = value.get("time"), value.get("precision")
        length = PRECISION_LEN.get(precision)
        if time is None or length is None:
            continue
        return time.lstrip("+")[:length]
    return None


def p39_claims(entity: dict[str, Any] | None) -> list[dict[str, Any]]:
    """List a person's non-deprecated P39 statements as qid/start/end."""
    claims = ((entity or {}).get("claims") or {}).get("P39") or []
    out = []
    for claim in claims:
        if claim.get("rank") == "deprecated":
            continue
        value = ((claim.get("mainsnak") or {}).get("datavalue") or {}).get("value") or {}
        qid = value.get("id")
        if qid is None:
            continue
        out.append({"qid": qid, "start": claim_date(claim, "P580"), "end": claim_date(claim, "P582")})
    return sorted(out, key=lambda c: (c["qid"], c["start"] or ""))


def agrees(left: str | None, right: str | None) -> bool:
    """Report whether two ISO dates agree at the coarser of their precisions."""
    if left is None or right is None:
        return False
    return left.startswith(right) or right.startswith(left)


def gold_for(title: dict[str, Any], claims: list[dict[str, Any]]) -> str | None:
    """Return the one P39 whose tenure starts (or ends) when the title does."""
    for prop in ("start", "end"):
        if title.get(prop) is None:
            continue
        hits = [c["qid"] for c in claims if agrees(title[prop], c[prop])]
        return hits[0] if len(hits) == 1 else None
    return None


def rows() -> list[dict[str, Any]]:
    """Join every extracted title of the latest extraction per person to P39."""
    records = conn().execute(
        "SELECT DISTINCT ON (e.qid) e.qid, e.response_json -> 'positions', i.json"
        " FROM extraction e LEFT JOIN item i ON i.qid = e.qid"
        " ORDER BY e.qid, e.id DESC"
    ).fetchall()
    out = []
    for qid, positions, entity in records:
        claims = p39_claims(entity)
        for title in positions or []:
            out.append(
                {
                    "person_qid": qid,
                    "title": title.get("title"),
                    "jurisdiction": title.get("jurisdiction"),
                    "lang": title.get("lang"),
                    "start": title.get("start"),
                    "end": title.get("end"),
                    "acting": title.get("acting"),
                    "p39": claims,
                    "gold_qid": gold_for(title, claims),
                }
            )
    return sorted(out, key=lambda r: (r["person_qid"], r["title"] or "", r["start"] or ""))


def main() -> None:
    fixture = rows()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8") as fh:
        for row in fixture:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    gold = [r for r in fixture if r["gold_qid"]]
    weak = [r for r in fixture if not r["gold_qid"] and r["p39"]]
    none = [r for r in fixture if not r["gold_qid"] and not r["p39"]]
    print(f"people:           {len({r['person_qid'] for r in fixture})}")
    print(f"titles:           {len(fixture)}")
    print(f"gold pair:        {len(gold)}")
    print(f"weak label only:  {len(weak)}")
    print(f"no label:         {len(none)}")
    print(f"written:          {OUT_PATH}")
    print("top gold QIDs:")
    for qid, count in Counter(r["gold_qid"] for r in gold).most_common(10):
        print(f"  {qid:>12}  {count}")


if __name__ == "__main__":
    main()
