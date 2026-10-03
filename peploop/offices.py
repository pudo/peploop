"""Decide what a missing office's item looks like, and whether it may be minted.

Reach for this when an article names an office Wikidata has no item for: the
holders it attests have nowhere to put their `P39` until one exists. Creating
an item is the least reversible thing peploop does -- undoing it needs a
deletion or a merge -- so the shape is fixed per kind of office rather than
drafted per item, and `guard` names every reason not to create before anything
is sent.

The rules are pure: the live reads they judge (duplicate searches, the body and
jurisdiction records, the sibling tallies, the type closure) are passed in, so
each one can be pinned offline in `check_mint`. The reads themselves sit in the
last section, all of them live.
"""

import re
import string
from collections import Counter
from dataclasses import dataclass, field, replace
from datetime import date
from typing import Any, Callable, Collection, Iterable, Sequence

from peploop import apply, db, http, positions, wikidata
from peploop.positions import NOT_AN_OFFICE, POSITION_METACLASSES, fold, tokens

#: What every office reaches through its `P279` chain.
POSITION = "Q4164871"
#: The metaclass most offices declare: 85% of ministers use it, against 14%
#: for `Q4164871` itself. The last fallback of `metaclass_for`.
PUBLIC_OFFICE = "Q294414"
#: Metaclasses that are true of some offices and wrong for a seat minted
#: because someone holds it now.
NOT_MINTABLE = {
    "Q114962596",  # historical position
    "Q355567",  # noble title
}
MINTABLE_METACLASSES = POSITION_METACLASSES - NOT_MINTABLE


@dataclass(frozen=True)
class Archetype:
    """The shape of one kind of office, so an item is never drafted field by field."""

    #: The kind of office, written as `P279`: "minister", "judge", "mayor".
    parent: str
    #: How the office points at the body it is a seat in.
    body_property: str = "P361"
    #: English description; `{body}`, `{jurisdiction}` and `{state}` are filled
    #: from resolved labels by `describe`.
    description: str = "public office in {jurisdiction}"
    #: One holder at a time, so one current holder plus an official source can
    #: stand in for the two-person floor.
    single_seat: bool = False
    #: Whether `P1001` is written. An office governs a polity; a company's
    #: chair does not.
    scoped: bool = True
    #: The level of polity the office governs: the state itself, one of its
    #: first-level subdivisions (`P150`), or a municipality below them. A
    #: mayor scoped to the state, or to the department its town sits in, is
    #: the default a missing jurisdiction falls to, and reads as plausible.
    level: str = "state"
    #: The description when a `{body}` template has no body to name: what the
    #: office is, said of the polity instead. None where no such sentence is
    #: true of every office of the kind, and `describe` then refuses.
    unbodied: str | None = None


ARCHETYPES: dict[str, Archetype] = {
    "minister": Archetype("Q83307", description="minister in the government of {jurisdiction}"),
    "legislator": Archetype("Q4175034", description="member of the {body}",
                            unbodied="member of a legislature of {jurisdiction}"),
    "judge": Archetype("Q16533", description="judge of the {body}",
                       unbodied="judge in {jurisdiction}"),
    "supreme_judge": Archetype("Q117826617", description="judge of the {body}",
                               unbodied="judge of a superior court of {jurisdiction}"),
    # Scoped to the polity governed, not the state: of 185 governorships with a
    # `P1001`, 172 name something narrower than their own `P17`.
    "governor": Archetype("Q132050", description="governor of {jurisdiction}", single_seat=True,
                          level="region"),
    # `Q30185` is the office itself rather than a class of it, and is what the
    # existing municipal items subclass.
    "mayor": Archetype("Q30185", description="mayor of {jurisdiction}", single_seat=True,
                       level="municipality"),
    # One person heads an agency at a time, so a census entry is a second
    # channel for it like for any other one-seat office.
    "agency_head": Archetype("Q1162163", description="head of the {body}", single_seat=True,
                             unbodied="head of a public body of {jurisdiction}"),
    # The presiding officer of a chamber: 84 of 96 speakerships measured use
    # `Q1758037`, and a state's existing one names its chamber under `P2389`.
    # A deputy speaker is not a speaker and has no archetype.
    "speaker": Archetype(
        "Q1758037", body_property="P2389", description="presiding officer of the {body}",
        single_seat=True, unbodied="presiding officer of a chamber of {jurisdiction}",
    ),
    # The parents below were measured across other states' items (P279 tallies
    # and the parents read in full); see research/position_items.md §10.
    # A seat in a party's standing politburo. Membership of a large organ (a
    # central committee) is recorded as `P463` on the body by a wide margin, so
    # it has no archetype and is never minted as a seat.
    # The body is usually the party: few parties' bureaus have items of their
    # own, and "member of {party}" would read as party membership.
    "politburo_member": Archetype(
        "Q115136557", description="member of the political bureau of the {body}",
        unbodied="member of a party's political bureau in {jurisdiction}"),
    # A seat in a collegial organ of the state (a council of state, a
    # presidium). The only recurring class, and a weak one: prefer a sibling's.
    "state_body_member": Archetype("Q16862850", description="member of the {body}",
                                   unbodied="member of a state body of {jurisdiction}"),
    "party_secretary": Archetype("Q836971", description="party office in the {body}", single_seat=True,
                                 unbodied="party office in {jurisdiction}"),
    # "Chief of defence", a subclass of chief of staff, is what 70% of typed
    # items use; the general staff is named under `P2389`, not `P361`.
    "military_chief_of_staff": Archetype(
        "Q5097014", body_property="P2389", description="head of the {body}", single_seat=True,
        unbodied="military command in {jurisdiction}",
    ),
    # "Chief justice", a subclass of court president, is the plurality for apex
    # courts and the one every Latin American presidency uses.
    "court_president": Archetype(
        "Q3188089", body_property="P2389", description="president of the {body}", single_seat=True,
        unbodied="president of a court of {jurisdiction}",
    ),
    # The class follows the title word (director general, chair, president);
    # director general is the default and a sibling's or the drafted parent
    # from `SOE_PARENTS` may replace it. Never "chief executive officer": it is
    # typed as an occupation. A company's head governs no polity.
    "soe_head": Archetype(
        "Q1501800", body_property="P2389", description="head of the {body}", single_seat=True,
        scoped=False, unbodied="head of a state enterprise of {state}",
    ),
    "central_bank_governor": Archetype(
        "Q107363151", body_property="P2389", description="governor of the {body}", single_seat=True,
        unbodied="central bank governor of {jurisdiction}",
    ),
    "prosecutor_general": Archetype(
        "Q3368517", description="prosecutor general of {jurisdiction}", single_seat=True,
    ),
}

#: Classes a polity reaching which (through `P31`/`P279`) is a municipality,
#: whatever level of the state's subdivisions it sits at. Measured over eight
#: states' `P150` lists: a borough and a city can be first-level subdivisions,
#: and their mayors are still mayors of a town. A department, a province, a
#: region or a county reaches none of these.
MUNICIPAL_CLASSES = frozenset({
    "Q15284",    # municipality
    "Q515",      # city
    "Q5195043",  # borough
    "Q3957",     # town
    "Q7930989",  # city or town
})

#: The parents an enterprise head may take by its title word: director general,
#: chairperson, president.
SOE_PARENTS = ("Q1501800", "Q140686", "Q1255921")

#: Types a duplicate-search hit can carry that make it not the office, whatever
#: its label says: a human holding the office as an alias, a news headline
#: that begins with the office's name. A denylist rather than a position test,
#: because a real position's type can sit behind a preferred or deprecated rank.
NOT_A_POSITION = {
    "Q5",  # human
    "Q4167836",  # Wikimedia category
    "Q4167410",  # Wikimedia disambiguation page
    "Q11266439",  # Wikimedia template
    "Q17633526",  # Wikinews article
    "Q13442814",  # scholarly article
}
#: A list of holders. Not a duplicate when it is *only* a list; an item typed
#: as a list and something else still blocks, because a false duplicate costs
#: a skip and a missed one mints an item nobody can un-mint.
LIST_ARTICLE = "Q13406463"

QID = re.compile(r"\bQ\d+\b")

#: An outbound or inbound posting names two states, and its shape inverts the
#: ordinary office's (`P17` is the receiver, there is no `P1001`), so none of
#: the archetypes above fits it. Matched on folded text, so a transliterated
#: label is read too. The prepositions are what separate "ambassador of X to Y"
#: from an ambassador-at-large.
BILATERAL = re.compile(
    r"\b(ambassador|ambassadeur|ambasador|ambasciatore|embajador|embaixador|botschafter"
    r"|velvyslanec|veleposlanik|posol|nuncio|high commissioner"
    r"|permanent representative|representante permanente|representant permanent)\b"
    r".*\b(to|en|in|au|aux|a|al|ante|bei|presso|junto|v|ve|pri|w|na)\b"
)

#: Words an office and the wrong body share all the time: "Minister of X" and
#: "Ministry of Y", "Governor" and "Government". Compared on the same prefix
#: the search index uses, so one stem covers its spellings across languages.
ROLE_WORDS = """
minister ministry member miembro membre judge juez juge head chief jefe chef
president secretary secretario director general governor government deputy
diputado vice first second national nacional republic state estado people
""".split()
ROLE_STEMS = frozenset(word[: positions.PREFIX] for word in ROLE_WORDS)


@dataclass
class Spec:
    """One office as it would be minted: every field a payload is built from."""

    #: Stable key, so a re-run recognises an office it already decided.
    ref: str
    archetype: str
    labels: dict[str, str]
    state_qid: str
    aliases: dict[str, list[str]] = field(default_factory=dict)
    descriptions: dict[str, str] = field(default_factory=dict)
    metaclass: str = PUBLIC_OFFICE
    #: The kind of office; the archetype's own parent when the siblings agree
    #: on nothing narrower.
    parent: str | None = None
    #: The polity the office governs, when narrower than the state.
    jurisdiction_qid: str | None = None
    #: The ministry, court, chamber or organ the office is a seat in.
    body_qid: str | None = None
    #: The office this one renamed, written as `P1365`.
    replaces: str | None = None

    @property
    def shape(self) -> Archetype:
        return ARCHETYPES[self.archetype]

    @property
    def kind(self) -> str:
        return self.parent or self.shape.parent

    @property
    def jurisdiction(self) -> str:
        return self.jurisdiction_qid or self.state_qid


def _item(qid: str) -> dict[str, str]:
    return {"entity-type": "item", "id": qid}


def _statement(prop: str, qid: str) -> dict[str, Any]:
    """A structural claim: no qualifiers, and no references by community practice."""
    return {"type": "statement", "rank": "normal", "mainsnak": apply._snak(prop, _item(qid))}


def _terms(texts: dict[str, str]) -> dict[str, dict[str, str]]:
    return {lang: {"language": lang, "value": text} for lang, text in texts.items()}


def entity_data(spec: Spec) -> dict[str, Any]:
    """The `wbeditentity` `data` blob that creates this office in one atomic edit."""
    claims = [
        _statement("P31", spec.metaclass),
        _statement("P279", spec.kind),
        _statement("P17", spec.state_qid),
    ]
    if spec.shape.scoped:
        claims.append(_statement("P1001", spec.jurisdiction))
    if spec.body_qid:
        claims.append(_statement(spec.shape.body_property, spec.body_qid))
    if spec.replaces:
        claims.append(_statement("P1365", spec.replaces))
    return {
        "labels": _terms(spec.labels),
        "aliases": {
            lang: [{"language": lang, "value": text} for text in texts]
            for lang, texts in spec.aliases.items() if texts
        },
        "descriptions": _terms(spec.descriptions),
        "claims": claims,
    }


def describe(spec: Spec, labels_of: dict[str, str]) -> str | None:
    """The English description, or None when a label it needs is unresolved.

    A description reading "governor of Q12345" is worse than none, so a
    missing label, or one that is itself a QID, refuses rather than degrades.
    A body-templated office with no body is described by its polity instead,
    where the archetype says how (`Archetype.unbodied`): a party leadership
    whose party has no item is still a party office in its state.
    """
    slots = {"body": spec.body_qid, "jurisdiction": spec.jurisdiction, "state": spec.state_qid}
    template = spec.shape.description
    if "{body}" in template and not spec.body_qid and spec.shape.unbodied:
        template = spec.shape.unbodied
    wanted = {name for _text, name, _spec, _conv in string.Formatter().parse(template) if name}
    values: dict[str, str] = {}
    for name in wanted:
        label = labels_of.get(slots.get(name) or "")
        if not label or QID.search(label):
            return None
        values[name] = label
    return template.format(**values)


@dataclass(frozen=True)
class Found:
    """One hit of a live duplicate search, as `duplicate_of` judges it."""

    qid: str
    #: Its labels and aliases, every language.
    names: frozenset[str] = frozenset()
    #: A label or alias of the hit equals one of the spec's, folded.
    label_match: bool = False
    #: The hit's `P17`/`P1001` names the spec's state.
    country_match: bool = False
    country_qids: tuple[str, ...] = ()
    #: The hit's declared `P31`, every rank but deprecated.
    types: frozenset[str] = frozenset()
    #: Other offices name the hit as their `P279`: it is a kind of office
    #: ("president of the senate"), not one. Read only for a stateless hit.
    is_class: bool = False
    #: The searched names, folded, that matched one of the hit's.
    matched: frozenset[str] = frozenset()
    #: The hit is typed as an organisation and not as an office: a council,
    #: a ministry, a party. Read only for a hit whose name matched.
    is_body: bool = False


def names_state(text: str, state_names: Iterable[str]) -> bool:
    """Whether a name says which state it is: one of the state's names, as a phrase."""
    folded = _phrase(text)
    return any(_phrase(name).strip() and _phrase(name) in folded for name in state_names)


def _phrase(text: str) -> str:
    """A name as its folded words between spaces, so a phrase test matches whole words."""
    return f" {' '.join(re.findall(r'[a-z0-9]+', fold(text)))} "


#: Words two renderings of one title differ by without naming another
#: seat: a minister of state "at" or "in" the ministry is one office.
LABEL_STOPWORDS = frozenset({"at", "in", "of", "the"})


def label_key(text: str) -> str:
    """A label folded to what makes two renderings of one title the same."""
    return " ".join(w for w in _phrase(text).split() if w not in LABEL_STOPWORDS)


def without_state(text: str, state_names: Iterable[str]) -> str:
    """A name with every one of the state's names taken out of it as a whole phrase."""
    out = _phrase(text)
    for name in sorted({_phrase(n) for n in state_names if _phrase(n).strip()}, key=len, reverse=True):
        out = out.replace(name, " ")
    return out


#: What a body reaches through `P31`/`P279`: organization.
ORGANISATION = "Q43229"


def body_hit(found: Iterable[Found], bodies: Collection[str] = ()) -> str | None:
    """A hit matching the office's name that is a body, not an office.

    The office's own body, or the census anchor's, or anything typed as an
    organisation: an article alias naming the council the seat is in finds
    the council. That is not a duplicate -- no office would be minted twice --
    but a name of the body is about to be written onto the seat, and the
    guard says so under its own name.
    """
    for hit in found:
        if hit.label_match and (hit.qid in bodies or hit.is_body):
            return hit.qid
    return None


def duplicate_of(found: Iterable[Found], state_names: Iterable[str] = ()) -> str | None:
    """The item this office would duplicate, judged hit by hit.

    A search's own status is not enough: two hits that both match come back
    ambiguous and a status test mints a third. A duplicate is a hit whose name
    matches, that is not a human, a page or a pure list, and that names the
    same state or no state at all. The same title in another state is another
    office.

    `state_names` are passed when the office's own label names its state.
    Then a stateless hit matched only by a bare title -- "Commissioner of
    Police", the alias an article wrote -- is the generic title, not this
    office: it would block every state's commissioner. Matched by a name that
    says the state, it still blocks.
    """
    state_names = list(state_names)
    for hit in found:
        if not hit.label_match or hit.types & NOT_A_POSITION:
            continue
        if hit.types == {LIST_ARTICLE}:
            continue
        if hit.country_match:
            return hit.qid
        # A stateless hit is this office with its state left out, unless
        # other offices subclass it: then it is the kind, which a state's
        # own seat is a subclass of rather than a duplicate of.
        if not hit.country_qids and not hit.is_class:
            if state_names and hit.matched and not any(
                    names_state(text, state_names) for text in hit.matched):
                continue
            return hit.qid
    return None


@dataclass
class Siblings:
    """How a state's own offices are typed, so a minted one looks like them."""

    #: Per archetype, the `P279` values of the state's offices that reach its
    #: parent: a state whose governors are all a narrower kind gets that kind.
    parents: dict[str, Counter[str]] = field(default_factory=dict)
    #: Per `P279` value, the metaclasses of the state's offices that declare it.
    metaclass_by_parent: dict[str, Counter[str]] = field(default_factory=dict)
    #: The metaclasses of all the state's offices.
    metaclasses: Counter[str] = field(default_factory=Counter)
    #: The bodies (`P361`/`P2389`) the state's offices are seats in.
    bodies: Counter[str] = field(default_factory=Counter)
    #: Per archetype, the bodies its offices name under the archetype's own
    #: body property: what `body_for` drafts a body from.
    bodies_by_archetype: dict[str, Counter[str]] = field(default_factory=dict)
    #: How many current offices were tallied, and how many carry a label in
    #: each language: what `label_langs` measures the guard's languages by.
    offices: int = 0
    label_langs: Counter[str] = field(default_factory=Counter)


def _mode(tally: Counter[str] | None) -> str | None:
    """The single most common mintable metaclass, or None on a tie or nothing."""
    ranked = [(qid, n) for qid, n in (tally or Counter()).most_common() if qid in MINTABLE_METACLASSES]
    if not ranked or (len(ranked) > 1 and ranked[0][1] == ranked[1][1]):
        return None
    return ranked[0][0]


def label_langs(siblings: Siblings, langs: Sequence[str], share: float = 0.5) -> list[str]:
    """The state languages a minted office must be labelled in, besides English.

    The ones at least `share` of the state's own offices are labelled in. A
    territory's official languages are not the languages its items are
    written in: one state's thirty-odd offices carried no label in its
    national language, and requiring one made a model draft it, badly -- "the
    government of X" as the label of X's governor. With no siblings to measure,
    every language is required, which is the conservative answer.
    """
    if not siblings.offices:
        return list(langs)
    return [lang for lang in langs if siblings.label_langs[lang] >= share * siblings.offices]


def metaclass_for(siblings: Siblings, parent: str) -> str:
    """The `P31` this state's offices of the same kind use, else its usual one."""
    return _mode(siblings.metaclass_by_parent.get(parent)) or _mode(siblings.metaclasses) or PUBLIC_OFFICE


def body_for(siblings: Siblings, archetype: str, min_agree: int | None = None) -> str | None:
    """The body the state's offices of this kind are seats in, when they agree on one.

    A draft often names no body, and an office minted without one sits in
    nothing its siblings sit in: one state's ministers of state all name the
    cabinet. The most common body of the archetype, when at least `min_agree`
    offices name it (`MEASURED_BODY_USES` by default) and no other is named
    as often; None otherwise.
    """
    min_agree = MEASURED_BODY_USES if min_agree is None else min_agree
    ranked = (siblings.bodies_by_archetype.get(archetype) or Counter()).most_common(2)
    if not ranked or ranked[0][1] < min_agree or (len(ranked) > 1 and ranked[1][1] == ranked[0][1]):
        return None
    return ranked[0][0]


def parent_for(siblings: Siblings, archetype: str, min_agree: int = 2, share: float = 2 / 3) -> str:
    """The `P279` the state's own offices of this kind agree on, else the archetype's."""
    tally = siblings.parents.get(archetype) or Counter()
    total = sum(tally.values())
    for qid, n in tally.most_common(1):
        if n >= min_agree and n / total >= share and qid not in POSITION_METACLASSES:
            return qid
    return ARCHETYPES[archetype].parent


Closure = Callable[[str], bool] | Collection[str]


def _reaches(closure: Closure, qid: str) -> bool:
    return closure(qid) if callable(closure) else qid in closure


def shape_defects(spec: Spec, closure: Closure) -> list[str]:
    """What would make the minted item one of Wikidata's own modelling defects.

    `closure` answers whether a class reaches `Q4164871`: a set of the QIDs
    that do, or a callable that asks the live type closure.
    """
    if spec.archetype not in ARCHETYPES:
        return [f"archetype/{spec.archetype}"]
    defects = []
    if spec.metaclass not in MINTABLE_METACLASSES:
        defects.append(f"metaclass/{spec.metaclass}")
    if spec.kind in POSITION_METACLASSES:
        defects.append("untyped")
    elif spec.kind in NOT_AN_OFFICE or spec.kind in NOT_A_POSITION:
        defects.append(f"not-an-office/{spec.kind}")
    elif not _reaches(closure, spec.kind):
        defects.append(f"unreached/{spec.kind}")
    if spec.replaces and spec.replaces == spec.body_qid:
        defects.append("replaces-body")
    return defects


def distinct_holders(rows: Iterable[dict[str, Any]], key: str = "person") -> int:
    """How many different people some attestations name.

    The floor counts people, not rows: one minister mentioned in three articles
    is one holder, and three rows would clear a floor of two.
    """
    return len({row[key] for row in rows if row.get(key)})


def _stems(texts: Iterable[str]) -> set[str]:
    out = set()
    for text in texts:
        for token in tokens(text):
            stem = token[: positions.PREFIX]
            if len(token) > 2 and stem not in ROLE_STEMS:
                out.add(stem)
    return out


def _names(entity: dict[str, Any]) -> list[str]:
    return [text for _lang, text, _alias in positions.names_of(entity)]


def bilateral(text: str) -> bool:
    """Does this name a posting from one state to another?"""
    return bool(BILATERAL.search(fold(text)))


def guard(
    spec: Spec,
    *,
    holders: int,
    current_holders: int,
    single_seat_source_ok: bool,
    duplicates: Sequence[Found],
    run_labels: Iterable[str],
    body: dict[str, Any] | None,
    jurisdiction: dict[str, Any] | None,
    closure: Closure,
    langs: Sequence[str] = (),
    state_names: Iterable[str] = (),
    known_bodies: Collection[str] = (),
    regions: Collection[str] | None = None,
    municipal: bool = False,
    bodies: Collection[str] = (),
) -> list[str]:
    """Every static reason not to mint this office. Empty means it may be created.

    The caller passes distinct-person counts (`distinct_holders`), the live
    duplicate hits, the labels of the run's other candidates, and the body and
    jurisdiction records as `wbgetentities` returns them. `state_names` are
    the state's own labels, kept out of the body word check because "Ministry
    of Health of X" and "Government of X" share nothing but X. `known_bodies`
    are the bodies the state's own offices already sit in: such a body is
    measured rather than drafted, so the word check, which exists to catch a
    drafted QID that is the wrong thing entirely, is not asked of it.
    `regions` are the state's first-level subdivisions, against which an
    archetype's `level` is checked; None skips that check. `municipal` says
    the jurisdiction is typed as a town (`MUNICIPAL_CLASSES`), which makes a
    first-level subdivision a mayor's polity all the same. `bodies` are any
    the office is known to sit in besides its own (the census anchor's).
    """
    problems: list[str] = []
    for lang in ("en", *langs):
        if not spec.labels.get(lang):
            problems.append(f"label/{lang}")
    if not spec.descriptions.get("en"):
        problems.append("description/en")
    texts = [
        *(("label", lang, text) for lang, text in spec.labels.items()),
        *(("alias", lang, text) for lang, many in spec.aliases.items() for text in many),
        *(("description", lang, text) for lang, text in spec.descriptions.items()),
    ]
    for kind, lang, text in texts:
        if QID.search(text):
            problems.append(f"qid-in-{kind}/{lang}")

    single = spec.archetype in ARCHETYPES and spec.shape.single_seat
    floor = 1 if single and single_seat_source_ok else 2
    if holders < floor:
        problems.append(f"holders/{holders}")
    if current_holders < 1:
        problems.append(f"current/{current_holders}")

    state_named = any(names_state(text, state_names) for text in spec.labels.values())
    own = {q for q in (spec.body_qid, *bodies) if q}
    if hit := body_hit(duplicates, own):
        problems.append(f"hit-is-body/{hit}")
    duplicates = [d for d in duplicates if not (d.label_match and (d.qid in own or d.is_body))]
    if dup := duplicate_of(duplicates, state_names if state_named else ()):
        problems.append(f"duplicate/{dup}")
    others = {label_key(text) for text in run_labels}
    if any(label_key(text) in others for text in spec.labels.values()):
        problems.append("run-duplicate")

    if spec.body_qid:
        problems.extend(_body_problems(spec, body, state_names, known_bodies))
    if spec.archetype in ARCHETYPES and spec.shape.scoped and spec.jurisdiction != spec.state_qid:
        if jurisdiction is None or jurisdiction.get("id") != spec.jurisdiction:
            problems.append(f"jurisdiction/{spec.jurisdiction}")
        elif spec.state_qid not in wikidata.claim_qids(jurisdiction, "P17", include_deprecated=False):
            problems.append(f"jurisdiction-state/{spec.jurisdiction}")
        elif dissolved(jurisdiction):
            # Before the level check, which would also refuse it but say less:
            # an article's stale "since 2015" makes the holder of a merged
            # province's governorship read as current.
            problems.append(f"jurisdiction-dissolved/{spec.jurisdiction}")
    if spec.archetype in ARCHETYPES and spec.shape.scoped and regions is not None:
        level, where = spec.shape.level, spec.jurisdiction
        if level == "region" and where not in regions:
            problems.append(f"jurisdiction-level/{level}")
        if level == "municipality" and (where == spec.state_qid or (where in regions and not municipal)):
            problems.append(f"jurisdiction-level/{level}")

    problems.extend(shape_defects(spec, closure))
    if any(bilateral(text) for text in spec.labels.values()):
        problems.append("bilateral")
    return problems


def _body_problems(spec: Spec, body: dict[str, Any] | None, state_names: Iterable[str],
                   known_bodies: Collection[str] = ()) -> list[str]:
    """Is the body a real, labelled organ of this state that the office names?

    A hand-drafted body QID is the easiest field to get wrong and the hardest
    to notice: two drafted for one country's courts were a construction brand
    and a character from an epic poem. Sharing a content word with the office
    is what catches that.
    """
    qid = spec.body_qid
    if body is None or body.get("id") != qid:
        return [f"body/{qid}"]
    if not wikidata.best_label(body):
        return [f"body-unlabelled/{qid}"]
    problems = []
    declared = set(positions.type_targets(body))
    if declared & POSITION_METACLASSES:
        problems.append(f"body-is-position/{qid}")
    if declared & NOT_A_POSITION:
        problems.append(f"body-not-a-body/{qid}")
    # The state's name comes off as a phrase, not as its words: in a state
    # named "X and Y", the "Chief Secretary of Y" and the "Y House of
    # Assembly" share "Y", an island and not the state -- while "Ministry of
    # Health of X and Y" and "Government of X and Y" share nothing once the
    # state is gone.
    names = list(state_names)
    mine = _stems(without_state(text, names) for text in spec.labels.values())
    theirs = _stems(without_state(text, names) for text in _names(body))
    # "Minister of Health" sits in the "Council of Ministers" and shares only
    # role words with it; when the state's own offices already use the body,
    # that is the measured shape and not a drafting slip.
    if qid not in known_bodies and not mine & theirs:
        problems.append(f"body-word/{qid}")
    states = wikidata.claim_qids(body, "P17", include_deprecated=False)
    if states and spec.state_qid not in states:
        problems.append(f"body-state/{qid}")
    body_names = {fold(text) for text in _names(body)}
    if any(fold(text) in body_names for text in spec.labels.values()):
        problems.append(f"office-is-body/{qid}")
    return problems


# --------------------------------------------------------------------------
# Live reads.
#
# Everything above judges records it is handed; everything below fetches them.
# Each read is live (`max_age=0`), because what it answers is Wikidata's state
# at the moment of minting: a duplicate created an hour ago must block, and a
# search answer cached for a week cannot see it. `http.get_json(max_age=0)`
# neither reads nor writes `http_cache`, and `wikidata.fetch_items` always goes
# through it that way.
# --------------------------------------------------------------------------

#: How many of the state's offices must sit in a body before the caller
#: passes it to `guard` as measured, skipping the body word check.
MEASURED_BODY_USES = 2
#: How many of a stateless hit's subclasses `is_office_class` reads.
CLASS_PROBE = 5

#: How long ago an office's most recent recorded holder may have started or
#: ended and the office still be a sibling. Past it the office is history --
#: a colonial governorship last held a century ago -- and a minted office
#: copying its typing copies a historical item's.
HISTORICAL_YEARS = 30
#: `P31` values that declare an office historical.
HISTORICAL_TYPES = {"Q114962596"}  # historical position

#: How many hits each search asks for. The office is usually in the first few;
#: the rest are the people who held it and the lists of them.
SEARCH_LIMIT = 30
#: How far `P279` is walked. Deeper than `positions.CLOSURE_DEPTH` because this
#: walk follows one property only and asks one yes-or-no question of it.
P279_DEPTH = 10

#: A leading article, so "The President of X" and "President of X" compare
#: equal. Matching more is the safe direction: a false duplicate costs a skip.
ARTICLE = re.compile(r"^(?:(?:the|an|a|el|la|los|las|lo|le|les|il|gli|der|die|das|o|os|as)\s+|l')")


def _norm(text: str) -> str:
    return " ".join(fold(text).split())


def _variants(text: str) -> set[str]:
    """A folded name, with and without its leading article."""
    folded = _norm(text)
    return {folded, ARTICLE.sub("", folded, count=1).strip()} - {""}


def _values(entity: dict[str, Any], prop: str) -> list[str]:
    """Item values of a property across every rank but deprecated."""
    return wikidata.claim_qids(entity, prop, include_deprecated=False)


def _unended(entity: dict[str, Any], prop: str) -> list[str]:
    """Item values of a property that are neither deprecated nor ended."""
    out = []
    for claim in entity.get("claims", {}).get(prop, []):
        if claim.get("rank") == "deprecated" or claim.get("qualifiers", {}).get("P582"):
            continue
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(value, dict) and "id" in value:
            out.append(value["id"])
    return out


def dissolved(entity: dict[str, Any], today: date | None = None) -> bool:
    """Whether the item records its own dissolution (`P576`) on or before today.

    A state's `P150` is not ended when the subdivisions are merged: one
    state's still lists sixteen provinces merged a year ago with no qualifier,
    while each province's own item carries the date. A dissolution at year precision
    counts from the first day of its year, and one of unknown date counts at
    once: an office of a polity that has ended is never minted as current.
    """
    today = today or date.today()
    for claim in entity.get("claims", {}).get("P576", []):
        if claim.get("rank") == "deprecated":
            continue
        snak = claim.get("mainsnak", {})
        if snak.get("snaktype") == "somevalue":
            return True
        value = snak.get("datavalue", {}).get("value")
        match = re.match(r"^\+?(\d{1,4})-(\d{2})-(\d{2})", (value or {}).get("time", "")
                         if isinstance(value, dict) else "")
        if match:
            year, month, day = (int(g) for g in match.groups())
            if date(year, max(month, 1), max(day, 1)) <= today:
                return True
    return False


def found_from(entity: dict[str, Any], label: str, state_qid: str,
               states_of: dict[str, list[str]]) -> Found:
    """Judge one search hit against the label searched for and the state.

    `states_of` maps each of the hit's `P1001` targets to that item's own
    `P17`, so an office scoped to a province of the state matches the state
    one hop up. Only one hop: a province's `P17` is the state, and anything
    further away is not this office.
    """
    names = frozenset(_norm(text) for text in _names(entity))
    named = {variant for name in names for variant in _variants(name)}
    p17, p1001 = _values(entity, "P17"), _values(entity, "P1001")
    country_match = state_qid in p17 or state_qid in p1001 or any(
        state_qid in states_of.get(qid, ()) for qid in p1001)
    return Found(
        qid=entity.get("id", ""),
        names=names,
        label_match=bool(_variants(label) & named),
        matched=frozenset({_norm(label)}) if _variants(label) & named else frozenset(),
        country_match=country_match,
        country_qids=tuple(dict.fromkeys(p17 + p1001)),
        types=frozenset(_values(entity, "P31")),
    )


def _search_entities(label: str, lang: str) -> list[str]:
    data = http.get_json(wikidata.WD_API, params={
        "action": "wbsearchentities", "format": "json", "type": "item",
        "search": label, "language": lang, "uselang": lang,
        "strictlanguage": "false", "limit": SEARCH_LIMIT,
    }, max_age=0)
    return [hit["id"] for hit in data.get("search", []) if "id" in hit]


def _cirrus(query: str) -> list[str]:
    data = http.get_json(wikidata.WD_API, params={
        "action": "query", "format": "json", "list": "search", "srnamespace": 0,
        "srsearch": query, "srlimit": SEARCH_LIMIT, "srprop": "",
    }, max_age=0)
    return [hit["title"] for hit in data.get("query", {}).get("search", [])
            if QID.fullmatch(hit.get("title", ""))]


def is_office_class(qid: str, children: Callable[[str], list[str]] | None = None,
                    items: Callable[[list[str]], dict[str, dict[str, Any]]] | None = None) -> bool:
    """Whether a position item is the `P279` parent of other position items.

    Only the first few subclasses are read: one office among them is enough to
    say the item is a kind of office.
    """
    children = children or (lambda q: _cirrus(f"haswbstatement:P279={q}")[:CLASS_PROBE])
    items = items or (lambda qs: wikidata.fetch_items(qs, props="claims"))
    found = children(qid)
    if not found:
        return False
    return any(set(_values(ent, "P31")) & POSITION_METACLASSES for ent in items(found).values())


def live_lookup(label: str, lang: str, state_qid: str) -> list[Found]:
    """Search Wikidata live for an item this office would duplicate.

    Three searches, because each misses what another finds: the entity
    search ranks by label and alias in the language given; `haswbstatement`
    finds the state's own items whatever language they are labelled in; and
    `inlabel` finds an exact label or alias that the other two rank below the
    people holding it. Every hit is then read in full, so `duplicate_of`
    judges the item and not a search snippet.
    """
    phrase = label.replace('"', " ").strip()
    qids = [
        *_search_entities(label, lang),
        *_cirrus(f'haswbstatement:P17={state_qid} "{phrase}"'),
        *_cirrus(f'inlabel:"{phrase}@{lang}"'),
    ]
    entities = wikidata.fetch_items(dict.fromkeys(qids), props="labels|aliases|claims")
    scopes = {q for ent in entities.values() for q in _values(ent, "P1001")} - {state_qid}
    scoped = wikidata.fetch_items(sorted(scopes), props="claims") if scopes else {}
    states_of = {qid: _values(ent, "P17") for qid, ent in scoped.items()}
    out: dict[str, Found] = {}
    for entity in entities.values():
        hit = found_from(entity, label, state_qid, states_of)
        if hit.label_match and not hit.country_qids and is_office_class(hit.qid):
            hit = replace(hit, is_class=True)
        if hit.label_match:
            types = positions.type_closure([hit.qid]).get(hit.qid, set())
            if ORGANISATION in types and not types & POSITION_METACLASSES:
                hit = replace(hit, is_body=True)
        out.setdefault(hit.qid, hit)
    return list(out.values())


class _Subclasses:
    """`P279` edges read live and remembered for the life of this object.

    For "is this kind a subclass of that archetype's kind", which only `P279`
    answers: `positions.type_closure` and `type_edge` mix in `P31`, under
    which every office is a kind of `Q4164871` and nothing narrower.
    """

    def __init__(self) -> None:
        self.edges: dict[str, list[str]] = {}

    def load(self, qids: Iterable[str]) -> None:
        missing = sorted({q for q in qids if q not in self.edges})
        found = wikidata.fetch_items(missing, props="claims") if missing else {}
        for qid in missing:
            self.edges[qid] = _unended(found.get(qid, {}), "P279")

    def ancestors(self, qids: Iterable[str]) -> dict[str, set[str]]:
        """Each class with everything above it, itself included."""
        seeds = list(dict.fromkeys(qids))
        level = set(seeds)
        for _ in range(P279_DEPTH):
            self.load(level)
            level = {t for q in level for t in self.edges[q]} - set(self.edges)
            if not level:
                break
        out = {}
        for seed in seeds:
            seen, frontier = {seed}, [seed]
            for _ in range(P279_DEPTH):
                frontier = [t for q in frontier for t in self.edges.get(q, []) if t not in seen]
                seen.update(frontier)
            out[seed] = seen
        return out


def live_closure() -> Callable[[str], bool]:
    """Answer, live, whether a class reaches `Q4164871`, for `shape_defects`.

    Through `positions.type_closure`, which walks `P31` and `P279` together:
    that is how the consumer of these items types them, and it is the only
    walk under which the kinds of office Wikidata actually has are offices.
    `P279` alone reaches `Q4164871` from 5 of the 13 archetype parents --
    governor, judge, legislator and director are typed `P31 = Q4164871` and
    subclass a profession. The class asked about is always re-read live, so a
    drafted parent nothing has walked before is answered, and its ancestors
    join `type_edge`; answers are remembered for the life of the callable.
    """
    memo: dict[str, bool] = {}

    def reaches(qid: str) -> bool:
        if qid not in memo:
            memo[qid] = POSITION in positions.type_closure([qid]).get(qid, set())
        return memo[qid]

    return reaches


def resolve(qids: Iterable[str]) -> dict[str, dict[str, Any]]:
    """Live records for the body and jurisdiction `guard` checks, keyed as asked.

    Raw `wbgetentities` JSON, because that is what `guard` reads names, types
    and `P17` from. A merged item keeps the id it was merged into, which the
    guard refuses: a drafted QID that redirects was drafted from stale data.
    """
    wanted = sorted({q for q in qids if q})
    return wikidata.fetch_items(wanted, props="labels|aliases|claims") if wanted else {}


def _year(text: str | None) -> int | None:
    """The year of a SPARQL dateTime, or None."""
    match = re.match(r"^(-?\d{1,6})-", text or "")
    return int(match.group(1)) if match else None


def last_held(qids: Sequence[str]) -> dict[str, int]:
    """The year an office's most recent recorded holder started or ended, read live.

    Over every `P39` statement, not only best-rank ones; an office with no
    dated holder is absent, which `historical` reads as "not known to be".
    """
    query = """SELECT ?pos (MAX(?when) AS ?last) WHERE {
      VALUES ?pos { %s }
      ?holder p:P39 ?st. ?st ps:P39 ?pos.
      { ?st pq:P580 ?when } UNION { ?st pq:P582 ?when }
    } GROUP BY ?pos"""
    out: dict[str, int] = {}
    for chunk in wikidata.values_chunks(qids):
        for row in wikidata.sparql(query % wikidata.values_block(chunk), max_age=0):
            year = _year(row.get("last"))
            if year is not None:
                out[row["pos"]] = year
    return out


def historical(entity: dict[str, Any], last_year: int | None, this_year: int) -> bool:
    """Is this office history rather than a template for a new one?

    Dissolved (`P576`), declared historical in `P31`, or last held more than
    `HISTORICAL_YEARS` ago. Nothing is concluded from an office with no dated
    holder: missing data is not evidence that an office ended.
    """
    if _values(entity, "P576") or set(_values(entity, "P31")) & HISTORICAL_TYPES:
        return True
    return last_year is not None and last_year < this_year - HISTORICAL_YEARS


def siblings(state_qid: str, subdivision_qids: Sequence[str] | None = None,
             this_year: int | None = None) -> Siblings:
    """Tally how the state's own current offices are typed, read live.

    The rows are the `position` table's for the state: by `P17` or `P1001`, and
    by a `P1001` that is one of the state's current subdivisions, because a
    provincial office often names only its province -- the one modern
    governorship of one state carried no `P17` at all, and was missed while a
    colonial one set the metaclass. Left out are diplomatic posts, items
    declared not to be offices, and offices `historical` says are history:
    none of them is what a minted office should look like. Where `diplomatic` is still NULL
    (`fill_diplomatic` has not run) it is answered here the same way, through
    the type closure, without writing it back: on one state the unflagged
    rows were 37 ambassadorships, 35 of them tallied as agency heads. Each office's `P279` value is
    mapped to an archetype when it is that archetype's parent or a subclass of
    it -- a "governor of a province of X" counts towards `governor`, and is
    the narrower parent `parent_for` may then choose. A value that is a kind of
    two archetypes (a supreme-court judge is also a judge) goes to the
    narrower one; one that is a kind of none counts only for metaclasses.
    """
    if subdivision_qids is None:
        subdivision_qids = [qid for qid, _labels in subdivisions(state_qid)]
    this_year = this_year or date.today().year
    rows = db.conn().execute(
        "SELECT qid, diplomatic FROM position WHERE (country_qid = %s OR jurisdiction_qid = %s"
        " OR jurisdiction_qid = ANY(%s))"
        " AND NOT coalesce(diplomatic, false) AND NOT coalesce(not_office, false)",
        (state_qid, state_qid, list(subdivision_qids)),
    ).fetchall()
    unflagged = [qid for qid, flag in rows if flag is None]
    closure = positions.type_closure(unflagged) if unflagged else {}
    keep = [qid for qid, _flag in rows if positions.DIPLOMATIC_CLASS not in closure.get(qid, set())]
    items = wikidata.fetch_items(keep, props="labels|claims")
    held = last_held(list(items))
    items = {qid: ent for qid, ent in items.items()
             if not historical(ent, held.get(qid), this_year)}
    walk = _Subclasses()
    kinds = {qid: _unended(ent, "P279") for qid, ent in items.items()}
    above = walk.ancestors(
        [*{k for ks in kinds.values() for k in ks},
         *(s.parent for s in ARCHETYPES.values())])
    out = Siblings()
    for qid, entity in items.items():
        out.offices += 1
        out.label_langs.update(entity.get("labels", {}).keys())
        metas = set(_values(entity, "P31")) & POSITION_METACLASSES
        out.metaclasses.update(metas)
        typed: set[str] = set()
        for kind in dict.fromkeys(kinds[qid]):
            out.metaclass_by_parent.setdefault(kind, Counter()).update(metas)
            matched = {a for a, s in ARCHETYPES.items()
                       if s.parent not in POSITION_METACLASSES and s.parent in above[kind]}
            # Narrowest: drop an archetype whose parent sits above another's.
            narrow = {a for a in matched if not any(
                b != a and ARCHETYPES[a].parent in above[ARCHETYPES[b].parent] for b in matched)}
            if len(narrow) == 1:
                typed |= narrow
                out.parents.setdefault(narrow.pop(), Counter())[kind] += 1
        out.bodies.update(list(dict.fromkeys(_values(entity, "P361") + _values(entity, "P2389"))))
        for arch in typed:
            out.bodies_by_archetype.setdefault(arch, Counter()).update(
                dict.fromkeys(_values(entity, ARCHETYPES[arch].body_property)))
    return out


def subdivisions(state_qid: str) -> list[tuple[str, dict[str, str]]]:
    """The state's current first-level subdivisions (`P150`), with every label.

    Current means the `P150` claim is not ended and the subdivision's own item
    is not `dissolved`: a merger is often recorded only on the merged items.
    """
    state = wikidata.fetch_items([state_qid], props="claims").get(state_qid, {})
    qids = list(dict.fromkeys(_unended(state, "P150")))
    found = wikidata.fetch_items(qids, props="labels|claims") if qids else {}
    return [(qid, {lang: obj["value"] for lang, obj in found[qid].get("labels", {}).items()})
            for qid in qids if qid in found and not dissolved(found[qid])]
