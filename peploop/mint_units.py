"""Mint the offices every unit of a local level has, from each unit's own article.

The person lane mints an office only when a seeded person's article names it,
so the mayoralties and council seats of places whose mayor has no article stay
missing. A census entry with `per: units` names a level (the class its units
are instances of, such as a country's local government areas) and the office
each unit has; this module turns every current unit that lacks the office into
a candidate, when the unit's own article names a current holder. The candidate
then goes through `mint.verify` like any other: the named holder is its one
attestation, so the floor, the guard, the model and `mint --submit` all apply
unchanged.

A level whose units mostly have the office already is completed on the
units' articles alone. One where fewer than half do is started only where the
entry gives a `source` for that subdivision: a law or official list saying
every unit has the office.
"""

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence
from urllib.parse import unquote

import yaml
from psycopg.types.json import Jsonb

from peploop import db, offices, positions, wikidata, wikipedia
from peploop.mint import CENSUS_DIR, PROTECTED_STATUSES

#: A unit typed as a former administrative entity, however recorded, is history.
FORMER = "Q19953632"

#: The share of a subdivision's units that must have the office already for
#: the set to be completed on the units' articles alone.
COMPLETE_AT = 0.5

#: The infobox titles a municipality's head is given. Whatever the title, the
#: seat subclasses mayor, as 171 of one state's 185 existing mayoralties do.
SHIRE_PRESIDENT = ("president", "shire president")
HEAD_LINE = re.compile(r"^[•·\s]*(?P<title>(?:lord )?mayor|(?:shire )?president)\s*:\s*(?P<name>.+)$", re.I)
#: What an infobox puts where nobody holds the office.
VACANT = re.compile(r"\b(vacant|administrator|none|tba|suspended|dismissed)\b", re.I)
#: The headings an article's section on its council goes under.
COUNCIL_HEADING = re.compile(r"^##\s*((?:elected |current |the )?council|councillors|"
                             r"(?:current )?composition|governance|government|local government|politics)\b",
                             re.I)
#: The type words a unit's label wraps its place name in: "City of X", "X Shire Council".
UNIT_WORDS = re.compile(
    r"^(?:the\s+)?(?:(?:aboriginal\s+)?shire|city|rural city|town|municipality|borough|region|"
    r"municipal district|district council|regional council|council)\s+of\s+(?:the\s+)?"
    r"|\s+(?:(?:city|regional|shire|municipal|town|district|aboriginal shire|rural city)\s+)?"
    r"(?:council|shire|region)$",
    re.I,
)


@dataclass
class Level:
    """One `per: units` census entry: the office every unit of a level has."""

    key: str
    archetype: str
    institution_class: str
    #: The class the level's units are instances of, directly or by a subclass.
    of: str
    #: Per subdivision QID, a source saying every unit of it has the office.
    sources: dict[str, str] = field(default_factory=dict)


@dataclass
class Unit:
    qid: str
    label: str
    title: str
    subdivision: str | None
    council: str | None
    council_label: str | None
    #: Offices of this archetype already scoped to the unit.
    has_office: bool = False


def levels(cc: str, path: Path | None = None) -> list[Level]:
    """The country's `per: units` census entries."""
    path = path or CENSUS_DIR / f"{cc}.yml"
    if not path.exists():
        return []
    out = []
    for entry in yaml.safe_load(path.read_text()) or []:
        if entry.get("per") != "units":
            continue
        out.append(Level(key=entry["key"], archetype=entry["archetype"],
                         institution_class=entry["class"], of=entry["of"],
                         sources=dict(entry.get("sources") or {})))
    return out


UNITS_SQL = """SELECT DISTINCT ?u ?uLabel ?article ?sub ?council ?councilLabel WHERE {{
  ?u wdt:P31/wdt:P279* wd:{of} ; wdt:P17 wd:{state} .
  FILTER NOT EXISTS {{ ?u wdt:P576 [] }}
  FILTER NOT EXISTS {{ ?u wdt:P31/wdt:P279?/wdt:P279? wd:{former} }}
  ?article schema:about ?u ; schema:isPartOf <https://en.wikipedia.org/> .
  OPTIONAL {{ ?u wdt:P131 ?sub . VALUES ?sub {{ {subs} }} }}
  OPTIONAL {{ ?u wdt:P194 ?council }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}"""

#: Units that already have an office of the archetype's parent: scoped to them
#: under `P1001`, or named as their head of government.
HELD_SQL = """SELECT DISTINCT ?u WHERE {{
  ?u wdt:P31/wdt:P279* wd:{of} ; wdt:P17 wd:{state} .
  {{ ?o wdt:P1001 ?u ; wdt:P279/wdt:P279* wd:{parent} . }} {head}
}}"""


def units(level: Level, state: str, subdivisions: Sequence[str], parent: str) -> list[Unit]:
    """Every current unit of the level with an English article, read live."""
    subs = " ".join(f"wd:{q}" for q in subdivisions) or "wd:Q0"
    rows = wikidata.sparql(UNITS_SQL.format(of=level.of, state=state, subs=subs, former=FORMER))
    head = "UNION { ?u wdt:P1313 [] }" if parent == "Q30185" else ""
    held = {r["u"] for r in wikidata.sparql(HELD_SQL.format(of=level.of, state=state,
                                                            parent=parent, head=head))}
    out: dict[str, Unit] = {}
    for r in rows:
        qid = r["u"]
        title = r["article"].rsplit("/wiki/", 1)[-1].replace("_", " ")
        unit = out.setdefault(qid, Unit(qid, r.get("uLabel") or qid, unquote(title), None, None, None,
                                        has_office=qid in held))
        unit.subdivision = unit.subdivision or r.get("sub")
        if r.get("council") and unit.council is None:
            unit.council, unit.council_label = r["council"], r.get("councilLabel")
    return sorted(out.values(), key=lambda u: u.qid)


def place_name(label: str) -> str:
    """The place a unit's label names, without its type words: "City of X" is X."""
    return UNIT_WORDS.sub("", label.strip()).strip() or label.strip()


def head_of(text: str) -> tuple[str, str] | None:
    """The head's title and name from an article's infobox lines, or None when vacant."""
    for line in text.splitlines():
        found = HEAD_LINE.match(line.strip())
        if not found:
            continue
        name = re.sub(r"\[\d+\]|\(.*?\)|^(?:Cr|Clr|Councillor)\.?\s+", "", found["name"]).strip(" ,;")
        if not name or VACANT.search(name):
            return None
        return found["title"].strip().lower(), name
    return None


def council_quote(text: str, limit: int = 380) -> str | None:
    """The first prose under the article's sections on its council, or None."""
    active = False
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("##"):
            active = bool(COUNCIL_HEADING.match(line))
            continue
        if active and len(line) > 25:
            return line[:limit]
    return None


#: A lead that puts the unit in the past: abolished, though nothing on its item says so.
PAST = re.compile(r"\b(?:was|were)\s+(?:an?|the)\s+[^.]{0,60}?\b(?:local government area|shire|city|town|"
                  r"municipality|borough|council|division)\b", re.I)


def lead(text: str) -> str:
    """The article's first sentence of prose, past the infobox lines."""
    for line in text.splitlines():
        if len(line) > 80 and not line.startswith("##") and ":" not in line[:40]:
            return line
    return ""


def draft_for(level: Level, unit: Unit, text: str, url: str) -> tuple[dict[str, Any] | None, str]:
    """The candidate's draft for one unit, or None with the reason it has none."""
    if PAST.search(lead(text)[:250]):
        return None, "unit/former"
    head = head_of(text)
    if head is None:
        return None, "unit/no-named-holder"
    title, name = head
    place = place_name(unit.label)
    source = level.sources.get(unit.subdivision or "")
    evidence = {"qid": unit.qid, "label": unit.label, "url": url, "holder": name, "source": source}
    if level.archetype == "mayor":
        parent = "Q30185"
        word = "Shire President" if title in SHIRE_PRESIDENT else title.title()
        label = f"{word} {of_unit(unit.label)}"
        evidence["quote"] = f"{title.title()}: {name}"
        single = True
    elif level.archetype == "councillor":
        quote = council_quote(text)
        if quote is None:
            return None, "unit/no-council-section"
        parent = "Q708492"
        council = unit.council_label or council_name(text, place)
        if not council:
            return None, "unit/no-council-name"
        label = f"member of {council}"
        evidence["quote"] = f"{quote} … {title.title()}: {name} (a member of the council)"
        single = False
    else:
        raise ValueError(f"{level.key}: no unit lane for archetype {level.archetype!r}")
    return {
        "decision": "office", "archetype": level.archetype, "labels": {"en": label},
        "institution_class": level.institution_class, "single_seat": single,
        "parent_qid": parent, "body_qid": unit.council, "jurisdiction_qid": unit.qid,
        "jurisdiction_name": unit.label, "evidence": evidence["quote"],
        "reason": f"every unit of the level has the office; {unit.label}'s article names its holder",
        "unit": evidence,
    }, "unit/drafted"


def of_unit(label: str) -> str:
    """"of" and the unit's full name, as the existing items word it: "of the Shire of X", "of X Shire"."""
    return f"of the {label}" if re.match(r"^(?:the\s+)?\w[\w ]*? of ", label, re.I) and not label.lower().startswith("the ") \
        else f"of {label}"


COUNCIL_NAME = re.compile(r"\b((?:[A-Z][\w'’-]*\s){1,5}Council)\b")


def council_name(text: str, place: str) -> str | None:
    """The council's name as the article writes it ("Clarence City Council"), or None."""
    for found in COUNCIL_NAME.finditer(text):
        name = re.sub(r"^(?:The|A|An)\s+", "", found.group(1).strip())
        if name.lower() != "council" and place.split()[0].lower() in name.lower():
            return name
    return None


def started(units_: Sequence[Unit]) -> dict[str | None, float]:
    """Per subdivision, the share of its units that already have the office."""
    total, held = Counter(), Counter()
    for u in units_:
        total[u.subdivision] += 1
        held[u.subdivision] += u.has_office
    return {sub: held[sub] / total[sub] for sub in total}


#: The statuses of a mention candidate still in the run: decided for an
#: item, or not yet decided.
LIVE_STATUSES = ("categorized", "guarded", "found", "loaded", "creating", "created")


def mention_seats(cc: str, ctx: "mint.Context | None" = None) -> set[tuple[str, str]]:
    """(archetype, town) of every local seat the run's mention candidates name."""
    from peploop import mint
    ctx = ctx or mint.Context(cc)
    rows = db.conn().execute(
        "SELECT archetype, draft, spec FROM office_candidate WHERE country = %s"
        " AND NOT ('unit' = ANY(origin)) AND status = ANY(%s) AND archetype = ANY(%s)",
        (cc, list(LIVE_STATUSES), [a for a, s in offices.ARCHETYPES.items() if s.level == "municipality"]),
    ).fetchall()
    out = set()
    for archetype, draft, spec in rows:
        draft = draft or {}
        place = (spec or {}).get("jurisdiction_qid") or draft.get("jurisdiction_qid")
        if not place or place in ctx.levels:
            found = ctx.local_place(draft.get("jurisdiction_name"))
            place = found[0] if found else None
        if place:
            out.add((archetype, place))
    return out


def supersede(cc: str, ref: str) -> None:
    """Take a unit's candidate out of the run, unless an item was made from it."""
    db.conn().execute(
        "UPDATE office_candidate SET status = 'superseded', updated_at = now()"
        " WHERE country = %s AND ref = %s AND status <> ALL(%s) AND decided_by IS NULL",
        (cc, ref, list(PROTECTED_STATUSES)))


UPSERT_SQL = (
    "INSERT INTO office_candidate (country, ref, origin, institution_class, archetype, single_seat,"
    " draft, holders, current_holders, source_url, status, problems)"
    " VALUES (%s, %s, '{unit}', %s, %s, %s, %s, 1, 1, %s, 'categorized', '{}')"
    " ON CONFLICT (country, ref) DO UPDATE SET draft = EXCLUDED.draft,"
    " single_seat = EXCLUDED.single_seat, source_url = EXCLUDED.source_url,"
    " status = 'categorized', rule = NULL, updated_at = now()"
    " WHERE office_candidate.status <> ALL(%s) AND office_candidate.decided_by IS NULL"
    " AND office_candidate.draft IS DISTINCT FROM EXCLUDED.draft"
)


def build(cc: str, log: Callable[[str], None] = print,
          read: Callable[[str], tuple[str, str]] | None = None) -> Counter[str]:
    """Write a candidate for every unit of every `per: units` level that lacks its office."""
    def _read(title: str) -> tuple[str, str]:
        art = wikipedia.fetch_article("en", title)
        return wikipedia.html_to_text(art["html"]), art["url"]

    read = read or _read
    state = positions.country_qid(cc)
    claimed = mention_seats(cc)
    subs = [q for q, _labels in offices.subdivisions(state)]
    stats: Counter[str] = Counter()
    for level in levels(cc):
        parent = offices.ARCHETYPES[level.archetype].parent
        found = units(level, state, subs, parent)
        shares = started(found)
        log(f"{level.key}: {len(found)} units, " + ", ".join(
            f"{sub or '?'} {share:.0%}" for sub, share in sorted(shares.items(), key=lambda kv: str(kv[0]))))
        for unit in found:
            if unit.has_office:
                stats[f"{level.key}:has-office"] += 1
                continue
            if (level.archetype, unit.qid) in claimed:
                # The run's holders name this seat: their candidate makes it, and feeds them.
                stats[f"{level.key}:mention-has-it"] += 1
                supersede(cc, f"unit/{level.key}/{unit.qid}")
                continue
            if shares[unit.subdivision] < COMPLETE_AT and not level.sources.get(unit.subdivision or ""):
                stats[f"{level.key}:set-not-started"] += 1
                continue
            try:
                text, url = read(unit.title)
            except Exception as exc:  # noqa: BLE001 -- one unreadable article is one skip
                log(f"{unit.qid} {unit.title}: unreadable: {exc}")
                stats[f"{level.key}:unreadable"] += 1
                continue
            draft, why = draft_for(level, unit, text, url)
            stats[f"{level.key}:{why}"] += 1
            if draft is None:
                # A unit drafted by an earlier run, whose article no longer qualifies.
                supersede(cc, f"unit/{level.key}/{unit.qid}")
                continue
            db.conn().execute(UPSERT_SQL, (
                cc, f"unit/{level.key}/{unit.qid}", level.institution_class, level.archetype,
                draft["single_seat"], Jsonb(draft), url, list(PROTECTED_STATUSES)))
    return stats
