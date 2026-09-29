"""Turn one person's extraction into `proposal` rows with a status.

Values are stored in Wikidata's own datavalue shape, so the renderer and a
later API writer read them unchanged. The status is a comparison against the
item's non-deprecated claims, recorded together with the revision it was
computed against: it is a snapshot for `stats`, never a licence to write.

`positions` become `P39` once reconciliation has given them a QID; the ones it
refused stay in `extraction.response_json` as the creation queue. `birth_places`
still wait for a reconciler of their own.
"""

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from psycopg.types.json import Jsonb
from rigour.territories import get_territory_by_qid, lookup_territory
from rigour.text.scripts import text_scripts

from peploop import db, scope, wikidata

CALENDAR = "http://www.wikidata.org/entity/Q1985727"
GENDER_QIDS = {"male": "Q6581097", "female": "Q6581072"}
DATE_PRECISION = {4: 9, 7: 10, 10: 11}
TIME_RE = re.compile(r"^([+-]?\d+)-(\d{2})-(\d{2})")
# Worst first: several dates already on the item make a proposed one
# `conflict` only when none of them matches it.
STATUS_RANK = ("exists", "refine", "new", "conflict", "unresolved")
# What `extract.py` files the quotes it could not find in the article text under.
BAD_QUOTES = "_bad_quotes"
# Only these can be true once, so only here does a differing value contradict
# the record: a citizenship of a predecessor state beside its successor is an
# addition.
SINGLE_VALUED = frozenset({"P569", "P570", "P21", "P19"})

LABEL_PREFIX = "label:"
ALIAS_PREFIX = "alias:"
# A value a mechanical rule threw out before a human could see it. The rule
# that did so is in `qualifiers._reason`, so each one's volume is countable.
FILTERED = "filtered"
# A tenure the item already records for the same office, dated a few days
# differently. Inert like `FILTERED` -- in neither `review.REVIEWABLE` nor
# `render.WRITABLE` -- and the spell it clashed with is in `qualifiers._reason`.
OVERLAPPING = "overlapping"
PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
# How much of an article says which scripts its language is written in. The
# lead is enough, and a whole article is mostly its own name in any case.
SCRIPT_SAMPLE = 2000
# Strongest first, for a value several articles attest on different grounds.
BASIS_RANK = ("explicit", "demonym")


@dataclass
class Source:
    """One article a value was read in, and the sentence that carried it."""

    lang: str | None
    quote: str | None


@dataclass
class Proposal:
    """One value peploop would add to one item, before it is stored."""

    property: str
    value: dict[str, Any]
    status: str
    qualifiers: dict[str, Any] | None = None
    quote: str | None = None
    lang: str | None = None
    #: The `resolution` row that placed a P39 on its item; null on anything else.
    resolution_id: int | None = None
    # Every article that attested this value. One proposal per value and not
    # per article, because the same citizenship in three languages is one
    # statement with three references, not three rows for one reviewer.
    sources: list[Source] = field(default_factory=list)


@dataclass
class ProposeSummary:
    """What `propose_person` did, for the run's per-person line."""

    qid: str
    label: str | None
    person_status: str
    extraction_id: int | None = None
    counts: Counter[tuple[str, str]] = field(default_factory=Counter)
    kept: int = 0
    positions: int = 0
    birth_places: int = 0

    @property
    def written(self) -> int:
        """Count the proposal rows this call inserted."""
        return sum(self.counts.values())


def time_value(text: str) -> dict[str, Any] | None:
    """Render a `YYYY`, `YYYY-MM` or `YYYY-MM-DD` string as a Wikidata time.

    Unknown month and day are padded with `00`, as Wikidata itself stores
    them; the precision is what says how much of the value to read.
    """
    precision = DATE_PRECISION.get(len(text))
    if precision is None:
        return None
    padded = (text + "-00-00")[:10]
    return {
        "time": f"+{padded}T00:00:00Z",
        "precision": precision,
        "calendarmodel": CALENDAR,
        "timezone": 0,
        "before": 0,
        "after": 0,
    }


def at_precision(text: str, precision: int) -> str | None:
    """Truncate a time value to a precision, so two dates compare like for like."""
    match = TIME_RE.match(text)
    if match is None:
        return None
    year, month, day = match.groups()
    if precision >= 11:
        return f"{year}-{month}-{day}"
    if precision == 10:
        return f"{year}-{month}"
    if precision == 9:
        return year
    scale = 10 ** (9 - precision)
    return str(int(year) // scale * scale)


def time_status(existing: list[tuple[str, int]], value: dict[str, Any]) -> str:
    """Decide what a proposed date adds to the dates already on the item."""
    if not existing:
        return "new"
    verdicts = []
    for text, precision in existing:
        shared = min(precision, value["precision"])
        if at_precision(text, shared) != at_precision(value["time"], shared):
            verdicts.append("conflict")
        elif precision >= value["precision"]:
            verdicts.append("exists")
        else:
            verdicts.append("refine")
    return min(verdicts, key=STATUS_RANK.index)


def item_status(existing: list[set[str]], proposed: set[str], prop: str) -> str:
    """Decide what a proposed item value adds, comparing whole QID families.

    Each side is a set because `rigour` folds predecessor states into their
    successor: an item carrying `Q713750` West Germany already covers a
    proposed `Q183` Germany. A value matching none of the existing ones is a
    second value, and only a `SINGLE_VALUED` property reads that as a conflict.
    """
    if not existing:
        return "new"
    if any(group & proposed for group in existing):
        return "exists"
    return "conflict" if prop in SINGLE_VALUED else "new"


def quote_status(status: str, quotes: list[str], bad: set[str]) -> str:
    """Downgrade a status to `unquoted` when no quote behind it survived the gate.

    `extract.py` already decided which quotes it could not find in the text
    that was sent; this only matches those strings back to the entry that
    carried them. A value whose every quote is paraphrase or fabrication has no
    evidence left, whatever the comparison against Wikidata says about it --
    and neither has one the model quoted nothing for at all.
    """
    if not quotes or all(quote in bad for quote in quotes):
        return "unquoted"
    return status


def _territory_qids(qid: str) -> set[str]:
    territory = get_territory_by_qid(qid)
    return set(territory.qids) if territory is not None else {qid}


def attestations(entries: list[dict[str, Any]]) -> list[Source]:
    """List one source per language that attested a value, with its first quote."""
    seen: dict[str, Source] = {}
    for entry in entries:
        lang = entry.get("lang")
        quotes = entry.get("quotes") or []
        seen.setdefault(lang or "", Source(lang, quotes[0] if quotes else None))
    return list(seen.values())


def group_dates(entries: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Cluster the date entries that say the same thing, finest value first.

    Two articles giving `1962` and `1962-02-06` are one date one of them knows
    more exactly, not two candidate values; two giving different days are two
    rows and a reviewer's decision. The values are `YYYY[-MM[-DD]]` strings, so
    agreement at the precision they share is a prefix comparison.
    """
    groups: list[list[dict[str, Any]]] = []
    for entry in sorted(entries, key=lambda e: -len(e["value"])):
        for group in groups:
            shared = min(len(group[0]["value"]), len(entry["value"]))
            if group[0]["value"][:shared] == entry["value"][:shared]:
                group.append(entry)
                break
        else:
            groups.append([entry])
    return groups


def _dates(
    entity: dict[str, Any], data: dict[str, Any], key: str, prop: str, bad: set[str]
) -> list[Proposal]:
    out = []
    existing = wikidata.claim_time(entity, prop, include_deprecated=False)
    entries = [e for e in data.get(key) or [] if time_value(e["value"]) is not None]
    for group in group_dates(entries):
        value = time_value(group[0]["value"])
        if value is None:
            continue
        quotes = [quote for entry in group for quote in entry.get("quotes") or []]
        out.append(
            Proposal(
                property=prop,
                value=value,
                status=quote_status(time_status(existing, value), quotes, bad),
                quote=quotes[0] if quotes else None,
                lang=group[0].get("lang"),
                sources=attestations(group),
            )
        )
    return out


def _gender(entity: dict[str, Any], data: dict[str, Any], bad: set[str]) -> list[Proposal]:
    value = data.get("gender")
    if value is None:
        return []
    quotes = data.get("gender_quotes") or []
    proposal = Proposal(
        property="P21",
        value={},
        status=quote_status("unresolved", quotes, bad),
        qualifiers={"_raw": value},
        quote=quotes[0] if quotes else None,
        lang=data.get("gender_lang"),
        sources=attestations([{"lang": data.get("gender_lang"), "quotes": quotes}]),
    )
    qid = GENDER_QIDS.get(value)
    if qid is not None:
        existing = [{q} for q in wikidata.claim_qids(entity, "P21", include_deprecated=False)]
        proposal.value = {"entity-type": "item", "id": qid}
        proposal.status = quote_status(item_status(existing, {qid}, "P21"), quotes, bad)
        proposal.qualifiers = None
    return [proposal]


def strongest_basis(entries: list[dict[str, Any]]) -> str | None:
    """Return the best grounds any article gave for a citizenship."""
    found = [entry.get("basis") for entry in entries if entry.get("basis")]
    for basis in BASIS_RANK:
        if basis in found:
            return basis
    return found[0] if found else None


def _citizenship(existing: list[set[str]], entries: list[dict[str, Any]], bad: set[str]) -> Proposal:
    """Turn every article that named one country into the one proposal for it.

    An undated citizenship of a state that no longer exists is filtered: it is
    what a lead sentence about somebody's origins reads as, and beside the
    successor state the item already records it adds nothing a reviewer wants.
    Wikidata models a citizenship that ended with `P582`, so the dated case is
    a real addition and stays.
    """
    quotes = [quote for entry in entries for quote in entry.get("quotes") or []]
    qualifiers: dict[str, Any] = {"_basis": strongest_basis(entries)}
    for prop, key in (("P580", "start"), ("P582", "end")):
        for entry in entries:
            bound = time_value(entry.get(key) or "")
            if bound is not None:
                qualifiers[prop] = bound
                break
    territory = lookup_territory(entries[0]["name"])
    proposal = Proposal(
        property="P27",
        value={},
        status=quote_status("unresolved", quotes, bad),
        qualifiers={**qualifiers, "_name": entries[0]["name"]},
        quote=quotes[0] if quotes else None,
        lang=entries[0].get("lang"),
        sources=attestations(entries),
    )
    if territory is None or not territory.qid:
        return proposal
    proposal.value = {"entity-type": "item", "id": territory.qid}
    proposal.qualifiers = qualifiers
    dated = "P580" in qualifiers or "P582" in qualifiers
    if territory.is_historical and not dated:
        proposal.status = FILTERED
        proposal.qualifiers = {**qualifiers, "_reason": "undated_predecessor"}
        return proposal
    proposal.status = quote_status(
        item_status(existing, set(territory.qids), "P27"), quotes, bad
    )
    return proposal


def _citizenships(entity: dict[str, Any], data: dict[str, Any], bad: set[str]) -> list[Proposal]:
    existing = [
        _territory_qids(q)
        for q in wikidata.claim_qids(entity, "P27", include_deprecated=False)
    ]
    groups: dict[str, list[dict[str, Any]]] = {}
    for entry in data.get("citizenships") or []:
        territory = lookup_territory(entry["name"])
        key = territory.qid if territory is not None and territory.qid else entry["name"]
        groups.setdefault(key, []).append(entry)
    return [_citizenship(existing, entries, bad) for entries in groups.values()]


def normalise(text: str) -> str:
    """Fold a name to what makes two spellings of it the same form.

    Case, punctuation and runs of whitespace are what a label and an alias of
    it differ by while naming the same person, so an academic title written
    with and without its commas compares equal.
    """
    return " ".join(PUNCT_RE.sub(" ", text).casefold().split())


def item_terms(entity: dict[str, Any]) -> dict[str, list[str]]:
    """Map each language to the item's label there, then its aliases."""
    terms: dict[str, list[str]] = {}
    for lang, term in (entity.get("labels") or {}).items():
        terms.setdefault(lang, []).append(term["value"])
    for lang, group in (entity.get("aliases") or {}).items():
        terms.setdefault(lang, []).extend(term["value"] for term in group)
    return terms


def expected_scripts(lang: str, terms: dict[str, list[str]], articles: dict[str, str]) -> set[str]:
    """Derive the scripts a language is written in, from what the run holds.

    The item's own terms in that language first, because they are what the
    community settled on for this person; failing those, the opening of the
    article in that language. Nothing to read from is no expectation and no
    check, which is the honest answer for a language we hold nothing in.
    """
    for sample in (" ".join(terms.get(lang) or []), (articles.get(lang) or "")[:SCRIPT_SAMPLE]):
        found = set(text_scripts(sample))
        if found:
            return found
    return set()


def wrong_script(text: str, expected: set[str]) -> str | None:
    """Name the expected scripts when a form is not written in any of them.

    Only the Latin boundary is decided, because that is the one a set derived
    from a couple of names can carry: a language written in no Latin script
    does not take a Latin-script name, and one written only in Latin does not
    take a name in another script.
    """
    if not expected:
        return None
    found = set(text_scripts(text))
    detail = "script:" + "+".join(sorted(expected))
    if "Latin" not in expected and "Latin" in found:
        return detail
    if expected == {"Latin"} and found - {"Latin"}:
        return detail
    return None


def is_fragment(text: str, lang: str, terms: dict[str, list[str]]) -> bool:
    """Say whether a form is part of the person's label rather than a name for them.

    A surname or a given name on its own, which is what an infobox row or a
    later mention of the person in the article reads as. The label of the
    language the form is proposed for answers it, falling back to the ones
    every language can see. A one-word pen name is not in the label and passes.
    """
    for code in (lang, "mul", "en"):
        label = (terms.get(code) or [""])[0]
        if label:
            tokens = set(normalise(text).split())
            return bool(tokens) and tokens < set(normalise(label).split())
    return False


def name_status(
    text: str,
    lang: str,
    prefix: str,
    labelled: set[str],
    terms: dict[str, list[str]],
    recorded: set[str],
    expected: set[str],
) -> tuple[str, str | None]:
    """Decide what one name form is, and name the rule that decided it.

    In this order: a language already labelled takes no second label, a literal
    the item carries in *any* language is not another language's to add, an
    alias that is only part of the label is a fragment, and a form in a script
    the language is not written in belongs to whichever language it is written
    in, not to this one.
    """
    if lang == "und":
        return "unresolved", None
    if prefix == LABEL_PREFIX and lang in labelled:
        return "exists", None
    if normalise(text) in recorded:
        return "exists", None
    if prefix == ALIAS_PREFIX and is_fragment(text, lang, terms):
        return FILTERED, "fragment"
    reason = wrong_script(text, expected)
    if reason is not None:
        return FILTERED, reason
    return "new", None


def _names(
    entity: dict[str, Any], data: dict[str, Any], articles: dict[str, str]
) -> list[Proposal]:
    """Propose labels and aliases under the pseudo-properties `label:` and `alias:`.

    Wikidata terms are not statements and have no property of their own, so a
    language code carries the slot they belong to instead.
    """
    terms = item_terms(entity)
    labelled = set(entity.get("labels") or {})
    recorded = {normalise(term) for group in terms.values() for term in group}
    scripts: dict[str, set[str]] = {}
    out = []
    for entry in data.get("names") or []:
        lang = entry.get("lang") or "und"
        forms = [(LABEL_PREFIX, entry.get("label") or "")]
        forms.extend((ALIAS_PREFIX, alias) for alias in entry.get("aliases") or [])
        for prefix, raw in forms:
            text = raw.strip()
            if not text:
                continue
            if lang not in scripts:
                scripts[lang] = expected_scripts(lang, terms, articles)
            status, reason = name_status(
                text, lang, prefix, labelled, terms, recorded, scripts[lang]
            )
            out.append(
                Proposal(
                    property=f"{prefix}{lang}",
                    value={"language": lang, "text": text},
                    status=status,
                    qualifiers={"_reason": reason} if reason else None,
                    lang=lang,
                )
            )
    return out


SPAN = (("start", "P580"), ("end", "P582"))


def span_of(claim: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Read a P39 statement's start and end qualifiers as time values."""
    found: dict[str, dict[str, Any]] = {}
    for _key, prop in SPAN:
        for snak in (claim.get("qualifiers") or {}).get(prop, []):
            value = snak.get("datavalue", {}).get("value")
            if isinstance(value, dict) and "time" in value:
                found[prop] = value
                break
    return found


def held(entity: dict[str, Any], qid: str) -> list[dict[str, dict[str, Any]]]:
    """List the spans of every non-deprecated P39 statement naming one office.

    Every rank is read but the deprecated ones: a preferred statement hides the
    normal-rank ones from a truthy read, and a second term is normal-rank.
    """
    spans = []
    for claim in entity.get("claims", {}).get("P39", []):
        if claim.get("rank") == "deprecated":
            continue
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(value, dict) and value.get("id") == qid:
            spans.append(span_of(claim))
    return spans


#: A tenure widened to the days it could cover, each side None when unbounded.
Extent = tuple[scope.Point | None, scope.Point | None]


def extent(span: dict[str, Any]) -> Extent | None:
    """The first and last day a tenure could cover, or None if it says nothing.

    Reach for this before comparing one tenure with another, because neither
    endpoint is the point it looks like. An absent endpoint is unbounded: a
    statement with a start and no end is a tenure still running, which is what
    Wikidata means by leaving `P582` off. An endpoint too coarse or too odd to
    place is unbounded on its side too, since a date nobody can read rules
    nothing out. The widening itself is `scope.interval`, which already knows
    that a decade is stored as the year it opens and a century as the year it
    closes.
    """
    if not span:
        return None
    bounds: list[scope.Point | None] = []
    for prop, side in (("P580", 0), ("P582", 1)):
        value = span.get(prop)
        placed = (
            None if value is None
            else scope.interval(value["time"], value.get("precision", 0))
        )
        bounds.append(None if placed is None else placed[side])
    return bounds[0], bounds[1]


def overlaps(one: dict[str, Any], other: dict[str, Any]) -> bool:
    """Say whether two tenures of one office can be the same appointment.

    An office has one holder at a time, so two overlapping spells of it are one
    appointment written down twice -- the reasoning `wd/campaign.py`'s
    `already_under_sibling` applies to a roster row against a sibling item.
    Both bounds are days a tenure could still cover, so touching counts; a
    tenure saying nothing overlaps nothing, having no span to intersect.
    """
    first, second = extent(one), extent(other)
    if first is None or second is None:
        return False
    starts_before_other_ends = first[0] is None or second[1] is None or first[0] <= second[1]
    ends_after_other_starts = first[1] is None or second[0] is None or second[0] <= first[1]
    return starts_before_other_ends and ends_after_other_starts


def clashing(
    spans: list[dict[str, dict[str, Any]]], span: dict[str, Any]
) -> dict[str, dict[str, Any]] | None:
    """The recorded spell a proposed tenure is a second writing-down of, if any.

    A proposal carrying no dates clashes with any dated statement for the
    office: it rules nothing out, so it cannot be a *further* term, and the
    item already says more about the office than the proposal does. It is only
    a refinement where what is recorded is itself undated.
    """
    for recorded in spans:
        if not recorded:
            continue
        if not span or overlaps(span, recorded):
            return recorded
    return None


def span_text(span: dict[str, dict[str, Any]]) -> str:
    """Name a spell the way a reviewer reads it, an open side left blank.

    Wikidata signs every year and a reader does not, so the `+` goes and the
    `-` of a BCE year stays.
    """
    bounds = []
    for prop in ("P580", "P582"):
        value = span.get(prop)
        text = None if value is None else at_precision(value["time"], value["precision"])
        bounds.append((text or "").lstrip("+"))
    return "..".join(bounds)


def tenure_status(spans: list[dict[str, dict[str, Any]]], span: dict[str, Any]) -> str:
    """Decide what a proposed tenure adds to the ones the item already records.

    An office has one holder at a time, so a proposal overlapping a spell the
    item already records for the *same* office is that one appointment written
    down twice, dated a few days apart. It is set aside as `OVERLAPPING`, which
    forfeits nothing: `apply` sees the office value already on the item and
    drops the proposal's dates anyway. Only the same office is asked -- a
    tenure overlapping a *different* office is a minister keeping their
    parliamentary seat, and legitimate.

    The clash test runs first, and the order carries the rule: whether the
    tenure is already recorded decides whether it belongs on the item at all,
    and only what survives that is asked what kind of tenure it was. So a
    recorded statement carrying no dates blocks nothing -- it is the thing the
    proposal exists to sharpen, and yields `refine` -- while a spell no
    recorded statement covers is a further term of the office and is `new`.
    """
    if not spans:
        return "new"
    if clashing(spans, span) is not None:
        return OVERLAPPING
    if any(not recorded for recorded in spans):
        return "refine"
    return "new"


def tenure_key(qid: str, span: dict[str, Any]) -> tuple[str, str, str]:
    """Identify one tenure, so the same spell named in two languages is one row."""
    return (
        qid,
        span.get("P580", {}).get("time", "")[:5],
        span.get("P582", {}).get("time", "")[:5],
    )


def _positions(
    entity: dict[str, Any], data: dict[str, Any],
    resolved: dict[int, tuple[str, int]], bad: set[str],
) -> list[Proposal]:
    """Propose a P39 for every office mention reconciliation placed on an item.

    `resolved` maps a mention's index to the item it was placed on and the
    verdict that placed it, and holds
    only the mentions that cleared the reconciler's own gate -- so nothing is
    judged again here. An acting tenure is kept out: Wikidata says "acting"
    with a qualifier this pipeline does not yet write, and a P39 that omits it
    asserts more than the article did.
    """
    out: dict[tuple[str, str, str], Proposal] = {}
    for index, entry in enumerate(data.get("positions") or []):
        placed = resolved.get(index)
        if placed is None:
            continue
        qid, resolution_id = placed
        span = {}
        for key, prop in SPAN:
            value = time_value(entry.get(key) or "")
            if value is not None:
                span[prop] = value
        quotes = entry.get("quotes") or []
        # Both deliberate non-proposals name the rule that decided them, so
        # each one's volume stays countable from the table alone.
        qualifiers: dict[str, Any] = dict(span)
        if entry.get("acting"):
            status = FILTERED
            qualifiers["_reason"] = "acting"
        else:
            recorded = held(entity, qid)
            status = quote_status(tenure_status(recorded, span), quotes, bad)
            if status == OVERLAPPING:
                qualifiers["_reason"] = f"overlaps {span_text(clashing(recorded, span) or {})}"
        key = tenure_key(qid, span)
        existing = out.get(key)
        if existing is not None:
            # The same spell read in a second language: one statement with two
            # references, not two rows asking a reviewer the same question.
            existing.sources.extend(attestations([entry]))
            continue
        out[key] = Proposal(
            property="P39",
            value={"entity-type": "item", "id": qid},
            status=status,
            qualifiers=qualifiers or None,
            quote=quotes[0] if quotes else None,
            lang=entry.get("lang"),
            resolution_id=resolution_id,
            sources=attestations([entry]),
        )
    return list(out.values())


def build(
    entity: dict[str, Any], data: dict[str, Any], articles: dict[str, str] | None = None,
    resolved: dict[int, tuple[str, int]] | None = None,
) -> list[Proposal]:
    """Turn one extraction's answer into the proposals it implies.

    Name forms carry no quotes and so are never `unquoted`: a label is read off
    the article's own title and lead, not asserted by a sentence in it. The
    article texts are what the script gate falls back to for a language the
    item carries no name in; without them that gate simply does not fire.
    """
    bad = set(data.get(BAD_QUOTES) or [])
    proposals = _dates(entity, data, "birth_date", "P569", bad)
    proposals.extend(_dates(entity, data, "death_date", "P570", bad))
    proposals.extend(_gender(entity, data, bad))
    proposals.extend(_citizenships(entity, data, bad))
    proposals.extend(_names(entity, data, articles or {}))
    proposals.extend(_positions(entity, data, resolved or {}, bad))
    return proposals


def article_urls(qid: str) -> dict[str, tuple[str, int | None]]:
    """Map each language to the URL and revision of the article read in it."""
    rows = db.conn().execute("SELECT lang, url, rev_id FROM article WHERE qid = %s", (qid,))
    return {lang: (url, rev_id) for lang, url, rev_id in rows}


def article_texts(qid: str) -> dict[str, str]:
    """Map each language to as much of its article as the script gate reads."""
    rows = db.conn().execute(
        "SELECT lang, left(text, %s) FROM article WHERE qid = %s", (SCRIPT_SAMPLE, qid)
    )
    return dict(rows)


def value_key(prop: str, value: dict[str, Any]) -> str:
    """Identify one (property, value) pair, for matching proposals across runs."""
    return prop + "\t" + json.dumps(value, sort_keys=True, ensure_ascii=False)


def proposal_key(prop: str, value: dict[str, Any], qualifiers: dict[str, Any] | None) -> str:
    """Identify one proposal by its value *and* its qualifiers.

    The value alone stopped identifying a proposal the day two spells of one
    office became two statements: keyed on it, a person's second term was
    never inserted once their first carried a verdict. Only the qualifiers
    that reach Wikidata count; peploop's own `_` keys are bookkeeping.
    """
    real = {k: v for k, v in (qualifiers or {}).items() if k.startswith("P")}
    return value_key(prop, value) + "\t" + json.dumps(real, sort_keys=True, ensure_ascii=False)


#: A row `propose` may not replace: it records something a re-run cannot
#: reproduce -- a human's ruling, or an edit that has already reached Wikidata.
KEPT_STATUSES = ("applied",)


def _store(
    qid: str, proposals: list[Proposal], extraction_id: int, item_rev: int | None
) -> tuple[Counter[tuple[str, str]], int]:
    """Replace this person's proposals, keeping what a re-run cannot reproduce.

    A human's verdict and a written edit are the two things in the table that
    are not derived from the extraction, so rows carrying either survive and
    the proposal that would duplicate them is not inserted again. Everything
    else -- including what the policy decided last time -- is re-derived, and
    the policy runs again after; that is what makes a rule change one command.
    """
    conn = db.conn()
    counts: Counter[tuple[str, str]] = Counter()
    urls = article_urls(qid)
    with conn.transaction():
        judged = conn.execute(
            "SELECT p.id, p.property, p.value, p.qualifiers FROM proposal p"
            " WHERE p.person_qid = %s AND (p.status = ANY(%s) OR EXISTS ("
            " SELECT 1 FROM verdict v WHERE v.proposal_id = p.id))",
            (qid, list(KEPT_STATUSES)),
        ).fetchall()
        kept = {proposal_key(prop, value, quals) for _, prop, value, quals in judged}
        conn.execute(
            "DELETE FROM proposal WHERE person_qid = %s AND NOT (id = ANY(%s))",
            (qid, [row[0] for row in judged]),
        )
        for proposal in proposals:
            if proposal_key(proposal.property, proposal.value, proposal.qualifiers) in kept:
                continue
            url, rev = urls.get(proposal.lang or "", (None, None))
            qualifiers = dict(proposal.qualifiers or {})
            if proposal.sources:
                qualifiers["_sources"] = [
                    {
                        "lang": source.lang,
                        "url": urls.get(source.lang or "", (None, None))[0],
                        "rev": urls.get(source.lang or "", (None, None))[1],
                        "quote": source.quote,
                    }
                    for source in proposal.sources
                ]
            conn.execute(
                "INSERT INTO proposal (person_qid, property, value, qualifiers, quote,"
                " source_lang, source_url, source_rev, extraction_id, item_rev, status,"
                " resolution_id)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    qid,
                    proposal.property,
                    Jsonb(proposal.value),
                    Jsonb(qualifiers) if qualifiers else None,
                    proposal.quote,
                    proposal.lang,
                    url,
                    rev,
                    extraction_id,
                    item_rev,
                    proposal.status,
                    proposal.resolution_id,
                ),
            )
            counts[(proposal.property, proposal.status)] += 1
    return counts, len(judged)


def placements(extraction_id: int) -> dict[int, tuple[str, int]]:
    """Map each placed mention of an extraction to its item and its verdict row.

    Only the rows the reconciler resolved: a null `qid` is a refusal or a veto,
    and belongs in the creation queue rather than on anybody's item. A prompt
    edit re-asks, so the newest verdict per mention is the one that counts.

    **Newest first, then drop the refusals** -- in that order, and the order is
    the whole point. Filtering the nulls inside the same query picks the newest
    verdict *that matched*, so a mention a new prompt refuses quietly keeps the
    old prompt's match and the re-ask changes nothing. Measured: a rule that
    dropped 200 placements from one item left 226 proposals standing on it.
    """
    rows = db.conn().execute(
        "SELECT mention_idx, qid, id FROM ("
        "  SELECT DISTINCT ON (mention_idx) mention_idx, qid, id FROM resolution"
        "  WHERE extraction_id = %s ORDER BY mention_idx, id DESC"
        ") newest WHERE qid IS NOT NULL",
        (extraction_id,),
    )
    return {index: (qid, row_id) for index, qid, row_id in rows}


def propose_person(qid: str) -> ProposeSummary:
    """Propose everything this person's latest extraction says, and store it.

    A person the model read as not human produces no proposals at all: their
    extraction says nothing that could be trusted about anyone.
    """
    row = db.conn().execute(
        "SELECT id, response_json FROM extraction WHERE qid = %s ORDER BY id DESC LIMIT 1",
        (qid,),
    ).fetchone()
    if row is None:
        raise LookupError(f"no extraction stored for {qid}")
    extraction_id, data = row
    item = db.conn().execute(
        "SELECT lastrevid, json FROM item WHERE qid = %s", (qid,)
    ).fetchone()
    if item is None:
        raise LookupError(f"no item stored for {qid}")
    item_rev, entity = item
    summary = ProposeSummary(
        qid=qid,
        label=wikidata.best_label(entity),
        person_status="proposed",
        extraction_id=extraction_id,
        positions=len(data.get("positions") or []),
        birth_places=len(data.get("birth_places") or []),
    )
    if not data.get("is_human", True):
        summary.person_status = "not_human"
    proposals = (
        []
        if summary.person_status == "not_human"
        else build(entity, data, article_texts(qid), placements(extraction_id))
    )
    summary.counts, summary.kept = _store(qid, proposals, extraction_id, item_rev)
    db.set_person_status(qid, summary.person_status)
    return summary
