#!/usr/bin/env python
"""Find the Iraqi `P39` statements whose *value is not a position*, and say why.

    python scripts/iq_removals.py                 # classes 1 and 2
    python scripts/iq_removals.py --generics      # …and the class-3 proposal

Writes `data/iraq/removals.md` (the account a human reads) and
`data/iraq/removals.json` (statement GUIDs plus the reason each was chosen, which
`scripts/apply_removals.py` consumes). Nothing is written to Wikidata here.

Iraq's item layer holds three distinct kinds of wrong `P39`, and lumping them
together is the mistake this script exists to avoid — two are defects and the
third is a disagreement.

* **Class 1 — a `Category:` item as a position.** `Q25167655`
  "Category:Governors of the Central Bank of Iraq" carries `P31 = Q4167836` and
  is held by ten people. A category is not an office anyone can hold. It also
  does active harm: several of those statements are open-ended, and
  `campaign.interim_of` read their spans as a concurrent office and stamped three
  genuine central-bank appointments `P2868 = acting` until the item was named in
  `concurrency_ignore`.

* **Class 2 — a *body* as a position.** `Q1973075` is the Council of
  Representatives itself (`P31 = Q37002670`, a legislature); `Q6867009` is the
  Ministry of Foreign Affairs. Holding an organisation is not holding an office —
  the membership and the ministership both have their own items, and the people
  concerned are on the rosters that fill them.

* **Class 3 — a generic role item used for a national office. NOT a removal.**
  Iraq's entire 1921–58 justice bench sits on `Q17763739` "justice minister", a
  cross-country role item with 405 holders and no `P17`; there are 107 such
  statements among the justice roster's own people against 8 on Iraq's
  `Q106964104`. That is how much of Wikidata models ministers, often with
  qualifiers that carry the country, and removing ~150 of them would take a side
  the community has not. So `--generics` emits them as a **replacement proposal**
  with the specific item named, and never as a removal; meanwhile
  `Campaign.generic_targets` stops the sweep proposing redundantly beside them.

Ordering is load-bearing, and it is the reason this script only ever *proposes*:
the additive batch goes in first, so the statement that replaces a wrong one
already exists before anything is taken away. Otherwise a removal leaves a real
officeholder with no `P39` at all.
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wd.api import best_label, fetch_entities, sparql
from wd.campaign import STATE_MAX_AGE
from wd.http import REPO_ROOT, make_session

OUT_DIR = REPO_ROOT / "data" / "iraq"

#: `P31` values that make an item structurally incapable of being held.
#: Wikimedia categories, list articles and templates are class 1; anything whose
#: type is an organisation or a body is class 2. Kept as an explicit map rather
#: than a subclass walk because `wdt:P31` misclassifies — a preferred value hides
#: the others and a deprecated one vanishes — so the census below reads
#: `p:P31/ps:P31` and matches against these directly.
#: An item claiming this anywhere in its `P31` says it is a position, whatever
#: else it also claims — and that is enough to leave its statements alone.
POSITION_TYPE = "Q4164871"
#: A label that names an *officeholder* rather than the body they run. Used only
#: to demote a class-2 finding to an item repair, never to promote anything.
OFFICE_LABEL = re.compile(
    r"^\s*(?:minister|governor|president|prime minister|speaker|chief|head|"
    r"secretary|director|chair|وزير|محافظ|رئيس|أمين)\b", re.I
)

CATEGORY_TYPES = {
    "Q4167836": "a Wikimedia category",
    "Q13406463": "a Wikimedia list article",
    "Q11266439": "a Wikimedia template",
    "Q4167410": "a Wikimedia disambiguation page",
}
BODY_TYPES = {
    "Q37002670": "a legislature",
    "Q192350": "a ministry",
    "Q327333": "a government agency",
    "Q43229": "an organisation",
    "Q2659904": "a government organisation",
    "Q7188": "a government",
    "Q640506": "a cabinet",
    "Q66712772": "a governor's office",
}

#: What holds the office instead, and why this is the right substitute. Only
#: filled in where the sweep's own rosters put the same people on the same
#: office, which is what makes the removal safe rather than merely tidy.
REPLACEMENTS = {
    "Q25167655": ("Q110490288",
                  "the real Governor of the Central Bank of Iraq item, which "
                  "this run's central-bank roster fills with 15 statements"),
    "Q1973075": ("Q21328603",
                 "member of the Council of Representatives of Iraq — the "
                 "membership item, whose P361 is this very body"),
    "Q6867009": ("Q6895071",
                 "Minister of Foreign Affairs — the office, not the ministry"),
    "Q61958669": ("Q56650429",
                  "Minister of Municipalities and Public Works; the era item is "
                  "a judgement, so this one is flagged rather than asserted"),
}


def iraqi_p39_values(session) -> Dict[str, int]:
    """Every `P39` value used by a person with Iraqi citizenship, with a count.

    Deliberately holder-first rather than item-first: an item that is not a
    position cannot be found by asking for positions, which is the whole point.
    """
    query = """
    SELECT ?value (COUNT(DISTINCT ?person) AS ?holders) WHERE {
      { SELECT DISTINCT ?value ?person WHERE {
          ?person wdt:P27 wd:Q796 ; p:P39/ps:P39 ?value } }
    } GROUP BY ?value ORDER BY DESC(?holders)
    """
    # `sparql` already flattens each binding to plain strings and shortens an
    # entity URI to its bare QID, so there is nothing left to unwrap here.
    return {
        row["value"]: int(row["holders"])
        for row in sparql(session, query, max_age=STATE_MAX_AGE)
    }


def classify(session, qids: List[str]) -> Dict[str, dict]:
    """Each candidate's label and what its own `P31` values make it."""
    out: Dict[str, dict] = {}
    for chunk in (qids[i:i + 40] for i in range(0, len(qids), 40)):
        entities = fetch_entities(session, chunk, max_age=STATE_MAX_AGE)
        for qid, entity in entities.items():
            types = [
                snak["mainsnak"]["datavalue"]["value"]["id"]
                for snak in entity.get("claims", {}).get("P31", [])
                if snak["mainsnak"].get("datavalue")
            ]
            label = best_label(entity) or qid
            kind, reason = None, None
            for value in types:
                if value in CATEGORY_TYPES:
                    kind, reason = 1, CATEGORY_TYPES[value]
                    break
                if value in BODY_TYPES:
                    kind, reason = 2, BODY_TYPES[value]
                    break
            # Two ways an item that *is* an office looks like one that is not,
            # both of which produced a false positive on the first run and would
            # have removed valid statements.
            #
            # It carries a position type as well. `Q89036894` "Governor of Najaf"
            # is `Q4164871` *and* `Q66712772` "governor's office" — the office
            # conflated with its bureau. A second, wrong type does not stop the
            # first one being true, so any item that claims to be a position
            # anywhere among its values is left alone; §2's `wdt:` warning in
            # another guise.
            if POSITION_TYPE in types:
                kind, reason = None, None
            # Or its *label* names an office while its type names the body.
            # `Q37827445` "Minister of Youth and Sports (Iraq)" is typed
            # `Q192350`, a ministry, and held by three people who really were
            # the minister. The defect is the `P31`, not the three statements,
            # so this is an item repair for `tasks/followups.md` and never a
            # removal — taking the statements off would destroy good data to
            # tidy a bad type.
            elif kind == 2 and OFFICE_LABEL.match(label):
                kind, reason = None, f"MISTYPED: labelled an office, typed {reason}"
            out[qid] = {
                "label": label,
                "types": types,
                "class": kind,
                "reason": reason,
            }
    return out


def statements(session, value_qid: str) -> List[dict]:
    """The `P39` statements pointing at `value_qid`, with their GUIDs.

    The GUID is the only handle `wb remove-claim` accepts, and it can only come
    from the live entity — read with `STATE_MAX_AGE`, never the seven-day cache,
    because this is a question about Wikidata's current state.
    """
    query = """
    SELECT ?person WHERE { ?person p:P39/ps:P39 wd:%s }
    """ % value_qid
    people = [
        row["person"] for row in sparql(session, query, max_age=STATE_MAX_AGE)
    ]
    found: List[dict] = []
    for chunk in (people[i:i + 40] for i in range(0, len(people), 40)):
        entities = fetch_entities(session, chunk, max_age=STATE_MAX_AGE)
        for qid, entity in entities.items():
            for claim in entity.get("claims", {}).get("P39", []):
                snak = claim.get("mainsnak", {})
                datavalue = snak.get("datavalue") or {}
                if (datavalue.get("value") or {}).get("id") != value_qid:
                    continue
                found.append({
                    "person": qid,
                    "person_label": best_label(entity) or qid,
                    "guid": claim["id"],
                    "rank": claim.get("rank"),
                    "qualifiers": sorted(claim.get("qualifiers", {})),
                })
    return found


def render(rows: List[dict], generics: List[dict], path: Path) -> None:
    lines = [
        "# Iraq — `P39` statements whose value is not a position",
        "",
        "Generated by `scripts/iq_removals.py`. **Read this before running "
        "`scripts/apply_removals.py`, and run the additive batch first** — a "
        "removal that lands before its replacement leaves a real officeholder "
        "with no `P39` at all.",
        "",
        f"{len(rows)} statements proposed for removal.",
        "",
    ]
    by_value: Dict[str, List[dict]] = {}
    for row in rows:
        by_value.setdefault(row["value"], []).append(row)
    for value, group in sorted(by_value.items(), key=lambda kv: -len(kv[1])):
        first = group[0]
        lines += [
            f"## {value} — {first['value_label']}",
            "",
            f"* **Class {first['class']}**: the value is {first['reason']}, "
            "which nobody can hold.",
            f"* `P31` values: {', '.join(first['types']) or '(none)'}",
        ]
        if first.get("replacement"):
            lines.append(f"* **Replaced by** {first['replacement']} — "
                         f"{first['replacement_why']}")
        else:
            lines.append("* **No replacement identified** — do not remove until "
                         "one is, or the holder is left with nothing.")
        lines += ["", "| person | label | statement GUID | rank | qualifiers |",
                  "|---|---|---|---|---|"]
        for row in group:
            quals = ", ".join(row["qualifiers"]) or "—"
            lines.append(f"| {row['person']} | {row['person_label']} | "
                         f"`{row['guid']}` | {row['rank']} | {quals} |")
        lines.append("")
    if generics:
        lines += [
            "## Class 3 — a proposal, not a removal",
            "",
            "These are generic cross-country role items standing in for an Iraqi "
            "office. They are used this way across Wikidata, often with "
            "qualifiers carrying the country, so **nothing here is removed**: "
            "the specific statement is added by the sweep and these are listed "
            "so a human can decide separately whether the generic should also "
            "come off.",
            "",
            "| generic | label | Iraqi holders | the specific item instead |",
            "|---|---|---|---|",
        ]
        for row in generics:
            lines.append(f"| {row['value']} | {row['value_label']} | "
                         f"{row['holders']} | {row.get('replacement') or '—'} |")
        lines.append("")
    path.write_text("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generics", action="store_true",
                        help="Also report the class-3 replacement proposal")
    args = parser.parse_args()

    session = make_session()
    counts = iraqi_p39_values(session)
    print(f"{len(counts)} distinct P39 values held by people with P27 = Q796")
    facts = classify(session, list(counts))

    rows: List[dict] = []
    for qid, fact in sorted(facts.items()):
        if fact["class"] is None:
            continue
        replacement, why = REPLACEMENTS.get(qid, (None, None))
        for statement in statements(session, qid):
            rows.append({
                **statement,
                "value": qid,
                "value_label": fact["label"],
                "class": fact["class"],
                "reason": fact["reason"],
                "types": fact["types"],
                "replacement": replacement,
                "replacement_why": why,
            })
        print(f"  class {fact['class']}: {qid} {fact['label']!r} — "
              f"{counts[qid]} holders, {fact['reason']}")

    generics: List[dict] = []
    if args.generics:
        from iq_offices import CAMPAIGN
        for qid in CAMPAIGN.generic_targets:
            fact = facts.get(qid)
            if not fact:
                continue
            generics.append({
                "value": qid,
                "value_label": fact["label"],
                "holders": counts.get(qid, 0),
                "replacement": None,
            })

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "removals.json").write_text(
        json.dumps({"removals": rows, "proposals": generics},
                   ensure_ascii=False, indent=2) + "\n"
    )
    render(rows, generics, OUT_DIR / "removals.md")
    print(f"\n{len(rows)} statements proposed for removal"
          f"{f', {len(generics)} generics reported' if generics else ''}")
    print(f"Wrote {OUT_DIR / 'removals.md'} and removals.json")


if __name__ == "__main__":
    main()
