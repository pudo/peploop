"""Read a country's file: everything the lanes know about one country that code must not.

Each country, and the Union as `eu`, has one hand-written file
`countries/<cc>.yml`, so what is measured about a country is read and
corrected in one place. Facts every lane needs sit at the top:

- `state`: the polity whose subdivisions are the regional tier, where it is
  not the one rigour gives (a realm or kingdom around the state, or the Union);
- `realm`: the sovereign realm around that state, which offices also name and
  which stays a home state, never a predecessor;
- `not_predecessor`: items the predecessor chain reaches whose offices are
  none of the country's, each `{qid, name}`.

Each lane owns one top-level section:

- `seeds`: the Wikipedia categories and list articles a peploop run starts from;
- `census`: the offices that must exist whether or not an article named them;
- `corp`: pepcorp's spec (`corp/country.py`);
- `amlr`: the AMLR's unit classes and threshold (`amlr.py`).

The AMLR's function list is generated from the Commission's sheet and
rewritten by its tools, so it lives beside the file as `<cc>.amlr.yml`
and never touches a hand-written comment.
"""

from pathlib import Path
from typing import Any

import yaml

DIR = Path(__file__).resolve().parent / "countries"
SECTIONS = ("seeds", "census", "corp", "amlr")
SHARED = ("state", "realm", "not_predecessor")


def path(cc: str) -> Path:
    return DIR / f"{cc}.yml"


def _read(cc: str, file: Path | None) -> dict[str, Any]:
    file = file or path(cc)
    if not file.exists():
        return {}
    data = yaml.safe_load(file.read_text()) or {}
    unknown = set(data) - set(SECTIONS) - set(SHARED)
    if unknown:
        raise ValueError(f"{file}: unknown keys {sorted(unknown)}")
    return data


def section(cc: str, name: str, file: Path | None = None) -> Any:
    """One lane's section of a country's file; `None` when the file or the section is absent."""
    if name not in SECTIONS:
        raise ValueError(f"unknown section {name!r}")
    return _read(cc, file).get(name)


def state(cc: str, file: Path | None = None) -> str | None:
    """The file's `state`, where the country names one."""
    value = _read(cc, file).get("state")
    return str(value) if value else None


def realm(cc: str) -> str | None:
    """The file's `realm`, where the state sits in one."""
    value = _read(cc, None).get("realm")
    return str(value) if value else None


def not_predecessors(cc: str) -> frozenset[str]:
    """The QIDs the country's predecessor chain must leave out."""
    return frozenset(str(e["qid"]) for e in _read(cc, None).get("not_predecessor") or [])


def codes(name: str) -> list[str]:
    """The codes whose file has this section."""
    return sorted(p.stem for p in DIR.glob("*.yml")
                  if not p.name.endswith(".amlr.yml") and section(p.stem, name) is not None)
