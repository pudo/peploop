"""Write a country's run file of QuickStatements lines, and find the latest one.

The lines are peploop's own (`route.render`): a `+` line for a new statement,
a plain line adding dates, role or a reference to the only statement holding
its value. What reaches Wikidata goes out through `outbox.py`
(`peploop.cli corp send`), as a QuickStatements 3.0 batch.
"""

import datetime as dt
from pathlib import Path

from peploop import route

OUT_DIR = Path(__file__).resolve().parents[2] / "data" / "pepcorp"
validate = route.validate


def run_path(cc: str, day: dt.date | None = None, suffix: str = ".qs") -> Path:
    """`data/pepcorp/<cc>/<cc>-<day>.qs`: one file per country and run day."""
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
