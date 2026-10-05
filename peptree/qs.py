"""Render a run's applied decisions as QuickStatements V1, and check them.

A country's run file is rendered here and checked twice: locally (`validate`)
and by QuickStatements' own parser (`parse`, sent without `submit`, so it needs
no auth). What reaches Wikidata goes out through `outbox.py`, pasted into the
importer by hand; `batch_info` and `errors` read a pasted batch back.
"""

import datetime as dt
import re
from pathlib import Path
from typing import Any


from peploop import http

API = "https://quickstatements.toolforge.org/api.php"
OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "peptree"
EDITGROUPS = "https://editgroups.toolforge.org/b/QSv2/{}/"
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


# --- a pasted batch ---------------------------------------------------------------

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
