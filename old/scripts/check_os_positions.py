#!/usr/bin/env python
"""Pin the gates that decide the `wd_categories.yml` position batch.

    python scripts/check_os_positions.py

Reach for this before and after touching `render_os_positions_plan.py`. Every
case below is a mistake that was actually made while building that renderer,
reduced to the smallest input that reproduces it — the same discipline as
`check_shape.py` and `check_dates.py`, and for the same reason: `regression/`
catches a decision that changed, this catches the gate underneath it.

Two halves. The label/name channel is **offline** — it is pure string work, and a
pin that needs the network is a pin nobody runs. `verify_body` cannot be, since
its whole job is to read an item, so those cases are marked and skipped unless
`--online` is passed.
"""

import argparse
import sys
from pathlib import Path
from typing import List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from render_os_positions_plan import (  # noqa: E402
    EXCLUDED, NATIONAL_POLITY, ORG_TARGETS, PARENTS, POLITY, _names_the_body,
    verify_body,
)

#: (seat label, body label, polity label, should match, what it guards)
NAME_CASES: List[Tuple[str, str, str, bool, str]] = [
    (
        "Member of the Bryansk Oblast Duma", "Bryansk Oblast Duma", "Bryansk Oblast",
        True, "the ordinary case: the body's label is the seat's tail verbatim",
    ),
    (
        # `Q4467481`'s label really ends in U+200E. The seat named for it was
        # refused a `P17` over an invisible character.
        "Member of the Tyumen Oblast Duma", "Tyumen Oblast Duma‎", "Tyumen Oblast",
        True, "a bidi control character in the body's label must not split them",
    ),
    (
        # `Q101483020` vs `Q4122951`: "Regional" against "Oblast". Refusing this
        # row would have dropped a correct statement over a synonym.
        "Member of the Volgograd Regional Duma", "Volgograd Oblast Duma",
        "Volgograd Oblast", True,
        "the polity's name carries the row when the body's wording differs",
    ),
    (
        "member of the Parliament of the Kabardino-Balkar Republic",
        "Parliament of the Kabardino-Balkar Republic", "Kabardino-Balkaria", True,
        "a polity whose name shares no word with the seat still matches on the body",
    ),
    (
        "Member of the Tula Oblast Duma", "Bryansk Oblast Duma", "Bryansk Oblast",
        False, "a P361 pointing at the wrong oblast's parliament must be refused — "
               "the copy-paste error a bulk creation makes",
    ),
    (
        "Member of the State Council of the Komi Republic", "Some Other Assembly",
        "Komi Republic", True,
        "four characters is the floor, not below it: Komi is a real federal "
        "subject and every one of them clears the bar",
    ),
    (
        # The floor exists because of `CLAUDE.md`'s matcher warnings: a short stem
        # fires inside longer names ("Loire" inside "Indre-et-Loire"). The stem
        # here is synthetic — no Russian federal subject is this short — which is
        # the point: the pin is on the floor, not on a case that occurs.
        "Member of the Ufa City Council", "Some Other Assembly", "Ufa Oblast",
        False, "a stem under four characters is not evidence",
    ),
    (
        "Member of the Legislative Assembly of Amur Oblast", "Some Other Assembly",
        "Amursk Oblast", False,
        "a stem must match as a whole word, not as a prefix of one",
    ),
]

#: (qid, wanted countries, should be accepted, what it guards). Online only.
BODY_CASES: List[Tuple[str, List[str], bool, str]] = [
    ("Q11201", ["us"], True, "the Supreme Court of the United States"),
    ("Q672108", ["ru"], True, "the Security Council of Russia"),
    (
        # Written into `POLITY` as Managua on the first pass. It is San José.
        "Q3070", ["ni"], False,
        "a capital city of the wrong country — the QID-from-memory failure, "
        "reproduced in this very campaign",
    ),
    (
        "Q1129582", ["qa"], False,
        "the Cook Islands Cup — the QID `GAP_TARGETS_BY_COUNTRY` documents "
        "reaching a rendered batch as the Cabinet of Qatar",
    ),
    ("Q9952070", ["ru"], False, "a Wikimedia category, not a body"),
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--online", action="store_true",
                        help="also run the verify_body cases, which read Wikidata")
    args = parser.parse_args()
    bad = 0

    for seat, body, polity, want, why in NAME_CASES:
        got = _names_the_body(seat, body, polity)
        if bool(got) != want:
            bad += 1
            print(f"FAIL _names_the_body({seat!r}, {body!r}, {polity!r}) "
                  f"= {got!r}, want {'a match' if want else 'None'}\n  ({why})")

    # A decided table must not contradict the hold-out list: a QID in both would
    # ship a statement the campaign has already ruled out, and the tables are
    # long enough that the collision would not be visible by reading them.
    for label, table in (("PARENTS", PARENTS), ("POLITY", POLITY),
                         ("NATIONAL_POLITY", NATIONAL_POLITY),
                         ("ORG_TARGETS", ORG_TARGETS)):
        for qid in table:
            if qid in EXCLUDED:
                bad += 1
                print(f"FAIL {qid} is in both {label} and EXCLUDED: "
                      f"{EXCLUDED[qid]}")

    # Every held-out item needs a reason a reviewer can act on. "review later" is
    # not a disposition; neither is an empty string.
    for qid, reason in EXCLUDED.items():
        if len(reason) < 20:
            bad += 1
            print(f"FAIL EXCLUDED[{qid!r}] = {reason!r}: too thin to be a decision")

    # `P2389` is for the organisation an office *directs* and `P361` for the body
    # it sits *in*. Anything else in this table is a typo that would write a
    # claim nobody meant.
    for qid, props in ORG_TARGETS.items():
        for prop in props:
            if prop not in ("P361", "P2389"):
                bad += 1
                print(f"FAIL ORG_TARGETS[{qid!r}] writes {prop}, which is neither "
                      "P361 nor P2389")

    checked = len(NAME_CASES)
    if args.online:
        from wd.http import make_session  # noqa: E402

        session = make_session()
        cache: dict = {}
        for qid, want, accept, why in BODY_CASES:
            problem: Optional[str] = verify_body(session, qid, want, cache)
            if (problem is None) != accept:
                bad += 1
                print(f"FAIL verify_body({qid}, {want}) = {problem!r}, want "
                      f"{'acceptance' if accept else 'a refusal'}\n  ({why})")
        checked += len(BODY_CASES)

    if bad:
        raise SystemExit(f"\n{bad} check(s) failed")
    print(f"{checked} cases pass"
          + ("" if args.online else f" ({len(BODY_CASES)} online cases skipped)"))


if __name__ == "__main__":
    main()
