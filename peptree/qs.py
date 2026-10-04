"""Write a run's applied decisions to Wikidata as one QuickStatements batch.

Reach for this at the end of a run: it renders the decisions as V1, refuses a
batch QuickStatements would mis-parse (`parse` sends it without `submit`, which
needs no auth), submits it once under the user's account and polls it to the
end. Every submission is recorded in `ptree_write` before it is polled, so a
batch id is never lost to a crash.
"""

import datetime as dt
import os
import re
import time
from pathlib import Path
from typing import Any, Callable

import requests
from psycopg.types.json import Jsonb

from peploop import http
from peptree import wd

API = "https://quickstatements.toolforge.org/api.php"
OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "peptree"
EDITGROUPS = "https://editgroups.toolforge.org/b/QSv2/{}/"
FINAL = ("DONE", "STOP", "BLOCKED")
SUMMARY_RE = re.compile(r" /\* [^*]+ \*/$")


def today() -> str:
    return dt.date.today().strftime("+%Y-%m-%dT00:00:00Z/11")


def batch_name(cc: str, day: dt.date | None = None, lane: str = "repair") -> str:
    """The handle for one country's batch: the QS batch name and every edit's summary."""
    return f"peptree {lane} {cc} {(day or dt.date.today()).isoformat()}"


def line(d: dict[str, Any], retrieved: str, name: str) -> str:
    """One statement. Article-derived values carry S854 + S813; structural ones nothing."""
    cols = [d["qid"], d["prop"], d["value"]]
    source = d.get("source") or ""
    lang = source.removeprefix("article_") if source.startswith("article_") else None
    url = (d.get("articles") or {}).get(lang) if lang else None
    if url:
        cols += ["S854", f'"{url}"', "S813", retrieved]
    # The summary rides on the last column after a space: as a column of its
    # own, QS reads it as half a qualifier pair and fails the line.
    return "\t".join(cols) + f" /* {name} */"


def render(decisions: list[dict[str, Any]], name: str) -> list[str]:
    retrieved = today()
    lines = [line(d, retrieved, name) for d in decisions if d["disposition"] == "apply"]
    return sorted(dict.fromkeys(lines))


def validate(lines: list[str]) -> list[str]:
    """Local checks: no duplicate statement, one value per (item, property), well-formed columns."""
    errors = []
    seen: dict[tuple[str, str], str] = {}
    for n, text in enumerate(lines, 1):
        if text.startswith("-"):
            errors.append(f"{n}: removal in an add-only batch")
            continue
        cols = SUMMARY_RE.sub("", text).split("\t")
        if len(cols) < 3 or not cols[0].startswith("Q") or not cols[1].startswith("P") or not cols[2].startswith("Q"):
            errors.append(f"{n}: malformed: {text!r}")
            continue
        key = (cols[0], cols[1])
        if key in seen and cols[1] != "P279":
            errors.append(f"{n}: second {cols[1]} on {cols[0]} ({seen[key]} and {cols[2]})")
        seen[key] = cols[2]
        if "S854" in cols and "S813" not in cols:
            errors.append(f"{n}: S854 without S813")
    return errors


def parse_commands(text: str) -> tuple[bool, str, list[dict[str, Any]]]:
    """Server-side parse with no submit: (ok, detail, commands as QS would store them)."""
    res = http.post(API, data={"action": "import", "format": "v1", "data": text}, timeout=120)
    try:
        out = res.json()
    except ValueError:
        return False, f"HTTP {res.status_code}: {res.text[:200]}", []
    commands = (out.get("data") or {}).get("commands") or []
    bad = [c for c in commands if c.get("error")]
    if out.get("status") != "OK" or bad:
        return False, f"status={out.get('status')} errors={bad[:3]}", commands
    return True, f"{len(commands)} commands parsed, 0 errors", commands


def parse(text: str) -> tuple[bool, str]:
    ok, detail, _ = parse_commands(text)
    return ok, detail


def statements(lines: list[str]) -> list[tuple[str, str, str]]:
    """(item, property, value) of every line."""
    out = []
    for text in lines:
        cols = SUMMARY_RE.sub("", text).split("\t")
        out.append((cols[0], cols[1], cols[2]))
    return out


def preflight(cc: str, lines: list[str]) -> list[str]:
    """Problems against live Wikidata (max_age=0): a statement already present at
    any rank, an item gone, or an item edited since it was loaded."""
    stmts = statements(lines)
    qids = sorted({q for q, _, _ in stmts})
    live = wd.fetch_items(qids, props="info|claims")
    loaded = dict(wd.conn().execute(
        "SELECT qid, lastrevid FROM ptree_item WHERE country = %s AND qid = ANY(%s)", (cc, qids)).fetchall())
    problems = []
    for q in qids:
        ent = live.get(q)
        if ent is None:
            problems.append(f"{q}: missing live")
        elif ent.get("lastrevid") != loaded.get(q):
            problems.append(f"{q}: revision moved ({loaded.get(q)} -> {ent.get('lastrevid')})")
    for q, prop, value in stmts:
        for claim in (live.get(q) or {}).get("claims", {}).get(prop, []):
            v = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
            if isinstance(v, dict) and v.get("id") == value:
                problems.append(f"{q} {prop} {value}: already present ({claim.get('rank')})")
    return problems


# --- upload ------------------------------------------------------------------------

def credentials() -> tuple[str, str] | None:
    user, token = os.environ.get("QS_USERNAME"), os.environ.get("QS_TOKEN")
    return (user, token) if user and token else None


def submitted(name: str) -> int | None:
    """The batch id already recorded under this name: a batch is submitted at most once."""
    row = wd.conn().execute("SELECT batch_id FROM ptree_write WHERE batch_name = %s", (name,)).fetchone()
    return None if row is None else row[0]


def submit(cc: str, path: Path, text: str, name: str) -> int:
    """Upload `text` as one named batch and record its id at once. Never retried.

    The caller parse-checks first. The token goes only into the POST body,
    never into a log line or an exception.
    """
    creds = credentials()
    if creds is None:
        raise RuntimeError("QS_USERNAME / QS_TOKEN are not set")
    if submitted(name) is not None:
        raise RuntimeError(f"{name!r} was already submitted as batch {submitted(name)}")
    user, token = creds
    started = dt.datetime.now(dt.timezone.utc)
    res = requests.post(API, timeout=600, headers={"User-Agent": http.USER_AGENT}, data={
        "action": "import", "submit": 1, "format": "v1", "compress": 1, "batchname": name,
        "data": text, "username": user, "token": token})
    try:
        out = res.json()
    except ValueError:
        raise RuntimeError(f"QS answered HTTP {res.status_code} with no JSON: {res.text[:200]!r}") from None
    if out.get("status") != "OK" or "batch_id" not in out:
        raise RuntimeError(f"QS refused the batch: {out.get('status')!r}")
    batch_id = int(out["batch_id"])
    wd.conn().execute(
        "INSERT INTO ptree_write (batch_id, country, batch_name, qs_path, lines, username, submitted_at, status,"
        " editgroup) VALUES (%s,%s,%s,%s,%s,%s,%s,'SUBMITTED',%s)",
        (batch_id, cc, name, str(path), len(text.splitlines()), user, started, EDITGROUPS.format(batch_id)))
    return batch_id


def batch_info(batch_id: int) -> tuple[str, dict[str, int], dict[str, Any]]:
    """(status, per-status command counts, the batch row), read live."""
    out = http.get_json(API, params={"action": "get_batch_info", "batch": batch_id}, max_age=0)
    row = out["data"][str(batch_id)]
    counts = {k: int(v) for k, v in (row.get("commands") or {}).items()}
    return row["batch"]["status"], counts, row["batch"]


def errors(batch_id: int, limit: int = 500) -> list[dict[str, Any]]:
    """Every command that ended in ERROR, paged; `limit` must be passed or QS returns nothing."""
    out, start = [], 0
    while True:
        page = http.get_json(API, params={"action": "get_commands_from_batch", "batch": batch_id,
                                          "start": start, "limit": limit, "filter": "ERROR"}, max_age=0)
        rows = page.get("data") or []
        out += rows
        if len(rows) < limit:
            return out
        start += limit


def record(batch_id: int, status: str, counts: dict[str, int], errs: list[dict[str, Any]] | None) -> None:
    wd.conn().execute(
        "UPDATE ptree_write SET status = %s, counts = %s, errors = COALESCE(%s, errors), checked_at = now(),"
        " finished_at = CASE WHEN %s THEN COALESCE(finished_at, now()) END WHERE batch_id = %s",
        (status, Jsonb(counts), Jsonb(errs) if errs is not None else None, status in FINAL, batch_id))


def poll(batch_id: int, every: int = 30, timeout: float = 6 * 3600, log: Callable[[str], None] = print) -> dict:
    """Wait for DONE/STOP/BLOCKED, recording progress; a DONE batch can still hold errors."""
    deadline = time.time() + timeout
    last = None
    while True:
        try:
            status, counts, _ = batch_info(batch_id)
        except (requests.RequestException, KeyError, ValueError) as exc:
            log(f"  poll failed, retrying: {exc}")
            time.sleep(every)
            continue
        if (status, counts) != last:
            log(f"  {status} {counts}")
            last = (status, counts)
            record(batch_id, status, counts, None)
        if status in FINAL or time.time() > deadline:
            break
        time.sleep(every)
    errs = errors(batch_id)
    record(batch_id, status, counts, errs)
    return {"status": status, "counts": counts, "errors": errs, "editgroup": EDITGROUPS.format(batch_id)}


def run_path(cc: str, day: dt.date | None = None, suffix: str = ".qs") -> Path:
    """`data/peptree/<cc>/<cc>-<day>.qs`: one file per country and run day, every lane in it."""
    return OUT_DIR / cc / f"{cc}-{(day or dt.date.today()).isoformat()}{suffix}"


def write(cc: str, lines: list[str]) -> Path:
    path = run_path(cc)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n" if lines else "")
    return path


def latest(cc: str) -> Path | None:
    """The newest run file for a country, by the day in its name."""
    found = sorted((OUT_DIR / cc).glob(f"{cc}-[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].qs"))
    return found[-1] if found else None
