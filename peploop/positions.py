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

import re
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from normality import ascii_text
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


def discover(qid: str, sources: Iterable[str] = SOURCES) -> dict[str, set[str]]:
    """Run each discovery query for one country, keyed by the source name."""
    found: dict[str, set[str]] = {}
    for source in sources:
        rows = wikidata.sparql(QUERIES[source] % {"country": qid})
        found[source] = {row["pos"] for row in rows}
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


def _label_map(qids: Iterable[str]) -> dict[str, str]:
    """Best label per QID, for the `P279` kinds shown beside a candidate."""
    wanted = sorted({q for q in qids if q})
    if not wanted:
        return {}
    entities = wikidata.fetch_items(wanted, props="labels")
    out = {}
    for qid, entity in entities.items():
        label = wikidata.best_label(entity)
        if label is not None:
            out[qid] = label
    return out


def _jurisdiction_text(qids: Iterable[str]) -> dict[str, str]:
    """Every name of each jurisdiction item, joined for the trigram index.

    The cross-language bridge, and the reason it is a column of its own: an
    article naming an office in one language and an item labelled in another
    still agree on the place, because a place name travels between languages
    largely unchanged.
    """
    wanted = sorted({q for q in qids if q})
    if not wanted:
        return {}
    entities = wikidata.fetch_items(wanted, props="labels|aliases")
    out = {}
    for qid, entity in entities.items():
        names = {text for _lang, text, _alias in names_of(entity)}
        if names:
            out[qid] = " | ".join(sorted(names))
    return out


def upsert_position(row: dict[str, Any], names: Sequence[tuple[str, str, bool]]) -> None:
    """Write one position and its names, replacing what a previous load wrote."""
    columns = [
        "qid", "label", "description", "country_qid", "jurisdiction_qid",
        "jurisdiction_text", "body_qid", "kinds", "sources", "not_office",
        "inception", "abolished", "replaces", "replaced_by", "redirected_from",
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
    found = discover(qid, sources)
    for source, qids in found.items():
        log(f"{source}: {len(qids)} items")
    union = sorted({q for qids in found.values() for q in qids})
    log(f"union: {len(union)} items")

    entities = wikidata.fetch_items(union)
    missing = [q for q in union if q not in entities]
    if missing:
        log(f"missing or deleted: {len(missing)}")

    closure = type_closure(sorted(entities))
    rows: list[tuple[dict[str, Any], list[tuple[str, str, bool]]]] = []
    parents: set[str] = set()
    jurisdictions: set[str] = set()
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
        parents.update(kind_qids)
        jurisdiction = _unended_qid(entity, "P1001")
        if jurisdiction:
            jurisdictions.add(jurisdiction)
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
                "_closure": closure.get(actual, set()),
            },
            names_of(entity),
        ))

    kinds = _label_map(parents)
    juris = _jurisdiction_text(jurisdictions)
    for row, names in rows:
        row["kinds"] = [kinds[q] for q in row.pop("_kind_qids") if q in kinds]
        row["jurisdiction_text"] = juris.get(row["jurisdiction_qid"])
        row.pop("_closure", None)
        upsert_position(row, names)

    counts = {source: len(qids) for source, qids in found.items()}
    counts["loaded"] = len(rows)
    counts["names"] = sum(len(names) for _row, names in rows)
    return counts


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

#: How many rows each retrieval channel contributes before scoring. Wide
#: enough that ranking is the thing being measured and not the cut-off.
POOL = 200

#: pg_trgm floors. Low on purpose: recall is the table's job and precision is
#: the ranking's, and a title in an inflected language shares fewer trigrams
#: with its label than an English one does.
NAME_FLOOR = 0.2
JURISDICTION_FLOOR = 0.4


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


@dataclass
class Hit:
    """One position a query reached, and why it scored where it did."""

    qid: str
    #: The name that scored best — what to show beside the candidate.
    name: str
    lang: str
    score: float
    #: Does the candidate name everything the query names? The asymmetry is
    #: load-bearing: a generic "mayor" is contained *by* "mayor of Kravaře"
    #: and not the other way round, and ranking on containment alone would
    #: write a named mayoralty onto the occupation class.
    covers: bool
    jurisdiction: float = 0.0

    def sort_key(self) -> tuple[Any, ...]:
        return (self.covers, self.score + self.jurisdiction, self.qid)


def _name_pool(title: str, country_qid: str | None) -> list[tuple[str, str, str]]:
    """Candidate (qid, lang, name) rows a title reaches, both channels.

    Trigram similarity survives inflection and word order, which a `simple`
    tsvector cannot: "ministr obrany" and "ministra obrany" are different
    tokens to it. Full text catches the exact-token case the trigram floor
    would drop. Both are needed and neither subsumes the other.
    """
    scope = "" if country_qid is None else " AND p.country_qid = %(country)s"
    params = {"title": title, "country": country_qid, "pool": POOL,
              "floor": NAME_FLOOR}
    rows = db.conn().execute(
        "SELECT n.qid, n.lang, n.text FROM position_name n"
        " JOIN position p ON p.qid = n.qid"
        " WHERE n.text %% %(title)s" + scope +
        " ORDER BY similarity(n.text, %(title)s) DESC LIMIT %(pool)s",
        params,
    ).fetchall()
    fts = db.conn().execute(
        "SELECT n.qid, n.lang, n.text FROM position_name n"
        " JOIN position p ON p.qid = n.qid"
        " WHERE to_tsvector('simple', n.text) @@ plainto_tsquery('simple', %(title)s)"
        + scope +
        " ORDER BY ts_rank(to_tsvector('simple', n.text),"
        "                  plainto_tsquery('simple', %(title)s)) DESC LIMIT %(pool)s",
        params,
    ).fetchall()
    return list(rows) + list(fts)


def _jurisdiction_scores(text: str, country_qid: str | None) -> dict[str, float]:
    """How well each position's jurisdiction names the place the title gave.

    Word similarity rather than plain similarity, because the column holds
    every name the jurisdiction item has in every language: the question is
    whether the place appears in it, not whether the whole string looks alike.
    """
    scope = "" if country_qid is None else " AND country_qid = %(country)s"
    rows = db.conn().execute(
        "SELECT qid, word_similarity(%(text)s, jurisdiction_text) FROM position"
        " WHERE %(text)s <<%% jurisdiction_text" + scope +
        " ORDER BY 2 DESC LIMIT %(pool)s",
        {"text": text, "country": country_qid, "pool": POOL},
    ).fetchall()
    return {qid: score for qid, score in rows if score >= JURISDICTION_FLOOR}


def search(
    title: str,
    jurisdiction: str | None = None,
    country_qid: str | None = None,
    limit: int = 15,
) -> list[Hit]:
    """The positions an office title reaches, best first.

    Retrieval, not resolution: the shortlist is what a model is later shown,
    so a right answer buried at rank 40 is the same failure as no answer at
    all. The country is tried first and dropped when it finds nothing, since
    an article can name an office of a state its subject was never a citizen
    of.
    """
    pool = _name_pool(title, country_qid)
    if not pool and country_qid is not None:
        pool = _name_pool(title, None)
        country_qid = None
    if not pool:
        return []
    query_tokens = tokens(title)
    best: dict[str, Hit] = {}
    for qid, lang, name in pool:
        name_tokens = tokens(name)
        if not name_tokens or not query_tokens:
            continue
        score = len(query_tokens & name_tokens) / len(query_tokens | name_tokens)
        hit = best.get(qid)
        if hit is None or score > hit.score:
            best[qid] = Hit(qid=qid, name=name, lang=lang, score=score,
                            covers=query_tokens <= name_tokens)
    if jurisdiction:
        for qid, score in _jurisdiction_scores(jurisdiction, country_qid).items():
            if qid in best:
                best[qid].jurisdiction = score
    return sorted(best.values(), key=Hit.sort_key, reverse=True)[:limit]
