#!/usr/bin/env python
"""Give Iraq's position items the `P31` that makes them findable.

    python scripts/iq_item_types.py            # writes data/iraq/item_types.qs

A byproduct of the Iraq sweep, and the reason it is worth a batch of its own:
**an office with no `P31 = Q4164871` is invisible to every census built on
type**, including the OpenSanctions PEP build this workbench feeds. The sweep
found 35 such items among its own targets — real Iraqi ministries with holders,
labels and `P17 = Q796`, which no "list the positions of Iraq" query returns.

Two shapes, both additive, neither contentious:

* **Items carrying no `P31` at all.** All but one already state `P279` (the role
  they specialise) and `P17 = Q796`, so nothing about their identity is in doubt
  — `Q56043357` "Minister of Awqaf" has ten holders and a country and simply
  never got typed.
* **Items whose only type sits outside the position closure.** `Q889817`
  President of Iraq is typed `Q248577` "President of the Republic", which is
  *not* a subclass of `Q4164871` — so the head of state of the country is
  missing from every "positions of Iraq" query, which is where this whole sweep
  started.

What it deliberately does **not** touch is the larger group whose type merely
differs: `Q83307` "minister", `Q294414` "public office" and `Q17279032`
"elective office" are all subclasses of `Q4164871`, so ten Iraqi ministries typed
`Q83307` are already reachable through `P31/P279*` and need nothing. Adding a
second type to them would be ten edits that change no query's answer. The test is
therefore **reachability through the subclass closure, measured live**, not
whether the literal value is present — the same distinction that makes `wdt:`
unsafe for this question in the first place.

Measured rather than assumed: 29 of the campaign's own target items already carry
`Q4164871`, so this follows Iraq's convention instead of importing one. No
references — a type inferred from an item's own `P279` and label is a structural
inference, and community practice leaves those unsourced.
"""

import argparse
import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wd.api import best_label, fetch_entities, sparql
from wd.campaign import STATE_MAX_AGE
from wd.http import REPO_ROOT, make_session

OUT_DIR = REPO_ROOT / "data" / "iraq"
#: The type every position item should carry.
POSITION = "Q4164871"


def under_position(session, classes):
    """Which of these classes already sit under `Q4164871`, asked of Wikidata.

    The question is never "does the item say `Q4164871`" but "does anything it
    says lead there" — `Q83307` "minister" and `Q294414` "public office" both do,
    so an item typed either is already found by every census that matters and
    wants no edit. `Q248577` "President of the Republic" does not, which is why
    the head of state of Iraq was missing from the survey that began this run.
    """
    values = " ".join(f"wd:{qid}" for qid in sorted(classes) if qid)
    if not values:
        return set()
    rows = sparql(session, f"""
        SELECT ?c WHERE {{ VALUES ?c {{ {values} }}
                           ?c wdt:P279* wd:{POSITION} }}
    """, max_age=STATE_MAX_AGE)
    return {row["c"] for row in rows}


def campaign_targets():
    """Every item the Iraq campaign routes a statement to."""
    spec = importlib.util.spec_from_file_location(
        "iq_offices", Path(__file__).resolve().parent / "iq_offices.py"
    )
    module = importlib.util.module_from_spec(spec)
    argv, sys.argv = sys.argv, ["iq_offices"]
    try:
        spec.loader.exec_module(module)
    finally:
        sys.argv = argv
    qids = {q for _, q in module.PORTFOLIOS if q}
    for office in module.OFFICES:
        if office.target:
            qids.add(office.target)
        qids |= {q for _, q in office.section_targets if q}
        qids |= {q for *_, q in office.date_targets if q}
    return sorted(qids)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retrieved", default=None, help="unused; kept for symmetry")
    # Called for its side effects — `--help` and rejecting unknown flags — and
    # not assigned, because nothing here reads an argument.
    parser.parse_args()

    session = make_session()
    targets = campaign_targets()
    entities = fetch_entities(session, targets, max_age=STATE_MAX_AGE)
    print(f"{len(targets)} target items; {len(entities)} fetched")

    typed = {
        qid: [
            (snak["mainsnak"].get("datavalue", {}).get("value") or {}).get("id")
            for snak in (entities.get(qid) or {}).get("claims", {}).get("P31", [])
        ]
        for qid in targets if qid in entities
    }
    reachable = under_position(session, {t for ts in typed.values() for t in ts})

    lines, report, already = [], [], 0
    for qid, types in sorted(typed.items()):
        entity = entities[qid]
        if any(t in reachable for t in types):
            already += 1
            continue
        # Everything left is either untyped or typed outside the closure. The
        # second case has to be looked at rather than assumed: a *body* typed
        # `Q192350` would land here too, and typing it a position would write the
        # very defect `iq_removals.py` cleans. `Q61958669` is how that happens.
        why = ("no P31 at all" if not types
               else f"P31 = {', '.join(types)}, none of them under {POSITION}")
        if types:
            print(f"  · {qid} {best_label(entity)!r}: {why}")
        lines.append(f"{qid}\tP31\t{POSITION}")
        report.append((qid, best_label(entity) or qid, why))
    print(f"\n{already} targets already reach {POSITION} through their own types "
          "and are left alone")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "item_types.qs").write_text("\n".join(lines) + "\n")
    (OUT_DIR / "item_types.md").write_text("\n".join(
        [f"# Iraq — position items missing `P31 = {POSITION}`", "",
         f"{len(lines)} items. Additive, unreferenced (a type inferred from the "
         "item's own `P279` and label is a structural inference).", "",
         "| item | label | why |", "|---|---|---|"]
        + [f"| {q} | {label} | {why} |" for q, label, why in report]
    ) + "\n")
    print(f"\n{len(lines)} items need P31 = {POSITION}")
    print(f"Wrote {OUT_DIR / 'item_types.qs'} and item_types.md")


if __name__ == "__main__":
    main()
