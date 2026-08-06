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
from typing import Dict, List, Optional

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
    "agency_head": Archetype(
        parent="Q1162163",
        description="head of {body}",
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
        # country's office rather than a generic one.
        "P1001": spec.country_qid,
    }
    if spec.body:
        claims[archetype.body_property] = spec.body
    if spec.list_item:
        # The roster this campaign read is the office's list article, and
        # saying so links the item to its own provenance.
        claims["P2354"] = spec.list_item
    if spec.inception:
        claims["P571"] = _time(spec.inception)

    descriptions = dict(spec.descriptions)
    descriptions.setdefault(
        "en",
        archetype.description.format(
            country=spec.country_label or spec.country_qid,
            body=spec.body_label or (spec.country_label or spec.country_qid),
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
