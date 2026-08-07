"""Score the engine against the statements Wikidata already has.

Reach for this before trusting a campaign's output. Most of a roster is people
whose spell is already written down — 789 of Spain's 1,052 rows already hold the
target and 900 have *something* on record to compare against — and the engine's
only use for them has been to skip them. But each one is a
**labelled example**: the roster says what the engine believes, the item says
what the community recorded, and comparing the two costs nothing, because the
person's statements were fetched for the identity gates anyway.

That comparison answers, per office, before a single edit is proposed:

* **did we pick the right item?** The Spanish Congress presidency turned out to
  be four items and the engine was about to add 21 statements to the wrong one.
  It was found because an unrelated rule misfired and a human noticed; the office
  scores 58% here without its era routing and 90% with it, which says the same
  thing without needing anyone to notice.
* **did we parse the dates right?** A parser defect shows up as conflicts
  confined to one page — which is how `"5 de julio del 2022"` was caught in
  Ecuador months after that campaign shipped.
* **is the tenure convention what the rules assume?** `interim_concurrent_office`
  fired 42 times in Spain and was wrong 42 times, and the `P2868` the acting
  rules add appears on 2 of the 88 target items measured so far.

This module only measures and reports. Nothing here decides a disposition:
thresholds belong in `wd/policy.py` once there is enough evidence to set one,
and the first thing that evidence has to survive is a human reading it.
"""

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

#: How a roster row relates to what the item already records for this office.
#: The distinctions are the whole value of the measurement: three of these five
#: are *agreement* written differently, and reading them all as "conflict" — the
#: first version of this module did — reports a healthy office at 24% and buries
#: the real defects.
SAME_TERM = "same_term"
#: The roster's spell sits inside a longer recorded one. The roster counts a
#: term per legislature, the item records one continuous tenure: Felipe
#: González is four roster rows and one statement from 1982 to 1996. Nothing is
#: wrong with either.
CONTAINED = "contained"
#: Boundaries within `NEAR_DAYS` — the gap between the decree and the swearing
#: in. Carlos Arias Navarro's roster row ends the day after his statement does.
NEAR = "near"
#: Recorded, but undated or at year/month precision where the roster has the day.
COARSER = "coarser"
#: Overlapping and genuinely disagreeing. This is the bucket that means a parser
#: defect, and keeping it small is what makes it worth reading.
CONFLICT = "conflict"
#: Not recorded at all, though the person holds the item for another spell.
DISJOINT = "disjoint"

#: A boundary disagreement no larger than this is a bookkeeping difference
#: between two sources, not a defect in either.
NEAR_DAYS = 7

#: Qualifier marking a spell someone was covering rather than holding.
ACTING = "P2868"


@dataclass(frozen=True)
class ExistingTerm:
    """One P39 statement already on the item, with what a comparison needs.

    `wd.campaign.dated_positions` deliberately keeps only day-precision bounds,
    because a coarser date cannot bracket a spell of a few weeks and every
    caller of it is asking about containment. A backtest asks a different
    question — *is this the same term* — and for that a year-precision start and
    a missing one are not the same thing at all.
    """

    position: str
    start: Optional[str] = None
    end: Optional[str] = None
    #: Precision of the start bound: 0 none, 9 year, 10 month, 11 day.
    precision: int = 0
    acting: bool = False
    rank: str = "normal"

    def covers(self, start: Optional[str], end: Optional[str]) -> bool:
        """Does this recorded term overlap the span the roster gives?"""
        if not start or not self.start:
            return False
        left, right = self.start, self.end
        return left <= (end or start) and (right is None or start <= right)


def existing_terms(entity: Dict[str, Any]) -> List[ExistingTerm]:
    """Every P39 on an item, as comparable terms. Reads claims, not the API."""
    out: List[ExistingTerm] = []
    for claim in entity.get("claims", {}).get("P39", []):
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        if not isinstance(value, dict) or "id" not in value:
            continue
        bounds: Dict[str, Tuple[str, int]] = {}
        for prop, key in (("P580", "start"), ("P582", "end")):
            for qualifier in claim.get("qualifiers", {}).get(prop, []):
                time_value = qualifier.get("datavalue", {}).get("value")
                if not isinstance(time_value, dict) or "time" not in time_value:
                    continue
                precision = time_value.get("precision", 0)
                if precision < 9:
                    continue  # a century renders as a misleading year
                width = {9: 4, 10: 7}.get(precision, 10)
                bounds[key] = (time_value["time"].lstrip("+")[:width], precision)
        start, start_precision = bounds.get("start", (None, 0))
        end, _ = bounds.get("end", (None, 0))
        out.append(
            ExistingTerm(
                position=value["id"],
                start=start,
                end=end,
                precision=start_precision,
                acting=bool(claim.get("qualifiers", {}).get(ACTING)),
                rank=claim.get("rank", "normal"),
            )
        )
    return out


@dataclass(frozen=True)
class Comparison:
    """What the engine would have said about a row already on record."""

    campaign: str
    office: str
    qid: str
    label: str
    #: The item `target_for` routed this row to.
    target_chosen: str
    #: The item the community actually used for this spell, if any.
    target_actual: Optional[str]
    row_start: Optional[str] = None
    row_end: Optional[str] = None
    recorded_start: Optional[str] = None
    recorded_end: Optional[str] = None
    verdict: str = DISJOINT
    acting_predicted: bool = False
    acting_recorded: bool = False
    period_raw: str = ""
    #: The recorded term shares a boundary with the roster row. What separates
    #: "the same appointment written down under another item" from "a seat in
    #: parliament that happens to span these years".
    boundary_match: bool = False

    @property
    def target_agrees(self) -> bool:
        return self.target_actual == self.target_chosen

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v not in (None, "", False)}


def _same_span(
    row_start: Optional[str], row_end: Optional[str], term: ExistingTerm
) -> bool:
    """Equal at the coarser of the two precisions.

    A recorded year-precision start is not *wrong* about a day-precision roster
    row; it is the same term, less precisely written down, and counting it as a
    mismatch would report every well-curated pre-1900 office as a parser defect.
    """
    if not row_start or not term.start:
        return False
    width = {9: 4, 10: 7}.get(term.precision, 10)
    if row_start[:width] != term.start[:width]:
        return False
    if term.end is None:
        return row_end is None
    return bool(row_end) and row_end[:width] == term.end[:width]


def _pad(value: Optional[str], high: bool) -> Optional[str]:
    """A partial ISO date as its earliest or latest day, for span arithmetic."""
    if not value:
        return None
    if len(value) == 4:
        return f"{value}-12-31" if high else f"{value}-01-01"
    if len(value) == 7:
        return f"{value}-28" if high else f"{value}-01"
    return value


def _days_apart(left: Optional[str], right: Optional[str]) -> Optional[int]:
    if not left or not right or len(left) != 10 or len(right) != 10:
        return None
    try:
        return abs((date.fromisoformat(left) - date.fromisoformat(right)).days)
    except ValueError:
        return None


def _verdict(
    row_start: Optional[str], row_end: Optional[str], on_target: Sequence[ExistingTerm]
) -> str:
    """How the roster's spell relates to what this item already records.

    Ordered from the strongest agreement down, and every branch above `CONFLICT`
    exists because the first version of this function put a well-curated office
    in that bucket: exact match, the item recording one tenure where the roster
    counts legislatures, a boundary a day out, and a coarser recorded date are
    four ways of agreeing.
    """
    if not on_target:
        return DISJOINT
    if any(_same_span(row_start, row_end, t) for t in on_target):
        return SAME_TERM
    low, high = _pad(row_start, False), _pad(row_end or row_start, True)
    for term in on_target:
        term_low, term_high = _pad(term.start, False), _pad(term.end, True)
        if low and term_low and low >= term_low and (
            term_high is None or (high and high <= term_high)
        ):
            return CONTAINED
    for term in on_target:
        starts = _days_apart(row_start, term.start)
        ends = _days_apart(row_end, term.end)
        if starts is not None and starts <= NEAR_DAYS and (
            ends is None or ends <= NEAR_DAYS
        ):
            return NEAR
    if any(not t.start or t.precision < 11 for t in on_target):
        return COARSER
    if any(t.covers(row_start, row_end) for t in on_target):
        return CONFLICT
    return DISJOINT


def compare(
    *, campaign: str, office: str, qid: str, label: str, target: str,
    row_start: Optional[str], row_end: Optional[str], period_raw: str,
    terms: Sequence[ExistingTerm], acting_predicted: bool = False,
) -> Comparison:
    """One roster row against everything the item already records.

    `target_actual` is the item the community used for *this spell*, chosen
    across every position on the item rather than only the one this office
    names — that is the whole point, since the office may be several items and
    the engine may have picked the wrong one.
    """
    overlapping = [t for t in terms if t.covers(row_start, row_end)]
    exact = [t for t in overlapping if _same_span(row_start, row_end, t)]
    best = (exact or overlapping or [None])[0]
    # Prefer an overlap on the chosen target when there is one either way, so a
    # person holding two offices at once does not read as a routing error.
    for candidate in exact or overlapping:
        if candidate.position == target:
            best = candidate
            break

    on_target = [t for t in terms if t.position == target]
    verdict = _verdict(row_start, row_end, on_target)

    return Comparison(
        campaign=campaign, office=office, qid=qid, label=label,
        target_chosen=target,
        target_actual=best.position if best else None,
        row_start=row_start, row_end=row_end,
        recorded_start=best.start if best else None,
        recorded_end=best.end if best else None,
        verdict=verdict,
        acting_predicted=acting_predicted,
        acting_recorded=bool(best and best.acting),
        period_raw=period_raw,
        boundary_match=bool(best and _shares_boundary(row_start, row_end, best)),
    )


def _shares_boundary(
    row_start: Optional[str], row_end: Optional[str], term: ExistingTerm
) -> bool:
    """Does the recorded term begin or end where the roster row does?

    Two records of one appointment nearly always agree on a boundary even when
    they disagree about the other end — Moscoso's 1821 presidency is recorded as
    ending on the 21st where the roster says the 30th, but both start on 1 June.
    A parliamentary seat that merely spans the same years agrees on neither, and
    that is what keeps it out of the office's item family.
    """
    width = {9: 4, 10: 7}.get(term.precision, 10)
    if row_start and term.start and row_start[:width] == term.start[:width]:
        return True
    return bool(row_end and term.end and row_end[:width] == term.end[:width])


@dataclass
class Score:
    """One office's agreement with the record, in the three axes that matter."""

    office: str
    rows: int = 0
    target_checked: int = 0
    target_agree: int = 0
    date_checked: int = 0
    date_agree: int = 0
    date_contained: int = 0
    date_near: int = 0
    date_coarser: int = 0
    date_conflict: int = 0
    #: The spell is recorded, but under an item outside this office's family —
    #: a concurrent seat in parliament, a head-of-state title. Reported, never
    #: counted as a routing error.
    other_office: int = 0
    acting_checked: int = 0
    acting_agree: int = 0
    #: Roster spells the item does not record at all, though it records another
    #: spell in the same office — what the person-level `held` skip is costing.
    disjoint: int = 0
    #: Items the cohort actually uses for this office, most-used first.
    family: List[Tuple[str, int]] = field(default_factory=list)
    #: The items target agreement was measured against — this office's own.
    verified: List[str] = field(default_factory=list)

    def _share(self, agree: int, checked: int) -> Optional[float]:
        return agree / checked if checked else None

    @property
    def target_rate(self) -> Optional[float]:
        return self._share(self.target_agree, self.target_checked)

    @property
    def date_rate(self) -> Optional[float]:
        """Share of comparable rows that do *not* contradict the record.

        Deliberately not "share that match exactly". An office whose statements
        were written at year precision is not misparsed, and neither is one whose
        item records a single tenure where the roster counts legislatures —
        scoring those as disagreement put Ecuador's foreign ministry at 59% with
        one genuine defect in thirty-one rows, and a number that cries wolf is a
        number nobody reads.
        """
        return self._share(self.date_checked - self.date_conflict, self.date_checked)

    @property
    def acting_rate(self) -> Optional[float]:
        return self._share(self.acting_agree, self.acting_checked)


def score(
    office: str, comparisons: Sequence[Comparison], family: Sequence[str] = ()
) -> Score:
    """Aggregate one office's comparisons.

    `family` is the set of items that *are* this office — its declared targets
    plus whatever the cohort revealed and `verify_family` accepted. Target
    agreement is measured against those alone, because the alternative measures
    something else entirely: a nineteenth-century Congress president also held a
    seat in that Congress, and scoring the presidency against the seat reports a
    routing error where there is only a person with two offices.
    """
    result = Score(office=office, rows=len(comparisons))
    known = set(family)
    counts: Dict[str, int] = {}
    for comparison in comparisons:
        actual = comparison.target_actual
        if actual:
            counts[actual] = counts.get(actual, 0) + 1
            if actual in known or actual == comparison.target_chosen:
                result.target_checked += 1
                result.target_agree += int(comparison.target_agrees)
            else:
                result.other_office += 1
        bucket = {
            SAME_TERM: "date_agree",
            CONTAINED: "date_contained",
            NEAR: "date_near",
            COARSER: "date_coarser",
            CONFLICT: "date_conflict",
        }.get(comparison.verdict)
        if bucket:
            result.date_checked += 1
            setattr(result, bucket, getattr(result, bucket) + 1)
        else:
            result.disjoint += 1
        # Only the rows where either side says "acting" carry information; the
        # overwhelming majority say neither and would drown the rate.
        if comparison.acting_predicted or comparison.acting_recorded:
            result.acting_checked += 1
            result.acting_agree += int(
                comparison.acting_predicted == comparison.acting_recorded
            )
    result.family = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    result.verified = sorted(known)
    return result


def observed_family(
    comparisons: Sequence[Comparison],
    exclude: Sequence[str] = (),
    floor: int = 2,
) -> List[Tuple[str, int]]:
    """Items the cohort uses for this office, beyond the ones anyone declared.

    An office's item family is a fact about the data, not about the profile:
    `already_under_sibling` could only see Q45213921 in Spain because a human
    had already found it and written it into `date_targets`. Two independent
    *people* recording a spell this roster also describes, under one item, and
    agreeing with the roster about when it began or ended, is enough to call it
    the same office.

    Both conditions are load-bearing. Without the boundary test a minister's
    parliamentary seat — which overlaps every ministry they ever held — joins the
    family and the sibling check then suppresses genuine statements; `exclude`
    is the second guard, and takes the campaign's `concurrency_ignore` plus the
    items other offices in the same campaign own.
    """
    people: Dict[str, set] = {}
    for comparison in comparisons:
        item = comparison.target_actual
        if not item or item in set(exclude) or not comparison.boundary_match:
            continue
        people.setdefault(item, set()).add(comparison.qid)
    return sorted(
        ((qid, len(holders)) for qid, holders in people.items() if len(holders) >= floor),
        key=lambda kv: (-kv[1], kv[0]),
    )


#: Words that say what *kind* of office an item is, not which one. Two labels
#: sharing only these are not the same office: "President of the Council of
#: Ministers" and "Minister of State of Spain" have nothing in common but the
#: word for a government job, and treating them as one item family suppressed
#: four genuine statements the first time this ran.
OFFICE_WORDS = {
    "minister", "ministers", "ministry", "ministro", "ministros", "ministra",
    "ministras", "ministre", "ministr", "secretary", "secretario", "secretaria",
    "president", "presidente", "presidenta", "presidents", "chairman", "chair",
    "head", "chief", "judge", "member", "deputy", "vice", "general", "office",
    "position", "government", "gobierno", "state", "estado", "national",
    "nacional", "republic", "republica", "federal", "the", "of", "de", "del",
    "la", "las", "los", "el", "and", "y", "for", "in", "a", "an", "to",
}


def shares_office_word(left: str, right: str) -> bool:
    """Do two office labels name the *same* office rather than the same kind?

    The distinguishing word is the portfolio or the body — "congress",
    "deputies", "justice", "senate" — so a shared word that only says "this is a
    government job" does not count. Used to decide whether an item the cohort
    turned out to be using belongs to the office's family or is a second office
    its holders happened to hold on the same day.
    """
    def words(label: str) -> set:
        cleaned = "".join(c.lower() if c.isalnum() else " " for c in label)
        return {w for w in cleaned.split() if len(w) > 2 and w not in OFFICE_WORDS}

    return bool(words(left) & words(right))


def _pct(value: Optional[float]) -> str:
    return "—" if value is None else f"{value * 100:.0f}%"


def report(
    scores: Sequence[Score], comparisons: Sequence[Comparison], examples: int = 6
) -> List[str]:
    """The audit section: a table, then the disagreements worth reading.

    Printed whether or not anything reads the numbers, on the same principle as
    the precedent census — a measurement that could flip a decision has to show
    its working.
    """
    if not scores:
        return []
    lines = [
        "## Backtest against statements Wikidata already has",
        "",
        "Rows whose person already holds the target: what the engine would have "
        "said about them, against what the community recorded. Low target "
        "agreement means the office is several items and the routing is guessing; "
        "low date agreement on one office means its roster is misparsed.",
        "",
        "| office | on record | target agreement | date agreement | exact | "
        "contained | near | coarser | **conflict** | acting | other office | "
        "unrecorded |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for item in scores:
        lines.append(
            f"| {item.office} | {item.rows} "
            f"| {_pct(item.target_rate)} ({item.target_agree}/{item.target_checked}) "
            f"| {_pct(item.date_rate)} ({item.date_checked - item.date_conflict}"
            f"/{item.date_checked}) "
            f"| {item.date_agree} | {item.date_contained} | {item.date_near} "
            f"| {item.date_coarser} | **{item.date_conflict}** "
            f"| {_pct(item.acting_rate)} ({item.acting_agree}/{item.acting_checked}) "
            f"| {item.other_office} | {item.disjoint} |"
        )
    lines.append("")

    known = {qid for item in scores for qid in item.verified}
    wrong_target = [
        c for c in comparisons
        if c.target_actual and not c.target_agrees and c.target_actual in known
    ]
    if wrong_target:
        lines.append(
            f"**{len(wrong_target)} rows are recorded under a different item than "
            "this office would have chosen** — the strongest signal that an office "
            "is a family of items:"
        )
        for comparison in wrong_target[:examples]:
            lines.append(
                f"* {comparison.qid} {comparison.label} ({comparison.office}): "
                f"chose {comparison.target_chosen}, recorded as "
                f"{comparison.target_actual} for {comparison.row_start}–"
                f"{comparison.row_end or ''}"
            )
        if len(wrong_target) > examples:
            lines.append(f"* … and {len(wrong_target) - examples} more")
        lines.append("")

    unqualified = [
        c for c in comparisons if c.acting_predicted and not c.acting_recorded
    ]
    if unqualified:
        lines.append(
            f"**{len(unqualified)} spells the roster marks acting are recorded "
            "without `P2868`** — check the precedent census below for how often "
            "these items use that qualifier at all: where the answer is never, the "
            "rule that adds it is inventing a convention rather than following "
            "one, and that is a ruling for a human:"
        )
        for comparison in unqualified[:examples]:
            lines.append(
                f"* {comparison.qid} {comparison.label} ({comparison.office}): "
                f"{comparison.row_start}–{comparison.row_end or ''} recorded on "
                f"{comparison.target_actual} with no qualifier"
            )
        if len(unqualified) > examples:
            lines.append(f"* … and {len(unqualified) - examples} more")
        lines.append("")

    # Both boundaries wrong is a parse error; one boundary wrong is usually a
    # stale or coarser statement, so the parse suspects go first.
    conflicts = sorted(
        (c for c in comparisons if c.verdict == CONFLICT),
        key=lambda c: c.boundary_match,
    )
    if conflicts:
        lines.append(
            f"**{len(conflicts)} rows overlap a recorded term but disagree about its "
            "dates** — a parser defect, or the roster and the item disagree:"
        )
        for comparison in conflicts[:examples]:
            lines.append(
                f"* {comparison.qid} {comparison.label} ({comparison.office}): "
                f"roster {comparison.row_start}–{comparison.row_end or ''} "
                f"({comparison.period_raw}), recorded {comparison.recorded_start}–"
                f"{comparison.recorded_end or ''}"
            )
        if len(conflicts) > examples:
            lines.append(f"* … and {len(conflicts) - examples} more")
        lines.append("")

    disjoint = [c for c in comparisons if c.verdict == DISJOINT]
    if disjoint:
        lines.append(
            f"**{len(disjoint)} roster spells are not recorded at all**, though the "
            "person holds the item for some other spell — these are dropped today "
            "by the person-level `already holds` check, not decided:"
        )
        for comparison in disjoint[:examples]:
            lines.append(
                f"* {comparison.qid} {comparison.label} ({comparison.office}): "
                f"{comparison.row_start}–{comparison.row_end or ''} "
                f"({comparison.period_raw})"
            )
        if len(disjoint) > examples:
            lines.append(f"* … and {len(disjoint) - examples} more")
        lines.append("")
    return lines


def dump(comparisons: Iterable[Comparison], path: Path) -> None:
    """Write the comparisons as JSONL, outside `verdicts/`.

    Deliberately not a `Record`: these are measurements, not decisions, and
    several hundred per campaign in the verdict directory would swamp the review
    document and fill the regression diff with churn.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(c.to_dict(), sort_keys=True, ensure_ascii=False) + "\n"
            for c in comparisons
        )
    )


__all__ = [
    "ACTING", "COARSER", "CONFLICT", "DISJOINT", "SAME_TERM",
    "Comparison", "ExistingTerm", "Score",
    "compare", "dump", "existing_terms", "observed_family", "report", "score",
]
