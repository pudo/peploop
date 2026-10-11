"""Render a run's applied decisions as QuickStatements V1, and check them.

A country's run file is rendered and checked here (`validate`). What reaches
Wikidata goes out through `outbox.py` (`peploop.cli tree send`), as a QuickStatements 3.0 batch.
"""

import datetime as dt
from pathlib import Path
from typing import Any

from peploop import qs

OUT_DIR = Path(__file__).resolve().parents[2] / "data" / "peptree"


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
        # A quote would end the string column; percent-encoded it is the same URL.
        cols += ["S854", qs.qs_value(url.replace('"', "%22")), "S813", retrieved]
    return qs.line(cols, name)


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
        cols = qs.columns(text)
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


def statements(lines: list[str]) -> list[tuple[str, str, str]]:
    """(item, property, value) of every line."""
    out = []
    for text in lines:
        cols = qs.columns(text)
        out.append((cols[0], cols[1], cols[2]))
    return out


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
