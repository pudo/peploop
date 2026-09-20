"""Write accepted proposals to Wikidata through the action API.

One person is one `wbeditentity` edit: every proposal accepted for them lands
atomically, under the user's own account, with `baserevid` set to the revision
the pre-flight read. Nothing here trusts a stored status. The plan for each row
is recomputed against the live item, because a status was decided against
`item_rev` and the item — including by our own earlier writes — may have moved
since.

QuickStatements is the other write path (`render.py`), and the two agree on the
reference shape: `P143` the wiki it was imported from, `P4656` the permanent
URL of the revision read, `P813` today.
"""

import datetime
import json
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from peploop import db, http, propose, wikidata, wikipedia
from peploop.review import PROPERTY_NAMES

CONFIG_PATH = Path.home() / ".config" / "wikibase-cli" / "config.json"
WD_SITE = "https://www.wikidata.org"
WD_API = f"{WD_SITE}/w/api.php"
MAXLAG = 5
MAX_BACKOFF = 120.0
# Lag episodes outlast a short budget; the remedy is patience, not a higher threshold.
MAXLAG_BUDGET = 600.0
THROTTLE = 10.0
FOLLOW_IDLE = 60.0
# A reference built only from these says "imported from a Wikipedia article",
# which is the one provenance a refinement may overwrite in place.
IMPORT_PROPS = frozenset({"P143", "P4656", "P813"})
TERM_PREFIXES = (propose.LABEL_PREFIX, propose.ALIAS_PREFIX)


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
    # (proposal id, property, value) per statement, for matching the guid back
    # out of the response.
    claims: list[tuple[int, str, dict[str, Any]]] = field(default_factory=list)
    terms: list[int] = field(default_factory=list)
    skipped: list[tuple[int, str]] = field(default_factory=list)
    routes: Counter[str] = field(default_factory=Counter)

    @property
    def covered(self) -> int:
        """Count the proposals this edit would move to `applied`."""
        return len(self.claims) + len(self.terms)


def credentials() -> tuple[str, str]:
    """Read the Wikidata username and password wikibase-cli was configured with."""
    config = json.loads(CONFIG_PATH.read_text())
    entry = config.get("credentials", {}).get(WD_SITE)
    if not entry or not entry.get("username") or not entry.get("password"):
        raise RuntimeError(f"no {WD_SITE} credentials in {CONFIG_PATH}")
    return entry["username"], entry["password"]


def _api(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    """POST one action API call, returning its parsed body and response headers.

    An error is left in the body: `maxlag` arrives as HTTP 503 with a JSON
    error and a `Retry-After`, so the status alone must not raise.
    """
    res = http.post(WD_API, {**payload, "format": "json"})
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


def is_import(claim: dict[str, Any]) -> bool:
    """Say whether a statement rests on nothing but Wikipedia imports.

    An unreferenced statement counts: there is no sourcing to lose by writing
    a better value over it. One `P248` reference is enough to make the claim
    somebody else's, and a refinement then goes beside it instead.
    """
    for ref in claim.get("references") or []:
        if not set(ref.get("snaks") or {}) <= IMPORT_PROPS:
            return False
    return True


def _qualifiers(row: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Take the real qualifiers off a proposal, dropping peploop's own `_` keys."""
    snaks: dict[str, list[dict[str, Any]]] = {}
    for prop, value in (row.get("qualifiers") or {}).items():
        if prop.startswith("P"):
            snaks[prop] = [_snak(prop, value)]
    return snaks, list(snaks)


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
    superseding = False
    for claim, found in matching:
        if "time" not in value or found.get("precision", 11) >= value["precision"]:
            return "exists", None
        if is_import(claim):
            refined = dict(claim)
            refined["mainsnak"] = _snak(prop, value)
            refined["references"] = [*(claim.get("references") or []), *refs]
            return "refine", refined
        # Somebody else's sourcing on a coarser value: ours goes beside it,
        # outranking it rather than replacing it.
        superseding = True
    statement: dict[str, Any] = {
        "type": "statement",
        "rank": "preferred" if superseding else "normal",
        "mainsnak": _snak(prop, value),
    }
    if qualifiers:
        statement["qualifiers"] = qualifiers
        statement["qualifiers-order"] = order
    if refs:
        statement["references"] = refs
    return ("preferred" if superseding else "new"), statement


def plan_term(entity: dict[str, Any], row: dict[str, Any]) -> tuple[str, str, str] | None:
    """Decide what one label or alias proposal does, or nothing if it is there.

    A label is only ever filled in, never replaced: the item having any label
    in that language is the end of it.
    """
    prop, text = row["property"], row["value"]["text"]
    lang = prop.split(":", 1)[1]
    labels = {code: term["value"] for code, term in entity.get("labels", {}).items()}
    if prop.startswith(propose.LABEL_PREFIX):
        return None if lang in labels else ("labels", lang, text)
    aliases = {term["value"] for term in entity.get("aliases", {}).get(lang, [])}
    if text in aliases or text == labels.get(lang):
        return None
    return ("aliases", lang, text)


def _summary(rows: list[dict[str, Any]], claims: int, terms: Counter[str]) -> str:
    """Name what the edit changes and which article revisions say so."""
    parts = []
    for prop in dict.fromkeys(row["property"] for row in rows if row["property"][0] == "P"):
        parts.append(PROPERTY_NAMES.get(prop, prop))
    for kind, count in sorted(terms.items()):
        parts.append(f"{count} {kind}{'es' if kind == 'alias' and count > 1 else ''}")
    sources = {}
    for row in rows:
        for source in row_sources(row):
            if source.get("lang") and source.get("rev"):
                sources[f"{source['lang']}.wikipedia"] = source["rev"]
    where = ", ".join(f"{site} (rev {rev})" for site, rev in sorted(sources.items()))
    head = f"peploop: add {', '.join(parts) or f'{claims} statements'}"
    return f"{head} from {where}" if where else head


def _statement_key(prop: str, statement: dict[str, Any]) -> str:
    """Identify the statement a row lands on, so two rows cannot both create it.

    The API de-duplicates nothing, so the same citizenship attested in two
    languages would otherwise go out as two identical claims.
    """
    guid = statement.get("id")
    if guid:
        return guid
    value = statement["mainsnak"]["datavalue"]["value"]
    return prop + "\t" + json.dumps(value, sort_keys=True, ensure_ascii=False)


def plan_person(qid: str, entity: dict[str, Any], rows: list[dict[str, Any]]) -> Plan:
    """Turn one person's accepted proposals into the edit they imply.

    Rows attesting the same thing from two wikis become one statement with two
    references, and both are recorded as applied against the one it produced.
    """
    plan = Plan(qid=qid, baserevid=entity.get("lastrevid"))
    statements: dict[str, dict[str, Any]] = {}
    seen_terms: set[tuple[str, str]] = set()
    terms: Counter[str] = Counter()
    written: list[dict[str, Any]] = []
    for row in rows:
        if row["property"].startswith(TERM_PREFIXES):
            placed = plan_term(entity, row)
            if placed is None or placed[1:] in seen_terms:
                plan.skipped.append((row["id"], "term already on the item"))
                continue
            slot, lang, text = placed
            seen_terms.add((lang, text))
            kind = "label" if slot == "labels" else "alias"
            entry = {"language": lang, "value": text}
            if slot == "aliases":
                plan.data.setdefault("aliases", {}).setdefault(lang, []).append(
                    {**entry, "add": ""}
                )
            else:
                plan.data.setdefault("labels", {})[lang] = entry
            terms[kind] += 1
            plan.routes[kind] += 1
            plan.terms.append(row["id"])
            written.append(row)
            continue
        route, statement = plan_claim(entity, row)
        if statement is None:
            plan.routes[route] += 1
            plan.skipped.append((row["id"], route))
            continue
        key = _statement_key(row["property"], statement)
        already = statements.get(key)
        if already is None:
            statements[key] = statement
            plan.routes[route] += 1
        else:
            already.setdefault("references", []).extend(statement.get("references") or [])
            plan.routes["merged"] += 1
        plan.claims.append((row["id"], row["property"], row["value"]))
        written.append(row)
    if statements:
        plan.data["claims"] = list(statements.values())
    plan.summary = _summary(written, len(statements), terms)
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


def people(qids: list[str], limit: int) -> list[str]:
    """Pick the people to write: the named ones, or those with accepted rows."""
    if qids:
        return qids
    rows = db.conn().execute(
        "SELECT DISTINCT person_qid FROM proposal WHERE status = 'accepted'"
        " ORDER BY person_qid LIMIT %s",
        (limit,),
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
        propose.propose_person(qid)
        rows = accepted_rows(qid)
    return entity, rows, moved


def _find_guid(entity: dict[str, Any], prop: str, value: dict[str, Any]) -> str | None:
    for claim in entity.get("claims", {}).get(prop, []):
        existing = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(existing, dict) and same_value(existing, value):
            return claim.get("id")
    return None


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


def send(plan: Plan, token: str) -> dict[str, Any]:
    """Send one person's edit, waiting out replication lag rather than adding to it.

    `maxlag` covers the query-service updaters, not just database replication,
    so a refusal means a legitimate wait of minutes; the answer to a lagged
    site is to sleep — up to `MAXLAG_BUDGET` — not to declare a willingness to
    load it further.
    """
    payload = {
        "action": "wbeditentity",
        "id": plan.qid,
        "data": json.dumps(plan.data, ensure_ascii=False),
        "summary": plan.summary,
        "token": token,
        "bot": 0,
        "maxlag": MAXLAG,
    }
    if plan.baserevid is not None:
        payload["baserevid"] = plan.baserevid
    delay = 5.0
    spent = 0.0
    while True:
        body, headers = _api(payload)
        error = body.get("error")
        if error is None:
            return body
        wait = None
        if error.get("code") == "maxlag":
            header = headers.get("Retry-After")
            wait = maxlag_wait(spent, delay, float(header) if header else None)
        if wait is None:
            raise ApiError(error.get("code", "?"), error.get("info") or json.dumps(error))
        print(f"  maxlag {error.get('lag')}s: waiting {wait:.0f}s", flush=True)
        time.sleep(wait)
        spent += wait
        delay = min(delay * 2, MAX_BACKOFF)


def record(plan: Plan, body: dict[str, Any]) -> int:
    """Mark the written proposals `applied` and refresh our copy of the item."""
    entity = body.get("entity", {})
    rev = entity.get("lastrevid")
    conn = db.conn()
    with conn.transaction():
        for proposal_id, prop, value in plan.claims:
            conn.execute(
                "UPDATE proposal SET status = 'applied', applied_rev = %s, claim_guid = %s"
                " WHERE id = %s",
                (rev, _find_guid(entity, prop, value), proposal_id),
            )
        for proposal_id in plan.terms:
            conn.execute(
                "UPDATE proposal SET status = 'applied', applied_rev = %s WHERE id = %s",
                (rev, proposal_id),
            )
    stored = db.conn().execute(
        "SELECT json FROM item WHERE qid = %s", (plan.qid,)
    ).fetchone()
    # The response carries the whole entity, but merging over the stored copy
    # means a field the API happens to leave out cannot vanish from the cache.
    merged = {**(stored[0] if stored else {}), **entity}
    db.upsert_item(plan.qid, rev, merged)
    return plan.covered


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
    if token is None or not plan.data:
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
        return plan, note
    return plan, note
