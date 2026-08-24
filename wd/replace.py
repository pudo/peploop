"""Split one statement into the several it should have been, atomically.

The case this exists for: a person's item carries **one `P39` with no dates at
all** while the evidence says they served three terms. That statement is worse
than absent — `zavod` refuses an Occupancy when nothing is dated anywhere, so it
looks recorded and emits no PEP — and neither ordinary write path can fix it.
QuickStatements matches on subject, property and *value*, so three dated lines
fold into that one statement and leave it carrying every start and every end with
nothing pairing them up (the `Q1368615` shape, live from the Ecuador batch). The
API creates, so it would leave the undated statement standing beside three new
ones.

The fix is one `wbeditentity` carrying the removal *and* the replacements
together — see `wd/write.py:edit_entity`. One revision, whole or nothing, and one
undo restores everything.

Two findings shape everything below, and both invert the obvious design:

* **Most of these statements are not actually undated.** Eleven of Poland's
  fourteen carry `P2937` naming the 9th Sejm, and that term item carries
  `P580 2019-11-12` / `P582 2023-11-12`. The statement is dated *exactly*, by
  reference. Copying those dates onto it is a plain QuickStatements merge with no
  removal and no risk, so `plan` looks for that first and refuses to remove
  anything it can date instead.
* **Every one of the fourteen carries something a naive replace would destroy.**
  All fourteen have references (`P143`, `P854`, `P4656`, `P1476`, `P1810`), and
  eleven have `P2937` and `P4100`. A remove-and-replace that drops those is data
  loss dressed as an improvement, so carrying them forward is the default and
  anything unattributable is a refusal.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from requests import Session

from wd.api import fetch_entities

#: Qualifiers that describe *which* spell a statement is about, so they cannot be
#: copied onto several replacements without asserting something false. If one is
#: present and the split produces more than one claim, refuse.
TERM_SPECIFIC: Set[str] = {
    "P2937",   # parliamentary term
    "P768",    # electoral district
    "P2715",   # elected in
    "P1365",   # replaces
    "P1366",   # replaced by
    "P580",    # start / end — a dated statement is not this module's business
    "P582",
}

#: Where a parliamentary term keeps its own dates. `P580`/`P582` first because a
#: term is a period; `P571`/`P576` are the fallback for one modelled as a body.
TERM_DATE_PROPS: Tuple[Tuple[str, str], ...] = (("P580", "P582"), ("P571", "P576"))


@dataclass
class Plan:
    """What to do about one undated statement, and why."""

    qid: str
    guid: Optional[str] = None
    baserevid: Optional[int] = None
    #: The statement as it stands, kept whole so a bad edit can be undone by hand.
    removing: Optional[Dict[str, Any]] = None
    #: Replacement claims, in wikibase-edit form.
    claims: List[Dict[str, Any]] = field(default_factory=list)
    #: Qualifier and reference properties carried onto every replacement.
    carried: List[str] = field(default_factory=list)
    #: Set when nothing should be removed. `dates` is filled when the statement
    #: turned out to be datable from its own term, which is the good outcome.
    refusal: Optional[str] = None
    dates: Optional[Tuple[Optional[str], Optional[str]]] = None

    @property
    def ok(self) -> bool:
        return self.refusal is None and bool(self.guid) and bool(self.claims)

    def describe(self) -> str:
        if self.dates:
            return (f"{self.qid} datable from its own term "
                    f"{self.dates[0]}–{self.dates[1]} — merge, do not remove")
        if self.refusal:
            return f"{self.qid} refused: {self.refusal}"
        spans = "; ".join(
            "–".join(filter(None, (
                (c.get("qualifiers", {}).get("P580") or {}).get("time"),
                (c.get("qualifiers", {}).get("P582") or {}).get("time"))))
            or "undated" for c in self.claims
        )
        return (f"{self.qid} split 1 statement into {len(self.claims)} [{spans}]"
                + (f", carrying {','.join(self.carried)}" if self.carried else ""))


def _time(entity: Dict[str, Any], prop: str) -> Optional[str]:
    for claim in (entity.get("claims") or {}).get(prop, []):
        if claim.get("rank") == "deprecated":
            continue
        value = ((claim.get("mainsnak") or {}).get("datavalue") or {}).get("value")
        if isinstance(value, dict) and value.get("time"):
            if int(value.get("precision", 0)) < 9:
                continue
            return value["time"][1:11]
    return None


def term_dates(
    session: Session, statement: Dict[str, Any]
) -> Optional[Tuple[Optional[str], Optional[str]]]:
    """The dates the statement's own `P2937` term carries, if it names one.

    This is the check that makes most removals unnecessary. A `P39` qualified
    with "9th term of the Sejm" is not undated — it is dated by reference, and
    the honest fix is to copy those dates onto it rather than to split anything.
    """
    terms = [
        (snak.get("datavalue") or {}).get("value", {}).get("id")
        for snak in (statement.get("qualifiers") or {}).get("P2937", [])
    ]
    terms = [t for t in terms if t]
    if len(terms) != 1:
        return None            # none, or several: not a single attributable term
    entity = fetch_entities(session, terms, max_age=0).get(terms[0])
    if entity is None:
        return None
    for start_prop, end_prop in TERM_DATE_PROPS:
        start, end = _time(entity, start_prop), _time(entity, end_prop)
        if start or end:
            return (start, end)
    return None


def _api_time(iso: str) -> Dict[str, Any]:
    """A partial ISO date as a wikibase-edit time value, precision stated.

    Stated rather than inferred: the precision the evidence actually offered is
    the thing being asserted, and `wikibase-edit` guessing right by accident is
    not the same as saying so.
    """
    return {"time": iso,
            "precision": {1: 9, 2: 10, 3: 11}[min(len(iso.split("-")), 3)]}


def snak_value(snak: Dict[str, Any]) -> Optional[Any]:
    """One snak as a wikibase-edit simplified value, or None if it cannot be.

    Qualifiers are not all item-valued, which is the assumption that crashed
    this the first time it met a real statement: `P1810` "subject named as" is a
    plain string and `P1476` a monolingual text. `somevalue` and `novalue` have
    no simplified form at all, so they return None and the caller refuses to
    carry them rather than silently dropping or mangling them.
    """
    if snak.get("snaktype") != "value":
        return None
    value = (snak.get("datavalue") or {}).get("value")
    if isinstance(value, str):
        return value
    if not isinstance(value, dict):
        return None
    if value.get("id"):
        return value["id"]                       # wikibase-entityid
    if value.get("time"):
        return {"time": value["time"], "precision": value.get("precision")}
    if "text" in value and "language" in value:
        return {"text": value["text"], "language": value["language"]}
    if value.get("amount"):
        return value["amount"]
    return None


def _carry(
    statement: Dict[str, Any], count: int
) -> Tuple[Dict, List[Dict], List[str], List[str]]:
    """Qualifiers and references worth copying onto each replacement.

    A term-specific qualifier is dropped from the carry set when there is more
    than one replacement, because copying "9th term of the Sejm" onto a 2023
    tenure asserts something false. With a single replacement there is nothing to
    mis-attribute, so everything carries.

    Returns the qualifiers, the references, what was carried, and what could
    **not** be expressed — the last is a refusal reason, not a warning, because
    dropping a snak is the data loss this module exists to avoid.
    """
    quals: Dict[str, Any] = {}
    carried: List[str] = []
    lost: List[str] = []
    for prop, snaks in sorted((statement.get("qualifiers") or {}).items()):
        if prop in ("P580", "P582"):
            continue                     # the replacements bring their own dates
        if count > 1 and prop in TERM_SPECIFIC:
            continue                     # reported separately by `plan`
        values = [snak_value(snak) for snak in snaks]
        if any(v is None for v in values):
            lost.append(prop)
            continue
        quals[prop] = values if len(values) > 1 else values[0]
        carried.append(prop)

    references: List[Dict[str, Any]] = []
    for ref in statement.get("references") or []:
        block: Dict[str, Any] = {}
        for prop, snaks in sorted((ref.get("snaks") or {}).items()):
            values = [snak_value(snak) for snak in snaks]
            if any(v is None for v in values):
                lost.append(f"reference {prop}")
                continue
            block[prop] = values if len(values) > 1 else values[0]
        if block:
            references.append(block)
    if references:
        carried.append(f"{len(references)} reference(s)")
    return quals, references, carried, lost


def plan(
    session: Session,
    qid: str,
    position: str,
    spans: Sequence[Tuple[Optional[str], Optional[str]]],
) -> Plan:
    """What to do about `qid`'s undated statement for `position`.

    Reads the item fresh — the statement's GUID and the item's revision are both
    state that moves, and a stale read here is the one that writes into an item
    nobody inspected.

    Refuses rather than guesses. In order: nothing undated to replace; several
    undated statements; the statement is datable from its own term (the good
    refusal); no spans offered; a term-specific qualifier that cannot be
    attributed across several replacements.
    """
    entity = fetch_entities(session, [qid], max_age=0).get(qid) or {}
    result = Plan(qid=qid, baserevid=entity.get("lastrevid"))
    if entity.get("id") and entity["id"] != qid:
        result.refusal = f"redirects to {entity['id']}"
        return result

    undated = [
        claim for claim in (entity.get("claims") or {}).get("P39", [])
        if ((claim.get("mainsnak") or {}).get("datavalue") or {})
        .get("value", {}).get("id") == position
        and not ({"P580", "P582"} & set(claim.get("qualifiers") or {}))
        and claim.get("rank") != "deprecated"
    ]
    if not undated:
        result.refusal = "no undated statement for this office"
        return result
    if len(undated) > 1:
        result.refusal = f"{len(undated)} undated statements — ambiguous"
        return result

    statement = undated[0]
    result.guid = statement.get("id")
    result.removing = statement

    dates = term_dates(session, statement)
    if dates:
        # The good outcome: no removal is needed at all.
        result.refusal = "datable from its own parliamentary term"
        result.dates = dates
        return result

    spans = [(a, b) for a, b in spans if a or b]
    if not spans:
        result.refusal = "no dated spans to replace it with"
        return result

    # Two spans that are still open cannot both be right: nobody currently holds
    # one seat twice. This caught a real case — a senator whose Sejm statement
    # was about to be replaced by "from 2015" *and* "from 2023-11-12", built from
    # evidence that was largely about the Senate.
    open_ended = [span for span in spans if not span[1]]
    if len(open_ended) > 1:
        result.refusal = (
            f"{len(open_ended)} of {len(spans)} replacement spans are open-ended "
            "— one seat cannot be currently held twice"
        )
        return result
    # ...and spans that overlap are the same objection with dates on it. Compared
    # at the precision they share, as everything here is.
    ordered = sorted(spans, key=lambda span: span[0] or "")
    for (a_start, a_end), (b_start, _b_end) in zip(ordered, ordered[1:]):
        if not (a_end and b_start):
            continue
        width = min(len(a_end), len(b_start))
        if a_end[:width] > b_start[:width]:
            result.refusal = (
                f"replacement spans overlap ({a_start}–{a_end} and {b_start}–)"
            )
            return result

    quals, references, carried, lost = _carry(statement, len(spans))
    if lost:
        result.refusal = (
            f"carries {','.join(sorted(set(lost)))} in a form this cannot copy "
            "forward — removing it would lose them"
        )
        return result
    dropped = sorted(
        (set(statement.get("qualifiers") or {}) & TERM_SPECIFIC)
        - {"P580", "P582"}
    )
    if dropped and len(spans) > 1:
        result.refusal = (
            f"carries {','.join(dropped)}, which names one spell and cannot be "
            f"attributed across {len(spans)} replacements"
        )
        return result

    for start, end in spans:
        claim: Dict[str, Any] = {"value": position, "qualifiers": dict(quals)}
        for prop, value in (("P580", start), ("P582", end)):
            if value:
                claim["qualifiers"][prop] = _api_time(value)
        if references:
            claim["references"] = references
        result.claims.append(claim)
    result.carried = carried
    return result


def payload(result: Plan) -> Dict[str, Any]:
    """The one `wbeditentity` blob: the removal and the replacements together.

    They must stay in one payload. Split into two edits and there is a window
    where the statement is gone and its replacements are not, and no single undo
    restores the item.
    """
    if not result.ok:
        raise ValueError(f"refusing to build a payload: {result.describe()}")
    return {
        "id": result.qid,
        "claims": {"P39": [{"id": result.guid, "remove": True}, *result.claims]},
    }
