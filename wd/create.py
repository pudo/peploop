"""Build a well-formed position item from an office's parameters.

Reach for this when a campaign finds holders with nowhere to put them — the
Czech run found 45 supreme-court judges and four ministerial portfolios with no
Wikidata item at all, and every one of those statements was unwritable for want
of a target. Creating the item is a small, mechanical job that this workbench
kept recording as a byproduct list nobody worked through.

An **archetype** is what makes it mechanical. Rather than each country
describing a position item field by field, it names the kind of office and the
body it belongs to, and the archetype supplies the shape. The shapes were read
off seven well-curated Czech position items: `P31`, `P279`, `P17` and `P1001`
appear on all of them, `P361` (part of the ministry or court), `P2354` (has
list — the roster article itself), `P571` and `P2521` on most.

Creation is the least reversible thing the workbench does — undoing it needs a
deletion or a merge, both reserved for a human — so `guard` refuses to build a
payload that has not survived a duplicate search.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

#: P31 for every position item; the archetype narrows it with P279.
POSITION = "Q4164871"


@dataclass(frozen=True)
class Archetype:
    """The shape of one kind of office."""

    #: Superclass — "minister", "judge", "member of parliament".
    parent: str
    #: How the body relates to the office, when the profile names one.
    body_property: str = "P361"
    #: English description template; `{body}` and `{country}` are filled in.
    description: str = "position in {country}"


ARCHETYPES: Dict[str, Archetype] = {
    "minister": Archetype(
        parent="Q83307",
        description="minister in the government of {country}",
    ),
    "judge": Archetype(
        parent="Q16533",
        description="judge of {body}",
    ),
    "supreme_judge": Archetype(
        parent="Q117826617",
        description="judge of {body}",
    ),
    "legislator": Archetype(
        parent="Q4175034",
        description="member of {body}",
    ),
    "head_of_state": Archetype(
        parent="Q48352",
        description="head of state of {country}",
    ),
    "head_of_government": Archetype(
        parent="Q2285706",
        description="head of government of {country}",
    ),
    "ambassador": Archetype(
        parent="Q121998",
        description="diplomatic post of {country}",
    ),
    # A *bilateral* posting names both ends, and the two are not
    # interchangeable: measured over ten "ambassador of Qatar to X" items, `P17`
    # is the receiving state and the sending country appears only through
    # `P279`. The shape is reached with `claims_override`; this archetype exists
    # for the description, because "diplomatic post of Qatar" repeated across
    # twenty-one items says nothing about which posting each one is.
    "bilateral_ambassador": Archetype(
        parent="Q121998",
        description="diplomatic post of {country} in {jurisdiction}",
    ),
    "agency_head": Archetype(
        parent="Q1162163",
        description="head of {body}",
    ),
    # Measured off the fourteen emirate-office items that already exist rather
    # than chosen: all seven Rulers carry `P279 = Q166382` (Amir), and six of
    # the seven relate to the Federal Supreme Council — the body whose members
    # they are — through P361.
    "ruler": Archetype(
        parent="Q166382",
        description="hereditary ruler of {jurisdiction}",
    ),
    # Q125497756, Q30635458 and Q22935234 all use `P279 = Q207293`, and none
    # names a body: an heir apparent belongs to the emirate, not to an organ of
    # it, so `body` is left unset for this shape.
    "heir_apparent": Archetype(
        parent="Q207293",
        description="heir apparent in {jurisdiction}",
    ),
    # A deputy ruler is emphatically *not* an Amir, so this cannot reuse
    # `ruler`. The two existing items disagree with each other — Q123117007
    # (Sharjah) says Q3250324 "deputy", Q106181563 (Dubai) says Q42178 "vice
    # president" — and neither is the counterpart of Amir. Q3250324 is the less
    # wrong of the two and is the convention here; four of the seven emirates
    # have no deputy-ruler item at all and take this shape when created.
    "deputy_ruler": Archetype(
        parent="Q3250324",
        description="deputy ruler of {jurisdiction}",
    ),
    # Measured off the eight Saudi provincial governorships that already exist
    # rather than chosen: every one of them carries `P279 = Q98786082` ("emir of
    # province", itself an Amir and a military-officer subclass) and scopes
    # itself to its province through P1001. The `agency_head` shape would have
    # given the five missing ones `P279 = Q1162163` ("director") and made them a
    # different kind of thing from their own siblings.
    # Not the same shape as `provincial_governor`, which is an Amir. Measured
    # over the 242 worldwide items with `P279 = Q132050` and `P31 = Q4164871`:
    # 185 carry `P1001` and **172 of those scope strictly narrower than their
    # own `P17`** — the convention is not "province vs country" but *scope to
    # the polity governed*. The thirteen that scope nationally are offices whose
    # governed polity genuinely is the country (Governor of Cuba, Ban, King's
    # Commissioner). Iraq reached for `provincial_governor` and overrode its
    # parent and inception to get here (`iq_offices.py:329`); a second country
    # patching the same field is a missing archetype, not a clever workaround.
    "governor": Archetype(
        parent="Q132050",
        description="governor of {jurisdiction}",
    ),
    # Q30185 is the office itself rather than a class of it, and is what the
    # existing municipal items subclass.
    "mayor": Archetype(
        parent="Q30185",
        description="mayor of {jurisdiction}",
    ),
    "provincial_governor": Archetype(
        parent="Q98786082",
        description="governor of {jurisdiction}",
    ),
}


@dataclass
class CreateSpec:
    """Everything needed to mint one position item."""

    #: Stable key, so a re-run recognises an item it already created.
    ref: str
    archetype: str
    labels: Dict[str, str]
    country_qid: str
    country_label: str = ""
    #: The polity the office actually governs, when that is narrower than the
    #: country: `P17` stays the sovereign state while `P1001` names the
    #: subdivision. A Ruler of Ajman is an office of the UAE (Q878) whose
    #: jurisdiction is the emirate (Q159477), and OpenSanctions reads exactly
    #: this pair — country from `P17`, `subnationalArea` from a `P1001` whose
    #: territory is not itself a country. Defaults to the country.
    jurisdiction: Optional[str] = None
    #: The prose form for the description, so pass the short name ("Sharjah",
    #: not "Emirate of Sharjah") — the templates read "…of {jurisdiction}" and
    #: the long form makes "heir apparent in Emirate of Sharjah".
    jurisdiction_label: str = ""
    #: The ministry, court or chamber the office belongs to.
    body: Optional[str] = None
    body_label: str = ""
    #: The roster article's own item, for P2354 "has list".
    list_item: Optional[str] = None
    #: Earliest term seen on the roster, as the office's inception.
    inception: Optional[str] = None
    descriptions: Dict[str, str] = field(default_factory=dict)
    #: Why this office is believed to exist, for the edit summary.
    attested_by: str = ""
    holders: int = 0
    #: Base claims to override, as `(property, value)`. A value of `None`
    #: removes the property the defaults would have written; a list writes
    #: several values.
    #:
    #: Needed because the defaults below encode one shape — a *national* office
    #: whose country and jurisdiction are the campaign's own — and not every
    #: office is one. An outbound ambassadorship inverts it: measured over ten
    #: exemplars, `P17` is the **receiving** state and never the sending one,
    #: `P279` carries two parents (the sending country's ambassador class and
    #: the receiving state's), and `P1001` is used by two of the ten and so is
    #: not asserted at all. Writing those through the defaults would put Qatar
    #: in the receiving state's slot on every item minted.
    claims_override: Tuple[Tuple[str, object], ...] = ()


def payload(spec: CreateSpec) -> dict:
    """The `wb create-entity` JSON for this office.

    One atomic call carries labels, descriptions and every base statement — a
    QuickStatements CREATE plus a dozen LAST lines can half-fail and leave a
    malformed item behind, which is the other reason creation does not go
    through the batch.
    """
    archetype = ARCHETYPES[spec.archetype]
    claims: Dict[str, object] = {
        "P31": POSITION,
        "P279": archetype.parent,
        "P17": spec.country_qid,
        # Applies-to-jurisdiction is what makes the item findable as *this*
        # country's office rather than a generic one — or as *this subdivision's*
        # where the office is not national.
        "P1001": spec.jurisdiction or spec.country_qid,
    }
    if spec.body:
        claims[archetype.body_property] = spec.body
    if spec.list_item:
        # The roster this campaign read is the office's list article, and
        # saying so links the item to its own provenance.
        claims["P2354"] = spec.list_item
    if spec.inception:
        claims["P571"] = _time(spec.inception)
    for prop, value in spec.claims_override:
        if value is None:
            claims.pop(prop, None)
        else:
            claims[prop] = value

    country = spec.country_label or spec.country_qid
    descriptions = dict(spec.descriptions)
    descriptions.setdefault(
        "en",
        archetype.description.format(
            country=country,
            body=spec.body_label or country,
            jurisdiction=spec.jurisdiction_label or country,
        ),
    )
    return {
        "labels": dict(spec.labels),
        "descriptions": descriptions,
        "claims": claims,
    }


def _time(iso: str) -> dict:
    """A partial ISO date in the shape wikibase-cli expects."""
    precision = {1: 9, 2: 10, 3: 11}[min(len(iso.split("-")), 3)]
    parts = (iso.split("-") + ["01", "01"])[:3]
    return {
        "time": f"+{parts[0]}-{parts[1]}-{parts[2]}T00:00:00Z",
        "precision": precision,
    }


#: Types that disqualify a candidate from being the office a spec describes,
#: whatever its label says. Both were found by the Iran governor lane's first
#: dry run, and neither is exotic: `استاندار کرمان` matched `Q19793882`, a
#: **Wikinews headline** that begins with the office's name, and `استاندار
#: البرز` matched `Q64759749`, **a human** carrying the office as an alias.
#: The second is the dangerous one — a person has no `P17`, so they arrive
#: through the same "asserts no country" branch that `label-only` needs.
#:
#: A denylist rather than a `P31 = Q4164871` requirement, because a real
#: position's type can sit behind a preferred or deprecated rank and a positive
#: test would reject it (see the `wdt:` gotcha). Nothing here is ever also a
#: position.
NOT_A_POSITION = {
    "Q5",          # human
    "Q4167836",    # Wikimedia category
    "Q4167410",    # Wikimedia disambiguation page
    "Q11266439",   # Wikimedia template
    "Q17633526",   # Wikinews article
    "Q13442814",   # scholarly article
}
#: A Wikimedia list article, which `lookup_position` already refuses to match
#: strongly. Excluded only when it is *purely* a list: an item typed as both a
#: list and something else is left to block creation, because a false duplicate
#: costs a manual check and a missed one mints an item nobody can un-mint.
LIST_ARTICLE = "Q13406463"


def duplicate_of(found) -> Optional[str]:
    """A QID this spec would duplicate, if any — judged from the candidates.

    Reach for this instead of reading `Lookup.status`. `lookup_position` sets
    `matched` only when exactly one *strong* candidate exists, so two items
    that both match the label and the country come back `ambiguous` and a
    status test mints a third. `label-only` is worse: a unique label match on
    an item carrying no country property at all, with its QID sitting right
    there in `resolved_qid`.

    A candidate must also be a plausible *position*: see `NOT_A_POSITION`.

    Trusting `ambiguous` wholesale is not the fix either — it is the default
    for any search that returned candidates, and would refuse nearly every
    creation. So judge the candidates: a duplicate is one whose label matches,
    which is not a pure list article, and which either agrees on country or
    asserts no country at all. An item labelled the same in a *different*
    country is a different office and does not block.
    """
    for candidate in getattr(found, "candidates", ()) or ():
        types = set(candidate.types or ())
        if not candidate.label_match or types & NOT_A_POSITION:
            continue
        if types == {LIST_ARTICLE}:
            continue
        if candidate.country_match or not candidate.country_qids:
            return candidate.qid
    return None


def guard(
    spec: CreateSpec, lookup, label_of=None, min_holders: int = 2
) -> List[str]:
    """Reasons not to create this item. Empty means it may be created.

    `lookup` is `wd.positions.lookup_position` or anything with its shape: it
    already does two-signal name-and-country matching and already refuses to
    match list articles, so the duplicate search reuses it rather than
    inventing a second, worse one.

    `label_of` resolves a QID to its label, and exists because a hand-written
    `body` is the easiest thing in a profile to get wrong and the hardest to
    notice: the first two written for the Czech courts were a Spanish
    construction brand and a character from the Nibelungenlied, and nothing
    downstream would have objected. A body whose label shares no word with the
    office's own is refused.
    """
    problems: List[str] = []
    if spec.archetype not in ARCHETYPES:
        problems.append(f"unknown archetype {spec.archetype!r}")
    if not spec.labels.get("en"):
        problems.append("no English label")
    if spec.holders < min_holders:
        problems.append(
            f"only {spec.holders} attested holder(s); {min_holders} required"
        )
    for language, label in spec.labels.items():
        found = lookup(label, spec.country_qid)
        if found:
            problems.append(
                f"an item already matches the {language} label: {found}"
            )
            break
    if spec.body and label_of is not None:
        body_label = label_of(spec.body)
        if not body_label:
            problems.append(f"body {spec.body} has no label — does it exist?")
        elif not _shares_a_word(body_label, spec.labels):
            problems.append(
                f"body {spec.body} is {body_label!r}, which shares no word "
                f"with the office's own name — wrong QID?"
            )
    return problems


#: Words too common to count as agreement between an office and its body.
_STOPWORDS = {
    "of", "the", "de", "la", "for", "and", "a", "an", "in", "judge", "member",
    "minister", "head", "chief", "republic", "czech", "national", "state",
}


def _shares_a_word(body_label: str, labels: Dict[str, str]) -> bool:
    body_words = {
        w for w in "".join(
            c.lower() if c.isalnum() else " " for c in body_label
        ).split() if w not in _STOPWORDS and len(w) > 2
    }
    for label in labels.values():
        office_words = {
            w for w in "".join(
                c.lower() if c.isalnum() else " " for c in label
            ).split() if w not in _STOPWORDS and len(w) > 2
        }
        if body_words & office_words:
            return True
    return False


def summary(spec: CreateSpec) -> str:
    """Edit summary, naming the evidence rather than the tool."""
    return (
        f"create position item for {spec.labels.get('en', spec.ref)}"
        + (f"; {spec.holders} holders attested by {spec.attested_by}"
           if spec.attested_by else "")
    )
