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

from peploop import db, positions, prompt, propose, scope, verify, wikidata

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
#: How many years ago a tenure may have ended and still be written. The loop
#: records who holds office now; a tenure that ended a generation ago is a
#: biography, and a start that long ago with no end is more often an end the
#: article did not give than a career still running.
P39_MAX_ENDED_YEARS = 20
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
#: How many years before an office's earliest recorded holder a tenure may
#: end and still be written onto it. Coverage is sparse -- a ministry held
#: since 1991 had its first dated holder in 2008 -- so the margin is wide,
#: and what it still catches is a mayoralty of 1948 on a municipality whose
#: every recorded mayor began after 1994.
FIRST_HELD_MARGIN = 30
#: How many years before the polity's own inception a tenure may end. Two,
#: because a state's first government usually predates its recognition.
POLITY_MARGIN = 2
#: How many of a state's offices may declare a kind before it names a class
#: of seats rather than one seat. Measured over six states' tables: the kinds
#: two offices share are twins and renamed successors (two communications
#: ministries, two agriculture ministries, one mufti in two languages); at
#: three the first concurrent class appears -- one convocation of local
#: councils, regional, city and district, which one person sits on at once.
FAMILY_MAX_OFFICES = 2
#: Kinds that name a class of seats however few of a state's offices declare
#: them: the archetype parents of `offices.ARCHETYPES` (which this module
#: cannot import) except the three a state has one of, the deputies of them,
#: and the plural legislative and diplomatic classes. `check_policy` pins the
#: archetype half against `offices.py`.
FAMILY_GENERIC = frozenset({
    "Q83307",      # minister
    "Q4175034",    # legislator
    "Q16533",      # judge
    "Q117826617",  # supreme court judge
    "Q132050",     # governor
    "Q30185",      # mayor
    "Q1162163",    # director / agency head
    "Q1758037",    # speaker: one senate president presides over the whole congress too
    "Q115136557",  # politburo member
    "Q16862850",   # member of a state body
    "Q836971",     # party secretary
    "Q3188089",    # court president
    "Q1501800",    # director general
    "Q140686",     # chairperson
    "Q1255921",    # president
    "Q486839",     # member of parliament
    "Q1055894",    # deputy
    "Q3250324",    # deputy
    "Q708492",     # council member
    "Q26204040",   # deputy minister
    "Q90132546",   # deputy minister
    "Q124079538",  # deputy head
    "Q121998",     # ambassador
    "Q29645886",   # ambassador to a country
})


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
    #: The person's other proposals for the same property, as (value, status).
    siblings: list[tuple[dict[str, Any], str]] = field(default_factory=list)
    #: What `spell_conflicts` found for a P39 among the person's other spells
    #: of the same office: `sibling_spell`, `contested`, or None.
    spell_conflict: str | None = None
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


def _dated_after(value: dict[str, Any] | None, today: date) -> bool:
    """Whether a time value names a day, month or year after today.

    A coarse value compares as its first day ("+2027-00-00" sorts after
    2026-09-30 and "+2026-00-00" before it), which is the right reading: a
    year that has begun is not in the future.
    """
    if not value or not isinstance(value.get("time"), str):
        return False
    return value["time"][1:11] > today.isoformat()


def future_date(case: Case) -> Disposition | None:
    """A date after today is a schedule, not a record: a term's planned end, a nominee's start."""
    today = case.today or date.today()
    dates = [case.value if case.property in ("P569", "P570") else None,
             case.tenure("P580"), case.tenure("P582")]
    if any(_dated_after(value, today) for value in dates):
        return _skip("future_date")
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


def contested(case: Case) -> Disposition | None:
    """Two articles giving different values for a fact that can be true once.

    The verifier reads one article, so a disagreement between two is invisible
    to it: each side would pass on its own. Both were rejected as `source_wrong`
    when a human read them side by side. Neither is written; the report shows
    the pair, and fixing the wiki that is wrong is the remedy.
    """
    if case.property not in propose.SINGLE_VALUED:
        return None
    for value, status in case.siblings:
        if status in (propose.FILTERED, "unquoted"):
            continue
        if "time" in value and "time" in case.value:
            shared = min(value.get("precision", 11), case.value.get("precision", 11))
            agree = propose.at_precision(value["time"], shared) == propose.at_precision(
                case.value["time"], shared
            )
        else:
            agree = value == case.value
        if not agree:
            return _skip("contested")
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


def _endpoints(span: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {p: span[p] for p in ("P580", "P582") if isinstance(span.get(p), dict)}


def _covers(one: dict[str, Any], other: dict[str, Any]) -> bool:
    """Whether spell `one` says everything `other` says, and agrees with it."""
    mine, theirs = _endpoints(one), _endpoints(other)
    if not set(theirs) <= set(mine):
        return False
    for prop, value in theirs.items():
        shared = min(value.get("precision", 11), mine[prop].get("precision", 11))
        if propose.at_precision(value["time"], shared) != propose.at_precision(
            mine[prop]["time"], shared
        ):
            return False
    return True


def _spell_rank(span: dict[str, Any]) -> tuple[int, int, int]:
    """More endpoints, then finer, then better attested."""
    ends = _endpoints(span)
    return (
        len(ends),
        sum(v.get("precision", 0) for v in ends.values()),
        len(span.get("_sources") or []),
    )


def _touching(one: dict[str, Any], other: dict[str, Any]) -> bool:
    """Whether two spells only share a boundary: one ends the year the other starts.

    `propose.overlaps` counts touching as overlap, which is right for a spell
    against the item's record -- a date a few days off is the same appointment
    -- and wrong between two of the article's own spells, where 1992–1996 and
    1996–2000 are two terms.
    """
    for first, second in ((one, other), (other, one)):
        end, start = first.get("P582"), second.get("P580")
        if not (isinstance(end, dict) and isinstance(start, dict)):
            continue
        shared = min(end.get("precision", 11), start.get("precision", 11))
        if propose.at_precision(end["time"], shared) == propose.at_precision(start["time"], shared):
            return True
    return False


def _disputed(one: dict[str, Any], other: dict[str, Any]) -> bool:
    return propose.overlaps(one, other) and not _touching(one, other)


def spell_conflicts(spells: Sequence[tuple[int, dict[str, Any]]]) -> dict[int, str]:
    """Judge a person's several proposed spells of one office against each other.

    Two articles date one spell differently -- one says 1992–1996, the other
    1992 and nothing more -- and each passes the verifier on its own, because
    the verifier reads one article; written, they are two statements with one
    start. A spell another spell covers (same endpoints where both have them,
    fewer of its own) is `sibling_spell`. Among the survivors, two spells that
    overlap without merely touching are in dispute: both closed, both are
    `contested`; one open, the open one is, because an end the article did not
    state is evidently before the other spell began; both open, the earlier.
    Covered spells are set aside first, so a third term is judged against the
    survivors only.
    """
    out: dict[int, str] = {}
    for pid, span in spells:
        for other_id, other in spells:
            if other_id == pid or not propose.overlaps(span, other):
                continue
            if _covers(other, span) and (
                not _covers(span, other) or _spell_rank(other) > _spell_rank(span)
                or (_spell_rank(other) == _spell_rank(span) and other_id < pid)
            ):
                out[pid] = "sibling_spell"
                break
    live = [(pid, span) for pid, span in spells if pid not in out]
    for pid, span in live:
        if any(other_id != pid and _loses(span, other) for other_id, other in live):
            out[pid] = "contested"
    return out


def _loses(span: dict[str, Any], other: dict[str, Any]) -> bool:
    """Whether `span` is the one set aside when it and `other` are in dispute.

    Both closed, both are; one open, the open one is, because an end the
    article did not state is evidently before the other spell began; both
    open, the earlier.
    """
    if not _disputed(span, other):
        return False
    mine_open = "P582" not in _endpoints(span)
    theirs_open = "P582" not in _endpoints(other)
    if mine_open != theirs_open:
        return mine_open
    return not mine_open or _year(span.get("P580")) <= _year(other.get("P580"))


def family_kinds(position: dict[str, Any], use: Counter[str] | dict[str, int]) -> set[str]:
    """The kinds an office declares that name one office, not a class of many.

    `use` counts how many of the state's offices declare each kind. A kind
    that is a metaclass, says the item is not an office, is one of the
    archetype-level classes, or is declared by more than `FAMILY_MAX_OFFICES`
    of the state's offices says nothing about which seat this is.
    """
    return {
        kind for kind in position.get("kind_qids") or ()
        if kind not in positions.POSITION_METACLASSES
        and kind not in positions.NOT_AN_OFFICE
        and kind not in FAMILY_GENERIC
        and use.get(kind, 0) <= FAMILY_MAX_OFFICES
    }


def _bare_names(names: Sequence[str], drop: set[str]) -> set[frozenset[str]]:
    """Names as their content tokens, clipped, without the state's own name."""
    out = set()
    for name in names:
        bare = frozenset(t[:positions.PREFIX] for t in positions.tokens(name)) - drop
        if bare:
            out.add(bare)
    return out


def same_family(
    one: dict[str, Any],
    other: dict[str, Any],
    use: Counter[str] | dict[str, int],
    kind_names: dict[str, Sequence[str]],
) -> bool:
    """Whether two items of one state are the same seat, so one person holds one at a time.

    One office is often two items -- an interior ministry typed `P31 =
    interior minister`, and beside it one typed only `P279 = minister` and
    labelled "Minister of Internal Affairs" -- and a tenure placed on both is
    one tenure written twice. Two items are one family when they share a kind
    `family_kinds` keeps. An item whose only kinds are generic borrows the
    other's when one of its names, less the state's, *is* a name of that kind:
    "Minister of Internal Affairs of Ruritania" is an "interior minister", which
    lists "Minister of Internal Affairs" among its aliases; "Deputy Minister of
    Interior" is not. `kind_names` holds those names, from the position table.

    Ambassadorships never join one: a posting accredited to several states at
    once is the ordinary case, not a duplicate.
    """
    if one.get("qid") == other.get("qid") or one.get("diplomatic") or other.get("diplomatic"):
        return False
    mine, theirs = family_kinds(one, use), family_kinds(other, use)
    if mine & theirs:
        return True
    for untyped, typed, kinds in ((one, other, theirs), (other, one, mine)):
        if family_kinds(untyped, use) or not kinds:
            continue
        drop = {t[:positions.PREFIX] for t in positions.tokens(untyped.get("jurisdiction_text") or "")}
        names = _bare_names(untyped.get("names") or [untyped.get("label") or ""], drop)
        if any(names & _bare_names(kind_names.get(kind, ()), drop) for kind in kinds):
            return True
    return False


def family_conflicts(
    spells: Sequence[tuple[int, dict[str, Any], dict[str, Any]]],
    use: Counter[str] | dict[str, int],
    kind_names: dict[str, Sequence[str]],
) -> dict[int, str]:
    """Judge a person's spells on different items of one office family against each other.

    `spells` is (proposal id, office row, qualifiers) per surviving `P39`. Two
    spells on two items of one family that overlap without merely touching are
    one tenure on two items, or two articles disagreeing about it; either way
    the verifier, reading one article and one item at a time, passes both. The
    one set aside is picked as `spell_conflicts` picks within one item, and it
    is `contested/twin`.
    """
    out: dict[int, str] = {}
    for pid, office, span in spells:
        for other_id, other_office, other in spells:
            if other_id == pid or office.get("qid") == other_office.get("qid"):
                continue
            if _loses(span, other) and same_family(office, other_office, use, kind_names):
                out[pid] = "contested/twin"
                break
    return out


def sibling_spell(case: Case) -> Disposition | None:
    """Another proposal of the same office already says this, or disputes it."""
    if case.property == "P39" and case.spell_conflict is not None:
        return _skip(case.spell_conflict)
    return None


def tenure_before_record(case: Case) -> Disposition | None:
    """A tenure generations before anyone Wikidata records in the office.

    An item with no inception earns no `date-conflict`, and a 1948 mayoralty
    was placed on an item whose every recorded holder began after 1994: a
    municipality created that year. The first recorded holder's year stands
    in for the missing inception, with a margin for sparse coverage.
    """
    if case.property != "P39" or case.position is None:
        return None
    first = case.position.get("first_held_year")
    if first is None or case.position.get("inception") is not None:
        return None
    latest = _year(case.tenure("P582")) or _year(case.tenure("P580"))
    if latest is not None and latest < first - FIRST_HELD_MARGIN:
        return _skip("tenure_before_record")
    return None


def tenure_before_polity(case: Case) -> Disposition | None:
    """A tenure that ended before the polity the office governs existed.

    A republic founded in 1991 had no minister of the interior in 1978: that
    was the socialist republic's secretary, another era's office under a
    similar name, and the reconciler had no item to prefer.
    """
    if case.property != "P39" or case.position is None:
        return None
    founded = case.position.get("polity_inception_year")
    if founded is None:
        return None
    latest = _year(case.tenure("P582")) or _year(case.tenure("P580"))
    if latest is not None and latest < founded - POLITY_MARGIN:
        return _skip("tenure_before_polity")
    return None


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


def tenure_ended(case: Case) -> Disposition | None:
    """A tenure that ended a generation ago is a biography, not who holds office now."""
    if case.property != "P39":
        return None
    latest = _year(case.tenure("P582")) or _year(case.tenure("P580"))
    today = case.today or date.today()
    if latest is not None and latest < today.year - P39_MAX_ENDED_YEARS:
        return _skip("tenure_ended")
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


def _same_start(one: dict[str, Any], other: dict[str, Any]) -> bool:
    """Do two start times agree at the precision they share?"""
    shared = min(one.get("precision", 11), other.get("precision", 11))
    width = 11 if shared >= 11 else 8 if shared == 10 else 5
    return one["time"][:width] == other["time"][:width]


def recorded_elsewhere(case: Case) -> Disposition | None:
    """A spell nobody records under this office, already recorded under another.

    One office is often two items, and the unused twin is the trap: an
    unlabelled item for a presidency held by no one, beside the item the
    community uses for the same seat. When the item has no holder in this
    state and the person's record already carries another `P39` starting the
    same day, the spell is on record and writing it again would make the twin
    its first holder. An office minted this run is uncounted, not unheld, so
    it is never caught here.
    """
    if case.property != "P39" or case.position is None:
        return None
    counts = case.position.get("holders_by_country") or {}
    if case.state_qid is None or counts.get(case.state_qid) != 0:
        return None
    start = case.tenure("P580")
    if start is None:
        return None
    target = (case.value or {}).get("id")
    for claim in case.entity.get("claims", {}).get("P39", []):
        held = claim.get("mainsnak", {}).get("datavalue", {}).get("value", {})
        if not isinstance(held, dict) or held.get("id") in (None, target):
            continue
        for qualifier in claim.get("qualifiers", {}).get("P580", []):
            other = qualifier.get("datavalue", {}).get("value")
            if isinstance(other, dict) and "time" in other and _same_start(start, other):
                return _skip("office/recorded-elsewhere")
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
    future_date,
    # Per property, what the evidence has to be.
    minor_wiki_only,
    contested,
    refine_over_sourced,
    demonym_abroad,
    resolution_weak,
    tenure_ended,
    undated_tenure,
    start_precision,
    office_rejected,
    recorded_elsewhere,
    generic_needs_scope,
    tenure_before_polity,
    tenure_before_record,
    sibling_spell,
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
    keys = {
        row["id"]: verify.content_key(qid, row["property"], row["value"], row["qualifiers"])
        for row in rows
    }
    verified = verify.recorded_many(list(keys.values()))
    by_property: dict[str, list[tuple[dict[str, Any], str]]] = {}
    for row in rows:
        by_property.setdefault(row["property"], []).append((row["value"], row["status"]))
    out = []
    for row in rows:
        verification = verified.get(keys[row["id"]])
        siblings = [
            (value, status) for value, status in by_property.get(row["property"], [])
            if value != row["value"]
        ]
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
            verification=None if verification is None else {
                "verdict": verification.verdict, "confidence": verification.confidence,
            },
            siblings=siblings,
            today=today,
        )))
    # Spells are judged against each other only among the rows every other
    # rule lets through: a spell a rule has already set aside -- a rename the
    # reconciler was unsure of, a tenure before the polity -- is not going to
    # be written, and must not take a good sibling down with it.
    spells: dict[str, list[tuple[int, dict[str, Any]]]] = {}
    by_id = {pid: case for pid, case in out}
    for pid, case in out:
        if case.property == "P39" and decide(case).status != SKIPPED:
            spells.setdefault(case.value.get("id", ""), []).append((pid, case.qualifiers))
    for group in spells.values():
        for pid, conflict in spell_conflicts(group).items():
            by_id[pid].spell_conflict = conflict
    for pid, conflict in _family_conflicts_of(
        [(pid, by_id[pid]) for group in spells.values() for pid, _span in group], state_qid
    ).items():
        by_id[pid].spell_conflict = conflict
    return out


def _family_conflicts_of(cases: Sequence[tuple[int, Case]], state_qid: str | None) -> dict[int, str]:
    """`family_conflicts` over the surviving spells on the state's own offices.

    The names and the state's kind counts are read only when two spells on
    two items are in dispute at all, which for most people they are not.
    """
    live = [
        (pid, case.position, case.qualifiers) for pid, case in cases
        if case.spell_conflict is None and case.position is not None
        and state_qid is not None and case.position.get("country_qid") == state_qid
    ]
    if state_qid is None or not any(
        office["qid"] != other_office["qid"] and _disputed(span, other)
        for _pid, office, span in live for _other_id, other_office, other in live
    ):
        return {}
    use = positions.kind_use(state_qid)
    offices = {office["qid"]: office for _pid, office, _span in live}
    kinds = {kind for office in offices.values() for kind in family_kinds(office, use)}
    names = positions.names_by_qid([*offices, *kinds])
    for qid, office in offices.items():
        office.setdefault("names", names.get(qid, []))
    return family_conflicts(live, use, names)


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


def offices_of(qids: Sequence[str]) -> list[str]:
    """The offices the P39 proposals of these people name."""
    if not qids:
        return []
    rows = db.conn().execute(
        "SELECT DISTINCT value->>'id' FROM proposal WHERE person_qid = ANY(%s)"
        " AND property = 'P39' AND status = ANY(%s)",
        (list(qids), list(DECIDABLE)),
    )
    return [row[0] for row in rows if row[0]]


def states_of(qids: Sequence[str]) -> list[str]:
    """The states these people's runs are about."""
    if not qids:
        return []
    rows = db.conn().execute(
        "SELECT DISTINCT country FROM person WHERE qid = ANY(%s)", (list(qids),)
    )
    return [state for (cc,) in rows if (state := _state_qid(cc)) is not None]


def run(qids: Sequence[str], write: bool, today: date | None = None) -> Funnel:
    """Decide every decidable proposal of these people, writing unless told not to.

    The one thing here that reaches the network: an office nobody has asked
    the first-holder question about is asked it once, so `tenure_before_record`
    reads a filled column rather than silence; and a state whose offices'
    kinds were never read has them read once, so `family_conflicts` counts the
    whole table rather than the part that happened to be loaded since.
    """
    offices = offices_of(qids)
    unfilled = positions.unfilled_polity_inception(offices)
    if unfilled:
        positions.fill_polity_inception(unfilled)
    unfilled = positions.unfilled_first_held(offices)
    if unfilled:
        positions.fill_first_held(unfilled)
    unfilled = positions.unfilled_kinds(states_of(qids))
    if unfilled:
        positions.fill_kinds(unfilled)
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
