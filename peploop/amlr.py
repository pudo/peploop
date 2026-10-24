"""Read the EU AMLR asset: each member state's listed public functions and its governed units.

The AMLR (Reg. 2024/1624, Art. 2(34)) makes PEPs of functions the lanes do
not reach by type alone: heads of municipalities, groupings of municipalities
and metropolitan regions of 50,000 inhabitants or more, and whatever a member
state lists under Art. 43 (Commission notice C/2023/724). All three lanes read
one file per country here, `amlr/<cc>.yml` (`eu.yml` for the Union's own
functions and the rows no state lists), so the unit set and the function list
are measured once:

- `threshold`: the population a unit needs, where the state notified a lower
  one than `POPULATION`;
- `units`: per level (`municipal`, `grouping`, `metro`), the classes whose
  instances are governed units of that level, each `{qid, name}`. A unit's
  `P31` must name the class itself: the type tree is too polluted to walk.
  `grouping` is the governed tier between the municipality and the
  first-level subdivision (Landkreis, powiat, EPCI, provincia); first-level
  subdivisions are the regional tier, not a level here. `exclude` lists units
  the classes wrongly take in, each `{qid, name}`: a city item typed like the
  municipality it lies in, a council area merged away with no end on its item;
- `functions`: the state's list, one entry per sheet row, the source's text
  verbatim and ours beside it. See `Function`.

`expansion` is what grows: the concrete Wikidata items a row stands for, one
entry each, in one of three shapes:

    expansion:
      - {position: Q123}                    # the office itself
      - {body: Q456}                        # a body whose governing seats are the function
      - {level: municipal, office: head}    # that office in every unit of a level
"""

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from peploop import eras, memo, wikidata

DIR = Path(__file__).resolve().parent / "amlr"
#: The AMLR's floor for local units, Art. 2(34)(viii).
POPULATION = 50_000
LEVELS = ("municipal", "grouping", "metro")
#: Which level a unit typed with classes of two levels belongs to: a métropole
#: is also an EPCI, and a Polish city with powiat rights also a powiat.
PRECEDENCE = ("metro", "municipal", "grouping")
#: A unit typed as a former administrative entity, however recorded, is history.
FORMER = "Q19953632"
#: Our reading of which AMLR clause a row falls under. `agency` is a state's own
#: addition beyond the clauses (heads of national agencies and institutions);
#: `eu` a Union function; `viii_local` takes regional and local authorities alike.
CATEGORIES = ("i_executive", "ii_legislature", "iii_party", "iv_courts", "v_audit_cb",
              "vi_diplomat_military", "vii_soe", "viii_local", "ix_io", "eu", "agency")
#: What a row names: one office; one body, whose governing seats are the function; a
#: class of bodies or of their offices ("mayors", "boards of regional enterprises");
#: or nothing a lane can use (a rank, a role with no body).
KINDS = ("position", "body", "body_class", "unusable")


@dataclass(frozen=True)
class Function:
    """One row of a member state's list of prominent public functions."""

    #: The row in the curated sheet; unique across all files.
    row: int
    #: The function as the notice gives it, in English.
    position: str
    #: Our AMLR clause for the row (`CATEGORIES`).
    amlr: str
    #: What the row names (`KINDS`).
    kind: str
    #: The sheet's own status ("Position for territory", "To split", ...).
    status: str = ""
    #: The sheet's category: the directive clause the state filed it under.
    category: str = ""
    #: The function in the state's language, and that language's code.
    local: str | None = None
    lang: str | None = None
    #: The body the function sits in, as the sheet names it.
    organisation: str | None = None
    #: The state's own code for the function and its note, where it gave one.
    identifier: str | None = None
    notes: str | None = None
    #: False while `amlr` and `kind` are a keyword classifier's, unreviewed.
    checked: bool = False
    expansion: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class Spec:
    cc: str
    threshold: int = POPULATION
    #: Class QID → level.
    classes: dict[str, str] = field(default_factory=dict)
    exclude: frozenset[str] = frozenset()
    functions: list[Function] = field(default_factory=list)


def codes() -> list[str]:
    """Every file's code, `eu` included."""
    return sorted(p.stem for p in DIR.glob("*.yml"))


@lru_cache(maxsize=None)
def get(cc: str) -> Spec:
    """A country's asset; an empty one when it has no file."""
    path = DIR / f"{cc}.yml"
    data = (yaml.safe_load(path.read_text()) if path.exists() else {}) or {}
    units = data.get("units") or {}
    return Spec(
        cc=cc,
        threshold=int(data.get("threshold") or POPULATION),
        classes={str(c["qid"]): level for level in LEVELS for c in units.get(level) or []},
        exclude=frozenset(str(u["qid"]) for u in units.get("exclude") or []),
        functions=[Function(**row) for row in data.get("functions") or []],
    )


def functions(cc: str) -> list[Function]:
    """The rows of a country's list, in sheet order."""
    return get(cc).functions


def population(entity: dict[str, Any]) -> int | None:
    """The best-rank `P1082` with the latest point in time; undated values count as oldest."""
    claims = [c for c in entity.get("claims", {}).get("P1082", []) if c.get("rank") != "deprecated"]
    best = [c for c in claims if c.get("rank") == "preferred"] or claims
    dated = []
    for claim in best:
        amount = (claim.get("mainsnak", {}).get("datavalue", {}).get("value") or {}).get("amount")
        if amount is None:
            continue
        times = [q.get("datavalue", {}).get("value", {}).get("time", "")
                 for q in claim.get("qualifiers", {}).get("P585", [])]
        dated.append((max(times, default=""), int(float(amount))))
    return max(dated)[1] if dated else None


def unit_level(entity: dict[str, Any], classes: dict[str, str], current: set[str],
               threshold: int) -> tuple[str, int] | None:
    """The level and population of an item that is a current governed unit, else None.

    A unit is in the country (`P17`), typed directly with one of the level's
    classes, neither dissolved nor former, and populous enough.
    """
    types = set(wikidata.claim_qids(entity, "P31", include_deprecated=False))
    if FORMER in types or wikidata.claim_time(entity, "P576", include_deprecated=False):
        return None
    if not set(wikidata.claim_qids(entity, "P17", include_deprecated=False)) & current:
        return None
    levels = {classes[t] for t in types if t in classes}
    level = next((lv for lv in PRECEDENCE if lv in levels), None)
    pop = population(entity)
    if level is None or pop is None or pop < threshold:
        return None
    return level, pop


CANDIDATES_SQL = """SELECT DISTINCT ?u WHERE {{
  VALUES ?t {{ {classes} }} VALUES ?c {{ {countries} }}
  ?u p:P31/ps:P31 ?t ; wdt:P17 ?c ; wdt:P1082 ?pop . FILTER(?pop >= {threshold})
}}"""


def candidates(classes: list[str], countries: list[str], threshold: int) -> list[str]:
    """Items typed with any of the classes, in the country, with a best-rank population over the threshold."""
    query = CANDIDATES_SQL.format(classes=wikidata.values_block(classes),
                                  countries=wikidata.values_block(countries), threshold=threshold)
    return sorted({r["u"] for r in wikidata.sparql(query)})


def units(cc: str) -> dict[str, tuple[str, int]]:
    """The country's governed units at or above its threshold: QID → (level, population).

    Reach for this wherever the AMLR's local clause decides scope: which
    units' heads are PEPs, which municipal enterprises count. Kept a week.
    """
    spec = get(cc)
    if not spec.classes:
        return {}
    current = eras.current_qids(cc)

    def read() -> dict[str, list[Any]]:
        qids = candidates(sorted(spec.classes), current, spec.threshold)
        ents = wikidata.fetch_items(qids, props="claims")
        found = {q: unit_level(e, spec.classes, set(current), spec.threshold) for q, e in ents.items()
                 if q not in spec.exclude}
        return {q: list(hit) for q, hit in found.items() if hit}

    key = (f"amlr_units:{cc}:{spec.threshold}:" + "|".join(f"{q}={lv}" for q, lv in sorted(spec.classes.items()))
           + ":" + "|".join(sorted(spec.exclude)))
    return {q: (lv, int(pop)) for q, (lv, pop) in memo.cached(key, read, 7 * memo.DAY).items()}
