"""Write accepted proposals to Wikidata through the action API.

One person is one `wbeditentity` edit: every proposal accepted for them lands
atomically, under the user's own account, with `baserevid` set to the revision
the pre-flight read. Nothing here trusts a stored status. The plan for each row
is recomputed against the live item, because a status was decided against
`item_rev` and the item — including by our own earlier writes — may have moved
since.

The reference shape is `P143` the wiki it was imported from, `P4656` the
permanent URL of the revision read, `P813` today.
"""

import datetime
import json
import re
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from peploop import db, http, policy, propose, wikidata, wikipedia

PROPERTY_NAMES = wikidata.PROPERTY_NAMES

CONFIG_PATH = Path.home() / ".config" / "wikibase-cli" / "config.json"
WD_SITE = "https://www.wikidata.org"
WD_API = f"{WD_SITE}/w/api.php"
#: A write waits out replication lag rather than adding to it, so it needs a
#: timeout longer than a read's: one edit in the older pipeline sat through a
#: 27-second query-service lag for over four minutes.
WRITE_TIMEOUT = 420.0
#: One id per process, so a run's edits are one batch in EditGroups and can be
#: reverted together. Without it every edit has to be undone one at a time,
#: which is the capability the QuickStatements path had and this one did not.
BATCH_ID = uuid.uuid4().hex[:10]
#: Every payload sent, appended. `data/` is gitignored; this is an operator's
#: undo log, not a record anybody inherits.
LOG_PATH = Path(__file__).resolve().parent.parent / "data" / "applied.jsonl"
MAXLAG = 5
MAX_BACKOFF = 120.0
# Lag episodes outlast a short budget; the remedy is patience, not a higher threshold.
MAXLAG_BUDGET = 600.0
THROTTLE = 10.0
FOLLOW_IDLE = 60.0
# A reference built only from these says "imported from a Wikipedia article",
# which is the one provenance a refinement may overwrite in place.
IMPORT_PROPS = wikidata.IMPORT_PROPS


class ApiError(RuntimeError):
    """An action API call that answered with an `error` object."""

    def __init__(self, code: str, info: str) -> None:
        super().__init__(f"{code}: {info}")
        self.code = code
        self.info = info


@dataclass
class Plan:
    """One person's whole edit, before it is sent."""

    qid: str
    baserevid: int | None
    data: dict[str, Any] = field(default_factory=dict)
    summary: str = ""
    # (proposal id, property, value, qualifiers) per statement. The qualifiers
    # are here because the value alone stopped identifying a statement the day
    # two spells of one office became two statements rather than one.
    claims: list[tuple[int, str, dict[str, Any], dict[str, Any]]] = field(default_factory=list)
    skipped: list[tuple[int, str]] = field(default_factory=list)
    routes: Counter[str] = field(default_factory=Counter)

    @property
    def covered(self) -> int:
        """Count the proposals this edit would move to `applied`."""
        return len(self.claims)


def credentials() -> tuple[str, str]:
    """Read the Wikidata username and password wikibase-cli was configured with."""
    config = json.loads(CONFIG_PATH.read_text())
    entry = config.get("credentials", {}).get(WD_SITE)
    if not entry or not entry.get("username") or not entry.get("password"):
        raise RuntimeError(f"no {WD_SITE} credentials in {CONFIG_PATH}")
    return entry["username"], entry["password"]


def _api(
    payload: dict[str, Any], timeout: float | None = None
) -> tuple[dict[str, Any], dict[str, str]]:
    """POST one action API call, returning its parsed body and response headers.

    An error is left in the body: `maxlag` arrives as HTTP 503 with a JSON
    error and a `Retry-After`, so the status alone must not raise.
    """
    res = http.post(WD_API, {**payload, "format": "json"}, timeout=timeout)
    try:
        return res.json(), dict(res.headers)
    except ValueError as exc:
        raise RuntimeError(f"HTTP {res.status_code} from {WD_API}: {res.text[:200]}") from exc


def _token(kind: str) -> str:
    body, _ = _api({"action": "query", "meta": "tokens", "type": kind})
    return body["query"]["tokens"][f"{kind}token"]


def login() -> str:
    """Log the shared session in and return the account name the API reports.

    `action=login` is what a bot password is for. A main-account password is
    refused there, so the failure falls through to `clientlogin`, which the
    caller is told about because the two leave different traces in the logs.
    """
    username, password = credentials()
    body, _ = _api(
        {
            "action": "login",
            "lgname": username,
            "lgpassword": password,
            "lgtoken": _token("login"),
        }
    )
    result = body.get("login", {}).get("result")
    if result != "Success":
        body, _ = _api(
            {
                "action": "clientlogin",
                "username": username,
                "password": password,
                "logintoken": _token("login"),
                "loginreturnurl": WD_SITE,
                "rememberMe": "1",
            }
        )
        status = body.get("clientlogin", {}).get("status")
        if status != "PASS":
            raise RuntimeError(f"login refused: {result}, clientlogin: {status or body}")
    info, _ = _api({"action": "query", "meta": "userinfo"})
    name = info.get("query", {}).get("userinfo", {}).get("name")
    if not name or info["query"]["userinfo"].get("anon") is not None:
        raise RuntimeError(f"logged in but the API still reports {name!r}")
    return name


def csrf_token() -> str:
    """Return the edit token for the session `login` authenticated."""
    return _token("csrf")


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


def editgroup() -> str:
    """The marker that makes this run's edits one revertable batch.

    EditGroups reads it out of the edit summary and offers the whole run for
    revert in one action. The older pipeline had this for free because
    QuickStatements batches are revertable; an edit made straight through the
    API has to say so itself, or a bad run has to be undone one item at a time.
    """
    return f"([[:toollabs:editgroups/b/CB/{BATCH_ID}|details]])"


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
    when a tenure began is not one this may re-date. `wbeditentity` replaces a
    statement with what it is sent, so the caller sends the live claim back with
    these merged in rather than a payload holding only the new qualifier --
    which would wipe every qualifier already on it.
    """
    present = claim.get("qualifiers") or {}
    if any(prop in present for prop in qualifiers):
        return None
    return {prop: snaks for prop, snaks in qualifiers.items() if prop not in present}


def plan_claim(entity: dict[str, Any], row: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
    """Decide what one statement proposal does to the live item.

    Contradiction is ruled out first, and over every statement rather than the
    one that happens to match: a person with a year-precision 1950 *and* a
    day-precision 1 March 1950 is not someone our 1 February 1950 refines, even
    though it agrees with the coarse one at the precision they share. Then a
    value already recorded as finely writes nothing, a coarser one that is only
    a Wikipedia import is ours to sharpen in place, a coarser one somebody else
    sourced gets ours beside it as preferred, and anything left is new.
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
        return plan_tenure(prop, value, matching, qualifiers, order, refs, row)
    superseding = False
    # An undated statement first, so a tenure the item records twice is sharpened
    # on the copy that says nothing rather than on one that already has dates.
    for claim, found in sorted(matching, key=lambda pair: len(pair[0].get("qualifiers") or {})):
        sharper = "time" in value and found.get("precision", 11) < value["precision"]
        if sharper and is_import(claim):
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
    """A new statement, as `wbeditentity` takes one."""
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
    row: dict[str, Any],
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
    A spell overlapping nothing is a further term, and new.
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
        refined = dict(claim)
        refined["references"] = [*(claim.get("references") or []), *refs]
        return "refine", _with_qualifiers(refined, missing)
    if undated is not None:
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

    The API de-duplicates nothing, so the same citizenship attested in two
    languages would otherwise go out as two identical claims. They are the same
    statement with two references, and that is what this collapses them into.

    **The qualifiers are part of the identity.** Keyed on the value alone, a
    person's two spells in one office are one statement and the second one's
    dates are dropped in silence -- measured on Q6873822, whose two accepted
    National Council rows produced a single statement carrying no dates at all.
    That is the collapse `wd/validate.py:collapsing_groups` documents for
    QuickStatements, and avoiding it is the reason this path writes through the
    API instead.
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
    plan = Plan(qid=qid, baserevid=entity.get("lastrevid"))
    statements: dict[str, dict[str, Any]] = {}
    written: list[dict[str, Any]] = []
    for row in rows:
        if row["property"].startswith(policy.TERM_PREFIXES):
            # A label or alias a human accepted before the lane was removed:
            # closed, never written.
            plan.routes["lane_removed"] += 1
            plan.skipped.append((row["id"], "lane_removed"))
            continue
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
            plan.routes[route] += 1
        else:
            already.setdefault("references", []).extend(statement.get("references") or [])
            plan.routes["merged"] += 1
        plan.claims.append(
            (row["id"], row["property"], row["value"], (statement.get("qualifiers") or {}))
        )
        written.append(row)
    if statements:
        plan.data["claims"] = list(statements.values())
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


def people(qids: list[str], limit: int, country: str | None = None) -> list[str]:
    """Pick the people to write: the named ones, or those with accepted rows."""
    if qids:
        return qids
    rows = db.conn().execute(
        "SELECT DISTINCT p.person_qid FROM proposal p JOIN person pe ON pe.qid = p.person_qid"
        " WHERE p.status = 'accepted' AND (%s::text IS NULL OR pe.country = %s)"
        " ORDER BY p.person_qid LIMIT %s",
        (country, country, limit),
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


def _find_guid(
    entity: dict[str, Any], prop: str, value: dict[str, Any],
    qualifiers: dict[str, Any] | None = None, taken: set[str] = frozenset(),
) -> str | None:
    """Find the statement a written row produced, in the item the API returned.

    The value alone stopped identifying a statement the day two spells of one
    office became two statements: both rows then matched the first claim and
    were recorded under the same id. So the qualifiers narrow it, and `taken`
    excludes the ids already claimed by rows written in the same edit -- which
    is what separates two statements the item genuinely records identically.
    """
    fallback = None
    for claim in entity.get("claims", {}).get(prop, []):
        guid = claim.get("id")
        if guid in taken:
            continue
        existing = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        if not isinstance(existing, dict) or not same_value(existing, value):
            continue
        if fallback is None:
            fallback = guid
        if _qualifier_fingerprint(claim.get("qualifiers")) == _qualifier_fingerprint(qualifiers):
            return guid
    return fallback


def maxlag_wait(spent: float, delay: float, retry_after: float | None = None) -> float | None:
    """Say how long to sleep before retrying a `maxlag` refusal, or None to give up.

    `spent` is what this write has already slept. A `Retry-After` the response
    carries is a floor, not an override: the header is usually the `maxlag`
    threshold itself, so obeying it literally would poll every five seconds for
    the whole budget. The wait is clipped to what is left of `MAXLAG_BUDGET`, so
    the last one ends on the budget rather than past it.
    """
    remaining = MAXLAG_BUDGET - spent
    if remaining <= 0:
        return None
    return min(max(retry_after or 0.0, delay), MAX_BACKOFF, remaining)


def write_payload(plan: Plan, token: str) -> dict[str, Any]:
    """The `wbeditentity` call one person's edit goes out as.

    Apart from one `data` blob per person, which is what makes the edit atomic,
    three things here are easy to get silently wrong and are pinned in
    `check_apply`: there is no `bot` key at all, because MediaWiki resolves a
    boolean parameter by its *presence* and `bot=0` therefore asks for the flag
    rather than declining it; `assert` fails an edit whose session has lapsed
    instead of attributing it to the client IP, which matters because `--follow`
    logs in once and may then run for days; and `baserevid` is the revision the
    decision was made against, so an item that moved underneath is a conflict
    rather than a silent overwrite.
    """
    payload = {
        "action": "wbeditentity",
        "id": plan.qid,
        "data": json.dumps(plan.data, ensure_ascii=False),
        "summary": f"{plan.summary} {editgroup()}",
        "token": token,
        "assert": "user",
        "maxlag": MAXLAG,
    }
    if plan.baserevid is not None:
        payload["baserevid"] = plan.baserevid
    return payload


def send(plan: Plan, token: str) -> dict[str, Any]:
    """Send one person's edit, waiting out replication lag rather than adding to it."""
    return _send(write_payload(plan, token))


def _send(payload: dict[str, Any]) -> dict[str, Any]:
    """POST one write, retrying a `maxlag` refusal and raising any other error.

    `maxlag` covers the query-service updaters, not just database replication,
    so a refusal means a legitimate wait of minutes; the answer to a lagged
    site is to sleep — up to `MAXLAG_BUDGET` — not to declare a willingness to
    load it further.
    """
    delay = 5.0
    spent = 0.0
    while True:
        body, headers = _api(payload, timeout=WRITE_TIMEOUT)
        error = body.get("error")
        if error is None:
            log_write(payload, body)
            return body
        wait = None
        if error.get("code") == "maxlag":
            header = headers.get("Retry-After")
            wait = maxlag_wait(spent, delay, float(header) if header else None)
        if wait is None:
            raise api_error(error)
        print(f"  maxlag {error.get('lag')}s: waiting {wait:.0f}s", flush=True)
        time.sleep(wait)
        spent += wait
        delay = min(delay * 2, MAX_BACKOFF)


class LabelConflict(ApiError):
    """A creation refused because another item already has its label and description.

    Wikibase keeps label plus description unique per language, so this refusal
    is a duplicate the live search missed, and it names the item: the caller
    records that QID as found rather than retrying under another wording.
    """

    def __init__(self, code: str, info: str, qid: str) -> None:
        super().__init__(code, info)
        self.qid = qid


_CONFLICT_QID = re.compile(r"\[\[(?:Item:)?(Q\d+)\|")


def api_error(error: dict[str, Any]) -> ApiError:
    """Turn an action API `error` object into the exception a caller can act on."""
    code = error.get("code", "?")
    info = error.get("info") or json.dumps(error)
    if code in ("modification-failed", "failed-save"):
        messages = error.get("messages") or []
        texts = [info]
        for message in messages:
            if "conflict" in (message.get("name") or ""):
                texts.extend(str(param) for param in message.get("parameters") or [])
        if "already has label" in info or len(texts) > 1:
            for text in texts:
                found = _CONFLICT_QID.search(text)
                if found:
                    return LabelConflict(code, info, found.group(1))
    return ApiError(code, info)


def create_payload(data: dict[str, Any], summary: str, token: str) -> dict[str, Any]:
    """The `wbeditentity` call that creates one new item.

    The same guards as `write_payload` -- no `bot` key, `assert=user`, maxlag,
    the EditGroups marker -- and no `id` or `baserevid`, because there is no
    revision yet for the edit to be decided against. The caller puts its intent
    tag in `summary`, which is what `find_created` reads back after a crash.
    """
    return {
        "action": "wbeditentity",
        "new": "item",
        "data": json.dumps(data, ensure_ascii=False),
        "summary": f"{summary} {editgroup()}",
        "token": token,
        "assert": "user",
        "maxlag": MAXLAG,
        "format": "json",
    }


def create_item(data: dict[str, Any], summary: str, token: str) -> tuple[str, int]:
    """Create one item and return its QID and first revision.

    Raises `LabelConflict` when an item with the same label and description
    exists, and `ApiError` for any other refusal.
    """
    body = _send(create_payload(data, summary, token))
    entity = body.get("entity") or {}
    qid, rev = entity.get("id"), entity.get("lastrevid")
    if not body.get("success") or not qid or rev is None:
        raise ApiError("no-entity", f"creation answered without an item: {json.dumps(body)[:300]}")
    return qid, int(rev)


def account() -> str:
    """Name the account the shared session is logged in as."""
    info, _ = _api({"action": "query", "meta": "userinfo"})
    userinfo = info.get("query", {}).get("userinfo", {})
    if not userinfo.get("name") or userinfo.get("anon") is not None:
        raise RuntimeError("not logged in: usercontribs needs the account name")
    return userinfo["name"]


def find_created(
    tag: str, since: datetime.datetime, user: str | None = None
) -> str | None:
    """Find the item this account created with `tag` in its summary, if any.

    This is how a creation interrupted between the API call and the database
    write is resolved: `usercontribs` reads the edit log directly, so unlike
    search or the query service it is authoritative the moment the edit lands.
    Only page creations count -- a later edit carrying the same tag is not the
    one that made the item. Read live through the session, never cached.
    """
    user = user or account()
    start = since.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    params: dict[str, Any] = {
        "action": "query",
        "list": "usercontribs",
        "ucuser": user,
        "ucnamespace": 0,
        "ucshow": "new",
        "ucdir": "newer",
        "ucstart": start,
        "ucprop": "title|comment|ids|timestamp|flags",
        "uclimit": 500,
    }
    while True:
        body, _ = _api(params)
        if body.get("error"):
            raise api_error(body["error"])
        for contrib in body.get("query", {}).get("usercontribs", []):
            if "new" not in contrib:
                continue
            if tag in (contrib.get("comment") or ""):
                return contrib.get("title")
        more = body.get("continue")
        if not more:
            return None
        params = {**params, **more}


def log_write(payload: dict[str, Any], body: dict[str, Any]) -> None:
    """Append what was sent and what came back to `data/applied.jsonl`.

    The proposal table records the *outcome* of an edit -- its revision and the
    statement id -- which is enough to know something happened and not enough to
    undo it. This is the payload itself, so a bad run can be read back and
    reversed by hand without reconstructing it from the item's history.
    """
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    entity = body.get("entity") or {}
    line = {
        "at": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
        "batch": BATCH_ID,
        # A creation has no id until the response names it.
        "qid": payload.get("id") or entity.get("id"),
        "new": payload.get("new"),
        "summary": payload.get("summary"),
        "baserevid": payload.get("baserevid"),
        "data": json.loads(payload["data"]),
        "lastrevid": entity.get("lastrevid"),
    }
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(line, ensure_ascii=False, sort_keys=True) + "\n")


def record(plan: Plan, body: dict[str, Any]) -> int:
    """Mark the written proposals `applied` and refresh our copy of the item."""
    entity = body.get("entity", {})
    rev = entity.get("lastrevid")
    conn = db.conn()
    with conn.transaction():
        taken: set[str] = set()
        for proposal_id, prop, value, qualifiers in plan.claims:
            guid = _find_guid(entity, prop, value, qualifiers, taken)
            if guid is not None:
                taken.add(guid)
            conn.execute(
                "UPDATE proposal SET status = 'applied', applied_rev = %s, claim_guid = %s,"
                " base_rev = %s, applied_batch = %s WHERE id = %s",
                (rev, guid, plan.baserevid, BATCH_ID, proposal_id),
            )
    stored = db.conn().execute(
        "SELECT json FROM item WHERE qid = %s", (plan.qid,)
    ).fetchone()
    # The response carries the whole entity, but merging over the stored copy
    # means a field the API happens to leave out cannot vanish from the cache.
    merged = {**(stored[0] if stored else {}), **entity}
    db.upsert_item(plan.qid, rev, merged)
    return plan.covered


def retire(plan: Plan) -> int:
    """Close the accepted rows the edit could not carry, naming the route that said so.

    A conflict, a value already there, a removed lane's row: none of
    these will write on a later pass either, and an accepted row that stays
    accepted is selected again every minute by `--follow`. They become
    `skipped` under `apply:<route>`, which a report counts like any other rule.
    """
    conn = db.conn()
    with conn.transaction():
        for proposal_id, route in plan.skipped:
            conn.execute(
                "UPDATE proposal SET status = %s, decided_by = %s, decided_at = now()"
                " WHERE id = %s AND status = 'accepted'",
                (policy.SKIPPED, f"apply:{route}", proposal_id),
            )
    return len(plan.skipped)


def apply_person(qid: str, token: str | None, defer_lag: bool = False) -> tuple[Plan, str]:
    """Plan one person's edit and, with a token, send it and record the result.

    An edit conflict is retried once: the item moved between the pre-flight and
    the write, so the plan is rebuilt against what is there now. `defer_lag`
    leaves a person the lag budget ran out on untouched rather than `failed`,
    for a caller that will come back to them; the error still propagates.
    """
    entity, rows, moved = preflight(qid)
    plan = plan_person(qid, entity, rows)
    note = " (re-proposed: item moved)" if moved else ""
    if token is None:
        return plan, note
    if not plan.data:
        retire(plan)
        return plan, note
    for attempt in (0, 1):
        try:
            body = send(plan, token)
        except ApiError as exc:
            if exc.code != "editconflict" or attempt:
                if not (defer_lag and exc.code == "maxlag"):
                    db.set_person_status(qid, "failed", f"apply: {exc}")
                raise
            entity, rows, _ = preflight(qid)
            plan = plan_person(qid, entity, rows)
            note += " (retried after edit conflict)"
            if not plan.data:
                return plan, note
            continue
        record(plan, body)
        retire(plan)
        _clear_failure(qid)
        return plan, note
    return plan, note


def _clear_failure(qid: str) -> None:
    """Take a person out of `failed` once an edit for them has gone through.

    A lag episode marks the person `failed` with the refusal text, and the
    next pass retries them by their accepted rows rather than by that status;
    a write that then succeeds would otherwise leave the failure standing.
    """
    db.conn().execute(
        "UPDATE person SET status = 'proposed', error = NULL, updated_at = now()"
        " WHERE qid = %s AND status = 'failed'",
        (qid,),
    )
