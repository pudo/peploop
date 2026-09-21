#!/usr/bin/env python
"""Build the silver test set for position reconciliation.

    python scripts/position_fixture.py
    python scripts/position_fixture.py --compare peploop/fixtures/old.jsonl

One row per extracted title, carrying the person's P39 statements as a weak
label and, where the structure of the person's record identifies exactly one
of them, a `gold_qid`. Nothing is hand-labelled.

The pairing is **date- and structure-driven, never text-driven**, and that is
the whole design. A silver set selected by vocabulary overlap cannot be used
to measure a token-based retriever: recall goes to 100% by construction and
the benchmark measures its own selection rule. So the title text never decides
a label here; agreement between the title's vocabulary and the answer's is
written onto the row as a diagnostic (`vocab_overlap`) and read afterwards.

Four rules replace the first version's "first P39 whose start agrees", which
mislabelled about a quarter of the set by pairing correlated offices that
merely begin on the same day:

1. A person's titles are grouped into tenures by `(start, end, acting)`.
   Extraction reads one article per language, so one tenure is named at most
   once per language: a language occurring twice inside a date group proves
   the group holds two or more distinct offices, and the whole group is
   awarded nothing.
2. Every endpoint both sides carry must agree. The first version returned on
   the first non-null of start/end and never looked at the other, so a title
   that ran 2010-2011 paired happily with a statement that ran 2010-2013.
3. Matching is one-to-one at the tenure level: a statement is gold for at most
   one tenure and a tenure for at most one statement. Ties are dropped rather
   than broken. At tenure level and not title level, because one ministry
   named in six wikis is six titles, one tenure, and one right answer.
4. Tightness orders the competition: both endpoints beats one, day beats
   month beats year.
"""

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from peploop import positions
from peploop.db import conn

OUT_PATH = Path(__file__).resolve().parents[1] / "peploop" / "fixtures" / "cz_positions.jsonl"
PRECISION_LEN = {11: 10, 10: 7, 9: 4}
#: How much an agreement is worth, by the length of the coarser ISO date.
PRECISION_RANK = {10: 3, 7: 2, 4: 1}
#: A token in more than this share of position documents says nothing about
#: which position a title means, so the strict diagnostic ignores it.
COMMON_SHARE = 0.05
COLLISION = "the date group names one language twice, so it holds more than one office"


@dataclass
class Rules:
    """Which pairing rules are in force, so the ablation is one command.

    The defaults are what the fixture ships, and only the first rule does.
    The other two were implemented, measured against the answers they keep
    and discard, and found to select *against* correct pairs; they survive as
    switches because a rejected rule is worth being able to re-run, not
    because either is a preference. `peploop/positions_discarded.md` says
    what each cost.
    """

    #: Two titles in one language with the same dates are two offices, not
    #: one tenure named twice — extraction reads one article per language.
    language_collision: bool = True
    both_endpoints: bool = False
    one_to_one: bool = False
    tolerance: int | None = None


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


def endpoint_match(
    dates: tuple[str | None, str | None], claim: dict[str, Any], rules: "Rules"
) -> tuple[tuple[int, int, int], str] | None:
    """Score a tenure against one P39 statement, or reject it outright.

    Every endpoint both sides carry has to agree; one that disagrees ends the
    comparison rather than letting the other endpoint carry the pair, which is
    the defect that let a one-year committee post inherit a four-year seat.
    Returns a tightness key to order competing pairs by and the name of the
    evidence the pair rests on.

    `rules.tolerance` widens the second endpoint to that many years, which is
    the measured shape of the disagreement: an article dates a tenure by the
    day the holder left and Wikidata by the day the successor arrived. It is
    off by default -- see the ablation in `peploop/positions.md`.
    """
    agreed: list[tuple[str, int]] = []
    slack = 0
    for prop, value in zip(("start", "end"), dates):
        other = claim[prop]
        if value is None or other is None:
            continue
        if not agrees(value, other):
            if not rules.both_endpoints:
                continue
            if rules.tolerance is None or not near(value, other, rules.tolerance):
                return None
            slack += 1
            continue
        agreed.append((prop, PRECISION_RANK.get(min(len(value), len(other)), 0)))
    if not agreed:
        return None
    evidence = "both-endpoints" if len(agreed) == 2 else agreed[0][0]
    return (len(agreed), sum(rank for _, rank in agreed), -slack), evidence


def near(left: str, right: str, years: int) -> bool:
    """Report whether two ISO dates fall within `years` of each other."""
    try:
        return abs(int(left[:4]) - int(right[:4])) <= years
    except ValueError:
        return False


def tenures(titles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group one person's titles into tenures, flagging the ambiguous ones.

    The group key is the tenure's shape — start, end, whether it was acting —
    and the language of the article a title came from is the disambiguator. A
    language seen twice in one group means two offices that share dates, not
    one office named twice, so the group can never be awarded an answer.
    """
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for title in titles:
        grouped[(title.get("start"), title.get("end"), bool(title.get("acting")))].append(title)
    out = []
    for index, (key, members) in enumerate(sorted(grouped.items(), key=lambda kv: str(kv[0]))):
        langs = Counter(member.get("lang") for member in members)
        collision = [lang for lang, count in langs.items() if count > 1]
        out.append(
            {
                "id": index,
                "dates": (key[0], key[1]),
                "titles": members,
                "collision": sorted(lang for lang in collision if lang is not None) or None,
            }
        )
    return out


def resolve(groups: list[dict[str, Any]], claims: list[dict[str, Any]],
            rules: "Rules") -> None:
    """Award each tenure at most one P39 statement, and each statement one tenure.

    Written onto the group as `award` (a claim index) and `reason` (why not).
    A group a language collision already condemned still *competes*: its dates
    are real evidence that the statement belongs to one of its offices, so
    letting a weaker neighbour take the statement instead would be worse than
    awarding it to nobody.
    """
    for group in groups:
        scored = []
        for index, claim in enumerate(claims):
            match = endpoint_match(group["dates"], claim, rules)
            if match is not None:
                scored.append((match[0], match[1], index))
        group["award"], group["evidence"], group["reason"] = None, None, None
        if not scored:
            group["reason"] = "no P39 agrees with the tenure's dates"
            continue
        best = max(key for key, _, _ in scored)
        picks = [item for item in scored if item[0] == best]
        if len(picks) > 1 and not rules.one_to_one:
            qids = {claims[index]["qid"] for _, _, index in picks}
            if len(qids) == 1:
                picks = picks[:1]
        if len(picks) > 1:
            qids = sorted({claims[index]["qid"] for _, _, index in picks})
            group["reason"] = f"{len(picks)} P39 statements agree equally well ({', '.join(qids)})"
            continue
        group["tightness"], group["evidence"], group["award"] = picks[0]

    if not rules.one_to_one:
        for group in groups:
            if group["collision"] and rules.language_collision:
                group["award"], group["evidence"] = None, None
                group["reason"] = COLLISION
        return

    contested: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for group in groups:
        if group["award"] is not None:
            contested[group["award"]].append(group)
    for index, rivals in contested.items():
        if len(rivals) == 1:
            continue
        best = max(group["tightness"] for group in rivals)
        winners = [group for group in rivals if group["tightness"] == best]
        for group in rivals:
            if len(winners) == 1 and group is winners[0]:
                continue
            group["award"], group["evidence"] = None, None
            group["reason"] = (
                f"{len(rivals)} tenures claim {claims[index]['qid']} equally well"
                if len(winners) > 1
                else f"a tighter tenure claims {claims[index]['qid']}"
            )

    for group in groups:
        if group["collision"] and group["award"] is not None and rules.language_collision:
            group["award"], group["evidence"] = None, None
            group["reason"] = (
                f"the date group names {'/'.join(group['collision'])} twice,"
                " so it holds more than one office"
            )


def vocabularies() -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """Every token of every position, and the subset of them that discriminates.

    Two bags per item: everything its own names and its indexed document say,
    and the same minus the tokens that most position documents carry anyway —
    the state, the country adjective, the class words. The second is the
    honest reading of "the title and its answer talk about the same office".
    """
    bags: dict[str, set[str]] = defaultdict(set)
    for qid, text in conn().execute("SELECT qid, text FROM position_name"):
        bags[qid] |= positions.tokens(text)
    for qid, text in conn().execute("SELECT qid, search_text FROM position"):
        bags[qid] |= set((text or "").split())
    total = len(bags) or 1
    frequency = Counter(token for bag in bags.values() for token in bag)
    common = {token for token, count in frequency.items() if count > COMMON_SHARE * total}
    strict = {qid: bag - common for qid, bag in bags.items()}
    return dict(bags), strict


def generalise(reason: str | None) -> str | None:
    """Strip the item ids and counts out of a reason, so reasons tally."""
    if reason is None:
        return None
    return re.sub(r"\bQ\d+\b", "an item", re.sub(r"\b\d+\b", "N", reason))


def rows(rules: "Rules") -> list[dict[str, Any]]:
    """Join every extracted title of the latest extraction per person to P39."""
    records = conn().execute(
        "SELECT DISTINCT ON (e.qid) e.qid, e.response_json -> 'positions', i.json"
        " FROM extraction e LEFT JOIN item i ON i.qid = e.qid"
        " ORDER BY e.qid, e.id DESC"
    ).fetchall()
    bags, strict = vocabularies()
    out = []
    for qid, extracted, entity in records:
        claims = p39_claims(entity)
        groups = tenures(list(extracted or []))
        resolve(groups, claims, rules)
        for group in groups:
            gold = None if group["award"] is None else claims[group["award"]]["qid"]
            for title in group["titles"]:
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
                        "gold_qid": gold,
                        "tenure_id": group["id"],
                        "evidence": group["evidence"],
                        "vocab_overlap": None if gold is None
                        else bool(positions.tokens(title.get("title") or "") & bags.get(gold, set())),
                        "vocab_distinctive": None if gold is None
                        else bool(positions.tokens(title.get("title") or "") & strict.get(gold, set())),
                        "reason": group["reason"],
                    }
                )
    return sorted(out, key=lambda r: (r["person_qid"], r["title"] or "", r["start"] or ""))


def diagnostics(fixture: list[dict[str, Any]], bags: dict[str, set[str]],
                strict: dict[str, set[str]]) -> tuple[int, int, int]:
    """Count gold rows and how many of them share vocabulary with their answer."""
    gold = [r for r in fixture if r["gold_qid"]]
    loose = sum(
        1 for r in gold
        if positions.tokens(r["title"] or "") & bags.get(r["gold_qid"], set())
    )
    tight = sum(
        1 for r in gold
        if positions.tokens(r["title"] or "") & strict.get(r["gold_qid"], set())
    )
    return len(gold), loose, tight


def report(name: str, fixture: list[dict[str, Any]], bags, strict) -> None:
    """Print one fixture's composition and its vocabulary-agreement share."""
    total, loose, tight = diagnostics(fixture, bags, strict)
    gold_rows = [r for r in fixture if r["gold_qid"]]
    tenure_keys = {(r["person_qid"], r.get("tenure_id")) for r in gold_rows}
    print(f"{name}:")
    print(f"  people:           {len({r['person_qid'] for r in fixture})}")
    print(f"  titles:           {len(fixture)}")
    print(f"  gold pair:        {total}")
    print(f"  gold tenures:     {len(tenure_keys)}")
    print(f"  weak label only:  {len([r for r in fixture if not r['gold_qid'] and r['p39']])}")
    print(f"  no label:         {len([r for r in fixture if not r['gold_qid'] and not r['p39']])}")
    if total:
        print(f"  vocab_overlap:    {loose} of {total} ({loose / total:.1%})")
        print(f"  distinctive:      {tight} of {total} ({tight / total:.1%})")


def newly_lost(old: Iterable[dict[str, Any]], new: list[dict[str, Any]], count: int) -> None:
    """Print pairs the old rules awarded and the new ones refused, for a human.

    The one hand-check the method asks for: nothing else in this file is read
    by a person, so a change of rule that silently drops the right answers
    would look exactly like a change of rule that drops the wrong ones.
    """
    keyed = {(r["person_qid"], r["title"], r["start"], r["end"]): r for r in new}
    lost = []
    for row in old:
        key = (row["person_qid"], row["title"], row["start"], row["end"])
        fresh = keyed.get(key)
        if row.get("gold_qid") and fresh is not None and not fresh.get("gold_qid"):
            lost.append((row, fresh))
    print(f"\n{len(lost)} pairs the old rules awarded and the new rules refuse."
          f" The first {min(count, len(lost))}, for a hand-check:")
    for row, fresh in lost[:count]:
        span = f"{row['start'] or '?'}..{row['end'] or '?'}"
        print(f"  {row['person_qid']:<11} {span:<23} {row['gold_qid']:<11} {row['title']}")
        print(f"              {fresh['reason']}")


def flagged(fixture: list[dict[str, Any]], count: int) -> None:
    """Print the tenures the rules refused to award for an ambiguity.

    Not the ones no statement matched at all -- those are the bulk and say
    nothing -- but the ones two answers competed for. This is the list the
    method asks a human to eyeball, because a rule that drops the right
    answers looks from the inside exactly like one that drops the wrong ones.
    """
    rows = [
        r for r in fixture
        if r["reason"] and not r["reason"].startswith("no P39")
    ]
    print(f"\n{len(rows)} rows sit in a tenure the rules flagged ambiguous."
          f" The first {min(count, len(rows))}, for a hand-check:")
    for row in rows[:count]:
        span = f"{row['start'] or '?'}..{row['end'] or '?'}"
        print(f"  {row['person_qid']:<11} {span:<23} {row['title']}")
        print(f"              {row['reason']}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compare", type=Path,
                        help="An earlier fixture to diff the awards against.")
    parser.add_argument("--show", type=int, default=40,
                        help="How many newly refused pairs to print.")
    parser.add_argument("--no-collision", action="store_true",
                        help="Ablate rule 1: let a repeated language be awarded.")
    parser.add_argument("--both-endpoints", action="store_true",
                        help="Rule 2, measured harmful: demand both dates agree.")
    parser.add_argument("--one-to-one", action="store_true",
                        help="Rule 3, measured harmful: one statement, one tenure.")
    parser.add_argument("--tolerance", type=int,
                        help="Years of slack on a disagreeing endpoint.")
    parser.add_argument("--dry", action="store_true",
                        help="Measure without overwriting the fixture.")
    args = parser.parse_args()

    rules = Rules(
        language_collision=not args.no_collision,
        both_endpoints=args.both_endpoints,
        one_to_one=args.one_to_one,
        tolerance=args.tolerance,
    )
    fixture = rows(rules)
    if not args.dry:
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with OUT_PATH.open("w", encoding="utf-8") as fh:
            for row in fixture:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    bags, strict = vocabularies()
    if args.compare:
        old = [json.loads(line) for line in args.compare.read_text().splitlines()]
        report(f"{args.compare.name} (superseded)", old, bags, strict)
        print()
    report(OUT_PATH.name, fixture, bags, strict)
    print(f"  rules:            {rules}")
    print(f"  written:          {'nothing (--dry)' if args.dry else OUT_PATH}")

    print("\ntop gold QIDs:")
    for qid, count in Counter(r["gold_qid"] for r in fixture if r["gold_qid"]).most_common(10):
        print(f"  {qid:>12}  {count}")
    print("\nevidence behind a gold pair:")
    for evidence, count in Counter(r["evidence"] for r in fixture if r["gold_qid"]).most_common():
        print(f"  {evidence:>14}  {count}")
    print("\nwhy a tenure was awarded nothing (rows):")
    for reason, count in Counter(
        generalise(r["reason"]) for r in fixture if not r["gold_qid"] and r["p39"]
    ).most_common(8):
        print(f"  {count:>5}  {reason}")

    flagged(fixture, args.show)
    if args.compare:
        newly_lost(old, fixture, args.show)


if __name__ == "__main__":
    main()
