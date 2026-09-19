"""Turn one person's extraction into `proposal` rows with a status.

Values are stored in Wikidata's own datavalue shape, so the renderer and a
later API writer read them unchanged. The status is a comparison against the
item's non-deprecated claims, recorded together with the revision it was
computed against: it is a snapshot for `stats`, never a licence to write.

Round 1 proposes the flat fields only. `positions` and `birth_places` stay in
`extraction.response_json` until reconciliation can give them QIDs.
"""

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from psycopg.types.json import Jsonb
from rigour.territories import get_territory_by_qid, lookup_territory

from peploop import db, wikidata

CALENDAR = "http://www.wikidata.org/entity/Q1985727"
GENDER_QIDS = {"male": "Q6581097", "female": "Q6581072"}
DATE_PRECISION = {4: 9, 7: 10, 10: 11}
TIME_RE = re.compile(r"^([+-]?\d+)-(\d{2})-(\d{2})")
# Worst first: several existing claims make a proposal `conflict` only when
# none of them matches it.
STATUS_RANK = ("exists", "refine", "new", "conflict", "unresolved")
# Only these can be true once, so only here does a differing value contradict
# the record: a Czechoslovak citizenship beside a Czech one is an addition.
SINGLE_VALUED = frozenset({"P569", "P570", "P21", "P19"})

LABEL_PREFIX = "label:"
ALIAS_PREFIX = "alias:"


@dataclass
class Proposal:
    """One value peploop would add to one item, before it is stored."""

    property: str
    value: dict[str, Any]
    status: str
    qualifiers: dict[str, Any] | None = None
    quote: str | None = None
    lang: str | None = None


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


def _at(text: str, precision: int) -> str | None:
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
        if _at(text, shared) != _at(value["time"], shared):
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


def _territory_qids(qid: str) -> set[str]:
    territory = get_territory_by_qid(qid)
    return set(territory.qids) if territory is not None else {qid}


def _dates(entity: dict[str, Any], data: dict[str, Any], key: str, prop: str) -> list[Proposal]:
    out = []
    existing = wikidata.claim_time(entity, prop, include_deprecated=False)
    for entry in data.get(key) or []:
        value = time_value(entry["value"])
        if value is None:
            continue
        quotes = entry.get("quotes") or []
        out.append(
            Proposal(
                property=prop,
                value=value,
                status=time_status(existing, value),
                quote=quotes[0] if quotes else None,
                lang=entry.get("lang"),
            )
        )
    return out


def _gender(entity: dict[str, Any], data: dict[str, Any]) -> list[Proposal]:
    value = data.get("gender")
    if value is None:
        return []
    quotes = data.get("gender_quotes") or []
    proposal = Proposal(
        property="P21",
        value={},
        status="unresolved",
        qualifiers={"_raw": value},
        quote=quotes[0] if quotes else None,
        lang=data.get("gender_lang"),
    )
    qid = GENDER_QIDS.get(value)
    if qid is not None:
        existing = [{q} for q in wikidata.claim_qids(entity, "P21", include_deprecated=False)]
        proposal.value = {"entity-type": "item", "id": qid}
        proposal.status = item_status(existing, {qid}, "P21")
        proposal.qualifiers = None
    return [proposal]


def _citizenships(entity: dict[str, Any], data: dict[str, Any]) -> list[Proposal]:
    existing = [
        _territory_qids(q)
        for q in wikidata.claim_qids(entity, "P27", include_deprecated=False)
    ]
    out = []
    for entry in data.get("citizenships") or []:
        quotes = entry.get("quotes") or []
        qualifiers: dict[str, Any] = {"_basis": entry.get("basis")}
        for prop, key in (("P580", "start"), ("P582", "end")):
            bound = time_value(entry.get(key) or "")
            if bound is not None:
                qualifiers[prop] = bound
        territory = lookup_territory(entry["name"])
        proposal = Proposal(
            property="P27",
            value={},
            status="unresolved",
            qualifiers={**qualifiers, "_name": entry["name"]},
            quote=quotes[0] if quotes else None,
            lang=entry.get("lang"),
        )
        if territory is not None and territory.qid:
            proposal.value = {"entity-type": "item", "id": territory.qid}
            proposal.status = item_status(existing, set(territory.qids), "P27")
            proposal.qualifiers = qualifiers
        out.append(proposal)
    return out


def _names(entity: dict[str, Any], data: dict[str, Any]) -> list[Proposal]:
    """Propose labels and aliases under the pseudo-properties `label:` and `alias:`.

    Wikidata terms are not statements and have no property of their own, so a
    language code carries the slot they belong to instead.
    """
    labels = {lang: term["value"] for lang, term in entity.get("labels", {}).items()}
    aliases = {
        lang: {term["value"] for term in terms}
        for lang, terms in entity.get("aliases", {}).items()
    }
    out = []
    for entry in data.get("names") or []:
        lang = entry.get("lang") or "und"
        unresolved = lang == "und"
        label = (entry.get("label") or "").strip()
        if label:
            taken = lang in labels or label == labels.get("mul")
            out.append(
                Proposal(
                    property=f"{LABEL_PREFIX}{lang}",
                    value={"language": lang, "text": label},
                    status="unresolved" if unresolved else ("exists" if taken else "new"),
                    lang=lang,
                )
            )
        for alias in entry.get("aliases") or []:
            alias = alias.strip()
            if not alias:
                continue
            taken = alias in aliases.get(lang, set()) or alias in (
                labels.get(lang),
                labels.get("mul"),
            )
            out.append(
                Proposal(
                    property=f"{ALIAS_PREFIX}{lang}",
                    value={"language": lang, "text": alias},
                    status="unresolved" if unresolved else ("exists" if taken else "new"),
                    lang=lang,
                )
            )
    return out


def build(entity: dict[str, Any], data: dict[str, Any]) -> list[Proposal]:
    """Turn one extraction's answer into the proposals it implies."""
    proposals = _dates(entity, data, "birth_date", "P569")
    proposals.extend(_dates(entity, data, "death_date", "P570"))
    proposals.extend(_gender(entity, data))
    proposals.extend(_citizenships(entity, data))
    proposals.extend(_names(entity, data))
    return proposals


def _sources(qid: str) -> dict[str, tuple[str, int | None]]:
    rows = db.conn().execute("SELECT lang, url, rev_id FROM article WHERE qid = %s", (qid,))
    return {lang: (url, rev_id) for lang, url, rev_id in rows}


def _key(prop: str, value: dict[str, Any]) -> str:
    return prop + "\t" + json.dumps(value, sort_keys=True, ensure_ascii=False)


def _store(
    qid: str, proposals: list[Proposal], extraction_id: int, item_rev: int | None
) -> tuple[Counter[tuple[str, str]], int]:
    """Replace this person's proposals, keeping the ones a human has ruled on.

    A verdict is the only thing in the table that a re-run cannot reproduce,
    so rows carrying one survive and the proposal that would duplicate them is
    not inserted again.
    """
    conn = db.conn()
    counts: Counter[tuple[str, str]] = Counter()
    sources = _sources(qid)
    with conn.transaction():
        judged = conn.execute(
            "SELECT p.id, p.property, p.value FROM proposal p"
            " WHERE p.person_qid = %s AND EXISTS (SELECT 1 FROM verdict v WHERE"
            " v.proposal_id = p.id)",
            (qid,),
        ).fetchall()
        kept = {_key(prop, value) for _, prop, value in judged}
        conn.execute(
            "DELETE FROM proposal WHERE person_qid = %s AND NOT (id = ANY(%s))",
            (qid, [row[0] for row in judged]),
        )
        for proposal in proposals:
            if _key(proposal.property, proposal.value) in kept:
                continue
            url, rev = sources.get(proposal.lang or "", (None, None))
            conn.execute(
                "INSERT INTO proposal (person_qid, property, value, qualifiers, quote,"
                " source_lang, source_url, source_rev, extraction_id, item_rev, status)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    qid,
                    proposal.property,
                    Jsonb(proposal.value),
                    Jsonb(proposal.qualifiers) if proposal.qualifiers else None,
                    proposal.quote,
                    proposal.lang,
                    url,
                    rev,
                    extraction_id,
                    item_rev,
                    proposal.status,
                ),
            )
            counts[(proposal.property, proposal.status)] += 1
    return counts, len(judged)


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
    proposals = [] if summary.person_status == "not_human" else build(entity, data)
    summary.counts, summary.kept = _store(qid, proposals, extraction_id, item_rev)
    db.set_person_status(qid, summary.person_status)
    return summary
