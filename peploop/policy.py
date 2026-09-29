"""Decide every proposal without a human: accept it, skip it, or hold it for the verifier.

Reach for this after `propose` and before `apply`. A proposal used to wait in
a review screen until somebody ruled on it, and 1,334 of them were waiting
when this was written, against five ever written; the 158 rulings that were
made fell into a handful of classes a rule can name. So the rules are here,
ordered, and the first one that applies decides. The rule's name lands in
`proposal.decided_by` as `policy:<rule>`, which is what a run's report counts
and what a regression check compares with the human rulings it still has.

Three outcomes and no fourth. `accepted` is what `apply` writes. `skipped` is
a decision with a reason, never a queue. `pending` means only that the
verifier has not yet been asked, and `run` never leaves a row there. The
deterministic gates come first so that nothing a rule would skip anyway is
ever sent to the model, and the model's answer is itself only one more gate:
`supported` at better than low confidence, or the row is skipped.

Nothing here names a country. The state a run is about is read off
`person.country`, and every threshold is a constant at the top of the file.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from psycopg.rows import dict_row
from rigour.territories import get_territory_by_qid

from peploop import db, positions, prompt, propose, scope, wikidata

ACCEPTED = "accepted"
SKIPPED = "skipped"
PENDING = "pending"
#: What `propose` leaves for the policy to read.
PROPOSED = ("new", "refine")
#: Every status a row may carry that the policy owns and may re-decide.
DECIDABLE = PROPOSED + (PENDING, SKIPPED, ACCEPTED)
DECIDER = "policy:"

#: A P39 is written only on a reconciler verdict of one of these kinds ...
P39_KINDS = ("same-office",)
#: ... at this confidence: `high` means another reader would answer the same.
P39_MIN_CONFIDENCE = "high"
#: The coarsest start a tenure may carry and still be written. 9 is a year,
#: which the reviewer accepted 23 times against 4 refusals; 11 would be a day.
P39_MIN_START_PRECISION = 9
#: Tags `positions.tags_for` derives that rule an office out as the value of
#: a P39: the item is not an office, is a class of office, is another state's
#: mission to this one, or did not exist when the tenure ran.
REJECTING_TAGS = ("not-office", "abstract", "inbound-diplomatic", "date-conflict")
#: The qualifiers that make a generic office item concrete -- the place, the
#: body, the organisation -- as opposed to the ones that describe a tenure
#: (a term, an ordinal, a district). A placement on an item the community
#: uses *with* one of these, sent without it, names no office at all.
SCOPING_QUALIFIERS = frozenset({
    "P642",   # of
    "P2389",  # organization directed by the office or position
    "P101",   # field of work
    "P1001",  # applies to jurisdiction
    "P361",   # part of
    "P108",   # employer
    "P1268",  # represents
    "P463",   # member of
})
SUPPORTED = "supported"
LOW = "low"


@dataclass
class Case:
    """Everything one rule may look at to decide one proposal.

    Built once per proposal from the tables and handed to every rule in turn,
    so a rule is a function of this and nothing else -- which is what lets
    `check_policy` fabricate one per rule with no database behind it.
    """

    property: str
    value: dict[str, Any]
    qualifiers: dict[str, Any]
    #: The status `propose` gave the row: `new` or `refine`.
    proposed: str
    quote: str | None
    lang: str | None
    #: The Wikidata item as it stood when the proposal was made.
    entity: dict[str, Any]
    #: The extraction's answer, for the dates the item may lack.
    extracted: dict[str, Any] = field(default_factory=dict)
    #: The QID of the state whose run this is; None when the run has none.
    state_qid: str | None = None
    #: The language of the category that admitted the person.
    seed_lang: str | None = None
    #: The reconciler's verdict that placed a P39: kind, confidence, qid.
    resolution: dict[str, Any] | None = None
    #: The `position` row of the office a P39 names.
    position: dict[str, Any] | None = None
    #: The verifier's answer for this content, once one has been recorded.
    verification: dict[str, Any] | None = None
    today: date | None = None

    @property
    def sources(self) -> list[dict[str, Any]]:
        """Every article that attested the value, as `propose` stored them."""
        found = self.qualifiers.get("_sources")
        if found:
            return list(found)
        return [{"lang": self.lang, "quote": self.quote}]

    def tenure(self, prop: str) -> dict[str, Any] | None:
        """One endpoint of a P39 as a time value, or None when not proposed."""
        value = self.qualifiers.get(prop)
        return value if isinstance(value, dict) and "time" in value else None


@dataclass(frozen=True)
class Disposition:
    """What the policy decided, and the rule that decided it."""

    status: str
    rule: str

    @property
    def decided_by(self) -> str:
        return DECIDER + self.rule


Rule = Callable[[Case], Disposition | None]


def _skip(rule: str) -> Disposition:
    return Disposition(SKIPPED, rule)


def _year(value: dict[str, Any] | None) -> int | None:
    """The year of a time value, or None when it has none worth reading."""
    if value is None or value.get("precision", 0) < 9:
        return None
    text = propose.at_precision(value["time"], 9)
    if text is None:
        return None
    try:
        return int(text)
    except ValueError:
        return None


# --- universal gates, in the order they are asked ---------------------------


def lane_removed(case: Case) -> Disposition | None:
    """Labels and aliases are no longer written: 13 of the 19 reviewed were titles or fragments."""
    if case.property.startswith((propose.LABEL_PREFIX, propose.ALIAS_PREFIX)):
        return _skip("lane_removed")
    return None


def extracted_out_of_scope(case: Case) -> Disposition | None:
    """The item said nothing about when they lived, and the articles did."""
    if scope.out_of_scope_extracted(case.extracted, case.today) is not None:
        return _skip("extracted_out_of_scope")
    return None


def no_quote(case: Case) -> Disposition | None:
    """A value no article was quoted for has no evidence to verify."""
    if not any(source.get("quote") for source in case.sources):
        return _skip("no_quote")
    return None


# --- dates ------------------------------------------------------------------


def _allowed_langs(case: Case) -> set[str]:
    return {"en", *prompt.country_langs(case.seed_lang, case.entity)}


def minor_wiki_only(case: Case) -> Disposition | None:
    """A date only a wiki outside the person's own languages gives.

    Both dates the reviewer rejected as `source_wrong` were attested by one
    minor wiki alone and contradicted by the article in the person's own
    language. A second attestation, or the home wiki, clears it.
    """
    if case.property not in ("P569", "P570"):
        return None
    langs = {source.get("lang") for source in case.sources}
    if len(langs) == 1 and not (langs & _allowed_langs(case)):
        return _skip("minor_wiki_only")
    return None


def refine_over_sourced(case: Case) -> Disposition | None:
    """A sharper date over somebody else's citation stays unwritten.

    `apply` would put ours beside theirs at preferred rank, which outranks a
    source nobody here has read. Only an import-only or unreferenced
    statement is ours to sharpen.
    """
    if case.property not in ("P569", "P570") or case.proposed != "refine":
        return None
    value = case.value
    for claim in case.entity.get("claims", {}).get(case.property, []):
        if claim.get("rank") == "deprecated":
            continue
        found = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        if not isinstance(found, dict) or "time" not in found:
            continue
        precision = found.get("precision", 0)
        shared = min(precision, value["precision"])
        agrees = propose.at_precision(found["time"], shared) == propose.at_precision(
            value["time"], shared
        )
        if agrees and precision < value["precision"] and not wikidata.is_import(claim):
            return _skip("refine_over_sourced")
    return None


# --- citizenship --------------------------------------------------------------


def _state_qids(case: Case) -> set[str]:
    if case.state_qid is None:
        return set()
    territory = get_territory_by_qid(case.state_qid)
    return set(territory.qids) if territory is not None else {case.state_qid}


def demonym_abroad(case: Case) -> Disposition | None:
    """A demonym names the run's own state or it names nothing certain.

    The lead's nationality adjective beside a category of that state's
    politicians is two signals agreeing; a second adjective in the same lead
    is one word about origins, and Wikidata wants a citizenship. An explicit
    statement of citizenship passes whatever state it names.
    """
    if case.property != "P27" or case.qualifiers.get("_basis") == "explicit":
        return None
    if case.value.get("id") in _state_qids(case):
        return None
    if wikidata.claim_qids(case.entity, "P27", include_deprecated=False):
        return _skip("demonym/second_citizenship")
    return _skip("demonym/foreign")


# --- positions ----------------------------------------------------------------


def resolution_weak(case: Case) -> Disposition | None:
    """Only a confident, direct match of the office is written."""
    if case.property != "P39":
        return None
    if case.resolution is None:
        return _skip("resolution/missing")
    kind = case.resolution.get("kind")
    if kind not in P39_KINDS:
        return _skip(f"resolution/{kind}")
    if case.resolution.get("confidence") != P39_MIN_CONFIDENCE:
        return _skip(f"resolution/{case.resolution.get('confidence')}")
    return None


def tenure_out_of_scope(case: Case) -> Disposition | None:
    """A tenure that ended before anyone alive was born is not exposure."""
    if case.property != "P39":
        return None
    latest = _year(case.tenure("P582")) or _year(case.tenure("P580"))
    today = case.today or date.today()
    if latest is not None and latest < today.year - scope.MAX_AGE_YEARS:
        return _skip("tenure_out_of_scope")
    return None


def undated_tenure(case: Case) -> Disposition | None:
    """A P39 with no start is a fact about the person, not a tenure.

    Three of the four undated tenures reviewed were rejected, and downstream an
    undated statement produces no Occupancy without a birth date to anchor it.
    A `refine` may carry only an end, since it sharpens a statement already
    there.
    """
    if case.property != "P39":
        return None
    if case.tenure("P580") is None and (
        case.proposed != "refine" or case.tenure("P582") is None
    ):
        return _skip("undated_tenure")
    return None


def start_precision(case: Case) -> Disposition | None:
    """The start is at least as fine as `P39_MIN_START_PRECISION`."""
    if case.property != "P39":
        return None
    start = case.tenure("P580")
    if start is not None and start.get("precision", 0) < P39_MIN_START_PRECISION:
        return _skip("start_precision")
    return None


def office_tags(case: Case) -> list[str]:
    """The tags the ranking derives for the office, against this tenure."""
    if case.position is None:
        return []
    start, end = case.tenure("P580"), case.tenure("P582")
    return positions.tags_for(
        case.position,
        case.state_qid,
        None if start is None else _year(start),
        None if end is None else _year(end),
    )


def office_rejected(case: Case) -> Disposition | None:
    """What the ranking already knew about the item rules the placement out.

    `foreign-scoped` is another state's office reached only because one of
    this state's citizens held it, which is right for a posting abroad --
    `diplomatic` alongside it -- and wrong for anything else.
    """
    if case.property != "P39":
        return None
    if case.position is None:
        return _skip("office/unindexed")
    tags = office_tags(case)
    for tag in REJECTING_TAGS:
        if tag in tags:
            return _skip(f"office/{tag}")
    if "foreign-scoped" in tags and "diplomatic" not in tags:
        return _skip("office/foreign-scoped")
    return None


def generic_needs_scope(case: Case) -> Disposition | None:
    """A generic item is concrete only with the qualifier its community uses.

    `propose` writes no such qualifier yet, so today this lane -- the state
    secretaries, the party chairs, the committee chairs -- is skipped whole,
    and its size is what the report shows. Term and ordinal qualifiers do not
    count: a legislature's seat is the office, and the term describes the
    tenure.
    """
    if case.property != "P39" or case.position is None:
        return None
    wanted = case.position.get("scope_qualifier")
    generic = wanted in SCOPING_QUALIFIERS or "generic-by-convention" in office_tags(case)
    if generic and not (set(case.qualifiers) & SCOPING_QUALIFIERS):
        return _skip("generic_needs_scope")
    return None


# --- the verifier ------------------------------------------------------------


def unverified(case: Case) -> Disposition | None:
    """Everything that survives the rules above is asked of the verifier."""
    if case.verification is None:
        return Disposition(PENDING, "unverified")
    return None


def verify_refused(case: Case) -> Disposition | None:
    """The verifier's verdict is the last gate, and only `supported` passes it."""
    assert case.verification is not None
    verdict = case.verification.get("verdict")
    if verdict != SUPPORTED:
        return _skip(f"verify/{verdict}")
    if case.verification.get("confidence") == LOW:
        return _skip("verify/low")
    return None


RULES: tuple[Rule, ...] = (
    # Does the row belong in the write path at all.
    lane_removed,
    extracted_out_of_scope,
    no_quote,
    # Per property, what the evidence has to be.
    minor_wiki_only,
    refine_over_sourced,
    demonym_abroad,
    resolution_weak,
    tenure_out_of_scope,
    undated_tenure,
    start_precision,
    office_rejected,
    generic_needs_scope,
    # Only then the model, and only as one more gate.
    unverified,
    verify_refused,
)
#: The rule that applies when none of the others does.
ACCEPT_RULE = "supported"


def decide(case: Case) -> Disposition:
    """Run the rules in order and return the first disposition, or accept."""
    for rule in RULES:
        found = rule(case)
        if found is not None:
            return found
    return Disposition(ACCEPTED, ACCEPT_RULE)


# --- from the tables ------------------------------------------------------


def _position_rows(qids: Sequence[str]) -> dict[str, dict[str, Any]]:
    if not qids:
        return {}
    with db.conn().cursor(row_factory=dict_row) as cur:
        rows = cur.execute("SELECT * FROM position WHERE qid = ANY(%s)", (list(qids),))
        return {row["qid"]: row for row in rows}


def _seed_lang(qid: str) -> str | None:
    row = db.conn().execute(
        "SELECT lang FROM membership WHERE qid = %s ORDER BY seen_at, lang LIMIT 1", (qid,)
    ).fetchone()
    return None if row is None else row[0]


def _state_qid(country: str | None) -> str | None:
    if not country:
        return None
    try:
        return positions.country_qid(country)
    except ValueError:
        return None


def person_cases(qid: str, today: date | None = None) -> list[tuple[int, Case]]:
    """Build a case for every proposal of one person the policy may decide.

    A row a human ruled on is theirs and is left out; so is a row `apply` has
    written. Everything else is re-decided from scratch every time, which is
    what makes a rule change one command rather than a migration.
    """
    conn = db.conn()
    with conn.cursor(row_factory=dict_row) as cur:
        person = cur.execute(
            "SELECT p.country, i.json AS entity FROM person p"
            " LEFT JOIN item i ON i.qid = p.qid WHERE p.qid = %s",
            (qid,),
        ).fetchone()
        if person is None or person["entity"] is None:
            return []
        rows = cur.execute(
            "SELECT p.id, p.property, p.value, p.qualifiers, p.status, p.proposed_status,"
            " p.quote, p.source_lang, e.response_json,"
            " r.kind, r.confidence, r.qid AS office"
            " FROM proposal p"
            " LEFT JOIN extraction e ON e.id = p.extraction_id"
            " LEFT JOIN resolution r ON r.id = p.resolution_id"
            " WHERE p.person_qid = %s AND p.status = ANY(%s)"
            " AND (p.decided_by IS NULL OR p.decided_by LIKE %s)"
            " ORDER BY p.id",
            (qid, list(DECIDABLE), DECIDER + "%"),
        ).fetchall()
    offices = _position_rows(
        [row["value"].get("id") for row in rows if row["property"] == "P39"]
    )
    state_qid = _state_qid(person["country"])
    seed_lang = _seed_lang(qid)
    out = []
    for row in rows:
        proposed = row["proposed_status"] or row["status"]
        resolution = None
        if row["kind"] is not None:
            resolution = {
                "kind": row["kind"], "confidence": row["confidence"], "qid": row["office"],
            }
        out.append((row["id"], Case(
            property=row["property"],
            value=row["value"],
            qualifiers=dict(row["qualifiers"] or {}),
            proposed=proposed if proposed in PROPOSED else "new",
            quote=row["quote"],
            lang=row["source_lang"],
            entity=person["entity"],
            extracted=row["response_json"] or {},
            state_qid=state_qid,
            seed_lang=seed_lang,
            resolution=resolution,
            position=offices.get(row["value"].get("id")) if row["property"] == "P39" else None,
            verification=None,
            today=today,
        )))
    return out


def record(proposal_id: int, disposition: Disposition) -> None:
    """Write one disposition, keeping the status `propose` gave the row."""
    db.conn().execute(
        "UPDATE proposal SET proposed_status = coalesce(proposed_status, status),"
        " status = %s, decided_by = %s, decided_at = now() WHERE id = %s",
        (disposition.status, disposition.decided_by, proposal_id),
    )


@dataclass
class Funnel:
    """What a policy pass made of the rows it read, for the report."""

    #: (property group, rule) -> rows that rule decided.
    decided: Counter[tuple[str, str]] = field(default_factory=Counter)
    #: property group -> rows that entered.
    entered: Counter[str] = field(default_factory=Counter)
    #: office QID -> rows that reached the verifier or were accepted.
    offices: Counter[str] = field(default_factory=Counter)

    def add(self, case: Case, disposition: Disposition) -> None:
        group = property_group(case.property)
        self.entered[group] += 1
        self.decided[(group, disposition.rule)] += 1
        if case.property == "P39" and disposition.status in (PENDING, ACCEPTED):
            self.offices[case.value.get("id", "?")] += 1


def property_group(prop: str) -> str:
    """Fold the per-language term pseudo-properties into one row of the report."""
    if prop.startswith(propose.LABEL_PREFIX):
        return "label:*"
    if prop.startswith(propose.ALIAS_PREFIX):
        return "alias:*"
    return prop


def run(qids: Sequence[str], write: bool, today: date | None = None) -> Funnel:
    """Decide every decidable proposal of these people, writing unless told not to."""
    funnel = Funnel()
    for qid in qids:
        for proposal_id, case in person_cases(qid, today):
            disposition = decide(case)
            funnel.add(case, disposition)
            if write:
                record(proposal_id, disposition)
    return funnel


def _rule_order(rule: str) -> tuple[int, str]:
    base = rule.split("/", 1)[0]
    names = [fn.__name__ for fn in RULES] + [ACCEPT_RULE]
    # A dynamic name's base is the function's, minus the `_weak`/`_rejected`
    # suffix that keeps the function readable and the report short.
    for index, name in enumerate(names):
        if name == base or name.startswith(base + "_"):
            return (index, rule)
    return (len(names), rule)


def report_lines(funnel: Funnel, labels: dict[str, str | None] | None = None) -> list[str]:
    """Render the funnel per property: what entered, what each rule took, what is left."""
    lines: list[str] = []
    for group, total in sorted(funnel.entered.items(), key=lambda kv: -kv[1]):
        lines.append(f"{group}: {total} proposals")
        rules = [(rule, n) for (g, rule), n in funnel.decided.items() if g == group]
        for rule, count in sorted(rules, key=lambda kv: _rule_order(kv[0])):
            status = {ACCEPT_RULE: ACCEPTED, "unverified": PENDING}.get(rule, SKIPPED)
            lines.append(f"  {status:9s} {count:6d}  {rule}")
    if funnel.offices:
        lines.append("offices reaching the verifier or accepted (top 15):")
        for qid, count in funnel.offices.most_common(15):
            name = (labels or {}).get(qid) or ""
            lines.append(f"  {count:6d}  {qid} {name}")
    return lines


def office_labels(qids: Sequence[str]) -> dict[str, str | None]:
    """Name the offices the report lists, from the position table."""
    if not qids:
        return {}
    rows = db.conn().execute(
        "SELECT qid, label FROM position WHERE qid = ANY(%s)", (list(qids),)
    )
    return dict(rows)
