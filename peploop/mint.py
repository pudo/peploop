"""Turn the offices reconciliation could not place into a queue of items to mint.

A `resolution` row with no `qid` says an article named an office and no item on
the shortlist was it. One such row is a count; the same title held by several
living people is a missing item. This module is the counting half of minting:
it reads the misses, groups them by what they name, adds the offices a
per-country census says must exist, and applies the evidence floor before any
model is asked about them. Nothing here writes to Wikidata or calls a model.
"""

import hashlib
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field, replace
from datetime import date
from pathlib import Path
from typing import Any, Callable, Collection, Iterable, Literal, Optional, Protocol, Sequence

import yaml
from anthropic.lib._parse._transform import transform_schema
from psycopg.types.json import Jsonb
from rigour.langs import iso_639_alpha2
from rigour.territories import get_territory

from peploop import db, llm, offices, positions, reconcile, scope, typegraph, wikidata
from peploop import verify as person_verify
from peploop.offices import ARCHETYPES, distinct_holders

CENSUS_DIR = Path(__file__).resolve().parent / "census"

#: A tenure with a start and no end counts as running for this long. Most
#: articles never write the end of a term nobody announced, so an open tenure
#: is the normal shape of a current one; past a dozen years it is the more
#: likely shape of an end the article left out.
CURRENT_WINDOW_YEARS = 12

#: Person statuses whose mentions are no evidence of a current office: the
#: scope gate already decided they are not politically exposed now.
EXCLUDED_STATUSES = ("out_of_scope", "not_human")

#: The institution classes of `docs/institutions.md`, pinned here so nothing
#: reads docs at runtime. `check_mint_queue` compares the tuple against that
#: file's headings, so a class added there fails a check rather than going
#: unassignable.
INSTITUTION_CLASSES = (
    "executive.head_of_state",
    "executive.head_of_government",
    "executive.deputy_leadership",
    "executive.cabinet",
    "executive.deputy_ministers",
    "executive.leader_office",
    "legislature.lower_membership",
    "legislature.upper_membership",
    "legislature.leadership",
    "legislature.historic_chambers",
    "oversight.constitutional_body",
    "oversight.state_councils",
    "oversight.audit_anticorruption",
    "oversight.electoral_commission",
    "judiciary.apex",
    "judiciary.prosecution",
    "judiciary.specialised",
    "economic.central_bank",
    "economic.sovereign_wealth",
    "economic.soe_leadership",
    "economic.regulators",
    "security.defence_command",
    "security.paramilitary",
    "security.intelligence",
    "security.police",
    "subnational.executive",
    "subnational.municipal",
    "subnational.assemblies",
    "diplomatic.outbound",
    "diplomatic.multilateral",
    "hybrid.ruling_family",
    "hybrid.religious_hierarchy",
    "hybrid.parastatal_foundations",
    "hybrid.state_media",
    "political.parties",
)

#: How many quotes a group keeps for display; the rows keep all of them.
SAMPLE_QUOTES = 3


@dataclass
class Row:
    """One unplaced office mention, with what the floor and the passes read."""

    resolution_id: int
    extraction_id: int
    mention_idx: int
    person: str
    title: str
    jurisdiction: str | None = None
    #: The tenure as the extraction wrote it, `YYYY[-MM[-DD]]` or null.
    start: str | None = None
    end: str | None = None
    acting: bool = False
    #: The person's first `P570` as a Wikidata time string, if any.
    death: str | None = None
    quote: str | None = None
    #: What the reconciler said about the shortlist it refused.
    evidence: str | None = None
    kind: str = "none"
    chosen: str | None = None
    shortlist: list[str] = field(default_factory=list)
    lang: str | None = None
    current: bool = False


UNPLACED_SQL = """
WITH latest AS (
    SELECT DISTINCT ON (qid) id, qid FROM extraction ORDER BY qid, id DESC
), newest AS (
    SELECT DISTINCT ON (r.extraction_id, r.mention_idx) r.*
    FROM resolution r JOIN latest l ON l.id = r.extraction_id
    ORDER BY r.extraction_id, r.mention_idx, r.id DESC
)
SELECT n.id, n.extraction_id, n.mention_idx, e.qid, n.title, n.jurisdiction,
       n.start_text, n.end_text, n.lang, n.kind, n.chosen, n.shortlist, n.evidence,
       e.response_json -> 'positions' -> n.mention_idx,
       i.json -> 'claims' -> 'P570'
FROM newest n
JOIN extraction e ON e.id = n.extraction_id
JOIN person p ON p.qid = e.qid
LEFT JOIN item i ON i.qid = e.qid
WHERE n.qid IS NULL AND p.country = %s AND NOT (p.status = ANY(%s))
ORDER BY n.id
"""


def unplaced(country: str, today: date | None = None) -> list[Row]:
    """Read every office mention of a country's people that no item took.

    The newest verdict per mention decides, as in `propose.placements`, so a
    mention placed by a later re-ask is not in the queue; and only the newest
    extraction per person counts, because it is the only one `propose` reads.
    """
    today = today or date.today()
    out = []
    rows = db.conn().execute(UNPLACED_SQL, (country, list(EXCLUDED_STATUSES))).fetchall()
    for (rid, eid, idx, person, title, jurisdiction, start, end, lang, kind,
         chosen, shortlist, evidence, entry, deaths) in rows:
        entry = entry or {}
        died = wikidata.claim_time({"claims": {"P570": deaths or []}}, "P570",
                                   include_deprecated=False)
        quotes = entry.get("quotes") or []
        row = Row(
            resolution_id=rid, extraction_id=eid, mention_idx=idx, person=person,
            title=title, jurisdiction=jurisdiction,
            start=start or entry.get("start"), end=end or entry.get("end"),
            acting=bool(entry.get("acting")),
            death=died[0][0] if died else None,
            quote=quotes[0] if quotes else None, evidence=evidence,
            kind=kind, chosen=chosen, shortlist=list(shortlist or []),
            lang=lang or entry.get("lang"),
        )
        row.current = is_current(row, today)
        out.append(row)
    return out


_PRECISION = {4: 9, 7: 10, 10: 11}


def _bounds(text: str | None) -> tuple[scope.Point, scope.Point] | None:
    """The first and last day an extracted date could mean, or None."""
    if not text:
        return None
    precision = _PRECISION.get(len(text))
    if precision is None:
        return None
    return scope.interval(f"+{(text + '-00-00')[:10]}T00:00:00Z", precision)


def is_current(row: Row, today: date) -> bool:
    """Whether a mention attests that somebody holds the office now.

    The floor's second half: an office nobody holds today is history, and the
    loop records who holds office now. Read conservatively on every side. An
    acting tenure and a dead holder never count; an end counts only when its
    earliest reading is still to come; an open tenure counts only when it
    began inside `CURRENT_WINDOW_YEARS`; an undated one never does.
    """
    if row.acting or row.death:
        return False
    now: scope.Point = (today.year, today.month, today.day)
    if row.end:
        end = _bounds(row.end)
        return end is not None and end[0] > now
    start = _bounds(row.start)
    if start is None:
        return False
    cutoff: scope.Point = (today.year - CURRENT_WINDOW_YEARS, today.month, today.day)
    return start[1] >= cutoff


_SPACE = re.compile(r"\s+")


def _fold(text: str | None) -> str:
    return _SPACE.sub(" ", positions.fold(text or "")).strip()


def group_key(row: Row) -> str:
    """The key mentions are pooled under: the title and jurisdiction, folded."""
    return f"{_fold(row.title)}|{_fold(row.jurisdiction)}"


@dataclass
class Group:
    """The mentions that name one office in the same words."""

    key: str
    rows: list[Row]
    origin: tuple[str, ...] = ("reconcile",)

    @property
    def title(self) -> str:
        return Counter(r.title for r in self.rows).most_common(1)[0][0]

    @property
    def jurisdiction(self) -> str | None:
        named = Counter(r.jurisdiction for r in self.rows if r.jurisdiction)
        return named.most_common(1)[0][0] if named else None

    @property
    def mentions(self) -> int:
        return len(self.rows)

    @property
    def people(self) -> int:
        return distinct_holders({"person": r.person} for r in self.rows)

    @property
    def current(self) -> int:
        return distinct_holders({"person": r.person} for r in self.rows if r.current)

    @property
    def kinds(self) -> Counter[str]:
        return Counter(r.kind for r in self.rows)

    @property
    def chosen(self) -> Counter[str]:
        return Counter(r.chosen for r in self.rows if r.chosen)

    @property
    def quotes(self) -> list[str]:
        seen: list[str] = []
        for row in self.rows:
            if row.quote and row.quote not in seen:
                seen.append(row.quote)
            if len(seen) >= SAMPLE_QUOTES:
                break
        return seen


def groups(rows: Iterable[Row]) -> list[Group]:
    """Pool mentions by `group_key`, the best-attested office first."""
    pooled: dict[str, list[Row]] = {}
    for row in rows:
        pooled.setdefault(group_key(row), []).append(row)
    out = [Group(key, members) for key, members in pooled.items()]
    out.sort(key=lambda g: (-g.current, -g.people, -g.mentions, g.key))
    return out


@dataclass
class Anchor:
    """An office the census says the state has, whether or not anyone named it."""

    key: str
    institution_class: str
    archetype: str
    labels: dict[str, str]
    body: str | None = None
    source: str | None = None
    #: The subdivision a `per: subdivisions` entry was expanded for.
    jurisdiction: str | None = None


def _subdivisions(state_qid: str, dissolved: bool = False) -> list[str]:
    """The state's current first-level subdivisions, read live.

    A `P150` value whose own item records its dissolution is left out, because
    a state's list is often not updated when its provinces merge. `dissolved`
    asks for those too: categorize must still be able to name the province a
    mention is about, or a stale governorship is scoped to the whole state
    rather than refused for the province it governed.
    """
    entity = wikidata.fetch_items([state_qid], props="claims").get(state_qid) or {}
    out = []
    for claim in entity.get("claims", {}).get("P150", []):
        if claim.get("rank") == "deprecated" or claim.get("qualifiers", {}).get("P582"):
            continue
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(value, dict) and value.get("id") and value["id"] not in out:
            out.append(value["id"])
    if dissolved or not out:
        return out
    items = wikidata.fetch_items(out, props="claims")
    return [qid for qid in out if not offices.dissolved(items.get(qid) or {})]


def _labels_of(qids: Sequence[str]) -> dict[str, dict[str, str]]:
    items = wikidata.fetch_items(qids, props="labels")
    return {
        qid: {lang: obj["value"] for lang, obj in item.get("labels", {}).items()}
        for qid, item in items.items()
    }


def census(
    cc: str,
    path: Path | None = None,
    subdivisions: Callable[[str], list[str]] = _subdivisions,
    labels_of: Callable[[Sequence[str]], dict[str, dict[str, str]]] = _labels_of,
) -> list[Anchor]:
    """Load the offices a country's census says must exist.

    Reach for this to find the missing offices nobody's article named: the
    reconcile misses only show what the seeded people held. The file is
    `census/<cc>.yml`, a list of entries with `key`, `class` (one of
    `INSTITUTION_CLASSES`), `archetype` (one of `offices.ARCHETYPES`),
    `labels` by language, and optionally `body`, `source` and
    `per: subdivisions`. The last expands one entry per current `P150` of the
    state, read live, with `{name}` in each label filled from the
    subdivision's label in that language (or `en`, then `mul`; `{Name}` capitalises
    it); an optional
    `exclude: [QID, …]` drops the subdivisions that office does not exist in,
    such as a capital district governed by a mayor. An absent file is an empty
    census.
    """
    path = path or CENSUS_DIR / f"{cc}.yml"
    if not path.exists():
        return []
    entries = yaml.safe_load(path.read_text()) or []
    out: list[Anchor] = []
    for entry in entries:
        klass, archetype = entry["class"], entry["archetype"]
        if klass not in INSTITUTION_CLASSES:
            raise ValueError(f"{entry['key']}: unknown institution class {klass!r}")
        if archetype not in ARCHETYPES:
            raise ValueError(f"{entry['key']}: unknown archetype {archetype!r}")
        base = dict(
            institution_class=klass, archetype=archetype,
            body=entry.get("body"), source=entry.get("source"),
        )
        labels = dict(entry.get("labels") or {})
        per = entry.get("per")
        if per is None:
            out.append(Anchor(key=entry["key"], labels=labels, **base))
            continue
        if per != "subdivisions":
            raise ValueError(f"{entry['key']}: unknown expansion {per!r}")
        exclude = set(entry.get("exclude") or [])
        subs = [s for s in subdivisions(positions.country_qid(cc)) if s not in exclude]
        names = labels_of(subs)
        for sub in subs:
            known = names.get(sub, {})
            filled = {}
            for lang, template in labels.items():
                name = known.get(lang) or known.get("en") or known.get("mul")
                if name:
                    # `{Name}` for a label that starts mid-phrase in its source
                    # ("provincia de …") but is capitalised in the office's.
                    filled[lang] = template.format(name=name, Name=name[:1].upper() + name[1:])
            if filled:
                out.append(Anchor(key=f"{entry['key']}/{sub}", labels=filled,
                                  jurisdiction=sub, **base))
    return out


class Attested(Protocol):
    """What the floor reads: a group, or a candidate built from one."""

    rows: Sequence[Row]
    origin: Sequence[str]


def floor(candidate: Attested) -> str | None:
    """The rule that keeps an office from being asked about, or None.

    Applied before any tokens are spent, and neither model can override it:
    one distinct person attested, and a current holder among them. One holder
    is enough for any office, because the offices PEP screening needs most --
    a party's leadership, a state company's head, an agency's director -- are
    exactly the ones whose predecessors nobody seeded; verify and the guard
    are the gate on whether the office is real. A census anchor nobody's
    article attests is refused under its own rule, so the funnel shows how
    much of the census the seeds reached.
    """
    rows = list(candidate.rows)
    if "census" in candidate.origin and not rows:
        return "census/unattested"
    people = distinct_holders({"person": r.person} for r in rows)
    if people < 1:
        return f"holders/{people}"
    if not any(r.current for r in rows):
        return "not-current"
    return None


# --- categorize --------------------------------------------------------------
#
# The first model pass. The groups above are pooled by spelling, and one office
# is often many spellings: a gendered form, the same title in two languages,
# with and without its place. Categorize clusters them into offices, says what
# kind of thing each one is, and drafts the item it would be. It sees every
# group, including those one person attests, because the floor reads a current
# holder across the pieces of an office and a piece alone may have none.

CATEGORIZE_PROMPT = Path(__file__).resolve().parent / "prompts" / "mint_categorize.md"

#: The same model the reconciler runs, on purpose: verify is the one that must
#: be a different reader, and categorize only proposes.
CATEGORIZE_MODEL = reconcile.MODEL
CATEGORIZE_MAX_TOKENS = 64_000
CATEGORIZE_EFFORT = "low"

#: What the model is shown apart from the prompt. Bumped whenever the rendering
#: changes without a prompt edit, because an answer is keyed by what was shown.
#: 2: the parties the run's people belong to are listed, so a party's leader
#: can name its party as the body. Every chunk is asked again once.
CATEGORIZE_RENDER_VERSION = 2

#: How many of the parties the run's people belong to are listed, most members
#: first. A party with one seeded member is still listed while there is room.
PARTIES_CAP = 80

#: Groups per request. One request is one context, so related groups have to
#: share it to be clustered at all; `chunk_order` is what puts them together.
CATEGORIZE_GROUPS = 80

#: How many of the state's own offices are listed whole. Past it, a chunk is
#: shown only the rows that share a word with its groups, because a country of
#: thirteen thousand municipal offices does not fit in one request.
POSITION_ROWS_CAP = 400

#: A quote is shown up to this many characters; the rows keep all of it.
QUOTE_CHARS = 220

#: The closed decision set, in the order the prompt introduces them.
DECISIONS = (
    "office", "exists", "party-membership", "body", "occupation", "rank",
    "honorific", "historical-only", "foreign", "not-state", "unclear",
)

#: Seats with no archetype in `offices.ARCHETYPES` the model may still name:
#: an ambassadorship is an office, and recording it as one is what lets the
#: disposition defer it under its own rule rather than lose it.
EXTRA_ARCHETYPES = ("ambassador",)
CATEGORIZE_ARCHETYPES = tuple(ARCHETYPES) + EXTRA_ARCHETYPES

#: Statuses a re-categorize leaves alone: an item exists or is being made.
PROTECTED_STATUSES = ("created", "found", "loaded", "creating")

#: Seat words beyond `offices.ROLE_STEMS` that say what kind of seat a title is
#: and nothing about which one. Dropped from the ordering key only, so that two
#: forms of one office, or one office in two languages, sort next to each other.
SEAT_WORDS = """
mayor alcalde alcaldesa maire prefeito sindaco burgomaestre governor gobernador
gobernadora governador magistrate magistrado magistrada senator senador senadora
representative representante councillor concejal concejala conseiller
vicepresident vicepresidente vicepresidenta presidenta presidente
""".split()  # examples
SORT_ROLE_STEMS = offices.ROLE_STEMS | {w[: positions.PREFIX] for w in SEAT_WORDS}


def categorize_prompt() -> tuple[str, str]:
    """Read the frozen categorize prompt and return it with its sha256 hash."""
    return llm.system_prompt(CATEGORIZE_PROMPT)


def _stems(text: str | None, drop: frozenset[str] | set[str]) -> set[str]:
    out = set()
    for token in positions.tokens(text or ""):
        stem = token[: positions.PREFIX]
        if len(token) > 2 and stem not in drop:
            out.add(stem)
    return out


def state_stems(state_names: Iterable[str]) -> set[str]:
    """The stems of the state's own names, which every other title also carries."""
    out: set[str] = set()
    for name in state_names:
        out |= _stems(name, frozenset())
    return out


def chunk_order(group: Group, state: set[str]) -> tuple[tuple[str, ...], str]:
    """The sort key that puts the pieces of one office in one request.

    The title's and the jurisdiction's stems, less the seat words and the
    state's own name, so that a male and a female form of one mayoralty and its
    English rendering all sort under the town's name; then the full key, so the
    order is total and a rerun renders the same chunks.
    """
    drop = SORT_ROLE_STEMS | state
    stems = _stems(group.title, drop) | _stems(group.jurisdiction, drop)
    for row in group.rows:
        stems |= _stems(row.title, drop)
    return tuple(sorted(stems)), group.key


def worth_asking(gs: Sequence[Group], state: set[str]) -> tuple[list[Group], list[Group]]:
    """Split the groups into those categorize should see and those it need not.

    A cluster with no current holder can never clear the floor, so a group is
    only worth tokens if it is current itself or could merge into one that is:
    it shares a place or subject stem with a current group. Most of a country's
    queue is single historical mentions, and asking about them is what pushed a
    request past its output budget.
    """
    hot: set[str] = set()
    for g in gs:
        if g.current:
            hot |= set(chunk_order(g, state)[0])
    keep, drop = [], []
    for g in gs:
        stems = set(chunk_order(g, state)[0])
        (keep if g.current or stems & hot else drop).append(g)
    return keep, drop


def chunks(gs: Sequence[Group], state: set[str], size: int = CATEGORIZE_GROUPS) -> list[list[Group]]:
    """The groups in `chunk_order`, cut into requests of `size`."""
    ordered = sorted(gs, key=lambda g: chunk_order(g, state))
    return [ordered[i:i + size] for i in range(0, len(ordered), size)]


@dataclass
class PositionRow:
    """One of the state's existing offices, as categorize is shown it."""

    qid: str
    label: str | None
    kinds: list[str] = field(default_factory=list)
    not_office: bool = False

    def line(self) -> str:
        kind = ", ".join(self.kinds) or "-"
        mark = " (not an office)" if self.not_office else ""
        return f"{self.qid} | {self.label or '(no label)'} | {kind}{mark}"


@dataclass
class Offered:
    """Every QID categorize may cite, by the list it is shown in."""

    state_qid: str
    state_label: str
    langs: list[str] = field(default_factory=list)
    subdivisions: dict[str, str] = field(default_factory=dict)
    bodies: dict[str, str] = field(default_factory=dict)
    #: The parties the country's people belong to (`P102`), most members first:
    #: what a party office may name as its body.
    parties: dict[str, str] = field(default_factory=dict)
    parents: dict[str, str] = field(default_factory=dict)
    #: The items the reconciler chose for any group, by label.
    chosen: dict[str, str] = field(default_factory=dict)
    positions: list[PositionRow] = field(default_factory=list)
    census_keys: set[str] = field(default_factory=set)

    @property
    def offices(self) -> set[str]:
        """The QIDs an `exists` answer may name: offices, never bodies."""
        return {p.qid for p in self.positions if not p.not_office} | set(self.chosen)

    @property
    def qids(self) -> set[str]:
        return ({self.state_qid} | set(self.subdivisions) | set(self.bodies) | set(self.parties)
                | set(self.parents) | set(self.chosen) | {p.qid for p in self.positions})

    def label(self, qid: str) -> str | None:
        for table in (self.chosen, self.subdivisions, self.bodies, self.parties, self.parents):
            if qid in table:
                return table[qid]
        for row in self.positions:
            if row.qid == qid:
                return row.label
        return self.state_label if qid == self.state_qid else None

    def for_chunk(self, chunk: Sequence[Group]) -> "Offered":
        """The lists one request is shown: all of them, or the relevant rows."""
        chosen = {q for g in chunk for q in g.chosen}
        mine = dict(self.__dict__)
        mine["chosen"] = {q: l for q, l in self.chosen.items() if q in chosen}
        if len(self.positions) > POSITION_ROWS_CAP:
            words: set[str] = set()
            for group in chunk:
                words |= _stems(group.title, offices.ROLE_STEMS)
                words |= _stems(group.jurisdiction, offices.ROLE_STEMS)
            mine["positions"] = [
                p for p in self.positions
                if p.qid in chosen or _stems(p.label, offices.ROLE_STEMS) & words
            ][:POSITION_ROWS_CAP]
        return Offered(**mine)


def _clip(text: str, limit: int = QUOTE_CHARS) -> str:
    text = _SPACE.sub(" ", text).strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def group_block(gid: str, group: Group, offered: Offered) -> str:
    """One group as the model reads it: names, counts, the reconciler, quotes."""
    spellings = [t for t, _n in Counter(r.title for r in group.rows).most_common()]
    head = [gid, " | ".join(spellings[:3])]
    if group.jurisdiction:
        head.append(f"jur: {group.jurisdiction}")
    head.append(f"{group.mentions} mentions, {group.people} people, {group.current} current")
    langs = sorted({r.lang for r in group.rows if r.lang})
    if langs:
        head.append("lang " + ",".join(langs))
    lines = [" | ".join(head)]
    kinds = ", ".join(f"{k} {n}" for k, n in group.kinds.most_common())
    chosen = [f"{q} ({offered.label(q) or '?'})" for q, _n in group.chosen.most_common(2)]
    lines.append("  reconciler: " + kinds + (" → " + "; ".join(chosen) if chosen else ""))
    lines.extend(f"  > “{_clip(q)}”" for q in group.quotes[:2])
    return "\n".join(lines)


def render_categorize(
    groups_chunk: Sequence[Group],
    anchors: Sequence[Anchor],
    sib_hint: str | None,
    offered: Offered,
) -> str:
    """The per-request half of a categorize call: lists, anchors, then groups.

    Groups are numbered `g1…` in chunk order, which is how the answer names
    them and how `settle_categorize` maps them back.
    """
    o = offered
    parts = ["# The state", "", f"{o.state_qid} | {o.state_label}"]
    if o.langs:
        parts.append("languages: " + ", ".join(o.langs))
    parts += ["", "# Items you may cite", ""]
    if o.subdivisions:
        parts += ["## Subdivisions", ""] + [f"- {q} | {l}" for q, l in o.subdivisions.items()] + [""]
    if o.bodies:
        parts += ["## Census bodies", ""] + [f"- {q} | {l}" for q, l in o.bodies.items()] + [""]
    if o.parties:
        parts += ["## Parties", ""] + [f"- {q} | {l}" for q, l in o.parties.items()] + [""]
    if o.parents:
        parts += ["## Kinds of office", ""] + [f"- {q} | {l}" for q, l in o.parents.items()] + [""]
    if o.chosen:
        parts += ["## Items the reconciler considered", ""]
        parts += [f"- {q} | {l}" for q, l in o.chosen.items()] + [""]
    parts += ["## The state's existing offices", ""]
    parts += [f"- {p.line()}" for p in o.positions] or ["- (none loaded)"]
    if sib_hint:
        parts += ["", "# Kind tallies", "", sib_hint]
    parts += ["", "# Census anchors", ""]
    if anchors:
        for a in anchors:
            names = "; ".join(f"{lang}: {text}" for lang, text in sorted(a.labels.items()))
            extra = [a.institution_class, a.archetype]
            if a.body:
                extra.append(f"body {a.body}")
            if a.jurisdiction:
                extra.append(f"jur {a.jurisdiction}")
            parts.append(f"- {a.key} | {names} | {' | '.join(extra)}")
    else:
        parts.append("- (no census for this state)")
    parts += ["", f"# The groups ({len(groups_chunk)})", ""]
    parts += [group_block(f"g{i}", g, o) for i, g in enumerate(groups_chunk, 1)]
    parts += ["", "Cluster these groups into offices. Assign every group exactly once, "
              "and answer `unclear` rather than guess."]
    return "\n".join(parts)


class Label(reconcile.Strict):
    lang: str
    text: str


class OfficeAnswer(reconcile.Strict):
    """One office the groups name, as categorize drafts it."""

    groups: list[str]
    decision: Literal[DECISIONS]
    exists_qid: Optional[str]
    census_key: Optional[str]
    institution_class: Optional[str]
    archetype: Optional[str]
    single_seat: bool
    labels: list[Label]
    description_en: Optional[str]
    parent_qid: Optional[str]
    body_qid: Optional[str]
    jurisdiction_qid: Optional[str]
    jurisdiction_name: Optional[str]
    replaces_qid: Optional[str]
    evidence: str
    reason: str


class UnassignedAnswer(reconcile.Strict):
    group: str
    reason: str


class CategorizeAnswer(reconcile.Strict):
    """The whole answer for one chunk. One shape for every request."""

    offices: list[OfficeAnswer]
    unassigned: list[UnassignedAnswer]


@dataclass
class Drafted:
    """One office after settle: the model's draft, with what the gate removed."""

    groups: list[Group]
    decision: str
    labels: dict[str, str]
    exists_qid: str | None = None
    census_key: str | None = None
    institution_class: str | None = None
    archetype: str | None = None
    single_seat: bool = False
    description_en: str | None = None
    parent_qid: str | None = None
    body_qid: str | None = None
    jurisdiction_qid: str | None = None
    jurisdiction_name: str | None = None
    replaces_qid: str | None = None
    evidence: str = ""
    reason: str = ""
    problems: list[str] = field(default_factory=list)

    def draft(self) -> dict[str, Any]:
        """What `office_candidate.draft` stores: the settled answer, minus the rows."""
        out = {k: v for k, v in self.__dict__.items() if k not in ("groups", "problems")}
        out["group_keys"] = [g.key for g in self.groups]
        return out


QID_FIELDS = ("parent_qid", "body_qid", "jurisdiction_qid", "replaces_qid")


def settle_categorize(
    answer: CategorizeAnswer, chunk: Sequence[Group], offered: Offered
) -> tuple[list[Drafted], list[tuple[Group, str]], list[str]]:
    """Turn one chunk's answer into offices and unassigned groups, or refusals.

    Pure, so `check_mint_categorize` pins every path. The schema is a request
    and this is the guarantee: every group lands exactly once (a missing one is
    unassigned under a recorded problem, a second assignment is dropped), a QID
    not on the offered lists is nulled, an `exists` without an offered office
    becomes `unclear`, and a class or archetype outside the closed sets is
    nulled. Problems are kept on the office they concern and in the chunk list.
    """
    by_id = {f"g{i}": g for i, g in enumerate(chunk, 1)}
    seen: set[str] = set()
    problems: list[str] = []
    allowed = offered.qids

    def take(gid: str, where: list[str]) -> Group | None:
        if gid not in by_id:
            where.append(f"unknown-group:{gid}")
            return None
        if gid in seen:
            where.append(f"group-twice:{by_id[gid].key}")
            return None
        seen.add(gid)
        return by_id[gid]

    out: list[Drafted] = []
    for office in answer.offices:
        mine: list[str] = []
        members = [g for g in (take(gid, mine) for gid in office.groups) if g is not None]
        values = {name: getattr(office, name) for name in QID_FIELDS}
        for name, qid in values.items():
            if qid and qid not in allowed:
                mine.append(f"off-list:{name}:{qid}")
                values[name] = None
        decision, exists = office.decision, office.exists_qid
        if decision == "exists" and exists not in offered.offices:
            mine.append(f"off-list:exists_qid:{exists}")
            decision, exists = "unclear", None
        elif decision != "exists":
            exists = None
        klass, archetype = office.institution_class, office.archetype
        if klass and klass not in INSTITUTION_CLASSES:
            mine.append(f"unknown-class:{klass}")
            klass = None
        if archetype and archetype not in CATEGORIZE_ARCHETYPES:
            mine.append(f"unknown-archetype:{archetype}")
            archetype = None
        census_key = office.census_key
        if census_key and census_key not in offered.census_keys:
            mine.append(f"unknown-census:{census_key}")
            census_key = None
        labels: dict[str, str] = {}
        for label in office.labels:
            if label.text.strip() and label.lang not in labels:
                labels[label.lang] = label.text.strip()
        problems.extend(mine)
        if not members and not census_key:
            problems.append("office-without-groups")
            continue
        out.append(Drafted(
            groups=members, decision=decision, labels=labels, exists_qid=exists,
            census_key=census_key, institution_class=klass, archetype=archetype,
            single_seat=office.single_seat, description_en=office.description_en,
            jurisdiction_name=office.jurisdiction_name, evidence=office.evidence,
            reason=office.reason, problems=mine, **values,
        ))
    unassigned: list[tuple[Group, str]] = []
    for item in answer.unassigned:
        group = take(item.group, problems)
        if group is not None:
            unassigned.append((group, item.reason))
    for gid, group in by_id.items():
        if gid not in seen:
            problems.append(f"group-missing:{group.key}")
            unassigned.append((group, "categorize/missing"))
    return out, unassigned, problems


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", _fold(text)).strip("-")


def candidate_ref(office: Drafted) -> str:
    """The key a candidate is upserted under, stable across reruns."""
    if office.census_key:
        return office.census_key
    label = office.labels.get("en") or next(iter(office.labels.values()), None)
    label = label or office.groups[0].key
    return f"{_slug(label)}@{office.jurisdiction_qid or ''}"


@dataclass
class Cluster:
    """A candidate as the floor reads it: the rows of every group it merged."""

    ref: str
    groups: list[Group]
    drafts: list[Drafted] = field(default_factory=list)
    anchor: Anchor | None = None
    calls: list[int] = field(default_factory=list)

    @property
    def rows(self) -> list[Row]:
        return [r for g in self.groups for r in g.rows]

    @property
    def single_seat(self) -> bool:
        return bool(self.drafts and self.drafts[0].single_seat)

    @property
    def source_url(self) -> str | None:
        return self.anchor.source if self.anchor else None

    @property
    def origin(self) -> tuple[str, ...]:
        out = ("reconcile",) if self.groups else ()
        return out + (("census",) if self.anchor else ())

    @property
    def holders(self) -> int:
        return distinct_holders({"person": r.person} for r in self.rows)

    @property
    def current_holders(self) -> int:
        return distinct_holders({"person": r.person} for r in self.rows if r.current)

    @property
    def problems(self) -> list[str]:
        out = [p for d in self.drafts for p in d.problems]
        if len({(d.decision, d.archetype) for d in self.drafts}) > 1:
            out.append("merged-disagree")
        return out


def merge(drafts: Iterable[tuple[Drafted, int | None]], anchors: Sequence[Anchor],
          state_qid: str | None = None) -> dict[str, Cluster]:
    """Pool the settled offices of every chunk by ref, and give each anchor one.

    Two chunks may draft the same office, or name the same anchor; they become
    one candidate whose rows are all their groups. "The same" is the ref, or
    any shared label under the same jurisdiction. The first draft is the one
    stored, and a disagreement between drafts is recorded as a problem. An
    anchor no group names still gets a candidate, so its disposition can say so.
    """
    by_key = {a.key: a for a in anchors}
    out: dict[str, Cluster] = {}
    # Chunks are drafted apart, so one office can come back under two English
    # renderings ("Vice Minister …", "Deputy Minister …") with one Spanish
    # label. A label in any language, under one jurisdiction, is one office,
    # and so is one differing only by a stopword ("at"/"in the Ministry").
    named: dict[tuple[str, str], str] = {}

    def where(qid: str | None) -> str:
        return "" if qid in (None, state_qid) else qid
    for anchor in anchors:
        for text in anchor.labels.values():
            named.setdefault((offices.label_key(text), where(anchor.jurisdiction)), anchor.key)
    for office, call in drafts:
        ref = candidate_ref(office)
        if not office.census_key and office.decision == "office":
            seen = [named.get((offices.label_key(t), where(office.jurisdiction_qid)))
                    for t in office.labels.values()]
            ref = next((r for r in seen if r), ref)
        if office.decision == "office":
            for text in office.labels.values():
                named.setdefault((offices.label_key(text), where(office.jurisdiction_qid)), ref)
        cluster = out.setdefault(ref, Cluster(ref, [], anchor=by_key.get(office.census_key or "")))
        held = {g.key for g in cluster.groups}
        cluster.groups.extend(g for g in office.groups if g.key not in held)
        cluster.drafts.append(office)
        if call is not None and call not in cluster.calls:
            cluster.calls.append(call)
    for anchor in anchors:
        out.setdefault(anchor.key, Cluster(anchor.key, [], anchor=anchor))
    return out


class Truncated(RuntimeError):
    """An answer that stopped before its JSON closed, with what it cost."""

    def __init__(self, reason: str | None, usage: dict[str, int], body: str = "",
                 thinking: int = 0):
        super().__init__(f"categorize: answer not parseable (stop_reason={reason},"
                         f" usage={usage}, answer chars={len(body)}, thinking chars={thinking})")
        self.usage = usage
        self.body = body


def ask_categorize(message: str, model: str) -> tuple[CategorizeAnswer, dict[str, int]]:
    """Send one categorize request and return the parsed answer and its usage.

    Streamed, because an answer for 150 groups runs past what the SDK lets a
    non-streaming request wait for. The schema goes as a plain format and the
    answer is parsed after the stream ends, so an answer cut short raises
    `Truncated` carrying the usage rather than losing it inside the stream.
    """
    text, _hash = categorize_prompt()
    schema = transform_schema(CategorizeAnswer.model_json_schema())
    with llm.client().messages.stream(
        model=model,
        max_tokens=CATEGORIZE_MAX_TOKENS,
        thinking={"type": "adaptive"},
        output_config={"effort": CATEGORIZE_EFFORT,
                       "format": {"type": "json_schema", "schema": schema}},
        system=[{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": message}],
    ) as stream:
        response = stream.get_final_message()
    usage = llm.usage(response)
    body = "".join(block.text for block in response.content if block.type == "text")
    thinking = sum(len(getattr(block, "thinking", "") or "") for block in response.content
                   if block.type == "thinking")
    try:
        return CategorizeAnswer.model_validate_json(body), usage
    except ValueError:
        raise Truncated(response.stop_reason, usage, body, thinking) from None


def content_key(message: str) -> str:
    return hashlib.sha256(message.encode("utf-8")).hexdigest()


def recorded_call(country: str, key: str, prompt_hash: str, model: str) -> tuple[int, CategorizeAnswer] | None:
    """The answer the ledger already holds for this exact request, if any."""
    row = db.conn().execute(
        "SELECT id, response_json FROM mint_call WHERE pass = 'categorize' AND content_key = %s"
        " AND prompt_hash = %s AND render_version = %s AND model = %s",
        (key, prompt_hash, CATEGORIZE_RENDER_VERSION, model),
    ).fetchone()
    if row is None:
        return None
    return row[0], CategorizeAnswer.model_validate(row[1])


def store_call(country: str, key: str, prompt_hash: str, model: str, message: str,
               answer: CategorizeAnswer, usage: dict[str, int]) -> int:
    row = db.conn().execute(
        "INSERT INTO mint_call (pass, country, content_key, prompt_hash, render_version, model,"
        " request_json, response_json, usage_json) VALUES ('categorize', %s, %s, %s, %s, %s, %s, %s, %s)"
        " ON CONFLICT (pass, content_key, prompt_hash, render_version, model)"
        " DO UPDATE SET country = EXCLUDED.country RETURNING id",
        (country, key, prompt_hash, CATEGORIZE_RENDER_VERSION, model,
         Jsonb({"message": message}), Jsonb(answer.model_dump()), Jsonb(usage)),
    ).fetchone()
    return row[0]


def _labels(qids: Iterable[str]) -> dict[str, str]:
    """Labels for some QIDs, from the position table first and the item cache after."""
    wanted = sorted({q for q in qids if q})
    if not wanted:
        return {}
    out = dict(db.conn().execute(
        "SELECT qid, label FROM position WHERE qid = ANY(%s) AND label IS NOT NULL", (wanted,),
    ).fetchall())
    missing = [q for q in wanted if q not in out]
    if missing:
        for qid, item in wikidata.fetch_items(missing, props="labels").items():
            label = wikidata.best_label(item)
            if label:
                out[qid] = label
    return out


def state_positions(state: str) -> list[PositionRow]:
    """The state's own offices as categorize is shown them.

    By `P1001` as well as `P17`: an office that names only the polity it
    governs is as much the state's, and left out it is the office categorize
    is asked to mint a second time.
    """
    rows = db.conn().execute(
        "SELECT qid, label, kinds, coalesce(not_office, false) FROM position"
        " WHERE country_qid = %s OR jurisdiction_qid = %s ORDER BY label NULLS LAST, qid",
        (state, state),
    ).fetchall()
    return [PositionRow(q, l, list(k or []), bool(n)) for q, l, k, n in rows]


PEOPLE_SQL = "SELECT qid FROM person WHERE country = %s AND NOT (status = ANY(%s)) ORDER BY qid"


def party_members(country: str, *, people: Sequence[str] | None = None,
                  items: Callable[[Sequence[str]], dict[str, dict[str, Any]]] | None = None
                  ) -> Counter[str]:
    """How many of the country's people each party counts as a member (`P102`), read live.

    The run's own people, not a list of the state's parties: the leader an
    article names belongs to a party the run seeded someone from, and a party
    no seeded person belongs to is not one categorize will meet.
    """
    items = items or (lambda qids: wikidata.fetch_items(qids, props="claims"))
    if people is None:
        people = [q for (q,) in db.conn().execute(
            PEOPLE_SQL, (country, list(EXCLUDED_STATUSES))).fetchall()]
    out: Counter[str] = Counter()
    for entity in items(list(people)).values():
        out.update(set(wikidata.claim_qids(entity, "P102", include_deprecated=False)))
    return out


def party_order(members: Counter[str], cap: int = PARTIES_CAP) -> list[str]:
    """The parties categorize is shown: most members first, then by QID, at most `cap`."""
    return [q for q, _n in sorted(members.items(), key=lambda kv: (-kv[1], kv[0]))][:cap]


def offered_for(country: str, gs: Sequence[Group], anchors: Sequence[Anchor],
                parties: Counter[str] | None = None) -> tuple[Offered, str | None]:
    """Everything categorize may cite for a country, and the kind tallies.

    Read from the position table and the cached item reader. The subdivisions
    come from the live `P150` read the census uses; the parties from the
    run's people (`party_members`), unless passed.
    """
    state = positions.country_qid(country)
    parties = party_members(country) if parties is None else parties
    party_qids = party_order(parties)
    rows_out = state_positions(state)
    subs = _subdivisions(state, dissolved=True)
    current = set(_subdivisions(state))
    chosen = {q for g in gs for q in g.chosen}
    parents = {q for a in ARCHETYPES.values() for q in (a.parent, *a.parents)}
    bodies = {a.body for a in anchors if a.body}
    labels = _labels([state, *subs, *chosen, *parents, *bodies, *party_qids])
    territory = get_territory(country)
    langs = [iso_639_alpha2(lang) or lang for lang in (territory.langs if territory else [])]
    offered = Offered(
        state_qid=state, state_label=labels.get(state, state), langs=langs,
        subdivisions={q: labels.get(q, q) + ("" if q in current else " (dissolved)") for q in subs},
        bodies={q: labels.get(q, q) for q in sorted(bodies)},
        parties={q: labels.get(q, q) for q in party_qids},
        parents={q: labels.get(q, q) for q in sorted(parents)},
        chosen={q: labels.get(q, q) for q in sorted(chosen)},
        positions=rows_out, census_keys={a.key for a in anchors},
    )
    tally = Counter(k for r in rows_out for k in r.kinds)
    hint = ", ".join(f"{k} {n}" for k, n in tally.most_common(15)) or None
    return offered, hint


def _state_names(offered: Offered) -> list[str]:
    item = wikidata.fetch_items([offered.state_qid], props="labels").get(offered.state_qid) or {}
    return [offered.state_label] + [v["value"] for v in item.get("labels", {}).values()]


ATTESTATION_SQL = (
    "INSERT INTO office_attestation (candidate_id, resolution_id, extraction_id, mention_idx,"
    " person_qid, current) VALUES (%s, %s, %s, %s, %s, %s)"
    " ON CONFLICT (candidate_id, extraction_id, mention_idx) DO NOTHING"
)


def write_candidates(country: str, clusters: dict[str, Cluster],
                     unassigned: Sequence[tuple[Group, str, int | None]], complete: bool) -> dict[str, int]:
    """Upsert the candidates, their attestations and the unassigned groups.

    A candidate is keyed by its ref, so a rerun updates the row it made. Rows
    already created, found, loaded or being created are left as they are, save
    for new attestations. On a complete run every other candidate the answers
    no longer produce is `superseded`, and its attestations go with it.
    """
    conn = db.conn()
    stats = Counter()
    with conn.transaction():
        for ref, c in clusters.items():
            first = c.drafts[0] if c.drafts else None
            anchor = c.anchor
            klass = (first and first.institution_class) or (anchor and anchor.institution_class)
            archetype = (first and first.archetype) or (anchor and anchor.archetype)
            draft = first.draft() if first else None
            if draft is not None and len(c.drafts) > 1:
                draft["merged"] = [d.draft() for d in c.drafts[1:]]
            row = conn.execute(
                "INSERT INTO office_candidate (country, ref, origin, census_key, institution_class,"
                " archetype, single_seat, draft, holders, current_holders, source_url, status,"
                " problems, categorize_call)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'categorized', %s, %s)"
                " ON CONFLICT (country, ref) DO UPDATE SET origin = EXCLUDED.origin,"
                " census_key = EXCLUDED.census_key, institution_class = EXCLUDED.institution_class,"
                " archetype = EXCLUDED.archetype, single_seat = EXCLUDED.single_seat,"
                " draft = EXCLUDED.draft, holders = EXCLUDED.holders,"
                " current_holders = EXCLUDED.current_holders, source_url = EXCLUDED.source_url,"
                " status = 'categorized', rule = NULL, problems = EXCLUDED.problems,"
                " categorize_call = EXCLUDED.categorize_call, updated_at = now()"
                " WHERE office_candidate.status <> ALL(%s) AND office_candidate.decided_by IS NULL"
                " RETURNING id",
                (country, ref, list(c.origin), anchor.key if anchor else None, klass, archetype,
                 c.single_seat, Jsonb(draft) if draft is not None else None, c.holders,
                 c.current_holders, c.source_url, c.problems, c.calls[0] if c.calls else None,
                 list(PROTECTED_STATUSES)),
            ).fetchone()
            if row is None:
                stats["protected"] += 1
                cid = conn.execute("SELECT id FROM office_candidate WHERE country = %s AND ref = %s",
                                   (country, ref)).fetchone()[0]
            else:
                cid = row[0]
                stats["candidates"] += 1
                conn.execute("DELETE FROM office_attestation WHERE candidate_id = %s", (cid,))
            for r in c.rows:
                conn.execute(ATTESTATION_SQL, (cid, r.resolution_id, r.extraction_id,
                                               r.mention_idx, r.person, r.current))
        for group, reason, call in unassigned:
            conn.execute(
                "INSERT INTO office_unassigned (country, group_key, reason, categorize_call)"
                " VALUES (%s, %s, %s, %s) ON CONFLICT (country, group_key) DO UPDATE"
                " SET reason = EXCLUDED.reason, categorize_call = EXCLUDED.categorize_call",
                (country, group.key, reason, call))
        if complete:
            gone = conn.execute(
                "UPDATE office_candidate SET status = 'superseded', updated_at = now()"
                " WHERE country = %s AND NOT (ref = ANY(%s)) AND status <> ALL(%s)"
                " AND status <> 'superseded' AND decided_by IS NULL RETURNING id",
                (country, list(clusters), list(PROTECTED_STATUSES)),
            ).fetchall()
            stats["superseded"] = len(gone)
            if gone:
                conn.execute("DELETE FROM office_attestation WHERE candidate_id = ANY(%s)",
                             ([g[0] for g in gone],))
            keys = [g.key for g, _r, _c in unassigned]
            conn.execute("DELETE FROM office_unassigned WHERE country = %s AND NOT (group_key = ANY(%s))",
                         (country, keys))
    return dict(stats)


USAGE_KEYS = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")


def categorize(
    country: str,
    *,
    dry_run: bool = False,
    model: str = CATEGORIZE_MODEL,
    log: Callable[[str], None] = print,
    limit_chunks: int | None = None,
) -> dict[str, Any]:
    """Cluster a country's unplaced offices into candidates, and draft each one.

    The whole first pass: read the queue and the census, order and chunk the
    groups, ask once per chunk (or read the ledger back), settle, merge across
    chunks, and upsert `office_candidate` with its attestations at status
    `categorized`. A rerun over unchanged groups asks nothing. `dry_run` prints
    the first request and the request count and writes nothing; `limit_chunks`
    asks only the first chunks, and then supersedes nothing, because the rest
    of the answers were never read. A chunk whose answer is cut short is
    reported, costed and left for the next run, and also supersedes nothing.
    """
    gs = groups(unplaced(country))
    anchors = census(country)
    offered, hint = offered_for(country, gs, anchors)
    state = state_stems(_state_names(offered))
    asked, skipped = worth_asking(gs, state)
    cut = chunks(asked, state)
    if limit_chunks is not None:
        cut = cut[:limit_chunks]
    _text, prompt_hash = categorize_prompt()
    messages = [render_categorize(c, anchors, hint, offered.for_chunk(c)) for c in cut]
    stats: dict[str, Any] = {"groups": len(gs), "skipped": len(skipped),
                             "anchors": len(anchors), "chunks": len(cut),
                             "asked": 0, "recorded": 0, "problems": 0,
                             "usage": {k: 0 for k in USAGE_KEYS}}
    if dry_run:
        known = sum(1 for m in messages
                    if recorded_call(country, content_key(m), prompt_hash, model) is not None)
        stats["recorded"] = known
        log(f"{country}: {len(gs)} groups ({len(skipped)} with no current holder near them),"
            f" {len(anchors)} anchors, {len(cut)} requests"
            f" ({len(cut) - known} to ask, {known} in the ledger)")
        if messages:
            log(messages[0])
        return stats
    drafts: list[tuple[Drafted, int | None]] = []
    unassigned: list[tuple[Group, str, int | None]] = [
        (g, "floor/not-current", None) for g in skipped
    ]
    for i, (chunk, message) in enumerate(zip(cut, messages), 1):
        key = content_key(message)
        known = recorded_call(country, key, prompt_hash, model)
        if known is not None:
            call, answer = known
            stats["recorded"] += 1
        else:
            stats["asked"] += 1
            try:
                answer, usage = ask_categorize(message, model)
            except Truncated as exc:
                for k in USAGE_KEYS:
                    stats["usage"][k] += exc.usage.get(k, 0)
                stats["failed"] = stats.get("failed", 0) + 1
                stats.setdefault("truncated", []).append(exc.body)
                log(f"chunk {i}/{len(cut)}: {exc}")
                continue
            call = store_call(country, key, prompt_hash, model, message, answer, usage)
            for k in USAGE_KEYS:
                stats["usage"][k] += usage.get(k, 0)
        settled, left, problems = settle_categorize(answer, chunk, offered.for_chunk(chunk))
        stats["problems"] += len(problems)
        for p in problems:
            log(f"  chunk {i}: {p}")
        drafts.extend((d, call) for d in settled)
        unassigned.extend((g, reason, call) for g, reason in left)
        log(f"chunk {i}/{len(cut)}: {len(chunk)} groups → {len(settled)} offices,"
            f" {len(left)} unassigned{'' if known is None else ' (ledger)'}")
    clusters = merge(drafts, anchors, offered.state_qid)
    stats["offices"] = len(clusters)
    stats["unassigned"] = len(unassigned)
    # A chunk that failed decided nothing, so nothing it last produced may be
    # superseded on its account: the run is only complete when every chunk was read.
    complete = limit_chunks is None and not stats.get("failed")
    stats.update(write_candidates(country, clusters, unassigned, complete=complete))
    stats["clusters"] = clusters
    return stats


# --- verify ------------------------------------------------------------------
#
# The second model pass, and then the rules that decide. Categorize drafted an
# item per office from a chunk of eighty groups; verify reads one office at a
# time, with everything that bears on whether it should exist: the people who
# held it in their own words, what a live search of Wikidata finds for its
# names, the state's existing offices, how they are typed, and the draft as it
# would land. It never sees categorize's reasoning, because a second opinion is
# worth only its uncorrelated error.
#
# Only an office every rule lets through is asked about: a census anchor nobody
# attests, a refusal, a diplomatic post, a seat with no archetype and anything
# under the floor are decided before any tokens are spent. The model's answer
# is then one more gate among the guard's, and the first rule that applies
# decides. There is no review status: a disagreement is a skip with its rule.

VERIFY_PROMPT = Path(__file__).resolve().parent / "prompts" / "mint_verify.md"

#: The verifier's model, a different family from categorize's on purpose: the
#: pass exists to be an independent reading. Shared with the person loop's
#: verifier through `PEPLOOP_VERIFY_MODEL`.
VERIFY_MODEL = person_verify.MODEL
VERIFY_MAX_TOKENS = 16_000
VERIFY_EFFORT = person_verify.EFFORT

#: What the model is shown apart from the prompt. Bumped whenever the rendering
#: changes without a prompt edit, because an answer is keyed by what was shown.
VERIFY_RENDER_VERSION = 1

#: The closed verdict set, in the order the prompt introduces them.
VERIFY_VERDICTS = (
    "mint", "exists", "not-an-office", "not-current", "not-distinct",
    "generic-convention", "unclear",
)
CONFIDENCES = ("high", "medium", "low")
SHAPES = ("agree", "correct")
#: The fields a `correct` answer may name, in the order a skip rule reports them.
CORRECTION_FIELDS = ("parent_qid", "body_qid", "jurisdiction_qid", "metaclass",
                     "label_en", "label_local")
CORRECTION_QIDS = CORRECTION_FIELDS[:4]

#: How many of the state's offices are listed whole; past it, only the rows
#: sharing a word with the office's names.
INDEX_CAP = 300
#: How many live search hits are shown, name matches first.
DUPLICATES_SHOWN = 40
#: Attested titles kept as aliases, per language, most-held first.
ALIASES_PER_LANG = 5
VERIFY_QUOTE_CHARS = 400

SKIPPED, FOUND, GUARDED = "skipped", "found", "guarded"
#: Every status a disposition may write. There is no fourth: nothing waits.
DISPOSITION_STATUSES = (SKIPPED, FOUND, GUARDED)
#: The statuses verify reads and may re-decide. A `found` row, like a created
#: one, is left alone: an item exists and `feed` may already have used it.
VERIFIABLE = ("categorized", SKIPPED, GUARDED)
#: Statuses whose labels a guarded candidate may not repeat.
RUN_STATUSES = (GUARDED, "creating", "created", "loaded")
#: Prefixes of the problems this stage writes, so a rerun replaces its own and
#: keeps categorize's.
STAGE_PREFIXES = ("spec:", "verify:", "guard:")


def verify_prompt() -> tuple[str, str]:
    """Read the frozen verify prompt and return it with its sha256 hash."""
    return llm.system_prompt(VERIFY_PROMPT)


class Corrections(reconcile.Strict):
    """What a `correct` answer changes in the draft; null leaves a field alone."""

    parent_qid: Optional[str]
    body_qid: Optional[str]
    jurisdiction_qid: Optional[str]
    metaclass: Optional[str]
    label_en: Optional[str]
    label_local: Optional[str]


class VerifyAnswer(reconcile.Strict):
    """The verifier's answer for one office. One shape for every request."""

    verdict: Literal[VERIFY_VERDICTS]
    exists_qid: Optional[str]
    real: bool
    current: bool
    missing: bool
    shape: Literal[SHAPES]
    corrections: Corrections
    confidence: Literal[CONFIDENCES]
    evidence: str
    reason: str


@dataclass
class Attestation:
    """One mention behind a candidate, as verify shows it."""

    person: str
    current: bool
    title: str | None = None
    jurisdiction: str | None = None
    start: str | None = None
    end: str | None = None
    lang: str | None = None
    acting: bool = False
    quotes: list[str] = field(default_factory=list)
    person_label: str | None = None


@dataclass
class Candidate:
    """An `office_candidate` row with its attestations: what the rules read."""

    id: int
    country: str
    ref: str
    origin: tuple[str, ...] = ()
    archetype: str | None = None
    single_seat: bool = False
    draft: dict[str, Any] | None = None
    source_url: str | None = None
    status: str = "categorized"
    problems: list[str] = field(default_factory=list)
    spec: dict[str, Any] | None = None
    census_key: str | None = None
    attestations: list[Attestation] = field(default_factory=list)

    @property
    def rows(self) -> list[Attestation]:
        """The attestations, under the name `floor` reads."""
        return self.attestations

    @property
    def decision(self) -> str | None:
        return (self.draft or {}).get("decision")

    @property
    def kind(self) -> str | None:
        """The archetype: the draft's, else the census anchor's."""
        return (self.draft or {}).get("archetype") or self.archetype

    @property
    def holders(self) -> int:
        return distinct_holders({"person": a.person} for a in self.attestations)

    @property
    def current_holders(self) -> int:
        return distinct_holders({"person": a.person} for a in self.attestations if a.current)

    @property
    def labels(self) -> dict[str, str]:
        """The first draft's labels, with a language it lacks filled from a merged one."""
        draft = self.draft or {}
        out = dict(draft.get("labels") or {})
        for other in draft.get("merged") or []:
            for lang, text in (other.get("labels") or {}).items():
                out.setdefault(lang, text)
        return out


CANDIDATE_COLUMNS = ("id", "country", "ref", "origin", "archetype", "single_seat", "draft",
                     "source_url", "status", "problems", "spec", "census_key")

ATTESTATIONS_SQL = """
SELECT a.candidate_id, a.person_qid, a.current, r.title, r.jurisdiction, r.start_text,
       r.end_text, r.lang, e.response_json -> 'positions' -> a.mention_idx, i.json -> 'labels'
FROM office_attestation a
LEFT JOIN resolution r ON r.id = a.resolution_id
LEFT JOIN extraction e ON e.id = a.extraction_id
LEFT JOIN item i ON i.qid = a.person_qid
WHERE a.candidate_id = ANY(%s)
ORDER BY a.candidate_id, a.person_qid, a.extraction_id, a.mention_idx
"""


def _attestations(ids: Sequence[int]) -> dict[int, list[Attestation]]:
    out: dict[int, list[Attestation]] = {}
    if not ids:
        return out
    rows = db.conn().execute(ATTESTATIONS_SQL, (list(ids),)).fetchall()
    for cid, person, current, title, jur, start, end, lang, entry, labels in rows:
        entry = entry or {}
        out.setdefault(cid, []).append(Attestation(
            person=person, current=bool(current), title=title or entry.get("title"),
            jurisdiction=jur or entry.get("jurisdiction"), start=start or entry.get("start"),
            end=end or entry.get("end"), lang=lang or entry.get("lang"),
            acting=bool(entry.get("acting")), quotes=list(entry.get("quotes") or []),
            person_label=wikidata.best_label({"labels": labels or {}}),
        ))
    return out


def load_candidates(country: str, ids: Sequence[int] | None = None,
                    statuses: Sequence[str] = VERIFIABLE) -> list[Candidate]:
    """The country's candidates verify may decide, with their attestations, by id."""
    sql = (f"SELECT {', '.join(CANDIDATE_COLUMNS)} FROM office_candidate"
           " WHERE country = %s AND status = ANY(%s) AND decided_by IS NULL")
    params: list[Any] = [country, list(statuses)]
    if ids is not None:
        sql += " AND id = ANY(%s)"
        params.append(list(ids))
    rows = db.conn().execute(sql + " ORDER BY id", params).fetchall()
    out = [_candidate(dict(zip(CANDIDATE_COLUMNS, row))) for row in rows]
    found = _attestations([c.id for c in out])
    for cand in out:
        cand.attestations = found.get(cand.id, [])
    return out


def _candidate(row: dict[str, Any]) -> Candidate:
    known = {k: row[k] for k in CANDIDATE_COLUMNS if k in row}
    known["origin"] = tuple(known.get("origin") or ())
    known["problems"] = list(known.get("problems") or [])
    return Candidate(**known)


def country_langs(country: str) -> list[str]:
    """The languages a state's offices are labelled in, as two-letter codes where known."""
    territory = get_territory(country)
    return [iso_639_alpha2(lang) or lang for lang in (territory.langs if territory else [])]


class Context:
    """Every live read verify and the guard make for one country, done once.

    Each read is a constructor argument, so `check_mint_verify` hands in a
    fixed world and nothing reaches the network or the tables.
    """

    def __init__(
        self,
        country: str,
        *,
        state_qid: str | None = None,
        langs: Sequence[str] | None = None,
        state_names: Sequence[str] | None = None,
        siblings: offices.Siblings | None = None,
        closure: offices.Closure | None = None,
        index: Sequence[PositionRow] | None = None,
        labels_of: Callable[[Iterable[str]], dict[str, str]] | None = None,
        resolve: Callable[[Iterable[str]], dict[str, dict[str, Any]]] | None = None,
        run_labels: Callable[[Candidate], list[str]] | None = None,
        lookup: Callable[[str, str, str], list[offices.Found]] | None = None,
        items: Callable[[Sequence[str]], dict[str, dict[str, Any]]] | None = None,
        subdivisions: Sequence[str] | None = None,
        anchors: Sequence[Anchor] | None = None,
        claims: Callable[[Sequence[str]], dict[str, dict[str, Any]]] | None = None,
        diplomatic: Callable[[str], bool] | None = None,
        types: Callable[[str], set[str]] | None = None,
    ):
        self.country = country
        self.state_qid = state_qid or positions.country_qid(country)
        self.langs = list(langs) if langs is not None else country_langs(country)
        self._state_names = list(state_names) if state_names is not None else None
        self._siblings = siblings
        self._closure = closure
        self._index = list(index) if index is not None else None
        self._labels_of = labels_of or _labels
        self.resolve = resolve or offices.resolve
        self._run_labels = run_labels or _run_labels
        self.lookup = lookup or offices.live_lookup
        self._items = items or (lambda qids: wikidata.fetch_items(qids, props="labels|descriptions"))
        self._subdivisions = list(subdivisions) if subdivisions is not None else None
        self._anchors = {a.key: a for a in anchors} if anchors is not None else None
        self._claims = claims or (lambda qids: wikidata.fetch_items(qids, props="claims"))
        self._diplomatic = diplomatic or (
            lambda qid: positions.DIPLOMATIC_CLASS in typegraph.of_items([qid]).get(qid, set()))
        #: Every type an item reaches through `P31`/`P279`, itself included.
        self.types = types or (lambda qid: typegraph.of_items([qid]).get(qid, set()))
        self._labels: dict[str, str] = {}

    @property
    def subdivisions(self) -> list[str]:
        """The state's current first-level subdivisions, read live once."""
        if self._subdivisions is None:
            self._subdivisions = [qid for qid, _labels in offices.subdivisions(self.state_qid)]
        return self._subdivisions

    @property
    def anchors(self) -> dict[str, Anchor]:
        """The country's census anchors by key."""
        if self._anchors is None:
            self._anchors = {a.key: a for a in census(self.country)}
        return self._anchors

    def exists_problem(self, qid: str | None) -> str | None:
        """Why an item named as already existing is not this state's office, or None.

        `exists` is the one answer that sends holders to an item nobody
        created for them, so it must be an office of this state -- its `P17`
        or `P1001` the state or one of its subdivisions -- and not a class:
        not an archetype's parent, a position metaclass, or a kind the state's
        own offices subclass ("député", "ambassador to X"). Nor a diplomatic post.
        """
        if not qid:
            return None
        classes = ({a.parent for a in ARCHETYPES.values()} | positions.POSITION_METACLASSES
                   | set(self.siblings.metaclass_by_parent))
        if qid in classes:
            return f"exists-class/{qid}"
        if qid in positions.GENERIC:
            return f"exists-generic/{qid}"
        if self._diplomatic(qid):
            return f"exists-diplomatic/{qid}"
        entity = self._claims([qid]).get(qid) or {}
        scope = set(wikidata.claim_qids(entity, "P17", include_deprecated=False))
        scope |= set(wikidata.claim_qids(entity, "P1001", include_deprecated=False))
        if not scope & ({self.state_qid} | set(self.subdivisions)):
            return f"exists-unscoped/{qid}"
        return None

    @property
    def state_names(self) -> list[str]:
        if self._state_names is None:
            item = wikidata.fetch_items([self.state_qid], props="labels").get(self.state_qid) or {}
            names = [v["value"] for v in item.get("labels", {}).values()]
            self._state_names = list(dict.fromkeys(names))
        return self._state_names

    @property
    def siblings(self) -> offices.Siblings:
        if self._siblings is None:
            self._siblings = offices.siblings(self.state_qid, self.subdivisions)
        return self._siblings

    @property
    def closure(self) -> offices.Closure:
        if self._closure is None:
            self._closure = offices.live_closure()
        return self._closure

    @property
    def index(self) -> list[PositionRow]:
        """The state's existing offices: by `P17` or `P1001`, or scoped to a subdivision."""
        if self._index is None:
            rows = db.conn().execute(
                "SELECT qid, label, kinds, coalesce(not_office, false) FROM position"
                " WHERE country_qid = %s OR jurisdiction_qid = %s OR jurisdiction_qid = ANY(%s)"
                " ORDER BY label NULLS LAST, qid",
                (self.state_qid, self.state_qid, self.subdivisions),
            ).fetchall()
            self._index = [PositionRow(q, l, list(k or []), bool(n)) for q, l, k, n in rows]
        return self._index

    def labels_for(self, qids: Iterable[str | None]) -> dict[str, str]:
        wanted = [q for q in dict.fromkeys(qids) if q]
        missing = [q for q in wanted if q not in self._labels]
        if missing:
            self._labels.update(self._labels_of(missing))
        return {q: self._labels[q] for q in wanted if q in self._labels}

    def label(self, qid: str | None) -> str:
        return self.labels_for([qid]).get(qid or "", "(no label)") if qid else "-"

    def items(self, qids: Sequence[str]) -> dict[str, dict[str, Any]]:
        return self._items(qids) if qids else {}

    def run_labels(self, cand: Candidate) -> list[str]:
        return self._run_labels(cand)


def _run_labels(cand: Candidate) -> list[str]:
    """The labels of the country's other offices that are about to exist.

    Created and creating rows, and guarded rows with a lower id: verify decides
    in id order, so of two candidates with one label the first one guarded
    keeps it, and a rerun decides the same way.
    """
    rows = db.conn().execute(
        "SELECT spec -> 'labels' FROM office_candidate WHERE country = %s AND id <> %s"
        " AND spec IS NOT NULL AND status = ANY(%s) AND (status <> %s OR id < %s)",
        (cand.country, cand.id, list(RUN_STATUSES), GUARDED, cand.id),
    ).fetchall()
    return [text for (labels,) in rows for text in (labels or {}).values()]


#: Words that make a title another seat than the office it was clustered into:
#: the acting holder, the substitute, the co-judge, the deputy. Such a title
#: still attests the office's existence, but as an alias it would name a
#: different seat and let a later search place its holders here. Matched on
#: folded text, so the East Slavic acting forms ("исполняющий
#: обязанности", "врио", "и. о.", "выконваючы абавязкі") and deputy forms
#: ("заместитель", "намеснік", "заступник") are matched transliterated.
ACTING = re.compile(
    r"\b(acting|interim|interino|interina|encargad[oa]|ad hoc|provisional"
    r"|ispolna\w*|obazannost\w*|vrio|vykonva\w*|abavazk\w*)\b|\bi\. ?o\."
)
DEPUTY = re.compile(
    r"\b(substitute|suplente|alternate|co[- ]?judge|conjuez|conjueza|deputy|vice|vice-?\w+"
    r"|adjunt[oa]|zamestitel\w*|namesnik\w*|zastupnik\w*)\b"
)
#: A first deputy is another seat than the deputies of the same ministry.
FIRST = re.compile(r"\b(first|primer[oa]?|premier|premiere|pervyj|pervaa|persy|persaa)\b")
#: Archetypes whose seat *is* a deputy's, so a deputy word in a title is the
#: office's own and only an acting form, or a first deputy where the label
#: names none (or the reverse), is another seat.
DEPUTY_ARCHETYPES = ("deputy_minister",)


def not_the_seat(title: str, labels: dict[str, str], archetype: str | None = None) -> bool:
    """Whether a folded title names another seat than the labelled office."""
    if ACTING.search(title):
        return True
    if archetype not in DEPUTY_ARCHETYPES:
        return bool(DEPUTY.search(title))
    first = any(FIRST.search(_fold(text)) for text in labels.values())
    return bool(FIRST.search(title)) != first


def attested_aliases(attestations: Sequence[Attestation], labels: dict[str, str],
                     state_names: Iterable[str] = (), archetype: str | None = None,
                     ) -> dict[str, list[str]]:
    """The titles the holders' articles wrote, as aliases, per language.

    So the item is found by the words the next article uses. Folded and
    deduplicated, the most-held first, at most `ALIASES_PER_LANG` a language,
    never one of the labels, never a bare seat word ("Governor"), which
    names every office of its kind and would make a live search find them all,
    and never a title that marks another seat (`not_the_seat`), nor one written
    in another language than the article's: a title whose words all sit in
    another language's label and not in its own language's label.
    """
    taken = {_fold(text) for text in labels.values()}
    drop = offices.ROLE_STEMS | state_stems(state_names)
    state = state_stems(state_names)

    def words(text: str) -> set[str]:
        # Whole words, not stems: "secretary" and "secrétaire" share a stem,
        # and with the role words dropped an acronym is all a title has left.
        return {t for t in positions.tokens(text) if t[: positions.PREFIX] not in state}

    label_words = {lang: words(text) for lang, text in labels.items()}

    def misfiled(title: str, lang: str) -> bool:
        # An article quoting a title in another language is attested in its
        # own: the English "Secretary-General of X" from a French article.
        mine = words(title)
        if not mine or mine <= label_words.get(lang, set()):
            return False
        return any(mine <= other for other_lang, other in label_words.items() if other_lang != lang)

    people: dict[tuple[str, str], set[str]] = {}
    written: dict[tuple[str, str], str] = {}
    for a in attestations:
        if not a.title or not a.lang:
            continue
        folded = _fold(a.title)
        if not folded or folded in taken or offices.QID.search(a.title):
            continue
        if not _stems(a.title, drop) or not_the_seat(folded, labels, archetype):
            continue
        if misfiled(a.title, a.lang):
            continue
        key = (a.lang, folded)
        written.setdefault(key, _SPACE.sub(" ", a.title).strip())
        people.setdefault(key, set()).add(a.person)
    order = list(written)
    ranked = sorted(order, key=lambda k: (-len(people[k]), order.index(k)))
    out: dict[str, list[str]] = {}
    for lang, folded in ranked:
        bucket = out.setdefault(lang, [])
        if len(bucket) < ALIASES_PER_LANG:
            bucket.append(written[(lang, folded)])
    return out


def build_spec(cand: Candidate, ctx: Context | None = None) -> tuple[offices.Spec | None, list[str]]:
    """Turn a categorized candidate's draft into the item it would be.

    The shape comes from the archetype and the state's own offices rather than
    the draft wherever the two could differ: `parent_for` over the siblings
    unless the draft named a class the siblings of this kind already use or
    one its title word may name (`Archetype.parents`), and `metaclass_for`
    always.
    The description is `describe`d from resolved labels, never the draft's
    text. None, with the reason, for a seat no archetype fits: there is no
    shape to build.
    """
    ctx = ctx or Context(cand.country)
    arch = cand.kind
    if arch not in ARCHETYPES:
        return None, [f"archetype/{arch}"]
    problems: list[str] = []
    draft = cand.draft or {}
    shape = ARCHETYPES[arch]
    labels = cand.labels
    # A census anchor is curated, so it supplies any language the draft lacks:
    # categorize often drafts only the language its groups were written in.
    anchor = ctx.anchors.get(cand.census_key or "") if cand.census_key else None
    for lang, text in (anchor.labels.items() if anchor else ()):
        labels.setdefault(lang, text)
    # A label is written only in a language that is checked: English, the
    # languages the state's own offices are labelled in, or the census's own.
    # Categorize drafts a label in every official language, and one nobody
    # requires is one nobody reads -- a model's Kirundi would go out unseen.
    keep = {"en", *offices.label_langs(ctx.siblings, ctx.langs), *(anchor.labels if anchor else ())}
    labels = {lang: text for lang, text in labels.items() if lang in keep}
    sibs = ctx.siblings
    # Worded as the state's own offices of the same seat are: "at the
    # Ministry" where they all say "at", whatever the article wrote.
    if labels.get("en"):
        labels["en"] = offices.sibling_form(labels["en"], sibs.labels)
    # And its body, measured for the census, when the draft named none: a
    # draft that took the office for an existing generic class has no body,
    # and without one a "head of the {body}" description cannot be written.
    # Failing both, the body the state's offices of this kind agree on. An
    # archetype that sits where another does (`body_from`) takes the measured
    # body first: a deputy's drafted ministry is the minority shape.
    measured = offices.measured_body(sibs, arch)
    if shape.body_from and measured:
        body = measured
    else:
        body = draft.get("body_qid") or (anchor.body if anchor else None) or measured
    if not labels:
        problems.append("labels/none")
    jurisdiction = draft.get("jurisdiction_qid") or (ctx.state_qid if shape.scoped else None)
    drafted = draft.get("parent_qid")
    measured = set(sibs.parents.get(arch) or ())
    # The state's own offices of the same seat, read by label, outrank the
    # draft among the kinds the archetype allows.
    seat = offices.seat_parent(labels.get("en", ""), sibs, shape.parents or (shape.parent,))
    if seat:
        parent = seat
    elif drafted and (drafted in shape.parents or drafted in measured):
        parent = drafted
    else:
        parent = offices.parent_for(sibs, arch)
        if drafted and drafted != parent:
            problems.append(f"parent-replaced/{drafted}")
    spec = offices.Spec(
        ref=cand.ref, archetype=arch, labels=labels, state_qid=ctx.state_qid,
        aliases=attested_aliases(cand.attestations, labels, ctx.state_names, arch),
        metaclass=offices.metaclass_for(sibs, parent, shape.metaclass), parent=parent,
        jurisdiction_qid=jurisdiction, body_qid=body,
        replaces=draft.get("replaces_qid"),
    )
    text = offices.describe(spec, ctx.labels_for([spec.body_qid, spec.jurisdiction, spec.state_qid]))
    if text:
        spec.descriptions = {"en": text}
    else:
        problems.append("description")
    return spec, problems


def spec_from(stored: dict[str, Any]) -> offices.Spec:
    """A `Spec` back from its `office_candidate.spec` JSON."""
    return offices.Spec(**stored)


def live_duplicates(spec: offices.Spec, ctx: Context) -> list[offices.Found]:
    """Every live search hit for every label and alias, one per item.

    A hit found by two names keeps the reading in which its name matched, so a
    duplicate found by an alias is not lost behind the label's miss.
    """
    names = [*spec.labels.items(), *((lang, t) for lang, many in spec.aliases.items() for t in many)]
    out: dict[str, offices.Found] = {}
    for lang, text in dict.fromkeys(names):
        for hit in ctx.lookup(text, lang, spec.state_qid):
            have = out.get(hit.qid)
            if have is None or (hit.label_match and not have.label_match):
                out[hit.qid] = hit
            elif hit.matched:
                out[hit.qid] = replace(have, matched=have.matched | hit.matched)
    return list(out.values())


def scoped_duplicate(found: Iterable[offices.Found], bodies: Collection[str] = ()) -> str | None:
    """The duplicate that is this state's, or None.

    `duplicate_of` also blocks on a matching item that names no state at all,
    which is right for a guard and wrong for `found`: a countryless "member of
    the political bureau" would then receive this state's holders. So only a
    duplicate that names the state is taken as the office; the other kind
    still blocks, through the guard, as a skip. Nor is a body the office: a
    council found by its own name would receive its members' `P39`s, so the
    office's `bodies` and any hit typed as an organisation are passed over
    here and named by the guard as `hit-is-body`.
    """
    return offices.duplicate_of(hit for hit in found if hit.country_match
                                and not (hit.qid in bodies or hit.is_body))


@dataclass
class Evidence:
    """Everything one verify request shows, and the QIDs it may cite back."""

    attestations: str
    duplicates: str
    index: str
    siblings: str
    draft: str
    #: Every QID the request names: what a correction may use.
    shown: set[str] = field(default_factory=set)
    #: The offices among them: what an `exists` may name.
    office_qids: set[str] = field(default_factory=set)
    found: list[offices.Found] = field(default_factory=list)

    def message(self) -> str:
        return "\n".join([
            "# The attestations", "", self.attestations, "",
            "# Live duplicates", "", self.duplicates, "",
            "# The state's offices", "", self.index, "",
            "# Sibling tallies", "", self.siblings, "",
            "# The draft", "", self.draft, "",
            "Is this a real, current office that Wikidata is missing, shaped like its"
            " siblings? Answer with the verdict that names what is wrong, or `mint`.",
        ])


def _span(a: Attestation) -> str:
    if not a.start and not a.end:
        return "no dates"
    return f"{a.start or '?'}–{a.end or ('present' if a.current else '')}".rstrip("–")


def render_attestations(cand: Candidate) -> str:
    """One block per distinct person, each mention as the article wrote it."""
    by_person: dict[str, list[Attestation]] = {}
    for a in cand.attestations:
        by_person.setdefault(a.person, []).append(a)
    if not by_person:
        return "- none"
    blocks = []
    for person, mentions in by_person.items():
        lines = [f"## {person} {mentions[0].person_label or '(no label)'}"]
        for a in mentions:
            head = [f"“{a.title or '(no title)'}”"]
            if a.jurisdiction:
                head.append(f"jur: {a.jurisdiction}")
            head.append(_span(a))
            flags = [flag for flag, on in (("current", a.current), ("acting", a.acting)) if on]
            head.append(", ".join(flags) or "not current")
            head.append(f"lang {a.lang or '?'}")
            lines.append("- " + " | ".join(head))
            lines.extend(f"  > “{_clip(q, VERIFY_QUOTE_CHARS)}”" for q in a.quotes)
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _labelled(qids: Iterable[str], ctx: Context) -> str:
    qids = list(dict.fromkeys(qids))
    labels = ctx.labels_for(qids)
    return ", ".join(f"{q} {labels.get(q, '(no label)')}" for q in qids) or "-"


def _pick_term(terms: dict[str, Any], langs: Sequence[str]) -> tuple[str | None, str | None]:
    for lang in ("en", *langs, "mul"):
        if lang in terms:
            return terms[lang]["value"], lang
    for lang, obj in terms.items():
        return obj["value"], lang
    return None, None


def render_duplicates(found: Sequence[offices.Found], ctx: Context) -> tuple[str, set[str]]:
    """The live hits worth reading, name matches first, and their QIDs."""
    hits = [h for h in found if not (h.types & offices.NOT_A_POSITION)]
    hits.sort(key=lambda h: (not h.label_match, not h.country_match, h.qid))
    hits = hits[:DUPLICATES_SHOWN]
    if not hits:
        return "- none found", set()
    items = ctx.items([h.qid for h in hits])
    lines = []
    for h in hits:
        item = items.get(h.qid, {})
        label, lang = _pick_term(item.get("labels", {}), ctx.langs)
        described, _l = _pick_term(item.get("descriptions", {}), ctx.langs)
        line = (f"- {h.qid} | {label or '(no label)'} ({lang or '-'}) | {described or '-'}"
                f" | P31: {_labelled(sorted(h.types), ctx)}"
                f" | P17/P1001: {_labelled(h.country_qids, ctx)}")
        if h.label_match:
            line += " | exact name"
        lines.append(line)
    return "\n".join(lines), {h.qid for h in hits}


def render_index(spec: offices.Spec | None, ctx: Context) -> tuple[str, list[PositionRow]]:
    """The state's offices: all of them, or past `INDEX_CAP` those sharing a word."""
    rows = ctx.index
    if len(rows) > INDEX_CAP and spec is not None:
        drop = offices.ROLE_STEMS | state_stems(ctx.state_names)
        words: set[str] = set()
        for text in [*spec.labels.values(), *(t for ts in spec.aliases.values() for t in ts)]:
            words |= _stems(text, drop)
        rows = [p for p in rows if _stems(p.label, drop) & words][:INDEX_CAP]
    return "\n".join(f"- {p.line()}" for p in rows) or "- (none loaded)", list(rows)


def render_siblings(ctx: Context) -> tuple[str, set[str]]:
    """How the state's offices are typed, every QID with its label."""
    sibs = ctx.siblings
    lines, shown = ["## Kinds of seat (P279), by archetype", ""], set()
    for arch, tally in sorted(sibs.parents.items()):
        shown |= set(tally)
        lines.append(f"- {arch}: " + "; ".join(
            f"{q} {ctx.label(q)} ×{n}" for q, n in tally.most_common()))
    if not sibs.parents:
        lines.append("- none measured")
    lines += ["", "## Metaclasses (P31)", ""]
    lines += [f"- {q} {ctx.label(q)} ×{n}" for q, n in sibs.metaclasses.most_common(8)] or ["- none"]
    lines += ["", "## Bodies (P361/P2389)", ""]
    lines += [f"- {q} {ctx.label(q)} ×{n}" for q, n in sibs.bodies.most_common(15)] or ["- none"]
    shown |= set(sibs.metaclasses) | {q for q, _n in sibs.bodies.most_common(15)}
    return "\n".join(lines), shown


#: The structural properties a minted item carries, named for the reader.
DRAFT_PROPERTY_NAMES = {
    "P31": "instance of", "P279": "subclass of", "P17": "country",
    "P1001": "applies to jurisdiction", "P361": "part of",
    "P2389": "organization directed by the office or position", "P1365": "replaces",
}


def render_draft(spec: offices.Spec | None, ctx: Context) -> tuple[str, set[str]]:
    """The item as it would be created: terms, then every statement with labels."""
    if spec is None:
        return "- no draft", set()
    data = offices.entity_data(spec)
    shape = spec.shape
    seat = "one person at a time" if shape.single_seat else "each member holds it"
    lines = [f"archetype: {spec.archetype} ({seat})", ""]
    lines += [f"label ({lang}): {text}" for lang, text in spec.labels.items()]
    lines += [f"alias ({lang}): {'; '.join(texts)}" for lang, texts in spec.aliases.items()]
    lines += [f"description ({lang}): {text}" for lang, text in spec.descriptions.items()]
    lines.append("")
    shown = set()
    for claim in data["claims"]:
        snak = claim["mainsnak"]
        qid = snak["datavalue"]["value"]["id"]
        shown.add(qid)
        name = DRAFT_PROPERTY_NAMES.get(snak["property"], snak["property"])
        lines.append(f"{snak['property']} {name}: {qid} {ctx.label(qid)}")
    return "\n".join(lines), shown


def evidence(cand: Candidate, *, spec: offices.Spec | None = None, ctx: Context | None = None,
             found: list[offices.Found] | None = None) -> Evidence:
    """Gather and render what verify is shown about one candidate.

    `found` is read live when not given, for every label and alias.
    """
    ctx = ctx or Context(cand.country)
    if spec is None:
        spec, _problems = build_spec(cand, ctx)
    if found is None:
        found = live_duplicates(spec, ctx) if spec is not None else []
    dups, dup_qids = render_duplicates(found, ctx)
    index, rows = render_index(spec, ctx)
    sibs, sib_qids = render_siblings(ctx)
    draft, draft_qids = render_draft(spec, ctx)
    offices_shown = dup_qids | {p.qid for p in rows if not p.not_office}
    return Evidence(
        attestations=render_attestations(cand), duplicates=dups, index=index, siblings=sibs,
        draft=draft, shown=offices_shown | {p.qid for p in rows} | sib_qids | draft_qids,
        office_qids=offices_shown, found=list(found),
    )


@dataclass
class MintVerdict:
    """The verifier's answer after the gate: off-list QIDs removed, and why."""

    verdict: str
    real: bool
    current: bool
    missing: bool
    shape: str
    confidence: str
    exists_qid: str | None = None
    corrections: dict[str, str | None] = field(default_factory=dict)
    evidence: str = ""
    reason: str = ""
    problems: list[str] = field(default_factory=list)
    call: int | None = None

    @property
    def corrected(self) -> str | None:
        """The first field a `correct` answer changed, in `CORRECTION_FIELDS` order."""
        return next((f for f in CORRECTION_FIELDS if self.corrections.get(f)), None)


def settle_verify(answer: VerifyAnswer, ev: Evidence, call: int | None = None) -> MintVerdict:
    """Keep what of an answer the request could have supported.

    An `exists` must name an office the request showed, or it names nothing
    and the rules skip it; a correction QID must be one the request showed.
    Pure, so `check_mint_verify` pins it.
    """
    problems = []
    exists = answer.exists_qid if answer.verdict == "exists" else None
    if exists and exists not in ev.office_qids:
        problems.append(f"off-list:exists_qid:{exists}")
        exists = None
    corrections = answer.corrections.model_dump()
    for name in CORRECTION_QIDS:
        qid = corrections.get(name)
        if qid and qid not in ev.shown:
            problems.append(f"off-list:{name}:{qid}")
            corrections[name] = None
    return MintVerdict(
        verdict=answer.verdict, real=answer.real, current=answer.current,
        missing=answer.missing, shape=answer.shape, confidence=answer.confidence,
        exists_qid=exists, corrections=corrections, evidence=answer.evidence,
        reason=answer.reason, problems=problems, call=call,
    )


def ask_verify(message: str, model: str) -> tuple[VerifyAnswer, dict[str, int]]:
    """Send one verify request and return the parsed answer and its usage."""
    text, _hash = verify_prompt()
    response = llm.client().messages.parse(
        output_format=VerifyAnswer,
        model=model,
        max_tokens=VERIFY_MAX_TOKENS,
        thinking={"type": "adaptive"},
        output_config={"effort": VERIFY_EFFORT},
        system=[{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": message}],
    )
    if response.parsed_output is None:
        raise RuntimeError(f"verify: no parsed output ({response.stop_reason})")
    return response.parsed_output, llm.usage(response)


def recorded_verify(key: str, prompt_hash: str, model: str) -> tuple[int, VerifyAnswer, dict] | None:
    """The answer the ledger already holds for this exact request, if any."""
    row = db.conn().execute(
        "SELECT id, response_json, usage_json FROM mint_call WHERE pass = 'verify'"
        " AND content_key = %s AND prompt_hash = %s AND render_version = %s AND model = %s",
        (key, prompt_hash, VERIFY_RENDER_VERSION, model),
    ).fetchone()
    if row is None:
        return None
    return row[0], VerifyAnswer.model_validate(row[1]), row[2] or {}


def store_verify(country: str, key: str, prompt_hash: str, model: str, message: str,
                 answer: VerifyAnswer, usage: dict[str, int]) -> int:
    row = db.conn().execute(
        "INSERT INTO mint_call (pass, country, content_key, prompt_hash, render_version, model,"
        " request_json, response_json, usage_json) VALUES ('verify', %s, %s, %s, %s, %s, %s, %s, %s)"
        " ON CONFLICT (pass, content_key, prompt_hash, render_version, model)"
        " DO UPDATE SET country = EXCLUDED.country RETURNING id",
        (country, key, prompt_hash, VERIFY_RENDER_VERSION, model,
         Jsonb({"message": message}), Jsonb(answer.model_dump()), Jsonb(usage)),
    ).fetchone()
    return row[0]


@dataclass
class Verified:
    """One candidate's pass through verify: what was shown, and the answer."""

    evidence: Evidence
    message: str
    verdict: MintVerdict | None
    asked: bool = False
    usage: dict[str, int] = field(default_factory=dict)


def verify_candidate(cand: Candidate, dry_run: bool = False, *, ctx: Context | None = None,
                     spec: offices.Spec | None = None, model: str = VERIFY_MODEL) -> Verified:
    """Verify one candidate once: read the ledger, or render, ask and record.

    Keyed by the rendered request, so a rerun over unchanged evidence pays
    nothing and a new duplicate on Wikidata is a new question. A dry run
    renders and reads the ledger, and asks nothing.
    """
    ctx = ctx or Context(cand.country)
    ev = evidence(cand, spec=spec, ctx=ctx)
    message = ev.message()
    _text, prompt_hash = verify_prompt()
    key = content_key(message)
    known = recorded_verify(key, prompt_hash, model)
    if known is not None:
        call, answer, _usage_seen = known
        return Verified(ev, message, settle_verify(answer, ev, call))
    if dry_run:
        return Verified(ev, message, None)
    answer, usage = ask_verify(message, model)
    call = store_verify(cand.country, key, prompt_hash, model, message, answer, usage)
    return Verified(ev, message, settle_verify(answer, ev, call), asked=True, usage=usage)


# --- disposition ---------------------------------------------------------------


@dataclass
class Case:
    """What one disposition rule may read: the candidate and every verdict on it."""

    cand: Candidate
    spec: offices.Spec | None
    verdict: MintVerdict | None
    guard_reasons: list[str]
    #: The live item of this state that the office would duplicate.
    dup: str | None
    #: Why categorize's `exists` item is not this state's office, if it is not.
    exists_problem: str | None = None
    #: The same for the verifier's `exists` item.
    verify_exists_problem: str | None = None


Decision = tuple[str, str]
Rule = Callable[[Case], Optional[Decision]]


def census_unattested(case: Case) -> Decision | None:
    if "census" in case.cand.origin and not case.cand.attestations:
        return SKIPPED, "census/unattested"
    return None


def categorize_refused(case: Case) -> Decision | None:
    if case.cand.decision not in ("office", "exists"):
        return SKIPPED, f"categorize/{case.cand.decision or 'none'}"
    return None


def categorize_exists(case: Case) -> Decision | None:
    if case.cand.decision != "exists":
        return None
    if not (case.cand.draft or {}).get("exists_qid"):
        return SKIPPED, "categorize/exists-unnamed"
    if case.exists_problem:
        return None  # not this state's office: the rules below decide, problem kept
    return FOUND, "categorize:exists"


def diplomatic(case: Case) -> Decision | None:
    if case.cand.kind == "ambassador" or any(
            offices.bilateral(text) for text in case.cand.labels.values()):
        return SKIPPED, "diplomatic/deferred"
    return None


def no_archetype(case: Case) -> Decision | None:
    if case.cand.kind not in ARCHETYPES:
        return SKIPPED, "archetype/none"
    return None


def below_floor(case: Case) -> Decision | None:
    refused = floor(case.cand)
    return (SKIPPED, refused) if refused else None


def live_duplicate(case: Case) -> Decision | None:
    return (FOUND, "guard:duplicate") if case.dup else None


def verify_exists(case: Case) -> Decision | None:
    v = case.verdict
    if v is not None and v.verdict == "exists" and v.exists_qid and not case.verify_exists_problem:
        return FOUND, "verify:exists"
    return None


def verify_refused(case: Case) -> Decision | None:
    v = case.verdict
    if v is None:
        return SKIPPED, "verify:none"
    if v.verdict != "mint":
        return SKIPPED, f"verify:{v.verdict}"
    for name in ("real", "current", "missing"):
        if not getattr(v, name):
            return SKIPPED, f"verify:mint/not-{name}"
    return None


def shape_disagree(case: Case) -> Decision | None:
    v = case.verdict
    if v is not None and v.shape == "correct":
        return SKIPPED, f"disagree/shape:{v.corrected or 'unspecified'}"
    return None


def guard_refused(case: Case) -> Decision | None:
    if case.guard_reasons:
        return SKIPPED, f"guard:{case.guard_reasons[0]}"
    return None


def agreed(case: Case) -> Decision:
    v = case.verdict
    confidence = v.confidence if v is not None else "none"
    if confidence == "high":
        return GUARDED, "mint:agreed"
    return SKIPPED, f"verify:confidence/{confidence}"


RULES: tuple[Rule, ...] = (
    # Decided without tokens: is there anything to ask about at all.
    census_unattested,   # 1. a census anchor no article attests
    categorize_refused,  # 2. categorize said it is not an office
    diplomatic,          # 3. a posting abroad: needs the two-state shape, and
                         #    is never `found` on a generic ambassadorship
    categorize_exists,   # 4. categorize named the item it is: only an office
                         #    of this state and not a class; else fall through
    no_archetype,        # 5. no fixed shape to build
    below_floor,         # 6. one attested holder, and a current one
    # Decided on the live search and the model, in that order: a duplicate
    # beats any verdict, and an item the verifier names is taken as found.
    live_duplicate,      # 7. a live item of this state already has the name
    verify_exists,       # 8. the verifier named the item it is
    verify_refused,      # 9. real, current and missing, or skip
    shape_disagree,      # 10. the verifier would shape it otherwise. A future
                         #     rule may accept a correction naming a measured
                         #     sibling parent; the corrections are kept for it.
    guard_refused,       # 11. every static reason not to create
    agreed,              # 12. only on high confidence
)
#: The rules that read neither the live search nor the model.
MODEL_FREE = RULES[:6]


def _first(case: Case, rules: Sequence[Rule]) -> Decision | None:
    for rule in rules:
        found = rule(case)
        if found is not None:
            return found
    return None


def disposition(cand: Candidate, spec: offices.Spec | None, verdict: MintVerdict | None,
                guard_reasons: Sequence[str], dup: str | None, *,
                exists_problem: str | None = None,
                verify_exists_problem: str | None = None) -> Decision:
    """Decide one candidate: the first rule in `RULES` that applies, as (status, rule).

    The status is `skipped`, `found` or `guarded` and nothing else: every case
    is decided, a disagreement between the stages is a skip that names it, and
    a `guarded` row is one categorize, verify and the guard all agree on.
    """
    case = Case(cand, spec, verdict, list(guard_reasons), dup, exists_problem,
                verify_exists_problem)
    found = _first(case, RULES)
    assert found is not None  # `agreed` always answers
    return found


def found_qid(rule: str, cand: Candidate, verdict: MintVerdict | None, dup: str | None) -> str | None:
    """The item a `found` disposition names, by the rule that found it."""
    if rule == "categorize:exists":
        return (cand.draft or {}).get("exists_qid")
    if rule == "guard:duplicate":
        return dup
    if rule == "verify:exists" and verdict is not None:
        return verdict.exists_qid
    return None


def spec_bodies(cand: Candidate, spec: offices.Spec | None, ctx: Context) -> set[str]:
    """The bodies a candidate is known to sit in: its spec's, and its census anchor's."""
    anchor = ctx.anchors.get(cand.census_key or "") if cand.census_key else None
    return {q for q in (spec.body_qid if spec else None, anchor.body if anchor else None) if q}


def guard_reasons(cand: Candidate, spec: offices.Spec, ctx: Context,
                  found: Sequence[offices.Found]) -> list[str]:
    """Run `offices.guard` over a candidate with every live input it reads."""
    jurisdiction = spec.jurisdiction if spec.jurisdiction != spec.state_qid else None
    records = ctx.resolve([q for q in (spec.body_qid, jurisdiction) if q])
    # Asked only where the level check would refuse: a mayor of a first-level
    # subdivision, which is a town when it is typed as one.
    municipal = bool(
        jurisdiction and spec.shape.level == "municipality" and jurisdiction in ctx.subdivisions
        and ctx.types(jurisdiction) & offices.MUNICIPAL_CLASSES)
    return offices.guard(
        spec,
        holders=cand.holders,
        current_holders=cand.current_holders,
        duplicates=found,
        run_labels=ctx.run_labels(cand),
        body=records.get(spec.body_qid) if spec.body_qid else None,
        jurisdiction=records.get(jurisdiction) if jurisdiction else None,
        closure=ctx.closure,
        langs=offices.label_langs(ctx.siblings, ctx.langs),
        state_names=ctx.state_names,
        known_bodies={q for q, n in ctx.siblings.bodies.items() if n >= offices.MEASURED_BODY_USES},
        regions=set(ctx.subdivisions),
        municipal=municipal,
        bodies=spec_bodies(cand, spec, ctx),
    )


def reguard(cand_row: Candidate | dict[str, Any] | int, ctx: Context | None = None) -> list[str]:
    """Re-run the live guard for a candidate about to be created.

    Called immediately before the create, because a duplicate made since verify
    ran must still block: the searches, the body and jurisdiction records, the
    run's other labels and the holder counts are all read again. The spec is
    the stored one, so what is guarded is what will be sent. Returns the guard
    reasons; empty means it may be created, `duplicate/Q…` names a duplicate.
    """
    if isinstance(cand_row, Candidate):
        cand = cand_row
    elif isinstance(cand_row, dict) and "country" in cand_row:
        # The row as the caller locked it: read nothing back but the attestations.
        cand = _candidate(cand_row)
        cand.attestations = _attestations([cand.id]).get(cand.id, [])
    else:
        cid = cand_row if isinstance(cand_row, int) else cand_row["id"]
        found = load_candidates_by_id([cid])
        if not found:
            return [f"candidate/{cid}"]
        cand = found[0]
    ctx = ctx or Context(cand.country)
    spec = spec_from(cand.spec) if cand.spec else build_spec(cand, ctx)[0]
    if spec is None:
        return [f"archetype/{cand.kind}"]
    return guard_reasons(cand, spec, ctx, live_duplicates(spec, ctx))


def load_candidates_by_id(ids: Sequence[int]) -> list[Candidate]:
    """Candidates by id whatever their country or status, with their attestations."""
    rows = db.conn().execute(
        f"SELECT {', '.join(CANDIDATE_COLUMNS)} FROM office_candidate WHERE id = ANY(%s) ORDER BY id",
        (list(ids),),
    ).fetchall()
    out = [_candidate(dict(zip(CANDIDATE_COLUMNS, row))) for row in rows]
    found = _attestations([c.id for c in out])
    for cand in out:
        cand.attestations = found.get(cand.id, [])
    return out


def record_disposition(cand: Candidate, status: str, rule: str, *, spec: offices.Spec | None,
                       problems: Sequence[str], verdict: MintVerdict | None, qid: str | None) -> bool:
    """Write one decision onto its candidate. False when the row moved on meanwhile."""
    if status not in DISPOSITION_STATUSES:
        raise ValueError(f"not a disposition: {status}")
    kept = [p for p in cand.problems if not p.startswith(STAGE_PREFIXES)]
    row = db.conn().execute(
        "UPDATE office_candidate SET status = %s, rule = %s, problems = %s, spec = %s, data = %s,"
        " corrections = %s, verify_call = %s, qid = %s,"
        " updated_at = now() WHERE id = %s AND status = ANY(%s) AND decided_by IS NULL"
        " RETURNING id",
        (status, rule, kept + list(problems),
         Jsonb(asdict(spec)) if spec is not None else None,
         Jsonb(offices.entity_data(spec)) if spec is not None else None,
         Jsonb(verdict.corrections) if verdict is not None else None,
         verdict.call if verdict is not None else None, qid,
         cand.id, list(VERIFIABLE)),
    ).fetchone()
    return row is not None


class _Done:
    """A finished call, shaped like the future a pool would return."""

    def __init__(self, fn: Callable[..., Any], *args: Any):
        try:
            self.value, self.error = fn(*args), None
        except Exception as exc:  # noqa: BLE001 -- re-raised by result(), as a pool does
            self.value, self.error = None, exc

    def result(self) -> Any:
        if self.error is not None:
            raise self.error
        return self.value


class _Inline:
    """A pool of one that runs each call where it is submitted."""

    def __enter__(self) -> "_Inline":
        return self

    def __exit__(self, *_exc: Any) -> None:
        return None

    def submit(self, fn: Callable[..., Any], *args: Any) -> _Done:
        return _Done(fn, *args)


def verify(
    country: str,
    limit: int | None = None,
    threads: int = 4,
    dry_run: bool = False,
    log: Callable[[str], None] = print,
    *,
    model: str = VERIFY_MODEL,
    ctx: Context | None = None,
    ids: Sequence[int] | None = None,
) -> dict[str, Any]:
    """Decide every categorized candidate of a country: found, guarded or skipped.

    The rules that need no tokens run first, over every candidate; only an
    office of a mintable kind that clears the floor is shown to the model,
    one request each, under a thread pool and through the ledger. Then every
    candidate is decided in id order, so that of two with one label the
    lower id keeps it. `limit` caps the requests; candidates beyond it are
    left as they are for the next run. A dry run renders the first request,
    counts what would be asked, and writes nothing.
    """
    ctx = ctx or Context(country)
    cands = load_candidates(country, ids)
    stats: dict[str, Any] = {"candidates": len(cands), "asked": 0, "recorded": 0, "failed": 0,
                             "usage": {k: 0 for k in USAGE_KEYS}, "funnel": Counter()}
    planned: list[tuple[Candidate, offices.Spec | None, list[str], Decision | None]] = []
    exists_problems: dict[int, str | None] = {}
    for cand in cands:
        spec, problems = build_spec(cand, ctx)
        if cand.decision == "exists":
            exists_problems[cand.id] = ctx.exists_problem((cand.draft or {}).get("exists_qid"))
            if exists_problems[cand.id]:
                problems.append(exists_problems[cand.id])
        early = _first(Case(cand, spec, None, [], None, exists_problems.get(cand.id)), MODEL_FREE)
        planned.append((cand, spec, problems, early))
    ask = [(c, s) for c, s, _p, early in planned if early is None]
    if limit is not None:
        ask = ask[:limit]
    if dry_run:
        to_ask = 0
        for i, (cand, spec) in enumerate(ask):
            done = verify_candidate(cand, dry_run=True, ctx=ctx, spec=spec, model=model)
            to_ask += done.verdict is None
            if i == 0:
                log(done.message)
        stats["recorded"] = len(ask) - to_ask
        early_rules = Counter(early for _c, _s, _p, early in planned if early)
        stats["funnel"] = early_rules
        log(f"{country}: {len(cands)} candidates, {len(ask)} for the model"
            f" ({to_ask} to ask, {len(ask) - to_ask} in the ledger)")
        return stats

    results: dict[int, Verified] = {}

    def run(cand: Candidate, spec: offices.Spec | None) -> tuple[int, Verified]:
        return cand.id, verify_candidate(cand, ctx=ctx, spec=spec, model=model)

    # One thread runs inline, on this thread's connection: a pool thread opens
    # its own, which cannot see a caller's temporary tables.
    pool = ThreadPoolExecutor(max_workers=threads) if threads > 1 else None
    with pool or _Inline() as runner:
        futures = {runner.submit(run, c, s): c for c, s in ask}
        for future, cand in futures.items():
            try:
                cid, done = future.result()
            except Exception as exc:  # noqa: BLE001 -- one failure is not the run's
                stats["failed"] += 1
                log(f"{cand.ref}: verify failed: {exc}")
                continue
            results[cid] = done
            if done.asked:
                stats["asked"] += 1
                for k in USAGE_KEYS:
                    stats["usage"][k] += done.usage.get(k, 0)
            else:
                stats["recorded"] += 1

    decided: dict[int, dict[str, Any]] = {}
    for cand, spec, problems, early in planned:
        verdict, reasons, dup = None, [], None
        if early is not None:
            status, rule = early
        elif cand.id in results:
            verdict = results[cand.id].verdict
            found = results[cand.id].evidence.found
            dup = scoped_duplicate(found, spec_bodies(cand, spec, ctx))
            reasons = guard_reasons(cand, spec, ctx, found) if spec is not None else []
            verify_problem = (ctx.exists_problem(verdict.exists_qid)
                              if verdict is not None and verdict.verdict == "exists" else None)
            if verify_problem and verdict is not None:
                verdict.problems.append(verify_problem)
            status, rule = disposition(cand, spec, verdict, reasons, dup,
                                       exists_problem=exists_problems.get(cand.id),
                                       verify_exists_problem=verify_problem)
        else:
            continue
        qid = found_qid(rule, cand, verdict, dup) if status == FOUND else None
        written = [f"spec:{p}" for p in problems]
        written += [f"verify:{p}" for p in (verdict.problems if verdict else [])]
        written += [f"guard:{r}" for r in reasons]
        if record_disposition(cand, status, rule, spec=spec, problems=written, verdict=verdict,
                              qid=qid):
            stats["funnel"][(status, rule)] += 1
            decided[cand.id] = {"status": status, "rule": rule, "qid": qid, "spec": spec,
                                "verdict": verdict, "problems": written}
            log(f"{cand.id:>5} {status:<8} {rule:<32} {cand.ref}")
    stats["decided"] = decided
    return stats
