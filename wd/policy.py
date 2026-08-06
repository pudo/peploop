"""What to do with a candidate, decided by rule rather than by escalation.

Reach for this instead of adding another tier. The engine used to label every
awkward case with an `era` string and let one line in the renderer decide that
only `modern` shipped; everything else waited for a human ruling that, across
four campaigns and 438 held records, never came. The bottleneck was never a
shortage of judgement — it was that judgement had nowhere to live except a
person's inbox.

So policy lives here, as an ordered list of rules over a candidate's *flags*
and the *facts* gathered about its target. A rule is `predicate → disposition`,
first match wins, and every decision records which rule fired so a surprising
outcome is traceable to one line. Two consequences worth stating:

* **A country cannot express its convention as a constant.** Whether pre-cutoff
  terms belong on an item varies per *item*: Czech Agriculture already carries
  ten terms from before 1993, while Czech Defence's item only exists from 1993.
  Rules therefore read `Facts`, which `wd.precedent` measures, rather than a
  per-country default that would be wrong for half the offices.
* **Nothing is escalated per case.** A candidate with no evidence is skipped
  with a recorded reason, and a class of case needing data entry becomes a
  byproduct list. Neither is a question about a row.
"""

from dataclasses import dataclass, field
from typing import Callable, Dict, Optional, Sequence, Tuple

#: What a rule can decide. `hold` is transitional — it marks a statement the
#: engine believes but that no rule has yet been written to release — and its
#: population shrinking to zero is the measure of this project.
APPLY = "apply"
HOLD = "hold"
REVIEW = "review"
SKIP = "skip"
DEFECT = "defect"
BYPRODUCT = "byproduct"


@dataclass(frozen=True)
class Candidate:
    """One officeholding claim, described but not yet judged."""

    qid: str
    target: str
    #: Everything true about this candidate at once — acting, pre-cutoff,
    #: roster-only — rather than whichever label an if/elif chain reached first.
    flags: Tuple[str, ...]
    #: Terms as (start, end), partial ISO.
    terms: Tuple[Tuple[Optional[str], Optional[str]], ...] = ()
    #: How the person was identified: wikilink, article title, name match,
    #: category. A rule that applies on Wikipedia's own assertion should not
    #: apply on this engine's guess.
    identity: str = ""
    #: Whether the office claim itself is believed — two channels agreeing, or
    #: a roster row this engine trusts. False for candidates that are only
    #: suspected (a category with no roster row to corroborate it).
    believed: bool = False
    #: True when a Wikipedia category also puts this person in this office.
    in_category: bool = False
    office: str = ""


@dataclass(frozen=True)
class Facts:
    """What was measured before any decision was taken.

    Assembled once per run and frozen, so `decide` is a pure function of
    (candidate, facts) — testable without network, and diffable when either
    input changes.
    """

    #: Target QID → what the community already does with that item. Filled by
    #: `wd.precedent`; empty until that census runs.
    precedent: Dict[str, object] = field(default_factory=dict)
    #: Candidate key → signals gathered by the second-channel resolver.
    signals: Dict[str, list] = field(default_factory=dict)


@dataclass(frozen=True)
class Rule:
    id: str
    when: Callable[[Candidate, Facts], bool]
    disposition: str
    rationale: str
    #: Extra qualifiers the disposition carries, e.g. P2868 for acting spells.
    qualifiers: Dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Ruling:
    rule: str
    disposition: str
    rationale: str
    qualifiers: Dict[str, str] = field(default_factory=dict)
    source: str = "default"


def has(*flags: str) -> Callable[[Candidate, Facts], bool]:
    """Predicate: the candidate carries any of these flags."""
    wanted = set(flags)

    def check(candidate: Candidate, _facts: Facts) -> bool:
        return bool(wanted.intersection(candidate.flags))

    return check


def always(_candidate: Candidate, _facts: Facts) -> bool:
    return True


#: The default rule table, in order. First match wins.
#:
#: Every entry below `modern` is currently `hold` or `review`, which reproduces
#: the behaviour of the era gate it replaces — the point of introducing the
#: table separately from changing it is that the escalation ladder becomes data
#: first, so each later loosening is a one-line diff with one candidate cause.
DEFAULT_RULES: Tuple[Rule, ...] = (
    Rule(
        "modern.two_channel", has("modern"), APPLY,
        "a Wikipedia category and a dated roster row agree, inside the "
        "modern institutional era",
    ),
    Rule(
        "roster_only", has("roster_only"), HOLD,
        "named by the roster but by no category — one channel",
    ),
    Rule(
        "historical", has("historical", "historical_roster_only"), HOLD,
        "term starts before the country's institutional cutoff",
    ),
    Rule(
        "no_dates", has("no_dates"), HOLD,
        "two channels agree on the office, but nothing dates the term",
    ),
    # The convention for an acting spell is the office plus P2868, not a
    # separate item, and it is written down twice already. These were held for
    # a ruling that had in fact been made.
    Rule(
        "acting", has("acting"), APPLY,
        "the roster marks this spell acting; the convention is the office "
        "plus P2868 = Q4676846",
        qualifiers={"P2868": "Q4676846"},
    ),
    Rule(
        "interim_concurrent_office", has("interim_concurrent_office"), APPLY,
        "a short spell falling entirely inside a term the person holds in "
        "another office — cover, and recorded as acting",
        qualifiers={"P2868": "Q4676846"},
    ),
    Rule(
        "predecessor_body", has("predecessor_body"), REVIEW,
        "filed under a pre-ministerial body — a different institution",
    ),
    Rule(
        "category_only", has("category_only"), REVIEW,
        "in the category, named by no roster row, and undated",
    ),
    Rule(
        "namesake", has("lifetime_mismatch", "lifespan_not_term"), REVIEW,
        "the lifetime gate rejected this identification",
    ),
    # Regime and per-office holds carry campaign-specific names, so they cannot
    # be matched by flag here; they fall through to the two catch-alls, which
    # reproduce exactly what the era gate did with them.
    Rule(
        "believed.held", lambda c, f: c.believed, HOLD,
        "the engine believes the claim, but no rule releases this tier yet",
    ),
    Rule("uncertain", always, REVIEW, "no rule claims this case"),
)


def decide(
    candidate: Candidate,
    facts: Facts,
    rules: Sequence[Rule] = DEFAULT_RULES,
    overrides: Optional[Dict[str, str]] = None,
) -> Ruling:
    """The first rule that claims this candidate, and what it decided.

    `overrides` maps a rule id to a different disposition, which is how a
    country states that its own history contradicts the default — declared once
    per office, never per person.
    """
    for rule in rules:
        if not rule.when(candidate, facts):
            continue
        disposition = (overrides or {}).get(rule.id, rule.disposition)
        return Ruling(
            rule=rule.id,
            disposition=disposition,
            rationale=rule.rationale,
            qualifiers=dict(rule.qualifiers),
            source="profile" if overrides and rule.id in overrides else "default",
        )
    return Ruling("unmatched", REVIEW, "no rule matched")


def tally(decisions: Sequence[Tuple[str, str]]) -> Dict[str, int]:
    """(rule, disposition) → how often it fired.

    This is the review document's headline: a reader checks a dozen rules with
    counts against them, instead of reading three hundred rows and inferring
    the policy that produced them.
    """
    counts: Dict[str, int] = {}
    for rule, disposition in decisions:
        key = f"{rule} → {disposition}"
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


__all__ = [
    "APPLY", "HOLD", "REVIEW", "SKIP", "DEFECT", "BYPRODUCT",
    "Candidate", "Facts", "Rule", "Ruling",
    "DEFAULT_RULES", "decide", "has", "always", "tally",
]
