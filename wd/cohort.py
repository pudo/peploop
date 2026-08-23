"""Who a spec's enrichment run should read, and who it should not pay to read.

A `wd_categories.yml` spec names a Wikipedia category; its members are the
candidate set. This module turns that into three disjoint groups, and the split
is the point:

* **held** — members Wikidata already records in the office. Not work; a
  *labelled test set*, read for free by `wd/backtest.py`. Never propose to them.
* **todo** — the gap, filtered down to people there is evidence to read about.
* **dropped** — everyone else, with the reason, counted. A filter that silently
  shrinks a cohort is the same failure as a campaign that silently skips an
  institution.

The one rule worth stating twice: **a missing date is never a reason to drop
anyone.** Undated people are the highest-yield population, not the lowest —
`research/person_items.md` measured ten Lesotho holders whom a single `P569`
would make emittable and nine already standing on one. Only a *known* date that
puts someone outside the window drops them.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Optional, Sequence, Set, Tuple

from requests import Session

from wd.api import best_label, fetch_entities, sparql
from wd.human import AFTER_DEATH, YEAR_DAYS, claim_times
from wd.petscan import category_members
from wd.wikipedia import wikipedia_langs
from wd.positions import members_holding
from wd.specs import Spec

#: Nobody born before this is worth an LLM call: they cannot produce an
#: Occupancy (`zavod` drops a `P569` below 1900 outright) and their articles are
#: the ones a category sweeps in by accident. Later than zavod's own 1900 on
#: purpose — the gap between them is people who are correctly modelled and
#: correctly absent, which is not a campaign's business.
BORN_AFTER = "1920"

#: Props the gate needs. Sitelinks decide whether a dossier can be built at all.
COHORT_PROPS = "labels|descriptions|claims|sitelinks"


@dataclass
class Member:
    """One category member, with just enough to gate on."""

    qid: str
    title: str
    label: Optional[str] = None
    birth: Optional[str] = None
    death: Optional[str] = None
    langs: Tuple[str, ...] = ()

    @property
    def readable(self) -> bool:
        return bool(self.langs)


@dataclass
class Cohort:
    spec: Spec
    members: List[Member] = field(default_factory=list)
    held: List[Member] = field(default_factory=list)
    todo: List[Member] = field(default_factory=list)
    dropped: Dict[str, str] = field(default_factory=dict)   # qid -> reason
    not_human: List[str] = field(default_factory=list)

    @property
    def sizes(self) -> Dict[str, int]:
        return {
            "members": len(self.members),
            "held": len(self.held),
            "todo": len(self.todo),
            "dropped": len(self.dropped),
            "not_human": len(self.not_human),
        }

    def reasons(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for reason in self.dropped.values():
            counts[reason] = counts.get(reason, 0) + 1
        return dict(sorted(counts.items(), key=lambda kv: -kv[1]))


def category_qids(
    session: Session, spec: Spec, max_age: Optional[int] = None
) -> List[Tuple[str, str]]:
    """The spec's category members as (QID, page title), PETScan's own view."""
    return category_members(
        session,
        spec.category,
        spec.language,
        depth=spec.depth,
        max_age=max_age,
    )


def humans(session: Session, qids: Sequence[str]) -> Set[str]:
    """Which of these items are typed human, at any rank.

    PETScan's `wikidata_prop_item_use=Q5` filter passes `Category:` items
    through `P4224` ("category contains"), so the type has to be re-checked
    here. `p:P31/ps:P31` rather than `wdt:` because a `Q5` sitting behind a
    preferred value is still a `Q5` — and one query per 120 items is far
    cheaper than pulling every entity to find out.
    """
    found: Set[str] = set()
    qids = list(qids)
    for start in range(0, len(qids), 120):
        values = " ".join(f"wd:{q}" for q in qids[start:start + 120])
        rows = sparql(session, f"""SELECT DISTINCT ?p WHERE {{
          VALUES ?p {{ {values} }} ?p p:P31/ps:P31 wd:Q5 .
        }}""", max_age=0)
        found.update(row["p"] for row in rows)
    return found


def _first(values: Sequence[Optional[str]]) -> Optional[str]:
    return next((v for v in values if v), None)


def relevance(
    member: Member,
    *,
    born_after: str = BORN_AFTER,
    after_death: timedelta = AFTER_DEATH,
    today: Optional[date] = None,
) -> Optional[str]:
    """Why this person is not worth reading, or None.

    Three reasons, in the order they cost least to establish. Note what is
    absent: no rule fires on a *missing* date.
    """
    if not member.readable:
        return "no-sitelink"
    if member.birth and member.birth < born_after:
        return "born-before-%s" % born_after
    if member.death:
        cutoff = ((today or date.today()) - after_death).isoformat()
        # Compare at the precision they share — a year-precision death date
        # must not be read as January 1st of that year.
        span = min(len(member.death), len(cutoff))
        if member.death[:span] < cutoff[:span]:
            return "long-dead"
    return None


def size(
    session: Session, spec: Spec, max_age: Optional[int] = None
) -> Dict[str, int]:
    """Cheap sizing for one spec: members, how many already hold, the gap.

    Three queries and no per-member entity fetch, so it is affordable across all
    284 specs — which is what ranking them by cheapness needs. `build` is the
    real thing; this only answers "how much work is here". The gap it reports is
    therefore an upper bound: the relevance gate shrinks it further.
    """
    listed = category_qids(session, spec, max_age=max_age)
    if not listed:
        return {"members": 0, "human": 0, "held": 0, "gap": 0}
    qids = [qid for qid, _ in listed]
    real = humans(session, qids)
    held = (
        members_holding(session, sorted(real), spec.target)
        if spec.target and real
        else set()
    )
    return {
        "members": len(qids),
        "human": len(real),
        "held": len(held),
        "gap": len(real - held),
    }


def build(
    session: Session,
    spec: Spec,
    *,
    langs: Sequence[str] = (),
    gate: bool = True,
    born_after: str = BORN_AFTER,
    max_age: Optional[int] = None,
) -> Cohort:
    """Assemble the spec's cohort: members, the backtest set, and the work.

    `langs` restricts which wikis count as readable; empty means any sitelink
    will do. `gate=False` skips the relevance filter, for sizing a spec without
    committing to a policy.
    """
    cohort = Cohort(spec=spec)
    listed = category_qids(session, spec, max_age=max_age)
    if not listed:
        return cohort

    titles = {qid: title for qid, title in listed}
    real = humans(session, list(titles))
    cohort.not_human = sorted(set(titles) - real)

    # One batched fetch, fresh: dates and sitelinks are read to decide whether
    # to spend money on someone, and a week-old answer is a week-old decision.
    entities = fetch_entities(session, sorted(real), props=COHORT_PROPS, max_age=0)
    for qid in sorted(real):
        entity = entities.get(qid)
        if entity is None:
            cohort.dropped[qid] = "no-entity"
            continue
        wikis = tuple(wikipedia_langs(entity))
        if langs:
            wikis = tuple(w for w in wikis if w in set(langs))
        cohort.members.append(
            Member(
                qid=qid,
                title=titles[qid],
                label=best_label(entity),
                birth=_first(claim_times(entity, "P569")),
                death=_first(claim_times(entity, "P570")),
                langs=wikis,
            )
        )

    held = (
        members_holding(session, [m.qid for m in cohort.members], spec.target)
        if spec.target and cohort.members
        else set()
    )
    for member in cohort.members:
        if member.qid in held:
            cohort.held.append(member)
            continue
        reason = relevance(member, born_after=born_after) if gate else None
        if reason:
            cohort.dropped[member.qid] = reason
        else:
            cohort.todo.append(member)
    return cohort


# `YEAR_DAYS` is re-exported so a caller can express a window without importing
# `wd/human.py` for one constant.
__all__ = [
    "BORN_AFTER", "Cohort", "Member", "build", "category_qids", "humans",
    "relevance", "size", "YEAR_DAYS",
]
