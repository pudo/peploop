"""Read a country's spec: what pepcorp knows about one country that code must not.

pepcorp's logic is global. What differs by country lives in
`countries/<cc>.yml`, so a new country is a new file, not a code change:

- `holdings`: official lists of state holdings, each entry `name`, `qid`
  (null when the holding has no item), `holder`, `source`; an entry from a
  city's or district's list of its holdings says `level: municipal` and
  names the holding unit as `unit` (its QID);
- `forms`: state-only legal forms and types (`P31` or `P1454`, matched
  exactly) that mark a body as state, each with the `kind` it is;
- `not_government`: classes the type tree wrongly makes a government body
  in this country;
- `exclude`: classes never a candidate here, beyond the global ones (a
  municipal savings bank, a professional chamber);
- `roles`: seats beyond the global table, `role` → `property` and an
  optional `qualifier` (a party committee secretary in a party state);
- `tiers`: the control tiers whose bodies are written (`national`,
  `regional`, `municipal`), or `international` alone: the spec of the Union's
  bodies and the international organisations seated in it, whose boards are
  written whoever controls them (`eu.yml`);
- `state`: the item the country's items name as their country (`P17`), where
  it is not the one rigour gives (a realm or kingdom around the state);
- `actors`: items that stand for the state or its government here but that
  the type tree cannot place, each with its `kind`: `state` for a legal
  person the items name as owner in the state's place (a state treasury),
  `government` for a government body whose own statements miss the country;
- `parties`: parties whose governing bodies are in scope but whom the party
  lane misses (no member's current seat is on Wikidata), each `{qid, name}`;
- `party_branch_classes`: the classes, beyond political party, that make a
  part of a party one of its branches here (a federal party's state
  associations, typed as associations), matched exactly as `P31`, each
  `{qid, name}`;
- `municipal_classes`: the classes, beyond the global ones
  (`load.MUNICIPAL_CLASSES`), whose instances located in a governed unit of
  50,000 or more are candidates for the municipal tier here (a city's
  utility company, an inter-municipal association), matched exactly as
  `P31`, each `{qid, name}`;
- `categories`: Wikipedia categories that list the country's municipal
  enterprises, each `{lang, title, depth}` (the title without its
  namespace; `depth` as `wikipedia.walk_category` counts it, 1 by default);
- for the `international` tier: `body_classes`, the classes whose instances
  (through any subclass) are the scope's own bodies; `organisation_classes`,
  those whose instances count when headquartered (`P159`) in a member of the
  scope (its `P150`); each `{qid, name}`; and `wikis`, the languages its
  bodies are read in, best first, one article each.
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
    parties: frozenset[str] = frozenset()
    party_branch_classes: frozenset[str] = frozenset()
    municipal_classes: frozenset[str] = frozenset()
    #: (lang, title, depth) of each municipal enterprise category.
    categories: tuple[tuple[str, str, int], ...] = ()
    body_classes: tuple[str, ...] = ()
    organisation_classes: tuple[str, ...] = ()
    wikis: tuple[str, ...] = ()

    @property
    def international(self) -> bool:
        """Whether this is the spec of international bodies: no state actors, no control, boards only."""
        return "international" in self.tiers

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
        parties=frozenset(str(q["qid"]) for q in data.get("parties") or []),
        party_branch_classes=frozenset(str(q["qid"]) for q in data.get("party_branch_classes") or []),
        municipal_classes=frozenset(str(q["qid"]) for q in data.get("municipal_classes") or []),
        categories=tuple((str(c["lang"]), str(c["title"]), int(c.get("depth", 1))) for c in data.get("categories") or []),
        body_classes=tuple(str(q["qid"]) for q in data.get("body_classes") or []),
        organisation_classes=tuple(str(q["qid"]) for q in data.get("organisation_classes") or []),
        wikis=tuple(str(w) for w in data.get("wikis") or []),
    )


def state_qid(cc: str) -> str:
    """The polity whose subdivisions are the regional tier: the spec's state, else rigour's main QID."""
    return get(cc).state or positions.country_qid(cc)


def current_qids(cc: str) -> list[str]:
    """Every QID that names the country now, the spec's state among them. Bodies name any of them as their country."""
    state = get(cc).state
    return eras.current_qids(cc, [state] if state else [])
