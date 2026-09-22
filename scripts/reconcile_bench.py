#!/usr/bin/env python
"""Measure the second turn against the silver test set.

    python scripts/reconcile_bench.py --country cz --limit 20

Retrieval is measured by `position_bench.py`; this measures what a model
makes of the fifteen rows it hands over. Every row asked is recorded in
`resolution` under the exact extraction the mention came from, so the bench
and the live loop share one ledger, a re-run costs only what is new, and
widening the sample later reuses every answer already bought.

The sample is drawn round-robin over distinct gold answers rather than from
the top of the file, because one office is nearly half the gold rows and a
prefix of the fixture would measure that office alone.

Four numbers matter, and the first is the least of them. *Agreement* is the
share of asked rows where the pick equals the gold QID; the fixture is about
22% mispaired, so the ceiling is well under 100% and the figure is a floor.
*False match* is a `same-office`/`renamed` pick that is not gold and not a
row the fixture itself flags as doubtful -- the number a wrong P39 would be
made of. *Abstain with gold shown* is the model refusing a shortlist that
contained the answer. *Gold not shown* is retrieval's miss, and no verdict is
blamed for it.
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from peploop import db, positions, reconcile

FIXTURES = Path(__file__).resolve().parents[1] / "peploop" / "fixtures"

#: Hand-read truth for rows where the silver label and a verdict disagreed:
#: `person_qid, title, lang, start, truth_qid, status, note`. A row whose
#: `status` is `verified` replaces the gold QID for scoring; `unknown` rows
#: are listed and never scored. Written by hand after reading the person's
#: live P39, never by the bench.
VERIFIED = FIXTURES / "cz_positions_verified.jsonl"


def verified() -> dict[tuple[str, str, str | None, str | None], dict[str, Any]]:
    """Map a fixture row's identity to its hand-read truth, if any."""
    if not VERIFIED.exists():
        return {}
    out = {}
    for line in VERIFIED.read_text().splitlines():
        if line.strip():
            row = json.loads(line)
            out[(row["person_qid"], row["title"], row.get("lang"), row.get("start"))] = row
    return out


def key_of(row: dict[str, Any]) -> tuple[str, str, str | None, str | None]:
    return (row["person_qid"], row["title"], row.get("lang"), row.get("start"))


def sample(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """Take `limit` gold rows, one per distinct answer per round, deterministically."""
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in sorted(rows, key=lambda r: (r["person_qid"], r["title"], r.get("lang") or "")):
        groups[row["gold_qid"]].append(row)
    order = sorted(groups, key=lambda q: (-len(groups[q]), q))
    out: list[dict[str, Any]] = []
    while len(out) < limit and any(groups.values()):
        for qid in order:
            if groups[qid] and len(out) < limit:
                out.append(groups[qid].pop(0))
    return out


def latest_extraction(person_qid: str) -> tuple[int, list[dict[str, Any]]] | None:
    row = db.conn().execute(
        "SELECT id, response_json->'positions' FROM extraction WHERE qid = %s"
        " ORDER BY id DESC LIMIT 1",
        (person_qid,),
    ).fetchone()
    return None if row is None else (row[0], list(row[1] or []))


def locate(row: dict[str, Any], mentions: list[dict[str, Any]]) -> int | None:
    """Find the extraction entry a fixture row was cut from.

    The fixture copied title, language and dates verbatim, so an exact match
    on all of them is the entry; a title match alone is the fallback for a
    row whose extraction has since been redone.
    """
    keys = (("title", "title"), ("lang", "lang"), ("start", "start"), ("end", "end"))
    for idx, entry in enumerate(mentions):
        if all(entry.get(b) == row.get(a) for a, b in keys):
            return idx
    for idx, entry in enumerate(mentions):
        if entry.get("title") == row["title"]:
            return idx
    return None


def pct(n: int, d: int) -> str:
    return f"{100.0 * n / d:5.1f}%" if d else "  n/a "


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--country", default="cz")
    parser.add_argument("--limit", type=int, default=20, help="Gold rows to ask about.")
    parser.add_argument("--model", default=reconcile.MODEL)
    parser.add_argument("--no-ask", action="store_true",
                        help="Report only what the ledger already holds; send nothing.")
    parser.add_argument("--show", type=int, default=5,
                        help="Print this many shortlists carrying a generic-by-convention"
                             " candidate in full, with the verdict.")
    args = parser.parse_args()

    path = FIXTURES / f"{args.country}_positions.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    gold = [row for row in rows if row.get("gold_qid")]
    chosen = sample(gold, args.limit)
    state_qid = positions.country_qid(args.country)
    _text, prompt_hash = reconcile.system_prompt()
    print(f"{len(gold)} gold rows, {len(chosen)} sampled over"
          f" {len({r['gold_qid'] for r in chosen})} answers; prompt {prompt_hash[:12]}")

    truth = verified()
    unlocated = 0
    asked = 0
    usage: Counter[str] = Counter()
    results: list[tuple[dict[str, Any], reconcile.Verdict, int | None]] = []
    generic: list[tuple[dict[str, Any], reconcile.Verdict, list[reconcile.Candidate]]] = []
    for row in chosen:
        found = latest_extraction(row["person_qid"])
        idx = None if found is None else locate(row, found[1])
        if found is None or idx is None:
            unlocated += 1
            continue
        extraction_id, mentions = found
        mention = reconcile.mention_from(mentions[idx])
        if args.no_ask:
            verdict = reconcile.recorded(extraction_id, idx, prompt_hash)
            if verdict is None:
                continue
        else:
            verdict, sent = reconcile.resolve_mention(
                extraction_id, idx, mention, state_qid, model=args.model
            )
            if sent:
                asked += 1
                usage.update(verdict.usage or {})
        row = dict(row)
        checked = truth.get(key_of(row))
        row["silver_qid"] = row["gold_qid"]
        row["checked"] = None if checked is None else checked.get("status")
        if checked is not None and checked.get("status") == "verified":
            row["gold_qid"] = checked.get("truth_qid")
        shown = verdict.shortlist
        rank = shown.index(row["gold_qid"]) + 1 if row["gold_qid"] in shown else None
        results.append((row, verdict, rank))
        mark = "=" if verdict.qid == row["gold_qid"] else ("x" if verdict.qid else "-")
        flag = {"verified": "v", "unknown": "?", None: " "}[row["checked"]]
        print(f"  {mark}{flag}{row['person_qid']:11s} {row['title'][:44]:44s}"
              f" gold={str(row['gold_qid']):11s}"
              f" rank={rank if rank else '-':>2} {verdict.kind:14s} {verdict.confidence:6s}"
              f" pick={verdict.qid or verdict.chosen or '-'}")
        if len(generic) < args.show:
            hits = positions.search(mention.title, mention.jurisdiction, state_qid,
                                    limit=reconcile.SHORTLIST, start=mention.start,
                                    end=mention.end)
            if any("generic-by-convention" in hit.tags for hit in hits):
                generic.append((row, verdict, reconcile.candidates_for(hits, state_qid)))

    n = len(results)
    if not n:
        print("nothing to report")
        return
    shown_rows = [(r, v, k) for r, v, k in results if k is not None]
    agree = [v.qid == r["gold_qid"] for r, v, _ in results]
    matched = [(r, v) for r, v, _ in results if v.qid is not None]
    false_match = [(r, v) for r, v in matched if v.qid != r["gold_qid"]]
    false_clean = [(r, v) for r, v in false_match if r.get("vocab_overlap")]
    abstain = [(r, v) for r, v, k in shown_rows if v.qid is None]
    overlap = [(r, v, k) for r, v, k in results if r.get("vocab_overlap")]

    checked = [(r, v, k) for r, v, k in results if r["checked"] == "verified"]
    unread = [(r, v) for r, v, k in results
              if r["checked"] is None and v.qid != r["gold_qid"]]
    print()
    print(f"rows {n}, asked now {asked}, unlocated {unlocated};"
          f" {len(checked)} scored against hand-read truth,"
          f" {sum(1 for r, _, _ in results if r['checked'] == 'unknown')} unknown")
    print(f"agreement            {pct(sum(agree), n)}  ({sum(agree)}/{n})")
    print(f"  on vocab_overlap   {pct(sum(v.qid == r['gold_qid'] for r, v, _ in overlap), len(overlap))}"
          f"  ({len(overlap)} rows)")
    print(f"  with gold shown    {pct(sum(v.qid == r['gold_qid'] for r, v, _ in shown_rows), len(shown_rows))}"
          f"  ({len(shown_rows)} rows)")
    print(f"gold not shown       {pct(n - len(shown_rows), n)}  (retrieval's miss)")
    print(f"matched              {pct(len(matched), n)}")
    print(f"false match          {pct(len(false_match), len(matched))} of matches"
          f"  ({len(false_match)}; {len(false_clean)} where fixture row shares vocabulary)")
    print(f"abstain, gold shown  {pct(len(abstain), len(shown_rows))}")
    print()
    print("kind x confidence:")
    dist = Counter((v.kind, v.confidence) for _, v, _ in results)
    for (kind, conf), count in sorted(dist.items()):
        print(f"  {kind:14s} {conf:6s} {count}")
    vetoes = Counter(v.veto for _, v, _ in results if v.veto)
    if vetoes:
        print(f"vetoes: {dict(vetoes)}")
    if asked:
        print("tokens per asked request: " + ", ".join(
            f"{k.replace('_input_tokens', '').replace('_tokens', '')}={v / asked:,.0f}"
            for k, v in sorted(usage.items())))

    if unread:
        print()
        print(f"disagreements not yet hand-read ({len(unread)}):")
        for r, v in unread:
            print(json.dumps({"person_qid": r["person_qid"], "title": r["title"],
                              "lang": r.get("lang"), "start": r.get("start"),
                              "silver_qid": r["silver_qid"], "pick": v.qid or v.chosen,
                              "kind": v.kind}, ensure_ascii=False))

    if false_match:
        print()
        print("false matches (pick != gold):")
        for r, v in false_match:
            flag = "" if r.get("vocab_overlap") else "  [fixture row shares no vocabulary with gold]"
            flag += "  [verified]" if r["checked"] == "verified" else ""
            print(f"  {r['person_qid']} {r['title']!r} gold={r['gold_qid']} pick={v.qid}"
                  f" {v.kind}/{v.confidence}{flag}")
            print(f"      evidence: {v.evidence}")
            print(f"      reason:   {v.reason}")

    if generic:
        print()
        print(f"generic-by-convention cases, {len(generic)} shown in full:")
        for r, v, candidates in generic:
            print()
            print(reconcile.render_mention(reconcile.mention_from(
                {"title": r["title"], "jurisdiction": r["jurisdiction"], "start": r.get("start"),
                 "end": r.get("end"), "lang": r.get("lang")}), candidates))
            print(f">> gold={r['gold_qid']} verdict={v.kind}/{v.confidence} pick={v.qid or v.chosen}")
            print(f">> evidence: {v.evidence}")
            print(f">> reason: {v.reason}")


if __name__ == "__main__":
    main()
