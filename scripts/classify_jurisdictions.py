#!/usr/bin/env python
"""Judge which polity a country-less position item belongs to.

    python scripts/classify_jurisdictions.py --candidates data/jurisdictions/db_candidates.json

The mechanical channels get a candidate this far and no further: the holders'
citizenships and the label both say "Egypt", and neither can tell an Egyptian
ministry from a list of Egyptian ministers, or an office of the state from a
profession its holders happen to share. That judgement is this pass, and its
instructions are `prompts/jurisdiction_classifier.md` — read them before
reading this file, because the prompt is the substance and this is the plumbing.

Verdicts land in one JSONL that `render_citizenship_plan.py` consumes, and the
run is resumable against it: re-running after widening the candidate set costs
only the new items. Nothing here writes to Wikidata.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wd.http import REPO_ROOT
from wd.verdicts import EFFORT, MODEL, Ledger, classify

BASE = REPO_ROOT / "data" / "jurisdictions"
PROMPT = REPO_ROOT / "prompts" / "jurisdiction_classifier.md"

#: Mirrors the schema documented in the prompt. The API enforces it, so a
#: renderer never sees a missing field or a kind nobody defined — but the two
#: must be changed together, or the model is asked for one shape and held to
#: another.
KINDS = [
    "national-executive", "legislative", "judicial", "military", "central-bank",
    "subnational", "municipal", "party", "religious", "diplomatic",
    "state-owned-enterprise", "generic-occupation", "academy-or-award",
    "list-or-class", "other",
]

#: `anyOf` rather than a nullable type: structured outputs accept the union
#: form, and every field must be `required` for the schema to compile at all —
#: absence is expressed as null, not omission.
NULLABLE_STRING = {"anyOf": [{"type": "string"}, {"type": "null"}]}

VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "qid": {"type": "string"},
        "label": {"type": "string"},
        "verdict": {"type": "string",
                    "enum": ["fix-current", "fix-historical", "skip", "unclear"]},
        "country_qid": NULLABLE_STRING,
        "country_code": NULLABLE_STRING,
        "prop": {"type": "string", "enum": ["P1001", "P17"]},
        "jurisdiction_qid": NULLABLE_STRING,
        "kind": {"type": "string", "enum": KINDS},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "reason": {"type": "string"},
    },
    "required": ["qid", "label", "verdict", "country_qid", "country_code",
                 "prop", "jurisdiction_qid", "kind", "confidence", "reason"],
    "additionalProperties": False,
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path,
                        default=BASE / "db_candidates.json",
                        help="citizenship_candidates.py output to judge")
    parser.add_argument("--out", type=Path, default=BASE / "verdicts" / "db.jsonl",
                        help="verdict ledger; existing rows are skipped")
    parser.add_argument("--prompt", type=Path, default=PROMPT)
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--effort", default=EFFORT,
                        choices=["low", "medium", "high", "xhigh", "max"])
    parser.add_argument("--batch-size", type=int, default=10,
                        help="items per request; larger batches share the cached "
                             "prompt but also share a context")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--limit", type=int, default=0, help="debug: first N items")
    parser.add_argument("--dry", action="store_true",
                        help="report what would be judged and stop")
    args = parser.parse_args()

    candidates = json.loads(args.candidates.read_text())
    if args.limit:
        candidates = candidates[:args.limit]
    ledger = Ledger(args.out).load()

    if args.dry:
        todo = [c for c in candidates if c["qid"] not in ledger.done]
        print(f"{len(candidates)} candidates, {len(ledger.done)} already judged, "
              f"{len(todo)} to go in "
              f"{(len(todo) + args.batch_size - 1) // args.batch_size} requests")
        for c in todo[:5]:
            prior = (c.get("top") or {}).get("code")
            place = (c.get("label_place") or {}).get("code")
            print(f"  {c['qid']:<12} {c['label']}  [prior {prior}, label {place}]")
        return

    usage = classify(
        candidates,
        prompt=args.prompt.read_text(),
        item_schema=VERDICT_SCHEMA,
        ledger=ledger,
        model=args.model,
        effort=args.effort,
        batch_size=args.batch_size,
        workers=args.workers,
        log=lambda m: print(m, file=sys.stderr, flush=True),
    )
    print(usage.line())

    # The schema constrains every field's *shape* but not the QID's *value*: a
    # model that echoes a subject wrong would route a jurisdiction claim onto
    # the wrong item, and the renderer has no way to know. Check it here, where
    # the candidate set is still in hand.
    rows = [json.loads(l) for l in args.out.read_text().splitlines() if l.strip()]
    judged = [r["qid"] for r in rows]
    known = {c["qid"] for c in candidates}
    stray = sorted(set(judged) - known)
    dupes = sorted({q for q in judged if judged.count(q) > 1})
    if stray or dupes:
        raise SystemExit(
            f"ledger integrity: {len(stray)} verdict(s) for unknown QIDs "
            f"{stray[:5]}, {len(dupes)} duplicated {dupes[:5]} — do not render"
        )
    print(f"Wrote {args.out} ({len(rows)} verdicts, all QIDs accounted for)")


if __name__ == "__main__":
    main()
