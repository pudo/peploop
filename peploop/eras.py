"""When a state existed, for every statement whose value is a state.

Reach for this before writing a country, a jurisdiction or a citizenship: a
statement naming a state that did not exist while the office or the person
did is wrong, and Wikidata editors revert it ("no such republic in 1961").
Both lanes read one answer here: peptree for an office's `P17`/`P1001`,
peploop for a person's `P27` and an office's polity.

A state's span is its best-rank `P571`/`P576`: a republic of 1993 may carry a
normal-rank 1198 for a medieval kingdom of its name. That is late for some states (Germany prefers 1949) and
early for others (Russia 1263), so an era rule only ever skips a write; it
never reads another editor's statement as wrong. A run's home state starts
later still where its configured predecessor chain says so (`state_start`).
"""

import re
from collections.abc import Iterable
from typing import Any

from peploop import memo, wikidata

#: A predecessor dissolved before this year held no office a PEP list asks about.
PEP_ERA = 1900
#: Typed a sovereign state in its own right: a regime that replaced the state, not a period of it.
SOVEREIGN = "Q3624078"
PRED_PROPS, SUCC_PROPS = ("P1365", "P155"), ("P1366", "P156")

Span = list[int | None]


def time_year(value: Any) -> int | None:
    """The year of a Wikidata time value or a WDQS date string ("+1909-01-01T…", "-0550-…")."""
    text = value.get("time") if isinstance(value, dict) else value
    if not text or not isinstance(text, str):
        return None
    m = re.match(r"([+-]?\d+)-", text)
    return int(m.group(1)) if m else None


def years(entity: dict[str, Any], prop: str) -> list[int]:
    """The years of a time property's best-rank values (preferred if any, else normal)."""
    claims = [c for c in entity.get("claims", {}).get(prop, []) if c.get("rank") != "deprecated"]
    best = [c for c in claims if c.get("rank") == "preferred"] or claims
    out = []
    for claim in best:
        y = time_year(claim.get("mainsnak", {}).get("datavalue", {}).get("value"))
        if y is not None:
            out.append(y)
    return out


def year(entity: dict[str, Any], prop: str) -> int | None:
    found = years(entity, prop)
    return max(found) if found else None


def qids(entity: dict[str, Any], prop: str) -> list[str]:
    out = []
    for claim in entity.get("claims", {}).get(prop, []):
        if claim.get("rank") == "deprecated":
            continue
        v = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(v, dict) and "id" in v:
            out.append(v["id"])
    return out


def entity_span(entity: dict[str, Any]) -> Span:
    """[first year, last year] from `P571`/`P576`; either may be None."""
    start, end = years(entity, "P571"), years(entity, "P576")
    return [min(start) if start else None, max(end) if end else None]


def pushes(qid: str, pred: str, ents: dict[str, dict[str, Any]], preds: Iterable[str]) -> bool:
    """Whether a predecessor's end moves the state's start: did today's state begin there?

    Three things look like a predecessor in the chain and are not the state's
    previous form, so their end says nothing about when the state began:

    - a federation or empire (a colony's `P17`): the British Empire ends in
      1997 with Hong Kong, which had dated Kenya and Tanzania from 1997;
    - a polity whose successors are recorded and none is this state, one of
      its predecessors, or within it (`P17`): the Portuguese Empire, which Cape
      Verde "follows", is succeeded by Portugal, while the Jamahiriya's
      successor, the interim "State of Libya", is in Libya;
    - a period of the state itself: a polity that began on or after the
      state's own recorded inception (in the PEP era) is a form the state
      already had -- a Commonwealth realm before the republic, a
      "Republic (1985-2019)", or a sideline such as the Egyptian-administered
      All-Palestine Government -- unless it is typed a sovereign state in its
      own right (Zaire, the Central African Empire), which is a regime change.
    """
    preds = set(preds)
    if pred not in preds:
        return False
    e = ents.get(pred, {})
    succ = set(qids(e, "P1366") + qids(e, "P156"))
    ours = {qid} | preds
    if succ and not succ & ours and not any(qid in qids(ents.get(x, {}), "P17") for x in succ):
        return False
    own = years(ents.get(qid, {}), "P571")
    began = min(years(e, "P571"), default=None)
    if own and min(own) >= PEP_ERA and began is not None and began >= min(own) \
            and SOVEREIGN not in qids(e, "P31"):
        return False
    return True


def state_start(qid: str, preds: Iterable[str], ents: dict[str, dict[str, Any]]) -> int | None:
    """The latest of the state's best-rank `P571` and the end of every predecessor it replaced."""
    preds = list(preds)
    ends = [end for p in preds if (end := entity_span(ents.get(p, {}))[1]) is not None and pushes(qid, p, ents, preds)]
    own = years(ents.get(qid, {}), "P571")
    return max([*own, *ends]) if own or ends else None


def span_of(values: Iterable[str]) -> dict[str, Span]:
    """[start, end] of each state (or any polity) a statement names, read once a month.

    The item's own best-rank `P571`/`P576`, without the predecessor push:
    another state's `P155` names its regimes and periods as often as the
    state it replaced (India "follows" a 2000 polity, Afghanistan the 2021
    Islamic Republic), so only a home state's configured chain moves a start
    (`state_start`). A value nothing dates is left out, and no rule reads its
    absence as a veto.
    """
    wanted = sorted(set(values))
    out: dict[str, Span] = {}
    for chunk in wikidata.values_chunks(wanted, 50):
        out.update(memo.cached("eras1:" + "|".join(chunk), lambda chunk=chunk: {
            q: entity_span(e) for q, e in wikidata.fetch_items(chunk, props="claims").items()}))
    return {q: s for q, s in out.items() if s[0] is not None or s[1] is not None}


def overlaps(a: Span | tuple[int | None, int | None], b: Span | tuple[int | None, int | None]) -> bool:
    """Whether two year spans share a year; an unknown bound reaches as far as needed."""
    (s1, e1), (s2, e2) = a, b
    return not ((e1 is not None and s2 is not None and e1 < s2) or (e2 is not None and s1 is not None and e2 < s1))


def lived_under(born: int | None, died: int | None, span: Span | None) -> bool:
    """Whether a person's life shared a year with the state's; unknown years never veto."""
    return span is None or overlaps((born, died), span)
