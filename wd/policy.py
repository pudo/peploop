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
#: Identity rungs where somebody other than this engine made the claim: a
#: roster wikilink, or an article sitting at exactly the printed name.
STRONG_IDENTITY = ("wikilink", "article title")

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
    #: True when the roster row carried its own citation to something outside
    #: Wikimedia — a stronger second channel than any category.
    cited: bool = False
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
    #: The country's institutional cutoff, for reading the census.
    modern_from: int = 0
    #: Earlier polities that are the *same institution* under another
    #: constitution — the Czech Republic inside the federation, not the
    #: Protectorate. Their rows are judged like any other early term, on the
    #: target's own record, rather than refused for the name of the era.
    continuous_eras: frozenset = frozenset()
    #: Every era name the campaign routes on, continuous or not.
    regimes: frozenset = frozenset()


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


def in_era(kind: str) -> Callable[[Candidate, Facts], bool]:
    """Predicate: the candidate belongs to a continuous or a distinct polity."""

    def check(candidate: Candidate, facts: Facts) -> bool:
        flags = set(candidate.flags)
        if kind == "continuous":
            return bool(flags & facts.continuous_eras)
        return bool(flags & (facts.regimes - facts.continuous_eras))

    return check


def precedent_allows(candidate: Candidate, facts: Facts) -> bool:
    """Would the target item ordinarily carry a term this early?

    Answered from the item's own record rather than from a per-country rule,
    because the two disagree inside one country: Czech Agriculture already
    holds ten terms from before 1993, while a 1969 term on Czech Defence would
    predate the item's declared inception.
    """
    precedent = facts.precedent.get(candidate.target)
    if precedent is None or not facts.modern_from:
        return False
    if not precedent.supports_before(facts.modern_from):
        return False
    return all(precedent.covers(start) for start, _ in candidate.terms)


def _early(candidate: Candidate, facts: Facts) -> bool:
    return bool(
        set(candidate.flags) & {"historical", "historical_roster_only"}
    ) or in_era("continuous")(candidate, facts)


#: The default rule table, in order. First match wins.
#:
#: The order is load-bearing, and in one direction that is easy to get wrong.
#: Every row carries its era *alongside* its tier, so a candidate can be both
#: `acting` and `historical`. Rules that answer "does this claim belong on this
#: item at all" must therefore precede rules that answer "what kind of tenure
#: was it", and the general `modern` rule must come last of the applying rules
#: or it swallows the specific tiers and drops their qualifiers.
DEFAULT_RULES: Tuple[Rule, ...] = (
    # 1. Identity failures first: nothing else about the row matters.
    Rule(
        "namesake", has("lifetime_mismatch", "lifespan_not_term"), REVIEW,
        "the lifetime gate rejected this identification",
    ),
    # 2. Does the claim belong on this item at all?
    #    An earlier polity that is a different *state* keeps its own offices;
    #    its rows need an item of their own, which no rule can invent.
    Rule(
        "era.distinct", in_era("distinct"), SKIP,
        "a different polity's office — it needs its own item, which the "
        "profile must name",
    ),
    #    An acting spell in 1836 is still an 1836 term, and has to answer the
    #    same question about the target as any other. Ordered below `acting`,
    #    this would apply 19th-century spells to an item whose own record
    #    begins in 1979.
    #    One office with two items — Spain's normal state — means a term can be
    #    on record already under the item this office does not happen to name.
    #    Above the tenure rules on purpose: an acting spell already recorded
    #    elsewhere is still recorded, and adding a P2868 copy on a sibling item
    #    is the worst of the available outcomes.
    Rule(
        "duplicate_office_item", has("duplicate_office_item"), SKIP,
        "another item for this same office already records this spell",
    ),
    Rule(
        "early.unsupported",
        lambda c, f: _early(c, f) and not precedent_allows(c, f), SKIP,
        "the target's own record does not carry terms this early, or the "
        "term predates the item's declared inception",
    ),
    Rule(
        "early.weak_identity",
        lambda c, f: _early(c, f)
        and not (c.in_category or c.identity in STRONG_IDENTITY or c.cited),
        SKIP,
        "the target supports terms this early, but the identification is a "
        "name match rather than an assertion",
    ),
    # 3. What kind of tenure was it? The convention for a spell someone was
    #    covering is the office plus P2868, not a separate item.
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
    # Below the interim rules on purpose: a spell the roster shows was *cover*
    # is a real second office and keeps its P2868. What is left here is one
    # appointment written down twice under two names — Czech ministers without
    # portfolio already recorded under the remit the Gesce column names.
    Rule(
        "duplicate_appointment", has("duplicate_appointment"), SKIP,
        "an existing statement already covers exactly these dates under "
        "another office — the same appointment, named twice",
    ),
    Rule(
        "predecessor_body", has("predecessor_body"), REVIEW,
        "filed under a pre-ministerial body — a different institution",
    ),
    Rule(
        "category_only", has("category_only"), REVIEW,
        "in the category, named by no roster row, and undated",
    ),
    # 3b. The infobox channel, which answers the channel question differently
    #     from everything below and so has to be settled before it. A roster is
    #     an article about the *office* listing its holders, maintained as a
    #     unit and reviewed by whoever watches that office. An infobox is a
    #     claim on the holder's own page, written by whoever wrote that page. It
    #     is enough to date a tenure and never enough to assert one alone, so
    #     the office's own category has to say the same thing. Where a country
    #     publishes no rosters this is the only channel there is — Qatar dates
    #     two of thirty-two ministries — which is exactly when the temptation to
    #     relax it arrives.
    #     Both are held back from an undated row, which `no_dates` decides
    #     further down: placed this early they would otherwise claim it first
    #     and apply a P39 with no start at all. Rule order is load-bearing in
    #     both directions, and this is the direction that is easy to miss.
    Rule(
        "officebox.two_channel",
        lambda c, f: (
            "officebox" in c.flags and "no_dates" not in c.flags and c.in_category
        ), APPLY,
        "their own article's infobox states this office with dates, and the "
        "office's category names them independently",
    ),
    Rule(
        "officebox.one_channel",
        lambda c, f: "officebox" in c.flags and "no_dates" not in c.flags, SKIP,
        "the infobox on their own article is the only thing asserting this "
        "office, and one channel is not enough",
    ),
    # 4. How many channels, and how strong? A dedicated list article naming a
    #    *wikilinked* person is Wikipedia asserting both office and identity,
    #    and a row citing something outside Wikimedia is a better second
    #    channel than the category whose absence held it. A bare token-subset
    #    name match is this engine guessing, and earns no such credit.
    Rule(
        "roster_only.attested",
        lambda c, f: has("roster_only")(c, f)
        and (c.identity in STRONG_IDENTITY or c.cited),
        APPLY,
        "a dedicated roster names them, with the identity asserted by a "
        "wikilink or corroborated by the row's own citation",
    ),
    Rule(
        "roster_only.weak_identity", has("roster_only"), SKIP,
        "only a roster names them, and the identification is a name match "
        "rather than an assertion",
    ),
    Rule(
        "early.precedent_ok", _early, APPLY,
        "the target already carries terms this early, so this is how the "
        "community uses the item",
    ),
    Rule(
        "modern.two_channel", has("modern"), APPLY,
        "a Wikipedia category and a dated roster row agree, inside the "
        "modern institutional era",
    ),
    Rule(
        "no_dates", has("no_dates"), HOLD,
        "two channels agree on the office, but nothing dates the term",
    ),
    # 5. Catch-alls. `believed.held` shrinking to nothing is the measure of
    #    this project; a row reaching it is a tier no rule has been written for.
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


#: The enrichment loop's table, over the flags `wd/enrich.py:check` produces.
#: Separate from `DEFAULT_RULES` because the questions are different: a campaign
#: asks "does this roster row belong on this item", and an enrichment run asks
#: "did the mechanical channel confirm what the model read".
#:
#: The order is the same kind of load-bearing. Everything that says *this
#: proposal is not usable* has to precede everything that says *what kind of
#: statement it is*, because a proposal can be `acting` and unverifiable at
#: once. Failures come first, and the terminal rule is `skip` rather than
#: `review`: conservatism belongs in the rules, and a tier a human rules on
#: later is the thing this table exists to prevent.
ENRICH_RULES: Tuple[Rule, ...] = (
    # 1. The evidence is not in the evidence. Nothing else about the proposal
    #    matters, and this is the check no schema can do.
    Rule(
        "quote_unverified", has("fail_quote_not_in_evidence"), SKIP,
        "the quoted span does not occur in the dossier it cites",
    ),
    # 2. A QID nobody offered. The gazetteer is the closed set precisely so
    #    this is detectable rather than plausible.
    Rule(
        "position_invented", has("fail_position_not_in_gazetteer"), SKIP,
        "the position QID was not in the gazetteer for this run",
    ),
    # 3. Already there. The diff-against-item discipline, made a rule.
    Rule(
        "already_recorded", has("fail_already_recorded"), SKIP,
        "the item already carries this statement",
    ),
    # 4. Malformed or impossible. Ours to fix, not Wikidata's.
    Rule(
        "malformed", has("fail_malformed_start", "fail_malformed_end",
                        "fail_malformed_date", "fail_start_after_end"), SKIP,
        "the proposed dates are malformed or impossible",
    ),
    Rule(
        "before_inception", has("fail_starts_before_inception"), SKIP,
        "the term starts before the office existed",
    ),
    Rule(
        "january_first", has("fail_january_first_placeholder"), SKIP,
        "a day-precise 1 January is a year-precision import, not a birthday",
    ),
    # 5. One channel is not two. `dob_one_channel` is the measured gate from
    #    `tasks/birthdates.md`: the infobox against the article's own births
    #    category, which different editors maintain.
    Rule(
        "dob_conflict", has("fail_dob_disagrees_with_category",
                            "fail_dob_disagrees_with_infobox"), SKIP,
        "the birth date disagrees with the article's own category or infobox",
    ),
    Rule(
        "dob_one_channel", has("fail_dob_no_cross_check",
                               "fail_dob_category_flagged_uncertain"), SKIP,
        "no births category to confirm the date the prose states",
    ),
    Rule(
        "unresolvable_value", has("fail_country_unresolved",
                                  "fail_gender_unrecognised"), SKIP,
        "the named value did not resolve to an item",
    ),
    Rule(
        "unnamed_office", has("fail_unresolved_without_a_name"), SKIP,
        "no QID and no office name — nothing to act on or to create",
    ),
    # 6. An office the run could not offer an item for. Not a failure and not a
    #    statement: a byproduct list, carrying an attested holder and a quote.
    #    Whether an item exists is a separate question — `wd/positions.py` answers
    #    it, and only a genuine miss is a creation candidate.
    Rule(
        "office_unresolved", has("office_unresolved"), BYPRODUCT,
        "the office is named but this run offered no item for it",
    ),
    # 7. The model's own hedge, honoured. Nothing is relaxed to raise a count.
    Rule(
        "low_confidence", has("low_confidence"), SKIP,
        "the model reported it for a human to look at",
    ),
    # 8. Several dated terms against one undated statement. QuickStatements
    #    would merge them all into it; the API would leave it standing beside
    #    them. Either way the undated statement has to go, and removal is the
    #    human gate — so this is a surgical list, not a batch line.
    Rule(
        "undated_needs_removal", has("several_terms"), BYPRODUCT,
        "several dated terms against one undated statement — remove it first",
    ),
    # 9. Now the applying rules, specific before general — the general one last
    #    or it swallows the tiers and drops their qualifiers.
    #
    #    `dates_existing_statement` precedes `dated_tenure` because it is the
    #    same edit with a different meaning: the statement is already there and
    #    undated, so no Occupancy can be produced from it at all, and a
    #    QuickStatements line merges the dates into it rather than adding a
    #    second statement. This is the largest single class of fix the loop
    #    finds — 31 of 42 recorded Sejm seats.
    Rule(
        "dates_existing_statement",
        has("undated_statement"), APPLY,
        "the office is recorded undated; the dates make it emittable",
    ),
    Rule(
        "acting", has("acting"), APPLY,
        "an acting or interim spell, applied with P2868 = Q4676846",
        qualifiers={"P2868": "Q4676846"},
    ),
    Rule(
        "dated_tenure", has("gazetteer_hit"), APPLY,
        "the office is in the gazetteer and the quote checks out",
    ),
    Rule(
        "birth_date", has("dob_two_channel"), APPLY,
        "the infobox and the births category agree",
    ),
    Rule(
        "citizenship", has("country_resolved"), APPLY,
        "the country named resolved to an item",
    ),
    #: P21 moves nothing downstream — `zavod` reads it nowhere. Applied because
    #: Wikidata wants it, and kept its own rule so a run can report it as the
    #: Wikidata-quality lane it is rather than as PEP yield.
    Rule(
        "gender_wikidata_only", has("wikidata_only"), APPLY,
        "a Wikidata-quality statement; no OpenSanctions record moves",
    ),
    # 9. Terminal. Every case gets a disposition and this one is a skip with a
    #    reason, not a queue.
    Rule(
        "unmatched", always, SKIP,
        "no applying rule matched this proposal",
    ),
)
