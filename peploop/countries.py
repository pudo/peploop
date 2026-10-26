"""Read a country's file: everything the lanes know about one country that code must not.

Each country, and the Union as `eu`, has one hand-written file
`countries/<cc>.yml`, so what is measured about a country is read and
corrected in one place. Each lane owns one top-level section of it:

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


def path(cc: str) -> Path:
    return DIR / f"{cc}.yml"


def section(cc: str, name: str, file: Path | None = None) -> Any:
    """One lane's section of a country's file; `None` when the file or the section is absent."""
    if name not in SECTIONS:
        raise ValueError(f"unknown section {name!r}")
    file = file or path(cc)
    if not file.exists():
        return None
    data = yaml.safe_load(file.read_text()) or {}
    unknown = set(data) - set(SECTIONS)
    if unknown:
        raise ValueError(f"{file}: unknown sections {sorted(unknown)}")
    return data.get(name)


def codes(name: str) -> list[str]:
    """The codes whose file has this section."""
    return sorted(p.stem for p in DIR.glob("*.yml")
                  if not p.name.endswith(".amlr.yml") and section(p.stem, name) is not None)
