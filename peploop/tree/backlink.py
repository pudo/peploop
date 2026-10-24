"""Link each AMLR unit to the office that heads it, and the office back to the unit.

The AMLR makes PEPs of the heads of every municipality, grouping and metro
region of 50,000 or more (`amlr.units`). A consumer reaches the head from the
unit through the unit's `P1313` and the unit from the office through its
`P1001`; half the municipalities and almost no groupings carry the first,
though most of their head offices exist, scoped to the unit. This lane writes
the missing link both ways and creates nothing: a unit with no head office is
listed for peploop's `mint`.

- A unit with no `P1313` gets one when exactly one current head office is
  scoped to it (`P1001` the unit, or `P2389`/`P642` the unit or its council
  `P194`). Two current heads (a lord mayor and a mayor, a governor and a
  mayor) are listed, never chosen between.
- An office in a unit's `P1313`, or about to be, gets `P1001` the unit and
  `P17` the state where it has none, under the repair's jurisdiction and era
  rules. A unit's `P1313` that names a generic class, or an office another
  item also names, is not ours to follow or fix.

    python -m peploop.cli tree backlink <cc>… | --eu

Lines go to `data/peptree/<cc>/<cc>-backlink-<date>.qs`, sent apart from the
repair's with `tree send --lane backlink`; the report and the mint queue to
`data/peptree/backlink/`.
"""

import datetime as dt
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from peploop import amlr, amlr_report, positions, typegraph, wikidata
from peploop.tree import country as countries
from peploop.tree import gaps, qs, rules, signals
from peploop.tree.load import has, values

LANE = "backlink"
OUT = qs.OUT_DIR / LANE
#: The heads of a unit's executive that no mayor or head-of-government chain
#: reaches, measured over the offices scoped to the EU's ≥50k groupings.
LOCAL_HEADS = {
    "Q514725": "Landrat",
    "Q23090514": "president of departmental council",
    "Q61968143": "président d'EPCI à fiscalité propre",
    "Q29968251": "président de communauté de communes",
    "Q3911031": "province president",
    "Q40342479": "president of provincial deputation",
    "Q43291899": "president of comarcal council of Catalonia",
}
HEADS = frozenset(amlr_report.HEAD_CLASSES) | frozenset(LOCAL_HEADS)
#: Head classes of a regime that ended, whose office items rarely carry their own end:
#: the fascist podestà (1926-1945) reaches mayor.
FORMER_HEADS = frozenset({"Q694019"})
#: The statements that scope an office to a unit or to the unit's council.
SCOPE_PROPS = ("P1001", "P2389", "P642")
#: Types that make an item history, however its end is recorded.
FORMER = (amlr.FORMER,)


@dataclass
class Office:
    qid: str
    entity: dict[str, Any]
    #: The office's type closure (`typegraph.close`).
    types: set[str] = field(default_factory=set)
    #: Every item whose `P1313` names this office, at any rank.
    named_by: set[str] = field(default_factory=set)


@dataclass
class Plan:
    """What the lane does for one unit."""

    unit: str
    #: `line`, or why not: `linked`, `two_heads`, `only_ended`, `no_office`, or
    #: `heads_another` (the one head office is scoped through a council, and another item's `P1313`).
    verdict: str
    office: str | None = None
    #: The current head offices it chose among, or the ended ones it found.
    heads: list[str] = field(default_factory=list)
    #: The office of an existing `P1313`, when it is the unit's own office to complete.
    linked: str | None = None


def is_head(types: set[str]) -> bool:
    """Whether an office heads a unit's executive, by its type closure."""
    return bool(types & HEADS)


def ended(entity: dict[str, Any]) -> bool:
    """An office abolished (`P576`), ended (`P582`) or typed history."""
    if wikidata.claim_time(entity, "P576", include_deprecated=False):
        return True
    if wikidata.claim_time(entity, "P582", include_deprecated=False):
        return True
    return bool(set(values(entity, "P31")) & set(FORMER))


def scoped_now(entity: dict[str, Any], targets: set[str]) -> bool | None:
    """Whether an office is scoped to one of `targets` now: True, False when every such statement ended, None when unscoped."""
    found = [c for p in SCOPE_PROPS for c in entity.get("claims", {}).get(p, [])
             if c.get("rank") != "deprecated"
             and (c.get("mainsnak", {}).get("datavalue", {}).get("value") or {}).get("id") in targets]
    if not found:
        return None
    return any(not c.get("qualifiers", {}).get("P582") for c in found)


def own_office(unit: str, office: Office | None, generic: set[str] | frozenset[str]) -> bool:
    """Whether a `P1313` target is this unit's own head office, so the lane may complete it.

    A generic class ("mayor", "mayor of a place in France") or an office other
    items name too is someone else's to fix.
    """
    return (office is not None and office.qid not in generic and office.named_by <= {unit}
            and is_head(office.types))


def plan_unit(unit: str, entity: dict[str, Any], offices: dict[str, Office],
              generic: set[str] | frozenset[str] = frozenset()) -> Plan:
    """Decide one unit: which office its `P1313` should name, or why none.

    `offices` holds every office scoped to the unit or named by its `P1313`.
    """
    linked = values(entity, "P1313", any_rank=True)
    if linked:
        own = linked[0] if len(linked) == 1 and own_office(unit, offices.get(linked[0]), generic) else None
        return Plan(unit, "linked", linked=own)
    targets = {unit, *values(entity, "P194")}
    heads, gone = [], []
    for qid, office in sorted(offices.items()):
        if qid in generic or not is_head(office.types):
            continue
        now = scoped_now(office.entity, targets)
        if now is None:
            continue
        if not now or ended(office.entity) or office.types & FORMER_HEADS:
            gone.append(qid)
        else:
            heads.append(qid)
    if len(heads) > 1:
        return Plan(unit, "two_heads", heads=heads)
    if not heads:
        return Plan(unit, "only_ended" if gone else "no_office", heads=gone)
    # A town and the municipality it seats often share one head office; one
    # scoped only through a council and linked elsewhere may head the other.
    head = offices[heads[0]]
    if head.named_by - {unit} and unit not in values(head.entity, "P1001"):
        return Plan(unit, "heads_another", heads=heads)
    return Plan(unit, "line", office=heads[0], heads=heads)


def office_decisions(office: Office, unit: str, country: countries.Country) -> list[dict[str, Any]]:
    """The `P1001` and `P17` an office of the unit lacks, decided by the repair's own rules.

    `P17` is wanted only where the repair would want it (`gaps.wants_p17`),
    never beside a `P1001` that already names the state
    (`rules.p17_same_as_jurisdiction`), and only for a state that existed
    while the office did (`signals.era_ok`).
    """
    ent = office.entity
    out = []
    if not has(ent, "P1001"):
        out.append({"qid": office.qid, "prop": "P1001", "value": unit, "disposition": "apply", "rule": "back_link"})
    elif unit not in values(ent, "P1001", any_rank=True):
        return []  # scoped elsewhere: whose office it is is the repair's question
    if not has(ent, "P17") and gaps.wants_p17(country, {"kind": "subnational"}) and not gaps.p17_in_p1001(country, ent):
        facts = signals.Facts(item={"entity": ent, "holder_rows": []}, country=country,
                              places=signals.Places([]), sib=signals.Siblings())
        ok = signals.era_ok(facts, country.qid)
        out.append({"qid": office.qid, "prop": "P17", "value": country.qid,
                    "disposition": "apply" if ok else "skip", "rule": "jurisdiction" if ok else "era_mismatch"})
    rules.p17_same_as_jurisdiction(out, ent)
    return out


def unit_line(unit: str, office: str) -> str:
    return qs.line({"qid": unit, "prop": "P1313", "value": office})


# --- reading one country -----------------------------------------------------------

SCOPED_SQL = """SELECT DISTINCT ?o WHERE {{ VALUES ?x {{ {values} }}
  {{ ?o p:P1001/ps:P1001 ?x }} UNION {{ ?o p:P2389/ps:P2389 ?x }} UNION {{ ?o p:P642/ps:P642 ?x }} }}"""
NAMED_SQL = """SELECT DISTINCT ?o ?x WHERE {{ VALUES ?o {{ {values} }} ?x p:P1313/ps:P1313 ?o }}"""


def _ask(template: str, qids: list[str]) -> list[dict[str, str]]:
    return wikidata.bisect(lambda chunk: wikidata.sparql(template.format(values=wikidata.values_block(chunk))),
                           qids, size=60) if qids else []


@dataclass
class Units:
    """One country's units and the offices around them, read live."""

    cc: str
    units: dict[str, tuple[str, int]]
    entities: dict[str, dict[str, Any]]
    offices: dict[str, Office]


def read(cc: str) -> Units:
    """A country's units, the offices scoped to them or named by their `P1313`, and who else names each."""
    units = amlr.units(cc)
    ents = wikidata.fetch_items(sorted(units), props="claims|labels")
    targets = sorted(set(units) | {c for e in ents.values() for c in values(e, "P194")})
    found = {r["o"] for r in _ask(SCOPED_SQL, targets)}
    found |= {o for e in ents.values() for o in values(e, "P1313", any_rank=True)}
    office_ents = wikidata.fetch_items(sorted(found), props="claims|labels")
    closure = typegraph.close({q: typegraph.targets(e) for q, e in office_ents.items()})
    named: dict[str, set[str]] = defaultdict(set)
    for r in _ask(NAMED_SQL, sorted(office_ents)):
        named[r["o"]].add(r["x"])
    offices = {q: Office(q, e, closure.get(q, set()), named.get(q, set())) for q, e in office_ents.items()}
    return Units(cc, units, ents, offices)


def scoped_to(c: Units, unit: str) -> dict[str, Office]:
    """The offices scoped to a unit or its council, and the one its `P1313` names."""
    ent = c.entities.get(unit, {})
    targets = {unit, *values(ent, "P194")}
    mine = {q: o for q, o in c.offices.items() if scoped_now(o.entity, targets) is not None}
    for q in values(ent, "P1313", any_rank=True):
        if q in c.offices:
            mine[q] = c.offices[q]
    return mine


@dataclass
class Result:
    cc: str
    plans: list[tuple[str, Plan]]  # (level, plan)
    lines: list[str]
    office_skips: list[dict[str, Any]]
    labels: dict[str, str]
    populations: dict[str, int]


def run_country(cc: str, generic: set[str], log: Callable[[str], None]) -> Result:
    """Plan one country's back-links and the statements their offices lack; write its lines."""
    c = read(cc)
    state = countries.get(cc)
    plans, lines, skips = [], [], []
    decided: set[tuple[str, str]] = set()
    for unit, (level, _pop) in sorted(c.units.items()):
        ent = c.entities.get(unit)
        if ent is None:
            continue
        plan = plan_unit(unit, ent, scoped_to(c, unit), generic)
        plans.append((level, plan))
        office = plan.office or plan.linked
        if plan.office:
            lines.append(unit_line(unit, plan.office))
        if office and (office, unit) not in decided:
            decided.add((office, unit))
            for d in office_decisions(c.offices[office], unit, state):
                if d["disposition"] == "apply":
                    lines.append(qs.line(d))
                else:
                    skips.append(d)
    lines = sorted(dict.fromkeys(lines))
    errors = qs.validate(lines)
    if errors:
        log(f"{cc}: local validation failed: " + "; ".join(errors[:5]))
    path = qs.write(cc, lines, lane=LANE)
    log(f"{path}: {len(lines)} lines")
    labels = {q: wikidata.best_label(e, ("en", *state.langs)) or "" for q, e in
              [*c.entities.items(), *((q, o.entity) for q, o in c.offices.items())]}
    return Result(cc, plans, lines, skips, labels, {u: p for u, (_, p) in c.units.items()})


# --- the report ----------------------------------------------------------------------

#: The properties this lane writes: the unit's link, then the office's.
PROPS = ("P1313", "P1001", "P17")
VERDICTS = ("line", "linked", "two_heads", "heads_another", "only_ended", "no_office")


def render(results: list[Result]) -> str:
    """Counts by country and level, then the units listed by name: ambiguous, and with no head office."""
    day = dt.date.today().isoformat()
    out = [f"# AMLR back-links ({day})", "",
           "Per country and level: units, and what the lane did for each. `line` plans the unit's `P1313`;",
           "`linked` already has one; the rest are skipped.", "",
           "| cc | level | units | " + " | ".join(VERDICTS) + " |",
           "|---|---|---" + "|---" * len(VERDICTS) + "|"]
    total: Counter[str] = Counter()
    for r in results:
        for level in amlr.LEVELS:
            mine = [p for lv, p in r.plans if lv == level]
            if not mine:
                continue
            n = Counter(p.verdict for p in mine)
            total.update(n)
            out.append(f"| {r.cc} | {level} | {len(mine)} | " + " | ".join(str(n.get(v, 0)) for v in VERDICTS) + " |")
    out += ["", "Totals: " + ", ".join(f"{v} {total.get(v, 0)}" for v in VERDICTS), "",
            "## Lines by country", "", "| cc | " + " | ".join(PROPS) + " |", "|---" * (len(PROPS) + 1) + "|"]
    for r in results:
        n = Counter(qs.statements([ln])[0][1] for ln in r.lines)
        out.append(f"| {r.cc} | " + " | ".join(str(n.get(p, 0)) for p in PROPS) + " |")
    out.append("")
    for verdict, title in (("two_heads", "Two current head offices: skipped, not guessed"),
                           ("heads_another", "The one head office is another item's P1313"),
                           ("only_ended", "Only ended head offices"),
                           ("linked_foreign", "P1313 names no office of the unit's own (a generic class, a shared office): not completed")):
        rows = []
        for r in results:
            for lv, p in r.plans:
                if verdict == "linked_foreign":
                    if p.verdict == "linked" and p.linked is None:
                        rows.append(f"- {r.cc} {lv} {p.unit} {r.labels.get(p.unit, '')}")
                elif p.verdict == verdict:
                    heads = "; ".join(f"{h} {r.labels.get(h, '')}" for h in p.heads)
                    rows.append(f"- {r.cc} {lv} {p.unit} {r.labels.get(p.unit, '')}: {heads}")
        out += [f"## {title} ({len(rows)})", "", *rows, ""]
    skipped = [(r.cc, d) for r in results for d in r.office_skips]
    if skipped:
        out += [f"## Office statements skipped ({len(skipped)})", ""]
        out += [f"- {cc} {d['qid']} {d['prop']} {d['value']}: {d['rule']}" for cc, d in skipped]
        out.append("")
    queue = mint_queue(results)
    out += [f"## No head office: the mint queue ({len(queue)})", "",
            "| cc | level | units |", "|---|---|---|"]
    for (cc, level), count in sorted(Counter((cc, lv) for cc, lv, *_ in queue).items()):
        out.append(f"| {cc} | {level} | {count} |")
    out.append("")
    return "\n".join(out)


def mint_queue(results: list[Result]) -> list[tuple[str, str, str, str, int]]:
    """(cc, level, unit, label, population) of every unit with no head office at all."""
    return [(r.cc, lv, p.unit, r.labels.get(p.unit, ""), r.populations.get(p.unit, 0))
            for r in results for lv, p in r.plans if p.verdict == "no_office"]


def write(results: list[Result]) -> tuple[Path, Path]:
    day = dt.date.today().isoformat()
    OUT.mkdir(parents=True, exist_ok=True)
    md = OUT / f"backlink-{day}.md"
    md.write_text(render(results))
    tsv = OUT / f"mint-queue-{day}.tsv"
    tsv.write_text("cc\tlevel\tunit\tlabel\tpopulation\n"
                   + "".join(f"{cc}\t{lv}\t{u}\t{label}\t{pop}\n" for cc, lv, u, label, pop in mint_queue(results)))
    return md, tsv


def run(ccs: list[str], log: Callable[[str], None] = print) -> tuple[Path, Path]:
    """Plan every country's back-links, write each one's lines, and the joint report and mint queue."""
    generic = set(positions.generic_labels())
    results = [run_country(cc, generic, log) for cc in ccs if amlr.get(cc).classes]
    return write(results)
