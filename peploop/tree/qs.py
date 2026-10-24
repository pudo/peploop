"""Render a run's applied decisions as QuickStatements V1, and check them.

A country's run file is rendered and checked here (`validate`). What reaches
Wikidata goes out through `outbox.py` (`peploop.cli tree send`), as a QuickStatements 3.0 batch.
"""

import datetime as dt
from pathlib import Path
from typing import Any

from peploop import plan, qs

OUT_DIR = Path(__file__).resolve().parents[2] / "data" / "peptree"


def line(d: dict[str, Any]) -> str:
    """One statement. An article-derived value cites its article as peploop does; a structural one nothing."""
    cols = [d["qid"], d["prop"], d["value"]]
    source = d.get("source") or ""
    lang = source.removeprefix("article_") if source.startswith("article_") else None
    url = (d.get("articles") or {}).get(lang) if lang else None
    ref = plan.reference(lang, url.replace('"', "%22"), None) if url else None
    if ref is not None:
        # A quote would end the string column; percent-encoded it is the same URL.
        cols += qs.references([ref]) or []
    return qs.described("peptree", cols)


def render(decisions: list[dict[str, Any]]) -> list[str]:
    lines = [line(d) for d in decisions if d["disposition"] == "apply"]
    return sorted(dict.fromkeys(lines))


#: What peptree writes on an office: its type, class, state and jurisdiction.
OFFICE_PROPS = frozenset({"P31", "P279", "P17", "P1001"})
#: What peptree writes on a place: the office that heads it. A place's line is
#: the only kind whose subject is not an office, so it may carry nothing else.
PLACE_PROPS = frozenset({"P1313"})


def validate(lines: list[str]) -> list[str]:
    """Local checks: no duplicate statement, one value per (item, property), well-formed columns.

    A `P1313` line's subject is a place, so it carries no office statement in the
    same batch, and its value, an office, heads no place itself.
    """
    errors = []
    seen: dict[tuple[str, str], str] = {}
    places = {c[0] for c in map(qs.columns, lines) if len(c) >= 3 and c[1] in PLACE_PROPS}
    for n, text in enumerate(lines, 1):
        if text.startswith("-"):
            errors.append(f"{n}: removal in an add-only batch")
            continue
        cols = qs.columns(text)
        if len(cols) < 3 or not cols[0].startswith("Q") or not cols[1].startswith("P") or not cols[2].startswith("Q"):
            errors.append(f"{n}: malformed: {text!r}")
            continue
        if cols[1] not in OFFICE_PROPS | PLACE_PROPS:
            errors.append(f"{n}: {cols[1]} is no property peptree writes")
            continue
        if cols[1] in OFFICE_PROPS and cols[0] in places:
            errors.append(f"{n}: {cols[1]} on {cols[0]}, a place another line links to its head office")
        if cols[1] in PLACE_PROPS and cols[2] in places:
            errors.append(f"{n}: {cols[2]} is linked as a head office and as a place")
        key = (cols[0], cols[1])
        if key in seen and cols[1] != "P279":
            errors.append(f"{n}: second {cols[1]} on {cols[0]} ({seen[key]} and {cols[2]})")
        seen[key] = cols[2]
        if "S4656" in cols and "S813" not in cols:
            errors.append(f"{n}: S4656 without S813")
    return errors


def statements(lines: list[str]) -> list[tuple[str, str, str]]:
    """(item, property, value) of every line."""
    out = []
    for text in lines:
        cols = qs.columns(text)
        out.append((cols[0], cols[1], cols[2]))
    return out


def run_path(cc: str, day: dt.date | None = None, suffix: str = ".qs", lane: str = "") -> Path:
    """`data/peptree/<cc>/<cc>-<day>.qs`: one file per country and run day, every repair lane in it.

    A lane run apart from the repair (`backlink`) writes `<cc>-<lane>-<day>.qs`.
    """
    stem = f"{cc}-{lane}" if lane else cc
    return OUT_DIR / cc / f"{stem}-{(day or dt.date.today()).isoformat()}{suffix}"


def write(cc: str, lines: list[str], lane: str = "") -> Path:
    path = run_path(cc, lane=lane)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n" if lines else "")
    return path


def latest(cc: str, lane: str = "") -> Path | None:
    """The newest run file for a country, or for one of its lanes, by the day in its name."""
    stem = f"{cc}-{lane}" if lane else cc
    found = sorted((OUT_DIR / cc).glob(f"{stem}-[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].qs"))
    return found[-1] if found else None
