"""Read a country's spec: what pepcorp knows about one country that code must not.

pepcorp's logic is global. What differs by country lives in
`countries/<cc>.yml`, so a new country is a new file, not a code change:

- `holdings`: official lists of state holdings, each entry `name`, `qid`
  (null when the holding has no item), `holder`, `source`;
- `forms`: state-only legal forms and types (`P31` or `P1454`, matched
  exactly) that mark a body as state, each with the `kind` it is;
- `not_government`: classes the type tree wrongly makes a government body
  in this country;
- `exclude`: classes never a candidate here, beyond the global ones (a
  municipal savings bank, a professional chamber);
- `roles`: seats beyond the global table, `role` → `property` and an
  optional `qualifier` (a party committee secretary in a party state);
- `tiers`: the control tiers whose bodies are written;
- `state`: the item the country's items name as their country (`P17`), where
  it is not the one rigour gives (a realm or kingdom around the state);
- `actors`: items that stand for the state or its government here but that
  the type tree cannot place, each with its `kind`: `state` for a legal
  person the items name as owner in the state's place (a state treasury),
  `government` for a government body whose own statements miss the country.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from peploop import eras, positions

DIR = Path(__file__).resolve().parent / "countries"
#: The tiers written when a spec does not say: the state and its first-level subdivisions.
DEFAULT_TIERS = ("national", "regional")


@dataclass(frozen=True)
class Spec:
    cc: str
    holdings: list[dict[str, Any]] = field(default_factory=list)
    #: QID → kind ("enterprise" or "institution").
    forms: dict[str, str] = field(default_factory=dict)
    not_government: frozenset[str] = frozenset()
    exclude: frozenset[str] = frozenset()
    #: role → (property, qualifier or None).
    roles: dict[str, tuple[str, str | None]] = field(default_factory=dict)
    tiers: tuple[str, ...] = DEFAULT_TIERS
    state: str | None = None
    #: QID → actor kind ("state" or "government").
    actors: dict[str, str] = field(default_factory=dict)

    def seeded(self) -> dict[str, dict[str, Any]]:
        """QID → holdings entry, for the entries that name an item."""
        return {str(e["qid"]): e for e in self.holdings if e.get("qid")}

    def unmatched(self) -> list[dict[str, Any]]:
        """Holdings that name no item: residue for the report."""
        return [e for e in self.holdings if not e.get("qid")]


def get(cc: str) -> Spec:
    """A country's spec; an empty one (global defaults) when it has no file."""
    path = DIR / f"{cc}.yml"
    data = yaml.safe_load(path.read_text()) if path.exists() else {}
    data = data or {}
    return Spec(
        cc=cc,
        holdings=[e for h in data.get("holdings") or [] for e in h.get("entries") or []],
        forms={str(f["qid"]): str(f["kind"]) for f in data.get("forms") or []},
        not_government=frozenset(str(q["qid"]) for q in data.get("not_government") or []),
        exclude=frozenset(str(q["qid"]) for q in data.get("exclude") or []),
        roles={str(r["role"]): (str(r["property"]), r.get("qualifier")) for r in data.get("roles") or []},
        tiers=tuple(data.get("tiers") or DEFAULT_TIERS),
        state=str(data["state"]) if data.get("state") else None,
        actors={str(a["qid"]): str(a["kind"]) for a in data.get("actors") or []},
    )


def state_qid(cc: str) -> str:
    """The polity whose subdivisions are the regional tier: the spec's state, else rigour's main QID."""
    return get(cc).state or positions.country_qid(cc)


def current_qids(cc: str) -> list[str]:
    """Every QID that names the country now, the spec's state among them. Bodies name any of them as their country."""
    state = get(cc).state
    return eras.current_qids(cc, [state] if state else [])
