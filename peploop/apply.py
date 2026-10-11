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
from pathlib import Path
from typing import Any

from peploop import db, http, policy, propose, wikidata, wikipedia
from peploop.plan import Plan, _find_guid, plan_person, preflight, retire  # noqa: F401

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
#: How long a drain waits after the lag budget ran out before trying again.
LAG_WAIT = 60.0


class ApiError(RuntimeError):
    """An action API call that answered with an `error` object."""

    def __init__(self, code: str, info: str) -> None:
        super().__init__(f"{code}: {info}")
        self.code = code
        self.info = info



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


def editgroup() -> str:
    """The marker that makes this run's edits one revertable batch.

    EditGroups reads it out of the edit summary and offers the whole run for
    revert in one action. The older pipeline had this for free because
    QuickStatements batches are revertable; an edit made straight through the
    API has to say so itself, or a bad run has to be undone one item at a time.
    """
    return f"([[:toollabs:editgroups/b/CB/{BATCH_ID}|details]])"



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
    instead of attributing it to the client IP, which matters because a drain
    logs in once and may then wait out lag for hours; and `baserevid` is the revision the
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
