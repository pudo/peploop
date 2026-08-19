"""Audit a country's position items for discoverability, and propose the fixes.

Run this at phase A of a sweep, before scoping a roster lane. A P39 statement
written onto an item the OpenSanctions PEP build cannot see produces nothing,
and no holder count reveals which items those are — `recipes/position_items.md`
has the gates and what each one costs.

    python scripts/position_metadata.py --country lt
    python scripts/position_metadata.py --country lt --calibrate

`--calibrate` checks each verdict against a live `yente-cli fetch`, which is the
only regression net this reader has. Read a disagreement as no-holders first, the
review layer second, a port bug third.
"""

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from wd.api import best_label, claim_qids, fetch_entities, sparql  # noqa: E402
from wd.discover import verify_all  # noqa: E402
from wd.http import get_text, make_session  # noqa: E402
from wd.record import (  # noqa: E402
    Decision, Record, Signal, Snak, Statement, Subject, Value, dumps,
)

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
POSITION_CLASS = "Q4164871"

#: Countries this script knows how to scope. Each names the country item and the
#: label fragments that admit an item with no country path at all — which is the
#: ordering problem at the centre of the audit: "has no country" cannot also be
#: the membership test, so the label channel is what lets such an item in.
COUNTRIES: Dict[str, Dict[str, object]] = {
    "lt": {
        "qid": "Q37",
        "name": "Lithuania",
        "campaign": "lithuania",
        # CirrusSearch terms, not regex stems: "lithuan" is not a word and
        # matches nothing, which silently cost this audit the four apex-court
        # presidencies — the highest-value items in it — on the first run.
        "search_terms": ("Lithuania", "Lithuanian", "Lietuvos", "Seimas"),
    },
    # Persian hints as well as English: many Iranian position items carry an
    # `fa` label and no `en` one, and the label channel exists for exactly the
    # items the country channels miss.
    "ir": {
        "qid": "Q794",
        "name": "Iran",
        "campaign": "iran",
        "label_hints": ("iran", "persia", "majlis", "ایران", "استاندار"),
    },
}

#: Decided per office against the measured convention: every parent below is in
#: live use as a `P279` on real position items (counts taken 2026-08-19).
#:
#: Chosen because it *describes the office*, never to trip `wd.discover`'s PEP
#: sentinel. That ordering matters: typing a district judgeship as a supreme
#: court judge would flip the sentinel and corrupt the data to do it. Where the
#: honest parent does not set the default — `Q16533` judge, `Q14212` prime
#: minister — the gap is reported upstream and the parent stays honest.
PARENTS: Dict[str, Tuple[str, str]] = {
    "Q131824331": ("Q117826617", "apex court presidency — supreme court judge"),
    "Q133090275": ("Q117826617", "apex court presidency — supreme court judge"),
    "Q131824524": ("Q117826617", "final-instance court presidency"),
    "Q131807424": ("Q117826617", "constitutional court presidency"),
    "Q132891425": ("Q108290289", "judicial governance body, not a court"),
    "Q133190264": ("Q108290289", "parliamentary leadership"),
    "Q12663218": ("Q108290289", "parliamentary leadership"),
    "Q140916310": ("Q108290289", "agency headship"),
    "Q132068652": ("Q3368517", "public prosecutor general"),
    "Q55607326": ("Q707492", "military chief of staff"),
    "Q5177800": ("Q132050", "governor"),
}

#: Items typed as positions that are not offices at all, or that duplicate one.
#: These never enter a batch: retyping and merging are destructive-adjacent and
#: belong on the wikibase-cli list in `tasks/followups.md`.
SURGICAL: Dict[str, str] = {
    "Q114059276": "occupation ('lithuanist'), not a position — retype",
    "Q101540148": "occupation ('Lithuanian teacher'), not a position — retype",
    "Q258874": "folk-craft occupation ('dievdirbys'), not a position — retype",
    "Q565077": "military rank ('flotilla admiral'), not a position — retype",
    "Q12663357": "a body (P31=Q495430), not a position — retype",
    "Q139379876": "basketball league presidency, not a public office — retype",
    "Q63994897": "no en label, duplicates Grand Duke of Lithuania — merge",
    "Q132476998": "duplicates Q12661306 Minister of National Defence — merge",
    "Q132861229": "duplicates Q107735740 Minister of Transport — merge",
}


def candidates(session, country: Dict[str, object]) -> Dict[str, str]:
    """Position items the country owns, by qid -> label.

    Three channels, because the audit's own membership test cannot be "resolves
    to this country": that is the defect it looks for. `P17`/`P1001` find the
    well-formed ones and a text search finds the rest — an item with no country
    claim at all is reachable only by what its label says.
    """
    qid = country["qid"]
    found: Dict[str, str] = {}
    queries = [
        f"SELECT ?p WHERE {{ ?p wdt:P17 wd:{qid} ; wdt:P31/wdt:P279* wd:Q4164871 }}",
        f"SELECT ?p WHERE {{ ?p wdt:P1001 wd:{qid} ; wdt:P31/wdt:P279* wd:Q4164871 }}",
    ]
    for query in queries:
        for row in sparql(session, query, max_age=0):
            found.setdefault(row["p"], "")
    for term in country["search_terms"]:  # type: ignore[union-attr]
        for item in _search_labels(session, str(term)):
            found.setdefault(item, "")
    entities = fetch_entities(session, sorted(found), max_age=0)
    return {q: (best_label(entities.get(q, {})) or "") for q in sorted(found)}


def _search_labels(session, term: str) -> List[str]:
    """Position items whose text mentions `term`, via CirrusSearch.

    The label channel cannot be a SPARQL scan: `FILTER(CONTAINS(LCASE(?l), …))`
    over every position on Wikidata answers with a 504, and this channel exists
    precisely to admit items with no country path, so it cannot be narrowed by
    country either. CirrusSearch answers the same question in one request.

    Only reaches items carrying `P31 = Q4164871` outright, so an item typed
    solely as a subclass (`Q294414` public office) arrives through the country
    channels above instead.
    """
    found: List[str] = []
    offset = 0
    while True:
        raw = get_text(session, WIKIDATA_API, params={
            "action": "query", "format": "json", "list": "search",
            "srnamespace": "0", "srlimit": "50", "sroffset": str(offset),
            "srsearch": f"haswbstatement:P31={POSITION_CLASS} {term}",
        }, max_age=0)
        payload = json.loads(raw)
        hits = payload.get("query", {}).get("search", [])
        found.extend(hit["title"] for hit in hits)
        offset += len(hits)
        if len(hits) < 50 or offset >= 500:
            break
    return found


def holder_counts(session, qids: List[str]) -> Dict[str, int]:
    """Holders per item, any rank — the gate that is not in `position.py`.

    `wd_peps` reaches a position through people's P39, so an item nobody holds
    is never emitted however well-formed it is. Counted with `p:P39/ps:P39`
    because `wdt:` would report only best-rank holders.
    """
    counts: Dict[str, int] = {q: 0 for q in qids}
    for start in range(0, len(qids), 120):
        chunk = qids[start:start + 120]
        values = " ".join(f"wd:{q}" for q in chunk)
        rows = sparql(session, f"""SELECT ?pos (COUNT(DISTINCT ?h) AS ?n) WHERE {{
          VALUES ?pos {{ {values} }} OPTIONAL {{ ?h p:P39/ps:P39 ?pos }}
        }} GROUP BY ?pos""", max_age=0)
        for row in rows:
            counts[row["pos"]] = int(row["n"])
    return counts


def _item(qid: str) -> Value:
    return Value(type="item", id=qid, iso=None, precision=None, text=None)


def records_for(
    campaign: str, verdict, entity: Dict[str, object], holders: int
) -> Optional[Record]:
    """One record per item: the statements that would make it discoverable.

    Every case gets a disposition, including the ones with nothing to add — an
    item that already passes is recorded as a skip with its evidence, so the
    audit is an account of the country rather than a list of grievances.
    """
    qid = verdict.qid
    label = verdict.label or qid
    subject = Subject(kind="position", qid=qid, ref=None, label=label)
    signals = [
        Signal(channel="gate", supports="yes" if not verdict.failed else "no",
               detail=f"failed={verdict.failed or ['none']}; "
                      f"topics={sorted(verdict.topics - {'role.pep'}) or ['none']}; "
                      f"pep_default={verdict.pep_default}; "
                      f"country={verdict.countries or ['none']}"
                      f" via {verdict.country_via or 'nothing'}",
               source_url=None),
        Signal(channel="holders", supports="yes" if holders else "no",
               detail=f"{holders} holder(s) with a P39 to this item", source_url=None),
    ]
    flags = list(verdict.failed) + ([] if holders else ["no_holders"])

    if qid in SURGICAL:
        return Record(
            campaign=campaign, subject=subject, statements=[],
            decision=Decision(action="defect", rule="item_layer.surgical",
                              source="default", concern="item_layer",
                              rationale=SURGICAL[qid]),
            office="metadata", identity={"method": "qid"}, flags=flags,
            signals=signals, notes="stop-and-ask: never a batch line",
            byproduct={"kind": "surgical", "detail": SURGICAL[qid]},
        )

    statements: List[Statement] = []
    country_qid = "Q37"
    # Only items on the decided list get a country. An office scoped to the Grand
    # Duchy or the Lithuanian SSR resolves to no country *correctly*, and naming
    # the modern republic on one would be a wrong statement in the lane that
    # looks safest — those close `absent` in the ledger instead.
    if qid in PARENTS and "country" in verdict.failed:
        for prop in ("P17", "P1001"):
            if country_qid not in set(claim_qids(entity, prop)):
                statements.append(Statement(
                    property=prop, value=_item(country_qid),
                    qualifiers=[], references=[], existing=False,
                    end_withheld=False))
    parent = PARENTS.get(qid)
    if parent and parent[0] not in set(claim_qids(entity, "P279")):
        statements.append(Statement(
            property="P279", value=_item(parent[0]),
            qualifiers=[], references=[], existing=False, end_withheld=False))

    if not statements:
        rule = "metadata.sufficient" if not verdict.failed else "metadata.no_rule"
        rationale = (
            "already carries a country path and a parent that sets the PEP default"
            if not verdict.failed else
            f"fails {verdict.failed} and no measured correction applies — "
            "see the ledger row"
        )
        return Record(
            campaign=campaign, subject=subject, statements=[],
            decision=Decision(action="skip", rule=rule, source="default",
                              concern="item_layer", rationale=rationale),
            office="metadata", identity={"method": "qid"}, flags=flags,
            signals=signals, notes="", byproduct=None,
        )

    detail = parent[1] if parent else "country backfill"
    return Record(
        campaign=campaign, subject=subject, statements=statements,
        decision=Decision(action="apply", rule="metadata.two_channel",
                          source="default", concern="item_layer",
                          rationale=f"{detail}; parent measured in live use, and "
                                    "the label names the country"),
        office="metadata", identity={"method": "qid"}, flags=flags,
        signals=signals, notes="", byproduct=None,
    )


def calibrate(verdicts, holders: Dict[str, int]) -> None:
    """Check each verdict against the live API, and say which way it disagreed."""
    table: Counter = Counter()
    disagree: List[str] = []
    for verdict in verdicts:
        proc = subprocess.run(["yente-cli", "fetch", verdict.qid, "-f", "json"],
                              capture_output=True, text=True)
        present = False
        if proc.returncode == 0 and proc.stdout.strip():
            try:
                present = json.loads(proc.stdout).get("schema") == "Position"
            except json.JSONDecodeError:
                present = False
        table[(verdict.self_sufficient, present)] += 1
        if verdict.self_sufficient != present:
            why = ("no holders" if not holders.get(verdict.qid) else
                   "review layer, or a port bug")
            disagree.append(
                f"  {verdict.qid:12} self_sufficient={verdict.self_sufficient} "
                f"in_os={present}  ({why})  {verdict.label}")
    print("\n## Calibration")
    print(f"  agree            : {table[(True, True)] + table[(False, False)]}")
    print(f"  passes, absent   : {table[(True, False)]}")
    print(f"  fails, present   : {table[(False, True)]}")
    for line in disagree[:40]:
        print(line)
    if len(disagree) > 40:
        print(f"  … and {len(disagree) - 40} more")


def check_spec() -> int:
    """Fail if the recipe no longer enumerates every gate class the code applies.

    The recipe restates constants that live in `wd/discover.py`, which is the
    kind of duplication that rots quietly — a class added to `zavod` and ported
    here would leave the documented list wrong with nothing to notice it.
    """
    from wd import discover

    recipe = (REPO_ROOT / "recipes" / "position_items.md").read_text()
    sets = {
        "POSITION_BASICS": discover.POSITION_BASICS,
        "EXCLUDE_TYPES": discover.EXCLUDE_TYPES,
        "ALLOW_TYPES (extras)": discover.ALLOW_TYPES - set(discover.SUB_TYPES),
        "HISTORICAL_TYPES": discover.HISTORICAL_TYPES,
        "SKIP_PLACES": discover.SKIP_PLACES,
        "SUB_TYPES": set(discover.SUB_TYPES),
    }
    missing: List[str] = []
    for name, qids in sets.items():
        absent = sorted(q for q in qids if q not in recipe)
        # Only the pep-conferring subtypes need naming individually; the recipe
        # documents the classifying ones exhaustively because those are the traps.
        if name == "SUB_TYPES":
            absent = sorted(
                q for q in absent
                if "role.pep" not in discover.SUB_TYPES[q]
            )
        if absent:
            missing.append(f"  {name}: {absent}")
    for code in (discover.POSITION_ABOLISHED_CUTOFF,):
        if code not in recipe:
            missing.append(f"  POSITION_ABOLISHED_CUTOFF: {code}")
    if missing:
        print("recipes/position_items.md is missing gate classes:")
        print("\n".join(missing))
        return 1
    print("recipes/position_items.md enumerates every gate class and the cutoff.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--country", required=True, choices=sorted(COUNTRIES))
    parser.add_argument("--calibrate", action="store_true",
                        help="check every verdict against a live yente-cli fetch")
    parser.add_argument("--check-spec", action="store_true",
                        help="assert recipes/position_items.md enumerates every gate class")
    args = parser.parse_args()

    if args.check_spec:
        raise SystemExit(check_spec())

    country = COUNTRIES[args.country]
    campaign = str(country["campaign"])
    session = make_session()
    labels = candidates(session, country)
    print(f"## {country['name']}: {len(labels)} position items")

    verdicts = verify_all(session, sorted(labels), labels=labels)
    holders = holder_counts(session, sorted(labels))
    entities = fetch_entities(session, sorted(labels), max_age=0)

    records = [
        record for record in (
            records_for(campaign, verdict, entities.get(verdict.qid, {}),
                        holders.get(verdict.qid, 0))
            for verdict in verdicts
        ) if record is not None
    ]

    out_dir = REPO_ROOT / "data" / campaign / "verdicts"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{campaign}_metadata.jsonl").write_text(dumps(records))

    gates = Counter(f for v in verdicts for f in v.failed)
    actions = Counter(r.decision.action for r in records)
    print(f"  self-sufficient : {sum(1 for v in verdicts if v.self_sufficient)}")
    print(f"  no holders      : {sum(1 for q in labels if not holders.get(q))}")
    print("  gate failures   : " + ", ".join(f"{k}={n}" for k, n in gates.most_common()))
    print("  dispositions    : " + ", ".join(f"{k}={n}" for k, n in actions.most_common()))
    print(f"  wrote {out_dir / f'{campaign}_metadata.jsonl'}")

    # A decided item that the candidate set never reached would vanish without
    # a trace, which is the one thing an audit may not do.
    reached = {v.qid for v in verdicts}
    for name, decided in (("PARENTS", set(PARENTS)), ("SURGICAL", set(SURGICAL))):
        unreached = sorted(decided - reached)
        if unreached:
            print(f"  !! {name} not reached by any channel: {unreached}")

    if args.calibrate:
        calibrate(verdicts, holders)


if __name__ == "__main__":
    main()
