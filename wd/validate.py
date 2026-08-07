"""Check a rendered batch before anyone runs it.

`recipes/category_check.md` has prescribed these checks since the Ecuador run —
"verify mechanically before you eyeball: no duplicate (person, position) pairs,
no `start > end`, dates at the precision you expect, and the count of statements
sourced to a real citation versus to a wiki permalink" — and every campaign since
has done it by typing a throwaway script. This is that script, kept.

The split matters. A **defect** is something QuickStatements would happily write
and nobody wants written: the same statement twice, a term ending before it
begins, a value that is not an item. Those stop the render. A **warning** is a
quality signal that needs a human eye but not a veto — the citation split, or a
year-precision date on an item whose other statements in this same batch carry
the day, which is the signature of a parse failure rather than a coarse source.
"""

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Sequence, Tuple

#: A reference is provenance, not part of the claim: the same membership proved
#: by two different roster pages is one statement with two references, and
#: QuickStatements merges them. Counting them as duplicates would flag exactly
#: that case, which happens whenever a person appears in two offices.
REFERENCE_PROPERTIES = re.compile(r"^S\d+$")

ITEM_VALUE = re.compile(r"^Q\d+$")
TIME_VALUE = re.compile(r"^[+-]\d{4}-\d{2}-\d{2}T00:00:00Z/(9|10|11)$")


def well_formed_time(token: str) -> bool:
    """A QuickStatements time token that is also a real date.

    The shape alone is not enough: `+2000-13-99T00:00:00Z/11` matches the
    pattern and is not a day in any month. Coarser precisions keep the padded
    form QuickStatements expects, so only a day-precision token is checked
    against the calendar.
    """
    if not TIME_VALUE.match(token):
        return False
    if token.rsplit("/", 1)[1] != "11":
        return True
    try:
        date.fromisoformat(token[1:].split("T")[0])
    except ValueError:
        return False
    return True


@dataclass
class Result:
    """What the checks found. `defects` non-empty means do not ship."""

    statements: int = 0
    defects: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    #: Date precision → how many qualifiers carry it (9 year, 10 month, 11 day).
    precision: Counter = field(default_factory=Counter)
    #: Reference property → count, i.e. real citations versus wiki permalinks.
    sources: Counter = field(default_factory=Counter)

    @property
    def ok(self) -> bool:
        return not self.defects

    def lines(self) -> List[str]:
        """The `## Validation` section of the review document."""
        out = [
            "## Validation",
            "",
            f"{self.statements} statements · "
            + " · ".join(
                f"{n} at precision {p}" for p, n in sorted(self.precision.items())
            )
            + " · "
            + " · ".join(f"{n} {prop}" for prop, n in sorted(self.sources.items())),
            "",
        ]
        for defect in self.defects:
            out.append(f"* ✗ **defect**: {defect}")
        for warning in self.warnings:
            out.append(f"* ⚠ {warning}")
        if self.ok and not self.warnings:
            out.append("* every check passed")
        out.append("")
        return out


def _parse(line: str) -> Tuple[str, str, str, Dict[str, str], Dict[str, str]]:
    """One QuickStatements V1 line as subject, property, value, qualifiers, refs."""
    columns = line.split("\t")
    subject, prop, value = (columns + ["", "", ""])[:3]
    qualifiers: Dict[str, str] = {}
    references: Dict[str, str] = {}
    for index in range(3, len(columns) - 1, 2):
        key, argument = columns[index], columns[index + 1]
        if REFERENCE_PROPERTIES.match(key):
            references[key] = argument
        else:
            qualifiers[key] = argument
    return subject, prop, value, qualifiers, references


def check(lines: Sequence[str]) -> Result:
    """Run every check over a rendered QuickStatements batch."""
    result = Result(statements=len(lines))
    #: Whole lines, references included. The renderer already drops exact
    #: repeats, so one surviving here is a bug in the renderer.
    identical: Counter = Counter()
    #: The claim without its references. Two lines here are one statement with
    #: two sources — legitimate, and QuickStatements merges them — but a reviewer
    #: counting lines should be told, because then 111 lines are 110 statements.
    claims: Counter = Counter()
    #: (subject, property) → the precisions its statements' start dates carry,
    #: so a lone year-precision date among day-precision ones is visible.
    by_target: Dict[str, Counter] = {}

    for line in lines:
        subject, prop, value, qualifiers, references = _parse(line)
        identical[line] += 1
        if identical[line] == 1:
            claims[(subject, prop, value, tuple(sorted(qualifiers.items())))] += 1

        if not ITEM_VALUE.match(subject):
            result.defects.append(f"subject is not an item: {line[:80]!r}")
        if value.startswith("+"):
            if not well_formed_time(value):
                result.defects.append(f"malformed time value: {line[:80]!r}")
        elif not value.startswith('"') and not ITEM_VALUE.match(value):
            result.defects.append(f"value is neither an item nor a literal: {value!r}")

        start, end = qualifiers.get("P580"), qualifiers.get("P582")
        for bound in (start, end):
            if bound is None:
                continue
            if not well_formed_time(bound):
                result.defects.append(f"malformed date qualifier: {bound!r} in {subject}")
            else:
                result.precision[int(bound.rsplit("/", 1)[1])] += 1
        if start and end and well_formed_time(start) and well_formed_time(end):
            if start.split("T")[0] > end.split("T")[0]:
                result.defects.append(
                    f"{subject} {prop} {value}: starts {start.split('T')[0]} but "
                    f"ends {end.split('T')[0]}"
                )
        if prop == "P39" and not start:
            result.warnings.append(f"{subject} P39 {value} has no start date")
        if start and ITEM_VALUE.match(value):
            by_target.setdefault(value, Counter())[int(start.rsplit("/", 1)[1])] += 1

        for reference in references:
            result.sources[reference] += 1

    for line, count in identical.items():
        if count > 1:
            result.defects.append(f"{count}× this exact line: {line[:90]!r}")
    restated = {key: n for key, n in claims.items() if n > 1}
    if restated:
        result.warnings.append(
            f"{len(restated)} claim(s) appear on more than one line with different "
            "references, so the batch writes "
            f"{len(lines) - sum(n - 1 for n in restated.values())} statements from "
            f"{len(lines)} lines: "
            + ", ".join(f"{k[0]} {k[1]} {k[2]}" for k in sorted(restated)[:4])
        )

    for target, precisions in sorted(by_target.items()):
        # A coarse date on an office whose other terms in this very batch are
        # day-precision is not a coarse source; it is a cell that failed to
        # parse. Four Spanish pages lost every date this way and the batch was
        # still renderable.
        # …but only when the coarse ones are the exception. An office whose
        # pre-1990 rows give years and whose later ones give days is an ordinary
        # roster, and warning about that (Ecuador: three of six) is how a check
        # teaches people to ignore it.
        coarse = sum(n for p, n in precisions.items() if p < 11)
        total = sum(precisions.values())
        if coarse and precisions.get(11) and coarse / total < 0.25:
            result.warnings.append(
                f"{target}: {coarse} statement(s) at year/month precision beside "
                f"{precisions[11]} at day precision — a misparsed date cell?"
            )

    if result.sources:
        cited = result.sources.get("S854", 0)
        total = sum(n for prop, n in result.sources.items() if prop != "S813")
        if total and cited / total < 0.5:
            result.warnings.append(
                f"only {cited} of {total} statements cite a source outside "
                "Wikimedia; the rest cite a roster permalink (S4656)"
            )
    return result


__all__ = ["Result", "check"]
