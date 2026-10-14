"""Decide every proposal without a human: accept it, skip it, or hold it for the verifier.

It runs at the end of every `propose` and `verify`, and stands in for a human
gate: a class of rows a reviewer would reject is a rule here, ordered, and the
first rule that applies decides. The rule's name lands in
`proposal.decided_by` as `policy:<rule>`, which is what a run's report counts.

Three outcomes and no fourth. `accepted` is what `send` writes. `skipped` is
a decision with a reason, never a queue. `pending` means only that the
verifier has not yet been asked, and `run` never leaves a row there. The
deterministic gates come first so that nothing a rule would skip anyway is
ever sent to the model, and the model's answer is itself only one more gate:
`supported` at better than low confidence, or the row is skipped.

Nothing here names a country. The state a run is about is read off
`person.country`, and every threshold is a constant at the top of the file.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from psycopg.rows import dict_row
from rigour.langs import iso_639_alpha2
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
#: An open tenure that began this many years ago or more has outlived a
#: typical term: it must be quoted as held now (`open_unattested`).
OPEN_TERM_YEARS = 4
#: What an English quote says when the office is held now: an infobox's
#: "Incumbent" and "Assumed office", or prose in the present.
CURRENT_EN = re.compile(r"\bincumbent\b|\bassumed office\b|\bpresent\b|\bcurrent(?:ly)?\b|\bsince\b|"
                        r"\b(?:is|serves|sits) (?:as )?(?:the|a|an)\b|\bserving\b", re.I)
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
    "Q1553195",    # party leader: one per party, many per state
    "Q6501749",    # general secretary
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
    "Q2632935",    # minister of state
    "Q124079538",  # deputy head
    "Q121998",     # ambassador
    "Q29645886",   # ambassador to a country
})
#: Kinds that make an office a seat in a chamber: one of many, filled together
#: when the chamber is elected or appointed anew.
CHAMBER_KINDS = frozenset({
    "Q486839",     # member of parliament
    "Q4175034",    # legislator
    "Q15686806",   # senator
    "Q1055894",    # deputy, the legislator
})
#: Kinds whose items several people hold at once, so a later start by somebody
#: else ends nothing: the chamber seats, a bench, a council, a collegial organ,
#: and the deputies a ministry has more than one of.
MULTI_SEAT_KINDS = CHAMBER_KINDS | {
    "Q16533",      # judge
    "Q117826617",  # supreme court judge
    "Q708492",     # council member
    "Q115136557",  # politburo member
    "Q16862850",   # member of a state body
    "Q26204040",   # deputy minister
    "Q90132546",   # deputy minister
    "Q2632935",    # minister of state
    "Q124079538",  # deputy head
    "Q3250324",    # deputy, the second-in-command
}
#: How many people starting one office in the same year make it a chamber by
#: measurement, for an office whose kinds were never read. A cabinet seat
#: reshuffled twice in a year has three, a government formed with six deputy
#: premiers has six; a chamber has dozens.
CHAMBER_COHORT = 10
#: The most people who may start one office in the same year for it still to
#: be read as one seat: an incumbent replaced mid-year is two, and a premier
#: who served months between two others is three.
SINGLE_SEAT_COHORT = 3
#: How long two people's spells must certainly overlap before the office is
#: read as held by several at once. A handover dated a few weeks apart is one
#: seat changing hands.
CONCURRENT_DAYS = 180
#: The closed spells a chamber seat needs, and how many of them must agree on
#: one length in whole years, before that length is taken as its term.
TERM_MIN_SPELLS = 5
TERM_MIN_AGREE = 3
#: How much shorter than the measured term the gap to a newer one may be: an
#: election held a few months early still opens the next term.
TERM_SLACK_YEARS = 1
#: How many people must start the seat in one year for that year to be a new
#: term of the chamber rather than one by-election.
NEW_TERM_COHORT = 2
#: The proposal statuses whose spells count as on record for the office: what
#: `propose` left and the policy has not set aside, and what went out.
LIVE_SPELL_STATUSES = PROPOSED + (PENDING, ACCEPTED, "applied", "sent")


@dataclass(frozen=True)
class OfficeSpell:
    """One person's spell of an office, as the record or a proposal gives it."""

    person: str
    #: `P580`/`P582` as time values; either may be missing.
    span: dict[str, Any]
    #: Whether it is on record or still on its way there. A proposal the
    #: policy skipped is not, and only measures the office.
    live: bool = True


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
    #: The newest human verdict on the row from the review sampler, `accept`
    #: or `reject`, or None when nobody read it.
    review: str | None = None
    #: The person's other proposals for the same property, as (value, status).
    siblings: list[tuple[dict[str, Any], str]] = field(default_factory=list)
    #: What `spell_conflicts` found for a P39 among the person's other spells
    #: of the same office: `sibling_spell`, `contested`, or None.
    spell_conflict: str | None = None
    #: Every spell of the office a P39 names, by anyone: Wikidata's live
    #: statements and the proposals on record, as `OfficeSpell`. None when
    #: nobody read them, which no rule reads as an empty office.
    office_spells: list[OfficeSpell] | None = None
    #: When the office, or a body it is a seat in, was dissolved: `P576` as
    #: time values, read live. None when nobody read it.
    dissolved: list[dict[str, Any]] | None = None
    #: When the state's current head of government took office (`P1313`'s
    #: open spell, read live). None when nobody read it or nobody holds it.
    government: dict[str, Any] | None = None
    #: The state and its first-level subdivisions, each with its names: the
    #: polities a mention's jurisdiction is read against. Empty when unread.
    polities: dict[str, list[str]] = field(default_factory=dict)
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


def review_rejected(case: Case) -> Disposition | None:
    """A human who read the row in the review sampler rejected it.

    The reverse does not hold: an accept in the sampler is a measurement, not
    a way past the rules, so it decides nothing and the row goes on to them.
    """
    if case.review == "reject":
        return _skip("review_rejected")
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
    """English, the person's own languages, and the languages of the run's state.

    The state's count for the people whose items record no citizenship yet,
    which is most of the ones a run adds one to.
    """
    langs = {"en", *prompt.country_langs(case.seed_lang, case.entity)}
    territory = get_territory_by_qid(case.state_qid) if case.state_qid else None
    if territory is not None:
        langs.update(iso_639_alpha2(lang) for lang in territory.langs)
    return {lang for lang in langs if lang}


def minor_wiki_only(case: Case) -> Disposition | None:
    """A date, or an open tenure, only wikis outside the person's own languages give.

    Both dates the reviewer rejected as `source_wrong` were attested by one
    minor wiki alone and contradicted by the article in the person's own
    language. A second attestation, or the home wiki, clears it. An open
    tenure is held to the home wikis and English whatever else attests it:
    one that only a distant wiki keeps open is long over, the wrong office, or
    a claim that wiki alone makes.
    """
    langs = {source.get("lang") for source in case.sources}
    if case.property in ("P569", "P570"):
        if len(langs) == 1 and not (langs & _allowed_langs(case)):
            return _skip("minor_wiki_only")
        return None
    if (case.property == "P39" and case.tenure("P580") is not None
            and case.tenure("P582") is None and not (langs & _allowed_langs(case))):
        return _skip("minor_wiki_only/open")
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

    The plan would put ours beside theirs at preferred rank, which outranks a
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
    orgs: frozenset[str] | set[str] = frozenset(),
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

    A `P279` that is an organisation (`orgs`) -- a ministry written where the
    kind of office belongs -- is no kind: it is not a class of seats and two
    offices sharing it may be a minister and their deputy. It joins through
    its names instead: an office typed as the "Ministry of Planning", and
    itself named after it, is one family with another named "Minister of
    Planning", since all three clip to the same stems. A deputy typed as the
    ministry is not named after it, and joins nothing.
    """
    if one.get("qid") == other.get("qid") or one.get("diplomatic") or other.get("diplomatic"):
        return False
    mine, theirs = family_kinds(one, use) - orgs, family_kinds(other, use) - orgs
    if mine & theirs:
        return True
    for untyped, typed, kinds in ((one, other, theirs), (other, one, mine)):
        if family_kinds(untyped, use) - orgs or not kinds:
            continue
        drop = {t[:positions.PREFIX] for t in positions.tokens(untyped.get("jurisdiction_text") or "")}
        names = _bare_names(untyped.get("names") or [untyped.get("label") or ""], drop)
        if any(names & _bare_names(kind_names.get(kind, ()), drop) for kind in kinds):
            return True
    for typed, named in ((one, other), (other, one)):
        drop = {t[:positions.PREFIX] for t in positions.tokens(
            f"{typed.get('jurisdiction_text') or ''} {named.get('jurisdiction_text') or ''}")}
        bare = [_bare_names(office.get("names") or [office.get("label") or ""], drop)
                for office in (typed, named)]
        for org in set(typed.get("kind_qids") or ()) & set(orgs):
            org_names = _bare_names(kind_names.get(org, ()), drop)
            if all(names & org_names for names in bare):
                return True
    return False


def family_conflicts(
    spells: Sequence[tuple[int, dict[str, Any], dict[str, Any]]],
    use: Counter[str] | dict[str, int],
    kind_names: dict[str, Sequence[str]],
    orgs: frozenset[str] | set[str] = frozenset(),
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
            if _loses(span, other) and same_family(office, other_office, use, kind_names, orgs):
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


def _names_in(text: str, name: str) -> bool:
    return bool(re.search(rf"(?<!\w){re.escape(name.lower())}(?!\w)", text.lower()))


def other_polity(case: Case) -> Disposition | None:
    """The office governs another of the state's polities than the one the article names.

    A federation's states each have a "Minister for Disability Services", and
    the reconciler can take one state's minister for another's.
    Read only where the mention names one of the state's first-level polities
    and the office is scoped to one; a mention naming several, or none, is
    left to the other rules.
    """
    if case.property != "P39" or not case.resolution or not case.position or not case.polities:
        return None
    text = case.resolution.get("jurisdiction") or ""
    scoped = case.position.get("jurisdiction_qid")
    if not text or scoped not in case.polities:
        return None
    named = {qid for qid, names in case.polities.items() if any(_names_in(text, n) for n in names)}
    if named and scoped not in named:
        return _skip("office/other-polity")
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


def open_unattested(case: Case) -> Disposition | None:
    """An open tenure older than a term needs a quote saying it is held now.

    No end date is read as "holds it now", and an article says when someone
    was appointed far more often than that they left: a planning minister of
    2008, a judge since elevated to a higher court, a councillor of one term
    all came back open. Read only where every quote is English, the one
    language whose present-tense markers are listed.
    """
    if case.property != "P39" or case.tenure("P582") is not None:
        return None
    start = _year(case.tenure("P580"))
    today = case.today or date.today()
    if start is None or start > today.year - OPEN_TERM_YEARS:
        return None
    sources = case.sources
    if any((s.get("lang") or "en") != "en" for s in sources):
        return None
    if any(CURRENT_EN.search(s.get("quote") or "") for s in sources):
        return None
    return _skip("open_unattested")


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


def generic_office(case: Case) -> Disposition | None:
    """The item is a class of office no `P39` should name: mayor, minister, bishop.

    Read off `positions.generic_labels()`, the generic list, and not off the ranking's
    tags, which call the same item `abstract` in one state and a local
    convention in the next. No qualifier repairs such a placement, which is
    what separates it from `generic_needs_scope`.
    """
    if case.property == "P39" and positions.is_generic((case.value or {}).get("id")):
        return _skip("office/generic")
    return None


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


def _point_years(point: scope.Point) -> float:
    """A day as a fractional year, which is all the arithmetic below needs."""
    year, month, day = point
    return year + (month - 1) / 12 + (day - 1) / 365.25


def _inner(span: dict[str, Any]) -> tuple[float | None, float | None]:
    """The span every reading of a spell certainly covers: latest start, earliest end."""
    return _bound(span.get("P580"), 1), _bound(span.get("P582"), 0)


def _bound(value: dict[str, Any] | None, side: int) -> float | None:
    """The first (0) or last (1) day a time value could mean, as a fractional year."""
    if not isinstance(value, dict):
        return None
    bounds = scope.interval(value.get("time", ""), value.get("precision", 0))
    return None if bounds is None else _point_years(bounds[side])


def _cohorts(spells: Sequence[OfficeSpell]) -> Counter[int]:
    """How many different people started the office in each year."""
    seen = {(spell.person, year) for spell in spells
            if (year := _year(spell.span.get("P580"))) is not None}
    return Counter(year for _person, year in seen)


def _concurrent(spells: Sequence[OfficeSpell]) -> bool:
    """Whether two people certainly held the office at once, for longer than a handover."""
    closed = [(spell.person, *_inner(spell.span)) for spell in spells]
    closed = [(p, s, e) for p, s, e in closed if s is not None and e is not None and s < e]
    margin = CONCURRENT_DAYS / 365.25
    return any(
        one != other and min(e1, e2) - max(s1, s2) > margin
        for one, s1, e1 in closed for other, s2, e2 in closed
    )


def seat_kind(position: dict[str, Any], spells: Sequence[OfficeSpell]) -> str | None:
    """Whether an office is one seat, a chamber's seat, or neither as far as anyone can tell.

    A chamber by its declared kind, or by a year in which `CHAMBER_COHORT`
    people took it up. One seat when nothing says otherwise: no kind of a
    many-seat office, no year with more than `SINGLE_SEAT_COHORT` starters,
    and no two people certainly holding it at once. Anything between --
    four deputies appointed in a year, a deputy ministry -- is neither, and
    neither rule below reads it. Cohorts count only the spells on record or
    on their way: an office's turbulent decades long past, which the policy
    has already set aside, say nothing about how many hold it now.
    """
    kinds = set(position.get("kind_qids") or ())
    cohorts = _cohorts([spell for spell in spells if spell.live])
    largest = max(cohorts.values(), default=0)
    if kinds & CHAMBER_KINDS or largest >= CHAMBER_COHORT:
        return "chamber"
    if kinds & MULTI_SEAT_KINDS or largest > SINGLE_SEAT_COHORT or _concurrent(spells):
        return None
    return "single"


def term_years(spells: Sequence[OfficeSpell]) -> int | None:
    """The length of one term of a chamber seat, measured off its closed spells.

    The modal length in whole years, because neither tail is a term: a member
    re-elected twice is one statement fifteen years long, and one appointed to
    fill a vacancy is a statement of months. Unmeasured, None, when there are
    fewer than `TERM_MIN_SPELLS` closed spells or fewer than `TERM_MIN_AGREE`
    of them on one length.
    """
    lengths: Counter[int] = Counter()
    seen = set()
    for spell in spells:
        start, end = _year(spell.span.get("P580")), _year(spell.span.get("P582"))
        if start is None or end is None or (spell.person, start, end) in seen:
            continue
        seen.add((spell.person, start, end))
        span = spell.span
        if min(span["P580"].get("precision", 0), span["P582"].get("precision", 0)) >= 10:
            first, last = _inner(span)
            length = round(last - first) if first is not None and last is not None else 0
        else:
            length = end - start
        if length > 0:
            lengths[length] += 1
    if sum(lengths.values()) < TERM_MIN_SPELLS or not lengths:
        return None
    (length, agree), *rest = lengths.most_common()
    if agree < TERM_MIN_AGREE or (rest and rest[0][1] == agree):
        return None
    return length


def _later(one: dict[str, Any], other: dict[str, Any]) -> bool:
    """Whether time `other` is certainly after time `one`: "2015" is not after "2015-05-03"."""
    mine, theirs = _bound(one, 1), _bound(other, 0)
    return mine is not None and theirs is not None and theirs > mine


def cabinet_seat(position: dict[str, Any]) -> bool:
    """Whether an office is a minister's seat, which a new government fills anew.

    Read off the labels of the item's own `P279` parents ("minister", "foreign
    minister", "deputy prime minister"); a deputy ministry or a minister of
    state is one of several seats and is left out.
    """
    if set(position.get("kind_qids") or ()) & MULTI_SEAT_KINDS:
        return False
    return any(kind.split()[-1:] == ["minister"] for kind in position.get("kinds") or ())


def open_superseded(case: Case) -> Disposition | None:
    """An open tenure somebody else's later one has evidently ended.

    Articles state a start and leave the end out for years after it came:
    a minister of a cabinet two governments ago, a senator of a chamber since
    dissolved. Written without `P582`, each says they hold the office today.
    For an office one person holds at a time (`seat_kind`), a later start by
    anybody else, on record or proposed, is the end the article did not give.
    For a chamber's seat, a new term of the chamber is: at least
    `NEW_TERM_COHORT` people taking up the seat in one year, that year at
    least a measured term (`term_years`) less `TERM_SLACK_YEARS` after the
    tenure began. A seat whose term cannot be measured is left alone, and so
    is everything between one seat and a chamber.

    First of all, an office that was abolished, or whose body was dissolved
    (`Case.dissolved`), after the tenure began and before today has nobody
    in it, whatever its holders' statements say: a senate that lapsed with
    every term in it. One dissolved *before* the tenure began says nothing
    here: a body re-formed under its old item is the case it would get wrong.

    A cabinet seat (`cabinet_seat`) open since before the current head of
    government took office belongs to an earlier government: a minister kept
    on is reappointed, and the article that has not caught up says
    "incumbent" of the cabinet before.
    """
    if case.property != "P39" or case.position is None:
        return None
    start = case.tenure("P580")
    if start is None or case.tenure("P582") is not None:
        return None
    today = case.today or date.today()
    ended = list(case.dissolved or [])
    abolished = case.position.get("abolished")
    if abolished is not None:
        ended.append({"time": f"+{abolished}T00:00:00Z", "precision": 11})
    for value in ended:
        if _later(start, value) and not _dated_after(value, today):
            return _skip("open_superseded/dissolved")
    if (case.government is not None and cabinet_seat(case.position)
            and _later(start, case.government)):
        return _skip("open_superseded/government")
    if case.office_spells is None:
        return None
    me = case.entity.get("id")
    kind = seat_kind(case.position, case.office_spells)
    live = [spell for spell in case.office_spells if spell.live and "P580" in spell.span]
    if kind == "single":
        if any(spell.person != me and _later(start, spell.span["P580"]) for spell in live):
            return _skip("open_superseded/single")
        return None
    if kind != "chamber":
        return None
    term = term_years(case.office_spells)
    began = _bound(start, 1)
    if term is None or began is None:
        return None
    gap = max(1, term - TERM_SLACK_YEARS)
    starters: dict[int, set[str]] = {}
    for spell in live:
        other = _bound(spell.span["P580"], 0)
        if other is not None and other - began >= gap:
            starters.setdefault(int(other), set()).add(spell.person)
    if any(len(people) >= NEW_TERM_COHORT for people in starters.values()):
        return _skip("open_superseded/chamber")
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
    review_rejected,
    extracted_out_of_scope,
    no_quote,
    future_date,
    # Per property, what the evidence has to be.
    minor_wiki_only,
    contested,
    refine_over_sourced,
    demonym_abroad,
    resolution_weak,
    other_polity,
    tenure_ended,
    open_unattested,
    undated_tenure,
    start_precision,
    # Before the tags and before `generic_needs_scope`: a listed class is
    # skipped as the class it is, not as `abstract` in one state, and not as a
    # placement waiting for a scoping qualifier that would never make it one
    # office. `generic_needs_scope` stays for the items a single state's
    # community uses with a qualifier, which this list leaves out.
    generic_office,
    office_rejected,
    recorded_elsewhere,
    generic_needs_scope,
    tenure_before_polity,
    tenure_before_record,
    open_superseded,
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


def office_spells(offices: Sequence[str]) -> dict[str, list[OfficeSpell]]:
    """Every spell of these offices: Wikidata's, read live, and the proposals'.

    A successor this run is about to write is as much a successor as one on
    record, so the proposals count; one the policy skipped measures the office
    -- its cohorts, its term -- and is not taken for a successor.
    """
    out: dict[str, list[OfficeSpell]] = {}
    for office, spells in positions.holder_spells(offices).items():
        out.setdefault(office, []).extend(OfficeSpell(person, span) for person, span in spells)
    if not offices:
        return out
    rows = db.conn().execute(
        "SELECT value->>'id', person_qid, qualifiers, status FROM proposal"
        " WHERE property = 'P39' AND value->>'id' = ANY(%s) AND status = ANY(%s)",
        (list(offices), [*LIVE_SPELL_STATUSES, SKIPPED]),
    )
    for office, person, qualifiers, status in rows:
        out.setdefault(office, []).append(OfficeSpell(
            person, _endpoints(qualifiers or {}), live=status in LIVE_SPELL_STATUSES,
        ))
    return out


def person_cases(
    qid: str, today: date | None = None,
    spells: dict[str, list[OfficeSpell]] | None = None,
    dissolved: dict[str, list[dict[str, Any]]] | None = None,
    governments: dict[str, dict[str, Any]] | None = None,
) -> list[tuple[int, Case]]:
    """Build a case for every proposal of one person the policy may decide.

    A row a human ruled on is theirs and is left out; so is a row that has
    gone out. Everything else is re-decided from scratch every time, which is
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
            " r.kind, r.confidence, r.qid AS office, r.jurisdiction,"
            " (SELECT v.decision FROM verdict v WHERE v.proposal_id = p.id"
            "  ORDER BY v.id DESC LIMIT 1) AS review"
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
                "jurisdiction": row["jurisdiction"],
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
            review=row["review"],
            siblings=siblings,
            office_spells=None if spells is None or row["property"] != "P39"
            else spells.get(row["value"].get("id"), []),
            dissolved=None if dissolved is None or row["property"] != "P39"
            else dissolved.get(row["value"].get("id"), []),
            government=(governments or {}).get(state_qid or ""),
            polities=polities_of(state_qid) if state_qid else {},
            today=today,
        )))
    # Spells are judged against each other only among the rows every other
    # rule lets through: a spell a rule has already set aside -- a rename the
    # reconciler was unsure of, a tenure before the polity -- is not going to
    # be written, and must not take a good sibling down with it. One rule's
    # skips stay in: a spell `open_superseded` found ended is still the
    # article's account of the tenure, and its twin on another item of the
    # same office is the same tenure, ended as surely.
    spells: dict[str, list[tuple[int, dict[str, Any]]]] = {}
    by_id = {pid: case for pid, case in out}
    for pid, case in out:
        found = decide(case) if case.property == "P39" else None
        if found is not None and (found.status != SKIPPED
                                  or found.rule.startswith(open_superseded.__name__)):
            spells.setdefault(case.value.get("id", ""), []).append((pid, case.qualifiers))
    for group in spells.values():
        for pid, conflict in spell_conflicts(group).items():
            by_id[pid].spell_conflict = conflict
    for pid, conflict in _family_conflicts_of(
        [(pid, by_id[pid]) for group in spells.values() for pid, _span in group], state_qid
    ).items():
        by_id[pid].spell_conflict = conflict
    return out


_POLITIES: dict[str, dict[str, list[str]]] = {}


def polities_of(state_qid: str) -> dict[str, list[str]]:
    """The state and its current first-level subdivisions, with their English names, read once."""
    if state_qid not in _POLITIES:
        state = wikidata.fetch_items([state_qid], props="claims").get(state_qid) or {}
        subs = [q for q in wikidata.claim_qids(state, "P150", include_deprecated=False)]
        items = wikidata.fetch_items([state_qid, *subs], props="labels|aliases")
        _POLITIES[state_qid] = {
            qid: [n for n in dict.fromkeys(
                [(e.get("labels", {}).get(lang) or {}).get("value") for lang in ("en", "mul")]) if n]
            for qid, e in items.items()
        }
    return _POLITIES[state_qid]


def state_office(position: dict[str, Any], state_qid: str | None) -> bool:
    """Whether an office is the state's own, by `P17` or by the `P1001` it governs."""
    return state_qid is not None and state_qid in (
        position.get("country_qid"), position.get("jurisdiction_qid"))


def _family_conflicts_of(cases: Sequence[tuple[int, Case]], state_qid: str | None) -> dict[int, str]:
    """`family_conflicts` over the surviving spells on the state's own offices.

    The names and the state's kind counts are read only when two spells on
    two items are in dispute at all, which for most people they are not.
    """
    live = [
        (pid, case.position, case.qualifiers) for pid, case in cases
        if case.spell_conflict is None and case.position is not None
        and state_office(case.position, state_qid)
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
    orgs = positions.organisations(kinds)
    for org, texts in positions.item_names(orgs).items():
        names.setdefault(org, texts)
    for qid, office in offices.items():
        office.setdefault("names", names.get(qid, []))
    return family_conflicts(live, use, names, orgs)


#: The prefix of `decided_by` on a row an audit took out. Not `DECIDER`, so the
#: policy never selects the row again.
AUDITOR = "audit:"
#: Rows whose edit is in flight: an audit waits until they have landed or failed.
UNAUDITABLE = ("sent",)
#: Rows already on Wikidata: an audit strikes them, which queues their removal.
LANDED = ("applied",)


def audit(ids: Sequence[int], reason: str, by: str, country: str) -> list[dict[str, Any]]:
    """Take proposals out of the write path after the fact, durably.

    For an observer who doubts rows the policy accepted: their SQL picks the
    ids, this records who decided and why. The row is `skipped` under
    `audit:<by>` and also carries a `reject` verdict, because a verdict is
    what `propose` keeps across a re-run -- a status alone was wiped by the
    next one. Every audited statement is also struck in the send ledger, so
    no line for it goes out again under another row; for a row already on
    Wikidata the strike is the point, since it queues the statement's removal
    (approved when the statement is provably only ours, proposed otherwise).
    There is no approve. All or nothing: an id that is unknown, of another
    country's run, or in flight refuses the whole call.
    """
    if not by.strip() or not reason.strip():
        raise ValueError("an audit names who skipped it and why")
    conn = db.conn()
    with conn.transaction(), conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            "SELECT p.id, p.person_qid, p.property, p.value, p.status, p.decided_by, p.claim_guid, pe.country"
            " FROM proposal p JOIN person pe ON pe.qid = p.person_qid"
            " WHERE p.id = ANY(%s) ORDER BY p.id FOR UPDATE OF p",
            (list(ids),),
        ).fetchall()
        found = {row["id"] for row in rows}
        problems = [f"#{ident}: no such proposal" for ident in ids if ident not in found]
        problems += [f"#{row['id']}: of {row['country']}'s run, not {country}'s"
                     for row in rows if row["country"] != country]
        problems += [f"#{row['id']}: {row['status']}, its edit is in flight"
                     for row in rows if row["status"] in UNAUDITABLE]
        if problems:
            raise ValueError("; ".join(problems))
        for row in rows:
            if row["status"] in LANDED:
                continue
            cur.execute(
                "INSERT INTO verdict (proposal_id, decision, reason, note, decided_by)"
                " VALUES (%s, 'reject', 'other', %s, %s)",
                (row["id"], reason, AUDITOR + by),
            )
            cur.execute(
                "UPDATE proposal SET proposed_status = coalesce(proposed_status, status),"
                " status = %s, decided_by = %s, decided_at = now() WHERE id = %s",
                (SKIPPED, AUDITOR + by, row["id"]),
            )
    _strike(rows, reason, by, country)
    return rows


def _strike(rows: list[dict[str, Any]], reason: str, by: str, country: str) -> None:
    """Strike each audited statement; a landed one sent before the ledger is proposed for removal by its id."""
    from peploop import ledger, qs  # qs imports plan, which imports this module

    for row in rows:
        value = qs.qs_value(row["value"])
        if value is None:
            continue
        queued = ledger.strike("peploop", row["person_qid"], row["property"], value, country, reason,
                               origin=AUDITOR + by, log=lambda _m: None)
        if row["status"] in LANDED and not queued and row.get("claim_guid"):
            ledger.propose_removal("peploop", row["claim_guid"], row["person_qid"], row["property"], value,
                                   country, reason, AUDITOR + by, ours=False)


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
        group = case.property
        self.entered[group] += 1
        self.decided[(group, disposition.rule)] += 1
        if case.property == "P39" and disposition.status in (PENDING, ACCEPTED):
            self.offices[case.value.get("id", "?")] += 1


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


def government_since(states: Sequence[str]) -> dict[str, dict[str, Any]]:
    """When each state's current head of government took office, read live.

    The office is the state's `P1313`; the start is that of its one open,
    dated spell. A state with no such office, or with none or several open,
    is left out, and its cabinet seats are judged by their own holders only.
    """
    heads: dict[str, list[str]] = {}
    for state, entity in wikidata.fetch_items(states, props="claims").items():
        heads[state] = wikidata.claim_qids(entity, "P1313", include_deprecated=False)
    held = positions.holder_spells([q for offices in heads.values() for q in offices])
    out: dict[str, dict[str, Any]] = {}
    for state, offices in heads.items():
        current = [span["P580"] for office in offices for _person, span in held.get(office, [])
                   if "P580" in span and "P582" not in span]
        if len(current) == 1:
            out[state] = current[0]
    return out


def run(qids: Sequence[str], write: bool, today: date | None = None) -> Funnel:
    """Decide every decidable proposal of these people, writing unless told not to.

    The one thing here that reaches the network: an office nobody has asked
    the first-holder question about is asked it once, so `tenure_before_record`
    reads a filled column rather than silence; and a state whose offices'
    kinds were never read has them read once, so `family_conflicts` counts the
    whole table rather than the part that happened to be loaded since. Every
    office's holders and dissolution, and each state's head of government,
    are read live once per run, for `open_superseded`.
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
    spells = office_spells(offices)
    dissolved = positions.dissolutions(offices)
    governments = government_since(states_of(qids))
    funnel = Funnel()
    for qid in qids:
        for proposal_id, case in person_cases(qid, today, spells, dissolved, governments):
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
