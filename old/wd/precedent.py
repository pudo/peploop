"""What the community already does with a position item.

Reach for this before deciding whether a term "belongs" on an office item. The
question that stalled three campaigns — do pre-independence holders go on the
item labelled for the modern republic? — is not a convention to be ruled on
once per country, because the answer varies per *item* inside one country:
Czech Agriculture carries ten terms starting before 1993 out of twenty-seven,
while the Czech Defence item only exists from 1993 and a 1969 term there would
contradict the item's own inception date.

One query per target answers it. The census is cached to
`data/<campaign>/precedent.json` so it is reviewable in its own right, and so a
decision that changes can be traced to a census that changed.

Two traps this module exists to avoid:

* **`wdt:P39` returns only preferred-rank values**, so a person with a later
  preferred office hides the statement you are counting. Coverage measured that
  way reads roughly half the truth (`CLAUDE.md`).
* **Some items are already polluted.** Otakar Fischer's 1939 Protectorate term
  sits on the modern Czech interior item today, so a bare "has an earlier term"
  test reads one editor's mistake as community practice. Hence the thresholds
  in `supports_before`.
"""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from requests import Session

from wd.api import sparql

#: A target needs at least this many earlier statements, from at least this
#: share of its dated ones, before "the community does this" is a fair reading
#: rather than a description of one stray edit.
MIN_EARLIER = 3
MIN_SHARE = 0.15


@dataclass
class Precedent:
    """How an office item is actually used today."""

    target: str
    #: Distinct people holding it, any rank.
    holders: int = 0
    #: Start years of every dated statement, ascending.
    starts: List[int] = field(default_factory=list)
    #: How many of its statements carry P2868 (acting).
    acting: int = 0
    #: The item's own P571 / P576, when it declares them.
    inception: Optional[int] = None
    abolished: Optional[int] = None

    @property
    def dated(self) -> int:
        return len(self.starts)

    def earlier_than(self, year: int) -> int:
        return sum(1 for start in self.starts if start < year)

    def supports_before(self, year: int) -> bool:
        """Would a term starting before `year` be ordinary practice here?

        Requires both an absolute floor and a share, because a handful of
        mistaken imports on a heavily-used item would otherwise clear a
        percentage test, and one correct early statement on a sparse item would
        otherwise clear a count test.
        """
        if self.inception is not None and year <= self.inception:
            # The item declares it did not exist yet; an earlier term would
            # contradict the item, which is a different thing from contested.
            return False
        earlier = self.earlier_than(year)
        if earlier < MIN_EARLIER or not self.dated:
            return False
        return earlier / self.dated >= MIN_SHARE

    def covers(self, start: Optional[str]) -> bool:
        """Does the item's own lifespan contain this term's start?"""
        if not start:
            return True
        year = int(start[:4])
        if self.inception is not None and year < self.inception:
            return False
        if self.abolished is not None and year > self.abolished:
            return False
        return True

    @property
    def uses_acting_qualifier(self) -> bool:
        return self.acting > 0

    def to_dict(self) -> dict:
        return {
            "target": self.target,
            "holders": self.holders,
            "dated": self.dated,
            "starts": self.starts,
            "acting": self.acting,
            "inception": self.inception,
            "abolished": self.abolished,
        }

    @staticmethod
    def from_dict(data: dict) -> "Precedent":
        precedent = Precedent(target=data["target"])
        precedent.holders = data.get("holders", 0)
        precedent.starts = list(data.get("starts") or [])
        precedent.acting = data.get("acting", 0)
        precedent.inception = data.get("inception")
        precedent.abolished = data.get("abolished")
        return precedent


#: Selecting `?pos` alongside the holder is what lets one query serve a batch
#: of targets: without it the rows cannot be attributed back.
QUERY = """
SELECT ?pos ?p ?start ?acting WHERE {
  VALUES ?pos { %s }
  ?p p:P39 ?st . ?st ps:P39 ?pos .
  OPTIONAL { ?st pq:P580 ?start }
  OPTIONAL { ?st pq:P2868 ?acting }
}
"""

SPAN_QUERY = """
SELECT ?pos ?inception ?abolished WHERE {
  VALUES ?pos { %s }
  OPTIONAL { ?pos wdt:P571 ?inception }
  OPTIONAL { ?pos wdt:P576 ?abolished }
}
"""


def _year(value: Optional[str]) -> Optional[int]:
    if not value:
        return None
    text = value.lstrip("+")
    return int(text[:4]) if text[:4].isdigit() else None


def _retrying(session: Session, query: str, tries: int = 6) -> List[dict]:
    """WDQS drops statement-node scans under load; retry patiently."""
    for attempt in range(tries):
        try:
            return sparql(session, query)
        except Exception:  # noqa: BLE001 — a timeout is expected, not exceptional
            if attempt == tries - 1:
                raise
            time.sleep(4 * (attempt + 1))
    return []


def census(
    session: Session, targets: Iterable[str], cache: Optional[Path] = None,
    chunk: int = 40,
) -> Dict[str, Precedent]:
    """Measure every target, reading and writing `cache` when given.

    Statement-node queries (`p:`/`pq:`) time out easily, so targets go in small
    batches rather than one `VALUES` list of everything.
    """
    known: Dict[str, Precedent] = {}
    if cache and cache.exists():
        known = {
            qid: Precedent.from_dict(data)
            for qid, data in json.loads(cache.read_text()).items()
        }
    todo = [t for t in dict.fromkeys(targets) if t and t not in known]

    for index in range(0, len(todo), chunk):
        batch = todo[index : index + chunk]
        values = " ".join(f"wd:{q}" for q in batch)
        results: Dict[str, Precedent] = {q: Precedent(target=q) for q in batch}
        people: Dict[str, set] = {q: set() for q in batch}
        for row in _retrying(session, QUERY % values):
            target = row["pos"].rsplit("/", 1)[-1]
            precedent = results.get(target)
            if precedent is None:
                continue
            people[target].add(row["p"])
            start = _year(row.get("start"))
            if start is not None:
                precedent.starts.append(start)
            if row.get("acting"):
                precedent.acting += 1
        for target, precedent in results.items():
            precedent.holders = len(people[target])
            precedent.starts.sort()
        for row in _retrying(session, SPAN_QUERY % values):
            target = row["pos"].rsplit("/", 1)[-1]
            if target in results:
                results[target].inception = _year(row.get("inception"))
                results[target].abolished = _year(row.get("abolished"))
        known.update(results)

    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(
            json.dumps(
                {q: p.to_dict() for q, p in sorted(known.items())},
                indent=2, sort_keys=True,
            )
            + "\n"
        )
    return known


def report(precedents: Dict[str, Precedent], year_by_target: Dict[str, int]) -> List[str]:
    """Human-readable census lines, for the audit.

    Printed for every target where the answer is close, because a rule that
    flips a decision on a measurement deserves to show its working.
    """
    lines = []
    for target, precedent in sorted(precedents.items()):
        year = year_by_target.get(target)
        if year is None:
            continue
        verdict = "supports" if precedent.supports_before(year) else "declines"
        lines.append(
            f"{target}: {precedent.holders} holders, {precedent.dated} dated, "
            f"{precedent.earlier_than(year)} before {year}"
            + (f", inception {precedent.inception}" if precedent.inception else "")
            + (f", {precedent.acting} acting-qualified" if precedent.acting else "")
            + f" — {verdict} pre-{year} terms"
        )
    return lines
