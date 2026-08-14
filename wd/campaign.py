"""Roster-driven P39 campaigns: the country-independent engine.

Reach for this when a country's officeholders are tabulated or listed on a
wiki page per office (`recipes/country_sweep.md`). The country script supplies
only parameters — which offices, which roster pages, which position items —
and this module does the rest: harvest category members, identify each roster
row's person, gate the risky identifications, tier the results, and write both
the machine verdicts and the audit document a human reads before anything is
applied.

The tiering is the point. Only rows where two independent channels agree — a
Wikipedia category *and* a roster row — and that fall inside the modern
institutional era reach the batch; everything else keeps its reason in an
`era` label and waits for a ruling.
"""

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import quote

from requests import Session

from wd.api import best_description, best_label, claim_qids, fetch_entities, sparql
from wd.backtest import (
    Comparison,
    ExistingTerm,
    compare,
    existing_terms,
    observed_family,
    shares_office_word,
)
from wd.backtest import dump as dump_comparisons
from wd.backtest import report as backtest_report
from wd.backtest import score as backtest_score
from wd.http import get_text
from wd.petscan import category_members
from wd.policy import Candidate, Facts, decide, tally
from wd.precedent import census, report
from wd.officebox import officebox_rows as box_rows
from wd.record import (
    Decision,
    Record,
    Signal,
    Snak,
    Statement,
    Subject,
    Value,
    dumps,
)
from wd.roster import (
    RosterRow,
    fold,
    merge_terms,
    name_tokens,
    names_match,
    parse_bullet_rosters,
    parse_rosters,
)
from wd.wikipedia import WIKI_API, fetch_html, fetch_pages, permalink

#: Occupations that make a public-office claim plausible. A name that matches
#: only an item with none of these — es.wikipedia's "Ernesto Albán" is a
#: comedian, its "Carlos Pérez García" a Spanish footballer — is a namesake,
#: not the minister the roster names.
POLITICAL_OCCUPATIONS = {
    "Q82955",    # politician
    "Q185351",   # jurist
    "Q40348",    # lawyer
    "Q193391",   # diplomat
    "Q188094",   # economist
    "Q212238",   # civil servant
    "Q2285706",  # head of government
    "Q1097498",  # military officer
}
POLITICAL_WORDS = re.compile(
    r"pol[íi]tic|ministr|minister|diplomat|presiden|alcald|mayor|senador|"
    r"asamble[íi]sta|abogad|jurist|econom|gobernador|prefect|"
    r"полит|палiт|мiнiстр|минист|дыпламат|дипломат|дзярж|госуд|урад|прав",
    re.I,
)

#: Table headings that mark the office's own holders, matched against the
#: FOLDED heading (`wd.roster.fold`), which is why "минист" also catches
#: "Міністры". Defaults suit ministry and office pages in several languages;
#: override per office when a page uses something unusual.
DEFAULT_HEADINGS = (
    r"^(?:titulares|ministr|минист|прэм|премьер|спис|список|глав|руковод|кираун"
    # Czech list articles head each era's table rather than the office:
    # "V rámci československé federace", "V rámci samostatné republiky".
    r"|seznam|v ramci|chronolog|soudc|predsed|prezident|premier)"
)

#: Section names inside an accepted table that describe a *different*,
#: pre-ministerial body, whose rows go to review rather than the batch.
DEFAULT_REVIEW_SECTIONS = (
    "direccion", "dirección", "corporacion", "corporación", "instituto",
    "consejo", "subsecretar", "secretaría nacional", "secretaria nacional",
)


@dataclass
class RosterSource:
    """A page carrying an office's holders."""

    lang: str
    page: str
    #: "table" for wikitables, "bullets" for `* [[Name]] (dates)` lists.
    kind: str = "table"
    #: Regex the table's own heading must match; None uses DEFAULT_HEADINGS.
    headings: Optional[str] = None
    #: (start, end) ISO dates every row on this page shares, for a page that
    #: *is* one term.
    #:
    #: Reach for this where a legislature publishes a membership roll per term
    #: and dates the term in the page title rather than in the rows. Saudi
    #: Arabia is the case: `قائمة أعضاء مجلس الشورى السعودي (1442-1446هـ)`
    #: tabulates 150 members with no date column at all, and the Hijri years in
    #: its title are the only statement of when they served. Without this the
    #: whole lane is `no_dates` and skipped.
    #:
    #: Applied only to rows that parsed no date of their own, so a page that
    #: dates *some* rows keeps what it says. A row's own dates always win.
    term: Tuple[Optional[str], Optional[str]] = (None, None)


@dataclass
class Office:
    key: str
    label: str
    #: The position item roster rows are proposed against.
    target: str
    rosters: Tuple[RosterSource, ...] = ()
    #: Explicit (lang, category) generators.
    categories: Tuple[Tuple[str, str], ...] = ()
    #: An en.wikipedia category whose interwiki siblings become generators too —
    #: how a country whose people are documented on another wiki gets covered.
    sibling_category: Optional[str] = None
    #: Section header pattern → position item, for a roster that spans two
    #: named ministries. Matched against the row's section heading *and* its
    #: office cell, since a list serving several polities usually names them in
    #: a rowspanned column rather than in headings. First match wins; a row
    #: matching none uses `target`.
    section_targets: Tuple[Tuple[str, str], ...] = ()
    #: (from_year, to_year, position item) — the item that owned this office
    #: during that window, `to_year` exclusive and either bound optional.
    #:
    #: Reach for this where a portfolio's item changes on a *date* rather than
    #: by section. Spain is the case: one continuous roster of foreign ministers
    #: runs across "Ministro de Estado" (to 1938), "Ministro de Asuntos
    #: Exteriores" (to 2004) and two later renamings, each of which is its own
    #: item carrying its own era's holders. Without it every row lands on
    #: whichever item the office names, and most of them would be wrong.
    date_targets: Tuple[Tuple[Optional[int], Optional[int], str], ...] = ()
    review_sections: Tuple[str, ...] = DEFAULT_REVIEW_SECTIONS
    #: Section/heading patterns that mark a *different regime's* office
    #: (Byelorussian SSR, the 1918 republic): held with this era name.
    regime_sections: Tuple[Tuple[str, str], ...] = ()
    #: A flag every candidate from this office carries, naming why the office
    #: as a whole is unsettled ("rename_history"). No longer a gate of its own:
    #: it reaches `wd.policy` like any other flag, and giving it a disposition
    #: is what releases the office.
    hold: Optional[str] = None
    #: Set instead of `target` when Wikidata has no item for this office. The
    #: shape comes from `wd.create.ARCHETYPES`; `body` names the ministry,
    #: court or chamber it belongs to. `scripts/create_offices.py` mints the
    #: item, after which `target` can be filled in and the office runs like any
    #: other.
    archetype: Optional[str] = None
    body: Optional[str] = None
    #: The subdivision a created item applies to, where the office is not
    #: national — `P1001` on the new item, which defaults to the country.
    #:
    #: Needed wherever a country's own convention scopes the office narrower
    #: than itself: the eight Saudi provincial governorships that already have
    #: items all carry `P1001 = <province>`, so minting the missing five with
    #: `P1001 = Q851` would make them a different shape from their siblings.
    jurisdiction: Optional[str] = None
    #: Labels for the item to be created, by language.
    create_labels: Tuple[Tuple[str, str], ...] = ()
    #: Base claims to override on the item to be created, `(property, value)`,
    #: with `None` removing one. See `wd.create.CreateSpec.claims_override`:
    #: the defaults describe a national office, and an outbound ambassadorship
    #: is not one.
    create_claims: Tuple[Tuple[str, object], ...] = ()
    #: The dynasty that holds this office, for a `P53` backfill, plus the
    #: surname spellings that name it.
    #:
    #: Only reach for this where the office *is* the family's — a hereditary
    #: rulership — because that is what makes the second channel independent:
    #: holding the throne of Ajman and being called "Al Nuaimi" are two separate
    #: assertions, and neither alone is emitted. Three of the six Emirati ruling
    #: houses have no member recorded at all, including two sitting rulers.
    #:
    #: Spellings are needed because transliteration varies and `fold()` does not
    #: touch it (Qasimi/Qassimi); they are matched against the person's own name
    #: tokens, never as a substring.
    family: Optional[str] = None
    family_names: Tuple[str, ...] = ()
    #: Wikis whose articles' *own infoboxes* should be read for this office's
    #: tenures, for an office no roster article lists. Empty for every office
    #: that has a roster — this is a fallback channel, not a supplement, and
    #: running both against one office would date one tenure from two sources.
    #: The rows it produces apply only where the category agrees; see
    #: `officebox.two_channel` in `wd/policy.py`.
    officebox: Tuple[str, ...] = ()


@dataclass
class Campaign:
    #: Subdirectory of data/ to write into, and the verdict file prefix.
    name: str
    country_qid: str
    #: Institutional era the position items were created for. Terms starting
    #: earlier are a continuity judgment, not a mechanical add.
    modern_from: int
    offices: Sequence[Office]
    #: Label languages to prefer when naming people in review output.
    label_langs: Tuple[str, ...] = ("en",)
    #: Wikis whose sibling categories to follow, in order of usefulness.
    sibling_wikis: Tuple[str, ...] = ("es", "ru", "be", "be_x_old", "uk")
    #: Verb phrase for the evidence sentence.
    evidence_verb: str = "lists them as minister"
    #: Positions whose concurrency with another office carries no meaning, so
    #: `interim_of` ignores them: a minister keeps their parliamentary seat
    #: throughout, and a council seat overlaps everything.
    concurrency_ignore: Tuple[str, ...] = ()
    #: Rule id → disposition, for the rare case where a country's own history
    #: contradicts the default policy. Declared once, never per person.
    dispositions: Dict[str, str] = field(default_factory=dict)
    #: Items that name an office only vaguely — "minister without portfolio",
    #: the bare "minister" some campaigns still point at. A statement proposed
    #: against one of these is redundant when the person already records the
    #: same span under a specific office; the reverse is not true, so this
    #: cannot be inferred from coinciding dates alone.
    generic_targets: Tuple[str, ...] = ()
    #: Era names naming the *same institution* under an earlier constitution —
    #: the Czech Republic within the federation, not the Protectorate. Their
    #: rows are judged on the target item's own record, like any other early
    #: term; every other era named by `regime_sections` is a different state
    #: and is skipped for want of its own item.
    continuous_eras: Tuple[str, ...] = ()
    #: Categories whose members belong to another regime entirely: (lang, cat).
    regime_categories: Tuple[Tuple[str, str, str], ...] = ()
    #: Verdict files this campaign owns that no office produces — a second
    #: script writing into the same directory.
    #:
    #: The manifest exists so a renamed office key cannot strand a stale file
    #: that the renderer goes on reading forever, which means anything *not*
    #: named by an office is an orphan by default. A campaign whose lanes are not
    #: all offices has to say so: Saudi Arabia's kinship lane (`sa_family.py`)
    #: proposes P25/P22/P53 from a genealogy article rather than from a roster,
    #: and belongs in the same one batch as its offices.
    extra_verdicts: Tuple[str, ...] = ()


@dataclass
class Person:
    qid: str
    label: str
    description: Optional[str] = None
    names: List[str] = field(default_factory=list)
    p39: List[str] = field(default_factory=list)
    #: The same statements with their dates: (position, start, end).
    p39_terms: List[Tuple[str, Optional[str], Optional[str]]] = field(default_factory=list)
    #: And once more with what a *comparison* needs rather than what a
    #: containment test needs — coarse bounds kept, P2868 read. The two cannot
    #: be merged: `interim_of` and friends require day precision to mean
    #: anything, while a backtest asking "is this the same term" must be able to
    #: tell a year-precision start from a missing one.
    p39_claims: List[ExistingTerm] = field(default_factory=list)
    p27: List[str] = field(default_factory=list)
    p106: List[str] = field(default_factory=list)
    p102: List[str] = field(default_factory=list)
    #: Families already recorded, so a backfill can ask "does this item point at
    #: *this* family" rather than "does it have a family at all". P53 is
    #: multi-valued and branch families are real: Mohammed bin Rashid carries
    #: both Al Maktoum and House of Al-Falasi, and the coarser test would skip
    #: everyone in a branch.
    p53: List[str] = field(default_factory=list)
    birth: Optional[int] = None
    death: Optional[int] = None
    #: Categories that put this person forward, empty for roster-only people.
    cats: List[str] = field(default_factory=list)
    #: Wiki language → article title. `names` already carries the titles, but
    #: flattened, and the officebox channel has to ask a different question:
    #: *which* wiki holds this person's article, so it can read the infobox on
    #: it. Kept as a map rather than re-deriving it from `names`, which cannot
    #: say which of several strings was a sitelink.
    sitelinks: Dict[str, str] = field(default_factory=dict)
    #: Era name when a category places them in an earlier polity's version of
    #: the office. Informational for people the roster names — they may have
    #: served under both — and decisive only for category-only candidates.
    regime: Optional[str] = None


#: Bytes of percent-encoded titles to put in one `titles=` parameter. The API
#: allows 50 titles per request, but a *count* is the wrong unit: a title is
#: percent-encoded into the query string, and a non-Latin script spends three
#: bytes per character before encoding triples it again, so fifty Arabic titles
#: make an 18 KB URI and the server answers 414 rather than truncating. Latin
#: campaigns never came close and so never found this.
TITLES_BUDGET = 3500


def _title_chunks(titles: Sequence[str], limit: int = 50) -> Iterable[List[str]]:
    """Batches of titles that fit both the API's count cap and a sane URI."""
    chunk: List[str] = []
    size = 0
    for title in titles:
        cost = len(quote(title)) + 3  # the "|" separator, encoded
        if chunk and (len(chunk) >= limit or size + cost > TITLES_BUDGET):
            yield chunk
            chunk, size = [], 0
        chunk.append(title)
        size += cost
    if chunk:
        yield chunk


def resolve_titles(session: Session, lang: str, titles: Iterable[str]) -> Dict[str, str]:
    """Wikipedia titles → QIDs, 50 per request, redirects followed.

    Used for both a roster's own wikilinks and, for unlinked rows, the bare
    name as a title — an article at exactly that name is the same evidence a
    wikilink would have been.
    """
    out: Dict[str, str] = {}
    todo = [t for t in dict.fromkeys(titles) if t]
    for chunk in _title_chunks(todo):
        data = json.loads(
            get_text(
                session,
                WIKI_API.format(lang=lang),
                params={
                    "action": "query",
                    "prop": "pageprops",
                    "ppprop": "wikibase_item",
                    "titles": "|".join(chunk),
                    "redirects": "1",
                    "formatversion": "2",
                    "format": "json",
                },
            )
        )
        query = data.get("query", {})
        alias: Dict[str, str] = {}
        for key in ("normalized", "redirects"):
            for entry in query.get(key, []):
                alias[entry["from"]] = entry["to"]
        resolved: Dict[str, str] = {}
        for page in query.get("pages", []):
            qid = (page.get("pageprops") or {}).get("wikibase_item")
            if qid:
                resolved[page["title"]] = qid
        for title in chunk:
            target = title
            seen = {target}
            while target in alias and alias[target] not in seen:
                target = alias[target]
                seen.add(target)
            if target in resolved:
                out[title] = resolved[target]
    return out


def sibling_categories(
    session: Session, lang: str, category: str, wikis: Sequence[str]
) -> List[Tuple[str, str]]:
    """The same category on other wikis, via the category item's sitelinks.

    Where a country's people are written up on a wiki other than the one the
    config names, this is what finds them: the enwiki category for Belarusian
    ministers has 35 members, its Belarusian sibling 243.
    """
    data = json.loads(
        get_text(
            session,
            WIKI_API.format(lang=lang),
            params={
                "action": "query",
                "prop": "pageprops",
                "ppprop": "wikibase_item",
                "titles": f"Category:{category.replace('_', ' ')}",
                "redirects": "1",
                "formatversion": "2",
                "format": "json",
            },
        )
    )
    qid = None
    for page in data.get("query", {}).get("pages", []):
        qid = (page.get("pageprops") or {}).get("wikibase_item")
    if not qid:
        return []
    entity = fetch_entities(session, [qid], props="sitelinks").get(qid, {})
    out: List[Tuple[str, str]] = []
    for wiki in wikis:
        link = entity.get("sitelinks", {}).get(f"{wiki}wiki")
        if link:
            title = link["title"].split(":", 1)[-1].replace(" ", "_")
            out.append((wiki.replace("_", "-"), title))
    return out


def year_of(entity: dict, prop: str) -> Optional[int]:
    for claim in entity.get("claims", {}).get(prop, []):
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(value, dict) and "time" in value:
            if value.get("precision", 11) < 9:
                continue  # a century renders as a misleading year
            return int(value["time"].lstrip("+")[:4])
    return None


def dated_positions(entity: dict) -> List[Tuple[str, Optional[str], Optional[str]]]:
    """Every P39 the item already carries, with its start and end date.

    `claim_qids` reads the values alone, but the dates are what let an existing
    statement act as a second channel: a two-month ministry sitting inside the
    person's own four-year premiership is cover, not a term of its own. Only
    day-precision qualifiers are kept, since coarser ones cannot bracket a
    spell of a few weeks.
    """
    spans: List[Tuple[str, Optional[str], Optional[str]]] = []
    for claim in entity.get("claims", {}).get("P39", []):
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        if not isinstance(value, dict) or "id" not in value:
            continue
        bounds: Dict[str, str] = {}
        for prop, key in (("P580", "start"), ("P582", "end")):
            for qualifier in claim.get("qualifiers", {}).get(prop, []):
                time_value = qualifier.get("datavalue", {}).get("value")
                if isinstance(time_value, dict) and time_value.get("precision", 0) >= 11:
                    bounds[key] = time_value["time"].lstrip("+")[:10]
        spans.append((value["id"], bounds.get("start"), bounds.get("end")))
    return spans


def interim_of(
    row: RosterRow, person: Person, target: str, ignore: Sequence[str]
) -> Optional[str]:
    """The office this spell was covering for, if it looks like cover at all.

    Two channels have to agree before a roster row is read as an interim
    appointment: the spell is too short to be a term of its own, *and* it falls
    inside a dated term the person already holds for a different office. Both
    are needed — Petr Krčál really was labour minister for 21 days, while
    Vladimír Špidla's 41 days at Justice sit inside his premiership. Positions
    in `ignore` are skipped, because a minister holds their parliamentary seat
    the whole time and that overlap means nothing.
    """
    if not row.start or not row.end or len(row.start) != 10 or len(row.end) != 10:
        return None
    length = date.fromisoformat(row.end) - date.fromisoformat(row.start)
    if length.days >= SHORT_SPELL_DAYS:
        return None
    for qid, start, end in person.p39_terms:
        if qid == target or qid in ignore or start is None:
            continue
        if start <= row.start and (end is None or row.end <= end):
            return qid
    return None


def already_under_sibling(
    row: RosterRow, person: Person, target: str, siblings: Sequence[str]
) -> Optional[str]:
    """Another item of *this same office* already carrying this term, if one is.

    One office, several items is the normal state of affairs in Spain: the
    President of the Congress of Deputies is both Q17014422 and Q45213921, and
    the community files 1876–1923 on the second and everything modern on the
    first, with the 19th century scattered across both. A roster row whose spell
    the person already records under a sibling item is that same appointment —
    proposing it again on the item this office happens to name would duplicate
    it, and (because the spell sits inside the sibling's span) `interim_of` would
    read it as an acting appointment and add a P2868 to boot.

    Distinct from `coincides_with`, which asks whether a *vaguer* office
    duplicates a specific one and needs the dates to match exactly. Here the two
    items are the same office, so containment is enough.
    """
    if not row.start:
        return None
    for qid, start, end in person.p39_terms:
        if qid == target or qid not in set(siblings) or start is None:
            continue
        # Overlap, not containment: an office has one holder at a time, so two
        # overlapping spells of the same office are one appointment written down
        # twice with different end dates. Moscoso's 1821 presidency is on record
        # as ending on the 21st where the roster says the 30th.
        if start <= (row.end or row.start) and (end is None or row.start <= end):
            return qid
    return None


def coincides_with(
    terms: Sequence[Tuple[Optional[str], Optional[str]]],
    person: Person,
    target: str,
    generic_targets: Sequence[str],
) -> Optional[str]:
    """The specific office this generic term is already recorded under.

    The mirror of `interim_of`: that asks whether a spell sits *inside* a term
    the person holds elsewhere, this asks whether it *coincides* with one.

    Czechia is the case that made it necessary. "Ministr bez portfeje" is the
    formal appointment and the roster's `Gesce` column names the remit, which
    Wikidata already records as the office — so eight ministers were about to
    be given the generic item *on top of* the specific one, same dates.

    **Direction is the whole rule**, which is why `generic_targets` is required
    rather than inferred. Coinciding dates alone mean nothing: Alexandr Vondra
    was Deputy Prime Minister and Minister for European Affairs across exactly
    the same span and genuinely held both, and María Alejandra Vicuña's
    housing term coincides with a generic `Q83307` "minister" statement that
    the specific one ought to *replace*. Only a proposed statement that is
    vaguer than what the item already says is redundant.
    """
    if target not in set(generic_targets):
        return None
    for start, end in terms:
        if not start or not end:
            continue
        for qid, other_start, other_end in person.p39_terms:
            if qid == target or not other_start or not other_end:
                continue
            if other_start == start and other_end == end:
                return qid
    return None


def lifetime_conflict(person: Person, start: Optional[str]) -> Optional[str]:
    """Why this person cannot have held office from `start`, if they cannot.

    Namesakes across centuries are the failure mode a name match cannot see:
    es.wikipedia has one Ángel Polibio Chaves (1855–1930) and a roster names
    another as labour minister in 1998.
    """
    if not start:
        return None
    year = int(start[:4])
    if person.birth is not None and year - person.birth < 18:
        return f"born {person.birth}, term starts {year}"
    if person.death is not None and person.death < year:
        return f"died {person.death}, term starts {year}"
    return None


def political_marker(person: Person) -> bool:
    """Does anything on this item suggest a person who holds public office?"""
    if person.p39 or person.p102:
        return True
    if POLITICAL_OCCUPATIONS.intersection(person.p106):
        return True
    return bool(person.description and POLITICAL_WORDS.search(person.description))


def title_variants(name: str) -> List[str]:
    """A roster name and the shorter titles its article may actually sit at.

    Rosters print every name part ("Carlos Marx Carrasco Vicuña") while the
    article often sits at fewer, so the full name alone finds nothing.
    Truncations are namesake-prone, hence the gates in `identify`.
    """
    parts = name.split()
    return [" ".join(parts[:n]) for n in range(len(parts), 1, -1)]


#: Cache lifetime for the reads that establish *what Wikidata already records*,
#: as opposed to what a wiki page says. Zero, deliberately.
#:
#: `wd/http.py` caches for seven days, which is right for roster HTML and
#: category membership — a Wikipedia table does not move much, and re-fetching it
#: on every iteration is rude. It is wrong for the state this engine checks
#: itself against, because that state is exactly what the engine's own writes
#: change. A UAE re-run read a `holders()` list cached before its batch went in:
#: 5 holders against 10 live, so the `already holds P39` gate let twenty
#: already-existing statements back into the batch. Half of the whole point of
#: this engine is not proposing what is already there.
STATE_MAX_AGE = 0


def holders(session: Session, qid: str) -> set:
    """Everyone Wikidata already records in this position, any rank."""
    rows = sparql(
        session, f"SELECT DISTINCT ?p WHERE {{ ?p p:P39 ?st . ?st ps:P39 wd:{qid} . }}",
        max_age=STATE_MAX_AGE,
    )
    return {row["p"] for row in rows}


def office_rows(
    session: Session, office: Office
) -> Tuple[List[RosterRow], List[str], List[str]]:
    """The office's roster rows, the tables skipped, and the source URLs."""
    rows: List[RosterRow] = []
    skipped: List[str] = []
    sources: List[str] = []
    for source in office.rosters:
        page = fetch_html(session, source.lang, source.page)
        if page is None:
            skipped.append(f"{source.lang}:{source.page} MISSING")
            continue
        sources.append(permalink(source.lang, page["revid"]))
        pattern = source.headings or DEFAULT_HEADINGS
        if source.kind == "bullets":
            rosters = parse_bullet_rosters(page["html"])
        else:
            rosters = parse_rosters(page["html"])
        for roster in rosters:
            heading = (roster.heading or "").strip()
            # A table with no date column is a legend or a navbox, not a roster:
            # es.wikipedia heads each era's table with an "Espectro político"
            # colour key that otherwise contributes one unidentifiable row per
            # era to the audit's item-creation column.
            # …unless the source declares the dates itself. A membership roll
            # for one term has no date column *by design* — the term is in the
            # page title — so `term=` has to license the table the guard would
            # otherwise throw away.
            if roster.columns != ["bullet"] and source.term == (None, None) and not (
                {"period", "start", "end"} & set(roster.columns)
            ):
                skipped.append(
                    f"{heading or '(no heading)'} [{len(roster.rows)} rows, "
                    "no date column — legend or navbox]"
                )
                continue
            if roster.columns == ["bullet"] or re.search(pattern, fold(heading), re.I):
                for row in roster.rows:
                    # A bullet list has no in-table sections; carry the
                    # heading so regime routing still has something to read.
                    if row.section is None and heading:
                        row.section = heading
                    # A page that is one term dates the rows that date
                    # themselves nowhere. The row's own dates win where it has
                    # them, so a roll that footnotes a mid-term replacement
                    # keeps the footnote.
                    if source.term != (None, None) and not row.start:
                        row.start, row.end = source.term
                        row.period_raw = (
                            row.period_raw
                            or f"{source.term[0] or '?'} – {source.term[1] or '?'} "
                               "(the page's own term)"
                        )
                    rows.append(row)
            else:
                skipped.append(f"{heading or '(no heading)'} [{len(roster.rows)} rows]")
    return rows, skipped, sources


def build_people(
    session: Session,
    campaign: Campaign,
    office: Office,
    rows: Sequence[RosterRow],
) -> Tuple[Dict[str, Person], Dict[Tuple[str, str], str]]:
    """The person universe: category members plus roster-identified people."""
    generators: List[Tuple[str, str]] = list(office.categories)
    if office.sibling_category:
        generators.append(("en", office.sibling_category))
        generators += sibling_categories(
            session, "en", office.sibling_category, campaign.sibling_wikis
        )

    cats: Dict[str, List[str]] = {}
    titles: Dict[str, List[str]] = {}
    for lang, category in dict.fromkeys(generators):
        try:
            members = category_members(session, category, lang, depth=0)
        except Exception as exc:  # noqa: BLE001 — a missing category is data, not a crash
            print(f"    ! {lang}:{category}: {exc}")
            continue
        for qid, title in members:
            titles.setdefault(qid, []).append(title)
            cats.setdefault(qid, []).append(f"{lang}:{category}")

    regimes: Dict[str, str] = {}
    for lang, category, era in campaign.regime_categories:
        try:
            for qid, _ in category_members(session, category, lang, depth=1):
                regimes.setdefault(qid, era)
        except Exception as exc:  # noqa: BLE001
            print(f"    ! regime {lang}:{category}: {exc}")

    # Roster identities are resolved per roster language.
    by_title: Dict[Tuple[str, str], str] = {}
    for source in office.rosters:
        wanted: List[str] = []
        for row in rows:
            if row.link:
                wanted.append(row.link)
            else:
                wanted.extend(title_variants(row.name))
        for title, qid in resolve_titles(session, source.lang, wanted).items():
            by_title.setdefault((source.lang, title), qid)

    entities = fetch_entities(
        session,
        sorted(set(titles) | set(by_title.values())),
        props="labels|descriptions|aliases|claims|sitelinks",
        # Their existing P39s are what `duplicated`, `already_under_sibling` and
        # the backtest are all measured against — state, not page content.
        max_age=STATE_MAX_AGE,
    )
    people: Dict[str, Person] = {}
    for qid, entity in entities.items():
        if "Q5" not in claim_qids(entity, "P31"):
            continue  # PETScan's Q5 filter also passes Category: items
        names = list(titles.get(qid, []))
        for lang in campaign.label_langs + ("en", "mul"):
            term = entity.get("labels", {}).get(lang)
            if term:
                names.append(term["value"])
            for alias in entity.get("aliases", {}).get(lang, []):
                names.append(alias["value"])
        sitelinks: Dict[str, str] = {}
        for wiki in campaign.sibling_wikis + ("en",):
            link = entity.get("sitelinks", {}).get(f"{wiki}wiki")
            if link:
                names.append(link["title"])
                sitelinks.setdefault(wiki, link["title"])
        label = next(
            (
                entity["labels"][lang]["value"]
                for lang in campaign.label_langs
                if entity.get("labels", {}).get(lang)
            ),
            None,
        )
        people[qid] = Person(
            qid=qid,
            label=label or best_label(entity) or (names[0] if names else qid),
            description=best_description(entity),
            names=list(dict.fromkeys(names)),
            p39=claim_qids(entity, "P39"),
            p39_terms=dated_positions(entity),
            p39_claims=existing_terms(entity),
            p27=claim_qids(entity, "P27"),
            p106=claim_qids(entity, "P106"),
            p102=claim_qids(entity, "P102"),
            p53=claim_qids(entity, "P53"),
            birth=year_of(entity, "P569"),
            death=year_of(entity, "P570"),
            cats=cats.get(qid, []),
            regime=regimes.get(qid),
            sitelinks=sitelinks,
        )
    return people, by_title


def officebox_rows(
    session: Session,
    office: Office,
    people: Dict[str, Person],
    by_title: Dict[Tuple[str, str], str],
    lang: str,
) -> List[RosterRow]:
    """Rows read from each candidate's own infobox, for offices no roster lists.

    The office lane's usual evidence is a roster: one article dating every
    holder at once. Where a country publishes none — Qatar dates two of its
    thirty-two ministries — the same facts are still written down, one person at
    a time, in the infobox of each holder's own article.

    Only the office's *category members* are read, never the whole country: the
    category is the second channel `wd.policy` requires before an infobox row
    may apply, so a person outside it could not produce an applying row anyway.
    """
    rows: List[RosterRow] = []
    # One source per person, in the order the office names its wikis. A person
    # with an article on both wikis has their tenure stated twice, and the two
    # disagree in small ways: Q5746141's ICT ministership ends 2016-01-27 on one
    # and 2016-01-26 on the other, which is two sources dating one tenure and
    # exactly what §7 forbids for rosters. `wd/validate.py` refuses to render it
    # and is right to. Reading the second wiki only for people the first does
    # not cover keeps the reach of both without dating anything twice.
    covered: set = set()
    for box_lang in office.officebox:
        titles: Dict[str, str] = {}
        for qid, person in people.items():
            title = person.sitelinks.get(box_lang)
            # Category members only — see the docstring.
            if title and person.cats and qid not in covered:
                titles.setdefault(title, qid)
        if not titles:
            continue
        pages = fetch_pages(session, box_lang, sorted(titles))
        found = box_rows(pages, box_lang, sorted(titles))
        # `identify` resolves a row's link through `by_title[(lang, title)]`,
        # and these titles were resolved the other way round — from the item to
        # its sitelink — so the mapping is already known and authoritative.
        # Registered under the office's own identify language because that is
        # the key `identify` will look under, whichever wiki the article is on.
        for title, qid in titles.items():
            by_title.setdefault((lang, title), qid)
        covered.update(titles[row.link] for row in found if row.link in titles)
        rows.extend(found)
    return rows


def identify(
    row: RosterRow,
    people: Dict[str, Person],
    by_title: Dict[Tuple[str, str], str],
    lang: str,
    country_qid: str,
) -> Tuple[Optional[str], str]:
    """Roster row → QID, with how it was established (or why it wasn't)."""
    if row.link:
        qid = by_title.get((lang, row.link))
        if qid in people:
            return qid, "wikilink"
        if qid:
            return None, f"linked to {qid}, not a human item"
        return None, f"link '{row.link}' has no Wikidata item"
    for index, title in enumerate(title_variants(row.name)):
        qid = by_title.get((lang, title))
        person = people.get(qid) if qid else None
        if person is None:
            continue
        # An article title is not a wikilink from the roster: the roster never
        # asserted this identity, so it has to survive three checks — no
        # contradicting citizenship, a lifetime covering the term, and some
        # sign that this person holds public office at all.
        if person.p27 and country_qid not in person.p27:
            continue
        if lifetime_conflict(person, row.start):
            continue
        if not political_marker(person):
            continue
        if index == 0:
            return qid, "article title"
        if not any(names_match(row.name, n) for n in person.names):
            continue
        return qid, f"article title '{title}'"
    hits = [
        candidate
        for candidate, person in people.items()
        if person.cats
        and any(names_match(row.name, name) for name in person.names)
        and not lifetime_conflict(person, row.start)
    ]
    if len(hits) == 1:
        return hits[0], "name match"
    if len(hits) > 1:
        return None, f"ambiguous: {', '.join(hits)}"
    return None, "no item found under this name"


def verify_family(
    session: Session,
    candidates: Sequence[Tuple[str, int]],
    targets: Sequence[str],
    country_qid: str,
) -> Tuple[List[Tuple[str, int]], List[str]]:
    """Split cohort-derived items into ones that are this office, and the rest.

    Two channels have to agree before an item nobody declared is treated as the
    same office, because the cost of getting it wrong is a *silent suppression*
    of a real statement:

    * it must be **this country's** office (P17 or P1001). Without this the
      generic classes editors reach for — Q83307 "minister", Q2632935 "minister
      of state" — join the family, and the specific statement that ought to
      replace a generic one gets skipped as a duplicate instead.
    * its label must **name the same office**, not merely the same kind of
      office (`shares_office_word`). Nineteenth-century Spanish premiers took the
      Estado portfolio on the day they formed a government, so the premiership
      agrees with the roster on a boundary and would otherwise be read as an
      item for the foreign ministry.

    What fails goes back to the audit rather than into a rule: declaring it in
    `date_targets` or `section_targets` is a human's call, and the profile is
    where such a call belongs.
    """
    if not candidates:
        return [], []
    entities = fetch_entities(
        session, [qid for qid, _ in candidates] + list(targets), props="labels|claims"
    )
    target_labels = [
        best_label(entities[qid]) or "" for qid in targets if qid in entities
    ]
    verified: List[Tuple[str, int]] = []
    rejected: List[str] = []
    for qid, count in candidates:
        entity = entities.get(qid)
        if entity is None:
            rejected.append(f"{qid} ×{count} (no such item)")
            continue
        label = best_label(entity) or qid
        scope = set(claim_qids(entity, "P17")) | set(claim_qids(entity, "P1001"))
        if country_qid not in scope:
            rejected.append(f"{qid} ×{count} {label!r} (not scoped to the country)")
        elif not any(shares_office_word(label, other) for other in target_labels):
            rejected.append(f"{qid} ×{count} {label!r} (names a different office)")
        else:
            verified.append((qid, count))
    return verified, rejected


def target_for(row: RosterRow, office: Office) -> str:
    """The position item this row's term belongs to.

    Explicit section routing first — a heading or an office cell naming the
    polity is a statement about *this* row — then the date windows, which are a
    statement about the office's history.
    """
    # Both spellings of what the row says, because both kinds of pattern are in
    # use: the Czech profile matches accented section headings verbatim, while a
    # pattern for "Cataluña" is easier to write accent-free.
    said = [part for part in (row.section, row.cells.get("office")) if part]
    haystack = " · ".join([p.casefold() for p in said] + [fold(p) for p in said])
    for pattern, qid in office.section_targets:
        if re.search(pattern, haystack):
            return qid
    if row.start:
        year = int(row.start[:4])
        for start, end, qid in office.date_targets:
            if (start is None or year >= start) and (end is None or year < end):
                return qid
    return office.target


def review_section(row: RosterRow, office: Office) -> Optional[str]:
    section = (row.section or "").casefold()
    return row.section if any(w in section for w in office.review_sections) else None


def regime_of(row: RosterRow, office: Office) -> Optional[str]:
    section = row.section or ""
    for pattern, era in office.regime_sections:
        if re.search(pattern, section, re.I):
            return era
    return None


#: A ministerial spell shorter than this is nearly always an interim
#: appointment — a sitting minister or the premier formally charged with a
#: second portfolio — for which the convention is `P39` plus `P2868 = Q4676846`
#: rather than a plain statement.
SHORT_SPELL_DAYS = 90


def short_spells(records: Sequence[Record]) -> List[str]:
    """Warn about batched terms brief enough to be an interim appointment.

    Reach for this where a wiki marks acting officials nowhere: cs.wikipedia
    numbers Vladimír Špidla's 41-day spell at Justice as the office's eighth
    holder, with no legend, note or colour to distinguish it, so its duration is
    the only channel left that can raise the question for a human.
    """
    warnings: List[str] = []
    for record in records:
        if record.decision.action not in ("apply", "hold"):
            continue
        for statement in record.statements:
            bounds = {q.property: q.value.iso for q in statement.qualifiers}
            start, end = bounds.get("P580"), bounds.get("P582")
            if not start or not end or len(start) != 10 or len(end) != 10:
                continue
            days = (date.fromisoformat(end) - date.fromisoformat(start)).days
            if 0 <= days < SHORT_SPELL_DAYS:
                warnings.append(
                    f"{record.subject.qid} {record.subject.label} held "
                    f"{statement.value.id} for {days} days ({start} – {end}) "
                    "— interim spell?"
                )
    return warnings


#: P31 of a political party. Resolving the party column against this rather
#: than trusting the link keeps "nestraník" — non-party, which cs.wikipedia
#: writes in the same column for a third of Czech ministers — from becoming a
#: claim of membership in a party of that name.
PARTY_CLASS = "Q7278"

#: Cell text meaning the person sat for a party without belonging to it.
#: cs.wikipedia writes "nestraník za ANO" — non-party, nominated by ANO — and
#: still *links* ANO, so the link alone would assert the opposite of what the
#: cell says. Roman Prymula and Jan Blatný were both proposed as ANO members
#: this way before the guard existed.
NON_MEMBER = re.compile(
    r"nestran|bezpartijn|беспартийн|беспарт|незалежн|independiente|independent"
    r"|sin partido|nom\.|navržen",
    re.I,
)


def family_records(
    campaign: "Campaign", office: Office,
    per_person: Dict[Tuple[str, str], List[RosterRow]],
    people: Dict[str, Person], source: str,
) -> List[Record]:
    """P53 statements a hereditary office proves, and that nobody wrote down.

    The Emirates make this mechanical where elsewhere it would be a judgment
    call. Every Ruler of Umm Al Quwain is an Al Mualla and every Ruler of Ajman
    an Al Nuaimi, so *holding the office* and *carrying the name* are two
    independent assertions about the same fact — which is the two-channel bar
    this workbench applies to everything else. Neither channel is emitted alone:
    a name without the throne is a namesake, and the throne without the name is
    the case where a dynasty changed hands.

    It is worth doing because the gap is total rather than marginal: the Al
    Nuaimi, Al Sharqi and Al Mualla items have **no** members at all, and two of
    the missing people are the sitting rulers of Ajman and Fujairah.
    """
    if not office.family or not office.family_names:
        return []
    wanted = {fold(name) for name in office.family_names}
    records: List[Record] = []
    for qid in dict.fromkeys(qid for qid, _target in per_person):
        person = people[qid]
        # Not "has no family": P53 is multi-valued and a branch house is a real
        # second value, so the question is whether *this* family is recorded.
        if office.family in person.p53:
            continue
        spellings = [person.label, *person.names]
        matched = next(
            (
                name for name in wanted
                if any(name in name_tokens(spelling) for spelling in spellings)
            ),
            None,
        )
        if matched is None:
            continue
        records.append(Record(
            campaign=campaign.name,
            office=office.key,
            subject=Subject(kind="item", qid=qid, label=person.label),
            statements=[Statement(
                "P53", Value.item(office.family),
                references=[Snak("S4656", Value.url(source))] if source else [],
            )],
            decision=Decision(
                action="apply", rule="family.office_and_name", concern="p53",
                rationale="they hold this dynasty's own office and carry its "
                          "name, and the item records no P53 for it",
            ),
            identity={"method": "office holder"},
            flags=["family"],
            signals=[Signal(
                "office_holder", "family",
                f"holds {office.label}, whose dynasty is {office.family}, and "
                f"their name carries {matched!r}",
                source or None,
            )],
        ))
    return records


def party_records(
    session: Session, campaign: "Campaign", office: Office,
    per_person: Dict[Tuple[str, str], List[RosterRow]],
    people: Dict[str, Person], lang: str, source: str,
) -> List[Record]:
    """P102 statements the roster already proves, and that nobody wrote down.

    The party column is parsed for every row and then discarded. It prints an
    abbreviation but *links* the full name, so the link resolves to the party
    item without a per-country lexicon of initials.

    Emitted bare, with no dates: party membership is not bounded by the
    ministry, and the roster only says which party the person sat for at the
    time. Anyone already carrying a P102 is left alone, because a
    renamed-party duplicate is worse than a gap.
    """
    titles = {
        title
        for rows in per_person.values() for row in rows
        for title in row.links.get("party", [])
    }
    if not titles:
        return []
    by_title = resolve_titles(session, lang, sorted(titles))
    entities = fetch_entities(session, sorted(set(by_title.values())), props="claims")
    parties = {
        qid for qid, entity in entities.items()
        if PARTY_CLASS in claim_qids(entity, "P31")
    }

    records: List[Record] = []
    for (qid, _target), rows in per_person.items():
        person = people[qid]
        if person.p102:
            continue
        seen = []
        for row in rows:
            # The cell's *text* decides whether this is membership; the link
            # only says which party. "nestraník za ANO" links ANO and means
            # the person is not a member of it.
            if NON_MEMBER.search(row.cells.get("party", "")):
                continue
            for title in row.links.get("party", []):
                party = by_title.get(title)
                if party in parties and party not in seen:
                    seen.append(party)
        for party in seen:
            records.append(Record(
                campaign=campaign.name,
                office=office.key,
                subject=Subject(kind="item", qid=qid, label=person.label),
                statements=[Statement(
                    "P102", Value.item(party),
                    references=[Snak("S4656", Value.url(source))] if source else [],
                )],
                decision=Decision(
                    action="apply", rule="party.roster_column", concern="p102",
                    rationale="the roster's party column links this party, and "
                              "the item carries no P102 to contradict it",
                ),
                identity={"method": "roster party column"},
                flags=["party"],
                signals=[Signal(
                    "roster_party", "party",
                    f"roster lists them for {', '.join(row.cells.get('party', '') for row in rows[:1])}",
                    source or None,
                )],
            ))
    return records


def era_flag(start: Optional[str], modern_from: int) -> str:
    """Where a single term sits relative to the institutional cutoff.

    Every row carries this *alongside* its tier, not instead of it. An acting
    spell is still a term, and a spell in 1836 has to answer the same question
    about the target item as any other 1836 term — which it cannot do if
    "acting" is the only thing recorded about it.
    """
    if not start:
        return "no_dates"
    return "historical" if int(start[:4]) < modern_from else "modern"


def position_record(
    *, campaign: str, office: str, qid: str, label: str, target: str,
    verdict: str, era: str, terms: Sequence[dict], evidence: str, notes: str,
    source_url: str, source_prop: str, identity: Dict[str, object],
    facts: Facts, overrides: Optional[Dict[str, str]] = None,
    in_category: bool = False, extra_flags: Sequence[str] = (),
) -> Record:
    """One officeholding claim, decided and rendered as an edit record.

    Wikidata models each term as its own P39 statement, so a person with two
    separate spells in an office yields two statements on one record — the
    record is the decision, the statements are what it authorises.
    """
    flags = (era,) + tuple(extra_flags)
    candidate = Candidate(
        qid=qid,
        target=target,
        flags=flags,
        terms=tuple((t.get("start"), t.get("end")) for t in terms),
        identity=str(identity.get("method", "")),
        believed=verdict == "add",
        in_category=in_category,
        # S854 is used only when the roster row footnoted a real source; a
        # permalink to the roster itself goes in S4656 and is not a channel.
        cited=source_prop == "S854",
        office=office,
    )
    ruling = decide(candidate, facts, overrides=overrides)

    reference = [Snak(source_prop, Value.url(source_url))] if source_url else []
    statements = []
    for term in terms or [{}]:
        qualifiers = [
            Snak(prop, Value.time(term[key]))
            for prop, key in (("P580", "start"), ("P582", "end"))
            if term.get(key)
        ]
        # A disposition can carry qualifiers of its own — P2868 for the spells
        # a rule judges to be cover rather than tenure.
        qualifiers += [
            Snak(prop, Value.item(value))
            for prop, value in sorted(ruling.qualifiers.items())
        ]
        statements.append(
            Statement("P39", Value.item(target), qualifiers, list(reference))
        )
    return Record(
        campaign=campaign,
        office=office,
        subject=Subject(kind="item", qid=qid, label=label),
        statements=statements,
        decision=Decision(
            action=ruling.disposition,
            rule=ruling.rule,
            source=ruling.source,
            concern="p39",
            rationale=ruling.rationale,
        ),
        identity=dict(identity),
        flags=list(flags),
        signals=[Signal("roster_row", "office", evidence, source_url or None)],
        notes=notes,
    )


def overlaps(terms: Sequence[Tuple[str, Optional[str], Optional[str]]]) -> List[str]:
    """Warn when two people's terms overlap — a roster is sequential, so an
    overlap means a misparsed cell rather than a genuine co-appointment."""
    warnings: List[str] = []
    ordered = sorted((t for t in terms if t[1]), key=lambda t: t[1] or "")
    for (qid_a, start_a, end_a), (qid_b, start_b, _) in zip(ordered, ordered[1:]):
        if end_a and start_b and end_a > start_b and qid_a != qid_b:
            warnings.append(f"{qid_a} ({start_a}–{end_a}) overlaps {qid_b} (from {start_b})")
    return warnings


def run(session: Session, campaign: Campaign, out_dir: Path, keys: Optional[Sequence[str]] = None) -> None:
    """Run the campaign: verdict JSONL per office plus one audit document."""
    offices = [o for o in campaign.offices if keys is None or o.key in keys]
    # An office with no target has no item yet; `scripts/create_offices.py`
    # mints it, and until then there is nothing to propose statements against.
    pending = [o for o in offices if not o.target]
    offices = [o for o in offices if o.target]
    if pending:
        print(
            "! offices awaiting item creation (run scripts/create_offices.py): "
            + ", ".join(o.key for o in pending)
        )
    if not offices:
        raise SystemExit(f"No office matched {keys}")
    verdict_dir = out_dir / "verdicts"
    verdict_dir.mkdir(parents=True, exist_ok=True)
    # Everything measured before any decision is taken, so `policy.decide` is a
    # pure function of (candidate, facts). Empty until the precedent census
    # and the second-channel resolver fill it.
    # Everything measurable is measured before any decision is taken, so
    # `policy.decide` stays a pure function of (candidate, facts).
    all_targets = [
        qid for qid in (
            [o.target for o in offices]
            + [qid for o in offices for _, qid in o.section_targets]
            + [qid for o in offices for _, _, qid in o.date_targets]
        ) if qid
    ]
    precedents = census(session, all_targets, cache=out_dir / "precedent.json")
    regimes = {era for o in campaign.offices for _, era in o.regime_sections}
    regimes |= {era for _, _, era in campaign.regime_categories}
    facts = Facts(
        precedent=precedents,
        modern_from=campaign.modern_from,
        continuous_eras=frozenset(campaign.continuous_eras),
        regimes=frozenset(regimes),
    )
    #: (rule, disposition) for every record written, for the policy summary.
    decisions: List[Tuple[str, str]] = []
    #: Every row the record already answers, across all offices — the backtest.
    all_comparisons: List[Comparison] = []
    scores = []
    audit: List[str] = [
        f"# {campaign.name.title()} — roster match audit",
        "",
        "Every roster row, how its person was identified, and what became of "
        "it. `add` rows are in the .qs; everything else is review.",
        "",
    ]
    totals: Counter = Counter()

    for office in offices:
        rows, skipped, sources = office_rows(session, office)
        source = sources[0] if sources else ""
        people, by_title = build_people(session, campaign, office, rows)
        targets = [
            qid for qid in (
                [office.target]
                + [qid for _, qid in office.section_targets]
                + [qid for _, _, qid in office.date_targets]
            ) if qid
        ]
        held_by_target = {t: holders(session, t) for t in dict.fromkeys(targets)}
        lang = office.rosters[0].lang if office.rosters else "en"
        if office.officebox:
            extra = officebox_rows(session, office, people, by_title, lang)
            print(f"    officebox: {len(extra)} tenure(s) from "
                  f"{'/'.join(office.officebox)} infoboxes")
            rows = list(rows) + extra

        per_person: Dict[Tuple[str, str], List[RosterRow]] = {}
        row_status: List[Tuple[RosterRow, Optional[str], str]] = []
        # How each person's identity was established. A wikilink is Wikipedia
        # asserting it; a truncated article title is this engine guessing, and
        # a rule that applies on one rung should not apply on the other.
        identity_of: Dict[str, Dict[str, object]] = {}
        #: Rows whose era has no position item at all — a `date_targets` window
        #: declared empty. Spain's 1927–1931 Asamblea Nacional Consultiva is the
        #: case: its president is on the Congress roster, the chamber is not the
        #: Congress, and Wikidata has no item for the office. There is nothing to
        #: propose, so the row is recorded here and read as an item-creation
        #: byproduct rather than filed under the nearest item that exists.
        no_item: Dict[int, bool] = {}
        for row in rows:
            qid, how = identify(row, people, by_title, lang, campaign.country_qid)
            row_status.append((row, qid, how))
            if qid:
                target = target_for(row, office)
                if not target:
                    no_item[id(row)] = True
                    continue
                per_person.setdefault((qid, target), []).append(row)
                identity_of.setdefault(qid, {"method": how.split(" '")[0]})

        records: List[Record] = []
        # Per target, not per office: two autonomous communities' presidents
        # overlap all the time, and it means nothing.
        spans: Dict[str, List[Tuple[str, Optional[str], Optional[str]]]] = {}
        statuses: Dict[int, str] = {
            rid: "skip: no item exists for this era" for rid in no_item
        }

        # The rows the record already answers, measured before anything is
        # decided. Two thirds of a roster is typically people whose spell is
        # already written down somewhere, and the engine's only use for them has
        # been to skip them — but each one says what the community actually does
        # with this office, and that is the only evidence available for whether
        # the routing, the parsing and the tenure rules are right *here*.
        comparisons: List[Comparison] = []
        for (qid, target), group in per_person.items():
            person = people[qid]
            for row in group:
                recorded = [t for t in person.p39_claims if t.covers(row.start, row.end)]
                if not recorded and qid not in held_by_target.get(target, set()):
                    continue  # nothing on record to compare against
                comparisons.append(
                    compare(
                        campaign=campaign.name, office=office.key, qid=qid,
                        label=person.label, target=target,
                        row_start=row.start, row_end=row.end,
                        period_raw=row.period_raw,
                        terms=person.p39_claims,
                        acting_predicted=row.acting,
                    )
                )
        all_comparisons += comparisons
        # An office's other items, as the cohort reveals them rather than as
        # anyone declared them. Excluded: the seats whose overlap means nothing,
        # and the items another office in this campaign owns.
        owned_elsewhere = {
            qid
            for other in campaign.offices if other.key != office.key
            for qid in [other.target]
            + [q for _, q in other.section_targets]
            + [q for _, _, q in other.date_targets]
            if qid
        }
        candidates = observed_family(
            comparisons,
            exclude=list(campaign.concurrency_ignore)
            + sorted(owned_elsewhere - set(targets))
            + list(targets),
        )
        derived, not_this_office = verify_family(
            session, candidates, targets, campaign.country_qid
        )
        # An office's *era* items are siblings — Spain files one presidency of
        # the Congress across four of them, so a spell recorded on any of them
        # is this appointment already written down. Its *portfolio* items are
        # not: a bucket lane routed by `section_targets` is forty offices
        # wearing one `Office`, and treating them as one family makes every
        # portfolio a duplicate of every other. Jordan's ministers hold two at
        # once routinely — Ahmad al-Tarawneh was Justice and Education across
        # the same span — and thirteen true statements were skipped as
        # duplicates of each other before this distinction existed.
        era_siblings = [qid for _, _, qid in office.date_targets if qid]
        siblings = list(dict.fromkeys(
            ([office.target] if office.target else [])
            + era_siblings
            + [qid for qid, _ in derived]
        ))

        for (qid, target), group in per_person.items():
            person = people[qid]
            held = held_by_target.get(target, set())
            in_category = bool(person.cats)
            # Every row in the group, or the claim is not an infobox claim: a
            # person a roster names *and* their own box confirms has the two
            # channels already, and holding them to the stricter rule would
            # skip a row the roster alone would have applied.
            from_officebox = bool(group) and all(
                "officebox" in r.flags for r in group
            )
            conflict = next(
                (c for c in (lifetime_conflict(person, r.start) for r in group) if c), None
            )
            # A parenthesised year range after a name is sometimes the person's
            # lifespan rather than a term; the giveaway is a "term" starting in
            # their birth year.
            lifespan = conflict and any(
                r.start and person.birth is not None and int(r.start[:4]) == person.birth
                for r in group
            )
            ref = next((url for r in group for url in r.ref_urls), None)
            # An officebox group's source is the person's own article revision,
            # one per row rather than one per office, so it cannot come from the
            # office's roster permalink — there is no roster.
            box_source = next(
                (r.cells.get("officebox_source") for r in group
                 if r.cells.get("officebox_source")), ""
            )
            # Asked first, because it decides whether the row belongs on this
            # item at all: another item of the same office already recording
            # this spell means the appointment is written down, and every
            # question below it ("was this acting? was it cover?") is moot.
            elsewhere: Dict[int, str] = {}
            for row in group:
                other = already_under_sibling(row, person, target, siblings)
                if other:
                    elsewhere[id(row)] = other
            duplicated = [r for r in group if id(r) in elsewhere]
            acting = [r for r in group if r.acting and r not in duplicated]
            regime = [
                r for r in group
                if regime_of(r, office) and r not in acting and r not in duplicated
            ]
            flagged = [
                r for r in group
                if review_section(r, office) and r not in acting and r not in regime
                and r not in duplicated
            ]
            covers: Dict[int, str] = {}
            for row in group:
                if row in acting or row in regime or row in flagged or row in duplicated:
                    continue
                other = interim_of(row, person, target, campaign.concurrency_ignore)
                if other:
                    covers[id(row)] = other
            interim = [r for r in group if id(r) in covers]
            plain = [
                r for r in group
                if r not in acting and r not in regime and r not in flagged
                and r not in interim and r not in duplicated
            ]
            for row in group:
                if conflict:
                    statuses[id(row)] = f"review: lifetime ({conflict})"
                elif qid in held:
                    statuses[id(row)] = "already holds P39"
                elif row in duplicated:
                    statuses[id(row)] = (
                        f"skip: already recorded as {elsewhere[id(row)]}"
                    )
                elif row in acting:
                    statuses[id(row)] = "review: acting"
                elif row in regime:
                    statuses[id(row)] = f"review: {regime_of(row, office)}"
                elif row in flagged:
                    statuses[id(row)] = "review: pre-ministerial section"
                elif row in interim:
                    statuses[id(row)] = f"review: interim (covering {covers[id(row)]})"
                elif not row.start:
                    statuses[id(row)] = "review: no dates"
                elif int(row.start[:4]) < campaign.modern_from:
                    statuses[id(row)] = f"review: pre-{campaign.modern_from}"
                elif in_category:
                    statuses[id(row)] = "add"
                else:
                    statuses[id(row)] = "add (roster only)"

            def emit(
                verdict: str, era: str, terms: List[dict], evidence: str,
                notes: str, extra: Sequence[str] = (),
            ) -> None:
                records.append(
                    position_record(
                        campaign=campaign.name,
                        office=office.key,
                        qid=qid,
                        label=person.label,
                        target=target,
                        verdict=verdict,
                        era=era,
                        terms=terms,
                        evidence=evidence,
                        notes=notes,
                        source_url=ref or box_source or source,
                        source_prop="S854" if ref else "S4656",
                        identity=identity_of.get(qid, {}),
                        facts=facts,
                        overrides=campaign.dispositions,
                        in_category=in_category,
                        # Where the evidence came from is a fact about the
                        # claim, not about the row, so it has to travel with
                        # the candidate: `officebox.two_channel` is the rule
                        # that decides these, and without the flag they fall
                        # through to `modern.two_channel` and apply on the
                        # infobox alone.
                        extra_flags=tuple(extra)
                        + (("officebox",) if from_officebox else ())
                        + ((office.hold,) if office.hold else ()),
                    )
                )

            if conflict:
                emit(
                    "unclear", "lifespan_not_term" if lifespan else "lifetime_mismatch",
                    [{"start": r.start, "end": r.end} for r in group],
                    f"roster row '{group[0].name}' ({group[0].period_raw}) resolved to "
                    f"this item, but {conflict}",
                    "the bracketed years look like a lifespan, not a term"
                    if lifespan
                    else "probable namesake — the roster's person may have no item",
                )
                continue
            if qid in held:
                continue
            if plain:
                terms = merge_terms(plain)
                # A span with neither bound carries nothing, and the era below is
                # decided by the first term that *has* a start — so on a person
                # with one dated row and one undated row it rode along on the
                # dated record's verdict and shipped a bare P39 beside the real
                # one. Twenty-four of the UAE cabinet's statements were bare this
                # way, thirteen of them duplicating a dated statement for the
                # same person and office. Dropping them here keeps the promise
                # the `no_dates` branch below already makes.
                # When *every* span is undated the record still has to exist, so
                # it reaches the `no_dates` branch below and is skipped with a
                # reason rather than disappearing from the audit.
                dated = [(start, end) for start, end in terms if start or end]
                terms = dated or [(None, None)]
                spans.setdefault(target, []).extend(
                    (qid, start, end) for start, end in terms
                )
                first = next((start for start, _ in terms if start), None)
                historical = bool(first) and int(first[:4]) < campaign.modern_from
                if first is None:
                    # No date anywhere in the roster row: the office claim may
                    # be sound, but an undated P39 is not what this batch ships.
                    era = "no_dates"
                elif historical:
                    era = "historical" if in_category else "historical_roster_only"
                else:
                    era = "modern" if in_category else "roster_only"
                already = coincides_with(
                    terms, person, target, campaign.generic_targets
                )
                emit(
                    "add", era,
                    [{"start": start, "end": end} for start, end in terms],
                    # An officebox claim comes from the person's own article, so
                    # naming a roster page — or "?" where there is none — says
                    # nothing about where the evidence was read.
                    (f"their own {'/'.join(office.officebox)}.wikipedia "
                     f"infobox states this office, "
                     if from_officebox else
                     f"'{office.rosters[0].page if office.rosters else '?'}' "
                     f"{campaign.evidence_verb} ")
                    + f"{'; '.join(r.period_raw for r in plain)}"
                    + (f", appointed by {plain[0].appointer}" if plain[0].appointer else "")
                    + (f"; category: {', '.join(person.cats)}" if in_category
                       else "; NOT in any category — roster wikilink only")
                    + (f"; but {already} already covers exactly these dates"
                       if already else ""),
                    f"existing P39s: {', '.join(person.p39) or 'none'}",
                    extra=("duplicate_appointment",) if already else (),
                )
            for row in duplicated:
                emit(
                    "unclear", "duplicate_office_item",
                    [{"start": row.start, "end": row.end}],
                    f"roster lists them {row.period_raw}, and {elsewhere[id(row)]} "
                    "— another item for this same office — already records that "
                    "spell",
                    "one office with two items; the statement exists already",
                    extra=(era_flag(row.start, campaign.modern_from),),
                )
            for row in acting:
                emit(
                    "unclear", "acting",
                    [{"start": row.start, "end": row.end}],
                    f"roster marks this spell acting: {row.period_raw} "
                    f"({'; '.join(row.flags)})",
                    "acting — recorded as the office plus P2868",
                    extra=(era_flag(row.start, campaign.modern_from),),
                )
            for row in regime:
                emit(
                    "unclear", regime_of(row, office) or "other_regime",
                    [{"start": row.start, "end": row.end}],
                    f"roster section '{row.section}': {row.period_raw}",
                    "a different polity's office — needs its own item",
                    extra=(era_flag(row.start, campaign.modern_from),),
                )
            for row in flagged:
                emit(
                    "unclear", "predecessor_body",
                    [{"start": row.start, "end": row.end}],
                    f"roster section '{row.section}': {row.period_raw}",
                    "filed under a pre-ministerial body — same office?",
                    extra=(era_flag(row.start, campaign.modern_from),),
                )
            for row in interim:
                emit(
                    "unclear", "interim_concurrent_office",
                    [{"start": row.start, "end": row.end}],
                    f"roster lists them {row.period_raw}, but that whole spell "
                    f"falls inside their existing term as {covers[id(row)]}",
                    "covering a second portfolio — recorded as the office "
                    "plus P2868",
                    extra=(era_flag(row.start, campaign.modern_from),),
                )

        scores.append(backtest_score(office.label, comparisons, family=siblings))
        audit.append(f"## {office.label} → {', '.join(dict.fromkeys(targets))}")
        audit.append(
            f"{sum(1 for p in people.values() if p.cats)} category members · "
            f"{len(rows)} roster rows · "
            f"{sum(len(h) for h in held_by_target.values())} existing holders · "
            f"{len(comparisons)} already on record · "
            f"roster {source or 'NONE'}"
        )
        if derived:
            # Printed because a wrong derivation suppresses real statements, and
            # the only way that becomes visible is if the audit says which items
            # the cohort was read as using for this office.
            audit.append(
                "* undeclared items the cohort also uses for this office, now "
                "treated as siblings: "
                + ", ".join(f"{qid} ×{n}" for qid, n in derived)
            )
        if not_this_office:
            audit.append(
                "* items the cohort uses alongside this office but **not** "
                "treated as siblings — declare them in the profile if any is "
                "the same office: " + "; ".join(not_this_office)
            )
        for target_qid, target_spans in sorted(spans.items()):
            for warning in overlaps(target_spans):
                audit.append(f"* ⚠ date overlap on {target_qid}: {warning}")
        for warning in short_spells(records):
            audit.append(f"* ⚠ short spell: {warning}")
        if skipped:
            audit.append(
                "* tables/pages not counted as this office (sibling offices, "
                f"predecessor agencies, each its own item): {'; '.join(skipped)}"
            )
        audit.append("")
        audit.append("| roster row | dates | identified as | how | status |")
        audit.append("|---|---|---|---|---|")
        for row, qid, how in row_status:
            if qid:
                person = people[qid]
                if len(held_by_target) > 1:
                    how = f"{how} → {target_for(row, office)}"
                who = (
                    f"{qid} {person.label} — {person.description or 'no description'}"
                    f" [{', '.join(person.cats) or 'not in category'}]"
                )
                status = statuses.get(id(row), "?")
            else:
                who, status = "—", "no identity"
            totals[status] += 1
            audit.append(f"| {row.name} | {row.period_raw} | {who} | {how} | {status} |")

        matched = {qid for qid, _ in per_person}
        for qid, person in sorted(people.items()):
            if qid in matched or qid in held_by_target[office.target] or not person.cats:
                continue
            era = person.regime or "category_only"
            totals[f"review: {era}"] += 1
            audit.append(
                f"| — (absent from roster) | — | {qid} {person.label} — "
                f"{person.description or 'no description'} [{', '.join(person.cats)}] "
                f"| category | review: {era} |"
            )
            records.append(
                position_record(
                    campaign=campaign.name, office=office.key, qid=qid,
                    label=person.label, target=office.target,
                    verdict="unclear", era=era, terms=[],
                    evidence=f"in {', '.join(person.cats)} but named by no roster row",
                    notes=(
                        f"existing P39s: {', '.join(person.p39) or 'none'} — rosters "
                        "often start at a constitutional break, so earlier holders "
                        "land here"
                    ),
                    source_url=source, source_prop="S4656",
                    identity={"method": "category"},
                    facts=facts, overrides=campaign.dispositions,
                    in_category=True,
                )
            )
        audit.append("")

        records += party_records(
            session, campaign, office, per_person, people, lang, source
        )
        records += family_records(campaign, office, per_person, people, source)

        path = verdict_dir / f"{campaign.name}_{office.key}.jsonl"
        path.write_text(dumps(records))
        decisions += [(r.decision.rule, r.decision.action) for r in records]
        adds = Counter(
            r.decision.rule for r in records
            if r.decision.action in ("apply", "hold")
        )
        print(
            f"{office.label:<28} {len(rows):>3} rows → {adds['modern']:>3} batch, "
            f"{adds['roster_only']:>3} roster-only, "
            f"{adds['historical'] + adds['historical_roster_only']:>3} pre-{campaign.modern_from}, "
            f"{sum(1 for r in records if r.decision.action == 'review'):>3} review"
        )

    # Which files this campaign owns — every office, not just the ones this
    # invocation ran. Renaming an office key otherwise strands its old verdict
    # file in a directory the renderer reads by glob, and it goes on being
    # rendered forever: Ecuador carried 96 records from a superseded
    # `minister_gobierno.jsonl` for a day before anyone noticed.
    expected = sorted(
        [f"{campaign.name}_{o.key}.jsonl" for o in campaign.offices]
        + list(campaign.extra_verdicts)
    )
    (verdict_dir / "manifest.json").write_text(
        json.dumps({"campaign": campaign.name, "files": expected}, indent=2) + "\n"
    )
    orphans = sorted(
        p.name for p in verdict_dir.glob("*.jsonl") if p.name not in expected
    )
    if orphans:
        print(f"\n! verdict files not owned by this campaign: {', '.join(orphans)}")
        print("  (a renamed office key? they will still be read by the renderer)")

    # How the engine scores against the statements that already exist. Inserted
    # above the census for the same reason the census is printed at all, and
    # first because it is the only section that says whether the run can be
    # believed: a target agreement below ~90% means the office is a family of
    # items and the routing is guessing.
    dump_comparisons(all_comparisons, out_dir / "backtest.jsonl")
    backtest_lines = backtest_report(scores, all_comparisons)
    if backtest_lines:
        audit.insert(4, "")
        audit.insert(4, "\n".join(backtest_lines))

    # The census, and what it says about each target's own convention. Printed
    # whether or not a rule reads it yet: a rule that flips a decision on a
    # measurement has to show its working.
    census_lines = report(precedents, {t: campaign.modern_from for t in all_targets})
    if census_lines:
        audit.insert(4, "")
        audit.insert(4, "\n".join(f"* {line}" for line in census_lines))
        audit.insert(4, f"## Precedent census (cutoff {campaign.modern_from})")

    # What the policy did, as policy — the summary a reviewer reads instead of
    # three hundred rows.
    summary = tally(decisions)
    audit.insert(4, "")
    audit.insert(4, "\n".join(f"* `{rule}` — {n}" for rule, n in summary.items()))
    audit.insert(4, "## Decisions by rule")

    (out_dir / "roster_audit.md").write_text("\n".join(audit) + "\n")
    print(f"\nby rule: {summary}")
    print(f"\n{dict(totals)}")
    for item in scores:
        if not item.rows:
            continue
        print(
            f"backtest {item.office:<28} {item.rows:>4} on record · "
            f"target {_rate(item.target_rate)} · date {_rate(item.date_rate)} · "
            f"acting {_rate(item.acting_rate)} · {item.disjoint} unrecorded spells"
        )
    print(f"Wrote {out_dir / 'roster_audit.md'}")


def _rate(value: Optional[float]) -> str:
    return " n/a" if value is None else f"{value * 100:3.0f}%"
