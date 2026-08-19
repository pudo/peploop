"""Score a person item against how Wikidata models a human being.

The sibling of `wd/shape.py`, and the half a roster lane actually writes to. A
P39 statement is only worth adding if the item carrying it is a well-formed
person: typed `Q5`, named, dated, and placed. `recipes/person_items.md` is the
method; this module is its checker.

Three answers, kept apart on purpose and never mixed:

- **`defects`** — Wikidata modelling errors. An item typed both human and
  position, a person with no name in any language, a death date before the
  birth date. Worth fixing whether or not a consumer notices.
- **`gaps`** — properties a person item should carry and does not: `P569`
  birth date, `P21` gender, `P27` citizenship. Not errors. They are the data
  entry a campaign can do, and each one is measured so a lane can be sized.
- **`os_notes`** — what the OpenSanctions PEP build currently makes of the
  item. Never defects: an item can be modelled perfectly and still not be
  emitted, and bending the record to make it emit is how you corrupt the data
  while appearing to improve it.

The note worth reading twice is `no_occupancy`. `wd_peps` passes
`no_end_implies_current=False`, so a tenure with no `P580`/`P582` and a person
with no `P569`/`P570` gives `positions.py:204-214` no date to reason about and
the Occupancy is refused — the person is never emitted, and neither is the
position, for want of a holder. **A birth date is what rescues an undated
tenure**, which is a much sharper reason to run a birthdate lane than
completeness. Citizenship, by contrast, gates nothing at all: unlike a
position, a person needs no country to be emitted.

The consumer half is a port of `zavod/zavod/shed/wikidata/human.py`,
`zavod/zavod/stateful/positions.py` and the `_wikidata/peps` crawler, cited per
constant, because it is a reading of someone else's code and will drift.
`strict=True` (the `_wikidata/categories` crawler) is modelled but off by
default: `wd_peps` is the dataset every campaign here writes into, and it calls
with `strict=False`.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from rigour.dates import ended_before, starts_after

from wd.api import claim_qids, fetch_entities
from wd.shape import type_closure

#: `human.py:19`. The type closure over P31/P279 must reach this or the item is
#: not a person. The holder query below asks for something stricter.
HUMAN_TYPE = "Q5"

#: `human.py:21-24`. Two closures that drop a person who otherwise passes. The
#: position one is also a modelling defect in its own right: an item typed both
#: `Q5` and `Q4164871` conflates an office with whoever holds it, and every P39
#: statement written onto it is written onto the wrong kind of thing.
POSITION_TYPE = "Q4164871"
FICTIONAL_TYPE = "Q95074"

#: `human.py:10`. Hand-maintained upstream; a single QID today.
BLOCKED_PERSONS: Set[str] = {"Q1045488"}

#: `followthemoney/types/date.py:35` via `value.py:50`. A birth date before this
#: drops the person outright — the PEP build has no interest in the 19th century.
RELEVANCE_MIN = "1900-01-01"

#: `followthemoney/types/date.py:31`. What `value.py` renders a BC date, or any
#: pre-1900 date too coarse to be a year, as. It sorts below `RELEVANCE_MIN`, so
#: it reaches the same drop.
HISTORIC = "1001-01-01"

#: `value.py:52` and `:57`. **A date coarser than a year is not a date.** A
#: decade- or century-precision `P569` after 1900 renders as `None`: it is
#: neither read as a birth date nor counted as a date signal, so it cannot
#: rescue an undated tenure. The item looks dated to anyone reading it and is
#: not, which is why `coarse_birth_date` is a gap of its own and not folded into
#: `no_birth_date`. Wikidata's precision codes: 11 day, 10 month, 9 year.
MIN_PRECISION = 9
PRECISION_LEN: Dict[int, int] = {11: 10, 10: 7, 9: 4}

#: `positions.py:17-24`. All of these are `n * 365` days, not calendar years.
YEAR_DAYS = 365
#: `human.py:35`, and again `positions.py:23` as `MAX_AGE`. Both drop the person.
MAX_AGE = timedelta(days=110 * YEAR_DAYS)
#: `human.py:34`, `strict` only: a birth date inside this drops the person.
MIN_AGE = timedelta(days=18 * YEAR_DAYS)
#: `positions.py:22`. Dead longer than this and no Occupancy is produced at all.
AFTER_DEATH = timedelta(days=5 * YEAR_DAYS)
#: `positions.py:24`. An open-ended tenure that started longer ago than this is
#: read as a record nobody closed, not as a 40-year incumbency.
MAX_OFFICE = timedelta(days=40 * YEAR_DAYS)
#: `positions.py:18-21`, keyed by the *position's* topics — which is why a
#: verdict needs the office's topics from `wd/shape.py` to be exact.
DEFAULT_AFTER_OFFICE = timedelta(days=5 * YEAR_DAYS)
EXTENDED_AFTER_OFFICE = timedelta(days=20 * YEAR_DAYS)
NO_EXPIRATION = timedelta(days=50 * YEAR_DAYS)

#: `human.py:71`. Only consulted when `P27` yields nothing, and only to fill
#: `country` — never `citizenship`. None of it is a gate; it is the difference
#: between a person the matcher can place and one it cannot.
COUNTRY_FALLBACKS: Tuple[str, ...] = ("P1001", "P17", "P19", "P945", "P495", "P937")

#: Never read by `zavod`. `P21` appears nowhere in the crawl path — the only
#: code that touches it is `nomenklatura/wikidata/propose.py:163`, which pushes
#: OpenSanctions' gender *to* Wikidata. It is a gap here because Wikidata wants
#: it on a person item, not because anything downstream would notice.
GENDER_PROP = "P21"


def get_after_office(topics: Set[str]) -> timedelta:
    """How long after leaving office a holder stays a PEP. `positions.py:146`."""
    if "gov.national" in topics:
        if "gov.head" in topics:
            return NO_EXPIRATION
        return EXTENDED_AFTER_OFFICE
    if "gov.igo" in topics or "role.diplo" in topics:
        return EXTENDED_AFTER_OFFICE
    return DEFAULT_AFTER_OFFICE


def wd_time(value: Dict[str, Any]) -> Optional[str]:
    """Render a Wikidata time value the way `nomenklatura` does, or `None`.

    Reach for this rather than slicing the `time` string: the precision floor,
    the BC sentinel and the January-1st truncation below each change what the
    crawler compares against its cutoffs, so a raw read reports dates the build
    never saw. Mirrors `nomenklatura/wikidata/value.py:snak_value_to_string`.
    """
    raw = value.get("time")
    precision = value.get("precision")
    if not isinstance(raw, str) or not isinstance(precision, int):
        return None
    sign, time = raw[0], raw.strip("+-")
    if sign == "-":
        return HISTORIC
    if precision < MIN_PRECISION:
        # After 1900 an imprecise date is discarded; before it, the date is old
        # enough that the sentinel reaches the same answer.
        return None if time > RELEVANCE_MIN else HISTORIC
    time = time[: PRECISION_LEN.get(precision, 10)]
    # `value.py:65`: bots write Jan 1 for year-precision dates, so a day-precise
    # January 1st is read back as a year.
    if time.endswith("-01-01"):
        time = time[:4]
    return max(HISTORIC, time)


def claim_times(entity: Dict[str, Any], prop: str) -> List[Optional[str]]:
    """Every rendered value of a time property, deprecated statements excluded.

    Keeps the `None`s: `human.py:37` skips an unrenderable date rather than
    dropping the person, so "has a P569" and "has a usable P569" are different
    numbers and the gap between them is the finding.
    """
    out: List[Optional[str]] = []
    for claim in entity.get("claims", {}).get(prop, []):
        if claim.get("rank") == "deprecated":
            continue
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(value, dict):
            out.append(wd_time(value))
    return out


def _qualifier_time(claim: Dict[str, Any], prop: str) -> Optional[str]:
    """A claim's time qualifiers, reduced as `position.py:351-366` reduces them."""
    values: List[str] = []
    for snak in claim.get("qualifiers", {}).get(prop, []):
        value = snak.get("datavalue", {}).get("value")
        if isinstance(value, dict):
            text = wd_time(value)
            if text is not None:
                values.append(text)
    if not values:
        return None
    return min(values) if prop == "P580" else max(values)


def best_name(entity: Dict[str, Any]) -> Optional[str]:
    """The name that would reach a Person entity, or `None` if none would.

    Not `wd.api.best_label`, which answers "what should a report print". This
    answers "does any name reach the entity at all", a much lower bar: the
    preferred languages first, then any language, then aliases, and
    `rigour.names.is_name` asks only for one letter in any script. A `None` here
    means the item has no label and no alias anywhere.
    """
    from nomenklatura.wikidata.lang import PREFERRED_WD_LANGS
    from nomenklatura.wikidata.value import clean_wikidata_name

    for source in ("labels", "aliases"):
        values = entity.get(source, {})
        ordered = [values[lang] for lang in PREFERRED_WD_LANGS if lang in values]
        ordered += [v for lang, v in values.items() if lang not in PREFERRED_WD_LANGS]
        for value in ordered:
            for text in value if isinstance(value, list) else [value]:
                cleaned = clean_wikidata_name(text.get("value", ""))
                if cleaned:
                    return cleaned
    return None


@dataclass
class Tenure:
    """One P39 statement, and what the PEP build makes of it.

    `dropped` names the rule that refused the Occupancy, and is the only part
    worth acting on: `no_dates` is fixable with a birth date, `after_office` and
    `long_dead` are correct answers about someone who stopped being a PEP.
    """

    position: str
    start: Optional[str] = None
    end: Optional[str] = None
    status: Optional[str] = None
    dropped: Optional[str] = None

    @property
    def emitted(self) -> bool:
        return self.dropped is None


@dataclass
class Verdict:
    """How well one person item is modelled, and what a reader makes of it.

    `defects` are Wikidata modelling errors, `gaps` are properties a person item
    should carry and does not, and `os_notes` are observations about a
    downstream consumer that are never either — see the module docstring.
    """

    qid: str
    label: Optional[str] = None
    #: `P31 = Q5` present as a best-rank, un-ended claim. Stricter than the
    #: closure below, and separately reported because the holder query is `wdt:`.
    truthy_human: bool = False
    #: `Q5` anywhere in the P31/P279 closure, which is what `human.py:19` reads.
    closure_human: bool = False
    also_position: bool = False
    fictional: bool = False
    blocked: bool = False
    name: Optional[str] = None
    #: Rendered `P569`/`P570` values, `None` for each one too coarse to count.
    birth_dates: List[Optional[str]] = field(default_factory=list)
    death_dates: List[Optional[str]] = field(default_factory=list)
    citizenship: List[str] = field(default_factory=list)
    country_via: Optional[str] = None
    gender: Optional[str] = None
    #: One entry per non-deprecated P39 claim that names an item — restricted
    #: to `accepted` positions when the caller passed a set.
    tenures: List[Tenure] = field(default_factory=list)
    #: P39 claims `accepted` filtered out. What separates "holds no office" from
    #: "holds none this audit scoped", which are very different findings.
    out_of_scope: int = 0
    #: Wikidata modelling errors: `not_a_human`, `also_position`, `no_name`,
    #: `q5_not_best_rank`, `death_before_birth`, `future_birth`.
    defects: List[str] = field(default_factory=list)
    #: Missing recommended properties: `no_birth_date`, `coarse_birth_date`,
    #: `no_gender`, `no_citizenship`.
    gaps: List[str] = field(default_factory=list)
    #: The consumer's date notes. Set by `verify`, which is where the run time
    #: and `strict` live; `os_notes` splices them in at the right position.
    date_notes: List[str] = field(default_factory=list)

    @property
    def well_modelled(self) -> bool:
        return not self.defects

    @property
    def complete(self) -> bool:
        """Every property `recipes/person_items.md` asks for is on the item."""
        return not self.defects and not self.gaps

    @property
    def birth_date(self) -> Optional[str]:
        return max((d for d in self.birth_dates if d), default=None)

    @property
    def death_date(self) -> Optional[str]:
        return max((d for d in self.death_dates if d), default=None)

    @property
    def emitted(self) -> bool:
        """Whether the OpenSanctions PEP build produces this person at all."""
        return not self.os_notes

    @property
    def dob_would_rescue(self) -> bool:
        """A birth date, and only a birth date, would make this person emittable.

        The finding that justifies a birthdate lane on its own: every tenure was
        refused for `no_dates`, so one `P569` turns the whole set into
        occupancies. The inverse — `dob_carries` — is the same people one edit
        earlier, and is what a lane must not regress.
        """
        return (
            bool(self.tenures)
            and self.birth_date is None
            and all(t.dropped == "no_dates" for t in self.tenures)
            and not [n for n in self.os_notes if n != "no_occupancy"]
        )

    @property
    def dob_carries(self) -> bool:
        """The person is emitted *only* because they have a birth date."""
        return (
            self.emitted
            and self.birth_date is not None
            and self.death_date is None
            and all(t.start is None and t.end is None for t in self.tenures)
        )

    @property
    def os_notes(self) -> List[str]:
        """What the OpenSanctions PEP build currently makes of this item.

        Ordered as the crawl applies them — reached, built, emitted — because
        that is the order to read a disagreement in. `unreachable` is the
        sharpest: the holder query is truthy, so a person whose `Q5` sits behind
        a preferred value or is deprecated is never fetched at all, however well
        the rest of the item reads.
        """
        notes: List[str] = []
        if not self.truthy_human:
            notes.append("unreachable")
        if self.blocked:
            notes.append("blocked")
        if not self.closure_human:
            notes.append("not_human")
        if self.also_position:
            notes.append("also_position")
        if self.fictional:
            notes.append("fictional")
        notes.extend(self.date_notes)
        if self.tenures and not any(t.emitted for t in self.tenures):
            # `crawler.py:216` — the person is emitted only alongside an
            # occupancy, so every refused tenure is a person who vanishes too.
            notes.append("no_occupancy")
        if not self.tenures:
            # Distinguished on purpose. `no_accepted_tenures` is a statement
            # about the *scope* this audit ran with, not about the person, and
            # it is the expected disagreement when OpenSanctions carries them
            # anyway: the review layer rescues positions whose honest parent
            # leaves the PEP default off, and this repo cannot read it.
            notes.append(
                "no_accepted_tenures" if self.out_of_scope else "no_tenures"
            )
        return notes

    def as_dict(self) -> Dict[str, Any]:
        return {
            "qid": self.qid, "label": self.label, "name": self.name,
            "truthy_human": self.truthy_human,
            "closure_human": self.closure_human,
            "also_position": self.also_position, "fictional": self.fictional,
            "birth_date": self.birth_date, "death_date": self.death_date,
            "citizenship": self.citizenship, "country_via": self.country_via,
            "gender": self.gender,
            "tenures": [
                {"position": t.position, "start": t.start, "end": t.end,
                 "status": t.status, "dropped": t.dropped}
                for t in self.tenures
            ],
            "out_of_scope": self.out_of_scope,
            "defects": self.defects, "gaps": self.gaps,
            "well_modelled": self.well_modelled, "complete": self.complete,
            "os_notes": self.os_notes, "emitted": self.emitted,
            "dob_would_rescue": self.dob_would_rescue,
            "dob_carries": self.dob_carries,
        }


def occupancy_status(
    tenure: Tenure,
    birth_date: Optional[str],
    death_date: Optional[str],
    topics: Set[str],
    dissolution: Optional[str] = None,
    now: Optional[datetime] = None,
) -> Optional[str]:
    """`zavod`'s Occupancy verdict for one tenure, or `None` if it is refused.

    Sets `tenure.dropped` to the rule that refused it. `no_end_implies_current`
    is hard-coded `False` because that is what `position.py:375` passes, and it
    is the reason the `no_dates` branch below fires as often as it does.
    Mirrors `zavod/zavod/stateful/positions.py:occupancy_status`.
    """
    now = now or datetime.now(timezone.utc)
    if death_date is not None and ended_before(death_date, now - AFTER_DEATH):
        tenure.dropped = "long_dead"
        return None
    if birth_date is not None and ended_before(birth_date, now - MAX_AGE):
        tenure.dropped = "implausibly_old"
        return None
    died = death_date is not None and not starts_after(death_date, now)

    if not (death_date or birth_date or tenure.start or tenure.end):
        # `positions.py:204-214`. The gate nobody expects: with no date anywhere
        # on the person or the statement, and a source that does not promise to
        # close its records, there is nothing to judge and nothing is emitted.
        tenure.dropped = "no_dates"
        return None

    after_office = get_after_office(topics)
    if tenure.end is not None:
        if ended_before(tenure.end, now):
            if ended_before(tenure.end, now - after_office):
                tenure.dropped = "after_office"
                return None
            return "ended"
        return "ended" if died else "current"

    if dissolution is not None and ended_before(dissolution, now):
        if ended_before(dissolution, now - after_office):
            tenure.dropped = "position_dissolved"
            return None
        return "ended"

    if tenure.start is not None and ended_before(tenure.start, now - MAX_OFFICE):
        tenure.dropped = "max_office"
        return None
    if died:
        return "ended"
    return "unknown"


def verify(
    entity: Dict[str, Any],
    closure: Set[str],
    topics: Optional[Dict[str, Set[str]]] = None,
    accepted: Optional[Set[str]] = None,
    strict: bool = False,
    now: Optional[datetime] = None,
) -> Verdict:
    """Score one person item: modelling defects, then gaps, then reader notes.

    `topics` maps a position QID to the topics `wd/shape.py` resolved for it,
    and decides the after-office window — pass it, or every tenure is judged on
    the five-year default and long-serving ex-ministers read as dropped when
    they are not. `accepted` restricts the tenures that count to positions the
    build emits; without it every P39 target counts, which answers "could this
    person be emitted by *some* office" instead.
    """
    now = now or datetime.now(timezone.utc)
    topics = topics or {}
    qid = entity.get("id", "")
    verdict = Verdict(qid=qid)
    verdict.name = best_name(entity)
    verdict.label = verdict.name

    verdict.closure_human = HUMAN_TYPE in closure
    verdict.also_position = POSITION_TYPE in closure
    verdict.fictional = FICTIONAL_TYPE in closure
    verdict.blocked = qid in BLOCKED_PERSONS

    # The holder query is `wdt:P31 wd:Q5` — truthy, direct, exact. A person
    # typed only through a subclass, or whose `Q5` sits behind a preferred value
    # or is deprecated, is never reached. `p:P31/ps:P31` would find them; the
    # crawler does not use it, so the two reads are recorded separately.
    for claim in entity.get("claims", {}).get("P31", []):
        if claim.get("rank") == "deprecated":
            continue
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(value, dict) and value.get("id") == HUMAN_TYPE:
            verdict.truthy_human = True

    if not verdict.closure_human:
        verdict.defects.append("not_a_human")
    elif not verdict.truthy_human:
        # Typed a person only through a subclass or a deprecated claim. Every
        # human item should carry `P31 = Q5` outright.
        verdict.defects.append("q5_not_best_rank")
    if verdict.also_position:
        # Conflates the office with whoever holds it. Never repaired in a batch:
        # untangling one is a split, which is destructive-adjacent.
        verdict.defects.append("also_position")
    if verdict.name is None:
        verdict.defects.append("no_name")

    verdict.birth_dates = claim_times(entity, "P569")
    verdict.death_dates = claim_times(entity, "P570")
    birth, death = verdict.birth_date, verdict.death_date
    if birth is not None and death is not None and death < birth:
        verdict.defects.append("death_before_birth")
    if birth is not None and starts_after(birth, now):
        verdict.defects.append("future_birth")

    if not verdict.birth_dates:
        verdict.gaps.append("no_birth_date")
    elif birth is None:
        # Carries a P569 nothing can read: decade or century precision.
        verdict.gaps.append("coarse_birth_date")

    verdict.citizenship = claim_qids(entity, "P27", include_deprecated=False)
    if verdict.citizenship:
        verdict.country_via = "P27"
    else:
        verdict.gaps.append("no_citizenship")
        for prop in COUNTRY_FALLBACKS:
            if claim_qids(entity, prop, include_deprecated=False):
                verdict.country_via = prop
                break
    genders = claim_qids(entity, GENDER_PROP, include_deprecated=False)
    verdict.gender = genders[0] if genders else None
    if verdict.gender is None:
        verdict.gaps.append("no_gender")

    # The consumer's own date gates, which are notes and not defects: a person
    # born in 1880 is correctly recorded and correctly not a PEP.
    notes: List[str] = []
    for date in verdict.birth_dates:
        if date is None:
            continue
        if date < RELEVANCE_MIN:
            notes.append("born_pre_1900")
            break
        if ended_before(date, now - MAX_AGE):
            notes.append("implausibly_old")
            break
        if strict and not ended_before(date, now - MIN_AGE):
            notes.append("too_young")
            break
    if strict and any(d is not None for d in verdict.death_dates):
        notes.append("deceased")
    verdict.date_notes = notes

    for claim in entity.get("claims", {}).get("P39", []):
        if claim.get("rank") == "deprecated":
            continue  # `model.py:159` files these away; the crawl never sees them
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        if not isinstance(value, dict) or "id" not in value:
            continue
        target = value["id"]
        if accepted is not None and target not in accepted:
            verdict.out_of_scope += 1
            continue
        tenure = Tenure(
            position=target,
            start=_qualifier_time(claim, "P580"),
            end=_qualifier_time(claim, "P582"),
        )
        tenure.status = occupancy_status(
            tenure,
            birth_date=birth,
            death_date=death,
            topics=topics.get(target, set()),
            now=now,
        )
        verdict.tenures.append(tenure)

    return verdict


def verify_all(
    session: Any,
    qids: Sequence[str],
    topics: Optional[Dict[str, Set[str]]] = None,
    accepted: Optional[Set[str]] = None,
    strict: bool = False,
) -> List[Verdict]:
    """Verify a whole roster's people in one pass.

    Person items are read with `max_age=0`: they are exactly the state a
    campaign's own batches change, and a verdict read from last week's cache is
    a verdict about a record that no longer exists.
    """
    entities = fetch_entities(session, list(qids), max_age=0)
    closures = type_closure(session, sorted(entities))
    now = datetime.now(timezone.utc)
    return [
        verify(entity, closures.get(qid, set()), topics=topics,
               accepted=accepted, strict=strict, now=now)
        for qid, entity in sorted(entities.items())
    ]
