"""Audit how a country's position items are modelled, and propose the fixes.

Run this at phase A of a sweep, before scoping a roster lane. It reports Wikidata
modelling defects — an occupation typed as an office, an office scoped to no
polity, an office that says "position" and never says what kind — each worth
fixing on its own terms. `recipes/position_items.md` is the method.

Whether a downstream reader currently emits an item is reported separately as
notes, never as a defect.

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
from wd.shape import verify_all  # noqa: E402
from wd.validate import check  # noqa: E402
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
        "search_terms": ("Iran", "Iranian", "Persia", "Majlis", "ایران", "استاندار"),
    },
}

#: Decided per office against the measured convention: every parent below is in
#: live use as a `P279` on real position items (counts taken 2026-08-19).
#:
#: Chosen because it *describes the office*, never to trip `wd.shape`'s PEP
#: sentinel. That ordering matters: typing a district judgeship as a supreme
#: court judge would flip the sentinel and corrupt the data to do it. Where the
#: honest parent does not set the default — `Q16533` judge, `Q14212` prime
#: minister — the gap is reported upstream and the parent stays honest.
PARENTS_BY_COUNTRY: Dict[str, Dict[str, Tuple[str, str]]] = {
  "lt": {
    "Q131824331": ("Q117826617", "apex court presidency — supreme court judge"),
    "Q133090275": ("Q117826617", "apex court presidency — supreme court judge"),
    "Q131824524": ("Q117826617", "final-instance court presidency"),
    "Q131807424": ("Q117826617", "constitutional court presidency"),
    "Q132891425": ("Q108290289", "judicial governance body, not a court"),
    "Q133190264": ("Q108290289", "parliamentary leadership"),
    # WITHDRAWN 2026-08-19. The item already carried `P279 = Q1758037` speaker,
    # which is the convention at 84 of 96 typed speakerships. `Q108290289` was
    # added because it sets the reader's PEP default and for no other reason —
    # the thing `recipes/position_items.md` forbids. Removal is on the surgical
    # list; `Q1758037` not conferring is an upstream issue, not a parent to swap.
    # "Q12663218": ("Q108290289", "parliamentary leadership"),
    "Q140916310": ("Q108290289", "agency headship"),
    "Q132068652": ("Q3368517", "public prosecutor general"),
    "Q55607326": ("Q707492", "military chief of staff"),
    "Q5177800": ("Q132050", "governor"),
  },
  # Iran, measured 2026-08-19 by tallying `P279` over every position item whose
  # en label matches the office's class. Each share is that tally; only classes
  # with a clear winner are here. Council seats and secretaryships, deputy
  # speakerships, unit commands and spokesmanships were measured and came back
  # split — they stay untyped in the ledger with the tally as the reason, rather
  # than take a parent this run invented.
  "ir": {
    "Q2660216": ("Q42178", "vice president — 76 of 81"),
    "Q20987826": ("Q17578116", "interior minister — 25 of 31"),
    "Q115625149": ("Q83307", "minister; the general class, 380 in use"),
    "Q6597965": ("Q1758037", "speaker of a chamber — 62 of 69"),
    "Q5719341": ("Q380782", "commander-in-chief — 9 of 12"),
    "Q113337481": ("Q5784340", "consort — 34 of 50"),
    "Q107001741": ("Q6501749", "general secretary of a party — 46 of 58"),
    "Q124609039": ("Q1501800", "director general — 27 of 38"),
    "Q137004668": ("Q1501800", "director general — 27 of 38"),
    "Q137005532": ("Q1501800", "director general — 27 of 38"),
    "Q115625244": ("Q26204040", "deputy minister; the generic class, 10 in use"),
    # Not untyped — `Q14212` "prime minister" is already there. The office was
    # Iran's head of government until 1989 and the class that says so is absent.
    "Q13561063": ("Q2285706", "head of government, beside its existing Q14212"),
  },
}

#: Items typed as positions that are not offices at all, or that duplicate one.
#: These never enter a batch: retyping and merging are destructive-adjacent and
#: belong on the wikibase-cli list in `tasks/followups.md`.
SURGICAL_BY_COUNTRY: Dict[str, Dict[str, str]] = {
  "lt": {
    "Q114059276": "occupation ('lithuanist'), not a position — retype",
    "Q101540148": "occupation ('Lithuanian teacher'), not a position — retype",
    "Q258874": "folk-craft occupation ('dievdirbys'), not a position — retype",
    "Q565077": "military rank ('flotilla admiral'), not a position — retype",
    "Q12663357": "a body (P31=Q495430), not a position — retype",
    "Q139379876": "basketball league presidency, not a public office — retype",
    "Q63994897": "no en label, duplicates Grand Duke of Lithuania — merge",
    "Q132476998": "duplicates Q12661306 Minister of National Defence — merge",
    "Q132861229": "duplicates Q107735740 Minister of Transport — merge",
  },
  "ir": {
    "Q80934037": "military rank ('second brigadier general of IRGC') — retype",
    "Q80930817": "military rank ('brigadier general of IRGC') — retype",
    "Q80930670": "military rank ('second brigadier general') — retype",
    "Q49920382": "a Wikimedia category, not a position — retype",
    "Q49920381": "a Wikimedia category, not a position — retype",
    "Q4875094": "social class ('Bazaari'), not a position — retype",
    "Q2671576": "occupation ('Bakshy', a musician), not a position — retype",
    "Q113641745": "military rank ('Daryabegi'), not a position — retype",
    "Q106960625": "duplicates Q107391283 First Vice Chief Justice — merge",
    # Dual-typed. Adding its `P279` is additive and is in the batch; removing
    # the list-article `P31` is not, and is why it appears in both places.
    "Q6597965": "also typed Q13406463 Wikimedia list article — drop that P31",
    "Q107288100": "probably duplicates Q118321724 Deputy Speaker, which holds "
                  "the fawiki sitelink — the two name different bodies in P361, "
                  "so a human decides",
  },
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
    campaign: str, verdict, entity: Dict[str, object], holders: int,
    parents: Dict[str, Tuple[str, str]], surgical: Dict[str, str],
    country_qid: str,
) -> Optional[Record]:
    """One record per item: the statements that would model it correctly.

    Every case gets a disposition, including the ones with nothing to add — an
    item that already passes is recorded as a skip with its evidence, so the
    audit is an account of the country rather than a list of grievances.
    """
    qid = verdict.qid
    label = verdict.label or qid
    subject = Subject(kind="position", qid=qid, ref=None, label=label)
    signals = [
        Signal(channel="modelling",
               supports="yes" if verdict.well_modelled else "no",
               detail=f"defects={verdict.defects or ['none']}; "
                      f"declared={verdict.declared or ['none']}; "
                      f"polity={verdict.countries or ['none']}"
                      f" via {verdict.country_via or 'nothing'}",
               source_url=None),
        Signal(channel="os_legibility",
               supports="yes" if not verdict.os_notes else "no",
               detail=f"notes={verdict.os_notes or ['none']}; "
                      f"topics={sorted(verdict.topics - {'role.pep'}) or ['none']}",
               source_url=None),
        Signal(channel="holders", supports="yes" if holders else "no",
               detail=f"{holders} holder(s) with a P39 to this item", source_url=None),
    ]
    flags = list(verdict.defects) + list(verdict.os_notes) + (
        [] if holders else ["no_holders"])

    # An item can need both. `Q6597965` Speaker of the Majlis is untyped *and*
    # dual-typed as a list article: the `P279` is additive and belongs in the
    # batch, dropping the stray `P31` is not and belongs on the surgical list.
    # Returning early here would have silently dropped the additive half.
    if qid in surgical and qid not in parents:
        return Record(
            campaign=campaign, subject=subject, statements=[],
            decision=Decision(action="defect", rule="item_layer.surgical",
                              source="default", concern="item_layer",
                              rationale=surgical[qid]),
            office="metadata", identity={"method": "qid"}, flags=flags,
            signals=signals, notes="stop-and-ask: never a batch line",
            byproduct={"kind": "surgical", "detail": surgical[qid]},
        )

    statements: List[Statement] = []
    # Only items on the decided list get a country. An office scoped to the Grand
    # Duchy or the Lithuanian SSR resolves to no country *correctly*, and naming
    # the modern republic on one would be a wrong statement in the lane that
    # looks safest — those close `absent` in the ledger instead.
    if qid in parents and "no_polity" in verdict.defects:
        for prop in ("P17", "P1001"):
            if country_qid not in set(claim_qids(entity, prop)):
                statements.append(Statement(
                    property=prop, value=_item(country_qid),
                    qualifiers=[], references=[], existing=False,
                    end_withheld=False))
    parent = parents.get(qid)
    if parent and parent[0] not in set(claim_qids(entity, "P279")):
        statements.append(Statement(
            property="P279", value=_item(parent[0]),
            qualifiers=[], references=[], existing=False, end_withheld=False))

    if not statements:
        rule = ("modelling.sound" if verdict.well_modelled
                else "modelling.no_rule")
        rationale = (
            "already names its polity and says what kind of office it is"
            if verdict.well_modelled else
            f"defects {verdict.defects} and no measured correction applies — "
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
    if qid in surgical:
        return Record(
            campaign=campaign, subject=subject, statements=statements,
            decision=Decision(action="apply", rule="metadata.two_channel",
                              source="default", concern="item_layer",
                              rationale=f"{detail}; parent measured in live use. "
                                        "Carries a separate surgical note"),
            office="metadata", identity={"method": "qid"}, flags=flags,
            signals=signals, notes="stop-and-ask, separately: " + surgical[qid],
            byproduct={"kind": "surgical", "detail": surgical[qid]},
        )
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
        table[(verdict.well_modelled, present)] += 1
        if verdict.well_modelled != present:
            why = ("no holders" if not holders.get(verdict.qid) else
                   "review layer, or a port bug")
            disagree.append(
                f"  {verdict.qid:12} well_modelled={verdict.well_modelled} "
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
    """Fail if the recipe has drifted from the two things it must stay true to.

    The recipe names conventions that live in code, which is the kind of
    duplication that rots quietly. Two authorities, in priority order:

    `wd/create.py:ARCHETYPES` is the Wikidata authority — it holds the measured
    `P279` for each kind of office, and the recipe's table is a restatement of it.
    An archetype added there without the recipe naming it leaves the documented
    convention incomplete, and the next campaign mints against the gap.

    `wd/shape.py`'s ported constants are the secondary, OpenSanctions authority.
    Only the classes a reader would *silently* drop need naming, because those are
    the ones somebody has to look up when a well-modelled item does not appear.
    """
    from wd import create, shape

    recipe = (REPO_ROOT / "recipes" / "position_items.md").read_text()
    missing: List[str] = []

    absent = sorted(
        f"{key} ({arch.parent})"
        for key, arch in create.ARCHETYPES.items()
        if key not in recipe or arch.parent not in recipe
    )
    if absent:
        missing.append(f"  ARCHETYPES not named in the recipe: {absent}")

    ported = {
        "POSITION_BASICS": shape.POSITION_BASICS,
        "EXCLUDE_TYPES": shape.EXCLUDE_TYPES,
        "SKIP_PLACES": shape.SKIP_PLACES,
        "HISTORICAL_TYPES": shape.HISTORICAL_TYPES,
    }
    for name, qids in ported.items():
        gone = sorted(q for q in qids if q not in recipe)
        if gone:
            missing.append(f"  {name}: {gone}")
    # The subtypes that contribute topics but leave the PEP default off: the
    # traps, and the only members worth enumerating one by one.
    quiet = sorted(
        q for q, topics in shape.SUB_TYPES.items()
        if shape.PEP_SENTINEL not in topics and q not in recipe
    )
    if quiet:
        missing.append(f"  SUB_TYPES leaving the default off: {quiet}")

    if missing:
        print("recipes/position_items.md has drifted:")
        print("\n".join(missing))
        return 1
    print("recipes/position_items.md matches wd/create.py:ARCHETYPES "
          "and names every quietly-dropped class.")
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

    parents = PARENTS_BY_COUNTRY.get(args.country, {})
    surgical = SURGICAL_BY_COUNTRY.get(args.country, {})

    verdicts = verify_all(session, sorted(labels), labels=labels)
    holders = holder_counts(session, sorted(labels))
    entities = fetch_entities(session, sorted(labels), max_age=0)

    records = [
        record for record in (
            records_for(campaign, verdict, entities.get(verdict.qid, {}),
                        holders.get(verdict.qid, 0), parents, surgical,
                        str(country["qid"]))
            for verdict in verdicts
        ) if record is not None
    ]

    out_dir = REPO_ROOT / "data" / campaign / "verdicts"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{campaign}_metadata.jsonl").write_text(dumps(records))

    gates = Counter(f for v in verdicts for f in v.defects)
    notes = Counter(n for v in verdicts for n in v.os_notes)
    actions = Counter(r.decision.action for r in records)
    print(f"  well modelled   : {sum(1 for v in verdicts if v.well_modelled)}")
    print(f"  no holders      : {sum(1 for q in labels if not holders.get(q))}")
    print("  defects         : " + (", ".join(f"{k}={n}" for k, n in gates.most_common()) or "none"))
    print("  os notes        : " + (", ".join(f"{k}={n}" for k, n in notes.most_common()) or "none"))
    print("  dispositions    : " + ", ".join(f"{k}={n}" for k, n in actions.most_common()))
    print(f"  wrote {out_dir / f'{campaign}_metadata.jsonl'}")

    # A decided item that the candidate set never reached would vanish without
    # a trace, which is the one thing an audit may not do.
    reached = {v.qid for v in verdicts}
    for name, decided in (("PARENTS", set(parents)), ("SURGICAL", set(surgical))):
        unreached = sorted(decided - reached)
        if unreached:
            print(f"  !! {name} not reached by any channel: {unreached}")

    batch = [
        "\t".join([r.subject.qid, s.property, s.value.to_dict()["id"]])
        for r in records if r.decision.action == "apply" for s in r.statements
    ]
    if batch:
        result = check(batch)
        qs_path = out_dir.parent / f"{campaign}_item_layer.qs"
        if not result.ok:
            for defect in result.defects:
                print(f"  \u2717 {defect}")
            print(f"  {len(result.defects)} defect(s) — batch not written")
        else:
            qs_path.write_text("\n".join(batch) + "\n")
            print(f"  wrote {qs_path} ({len(batch)} statements)")
        for warning in result.warnings:
            print(f"  \u26a0 {warning}")

    surgical_rows = [r for r in records if r.byproduct]
    if surgical_rows:
        print(f"  surgical (stop-and-ask, never a batch line): {len(surgical_rows)}")
        for r in surgical_rows:
            print(f"     {r.subject.qid:12} {r.byproduct['detail']}")

    if args.calibrate:
        calibrate(verdicts, holders)


if __name__ == "__main__":
    main()
