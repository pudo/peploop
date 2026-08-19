#!/usr/bin/env python
"""Assert `wd.shape`'s three tiers against what got each one wrong.

    python scripts/check_shape.py

Reach for this before and after touching `verify` or `_add_gaps`. Every case
below is a real item this module scored wrongly at some point, reduced to the
smallest claim set that reproduces it — `check_dates.py` does the same for the
roster parser, and for the same reason: the `regression/` net catches a
*decision* that changed, this catches the scoring underneath it.

Offline by construction. Country claims name real states, which
`rigour.territories` resolves without a fetch, so `session` is never touched and
the closure is supplied by hand. A pin that needs the network is a pin nobody
runs.

Three tiers, and mixing them up is the failure this file mostly guards:

- **defects** are wrong or missing-and-fatal. Firing one proposes a *retype*.
- **gaps** are conventions unasserted. Firing one proposes an *additive claim*.
- **os_notes** are a consumer's view and are neither.
"""

import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wd.shape import (  # noqa: E402
    BILATERAL_GAPS, OFFICE_GAPS, Verdict, verify,
)

QATAR, UAE, BAHRAIN, FRANCE = "Q846", "Q878", "Q398", "Q142"
#: The Grand Duchy of Lithuania: names a polity, resolves to no modern country.
GRAND_DUCHY = "Q193689"

#: Closure entries for non-item QIDs the country walk would otherwise fetch.
#: `rigour.territories` answers for every modern state named below, but not for a
#: defunct one — and `_is_historical` falls through to a live `type_closure` for
#: anything it cannot place, which is what turns an offline pin into a network
#: call. Supplying the ancestry here keeps `session=None` honest.
AUX_CLOSURE: Dict[str, Set[str]] = {
    GRAND_DUCHY: {GRAND_DUCHY, "Q3024240"},  # historical country
}


def item(qid: str, **props: Sequence[str]) -> Dict[str, Any]:
    """A wbgetentities payload carrying nothing but the claims named."""
    claims: Dict[str, List[Dict[str, Any]]] = {}
    for prop, values in props.items():
        claims[prop] = [
            {"mainsnak": {"datavalue": {"value": {"id": v}, "type": "wikibase-entityid"}}}
            for v in values
        ]
    return {"id": qid, "claims": claims}


#: (label, entity, closure targets, expected defects, expected gaps, why)
#:
#: The closure is what a real `type_closure` would return for the item, its own
#: QID included — that is how the crawler reads types and how `verify` expects to
#: be handed them.
CASES: List[Tuple[str, Dict[str, Any], Set[str], List[str], List[str], str]] = [
    (
        "complete national office",
        item("X", P31=["Q294414"], P279=["Q83307"], P17=[QATAR],
             P1001=[QATAR], P361=["Q1129582"]),
        {"X", "Q294414", "Q83307", "Q4164871"},
        [], [],
        "Qatar's Minister of Energy: the shape every other case is measured "
        "against. Any gap here means a threshold moved.",
    ),
    (
        "national office, no P17",
        item("X", P31=["Q294414"], P279=["Q83307"], P1001=[QATAR],
             P361=["Q1129582"]),
        {"X", "Q294414", "Q83307", "Q4164871"},
        [], ["no_P17"],
        "Eleven held Qatari offices are exactly this. `no_polity` does not fire "
        "because P1001 resolves, so before the gap tier they read as complete.",
    ),
    (
        "national office, no P1001",
        item("X", P31=["Q4164871"], P279=["Q48352"], P17=[UAE]),
        {"X", "Q4164871", "Q48352"},
        [], ["no_P1001", "no_P361"],
        "President of the UAE. The first bug the tier had: `_scoped_to_history` "
        "is true of ANY polity claim, so the P17 suppressed both jurisdiction "
        "gaps and this reported complete.",
    ),
    (
        "sub-national office naming its kind",
        item("X", P31=["Q294414"], P279=["Q166382"], P17=[UAE],
             P1001=["Q100135"], P361=["Q1136236"]),
        {"X", "Q294414", "Q166382", "Q4164871", "Q3320743", "Q618779"},
        [], [],
        "A UAE emirate ruler. MUST stay empty: the second bug tested "
        "`no_office_kind` against SUB_TYPES, a list ported from a consumer, "
        "which omits Q166382 Amir — reporting all seven rulers as nameless.",
    ),
    (
        "head of state declaring only a noble title",
        item("X", P31=["Q355567"], P17=[BAHRAIN]),
        {"X", "Q355567", "Q4164871", "Q618779"},
        [], ["no_P1001", "no_P279", "no_P361"],
        "King of Bahrain. A gap and never a defect: nothing in the closure "
        "separates it from Q138024519, the Lithuanian bishopric false positive.",
    ),
    (
        "office declaring a metaclass and nothing else",
        item("X", P31=["Q294414"], P17=[BAHRAIN]),
        {"X", "Q294414", "Q4164871"},
        ["untyped"], ["no_P1001", "no_P361"],
        "`untyped` already says the kind is missing, so `no_P279` must not "
        "double-report it — the defect proposes the same P279 the gap would.",
    ),
    (
        "bilateral post, sender and embassy absent",
        item("X", P31=["Q4164871"], P279=["Q38717123", "Q29970877"], P17=[FRANCE]),
        {"X", "Q4164871", "Q38717123", "Q29970877", "Q29645880", "Q29645886"},
        [], ["no_embassy", "no_sender"],
        "All 21 ambassadorships Qatar minted. P137 sits at 78.3% and names the "
        "sender 95.8% of the time — the strongest of the diplomatic properties.",
    ),
    (
        "bilateral post is never asked for P1001 or P361",
        item("X", P31=["Q4164871"], P279=["Q38717123", "Q29970877"],
             P17=[FRANCE], P137=[QATAR], P2389=["Q3579564"]),
        {"X", "Q4164871", "Q38717123", "Q29970877", "Q29645880", "Q29645886"},
        [], [],
        "P1001 is 29.6% on bilateral posts and copies the receiver; P361 is "
        "1.2%. Listing either as missing would push a campaign into the "
        "minority idiom the recipe explicitly forbids asserting.",
    ),
    (
        "office scoped only to a historical polity",
        item("X", P31=["Q4164871"], P279=["Q83307"], P1001=[GRAND_DUCHY]),
        {"X", "Q4164871", "Q83307"},
        [], ["no_P361"],
        "Complete as it stands. Jurisdiction gaps MUST stay silent: proposing "
        "a P17 here is proposing the modern republic on a Grand Duchy office, "
        "a wrong statement in the lane that looks safest.",
    ),
    (
        "a military staff is a body, not a seat in it",
        item("X", P31=["Q6813432"], P17=["Q794"], P361=["Q2609135"]),
        {"X", "Q6813432", "Q43229", "Q4164871"},
        ["not_a_position"], [],
        "Q5942489. Declares the body class alone, so it read as a sound position "
        "and was offered P1001 — adding jurisdiction to a body entrenches the "
        "mis-type instead of surfacing it.",
    ),
    (
        "a state honorific is not an office",
        item("X", P31=["Q3320743"], P17=[BAHRAIN]),
        {"X", "Q3320743", "Q618779", "Q4164871"},
        ["not_a_position"], [],
        "Belarus has a whole stratum of these — 'Honored Architect of the Republic "
        "of Belarus' declares title-of-honor and no position metaclass. Fourteen "
        "of fifty proposed Belarusian statements were jurisdiction on an honour.",
    ),
    (
        "an office naming no polity declines the jurisdiction gaps",
        item("X", P31=["Q4164871"], P279=["Q895526"]),
        {"X", "Q4164871", "Q895526"},
        ["no_polity"], ["no_P361", "no_office_polity"],
        "Q1837782 Supreme Burgrave of the Kingdom of Bohemia. Which polity it "
        "belongs to is a decision the defect tier gates on a decided list; the "
        "label rule routed around it because 'Bohemia' is an alias of Czechia.",
    ),
    (
        "a bilateral post keeps its gaps even with no polity",
        item("X", P31=["Q4164871"], P279=["Q38717123", "Q29970877"]),
        {"X", "Q4164871", "Q38717123", "Q29970877", "Q29645880", "Q29645886"},
        ["no_polity"], ["no_P17", "no_embassy", "no_sender"],
        "Q65262135 ambassador of Qatar to Estonia. Both ends come off its own "
        "P279 classes, not off its label, so the stateless suppression above must "
        "not reach it — that would discard the tier's strongest channel.",
    ),
    (
        "a bilateral post recognised by its label alone",
        item("X", P31=["Q4164871"], P279=["Q303618"], P17=[FRANCE]),
        {"X", "Q4164871", "Q303618"},
        [], ["no_embassy", "no_sender"],
        "Q112662216 'Ambassador of the Netherlands to Saudi Arabia' declares a "
        "diplomatic rank and reaches neither bilateral class, so it took the "
        "ordinary set and was offered the P1001 the recipe forbids on a post.",
    ),
    (
        "a rank is not an office",
        item("X", P31=["Q56019"], P17=[BAHRAIN]),
        {"X", "Q56019", "Q4189293", "Q4164871"},
        ["not_a_position"], [],
        "Fires on positive evidence only, and a retype is destructive-adjacent, "
        "so no additive gap is proposed alongside it.",
    ),
]


def main() -> None:
    bad = 0
    for name, entity, types, want_defects, want_gaps, why in CASES:
        closure: Dict[str, Set[str]] = {entity["id"]: types, **AUX_CLOSURE}
        # The label matters: `_reads_bilateral` is the fallback for a post whose
        # class layer never says it is one.
        label = "Ambassador of the Netherlands to Saudi Arabia" if "label" in name \
            else name
        got: Verdict = verify(None, entity, closure, label=label)
        if got.defects != want_defects:
            bad += 1
            print(f"FAIL defects for {name!r}\n  want {want_defects!r}\n  "
                  f"got  {got.defects!r}\n  ({why})")
        if got.gaps != want_gaps:
            bad += 1
            print(f"FAIL gaps for {name!r}\n  want {want_gaps!r}\n  "
                  f"got  {got.gaps!r}\n  ({why})")
        if got.complete != (not want_defects and not want_gaps):
            bad += 1
            print(f"FAIL complete for {name!r}: got {got.complete!r}")

    # The gap names the renderer switches on. A gap added here without a
    # property to write is a gap nothing can ever close.
    for label, table in (("OFFICE_GAPS", OFFICE_GAPS), ("BILATERAL_GAPS", BILATERAL_GAPS)):
        for gap, (prop, share) in table.items():
            if not prop.startswith("P") or not 50.0 <= share <= 100.0:
                bad += 1
                print(f"FAIL {label}[{gap!r}] = {(prop, share)!r}: a gap needs a "
                      "property to write and a share strong enough to act on "
                      "unreviewed")

    if bad:
        raise SystemExit(f"\n{bad} check(s) failed")
    print(f"{len(CASES)} shape cases and "
          f"{len(OFFICE_GAPS) + len(BILATERAL_GAPS)} gap definitions pass")


if __name__ == "__main__":
    main()
