"""Turn one person's extraction into `proposal` rows with a status.

Values are stored in Wikidata's own datavalue shape, so the plan and the
verifier read them unchanged. The status is a comparison against the item's
non-deprecated claims, recorded together with the revision it was computed
against: it is a snapshot for `report`, never a licence to write.

`positions` become `P39` once reconciliation has given them a QID; the ones it
refused stay in `extraction.response_json` as the creation queue. `birth_places`
still wait for a reconciler of their own.
"""

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from psycopg.types.json import Jsonb
from rigour.territories import get_territory_by_qid, lookup_territory

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

# A value a mechanical rule threw out before a human could see it. The rule
# that did so is in `qualifiers._reason`, so each one's volume is countable.
FILTERED = "filtered"
# A tenure the item already records for the same office, dated a few days
# differently. Inert like `FILTERED` -- in no status the policy decides -- and
# the spell it clashed with is in `qualifiers._reason`.
OVERLAPPING = "overlapping"
# Strongest first, for a value several articles attest on different grounds.
BASIS_RANK = ("explicit", "demonym")
# Community names `rigour` reads as a state, which stay unresolved.
NOT_A_STATE = frozenset(
    line.strip().casefold()
    for line in (Path(__file__).resolve().parent / "not_a_state.txt").read_text().splitlines()
    if line.strip() and not line.startswith("#")
)


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


def citizenship_territory(name: str) -> Any:
    """Find the state a citizenship name means, or None for a community name."""
    if name.strip().casefold() in NOT_A_STATE:
        return None
    return lookup_territory(name)


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
    territory = citizenship_territory(entries[0]["name"])
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
        territory = citizenship_territory(entry["name"])
        key = territory.qid if territory is not None and territory.qid else entry["name"]
        groups.setdefault(key, []).append(entry)
    return [_citizenship(existing, entries, bad) for entries in groups.values()]


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
    appointment written down twice. Both bounds are days a tenure could still cover, so touching counts; a
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


def closes(recorded: dict[str, Any], span: dict[str, Any], today: date) -> bool:
    """Whether a proposed spell gives the end a recorded open term is missing.

    The same start at the precision both share, an end the record has none
    of, and that end neither before the start nor after today -- a planned
    end is a schedule, not a record.
    """
    start, mine, end = recorded.get("P580"), span.get("P580"), span.get("P582")
    if "P582" in recorded or start is None or mine is None or end is None:
        return False
    shared = min(start.get("precision", 11), mine.get("precision", 11))
    if at_precision(start["time"], shared) != at_precision(mine["time"], shared):
        return False
    shared = min(end.get("precision", 11), mine.get("precision", 11))
    if (at_precision(end["time"], shared) or "") < (at_precision(mine["time"], shared) or ""):
        return False
    return end["time"][1:11] <= today.isoformat()


def tenure_status(
    spans: list[dict[str, dict[str, Any]]], span: dict[str, Any], today: date | None = None,
) -> str:
    """Decide what a proposed tenure adds to the ones the item already records.

    An office has one holder at a time, so a proposal overlapping a spell the
    item already records for the *same* office is that one appointment written
    down twice, dated a few days apart, and is set aside as `OVERLAPPING`.
    Only the same office is asked -- a
    tenure overlapping a *different* office is a minister keeping their
    parliamentary seat, and legitimate.

    The clash test runs first, and the order carries the rule: whether the
    tenure is already recorded decides whether it belongs on the item at all,
    and only what survives that is asked what kind of tenure it was. So a
    recorded statement carrying no dates blocks nothing -- it is the thing the
    proposal exists to sharpen, and yields `refine` -- while a spell no
    recorded statement covers is a further term of the office and is `new`.

    One clash is not a second writing-down but the end the record is missing:
    a recorded open term with the same start, at the precision both share,
    and a proposal that closes it on or before today. That is `refine`, and
    the plan merges the `P582` into the statement that is there.
    """
    if not spans:
        return "new"
    if any(closes(recorded, span, today or date.today()) for recorded in spans):
        return "refine"
    if clashing(spans, span) is not None:
        return OVERLAPPING
    if any(not recorded for recorded in spans):
        return "refine"
    return "new"


def same_span(one: dict[str, Any], other: dict[str, Any]) -> bool:
    """Whether two spans agree on both endpoints at the precision each pair shares."""
    for _key, prop in SPAN:
        a, b = one.get(prop), other.get(prop)
        if a is None or b is None:
            continue
        shared = min(a.get("precision", 11), b.get("precision", 11))
        if at_precision(a["time"], shared) != at_precision(b["time"], shared):
            return False
    return True


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
            # Dates that differ within the year are two spells, or one wiki's
            # error; either way no source is cited against its own value.
            if not same_span(existing.qualifiers or {}, span) and existing.status != FILTERED:
                existing.status = FILTERED
                existing.qualifiers = {**(existing.qualifiers or {}), "_reason": "sources_disagree"}
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
    entity: dict[str, Any], data: dict[str, Any],
    resolved: dict[int, tuple[str, int]] | None = None,
) -> list[Proposal]:
    """Turn one extraction's answer into the proposals it implies.

    The extraction still carries the names it read; they are not proposed.
    Labels and aliases were a lane of their own until the policy threw every
    row of it away -- 13 of the 19 a human reviewed were titles or fragments.
    """
    bad = set(data.get(BAD_QUOTES) or [])
    proposals = _dates(entity, data, "birth_date", "P569", bad)
    proposals.extend(_dates(entity, data, "death_date", "P570", bad))
    proposals.extend(_gender(entity, data, bad))
    proposals.extend(_citizenships(entity, data, bad))
    proposals.extend(_positions(entity, data, resolved or {}, bad))
    return proposals


def article_urls(qid: str) -> dict[str, tuple[str, int | None]]:
    """Map each language to the URL and revision of the article read in it."""
    rows = db.conn().execute("SELECT lang, url, rev_id FROM article WHERE qid = %s", (qid,))
    return {lang: (url, rev_id) for lang, url, rev_id in rows}


def value_key(prop: str, value: dict[str, Any]) -> str:
    """Identify one (property, value) pair, for matching proposals across runs."""
    return prop + "\t" + json.dumps(value, sort_keys=True, ensure_ascii=False)


def proposal_key(prop: str, value: dict[str, Any], qualifiers: dict[str, Any] | None) -> str:
    """Identify one proposal by its value *and* its qualifiers.

    Two spells of one office are two statements, so the value alone would
    let a person's second term go uninserted once their first carried a
    verdict. Only the qualifiers
    that reach Wikidata count; peploop's own `_` keys are bookkeeping.
    """
    real = {k: v for k, v in (qualifiers or {}).items() if k.startswith("P")}
    return value_key(prop, value) + "\t" + json.dumps(real, sort_keys=True, ensure_ascii=False)


#: A row `propose` may not replace: it records something a re-run cannot
#: reproduce -- a human's ruling, or an edit that has gone out (`sent`), landed
#: (`applied`) or failed and is not sent again on its own.
KEPT_STATUSES = ("applied", "sent", "failed")
#: The provenance prefix of a row the plan closed without a line to send.
PLAN_DECIDED = "plan:"


def plan_decision_holds(entity: dict[str, Any] | None, row: dict[str, Any]) -> bool:
    """Whether a row the plan closed would be closed the same way against this item.

    The plan reads things `propose` does not -- a tenure statement carrying a
    term and no dates (`termed`), a single-valued property already holding
    another value (`conflict`), a merge QuickStatements cannot aim
    (`ambiguous-statement`) -- so a row it closed would come back from a
    re-propose as `accepted` until the next send closed it again. The decision is kept for as long as it still holds: the item's
    stored record is planned against again, and only a row that now routes to
    the same non-writing route stays closed. With no record to plan against,
    nothing is kept.
    """
    from peploop import plan  # plan imports propose

    route = (row.get("decided_by") or "")[len(PLAN_DECIDED):]
    if not route or entity is None:
        return False
    planned, statement = plan.plan_claim(entity, row)
    return statement is None and planned == route


def _store(
    qid: str, proposals: list[Proposal], extraction_id: int, item_rev: int | None,
    entity: dict[str, Any] | None = None,
) -> tuple[Counter[tuple[str, str]], int]:
    """Replace this person's proposals, keeping what a re-run cannot reproduce.

    A human's verdict and a written edit are the two things in the table that
    are not derived from the extraction, so rows carrying either survive and
    the proposal that would duplicate them is not inserted again. So does a
    row the plan closed against the live item, while `entity` -- the item as
    last stored -- still closes it (`plan_decision_holds`). Everything
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
        closed = conn.execute(
            "SELECT p.id, p.property, p.value, p.qualifiers, p.source_lang, p.source_url,"
            " p.source_rev, p.decided_by FROM proposal p WHERE p.person_qid = %s"
            " AND p.status = 'skipped' AND p.decided_by LIKE %s AND NOT EXISTS ("
            " SELECT 1 FROM verdict v WHERE v.proposal_id = p.id)",
            (qid, PLAN_DECIDED + "%"),
        ).fetchall()
        columns = ("id", "property", "value", "qualifiers", "source_lang", "source_url",
                   "source_rev", "decided_by")
        judged += [tuple(row[:4]) for row in closed
                   if plan_decision_holds(entity, dict(zip(columns, row)))]
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
        else build(entity, data, placements(extraction_id))
    )
    summary.counts, summary.kept = _store(qid, proposals, extraction_id, item_rev, entity)
    db.set_person_status(qid, summary.person_status)
    return summary
