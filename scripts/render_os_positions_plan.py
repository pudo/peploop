#!/usr/bin/env python
"""Render the batch that fixes the position items `wd_categories.yml` names.

    python scripts/audit_os_positions.py --json data/discover/os_positions.json
    python scripts/render_os_positions_plan.py

Three lanes, and every one of them answers "what kind of thing is this office,
and which polity or body does it belong to" — the questions `wd/shape.py` calls
`untyped`, `no_polity` and the jurisdiction gaps:

* **`P279`** on the ten items that declare a position metaclass and never say
  what kind of office they are. Each parent is measured off a sibling cluster,
  never chosen for what it makes a consumer do — the tallies are in the
  `PARENTS` table beside the QID they justify.
* **`P17` + `P1001`** on the Russian regional legislature seats. Derived from the
  body the seat's own `P361` names, gated four ways (see `regional_seats`).
* **`P361` / `P2389`** on the national offices where a body can be named with a
  second channel behind it — a sibling office that already carries the value, or
  a body named in the office's own label whose country agrees.

Nothing here is chosen to flip a downstream PEP default. `Q4175034` legislator
conferring no `role.pep` is zavod's call about zavod's topics and is reported by
the audit, not worked around: retyping 79 correctly-modelled regional seats to
trip a consumer's sentinel would be the corruption `recipes/position_items.md`
exists to prevent.
"""

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from wd.api import best_label, claim_qids, fetch_entities  # noqa: E402
from wd.http import make_session  # noqa: E402
from wd.shape import (  # noqa: E402
    COUNTRY_PROPS, FALLBACK_PROPS, _country_of, type_closure,
)
from wd.record import Decision, Record, Signal, Statement, Subject, Value, dumps  # noqa: E402
from wd.validate import check  # noqa: E402

CAMPAIGN = "os_positions"
AUDIT_JSON = REPO_ROOT / "data" / "discover" / "os_positions.json"
OUT_DIR = REPO_ROOT / "data" / "os_positions"

#: The class of every Russian regional legislature. The structural half of the
#: regional gate: it is what makes "read this body's `P1001`" a rule about one
#: institution type rather than about whatever the seat happens to point at.
REGIONAL_PARLIAMENT = "Q4345591"
RUSSIA = "Q159"

#: A kind of office for each item that declares a metaclass and nothing else,
#: with the tally that chose it. Measured 2026-08-23 by `P279` counts over the
#: sibling cluster named in each note, per `recipes/country_sweep.md` §10.
#:
#: Two of the twelve untyped items are *not* here. The Kremlin chief of staff
#: (`Q4488944`) gets no type at all because its description reads "Wikimedia list
#: article" while it is typed as a position — the item is two things and a `P279`
#: would entrench the wrong one; it is on the surgical list instead. Its label
#: cluster was split 8-5-4 anyway, and the structural cluster could not be built:
#: `Q7188` is not the class of a presidential administration, so the query
#: answered with Dutch municipal councillors. `Q4488944` is worse than thin — see `EXCLUDED`.
PARENTS: Dict[str, Tuple[str, str]] = {
    # The 5,211-item minister cluster in `research/position_items.md`: 85% of it
    # is `P31 = Q294414` + `P279 = Q83307`, which is the shape these three want.
    "Q106510813": ("Q83307", "minister — the 5,211-item cluster"),
    "Q106510814": ("Q83307", "minister — the 5,211-item cluster"),
    # Also the strongest sibling evidence in the batch: this cohort holds two
    # more generic minister-class items, `Q15620328` federal minister of Russia
    # and `Q20899145` minister of Spain, and both already declare `Q83307`.
    "Q68081922": ("Q83307", "minister — the 5,211-item cluster, and the two other "
                            "generic minister classes in this cohort declare it"),
    # 60 of 186 position items whose label contains "secretary general", the clear
    # winner, and 19 in the narrower cluster of offices directing a registered
    # international organisation. Both of this audit's other IGO secretaries
    # general — Council of Europe and OPEC — already carry it.
    "Q110934652": ("Q6501749", "general secretary — 60 of 186, and 19 of the IGO heads"),
    "Q12180685": ("Q6501749", "general secretary — 60 of 186, and 19 of the IGO heads"),
    # 32 of 84 "chairperson of the" items, against 7 for party leader and 6 for
    # speaker. `Q140686` is also second in the IGO-head cluster at 12.
    "Q2571270": ("Q140686", "chairperson — 32 of 84"),
    # `Q1255921` "president — leader of an organization", 10 in the IGO-head
    # cluster, and the class the World Bank, IADB and European Commission
    # presidencies in this same audit already carry. A generic "president of"
    # tally is useless here — it is dominated by state presidencies and
    # speakerships — so the org-directing cluster is the honest sample.
    "Q22955080": ("Q1255921", "president of an organisation — 10 of the IGO heads"),
    "Q7241513": ("Q1255921", "president of an organisation — 10 of the IGO heads"),
    "Q735587": ("Q1255921", "president of an organisation — the EU Commission "
                            "presidency, its sibling institution, carries it"),
    # Not a label tally: the sibling channel, and it disagrees with the tally.
    # `"president of the court"` came back 1-1-1-1 over eleven items and the wider
    # court cluster leads with `Q3188089` chief justice (73) and `Q16474031` court
    # president (29) — but the two international-court presidencies that carry any
    # `P279` both subclass **their own court's judgeship**: `Q19926443` President of
    # the ICJ takes `Q30771010` Judge of the ICJ, and `Q94692068` President of the
    # ECtHR takes `Q64682634` Judge of the ECtHR. The ICC's judgeship is
    # `Q965043` — one of the 209 items in this same audit.
    #
    # `Q3188089` chief justice is deliberately *not* also asserted: the ICJ
    # presidency carries it and the ECtHR presidency does not, and one sibling of
    # two is the thin sample §10 says to under-claim on.
    "Q7241113": ("Q965043", "the court's own judgeship — both the ICJ and ECtHR "
                            "presidencies subclass theirs"),
    # 64 of 200 "mayor of" items. `Q382617` "mayor of a place in France" leads at
    # 92 and is the corpus bias `CLAUDE.md` names outright: one wiki community
    # documented its communes, and a French subclass is not the class of a
    # Nicaraguan mayoralty.
    "Q104881755": ("Q30185", "mayor — 64 of 200, once the France-specific "
                             "subclass at 92 is set aside as corpus bias"),
}

#: The polity a decided office governs, for the cases no rule reaches.
#:
#: One entry, and it is the highest-value single row in the batch: `Q104881755`
#: Mayor of Managua is the **only** item among the 209 that resolves no country at
#: all, so zavod drops it at `position.py:230` and every holder's occupancy with
#: it. Municipal, so the polity governed is the municipality and the state goes on
#: `P17` — `recipes/position_items.md`'s pair, not a country-level `P1001`.
#:
#: `Q3274` was verified, not remembered. The first QID written here was `Q3070`,
#: which is San José, Costa Rica — the failure mode `GAP_TARGETS_BY_COUNTRY`
#: documents, reproduced within the hour.
POLITY: Dict[str, Dict[str, Tuple[str, str]]] = {
    "Q104881755": {
        "P17": ("Q811", "Nicaragua — the country Managua's own P17 names"),
        "P1001": ("Q3274", "Managua, the municipality governed (P17 = Q811)"),
    },
}

#: `P1001` on a national office whose `P17` already names its state. The measured
#: convention is 94.4% of the minister cluster, but it is applied as a decided
#: list of four rather than as a rule, because the rule would be "copy `P17` to
#: `P1001`" and that is wrong for exactly the office this audit is full of: a
#: country-level `P1001` on a *regional* seat is the sloppiness
#: `render_citizenship_plan.py` refuses. Each row names its sibling.
NATIONAL_POLITY: Dict[str, Tuple[str, str]] = {
    "Q1296423": ("Q30", "United States — a national office of the executive; "
                        "the White House Counsel serves the presidency"),
    "Q15835370": ("Q183", "Germany — Q1939555 member of the Bundestag, the "
                          "other federal chamber's seat, carries P1001 = Q183"),
    "Q4431732": ("Q159", "Russia — a national apex-court office"),
    "Q38715670": ("Q159", "Russia — Q141121446 member of the Security Council, "
                          "the generic seat in the same body, carries P1001 = Q159"),
}

#: The body an office sits in (`P361`) or directs (`P2389`), named by a **sibling
#: that already carries the value** wherever one exists, exactly as
#: `GAP_TARGETS_BY_COUNTRY` does and for the same reason: a `like:` spec carries
#: its own second channel, a QID typed from memory carries none.
#:
#: `P2389` where the office *runs* the organisation and `P361` where it is a seat
#: *in* a body — the split `igo_positions.py` measured. The three `P2389` rows are
#: head roles with no sibling to copy, so the body is named here and `verify_body`
#: is what stands in for the second channel: it must be an organisation and it
#: must resolve the office's own country.
#:
#: A label gate was written here first and removed: "the body is named in the
#: office's label" holds for the Bank of Lithuania and fails for the two offices
#: either side of it — "Chief of Defence of Lithuania" never says "Lithuanian
#: Armed Forces" — so the rule would have been documented and not run, which is
#: worse than not having it.
ORG_TARGETS: Dict[str, Dict[str, str]] = {
    # Q11144 Associate Justice of the same court carries P361 = Q11201.
    "Q11147": {"P361": "like:Q11144"},
    # Q141121446 "Member of the Security Council of Russia" — the generic seat in
    # the same body — carries P361 = Q672108.
    "Q38715670": {"P361": "like:Q141121446"},
    # Q3113035 Deputy Prime Minister of Spain carries P361 = Q3058576, and
    # Q844587 Prime Minister of Spain carries the same: two agreeing siblings.
    "Q20899145": {"P361": "like:Q3113035"},
    # Head roles, organisation named in the office's own label:
    "Q109496871": {"P2389": "Q616849"},   # Governor of the Bank of Lithuania
    "Q132068652": {"P2389": "Q282345"},   # Prosecutor General of Lithuania
    "Q55607326": {"P2389": "Q635598"},    # Chief of Defence of Lithuania
}

#: Items held out of the batch, each with the reason. Not a review queue: these
#: are decided, and the decision is "no statement from this campaign".
EXCLUDED: Dict[str, str] = {
    # The yml asserts `ua-cri`, the items resolve `ru`. A political-scope
    # decision, not a modelling gap — and `tasks/jurisdictions.md` already
    # declined to batch this exact pair, which this audit reproduced blind.
    "Q133268428": "Crimea: config says ua-cri, the item says ru — a human decides",
    "Q133268430": "Sevastopol: config says ua-cri, the item says ru — a human decides",
    # `P31 = Q4164871` with the description "Wikimedia list article": the item is
    # the *list* of chiefs of staff, so a P279 would type a list as an office and
    # a P1001 would give a list a jurisdiction. Retype or split — surgical.
    "Q4488944": "described as a Wikimedia list article while typed as a position "
                "— retype before anything is added",
    # Declares `Q28640` profession and `Q214339` role beside the metaclass, and
    # its label is a class of office rather than one seat. A generic bucket wants
    # no jurisdiction: whose municipality would it be?
    "Q4139102": "'head of municipality' is a class of office, not a seat — a "
                "generic bucket takes no P1001",
    # Typed `Q13406463` Wikimedia list article *and* a position. Additive
    # statements would entrench that; dropping the P31 is destructive.
    "Q12251224": "also typed Q13406463 Wikimedia list article — surgical",
    "Q12663218": "also typed Q13406463 Wikimedia list article — surgical",
    "Q6085548": "also typed Q13406463 Wikimedia list article — surgical",
}


def resolve_sibling(
    session: Any, spec: str, prop: str, cache: Dict[str, Dict[str, Any]]
) -> Optional[str]:
    """The value a sibling item carries for `prop`, or None if it carries no one.

    Refuses a sibling with several values: "the body the Associate Justice sits
    in" is only a second channel while there is exactly one answer.
    """
    if not spec.startswith("like:"):
        return spec
    sibling = spec[len("like:"):]
    entity = cache.get(sibling)
    if entity is None:
        entity = fetch_entities(session, [sibling], max_age=0).get(sibling, {})
        cache[sibling] = entity
    values = claim_qids(entity, prop)
    return values[0] if len(values) == 1 else None


def statement(prop: str, qid: str) -> Statement:
    return Statement(property=prop, value=Value.item(qid))


def flags_for(row: Dict[str, Any]) -> List[str]:
    """Row-level flags a reviewer should see, from the config rather than the item.

    `generic_class` means the config's own position name is a class of offices and
    not a seat (`wd.specs.BUCKET`). It is not a veto — a generic "minister of the
    Czech Republic" class wants `P279 = Q83307` as much as any single portfolio
    does — but it is the shape in which a *jurisdiction* claim goes wrong, which is
    how `Q19810880` acquired a `P1001` to Saudi Arabia. Surfaced so the reviewer
    reads those rows twice.
    """
    return ["generic_class"] if "bucket" in (row.get("granularity") or []) else []


#: Set by `--verify`. Suppresses the diff so the tables emit every statement they
#: would ever propose, which is what turns the renderer into an audit of an upload
#: that already happened. `CLAUDE.md` records four campaign checkboxes that were
#: wrong for want of exactly this, and the answer is not derivable from a run log:
#: it has to be read back off Wikidata.
VERIFY = False


def already(row: Dict[str, Any], prop: str, qid: str) -> bool:
    """Whether the item already carries this exact claim, per the audit snapshot.

    `wd/shape.py`'s gaps answer "does the item carry this property at all", which
    is the wrong question for a decided target: two of the three `P2389` rows in
    `ORG_TARGETS` were named from a search that had already been made on Wikidata,
    so the batch re-asserted a claim that was sitting on the item. QuickStatements
    would have merged them silently — which is exactly why the count a reviewer
    reads has to be the count of statements that are actually new.

    Reads the audit's own snapshot (`max_age=0` at audit time), not a fresh fetch:
    the batch a human reviews and the diff that justified it must describe the
    same moment.
    """
    return not VERIFY and qid in (row.get(prop.lower()) or [])


#: What a body is. Read as a closure over `P31`/`P279`, because none of these is
#: ever the declared type: `Q11201` Supreme Court of the United States declares
#: `Q190752` supreme court, and `Q616849` Bank of Lithuania declares
#: `Q66344` central bank — each reaches `Q43229` organization several hops up.
BODY_CLASSES = {
    "Q43229",     # organization
    "Q327333",    # government agency
    "Q11204",     # legislature
    "Q41487",     # court — its own branch of the tree
    "Q2659904",   # government organization
}


def verify_body(
    session: Any, qid: str, want: List[str], cache: Dict[str, Dict[str, Any]]
) -> Optional[str]:
    """Why `qid` is not a usable body for an office in `want`, or None if it is.

    The guard that catches a QID typed from memory — the failure that put the
    Cook Islands Cup and an Italian comune into a rendered batch, and that this
    run reproduced with San José for Managua. Two things are checked, and country
    is the sharper of them: a wrong QID from a search almost always belongs to
    another country or is not an organisation at all (a Wikimedia category, a
    scholarly article about the court, the court's *building*).

    It cannot catch a wrong *claim* — a body that really is Qatari but is not the
    body this office sits in — which is why every row still names its channel.
    """
    entity = cache.get(qid)
    if entity is None:
        entity = fetch_entities(session, [qid], max_age=0).get(qid, {})
        cache[qid] = entity
    if not entity:
        return "no such item"
    closure = type_closure(session, [qid]).get(qid, set())
    if not (closure & BODY_CLASSES):
        return f"not an organisation (declared {claim_qids(entity, 'P31')})"
    countries: set = set()
    for prop in COUNTRY_PROPS + FALLBACK_PROPS:
        for value in claim_qids(entity, prop):
            countries |= _country_of(session, value, (qid,))
        if countries:
            break
    if want and not (countries & set(want)):
        return f"resolves {sorted(countries) or 'no country'}, the office wants {want}"
    return None


#: Invisible characters that make two identical labels compare unequal. Real:
#: `Q4467481`'s label is `"Tyumen Oblast Duma\u200e"` with a trailing
#: left-to-right mark, and the seat named for it was refused a `P17` over it.
INVISIBLE = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]")

#: The leading word of a polity's name has to be this long before it counts as
#: corroboration. `CLAUDE.md`'s warning is the reason there is a floor at all:
#: the alias "Loire" fires inside "Indre-et-Loire" and "Gombe" names a city as
#: well as a state, so a short token is not evidence of anything.
MIN_STEM = 4


def _clean(text: Optional[str]) -> str:
    return INVISIBLE.sub("", text or "").casefold().strip()


def _names_the_body(seat_label: str, body_label: str, polity_label: str) -> Optional[str]:
    """Whether the seat is named for the body its `P361` points at.

    Two channels, because one wording is not enough. The body's own label is the
    strong one and usually the seat's tail verbatim. The fallback is the leading
    word of the **polity the body governs**: `Q101483020` is "Member of the
    Volgograd *Regional* Duma" while its body is the "Volgograd *Oblast* Duma",
    and refusing that row would have dropped a correct statement over a synonym.
    Matched as a whole word so a stem cannot fire inside a longer name.
    """
    seat = _clean(seat_label)
    body = _clean(body_label)
    if body and body in seat:
        return "body label is the seat's tail"
    stem = _clean(polity_label).split()
    if stem and len(stem[0]) >= MIN_STEM and re.search(
        r"\b" + re.escape(stem[0]) + r"\b", seat
    ):
        return f"the polity's name {stem[0]!r} is a word in the seat's label"
    return None


def regional_seats(
    session: Any, rows: List[Dict[str, Any]]
) -> Tuple[List[Record], List[Tuple[str, str]]]:
    """`P17` and `P1001` for the Russian regional legislature seats.

    The value comes off the **body the seat's own `P361` names**, not off the
    seat's label, and four things must hold before it is trusted:

    1. the body is typed `Q4345591` regional parliament of Russia;
    2. the seat is named for that body — `_names_the_body`, a wording-independent
       check, and the one that would catch a copy-paste error in the bulk
       creation these items came from;
    3. Russia is among the states the body names, directly or through the polity
       it governs. **Among**, not equal to: `Q4146671` State Assembly of
       Bashkortostan carries `P17` = Russia *and* the Soviet Union, and a
       superseded polity beside the current one is how Wikidata records history,
       not a reason to distrust the item. And **through the polity** because
       `Q4070652` Arkhangelsk Oblast Assembly of Deputies has no `P17` at all —
       the body has the same gap its seats do, and the one hop to the oblast
       closes it, which is the walk `country.py:item_countries` already makes; and
    4. the config's own country assertion agrees.

    Convention, measured 2026-08-23: sub-national legislator seats carry `P17` at
    103 of 114 (90%) outside Russia — 36/36 Nigeria, 13/13 Italy, 12/12 Malaysia,
    8/8 Argentina — against **2 of 66 inside it**. Russia is the anomaly, not the
    idiom: the `Q1332683xx` series was bulk-created without it.
    """
    seats = [
        row for row in rows
        if row["qid"] not in EXCLUDED
        and row["config_countries"] == ["ru"]
        # Only items with something to add. Without this, the seven *federal*
        # offices — the Government of Russia, the State Duma, the Federation
        # Council — reach the gates, fail them correctly, and fill the held-out
        # list with rows that need nothing: they already carry both properties.
        and (VERIFY or ({"no_P17", "no_P1001"} & set(row["gaps"])))
        and body_of(row) is not None
    ]
    body_qids = sorted({body_of(row) for row in seats} - {None})
    bodies = fetch_entities(session, [q for q in body_qids if q], max_age=0)
    # The polities those bodies govern, for the fallback name channel and for the
    # country walk when a body carries no `P17` of its own.
    polity_qids = sorted({
        qid for body in bodies.values() for qid in claim_qids(body, "P1001")
    })
    polities = fetch_entities(session, polity_qids, max_age=0)

    records: List[Record] = []
    rejected: List[Tuple[str, str]] = []
    for row in seats:
        qid = row["qid"]
        body_qid = body_of(row)
        body = bodies.get(body_qid or "", {})
        body_label = best_label(body) or ""
        seat_label = row.get("label") or ""
        jurisdictions = claim_qids(body, "P1001")
        polity = polities.get(jurisdictions[0], {}) if len(jurisdictions) == 1 else {}
        polity_label = best_label(polity) or ""

        if REGIONAL_PARLIAMENT not in claim_qids(body, "P31"):
            rejected.append((qid, f"P361 {body_qid} is not a regional parliament"))
            continue
        named = _names_the_body(seat_label, body_label, polity_label)
        if named is None:
            rejected.append((qid, f"P361 {body_qid} ({body_label!r}) is not named "
                                  f"in the seat's label {seat_label!r}"))
            continue
        via_body = RUSSIA in claim_qids(body, "P17")
        via_polity = RUSSIA in claim_qids(polity, "P17")
        if not (via_body or via_polity):
            rejected.append((qid, f"P361 {body_qid} reaches no Russian state, "
                                  f"directly or through {jurisdictions}"))
            continue

        statements: List[Statement] = []
        if VERIFY or "no_P17" in row["gaps"]:
            statements.append(statement("P17", RUSSIA))
        if VERIFY or "no_P1001" in row["gaps"]:
            if len(jurisdictions) != 1:
                rejected.append((qid, f"P361 {body_qid} names {len(jurisdictions)} "
                                      f"jurisdictions, so none is 'the' polity"))
            else:
                statements.append(statement("P1001", jurisdictions[0]))
        if not statements:
            continue
        records.append(Record(
            campaign=CAMPAIGN,
            subject=Subject(qid=qid, label=seat_label),
            statements=statements,
            office=qid,
            flags=flags_for(row),
            decision=Decision(
                action="apply", rule="regional_seat_from_body", concern="jurisdiction",
                rationale=f"the body {body_qid} ({body_label}) reaches Russia "
                          f"{'directly' if via_body else 'through ' + polity_label} "
                          f"and governs {polity_label or jurisdictions}",
            ),
            signals=[
                Signal(channel="body", supports="jurisdiction",
                       detail=f"{body_qid} P31 includes {REGIONAL_PARLIAMENT}, "
                              f"P1001={jurisdictions}"),
                Signal(channel="label", supports="jurisdiction", detail=named),
                Signal(channel="config", supports="jurisdiction",
                       detail="wd_categories.yml asserts country ru"),
            ],
        ))
    return records, rejected


def body_of(row: Dict[str, Any]) -> Optional[str]:
    """The single body a seat's `P361` names, or None if it names none or many."""
    bodies = row.get("p361") or []
    return bodies[0] if len(bodies) == 1 else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, default=AUDIT_JSON)
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    parser.add_argument("--verify", action="store_true",
                        help="report which of this campaign's statements are on "
                             "Wikidata now, instead of rendering what is missing")
    args = parser.parse_args()
    global VERIFY
    VERIFY = args.verify

    rows = [r for r in json.loads(args.audit.read_text()) if r["status"] == "ok"]
    by_qid = {r["qid"]: r for r in rows}
    session = make_session()
    cache: Dict[str, Dict[str, Any]] = {}
    records: List[Record] = []
    rejected: List[Tuple[str, str]] = []

    # Lane 1 — what kind of office is this.
    for qid, (parent, note) in PARENTS.items():
        row = by_qid.get(qid)
        if row is None or qid in EXCLUDED:
            rejected.append((qid, "absent from the audit or excluded"))
            continue
        if already(row, "P279", parent):
            rejected.append((qid, f"already carries P279 = {parent}"))
            continue
        records.append(Record(
            campaign=CAMPAIGN, subject=Subject(qid=qid, label=row.get("label") or ""),
            statements=[statement("P279", parent)], office=qid,
            flags=flags_for(row),
            decision=Decision(action="apply", rule="measured_parent", concern="type",
                              rationale=note),
            signals=[Signal(channel="cluster", supports="P279", detail=note)],
        ))

    # Lane 2 — the polity, for the decided cases.
    for qid, props in POLITY.items():
        row = by_qid.get(qid)
        if row is None or qid in EXCLUDED:
            continue
        for prop, (value, note) in props.items():
            if already(row, prop, value):
                rejected.append((qid, f"already carries {prop} = {value}"))
                continue
            records.append(Record(
                campaign=CAMPAIGN, subject=Subject(qid=qid, label=row.get("label") or ""),
                statements=[statement(prop, value)], office=qid,
                flags=flags_for(row),
                decision=Decision(action="apply", rule="decided_polity",
                                  concern="jurisdiction", rationale=note),
                signals=[Signal(channel="decided", supports=prop, detail=note)],
            ))
    for qid, (value, note) in NATIONAL_POLITY.items():
        row = by_qid.get(qid)
        if row is None or qid in EXCLUDED:
            continue
        if not VERIFY and "no_P1001" not in row["gaps"]:
            continue
        if already(row, "P1001", value):
            continue
        records.append(Record(
            campaign=CAMPAIGN, subject=Subject(qid=qid, label=row.get("label") or ""),
            statements=[statement("P1001", value)], office=qid,
            flags=flags_for(row),
            decision=Decision(action="apply", rule="national_polity",
                              concern="jurisdiction", rationale=note),
            signals=[Signal(channel="decided", supports="P1001", detail=note)],
        ))

    # Lane 3 — the Russian regional seats, derived from their bodies.
    seat_records, seat_rejects = regional_seats(session, rows)
    records.extend(seat_records)
    rejected.extend(seat_rejects)

    # Lane 4 — the body an office sits in or directs.
    for qid, props in ORG_TARGETS.items():
        row = by_qid.get(qid)
        if row is None or qid in EXCLUDED:
            continue
        for prop, spec in props.items():
            value = resolve_sibling(session, spec, prop, cache)
            if value is None:
                rejected.append((qid, f"{spec} carries no single {prop}"))
                continue
            if already(row, prop, value):
                rejected.append((qid, f"already carries {prop} = {value}"))
                continue
            problem = verify_body(session, value, row["countries"], cache)
            if problem is not None:
                rejected.append((qid, f"{prop} target {value}: {problem}"))
                continue
            body_label = best_label(cache.get(value, {})) or value
            records.append(Record(
                campaign=CAMPAIGN, subject=Subject(qid=qid, label=row.get("label") or ""),
                statements=[statement(prop, value)], office=qid,
                flags=flags_for(row),
                decision=Decision(action="apply", rule="body_from_sibling"
                                  if spec.startswith("like:") else "body_verified",
                                  concern="organisation",
                                  rationale=f"{prop} = {value} ({body_label}) via {spec}"),
                signals=[Signal(channel="sibling" if spec.startswith("like:") else "label",
                                supports=prop, detail=f"{spec} -> {value} ({body_label})")],
            ))

    if VERIFY:
        rows_by_qid = {r["qid"]: r for r in rows}
        live = missing = 0
        for record in records:
            row = rows_by_qid.get(record.subject.qid or "", {})
            for stmt in record.statements:
                on_wiki = stmt.value.id in (row.get(stmt.property.lower()) or [])
                live += on_wiki
                missing += not on_wiki
                if not on_wiki:
                    print(f"MISSING {record.subject.qid}\t{stmt.property}\t"
                          f"{stmt.value.id}  ({record.subject.label})")
        print(f"{live} of {live + missing} statements are on Wikidata; "
              f"{missing} missing")
        return

    lines = [
        f"{r.subject.qid}\t{s.property}\t{s.value.id}"
        for r in sorted(records, key=lambda r: (r.decision.concern, r.subject.qid or ""))
        for s in r.statements
    ]
    result = check(lines)
    args.out.mkdir(parents=True, exist_ok=True)
    if result.defects:
        for defect in result.defects:
            print(f"DEFECT {defect}")
        raise SystemExit("batch has defects; nothing written")

    (args.out / "os_positions.qs").write_text("\n".join(lines) + "\n")
    (args.out / "records.jsonl").write_text(dumps(records))

    by_rule = Counter(r.decision.rule for r in records)
    by_prop = Counter(s.property for r in records for s in r.statements)
    md: List[str] = [
        "# Position items named by `wd_categories.yml`: the fix batch",
        "",
        f"{len(lines)} statements over {len({r.subject.qid for r in records})} items, "
        f"from the {len(rows)} QIDs the config names.",
        "",
        f"By property: {dict(by_prop)}",
        f"By rule: {dict(by_rule)}",
        "",
    ]
    for concern in ("type", "jurisdiction", "organisation"):
        lane = [r for r in records if r.decision.concern == concern]
        if not lane:
            continue
        md.append(f"## {concern} ({len(lane)} records)")
        md.append("")
        for record in sorted(lane, key=lambda r: r.subject.qid or ""):
            claims = ", ".join(f"{s.property} = {s.value.id}" for s in record.statements)
            marks = "".join(f" `{flag}`" for flag in record.flags)
            md.append(f"* {record.subject.qid} **{record.subject.label}**{marks} "
                      f"→ {claims}")
            md.append(f"  * {record.decision.rule}: {record.decision.rationale}")
        md.append("")
    md.append(f"## held out of the batch ({len(EXCLUDED)} decided, "
              f"{len(rejected)} gated)")
    md.append("")
    for qid, reason in sorted(EXCLUDED.items()):
        md.append(f"* {qid} — {reason}")
    for qid, reason in sorted(rejected):
        md.append(f"* {qid} — gate: {reason}")
    md.append("")
    (args.out / "os_positions_plan.md").write_text("\n".join(md))

    print(f"{len(lines)} statements, {len(records)} records")
    print(f"by property: {dict(by_prop)}")
    print(f"by rule: {dict(by_rule)}")
    for warning in result.warnings:
        print(f"WARN {warning}")
    print(f"wrote {args.out}/os_positions.qs, records.jsonl, os_positions_plan.md")


if __name__ == "__main__":
    main()
