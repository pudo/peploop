"""Read the EU AMLR asset: each member state's listed public functions and its governed units.

The AMLR (Reg. 2024/1624, Art. 2(34)) makes PEPs of functions the lanes do
not reach by type alone: heads of municipalities, groupings of municipalities
and metropolitan regions of 50,000 inhabitants or more, and whatever a member
state lists under Art. 43 (Commission notice C/2023/724). All three lanes read
them from the country's files, so the unit set and the function list are
measured once. The `amlr` section of `countries/<cc>.yml` is written by hand:

- `threshold`: the population a unit needs, where the state notified a lower
  one than `POPULATION`;
- `units`: per level (`municipal`, `grouping`, `metro`), the classes whose
  instances are governed units of that level, each `{qid, name}`. A unit's
  `P31` must name the class itself: the type tree is too polluted to walk.
  `grouping` is the governed tier between the municipality and the
  first-level subdivision (Landkreis, powiat, EPCI, provincia); first-level
  subdivisions are the regional tier, not a level here. `exclude` lists units
  the classes wrongly take in, each `{qid, name}`: a city item typed like the
  municipality it lies in, a council area merged away with no end on its item.

`countries/<cc>.amlr.yml` (`eu` for the Union's own functions and the rows no
state lists) is generated: its `functions` are the state's list, one entry per
sheet row, the source's text verbatim and ours beside it. See `Function`.

`expansion` is what grows: the concrete Wikidata items a row stands for, one
entry each, in one of four shapes:

    expansion:
      - {position: Q123}                    # the office itself
      - {body: Q456}                        # a body whose governing seats are the function
      - {level: municipal, office: head}    # that office in every unit of a level
      - {tier: national, bodies: enterprise}  # the bodies pepcorp covers at that tier

Each entry may say how it was found (`by`, `BY`); one that does not was
written by hand. `amlr_expand` grows the expansions and `amlr_report` reads
them back as coverage; `save` writes a file back with its rows as they were.
"""

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from peploop import countries, eras, memo, wikidata

#: The generated function lists, beside the country files.
SUFFIX = ".amlr.yml"
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
#: How an expansion entry was found: a model's check of search candidates, or by hand.
BY = ("model", "hand")
#: The office a level rule names in each unit: the head of its executive.
OFFICES = ("head",)
#: pepcorp's tiers and kinds of body, for a row naming a class of state bodies.
TIERS = ("national", "regional", "municipal")
BODY_KINDS = ("enterprise", "institution")


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
    """Every function list's code, `eu` included."""
    return sorted(p.name.removesuffix(SUFFIX) for p in countries.DIR.glob(f"*{SUFFIX}"))


def path(cc: str) -> Path:
    """A country's generated function list."""
    return countries.DIR / f"{cc}{SUFFIX}"


def unit_block(cc: str) -> dict[str, Any]:
    """A country's hand-written `amlr` section as written: `units` by level, `exclude`, `threshold`."""
    return countries.section(cc, "amlr") or {}


@lru_cache(maxsize=None)
def get(cc: str) -> Spec:
    """A country's asset; an empty one when it has neither section nor list."""
    block = unit_block(cc)
    units = block.get("units") or {}
    data = (yaml.safe_load(path(cc).read_text()) if path(cc).exists() else {}) or {}
    return Spec(
        cc=cc,
        threshold=int(block.get("threshold") or POPULATION),
        classes={str(c["qid"]): level for level in LEVELS for c in units.get(level) or []},
        exclude=frozenset(str(u["qid"]) for u in units.get("exclude") or []),
        functions=[Function(**row) for row in data.get("functions") or []],
    )


def functions(cc: str) -> list[Function]:
    """The rows of a country's list, in sheet order."""
    return get(cc).functions


QID = re.compile(r"^Q[1-9]\d*$")


def entry_ok(entry: Any) -> bool:
    """Whether an expansion entry has one of the four shapes, with a known `by` if any."""
    if not isinstance(entry, dict):
        return False
    if "by" in entry and entry["by"] not in BY:
        return False
    keys = set(entry) - {"by"}
    if keys in ({"position"}, {"body"}):
        return bool(QID.match(str(entry[keys.pop()])))
    if keys == {"level", "office"}:
        return entry["level"] in LEVELS and entry["office"] in OFFICES
    return keys == {"tier", "bodies"} and entry["tier"] in TIERS and entry["bodies"] in BODY_KINDS


class _Literal(str):
    """A text with line breaks, written as a YAML block so the sheet's text stays readable."""


class _Dumper(yaml.SafeDumper):
    pass


_Dumper.add_representer(_Literal, lambda d, s: d.represent_scalar("tag:yaml.org,2002:str", s, style="|"))


def _blocks(value: Any) -> Any:
    if isinstance(value, str) and "\n" in value:
        return _Literal(value)
    if isinstance(value, dict):
        return {k: _blocks(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_blocks(v) for v in value]
    return value


def read_raw(cc: str) -> tuple[str, dict[str, Any]]:
    """A file's leading comment and its data as plain YAML, for a writer that must keep both."""
    text = path(cc).read_text()
    lines = text.split("\n")
    n = next((i for i, line in enumerate(lines) if not line.startswith("#")), len(lines))
    return "".join(f"{line}\n" for line in lines[:n]), yaml.safe_load(text) or {}


def dump(data: dict[str, Any]) -> str:
    """A file's data in the layout every file is written in."""
    return yaml.dump(_blocks(data), Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=110,
                     default_flow_style=None)


def save(cc: str, header: str, data: dict[str, Any]) -> None:
    """Write a file back in the layout it was written in: an unchanged file comes out byte for byte."""
    path(cc).write_text(header + dump(data), encoding="utf-8")
    get.cache_clear()


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


#: The classes a unit's head office is a kind of, through its `P279` chain: one
#: definition for what the report counts, the back-link links and `mint_units`
#: makes, so a minted office is the head office the other two look for. Mayor
#: and head of government reach most; the rest are heads no such chain reaches,
#: measured over the offices scoped to the EU's ≥50k units.
HEAD_CLASSES = {
    "Q30185": "mayor",
    "Q2285706": "head of government",
    "Q514725": "Landrat",
    "Q23090514": "president of departmental council",
    "Q61968143": "président d'EPCI à fiscalité propre",
    "Q29968251": "président de communauté de communes",
    "Q3911031": "province president",
    "Q40342479": "president of provincial deputation",
    "Q43291899": "president of comarcal council of Catalonia",
    # Finland's kaupunginjohtaja, the municipality's executive head where no
    # pormestari is elected: 6 of 13 existing Finnish head offices.
    "Q496728": "municipal manager",
    # Poland's starosta of a powiat: no powiat has a head office yet, and the
    # generic title is the one item to subclass.
    "Q7231714": "starosta",
}
HEADS = frozenset(HEAD_CLASSES)

#: The offices scoped to a unit or its council (`P1001`, `P2389`, `P642`), the
#: way the back-link reads scope; and which of them are head offices. Ended
#: offices count: a renamed office is the back-link's to sort out, not a new
#: one to make.
SCOPED_SQL = """SELECT DISTINCT ?o ?x WHERE {{ VALUES ?x {{ {values} }}
  {{ ?o p:P1001/ps:P1001 ?x }} UNION {{ ?o p:P2389/ps:P2389 ?x }} UNION {{ ?o p:P642/ps:P642 ?x }} }}"""
HEAD_SQL = """SELECT DISTINCT ?o WHERE {{ VALUES ?o {{ {values} }} VALUES ?head {{ {heads} }}
  ?o wdt:P279/wdt:P279* ?head . }}"""


def scoped_heads(qids: list[str]) -> set[str]:
    """The units some head office is scoped to, directly or through their council."""
    ents = wikidata.fetch_items(qids, props="claims") if qids else {}
    targets: dict[str, set[str]] = {}
    for qid in qids:
        for x in (qid, *wikidata.claim_qids(ents.get(qid, {}), "P194", include_deprecated=False)):
            targets.setdefault(x, set()).add(qid)
    rows = wikidata.bisect(lambda chunk: wikidata.sparql(
        SCOPED_SQL.format(values=wikidata.values_block(chunk))), sorted(targets), size=60) if targets else []
    offices = sorted({r["o"] for r in rows})
    heads = wikidata.values_block(sorted(HEADS))
    found = {r["o"] for r in wikidata.bisect(lambda chunk: wikidata.sparql(
        HEAD_SQL.format(values=wikidata.values_block(chunk), heads=heads)), offices, size=60)} if offices else set()
    return {unit for r in rows if r["o"] in found for unit in targets[r["x"]]}
