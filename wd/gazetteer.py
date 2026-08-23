"""The closed set of position items a judgement pass is allowed to name.

Position association is the hard half of enriching a person: the evidence says
"Minister of Roads and Urban Development, 2013–2017" and something has to turn
that into a QID. Handing an LLM the whole of Wikidata invites a plausible,
wrong, unverifiable QID. So the model never searches — it picks from a list
assembled here, and anything it cannot find in that list it reports as prose,
which becomes an item-creation candidate instead of a bad statement.

Two shapes, because a `wd_categories.yml` spec has two shapes:

* an **office** or **membership** spec names one seat, so the gazetteer is the
  target plus the items that are the same office under another name — a renamed
  ministry, a predecessor body. Position association collapses to "this one, or
  none, and when".
* a **bucket** spec names a class ("Governor of a Russian Region"), so the
  gazetteer is every position item the country has. Measured 62 (Lesotho), 194
  (Czechia), 200 (Iran) — small enough to sit in a cached system block, which is
  what makes one request per person affordable.

The rendering is the *prefix* of every request in a run, so it must be
byte-stable: entries are sorted and nothing derived from the clock goes in it.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set

from requests import Session

from wd.api import best_description, best_label, claim_qids, fetch_entities, sparql
from wd.shape import type_closure, verify

#: `P31`/`P279` into the position tree. `p:P31/ps:P31` and not `wdt:P31`: one
#: preferred value hides the normal-rank ones, and `wdt:` reports Q12251224
#: "Crown Prince of Saudi Arabia" — a live spec target — as not a position.
COUNTRY_OFFICES = """SELECT DISTINCT ?pos WHERE {
  ?pos p:P31/ps:P31/wdt:P279* wd:Q4164871 .
  { ?pos wdt:P17 wd:%(country)s } UNION { ?pos wdt:P1001 wd:%(country)s }
}"""

#: Closed candidate sets for the P39 qualifiers worth asserting. Same principle
#: as the position gazetteer: the model names the thing in prose and may only be
#: matched against a set we fetched, so it can never invent an identifier.
#:
#: A set is frequently **empty**, and that is a finding rather than a gap —
#: Guatemala has no electoral-district items and no parliamentary-group items at
#: all, so those qualifiers cannot be asserted there however good the evidence
#: is. Report the measurement; do not reach for a looser match.
QUALIFIER_CLASSES = {
    #: P768 electoral district — the constituency a seat was won in.
    "P768": "Q192611",
    #: P4100 parliamentary group — the caucus, not the party. `P102` is the
    #: person-level party claim and is a different statement.
    "P4100": "Q848197",
}

QUALIFIER_QUERY = """SELECT DISTINCT ?x WHERE {
  ?x p:P31/ps:P31/wdt:P279* wd:%(cls)s . ?x wdt:P17 wd:%(country)s
}"""


#: The same office under another name. A ministry renamed each cabinet is
#: several items on Wikidata and a roster's rows are on record under whichever
#: one covered the term — see `Office.date_targets` in `wd/campaign.py`.
SUCCESSION_PROPS = ("P1365", "P1366")   # replaces / replaced by


@dataclass
class Entry:
    """One nameable office, with what it takes to tell it from its neighbours."""

    qid: str
    label: Optional[str] = None
    description: Optional[str] = None
    aliases: List[str] = field(default_factory=list)
    #: `P279` targets by label — the *kind* of office, which is how a seat is
    #: told from the body it sits in.
    kinds: List[str] = field(default_factory=list)
    body: Optional[str] = None          # P361 label
    inception: Optional[str] = None     # P571
    abolished: Optional[str] = None     # P576
    holders: int = 0
    topics: List[str] = field(default_factory=list)
    defects: List[str] = field(default_factory=list)
    replaces: List[str] = field(default_factory=list)
    replaced_by: List[str] = field(default_factory=list)

    def line(self) -> str:
        """One line for the prompt prefix. Terse on purpose — this is paid for
        once per run at cache-write price and then re-read on every person."""
        parts = [f"{self.qid} | {self.label or '(no label)'}"]
        if self.description:
            parts.append(self.description)
        if self.kinds:
            parts.append("kind: " + ", ".join(self.kinds))
        if self.body:
            parts.append("part of: " + self.body)
        span = "–".join([self.inception or "", self.abolished or ""]).strip("–")
        if span:
            parts.append("exists: " + span)
        if self.topics:
            parts.append("topics: " + ",".join(sorted(self.topics)))
        parts.append(f"{self.holders} recorded holders")
        if self.defects:
            parts.append("item defects: " + ",".join(self.defects))
        return " | ".join(parts)


@dataclass
class Gazetteer:
    scope: str                    # what the set is ("target Q7250572", "country Q794")
    entries: List[Entry] = field(default_factory=list)

    @property
    def qids(self) -> Set[str]:
        return {e.qid for e in self.entries}

    def __contains__(self, qid: str) -> bool:
        return qid in self.qids

    def render(self) -> str:
        """The cacheable system block. Sorted, so the prefix is byte-stable."""
        head = [
            "# Position items you may name",
            "",
            "These are the only QIDs you may use as a P39 value. One line per",
            "office: QID | label | description | kind | part of | exists | topics |",
            "holders | item defects.",
            "",
            "A `kind` or `part of` naming a ministry, council, committee or general",
            "staff is a *body*; the office is the seat in it. If the evidence names a",
            "body rather than a seat, say so rather than picking the body's item.",
            "",
            "If the office the evidence names is not in this list, do not guess a",
            "QID — report it by name and leave the QID null.",
            "",
        ]
        lines = [e.line() for e in sorted(self.entries, key=lambda e: e.qid)]
        return "\n".join(head + lines)


def _holder_counts(session: Session, qids: Sequence[str]) -> Dict[str, int]:
    counts = {q: 0 for q in qids}
    for start in range(0, len(qids), 120):
        values = " ".join(f"wd:{q}" for q in list(qids)[start:start + 120])
        rows = sparql(session, f"""SELECT ?pos (COUNT(DISTINCT ?h) AS ?n) WHERE {{
          VALUES ?pos {{ {values} }} OPTIONAL {{ ?h p:P39/ps:P39 ?pos }}
        }} GROUP BY ?pos""", max_age=0)
        for row in rows:
            counts[row["pos"]] = int(row["n"])
    return counts


def _time(entity: dict, prop: str) -> Optional[str]:
    for claim in (entity.get("claims") or {}).get(prop, []):
        if claim.get("rank") == "deprecated":
            continue
        value = ((claim.get("mainsnak") or {}).get("datavalue") or {}).get("value")
        if isinstance(value, dict) and value.get("time"):
            # Precision below 9 renders as a misleading year ("+2000/7" is the
            # 20th century), so report the year only when it means one.
            if int(value.get("precision", 0)) < 9:
                continue
            return value["time"][1:5]
    return None


def describe(session: Session, qids: Sequence[str]) -> List[Entry]:
    """Build an `Entry` for each QID: the item, its kinds, and its shape."""
    qids = sorted(set(qids))
    if not qids:
        return []
    entities = fetch_entities(session, qids, max_age=0)
    # Resolve the label of every item referenced as a kind or a body in one go.
    referenced: Set[str] = set()
    for entity in entities.values():
        referenced.update(claim_qids(entity, "P279"))
        referenced.update(claim_qids(entity, "P361"))
    labels = {
        qid: best_label(ent)
        for qid, ent in fetch_entities(
            session, sorted(referenced), props="labels"
        ).items()
    } if referenced else {}

    closure = type_closure(session, qids)
    counts = _holder_counts(session, qids)
    entries = []
    for qid in qids:
        entity = entities.get(qid)
        if entity is None:
            continue
        verdict = verify(session, entity, closure)
        aliases = [
            alias["value"]
            for lang in ("en", "mul")
            for alias in (entity.get("aliases") or {}).get(lang, [])
        ]
        entries.append(
            Entry(
                qid=qid,
                label=best_label(entity),
                description=best_description(entity),
                aliases=aliases[:6],
                kinds=[labels[q] for q in claim_qids(entity, "P279") if labels.get(q)],
                body=next(
                    (labels[q] for q in claim_qids(entity, "P361") if labels.get(q)),
                    None,
                ),
                inception=_time(entity, "P571"),
                abolished=_time(entity, "P576"),
                holders=counts.get(qid, 0),
                topics=sorted(verdict.topics),
                defects=list(verdict.defects),
                replaces=claim_qids(entity, "P1365"),
                replaced_by=claim_qids(entity, "P1366"),
            )
        )
    return entries


def for_target(
    session: Session, target: str, *, siblings: Sequence[str] = ()
) -> Gazetteer:
    """The target plus the items that are the same office under another name.

    One office is often several items — a ministry renamed each cabinet, a body
    that replaced a predecessor — and a person's tenure belongs on whichever one
    covered the term. `siblings` takes anything a caller already knows to be in
    the family (`wd/backtest.py:observed_family` derives it from the cohort's
    own recorded statements, which is how a country nobody has hand-analysed
    still gets the protection).
    """
    wanted = {target, *siblings}
    # One hop of succession in both directions. Not transitive: a chain of
    # renamings walked to its end reaches offices a century away.
    for entry in describe(session, sorted(wanted)):
        wanted.update(entry.replaces)
        wanted.update(entry.replaced_by)
    return Gazetteer(
        scope=f"target {target}", entries=describe(session, sorted(wanted))
    )


def for_country(session: Session, country_qid: str) -> Gazetteer:
    """Every position item scoped to one state — the `bucket` spec's gazetteer."""
    rows = sparql(session, COUNTRY_OFFICES % {"country": country_qid}, max_age=0)
    qids = sorted({row["pos"] for row in rows})
    return Gazetteer(
        scope=f"country {country_qid}", entries=describe(session, qids)
    )


def for_qualifier(
    session: Session, prop: str, country_qid: str
) -> Gazetteer:
    """The items a P39 qualifier may name, for one country.

    Empty is a normal answer and means the qualifier is unavailable for this
    country, not that the run failed. Check `entries` before offering it.
    """
    cls = QUALIFIER_CLASSES.get(prop)
    if not cls or not country_qid:
        return Gazetteer(scope=f"{prop} in {country_qid}", entries=[])
    rows = sparql(
        session, QUALIFIER_QUERY % {"cls": cls, "country": country_qid}, max_age=0
    )
    return Gazetteer(
        scope=f"{prop} in {country_qid}",
        entries=describe(session, sorted({r["x"] for r in rows})),
    )


def render_qualifiers(sets: Dict[str, Gazetteer]) -> str:
    """The qualifier sets as one cacheable block. Skips the empty ones."""
    blocks = ["# Qualifier values you may name", ""]
    labels = {"P768": "electoral districts (P768) — the constituency a seat was "
                      "won in",
              "P4100": "parliamentary groups (P4100) — the caucus, not the party"}
    any_set = False
    for prop, gazetteer in sorted(sets.items()):
        if not gazetteer.entries:
            continue
        any_set = True
        blocks += [f"## {labels.get(prop, prop)}", ""]
        # Aliases, not just the label. A Polish constituency is *labelled* by
        # number ("Sejm Constituency no. 11") and *named* by place in its
        # aliases ("Sieradz electoral district"), while the evidence says
        # "okręgu sieradzkim". Printing the label alone asks the model to know a
        # place-to-number mapping it has no way to have, and it correctly
        # declined: one district named across 130 proposals.
        for e in sorted(gazetteer.entries, key=lambda e: e.qid):
            parts = [f"{e.qid} | {e.label or '(no label)'}"]
            if e.aliases:
                parts.append("also: " + "; ".join(e.aliases))
            if e.description:
                parts.append(e.description)
            blocks.append(" | ".join(parts))
        blocks.append("")
    if not any_set:
        return ""
    blocks += [
        "Name one of these in `district` or `group` when the evidence states it,",
        "using the label as written above. Leave the field null otherwise — an",
        "unnamed qualifier costs nothing, and a guessed one is a wrong statement",
        "on a public database. If a qualifier list is absent above, that value",
        "cannot be asserted for this country at all.",
        "",
    ]
    return "\n".join(blocks)
