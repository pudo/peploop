"""Plan what one person's accepted proposals do to their live item.

Nothing here trusts a stored status: each row is planned against the item as
it is now, because a status was decided against `item_rev` and the item --
including by our own earlier writes -- may have moved since. The plan is what
`send` renders as QuickStatements, and the routes that write nothing (a value
already there, a conflict, a statement QuickStatements cannot single out) are
dispositions recorded against the row.

The reference shape is `P143` the wiki it was imported from, `P4656` the
permanent URL of the revision read, `P813` today.
"""

import datetime
import json
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from peploop import db, policy, propose, wikidata, wikipedia

PROPERTY_NAMES = wikidata.PROPERTY_NAMES
# A reference built only from these says "imported from a Wikipedia article",
# which is the one provenance a refinement may overwrite in place.
IMPORT_PROPS = wikidata.IMPORT_PROPS

@dataclass
class Plan:
    """One person's whole edit, before it is sent."""

    qid: str
    data: dict[str, Any] = field(default_factory=dict)
    summary: str = ""
    skipped: list[tuple[int, str]] = field(default_factory=list)
    routes: Counter[str] = field(default_factory=Counter)
    # The proposal ids behind each statement of `data`, in the same order.
    members: list[list[int]] = field(default_factory=list)



def today() -> dict[str, Any]:
    """Render today as the day-precision time value P813 takes."""
    stamp = datetime.datetime.now(tz=datetime.timezone.utc).strftime("%Y-%m-%d")
    return {
        "time": f"+{stamp}T00:00:00Z",
        "precision": 11,
        "calendarmodel": propose.CALENDAR,
        "timezone": 0,
        "before": 0,
        "after": 0,
    }




def _snak(prop: str, value: dict[str, Any] | str) -> dict[str, Any]:
    if isinstance(value, str):
        datavalue = {"value": value, "type": "string"}
    elif "time" in value:
        datavalue = {"value": value, "type": "time"}
    elif "id" in value:
        datavalue = {"value": value, "type": "wikibase-entityid"}
    else:
        raise ValueError(f"no snak shape for {value}")
    return {"snaktype": "value", "property": prop, "datavalue": datavalue}


def reference(lang: str | None, url: str | None, rev: int | None) -> dict[str, Any] | None:
    """Build the three-snak reference that says where a value was read.

    A language whose Wikipedia has no item on Wikidata still gets a reference:
    the import URL and the retrieval date are the load-bearing halves.
    """
    snaks: dict[str, list[dict[str, Any]]] = {}
    wiki = wikipedia.edition_qid(lang) if lang else None
    if wiki is not None:
        snaks["P143"] = [_snak("P143", {"entity-type": "item", "id": wiki})]
    if url:
        snaks["P4656"] = [_snak("P4656", wikipedia.revision_url(url, rev))]
    if not snaks:
        return None
    snaks["P813"] = [_snak("P813", today())]
    return {"snaks": snaks, "snaks-order": list(snaks)}


def row_sources(row: dict[str, Any]) -> list[dict[str, Any]]:
    """List the articles one proposal was read in, newest shape first.

    `propose` writes every attesting article into `_sources`, because a value
    three wikis agree on is one statement with three references. A row stored
    before that grouping carries its one source in its own columns.
    """
    stored = (row.get("qualifiers") or {}).get("_sources")
    if stored:
        return list(stored)
    return [
        {
            "lang": row.get("source_lang"),
            "url": row.get("source_url"),
            "rev": row.get("source_rev"),
        }
    ]


def references(row: dict[str, Any]) -> list[dict[str, Any]]:
    """Build one reference per article a proposal's value was read in."""
    built = [
        reference(source.get("lang"), source.get("url"), source.get("rev"))
        for source in row_sources(row)
    ]
    return [ref for ref in built if ref is not None]


def same_value(existing: dict[str, Any], proposed: dict[str, Any]) -> bool:
    """Say whether two datavalues name the same thing, dates at shared precision."""
    if "time" in proposed and "time" in existing:
        shared = min(existing.get("precision", 11), proposed["precision"])
        return propose.at_precision(existing["time"], shared) == propose.at_precision(
            proposed["time"], shared
        )
    if "id" in proposed:
        return existing.get("id") == proposed["id"]
    return existing == proposed


is_import = wikidata.is_import


def _qualifiers(row: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Take the real qualifiers off a proposal, dropping peploop's own `_` keys."""
    snaks: dict[str, list[dict[str, Any]]] = {}
    for prop, value in (row.get("qualifiers") or {}).items():
        if prop.startswith("P"):
            snaks[prop] = [_snak(prop, value)]
    return snaks, list(snaks)


def _with_qualifiers(claim: dict[str, Any], qualifiers: dict[str, Any]) -> dict[str, Any]:
    """Add qualifiers to a claim, keeping the ones it already carries."""
    if not qualifiers:
        return claim
    merged = {**(claim.get("qualifiers") or {}), **qualifiers}
    claim["qualifiers"] = merged
    claim["qualifiers-order"] = list(merged)
    return claim


def addable_qualifiers(
    claim: dict[str, Any], qualifiers: dict[str, Any]
) -> dict[str, Any] | None:
    """The proposed qualifiers a claim carries none of, or None if it carries any.

    Purely additive, and the guard is what makes it so: a claim already saying
    when a tenure began is not one this may re-date. The plan keeps the live
    claim with these merged in, and `route.render` sends only the difference.
    """
    present = claim.get("qualifiers") or {}
    if any(prop in present for prop in qualifiers):
        return None
    return {prop: snaks for prop, snaks in qualifiers.items() if prop not in present}


#: The route of a refinement QuickStatements cannot aim: the statement it would
#: change is not the only one holding its value, and QS3 changes the *first*
#: such statement, by value -- it cannot be pointed at a GUID.
AMBIGUOUS = "ambiguous-statement"


def exact(a: Any, b: Any) -> bool:
    """Say whether two datavalues are the same to QuickStatements: a date at the same precision too."""
    if isinstance(a, dict) and isinstance(b, dict):
        if "id" in a or "id" in b:
            return a.get("id") == b.get("id")
        if "time" in a or "time" in b:
            return (a.get("time"), a.get("precision"), a.get("calendarmodel", propose.CALENDAR)) == (
                b.get("time"), b.get("precision"), b.get("calendarmodel", propose.CALENDAR))
    return a == b


def holding(entity: dict[str, Any], prop: str, value: Any) -> int:
    """How many statements of any rank hold exactly this value: what a QuickStatements merge chooses among."""
    return sum(
        1 for claim in entity.get("claims", {}).get(prop, [])
        if exact(claim.get("mainsnak", {}).get("datavalue", {}).get("value"), value)
    )


def plan_claim(entity: dict[str, Any], row: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
    """Decide what one statement proposal does to the live item.

    Contradiction is ruled out first, and over every statement rather than the
    one that happens to match: a person with a year-precision 1950 *and* a
    day-precision 1 March 1950 is not someone our 1 February 1950 refines, even
    though it agrees with the coarse one at the precision they share. Then a
    value already recorded as finely writes nothing, a coarser one that is only
    a Wikipedia import is ours to sharpen in place, a coarser one somebody else
    sourced gets ours beside it as preferred, and anything left is new.

    A refinement is only planned where QuickStatements can make it: sharpening
    a date in place needs the old value on exactly one statement and the new
    one on none, and merging into a statement needs its value on that one
    alone. Otherwise the route is `ambiguous-statement` and nothing is written.
    """
    prop, value = row["property"], row["value"]
    existing = [
        (claim, claim.get("mainsnak", {}).get("datavalue", {}).get("value"))
        for claim in entity.get("claims", {}).get(prop, [])
        if claim.get("rank") != "deprecated"
    ]
    # A `somevalue` snak records that nobody knows, and contradicts nothing.
    values = [(claim, found) for claim, found in existing if isinstance(found, dict)]
    matching = [(claim, found) for claim, found in values if same_value(found, value)]
    if prop in propose.SINGLE_VALUED and len(matching) < len(values):
        return "conflict", None
    refs = references(row)
    qualifiers, order = _qualifiers(row)
    if "id" in value and propose.span_of({"qualifiers": qualifiers}):
        return plan_tenure(prop, value, matching, qualifiers, order, refs, row,
                           unique=holding(entity, prop, value) == 1)
    superseding = False
    # An undated statement first, so a tenure the item records twice is sharpened
    # on the copy that says nothing rather than on one that already has dates.
    for claim, found in sorted(matching, key=lambda pair: len(pair[0].get("qualifiers") or {})):
        sharper = "time" in value and found.get("precision", 11) < value["precision"]
        if sharper and is_import(claim):
            if holding(entity, prop, found) != 1 or holding(entity, prop, value):
                return AMBIGUOUS, None
            refined = dict(claim)
            refined["mainsnak"] = _snak(prop, value)
            refined["references"] = [*(claim.get("references") or []), *refs]
            return "refine", _with_qualifiers(refined, qualifiers)
        if sharper:
            # Somebody else's sourcing on a coarser value: ours goes beside it,
            # outranking it rather than replacing it.
            superseding = True
            continue
        # The value is already recorded. That is the end of it for a date, but
        # not for a tenure: an office the item names without saying when is what
        # the article's dates are for, and adding them is a *merge* into the
        # statement that is there, never a second one beside it.
        added = addable_qualifiers(claim, qualifiers)
        if not added:
            return "exists", None
        if holding(entity, prop, found) != 1:
            return AMBIGUOUS, None
        refined = dict(claim)
        refined["references"] = [*(claim.get("references") or []), *refs]
        return "refine", _with_qualifiers(refined, added)
    route = "preferred" if superseding else "new"
    rank = "preferred" if superseding else "normal"
    return route, _statement(prop, value, qualifiers, order, refs, rank)


def _statement(
    prop: str, value: dict[str, Any], qualifiers: dict[str, Any], order: list[str],
    refs: list[dict[str, Any]], rank: str = "normal",
) -> dict[str, Any]:
    """A new statement, in Wikidata's JSON shape: what `route.render` turns into a `+` line."""
    statement: dict[str, Any] = {"type": "statement", "rank": rank, "mainsnak": _snak(prop, value)}
    if qualifiers:
        statement["qualifiers"] = qualifiers
        statement["qualifiers-order"] = order
    if refs:
        statement["references"] = refs
    return statement


#: What a term item (a legislature's convocation) spans, by QID: its own
#: start and end, read live once per run. Replaced in checks.
_TERM_SPANS: dict[str, dict[str, dict[str, Any]]] = {}


def term_span(qid: str) -> dict[str, dict[str, Any]]:
    """The span of a term item, from its P580/P582 or else its P571/P576."""
    if qid not in _TERM_SPANS:
        entity = wikidata.fetch_items([qid], props="claims").get(qid) or {}
        span: dict[str, dict[str, Any]] = {}
        for into, props in (("P580", ("P580", "P571")), ("P582", ("P582", "P576"))):
            for prop in props:
                found = wikidata.claim_time(entity, prop, include_deprecated=False)
                if found:
                    time_, precision = found[0]
                    span[into] = {"time": time_, "precision": precision}
                    break
        if "P582" not in span:
            # A convocation often records no end of its own, only its
            # successor, whose start is that end.
            for prop in ("P156", "P1366"):
                nxt = next(iter(wikidata.claim_qids(entity, prop, include_deprecated=False)), None)
                if nxt:
                    successor = wikidata.fetch_items([nxt], props="claims").get(nxt) or {}
                    found = (wikidata.claim_time(successor, "P580", include_deprecated=False)
                             or wikidata.claim_time(successor, "P571", include_deprecated=False))
                    if found:
                        span["P582"] = {"time": found[0][0], "precision": found[0][1]}
                        break
        _TERM_SPANS[qid] = span
    return _TERM_SPANS[qid]


def _term_excludes(claim: dict[str, Any], proposed: dict[str, Any]) -> bool:
    """Does the statement's term qualifier rule out the proposed spell?

    A seat recorded for the 12th Parliament is not the 13th Parliament's seat
    the article now dates: four sitting members were left unwritten because
    their previous term's statement was read as covering the new one. Only a
    term whose own dates are known and miss the spell rules it out.
    """
    terms = [snak.get("datavalue", {}).get("value", {}).get("id")
             for snak in (claim.get("qualifiers") or {}).get("P2937", [])]
    spans = [term_span(q) for q in terms if q]
    return bool(spans) and all(s and not propose.overlaps(proposed, s) for s in spans)


def plan_tenure(
    prop: str, value: dict[str, Any], matching: list[tuple[dict[str, Any], Any]],
    qualifiers: dict[str, Any], order: list[str], refs: list[dict[str, Any]],
    row: dict[str, Any], unique: bool = True,
) -> tuple[str, dict[str, Any] | None]:
    """Decide what one dated spell of an office does to the statements for it.

    An office is held more than once, so the value alone does not say which
    statement a spell is about: matched on it, a legislator's second term read
    as "already recorded" and was never written. A spell is judged against the
    statements it *overlaps*, the way `propose.tenure_status` judges it. One it
    overlaps is the same appointment: if the record lacks an endpoint the
    article gives and agrees on the one they share, that endpoint is merged in;
    otherwise nothing is touched, a near miss being nobody's to re-date. A
    statement carrying no dates at all is what the dates are for, and takes
    them whole -- unless it carries a term or a district, in which case it is a
    specific tenure nobody can date-check, and nothing is written (`termed`).
    A spell overlapping nothing is a further term, and new. Either merge needs
    the office on that one statement alone (`unique`), or QuickStatements
    cannot aim it: `ambiguous-statement`.
    """
    proposed = propose.span_of({"qualifiers": qualifiers})
    undated = None
    termed = False
    for claim, _found in matching:
        recorded = propose.span_of(claim)
        if not recorded:
            # An undated statement that still carries qualifiers -- a term, a
            # district, an ordinal -- is a specific tenure the article's dates
            # may or may not be about, not a blank to fill: a councillor's
            # "periods 2003-2012" was measured stretching one term's statement
            # over three.
            if claim.get("qualifiers"):
                termed = termed or not _term_excludes(claim, proposed)
            else:
                undated = undated or claim
            continue
        if not propose.overlaps(proposed, recorded):
            continue
        for endpoint in ("P580", "P582"):
            if endpoint in proposed and endpoint in recorded and not same_value(
                recorded[endpoint], proposed[endpoint]
            ):
                return "exists", None
        present = claim.get("qualifiers") or {}
        missing = {p: snaks for p, snaks in qualifiers.items() if p not in present}
        if not missing:
            return "exists", None
        if not unique:
            return AMBIGUOUS, None
        refined = dict(claim)
        refined["references"] = [*(claim.get("references") or []), *refs]
        return "refine", _with_qualifiers(refined, missing)
    if undated is not None:
        if not unique:
            return AMBIGUOUS, None
        refined = dict(undated)
        refined["references"] = [*(undated.get("references") or []), *refs]
        return "refine", _with_qualifiers(refined, qualifiers)
    if termed:
        return "termed", None
    return "new", _statement(prop, value, qualifiers, order, refs)


def _summary(rows: list[dict[str, Any]], claims: int) -> str:
    """Name what the edit changes and which article revisions say so."""
    parts = []
    for prop in dict.fromkeys(row["property"] for row in rows):
        parts.append(PROPERTY_NAMES.get(prop, prop))
    sources = {}
    for row in rows:
        for source in row_sources(row):
            if source.get("lang") and source.get("rev"):
                sources[f"{source['lang']}.wikipedia"] = source["rev"]
    where = ", ".join(f"{site} (rev {rev})" for site, rev in sorted(sources.items()))
    head = f"peploop: add {', '.join(parts) or f'{claims} statements'}"
    return f"{head} from {where}" if where else head


def _qualifier_fingerprint(qualifiers: dict[str, Any] | None) -> str:
    """Render a statement's qualifier values, so two spells can be told apart."""
    return json.dumps(
        {
            prop: [snak.get("datavalue", {}).get("value") for snak in snaks]
            for prop, snaks in (qualifiers or {}).items()
        },
        sort_keys=True,
        ensure_ascii=False,
    )


def _statement_key(prop: str, statement: dict[str, Any]) -> str:
    """Identify the statement a row lands on, so two rows cannot both create it.

    A `+` line de-duplicates nothing, so the same citizenship attested in two
    languages would otherwise go out as two identical statements. They are the same
    statement with two references, and that is what this collapses them into.

    **The qualifiers are part of the identity.** Keyed on the value alone, a
    person's two spells in one office are one statement and the second one's
    dates are dropped in silence. A plain QuickStatements line collapses them
    the same way, which is why a new statement goes out as a `+` line.
    """
    guid = statement.get("id")
    if guid:
        return guid
    value = statement["mainsnak"]["datavalue"]["value"]
    return "\t".join((
        prop,
        json.dumps(value, sort_keys=True, ensure_ascii=False),
        _qualifier_fingerprint(statement.get("qualifiers")),
    ))


def _further_term(row: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """A row's proposal as a statement of its own, beside whatever the item holds."""
    qualifiers, order = _qualifiers(row)
    return "new", _statement(row["property"], row["value"], qualifiers, order, references(row))


def plan_person(qid: str, entity: dict[str, Any], rows: list[dict[str, Any]]) -> Plan:
    """Turn one person's accepted proposals into the edit they imply.

    Rows attesting the same thing from two wikis become one statement with two
    references, and both are recorded as applied against the one it produced.
    """
    plan = Plan(qid=qid)
    statements: dict[str, dict[str, Any]] = {}
    members: dict[str, list[int]] = {}
    written: list[dict[str, Any]] = []
    for row in rows:
        route, statement = plan_claim(entity, row)
        if statement is None:
            plan.routes[route] += 1
            plan.skipped.append((row["id"], route))
            continue
        key = _statement_key(row["property"], statement)
        already = statements.get(key)
        if already is not None and route == "refine" and _qualifier_fingerprint(
            already.get("qualifiers")
        ) != _qualifier_fingerprint(statement.get("qualifiers")):
            # A second spell landing on the one undated statement a sibling has
            # just taken: once that edit is in, the statement carries the
            # sibling's dates and this spell overlaps nothing, so it is a
            # further term. Folded in as references it would be lost, and
            # recorded as applied.
            route, statement = _further_term(row)
            key = _statement_key(row["property"], statement)
            already = statements.get(key)
        if already is None:
            statements[key] = statement
            members[key] = []
            plan.routes[route] += 1
        else:
            already.setdefault("references", []).extend(statement.get("references") or [])
            plan.routes["merged"] += 1
        members[key].append(row["id"])
        written.append(row)
    if statements:
        plan.data["claims"] = list(statements.values())
        plan.members = list(members.values())
    plan.summary = _summary(written, len(statements))
    return plan


def accepted_rows(qid: str) -> list[dict[str, Any]]:
    """Read one person's accepted proposals, oldest first."""
    columns = (
        "id",
        "property",
        "value",
        "qualifiers",
        "source_lang",
        "source_url",
        "source_rev",
        "item_rev",
    )
    rows = db.conn().execute(
        f"SELECT {', '.join(columns)} FROM proposal WHERE person_qid = %s"
        " AND status = 'accepted' ORDER BY id",
        (qid,),
    )
    return [dict(zip(columns, row)) for row in rows]


def people(qids: list[str], country: str | None = None) -> list[str]:
    """Pick the people to write: the named ones, or those with accepted rows."""
    if qids:
        return qids
    rows = db.conn().execute(
        "SELECT DISTINCT p.person_qid FROM proposal p JOIN person pe ON pe.qid = p.person_qid"
        " WHERE p.status = 'accepted' AND (%s::text IS NULL OR pe.country = %s)"
        " ORDER BY p.person_qid",
        (country, country),
    )
    return [row[0] for row in rows]


def preflight(qid: str) -> tuple[dict[str, Any], list[dict[str, Any]], bool]:
    """Read the live item and the proposals to write against it.

    The stored rows were decided against `item_rev`; an item that moved since
    is re-proposed before anything is planned, because the revision that moved
    it may well have been one of ours.
    """
    entities = wikidata.fetch_items([qid])
    entity = entities.get(qid)
    if entity is None:
        raise RuntimeError(f"{qid} is missing or deleted")
    db.upsert_item(qid, entity.get("lastrevid"), entity)
    rows = accepted_rows(qid)
    moved = any(row["item_rev"] != entity.get("lastrevid") for row in rows)
    if moved:
        # A re-propose re-derives every row the policy decided, so the policy
        # runs again here; a verdict the verifier already gave is found by its
        # content, and only a row the move changed is left pending.
        propose.propose_person(qid)
        policy.run([qid], write=True)
        rows = accepted_rows(qid)
    return entity, rows, moved


def retire(plan: Plan) -> int:
    """Close the accepted rows the edit could not carry, naming the route that said so.

    A conflict, a value already there, a removed lane's row: none of
    these will write on a later pass either, and an accepted row that stays
    accepted is selected again by every send. They become
    `skipped` under `plan:<route>`, which a report counts like any other rule.
    """
    conn = db.conn()
    with conn.transaction():
        for proposal_id, route in plan.skipped:
            conn.execute(
                "UPDATE proposal SET status = %s, decided_by = %s, decided_at = now()"
                " WHERE id = %s AND status = 'accepted'",
                (policy.SKIPPED, f"{propose.PLAN_DECIDED}{route}", proposal_id),
            )
    return len(plan.skipped)
