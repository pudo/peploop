"""Find the Wikidata item behind an office named in an article.

Round one returns an office as the article writes it — a title, sometimes a
jurisdiction, dates, quotes. Round two has to turn that into a QID or say it
cannot, and this module is the half that does not involve a model: it loads a
country's position items into Postgres and searches them, so the shortlist a
model eventually picks from is short, legible and ordered.

Retrieval ranks and a model decides. Nothing here resolves anything, and
nothing is excluded from the table: an abolished office is the right answer
for a tenure that ended in 1960, and an item typed as an occupation is worth
offering *labelled* as one so the pick can be refused for the right reason.
"""

import math
import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from normality import ascii_text
from psycopg.types.json import Jsonb
from rigour.territories import get_territory

from peploop import db, wikidata

#: What discovery found an item. An item the class descent reached and nobody
#: holds is a different kind of candidate from one only its holders reveal,
#: and both facts survive into the ranking.
SOURCES = ("descent", "usage", "citizen")

#: `P31`/`P279` into the position tree, scoped to one state. `p:P31/ps:P31`
#: and not `wdt:P31`: one preferred value hides the normal-rank ones, and a
#: live office then reads as not a position at all.
DESCENT_QUERY = """SELECT DISTINCT ?pos WHERE {
  ?pos p:P31/ps:P31/wdt:P279* wd:Q4164871 .
  { ?pos wdt:P17 wd:%(country)s } UNION { ?pos wdt:P1001 wd:%(country)s }
}"""

#: Discovery by evidence of use: an office scoped to the state that someone is
#: recorded in, or that names its own holder. This is what catches the offices
#: the ontology mistyped — a country-generic class whose only `P31` is "type of
#: position" is invisible to the descent and can still have a thousand holders.
USAGE_QUERY = """SELECT DISTINCT ?pos WHERE {
  { ?pos wdt:P17 wd:%(country)s } UNION { ?pos wdt:P1001 wd:%(country)s }
  { ?h wdt:P31 wd:Q5 ; p:P39/ps:P39 ?pos } UNION { ?pos wdt:P1308 ?h }
}"""

#: Discovery by who holds it: offices held by citizens of the country whose
#: occupation is political. The only route to an office the country's own
#: people hold that is scoped to no polity of theirs — a posting abroad, a
#: seat in an international body, an item with no jurisdiction claim at all.
CITIZEN_QUERY = """SELECT DISTINCT ?pos WHERE {
  VALUES ?occupation { wd:Q82955 wd:Q193391 wd:Q16533 }
  ?h wdt:P27 wd:%(country)s ; wdt:P106 ?occupation ; p:P39/ps:P39 ?pos .
}"""

QUERIES = {
    "descent": DESCENT_QUERY,
    "usage": USAGE_QUERY,
    "citizen": CITIZEN_QUERY,
}


def country_qid(cc: str) -> str:
    """Resolve an ISO country code to the QID its offices are scoped by."""
    territory = get_territory(cc)
    if territory is None or territory.qid is None:
        raise ValueError(f"no territory QID for {cc!r}")
    return territory.qid


def discover(
    qid: str,
    sources: Iterable[str] = SOURCES,
    log: Any = lambda _m: None,
) -> dict[str, set[str]]:
    """Run each discovery query for one country, keyed by the source name.

    Each query is timed into the log, because the query service is erratic
    enough that a load which took an hour is only diagnosable if it says
    which of its steps the hour went into.
    """
    found: dict[str, set[str]] = {}
    for source in sources:
        started = time.monotonic()
        rows = wikidata.sparql(QUERIES[source] % {"country": qid})
        found[source] = {row["pos"] for row in rows}
        log(f"{source}: {len(found[source])} items in "
            f"{time.monotonic() - started:.0f}s")
    return found


#: Metaclasses that say "this is an office" and nothing about which kind.
#: `Q4164871` is not the modal one: of the items that are the target of some
#: `P39`, 17,788 are typed `Q294414` public office, and among ministers that
#: is 85% of them. A check demanding a literal `P31 = Q4164871` misses them.
POSITION_METACLASSES = {
    "Q4164871",  # position
    "Q294414",  # public office
    "Q17279032",  # elective office
    "Q114962596",  # historical position
    "Q83856136",  # legal position
    "Q136649946",  # type of position
    "Q355567",  # noble title
    "Q42045197",  # position of authority
}

#: Wikidata's own answer to what a position is not, read off `Q4164871`'s
#: `P1889 different from`, plus the rank, honour and body classes measurement
#: turned up. Tested against *declared* types only: within six hops
#: `Q28640` profession reaches `Q4164871`, so a closure test reads a naval
#: rank and a wood-carving trade as offices.
NOT_AN_OFFICE = {
    "Q480319",  # title of authority
    "Q12737077",  # occupation
    "Q28640",  # profession
    "Q11348",  # function
    "Q192581",  # job activity
    "Q4189293",  # rank
    "Q56019",  # military rank
    "Q4226220",  # naval officer rank
    "Q43229",  # organization
    "Q495430",  # general staff — a body, not a seat in one
    "Q6813432",  # military staff — also a body
    "Q3320743",  # title of honor
    "Q13424289",  # honorary title
    "Q618779",  # award
    "Q4192699",  # badge of distinction
    "Q486983",  # academic rank
    "Q4121104",  # sports title
}

#: Both properties at every level, matching the crawler that reads these
#: items downstream. Reading only `P31` misses the chain a position hangs off
#: its `P279`, which is where the kind of office usually lives.
TYPE_PROPS = ("P31", "P279")

#: An ended type claim is dropped, except this one: an office scoped to a
#: state that no longer exists is still an office of that state.
ALWAYS_KEPT = "Q3024240"  # historical country

#: Six hops, matching `nomenklatura.wikidata.model.Item.types`. A deeper walk
#: resolves types here that the consumer of these items will never see.
CLOSURE_DEPTH = 6

#: Wikidata time precision: 9 is a year, 10 a month, 11 a day. Anything
#: coarser renders as a misleading year — "+2000-00-00" at precision 7 is the
#: 20th century — so it is not a date and is not stored as one.
DATE_PRECISION = {11: 10, 10: 7, 9: 4}


def type_targets(entity: dict[str, Any]) -> list[str]:
    """The item's own `P31` and `P279` targets, ended claims dropped."""
    out: list[str] = []
    for prop in TYPE_PROPS:
        for claim in entity.get("claims", {}).get(prop, []):
            value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
            if not isinstance(value, dict) or "id" not in value:
                continue
            qid = value["id"]
            if claim.get("qualifiers", {}).get("P582") and qid != ALWAYS_KEPT:
                continue
            out.append(qid)
    return out


def _edges_cached(qids: Iterable[str]) -> dict[str, list[str]]:
    """Read known `P31`/`P279` edges out of the cache table."""
    wanted = list(dict.fromkeys(qids))
    if not wanted:
        return {}
    rows = db.conn().execute(
        "SELECT qid, targets FROM type_edge WHERE qid = ANY(%s)", (wanted,)
    ).fetchall()
    return {qid: list(targets) for qid, targets in rows}


def _edges_store(edges: dict[str, list[str]]) -> None:
    """Remember the edges of classes above the seeds; seeds are never stored."""
    if not edges:
        return
    with db.conn().cursor() as cur:
        cur.executemany(
            "INSERT INTO type_edge (qid, targets, fetched_at) VALUES (%s, %s, now())"
            " ON CONFLICT (qid) DO UPDATE SET targets = EXCLUDED.targets,"
            " fetched_at = now()",
            [(qid, targets) for qid, targets in edges.items()],
        )


def type_closure(qids: Sequence[str]) -> dict[str, set[str]]:
    """Every type each item has, closing over `P31` and `P279` together.

    Reach for this instead of a SPARQL property path whenever the question is
    "does this reach X anywhere among its values": one preferred `P31` hides
    the normal-rank ones from `wdt:` and a deprecated one vanishes entirely,
    so a closure built on truthy values reports real offices as untyped.

    The seeds are always re-read live, because they are the items being
    judged; their ancestry is stable and comes out of `type_edge`. An item's
    own QID counts as one of its types, so asking whether a class is in some
    set answers for the class itself too.
    """
    seeds = list(dict.fromkeys(qids))
    fresh = wikidata.fetch_items(seeds, props="claims")
    seed_edges = {qid: type_targets(fresh.get(qid, {})) for qid in seeds}

    edges: dict[str, list[str]] = {}
    frontier = {t for targets in seed_edges.values() for t in targets}
    for _ in range(CLOSURE_DEPTH):
        frontier -= set(edges)
        if not frontier:
            break
        known = _edges_cached(frontier)
        missing = sorted(frontier - set(known))
        found = wikidata.fetch_items(missing, props="claims") if missing else {}
        fetched = {qid: type_targets(found.get(qid, {})) for qid in missing}
        _edges_store(fetched)
        edges.update(known)
        edges.update(fetched)
        frontier = {t for qid in frontier for t in edges.get(qid, [])}
    for qid in frontier:  # depth-capped: keep them as leaves, do not lose them
        edges.setdefault(qid, [])

    edges.update(seed_edges)
    out: dict[str, set[str]] = {}
    for qid in seeds:
        seen = {qid}
        level = [qid]
        for _ in range(CLOSURE_DEPTH):
            level = [t for x in level for t in edges.get(x, []) if t not in seen]
            seen.update(level)
            if not level:
                break
        out[qid] = seen
    return out


def _claim_date(entity: dict[str, Any], *props: str) -> str | None:
    """The first time value of these properties, at day precision or coarser.

    Returns an ISO string truncated to what the precision actually asserts, so
    a year-precision claim never reads as the first of January.
    """
    for prop in props:
        for time, precision in wikidata.claim_time(entity, prop, include_deprecated=False):
            length = DATE_PRECISION.get(precision)
            if length is None:
                continue
            text = time.lstrip("+")[:length]
            return text + "-01" * (3 - len(text.split("-")))
    return None


def _unended_qid(entity: dict[str, Any], prop: str) -> str | None:
    """The first value of a property whose claim has not been ended.

    A country or a jurisdiction the item has moved on from is history, not the
    polity it is scoped to now — but an item with *only* ended claims keeps
    the last one, because an abolished office still belongs somewhere.
    """
    ended: str | None = None
    for claim in entity.get("claims", {}).get(prop, []):
        if claim.get("rank") == "deprecated":
            continue
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        if not isinstance(value, dict) or "id" not in value:
            continue
        if claim.get("qualifiers", {}).get("P582"):
            ended = ended or value["id"]
            continue
        return value["id"]
    return ended


def names_of(entity: dict[str, Any]) -> list[tuple[str, str, bool]]:
    """Every label and alias of an item as (lang, text, is_alias).

    All languages, always: an office can carry no English label at all, and
    the name the article used is the one the search has to match.
    """
    out: list[tuple[str, str, bool]] = []
    for lang, obj in entity.get("labels", {}).items():
        out.append((lang, obj["value"], False))
    for lang, objs in entity.get("aliases", {}).items():
        for obj in objs:
            out.append((lang, obj["value"], True))
    return out


#: The properties whose targets' names join a position's search document.
#: Each one earned its place in the ablation and nothing else did: the
#: polity the office governs and the state it belongs to, the body it is a
#: seat in, the kind of office it is, and the offices it succeeds or is
#: succeeded by.
#:
#: `P1889 different from` is deliberately absent and must stay absent. It is
#: an anti-relation: it names exactly the items this one is confusable with,
#: so indexing it teaches the search to answer with the wrong office.
#: Items whose every name in every language joins a position's document. The
#: office's own labels are rarely the only way an article names it: the
#: jurisdiction, the body it sits in, the state, and the office it replaced
#: are all words a reader would use. `P1889 different from` is permanently
#: excluded and must never be added -- it names exactly the items this one is
#: confusable with, which is the opposite of what an index wants.
#:
#: `P279` is deliberately absent. A kind contributes its one best label
#: through `kinds`, not its aliases: see `load_country`.
REFERENCED_PROPS = ("P1001", "P17", "P361", "P2389", "P1365", "P1366")


def _referenced_items(qids: Iterable[str]) -> dict[str, dict[str, Any]]:
    """Fetch, in one batch, every item the country's positions point at.

    One request per 50 QIDs for the whole country rather than per position:
    the jurisdictions, bodies and kinds of one country's offices repeat
    heavily, and a per-row fetch turns a minute's load into an hour's.
    """
    wanted = sorted({q for q in qids if q})
    if not wanted:
        return {}
    return wikidata.fetch_items(wanted, props="labels|aliases")


#: Function words across the languages offices are labelled in. Dropped
#: before scoring, so a title and a label are compared on their content and
#: not on how each language spells "of".
STOPWORDS = frozenset("""
a an and at by for from in of on or the to with
i w we na do dla oraz z za o po
de del la el las los y en al a
v ve na pro pri se pod pre
s so dlya iz
der die das des dem und von zu im
du le les et aux
""".split())

#: How much of a token the index keeps as its prefix. Names arrive in every
#: language the item has one in, Postgres ships a text search configuration
#: for few of them and one honest choice for all of them (`simple`, which
#: stems nothing) — so each token is stored twice, whole and clipped, and the
#: clipped copy is what lets an inflected form in a title reach the nominative
#: form on the item. Worth about three points of recall.
PREFIX = 6

#: What a lexeme may contain. `tokens` splits on exactly this, so the filter
#: in `search` is a guard and not a rule: anything else in a `to_tsquery`
#: string is a syntax error rather than a miss, and the query text comes from
#: an article by way of a model.
LEXEME = re.compile(r"[a-z0-9]+")


def fold(text: str) -> str:
    """Casefolded ASCII, so a diacritic cannot break a comparison.

    Transliterates rather than strips: the plain non-ASCII drop this replaced
    turned two spellings of the same city into two different words.
    """
    return (ascii_text(text) or "").casefold()


def tokens(text: str) -> set[str]:
    """An office name as its content tokens, folded and stopword-free.

    Falls back to the unstripped tokens when stripping would empty the set,
    so an office genuinely called "The Speaker" stays comparable.
    """
    parts = [t for t in re.split(r"[^a-z0-9]+", fold(text)) if t]
    content = {t for t in parts if t not in STOPWORDS}
    return content or set(parts)


def token_bag(texts: Iterable[str]) -> list[str]:
    """Some names as the lexemes the search is conducted in, whole and clipped.

    The one transformation both sides go through, which is why it is a
    function and not two loops: an item's document is this over every name it
    and the items it points at carry, a query is this over the title and the
    jurisdiction the article gave, and any divergence makes the query ask for
    lexemes the index never stored.

    De-duplicated and sorted, which is what makes a document a *bag*. Every
    lexeme occurs exactly once, so ranking counts how much of the query the
    document covers rather than how many of an item's thirty languages happen
    to spell a word the same way.
    """
    bag: set[str] = set()
    for text in texts:
        for token in tokens(text):
            bag.add(token)
            bag.add(token[:PREFIX])
    return sorted(bag)


def upsert_position(row: dict[str, Any], names: Sequence[tuple[str, str, bool]]) -> None:
    """Write one position and its names, replacing what a previous load wrote."""
    columns = [
        "qid", "label", "description", "country_qid", "jurisdiction_qid",
        "jurisdiction_text", "body_qid", "kinds", "sources", "not_office",
        "inception", "abolished", "replaces", "replaced_by", "redirected_from",
        "search_text",
    ]
    assignments = ", ".join(f"{c} = EXCLUDED.{c}" for c in columns[1:])
    db.conn().execute(
        f"INSERT INTO position ({', '.join(columns)}, loaded_at)"
        f" VALUES ({', '.join(['%s'] * len(columns))}, now())"
        f" ON CONFLICT (qid) DO UPDATE SET {assignments}, loaded_at = now()",
        [row.get(c) for c in columns],
    )
    # Names are replaced rather than merged: a label the community removed
    # should stop matching, and an item has few enough of them that diffing
    # would cost more than rewriting.
    db.conn().execute("DELETE FROM position_name WHERE qid = %s", (row["qid"],))
    if names:
        with db.conn().cursor() as cur:
            cur.executemany(
                "INSERT INTO position_name (qid, lang, text, alias)"
                " VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
                [(row["qid"], lang, text, alias) for lang, text, alias in names],
            )


def load_country(
    cc: str,
    sources: Iterable[str] = SOURCES,
    log: Any = lambda _m: None,
) -> dict[str, int]:
    """Load every position item one country scopes or its citizens hold.

    Incremental and additive: a second country leaves the first one's rows
    alone, a re-run updates in place, and an item this run did not find keeps
    its row. Nothing is deleted, because absence from one query is not
    evidence that an office is gone.
    """
    qid = country_qid(cc)
    found = discover(qid, sources, log=log)
    union = sorted({q for qids in found.values() for q in qids})
    log(f"union: {len(union)} items")

    started = time.monotonic()
    entities = wikidata.fetch_items(union)
    log(f"entities: {len(entities)} fetched in {time.monotonic() - started:.0f}s")
    missing = [q for q in union if q not in entities]
    if missing:
        log(f"missing or deleted: {len(missing)}")

    started = time.monotonic()
    closure = type_closure(sorted(entities))
    log(f"type closure: {len(closure)} items in {time.monotonic() - started:.0f}s")
    rows: list[tuple[dict[str, Any], list[tuple[str, str, bool]]]] = []
    referenced: set[str] = set()
    canonical: dict[str, dict[str, Any]] = {}
    redirects: dict[str, set[str]] = {}

    for requested, entity in entities.items():
        # A merged item comes back under the id it was merged into. Keying on
        # that, and remembering the id we asked for, is what stops one office
        # entering the table twice.
        actual = entity.get("id", requested)
        canonical[actual] = entity
        if actual != requested:
            redirects.setdefault(actual, set()).add(requested)

    for actual, entity in canonical.items():
        declared = set(type_targets(entity))
        kind_qids = wikidata.claim_qids(entity, "P279", include_deprecated=False)
        jurisdiction = _unended_qid(entity, "P1001")
        # Every item whose names join this one's document. Read off all ranks
        # and both directions of the succession, one hop and no further: a
        # renamed office is reached by the name it used to have, while a
        # transitive walk would eventually name the whole ministry lineage.
        refs = [q for prop in REFERENCED_PROPS
                for q in wikidata.claim_qids(entity, prop, include_deprecated=False)]
        referenced.update(refs)
        referenced.update(kind_qids)
        sources_here = sorted(
            source for source, qids in found.items()
            if actual in qids or qids & redirects.get(actual, set())
        )
        rows.append((
            {
                "qid": actual,
                "label": wikidata.best_label(entity),
                "description": (entity.get("descriptions", {}).get("en")
                                or entity.get("descriptions", {}).get("mul")
                                or {}).get("value"),
                "country_qid": _unended_qid(entity, "P17"),
                "jurisdiction_qid": jurisdiction,
                "body_qid": (_unended_qid(entity, "P361")
                             or _unended_qid(entity, "P2389")),
                "sources": sources_here,
                # Positive evidence that the item is something else, never the
                # absence of evidence that it is an office: an item declaring
                # both a rank and a position metaclass is left alone.
                "not_office": bool(declared & NOT_AN_OFFICE)
                and not (declared & POSITION_METACLASSES),
                "inception": _claim_date(entity, "P571"),
                "abolished": _claim_date(entity, "P576", "P582"),
                "replaces": wikidata.claim_qids(entity, "P1365", include_deprecated=False),
                "replaced_by": wikidata.claim_qids(entity, "P1366", include_deprecated=False),
                "redirected_from": sorted(redirects.get(actual, ())),
                "_kind_qids": kind_qids,
                "_refs": refs,
                "_closure": closure.get(actual, set()),
            },
            names_of(entity),
        ))

    started = time.monotonic()
    items = _referenced_items(referenced)
    names_by_qid = {qid: sorted({text for _lang, text, _alias in names_of(entity)})
                    for qid, entity in items.items()}
    labels = {qid: label for qid, entity in items.items()
              if (label := wikidata.best_label(entity)) is not None}
    log(f"referenced items: {len(items)} of {len(referenced)}"
        f" in {time.monotonic() - started:.0f}s")
    started = time.monotonic()
    for row, names in rows:
        row["kinds"] = [labels[q] for q in row.pop("_kind_qids") if q in labels]
        juris = names_by_qid.get(row["jurisdiction_qid"] or "", [])
        row["jurisdiction_text"] = " | ".join(juris) or None
        texts = [text for _lang, text, _alias in names]
        for qid in row.pop("_refs"):
            texts.extend(names_by_qid.get(qid, ()))
        # A kind contributes its one best label and none of its aliases. A
        # generic parent carries dozens per language, and pasting all of them
        # onto every child is the parent trap by another route: the class ends
        # up matching more queries than the office it is the class of. Measured
        # at 3.9 points of macro recall and a fifth of the index size.
        texts.extend(row["kinds"])
        row["search_text"] = " ".join(token_bag(texts))
        row.pop("_closure", None)
        upsert_position(row, names)
    log(f"upsert: {len(rows)} rows in {time.monotonic() - started:.0f}s")

    counts = {source: len(qids) for source, qids in found.items()}
    counts["loaded"] = len(rows)
    counts["names"] = sum(len(names) for _row, names in rows)
    return counts


# --- Ranking signals -------------------------------------------------------
#
# Everything below fills a nullable column. None of it filters: a count is a
# reason to order one candidate above another and to say why in a tag, and a
# column left `NULL` means nobody has counted yet -- never that the answer is
# zero. That distinction is why the counts that can be zero ask with an
# `OPTIONAL`: an item nobody holds has to come back as a row saying 0, or an
# absent row would be indistinguishable from an uncounted one. The one query
# that cannot (a held child either exists or the pattern does not match)
# defaults to zero for the items its own chunk asked about, and for no others.

#: Holders per item. `wdt:P39`, best rank only, because this is a *ranking*
#: signal: measured against `p:P39/ps:P39` over one country the two differ by
#: 29 pairs in 8,938 and cost 32 s against 97 s. A coverage claim would need
#: the expensive shape; an ordering does not.
HOLDERS_QUERY = """SELECT ?pos (COUNT(DISTINCT ?h) AS ?n) WHERE {
  VALUES ?pos { %(values)s } OPTIONAL { ?h wdt:P39 ?pos }
} GROUP BY ?pos"""

#: Holders who are citizens of one state, which is the signal that separates
#: an office a country genuinely records its people on from a world-level
#: class a handful of them were filed under by mistake. Counted per state
#: rather than per row, because the same item is a convention in one country
#: and an accident in the next.
HOLDERS_COUNTRY_QUERY = """SELECT ?pos (COUNT(DISTINCT ?h) AS ?n) WHERE {
  VALUES ?pos { %(values)s }
  OPTIONAL { ?h wdt:P39 ?pos ; wdt:P27 wd:%(country)s }
} GROUP BY ?pos"""

#: Items whose `P31` is this one: the item is a metaclass, a kind of office
#: rather than an office.
INSTANCE_QUERY = """SELECT ?pos (COUNT(DISTINCT ?x) AS ?n) WHERE {
  VALUES ?pos { %(values)s } OPTIONAL { ?x wdt:P31 ?pos }
} GROUP BY ?pos"""

#: Items whose `P279` is this one. A real office has zero children or a
#: handful of renamings; a class has hundreds.
SUBCLASS_QUERY = """SELECT ?pos (COUNT(DISTINCT ?x) AS ?n) WHERE {
  VALUES ?pos { %(values)s } OPTIONAL { ?x wdt:P279 ?pos }
} GROUP BY ?pos"""

#: The children somebody actually holds -- the class-versus-seat detector.
#: Children alone say little, because a renaming succession is modelled the
#: same way; children *that people are recorded in* say the community treats
#: this item as the class and the seat as something else.
HELD_SUBCLASS_QUERY = """SELECT ?pos (COUNT(DISTINCT ?child) AS ?n) WHERE {
  VALUES ?pos { %(values)s }
  ?child wdt:P279 ?pos . ?h wdt:P39 ?child .
} GROUP BY ?pos"""

#: `P39` qualifiers that describe the *tenure* rather than say which office
#: it was. Everything else a statement carries is a candidate for the
#: property that makes a generic office concrete.
#:
#: The list is not the dates alone, and measuring said so: over this corpus
#: the modal qualifier of fifty positions is `P1365 replaces`, which is a
#: fact about who the holder took over from. A column called
#: `scope_qualifier` that answers `P1365` would be read downstream as the
#: qualifier to emit, and emitting it would say something untrue.
NON_SCOPING_QUALIFIERS = frozenset((
    "P580",   # start time
    "P582",   # end time
    "P585",   # point in time
    "P1319",  # earliest date
    "P1326",  # latest date
    "P805",   # statement is subject of
    "P1365",  # replaces — whom the holder took over from
    "P1366",  # replaced by — and whom they handed over to
    "P1534",  # end cause
    "P2097",  # term length
    "P748",   # appointed by
    "P4100",  # parliamentary group — a fact about the holder, not the seat
))

#: Ambassadorship, reached through `type_closure` and never through a
#: `wdt:P279*` in a `FILTER NOT EXISTS`, which times the query service out.
#: An inbound mission is scoped to the *receiving* state, so a country's own
#: table is full of other countries' embassies to it.
DIPLOMATIC_CLASS = "Q121998"


def grouped_count(query: str, qids: Sequence[str], **params: str) -> dict[str, int]:
    """Run one grouped count over a list of items, 120 QIDs per request.

    The chunking is not an optimisation: about 150 `VALUES` entries overflow
    the query service's GET URI and come back as HTTP 414.
    """
    counts: dict[str, int] = {}
    for chunk in wikidata.values_chunks(qids):
        rows = wikidata.sparql(
            query % {"values": wikidata.values_block(chunk), **params}, max_age=0
        )
        for row in rows:
            counts[row["pos"]] = counts.get(row["pos"], 0) + int(row["n"])
    return counts


def fill_counts(
    state_qid: str,
    qids: Sequence[str] | None = None,
    log: Any = lambda _m: None,
) -> dict[str, float]:
    """Count holders, instances and subclasses for a country's positions.

    One grouped query per signal over the same chunks, intersected with the
    position set rather than scoped by `P17`: a state's `P17` is carried by
    items that are not offices at all, and a subclass count taken that way
    counts the children of a language.
    """
    if qids is None:
        # Every row, not the ones this state scopes. The search offers the
        # whole table and an office of a neighbouring state is a candidate
        # like any other, so a count restricted to the state's own offices
        # would leave exactly the rows that need discouraging uncounted.
        rows = db.conn().execute("SELECT qid FROM position ORDER BY qid").fetchall()
        qids = [qid for (qid,) in rows]
    timings: dict[str, float] = {}
    results: dict[str, dict[str, int]] = {}
    plan = (
        ("holders", HOLDERS_QUERY, {}),
        ("holders_country", HOLDERS_COUNTRY_QUERY, {"country": state_qid}),
        ("instance_count", INSTANCE_QUERY, {}),
        ("subclass_count", SUBCLASS_QUERY, {}),
        ("held_subclasses", HELD_SUBCLASS_QUERY, {}),
    )
    for name, query, params in plan:
        started = time.monotonic()
        results[name] = grouped_count(query, qids, **params)
        timings[name] = time.monotonic() - started
        log(f"{name}: {len(results[name])} rows in {timings[name]:.0f}s")

    with db.conn().cursor() as cur:
        cur.executemany(
            "UPDATE position SET holders = %s, holders_at = now(),"
            " holders_by_country = coalesce(holders_by_country, '{}'::jsonb) || %s,"
            " instance_count = %s, subclass_count = %s, held_subclasses = %s"
            " WHERE qid = %s",
            [
                (
                    results["holders"].get(qid),
                    Jsonb({state_qid: results["holders_country"].get(qid, 0)}),
                    results["instance_count"].get(qid),
                    results["subclass_count"].get(qid),
                    # Absent from a query with no OPTIONAL means no held child,
                    # but only for an item the chunk actually asked about.
                    results["held_subclasses"].get(qid, 0),
                    qid,
                )
                for qid in qids
            ],
        )
    return timings


#: Chunk size for the backfill below. Half of `VALUES_CHUNK`, and not for the
#: URI limit: a whole-table pass over the country-holder query is the one
#: request stage D could not get an answer to, and the query service refused
#: it with 504s rather than a 414. A smaller chunk is the repo's standing
#: answer to a query that times out — bisect it — and it costs only requests.
BACKFILL_CHUNK = 60


def fill_local_holders(
    state_qid: str,
    only_missing: bool = True,
    log: Any = lambda _m: None,
) -> int:
    """Count one state's citizens among the holders of every position.

    Reach for this after loading a second country. `fill_counts` writes
    `holders_by_country` only under the state it ran with, so every row a
    later country's load created carries that country's key and none for the
    countries already in the table — and those rows are exactly the ones a
    search of an earlier country must not credit with a borrowed count. This
    fills the hole without re-running the four whole-corpus queries beside
    it, which are state-independent and already answered.
    """
    sql = "SELECT qid FROM position"
    params: list[Any] = []
    if only_missing:
        # `jsonb_exists` rather than the `?` operator: psycopg reads a bare
        # `?` in a query as nothing in particular and Postgres then wants
        # `??`, which is a different error again. The function is the same
        # operator without the quoting argument.
        sql += (" WHERE holders_by_country IS NULL"
                " OR NOT jsonb_exists(holders_by_country, %s)")
        params = [state_qid]
    sql += " ORDER BY qid"
    qids = [qid for (qid,) in db.conn().execute(sql, params).fetchall()]
    if not qids:
        log(f"{state_qid}: nothing to backfill")
        return 0
    counts: dict[str, int] = {}
    chunks = list(wikidata.values_chunks(qids, size=BACKFILL_CHUNK))
    for index, chunk in enumerate(chunks, 1):
        started = time.monotonic()
        rows = wikidata.sparql(
            HOLDERS_COUNTRY_QUERY
            % {"values": wikidata.values_block(chunk), "country": state_qid},
            max_age=0,
        )
        for row in rows:
            counts[row["pos"]] = counts.get(row["pos"], 0) + int(row["n"])
        log(f"{state_qid}: chunk {index}/{len(chunks)}, {len(chunk)} items in "
            f"{time.monotonic() - started:.0f}s")
    with db.conn().cursor() as cur:
        cur.executemany(
            "UPDATE position SET holders_by_country ="
            " coalesce(holders_by_country, '{}'::jsonb) || %s WHERE qid = %s",
            [(Jsonb({state_qid: counts.get(qid, 0)}), qid) for qid in qids],
        )
    log(f"{state_qid}: {len(qids)} rows given a local count")
    return len(qids)


def fill_scope_qualifiers(log: Any = lambda _m: None) -> dict[str, str]:
    """Record the qualifier property the corpus uses to make an office concrete.

    Read off the `item` table rather than the query service, because the
    question is what *this* community does with *this* office: a generic
    council seat is scoped by the municipality, a party post by the
    organisation, and the corpus already read is the only evidence of which.
    Modal rather than majority — a property that occurs once on one statement
    is still the only scoping property anybody used.
    """
    tally: dict[str, Counter] = defaultdict(Counter)
    rows = db.conn().execute("SELECT json FROM item")
    for (blob,) in rows:
        for claim in blob.get("claims", {}).get("P39", []):
            value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
            if not isinstance(value, dict) or "id" not in value:
                continue
            for prop in claim.get("qualifiers", {}):
                if prop not in NON_SCOPING_QUALIFIERS:
                    tally[value["id"]][prop] += 1
    modal = {qid: counts.most_common(1)[0][0] for qid, counts in tally.items()}
    # Cleared first, because this is a re-derivation and not an increment: a
    # value the previous pass wrote from a rule this one no longer applies
    # would otherwise survive as the answer to a question nobody asks any more.
    db.conn().execute("UPDATE position SET scope_qualifier = NULL")
    with db.conn().cursor() as cur:
        cur.executemany(
            "UPDATE position SET scope_qualifier = %s WHERE qid = %s",
            [(prop, qid) for qid, prop in modal.items()],
        )
    log(f"scope qualifier recorded for {len(modal)} items")
    return modal


def fill_diplomatic(qids: Sequence[str] | None = None,
                    log: Any = lambda _m: None) -> int:
    """Flag the ambassadorships, which a country's own table is full of.

    Through the cached type closure and never through a SPARQL property path:
    an unbounded `wdt:P279*` inside a `FILTER NOT EXISTS` times the query
    service out. Flagged, never dropped — an ambassador is a real office and
    the right answer for somebody.
    """
    if qids is None:
        rows = db.conn().execute("SELECT qid FROM position ORDER BY qid").fetchall()
        qids = [qid for (qid,) in rows]
    closure = type_closure(list(qids))
    flags = {qid: DIPLOMATIC_CLASS in closure.get(qid, set()) for qid in qids}
    with db.conn().cursor() as cur:
        cur.executemany(
            "UPDATE position SET diplomatic = %s WHERE qid = %s",
            [(value, qid) for qid, value in flags.items()],
        )
    count = sum(flags.values())
    log(f"diplomatic: {count} of {len(flags)}")
    return count


# --- Re-ranking ------------------------------------------------------------
#
# The candidate set is whatever the text index returned; re-ranking only
# changes the order inside it, which is what makes the comparison honest.
# Recall cannot move, so a signal is judged on MRR and top-1 and on nothing
# else, and every signal that moves a row also names itself in the row's tags
# so a reader can see why it moved.

#: The signals, in the order they were added and measured. `search` takes a
#: subset so the bench can score each one on its own and cumulatively.
SIGNALS = ("not_office", "holders", "class", "dates", "diplomatic")

#: Where the holder bonus saturates. Log-scaled and capped, because the
#: question a holder count answers is "does the community use this item at
#: all", and the difference between 900 and 1,800 holders is not twice the
#: evidence that 1 and 2 is.
HOLDER_SATURATION = 1000

#: How much each signal is worth, as a fraction of a perfect text match. The
#: base score is normalised to 1.0 for the best-matching candidate of each
#: query, so a weight of 0.3 says "worth three tenths of the whole query's
#: vocabulary". Penalties are larger than bonuses on purpose: a signal that
#: says an item is the wrong *kind* of thing is stronger evidence than a
#: holder count is that it is the right one.
WEIGHTS = {
    "holders": 0.30,        # scaled by log10(holders) / log10(saturation)
    "unheld": -0.15,
    "not_office": -0.50,
    "abstract": -0.35,
    # Zero, and measured rather than assumed. The design said an abolished
    # office should be *boosted* for a tenure that ended before it, and that
    # half of the date signal is what wrecks the ranking: an inception that
    # precedes a tenure is true of almost every old office, so the boost is
    # an "is old" bonus handed out to the wrong candidates as freely as to
    # the right one. It costs 8 points of MRR and 16 of top-1. The tag is
    # still emitted, because the model is owed the observation.
    "date_fit": 0.0,
    "date_conflict": -0.30,
    "inbound_diplomatic": -0.25,
}

#: A class-like item is one somebody else's item is an instance of, or one
#: with at least this many children that people are recorded in. Measured,
#: not declared: see the increment 4 section of `positions.md`.
HELD_SUBCLASS_FLOOR = 3

#: How many of a state's own citizens have to hold a class-like item before
#: it stops being an abstraction somebody misfiled under and becomes the
#: item that state's community uses on purpose. Also measured.
CONVENTION_FLOOR = 50

#: How the holder bonus reads a count when a state is being searched. The
#: default is the only one of these that is a claim about the state asking:
#: `holders` is a count over the whole of Wikidata, and scoring it as though
#: it said something about the state being searched is what put one foreign
#: legislature's seat — 4,694 holders, and in the table only because a
#: *second* country's citizen lane imported it — at rank 1 for 74 of the
#: first country's 746 gold queries. The other three scopes exist because
#: the ablation between them is the measurement, and are reproducible from
#: the bench's `--holder-scope`.
#:
#: `local`
#:     The state's own count, and **silence** when the map has no key for
#:     this state. Silence rather than the global count: an absent key means
#:     nobody has counted here, which is the same thing every other nullable
#:     signal column means by `NULL`, and it is the reading that keeps a
#:     foreign office reachable without letting it win on a borrowed number.
#: `global`
#:     What increment 4 shipped. Correct only while the table holds one
#:     country, because then the largest counts are that country's.
#: `local_or_global`
#:     The repair stage D attempted. It cannot be right: the rows with no
#:     local key are exactly the rows another country's load created, so the
#:     fallback fires on precisely the candidates that need discouraging.
#: `local_or_zero`
#:     Missing key read as "held by nobody here", which earns the `unheld`
#:     penalty. Asserts a count nobody took.
HOLDER_SCOPES = ("local", "global", "local_or_global", "local_or_zero")


def _year(value: Any) -> int | None:
    """The year of a date, however coarse the value that carries it.

    Two dates are compared at the precision they share and a tenure is
    routinely known only to the year, so the year is the only precision both
    sides of this comparison reliably have.
    """
    if value is None:
        return None
    text = str(value)[:4]
    return int(text) if text.isdigit() else None


def date_verdict(
    inception: Any, abolished: Any, start: Any, end: Any
) -> str | None:
    """Whether an office could have been held over a tenure's span.

    Never a filter and never symmetric: an office abolished in 1992 is the
    *right* answer for a tenure that ended in 1980 and is boosted for it, and
    wrong only for one that began afterwards. An office with no dates, or a
    tenure with none, yields no verdict at all rather than a penalty.
    """
    began, ended = _year(start), _year(end)
    opened, closed = _year(inception), _year(abolished)
    if closed is not None and began is not None and began > closed:
        return "date_conflict"
    if opened is not None and ended is not None and ended < opened:
        return "date_conflict"
    if closed is not None and ended is not None and ended <= closed:
        return "date_fit"
    if opened is not None and began is not None and began >= opened:
        return "date_fit"
    return None


def holder_count(
    row: dict[str, Any], state_qid: str | None, scope: str = "local"
) -> int | None:
    """How many holders the ranking may credit this candidate with.

    Reach for this instead of `row["holders"]` whenever the number is about
    to become a *bonus*: a holder count is evidence that the community whose
    office this is uses the item, and that community is the one being
    searched. `None` means nobody has counted for this state, and a caller
    owes it silence rather than a substitute.

    With no state to be local to — a global search — the whole-corpus count
    is the only reading there is, and every scope returns it.
    """
    holders = row.get("holders")
    if state_qid is None or scope == "global":
        return holders
    local = (row.get("holders_by_country") or {}).get(state_qid)
    if local is not None:
        return local
    if scope == "local_or_global":
        return holders
    if scope == "local_or_zero":
        return 0
    return None


def tags_for(
    row: dict[str, Any],
    state_qid: str | None = None,
    start: Any = None,
    end: Any = None,
    signals: Sequence[str] = SIGNALS,
    held_subclass_floor: int = HELD_SUBCLASS_FLOOR,
    convention_floor: int = CONVENTION_FLOOR,
    holder_scope: str = "local",
) -> list[str]:
    """What is worth saying about a candidate, derived and never hand-listed.

    Every tag is shown to the model beside the row, so this is as much the
    explanation of the ordering as its cause. A tag is emitted from a column
    that is actually filled: an uncounted holder count produces silence
    rather than `unheld`.
    """
    tags: list[str] = []
    if "not_office" in signals and row.get("not_office"):
        tags.append("not-office")

    # Counted where the search is, so `unheld` says "nobody the state asked
    # about holds this" and not "nobody anywhere does". A globally unheld
    # office is locally unheld too and still earns the tag; an office held
    # only abroad now earns it as well, which is the point of the signal.
    local = holder_count(row, state_qid, holder_scope)
    if "holders" in signals and local == 0:
        tags.append("unheld")

    if "class" in signals:
        held_children = row.get("held_subclasses")
        class_like = bool(row.get("instance_count")) or (
            held_children is not None and held_children >= held_subclass_floor
        )
        if class_like:
            # The same shape reads two ways, and only a count of the state's
            # own holders tells them apart: an abstraction a handful of
            # people were misfiled under, or the item the state's community
            # uses on purpose because it mints no item per place. Strictly
            # the map, under every holder scope: the floor above is a
            # measured number of *this state's* citizens, and reading a
            # global count against it would call every large class a local
            # convention.
            counted = (row.get("holders_by_country") or {}).get(state_qid)
            if counted is not None and counted >= convention_floor:
                tags.append("generic-by-convention")
            else:
                tags.append("abstract")

    if "dates" in signals:
        if row.get("abolished") is not None:
            tags.append("abolished")
        verdict = date_verdict(row.get("inception"), row.get("abolished"), start, end)
        if verdict is not None:
            tags.append(verdict.replace("_", "-"))

    if "diplomatic" in signals and row.get("diplomatic"):
        # A mission is scoped to the *receiving* state, so an ambassadorship
        # whose scope is the state being searched is somebody else's embassy
        # to it rather than one of its own postings. Measured here, that
        # scope is `P17` far more often than `P1001`: of 64 ambassadorships
        # only 9 carry a jurisdiction at all, and reading the country as the
        # fallback separates 34 inbound missions from 30 outbound ones.
        scope = row.get("jurisdiction_qid") or row.get("country_qid")
        inbound = state_qid is not None and scope == state_qid
        tags.append("inbound-diplomatic" if inbound else "diplomatic")

    # An office of some *other* state that only the citizen query reached.
    # A world-level class has no country at all and is not this: it is
    # already answered by `abstract`.
    country = row.get("country_qid")
    if (state_qid is not None and row.get("sources") == ["citizen"]
            and country is not None and country != state_qid):
        tags.append("foreign-scoped")
    return tags


def adjustment(
    row: dict[str, Any],
    tags: Sequence[str],
    signals: Sequence[str] = SIGNALS,
    state_qid: str | None = None,
    holder_scope: str = "local",
) -> float:
    """What the tags are worth, added to a base score normalised to 1.0."""
    delta = 0.0
    if "holders" in signals:
        holders = holder_count(row, state_qid, holder_scope)
        if holders:
            share = min(1.0, math.log10(1 + holders) / math.log10(1 + HOLDER_SATURATION))
            delta += WEIGHTS["holders"] * share
        elif holders == 0:
            delta += WEIGHTS["unheld"]
    for tag, key in (("not-office", "not_office"), ("abstract", "abstract"),
                     ("date-fit", "date_fit"), ("date-conflict", "date_conflict"),
                     ("inbound-diplomatic", "inbound_diplomatic")):
        if tag in tags:
            delta += WEIGHTS[key]
    return delta


@dataclass
class Hit:
    """One position a query reached, and the name worth showing beside it."""

    qid: str
    #: A name the item actually carries, in the language it carries it in.
    #: The document that was ranked is a pooled token bag and unreadable, so
    #: the row a model is later shown has to say what it matched instead.
    name: str
    lang: str
    #: The base text coverage plus what the signals made of it. The order of
    #: a shortlist is this and nothing else; the number itself is comparable
    #: within one shortlist and never between two queries.
    score: float
    #: How much of the query this item's document accounted for, as a
    #: fraction of what the best candidate of this query accounted for. Kept
    #: apart from `score` so a reader can see what the signals did.
    base: float = 1.0
    #: Why it moved, and what the model is told about it. Derived from the
    #: filled columns, never hand-listed.
    tags: tuple[str, ...] = ()


def _display_names(qids: Sequence[str], bag: set[str]) -> dict[str, tuple[str, str]]:
    """Pick one name per hit to show, in one query over the whole shortlist.

    Display, never ranking. A position's document pools the names of the item
    and of everything it points at, so nothing in the score says which of an
    item's thirty-odd names the article was writing; the shortest name that
    covers most of the query is the closest honest answer, and showing it is
    what lets a reader see that a hit matched on its jurisdiction alone.
    """
    if not qids:
        return {}
    rows = db.conn().execute(
        "SELECT qid, lang, text FROM position_name WHERE qid = ANY(%s)",
        (list(qids),),
    ).fetchall()
    scored = sorted(
        (qid, -len(bag & set(token_bag([text]))), len(text), text, lang)
        for qid, lang, text in rows
    )
    out: dict[str, tuple[str, str]] = {}
    for qid, _shared, _length, text, lang in scored:
        out.setdefault(qid, (text, lang))
    return out


#: How many candidates the text index hands to the ranking, before the
#: ranking cuts to `limit`. It is a separate number from the shortlist size
#: because the two answer different questions: `limit` is how many rows a
#: model can be asked to read, and this is how deep the ordering the model
#: never sees is allowed to reach.
#:
#: It has to exist at all because the text score is a *count of matched
#: lexemes*, so dozens of candidates tie exactly and `qid` breaks the tie
#: alphabetically. Cutting at fifteen in SQL therefore threw away answers on
#: an alphabet, and a second country loaded into the table pushed the first
#: country's answers over that cliff: 78 of the 80 answers displaced that
#: way had one of the newcomer's rows above them in text order.
#:
#: 200 is measured rather than declared, and it is the smallest pool at
#: which every slice of the bench is at its ceiling: recall stops moving at
#: 100, the last displaced answer comes back at 200, and 400, 800 and a pool
#: larger than any shortlist buy nothing at all on any slice. The curve is
#: in the 2026-09-20 retrieval-depth section of `positions.md`.
CANDIDATE_POOL = 200

#: The columns the re-ranking reads, fetched with the shortlist rather than
#: per row: one round trip per candidate would cost more than the whole
#: search does, and the pool is a few hundred rows of narrow columns.
SIGNAL_COLUMNS = (
    "not_office", "holders", "holders_by_country", "instance_count",
    "subclass_count", "held_subclasses", "inception", "abolished",
    "diplomatic", "scope_qualifier", "country_qid", "jurisdiction_qid",
    "sources",
)


def search(
    title: str,
    jurisdiction: str | None = None,
    country_qid: str | None = None,
    limit: int = 15,
    start: Any = None,
    end: Any = None,
    signals: Sequence[str] = SIGNALS,
    held_subclass_floor: int = HELD_SUBCLASS_FLOOR,
    convention_floor: int = CONVENTION_FLOOR,
    pool: int = CANDIDATE_POOL,
    holder_scope: str = "local",
) -> list[Hit]:
    """The positions an office title reaches, best first.

    Retrieval, not resolution: the shortlist is what a model is later shown,
    so a right answer buried at rank 40 is the same failure as no answer at
    all. Pass whatever turn one wrote down — the title and the jurisdiction
    go into one query, because the place the article named is evidence about
    the office, and reading it as a channel of its own scored exactly zero.
    The tenure's `start` and `end` come in the same way, because whether an
    abolished office is the right answer is a question about the tenure.

    The text index chooses the candidates and the signals only re-order
    them, which is why `country_qid` still does not filter. Filtering on it
    is the single most expensive thing this search can do — it hides two
    fifths of a country's own table, being every globally abstract office
    recorded with a scoping qualifier and every office of the predecessor
    state, and costs 23.7 points of macro recall. As the scope of the
    holder-count signal it is worth 0.04 of MRR instead.

    `holder_scope` decides whose holder count the bonus may read; the
    default counts the state being searched and says nothing at all about a
    candidate no query has counted there. `HOLDER_SCOPES` has the account.

    `pool` is how many candidates SQL hands over before the signals run.
    It is not a performance knob: the text score ties massively, so a cut
    taken in SQL is a cut taken alphabetically on `qid`, and anything it
    drops no re-ranking can recover. Retrieve deep, order in Python, cut
    last.
    """
    bag = [t for t in token_bag([title, jurisdiction or ""]) if LEXEME.fullmatch(t)]
    if not bag:
        return []
    columns = ", ".join(SIGNAL_COLUMNS)
    rows = db.conn().execute(
        f"SELECT qid, ts_rank(tsv, to_tsquery('simple', %(q)s), 0) AS score, {columns}"
        " FROM position WHERE tsv @@ to_tsquery('simple', %(q)s)"
        " ORDER BY score DESC, qid LIMIT %(k)s",
        {"q": " | ".join(bag), "k": max(pool, limit)},
    ).fetchall()
    if not rows:
        return []
    # Normalised against the best candidate of *this* query, so a weight is a
    # fraction of a whole query's vocabulary rather than a raw `ts_rank`
    # value, which means nothing outside the one shortlist it came from. The
    # pool's best is the table's best: SQL ordered by this same score.
    top = max(float(row[1]) for row in rows) or 1.0
    scored: list[tuple[float, float, str, tuple[str, ...]]] = []
    for row in rows:
        qid, score = row[0], float(row[1])
        record = dict(zip(SIGNAL_COLUMNS, row[2:]))
        tags = tags_for(record, country_qid, start, end, signals,
                        held_subclass_floor, convention_floor, holder_scope)
        base = score / top
        delta = adjustment(record, tags, signals, country_qid, holder_scope)
        scored.append((base + delta, base, qid, tuple(tags)))
    # Stable on the text order, so a query no signal speaks to comes back in
    # exactly the order the index produced. Cut here rather than in SQL, and
    # only then look up the names: display is per shown row, so its cost is
    # `limit`'s and not the pool's.
    scored.sort(key=lambda item: -item[0])
    del scored[limit:]
    names = _display_names([item[2] for item in scored], set(bag))
    return [
        Hit(
            qid=qid,
            name=names.get(qid, (qid, ""))[0],
            lang=names.get(qid, (qid, ""))[1],
            score=score,
            base=base,
            tags=tags,
        )
        for score, base, qid, tags in scored
    ]
