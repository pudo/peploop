#!/usr/bin/env python
"""Pin the guards on the only tool here that removes a statement.

    python scripts/check_replace.py

Offline: `plan` needs a session only to look up a parliamentary term, so a
stand-in that answers `fetch_entities` covers every case. No key, no tokens.

`wd/replace.py` is the most dangerous module in the workbench — it is the one
that deletes — so every refusal it makes is pinned here, and each of the cases
below is one that a real run produced. The ordering matters as much as the
refusals: *datable from its own term* has to be found before anything is
removed, because eleven of Poland's fourteen were that and removal would have
been pure loss.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import wd.replace as replace  # noqa: E402
from wd.replace import payload, plan, snak_value  # noqa: E402

TERM = "Q71709885"


def item(**kw):
    return {"id": "Q1", "lastrevid": 99, "claims": {"P39": [kw["claim"]]}}


def claim(guid="Q1$abc", value="Q9", qualifiers=None, references=None, rank="normal"):
    return {"id": guid, "rank": rank,
            "mainsnak": {"snaktype": "value",
                         "datavalue": {"value": {"id": value}}},
            **({"qualifiers": qualifiers} if qualifiers else {}),
            **({"references": references} if references else {})}


def snak(value):
    return {"snaktype": "value", "datavalue": {"value": value}}


class FakeSession:
    """Answers the two `fetch_entities` calls `plan` can make."""

    def __init__(self, entity, term=None):
        self.entity, self.term = entity, term


def fake_fetch(session, qids, props=None, max_age=None):
    if list(qids) == ["Q1"]:
        return {"Q1": session.entity}
    if session.term is not None and list(qids) == [TERM]:
        return {TERM: session.term}
    return {}


DATED_TERM = {"id": TERM, "claims": {
    "P580": [{"mainsnak": {"datavalue": {"value": {"time": "+2019-11-12T00:00:00Z",
                                                   "precision": 11}}}}],
    "P582": [{"mainsnak": {"datavalue": {"value": {"time": "+2023-11-12T00:00:00Z",
                                                   "precision": 11}}}}]}}

#: (name, entity, term item, spans, expected refusal fragment or None)
CASES = [
    ("a clean two-way split",
     item(claim=claim(references=[{"snaks": {"P143": [snak({"id": "Q1551807"})]}}])),
     None, [("2015", "2019"), ("2024-06-26", None)], None),
    # The finding that reordered this whole module: most of these are not
    # undated at all, they are dated by the term they name.
    ("datable from its own term",
     item(claim=claim(qualifiers={"P2937": [snak({"id": TERM})]})),
     DATED_TERM, [("2015", "2019"), ("2023", None)],
     "datable from its own parliamentary term"),
    ("nothing undated to replace",
     item(claim=claim(qualifiers={"P580": [snak({"time": "+2015-01-01T00:00:00Z"})]})),
     None, [("2015", "2019")], "no undated statement"),
    ("a deprecated statement is not a candidate",
     item(claim=claim(rank="deprecated")), None, [("2015", "2019")],
     "no undated statement"),
    ("no spans to replace it with",
     item(claim=claim()), None, [(None, None)], "no dated spans"),
    # One seat cannot be currently held twice. A real senator's Sejm statement
    # was about to be replaced by "from 2015" and "from 2023" together.
    ("two open-ended spans",
     item(claim=claim()), None, [("2015", None), ("2023-11-12", None)],
     "open-ended"),
    ("overlapping spans",
     item(claim=claim()), None, [("2015", "2021"), ("2019", "2023")], "overlap"),
    # A term-specific qualifier cannot be attributed across several claims...
    ("term qualifier, several replacements",
     item(claim=claim(qualifiers={"P768": [snak({"id": "Q6518511"})]})),
     None, [("2015", "2019"), ("2023", None)], "cannot be attributed"),
    # ...but with one replacement there is nothing to mis-attribute.
    ("term qualifier, one replacement",
     item(claim=claim(qualifiers={"P768": [snak({"id": "Q6518511"})]})),
     None, [("2015", "2019")], None),
    # Dropping a snak is the data loss this module exists to avoid.
    ("a snak that cannot be copied forward",
     item(claim=claim(qualifiers={"P4100": [{"snaktype": "somevalue"}]})),
     None, [("2015", "2019"), ("2023", None)], "cannot copy forward"),
    ("a merged item is refused",
     {"id": "Q2", "lastrevid": 1, "claims": {}}, None, [("2015", "2019")],
     "redirects to Q2"),
]


def main() -> None:
    bad = 0
    original = replace.fetch_entities
    replace.fetch_entities = fake_fetch
    try:
        for name, entity, term, spans, want in CASES:
            result = plan(FakeSession(entity, term), "Q1", "Q9", spans)
            got = result.refusal
            if want is None and got is not None:
                bad += 1
                print(f"FAIL {name}: expected a plan, refused with {got!r}")
            elif want is not None and (got is None or want not in got):
                bad += 1
                print(f"FAIL {name}: expected refusal containing {want!r}, "
                      f"got {got!r}")

        # The payload must carry the removal and the replacements together. Two
        # edits would leave a window with the statement gone and nothing in its
        # place, and no single undo would restore the item.
        result = plan(FakeSession(item(claim=claim(
            references=[{"snaks": {"P143": [snak({"id": "Q1551807"})]}}])), None),
            "Q1", "Q9", [("2015", "2019"), ("2024-06-26", None)])
        blob = payload(result)
        claims = blob["claims"]["P39"]
        if claims[0] != {"id": "Q1$abc", "remove": True}:
            bad += 1
            print(f"FAIL payload must lead with the removal: {claims[0]}")
        if len(claims) != 3:
            bad += 1
            print(f"FAIL payload must hold the removal and both claims: {len(claims)}")
        if not all(c.get("references") for c in claims[1:]):
            bad += 1
            print("FAIL the old statement's references must carry onto each claim")
        if result.baserevid != 99:
            bad += 1
            print(f"FAIL baserevid must come from the fresh read: {result.baserevid}")

        # A refused plan must be structurally incapable of producing a payload.
        refused = plan(FakeSession(item(claim=claim()), None), "Q1", "Q9",
                       [("2015", None), ("2023", None)])
        try:
            payload(refused)
            bad += 1
            print("FAIL a refused plan must not build a payload")
        except ValueError:
            pass
    finally:
        replace.fetch_entities = original

    # Qualifiers are not all item-valued; assuming so crashed the first real run.
    shapes = [({"id": "Q42"}, "Q42"), ("Jan Kowalski", "Jan Kowalski"),
              ({"text": "x", "language": "pl"}, {"text": "x", "language": "pl"})]
    for value, want in shapes:
        if snak_value(snak(value)) != want:
            bad += 1
            print(f"FAIL snak_value({value!r}) -> {snak_value(snak(value))!r}")
    if snak_value({"snaktype": "somevalue"}) is not None:
        bad += 1
        print("FAIL somevalue has no simplified form and must return None")

    total = len(CASES) + 9
    if bad:
        raise SystemExit(f"\n{bad} of {total} replacement checks failed")
    print(f"{total} replacement checks pass (term-first, coherence refusals, "
          f"carry-forward, atomic payload)")


if __name__ == "__main__":
    main()
