#!/usr/bin/env python
"""Propose P39 ministerial statements for Ecuador, portfolio by portfolio.

    python scripts/ec_ministers.py --portfolio trabajo turismo deporte

Lane B of tasks/ecuador.md. Ecuador's minister categories subdivide by
portfolio on both wikis, and each portfolio has a Wikidata position item, so
no per-person office guessing is needed — only per-person confirmation.

Two independent channels have to agree before a statement reaches the batch:

* the person is in the portfolio's Wikipedia category, an editorial act on
  its own (candidate generator);
* an `Anexo:` roster row for that portfolio names them, with dates and — for
  most rows — a citation of its own.

Rows the roster names but no category does are kept separately (`era:
roster_only`): the identity is solid, since it comes from the roster's own
wikilink, but only one channel asserts the office. Rows the colour legend
marks `encargado` (acting), rows filed under a pre-ministerial body, and
category members no roster row names all go to review as well.

Writes data/ecuador/verdicts/minister_<portfolio>.jsonl (render_edit_plan.py
schema) and data/ecuador/ministers_audit.md, which lists every roster row with
its resolved identity so the matcher can be eyeballed in full.
"""

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wd.api import best_description, best_label, claim_qids, fetch_entities, sparql
from wd.http import REPO_ROOT, get_text, make_session
from wd.petscan import category_members
from wd.roster import RosterRow, merge_terms, names_match, parse_rosters
from wd.wikipedia import WIKI_API, fetch_html, permalink

OUT_DIR = REPO_ROOT / "data" / "ecuador"

#: Ecuador's present ministry structure dates from the 1979 return to
#: democracy, and the Wikidata items for these portfolios were created for the
#: modern ministries. Anything earlier is a continuity judgment (is an 1861
#: "Ministro del Interior y Relaciones Exteriores" a holder of the 2010 item?),
#: so it is held in the review document rather than batched.
MODERN_FROM = 1979

#: Occupations that make a public-office claim plausible. A name that matches
#: only an item with none of these — es.wikipedia's "Ernesto Albán" is a
#: comedian, its "Carlos Pérez García" a Spanish footballer — is a namesake,
#: not the minister the roster names.
POLITICAL_OCCUPATIONS = {
    "Q82955",    # politician
    "Q185351",   # jurist
    "Q40348",    # lawyer
    "Q193391",   # diplomat
    "Q188094",   # economist
    "Q212238",   # civil servant
    "Q2285706",  # head of government
    "Q1097498",  # military officer (defence portfolios)
}
POLITICAL_WORDS = re.compile(
    r"pol[íi]tic|ministr|minister|diplomat|presiden|alcald|mayor|senador|"
    r"asamble[íi]sta|abogad|jurist|econom|gobernador|prefect",
    re.I,
)

#: Headings of the tables that ARE the office: "Titulares", "Ministros de la
#: cartera de Turismo". The same article also tabulates predecessor agencies
#: (DITURIS, SENADER) and — the trap — sibling ministries carved out of the
#: same sector under headings like "Cartera de Minería" or "Cartera de
#: planificación económica". Those have their own (usually missing) items, and
#: attributing them here is what makes a roster's dates overlap.
MINISTERIAL_HEADING = r"^(?:titulares|ministr[oa]s?)\b"


@dataclass
class Portfolio:
    key: str
    label: str
    target: str
    roster: str
    es_cat: Optional[str] = None
    en_cat: Optional[str] = None
    #: Regex a table's heading must match for its rows to count as this office.
    headings: str = MINISTERIAL_HEADING
    #: When set, no row from this roster is batched — every add is held in the
    #: review document under this era name, pending a convention call.
    hold: Optional[str] = None
    #: Section header pattern → position item, for a roster that spans two
    #: named ministries (Gobierno/Interior). First match wins; a row matching
    #: none falls back to `target`.
    section_targets: Tuple[Tuple[str, str], ...] = ()
    #: Sections inside an accepted table that describe a *different*,
    #: pre-ministerial body — their rows go to review, not the batch.
    review_sections: Tuple[str, ...] = (
        "direccion", "dirección", "corporacion", "corporación", "instituto",
        "consejo", "subsecretar", "secretaría nacional", "secretaria nacional",
    )


PORTFOLIOS: List[Portfolio] = [
    Portfolio("trabajo", "Trabajo", "Q114289910",
              "Anexo:Ministros de Trabajo de Ecuador",
              "Ministros_de_Trabajo_de_Ecuador", "Labour_ministers_of_Ecuador"),
    Portfolio("turismo", "Turismo", "Q114289956",
              "Anexo:Ministros de Turismo de Ecuador",
              "Ministros_de_Turismo_de_Ecuador", "Tourism_ministers_of_Ecuador"),
    Portfolio("deporte", "Deporte", "Q114290016",
              "Anexo:Ministros de Deportes de Ecuador",
              "Ministros_de_Deporte_de_Ecuador", "Sports_ministers_of_Ecuador"),
    Portfolio("exteriores", "Relaciones Exteriores", "Q24293533",
              "Anexo:Ministros de Relaciones Exteriores de Ecuador",
              "Ministros_de_Relaciones_Exteriores_de_Ecuador",
              "Ministers_of_foreign_affairs_of_Ecuador"),
    Portfolio("finanzas", "Economía y Finanzas", "Q19845330",
              "Anexo:Ministros de Economía de Ecuador",
              "Ministros_de_Economía_y_Finanzas_de_Ecuador",
              "Ministers_of_finance_of_Ecuador"),
    Portfolio("defensa", "Defensa", "Q27921459",
              "Anexo:Ministros de Defensa de Ecuador",
              "Ministros_de_Defensa_de_Ecuador", "Defence_ministers_of_Ecuador"),
    # One roster covers both names (the Interior page is a redirect to it) and
    # spans 1830 to now, over a ministry that was renamed Gobierno → Interior
    # → Gobierno → Interior. The section header picks the item, but nothing
    # here is batched until that history is ruled on: hold=True.
    Portfolio("interior", "Gobierno / Interior", "Q114260168",
              "Anexo:Ministros de Gobierno de Ecuador",
              "Ministros_del_Interior_de_Ecuador", "Interior_ministers_of_Ecuador",
              section_targets=((r"\bgobierno\b", "Q114290115"),),
              hold="rename_history"),
    Portfolio("agricultura", "Agricultura y Ganadería", "Q114289753",
              "Anexo:Ministros de Agricultura de Ecuador",
              "Ministros_de_Agricultura_y_Ganadería_de_Ecuador",
              "Agriculture_ministers_of_Ecuador"),
    Portfolio("cultura", "Cultura y Patrimonio", "Q100594801",
              "Anexo:Ministros de Cultura y Patrimonio de Ecuador",
              "Ministros_de_Cultura_y_Patrimonio_de_Ecuador",
              "Culture_ministers_of_Ecuador"),
    Portfolio("educacion", "Educación", "Q114289770",
              "Anexo:Ministros de Educación de Ecuador",
              "Ministros_de_Educación_de_Ecuador", "Education_ministers_of_Ecuador"),
    Portfolio("energia", "Energía", "Q114289772",
              "Anexo:Ministros de Energía de Ecuador",
              "Ministros_de_Energía_y_Recursos_Naturales_no_Renovables_de_Ecuador",
              "Energy_ministers_of_Ecuador"),
    Portfolio("ambiente", "Ambiente", "Q114289994",
              "Anexo:Ministros de Ambiente de Ecuador",
              "Ministros_de_Ambiente_de_Ecuador", "Environment_ministers_of_Ecuador"),
    Portfolio("salud", "Salud Pública", "Q90885218",
              "Anexo:Ministros de Salud de Ecuador",
              "Ministros_de_Salud_Pública_de_Ecuador", "Ministers_of_health_of_Eduador"),
    Portfolio("justicia", "Justicia", "Q114289620",
              "Anexo:Ministros de Justicia de Ecuador",
              "Ministros_de_Justicia_de_Ecuador", "Justice_ministers_of_Ecuador"),
    Portfolio("inclusion", "Inclusión Económica y Social", "Q114289831",
              "Anexo:Ministros de Inclusión Económica y Social de Ecuador",
              "Ministros_de_Inclusión_Económica_y_Social_de_Ecuador", None),
    Portfolio("obras", "Transporte y Obras Públicas", "Q114289931",
              "Anexo:Ministros de Obras Públicas de Ecuador",
              "Ministros_de_Transporte_y_Obras_Públicas_de_Ecuador", None),
    Portfolio("vivienda", "Desarrollo Urbano y Vivienda", "Q114290143",
              "Anexo:Ministros de Desarrollo Urbano y Vivienda de Ecuador",
              "Ministros_de_Desarrollo_Urbano_y_Vivienda_de_Ecuador", None),
    Portfolio("industrias", "Industrias y Productividad", "Q114289842",
              "Anexo:Ministros de Industrias y Productividad de Ecuador",
              "Ministros_de_Industrias_y_Productividad_de_Ecuador", None),
    Portfolio("telecom", "Telecomunicaciones", "Q114290138",
              "Anexo:Ministros de Telecomunicaciones de Ecuador", None, None),
]


@dataclass
class Person:
    qid: str
    label: str
    description: Optional[str] = None
    names: List[str] = field(default_factory=list)
    p39: List[str] = field(default_factory=list)
    p27: List[str] = field(default_factory=list)
    p106: List[str] = field(default_factory=list)
    p102: List[str] = field(default_factory=list)
    birth: Optional[int] = None
    death: Optional[int] = None
    #: Categories that put this person forward, empty for roster-only people.
    cats: List[str] = field(default_factory=list)


def resolve_titles(session, lang: str, titles: List[str]) -> Dict[str, str]:
    """es.wikipedia titles → QIDs, 50 per request, redirects followed.

    Used for both the roster's own wikilinks and, for unlinked rows, the bare
    name as a title — an article at exactly that name is the same evidence a
    wikilink would have been.
    """
    out: Dict[str, str] = {}
    todo = [t for t in dict.fromkeys(titles) if t]
    for i in range(0, len(todo), 50):
        chunk = todo[i : i + 50]
        data = json.loads(
            get_text(
                session,
                WIKI_API.format(lang=lang),
                params={
                    "action": "query",
                    "prop": "pageprops",
                    "ppprop": "wikibase_item",
                    "titles": "|".join(chunk),
                    "redirects": "1",
                    "formatversion": "2",
                    "format": "json",
                },
            )
        )
        query = data.get("query", {})
        alias: Dict[str, str] = {}
        for key in ("normalized", "redirects"):
            for entry in query.get(key, []):
                alias[entry["from"]] = entry["to"]
        resolved: Dict[str, str] = {}
        for page in query.get("pages", []):
            qid = (page.get("pageprops") or {}).get("wikibase_item")
            if qid:
                resolved[page["title"]] = qid
        for title in chunk:
            target = title
            seen = {target}
            while target in alias and alias[target] not in seen:
                target = alias[target]
                seen.add(target)
            if target in resolved:
                out[title] = resolved[target]
    return out


def year_of(entity: dict, prop: str) -> Optional[int]:
    for claim in entity.get("claims", {}).get(prop, []):
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(value, dict) and "time" in value:
            if value.get("precision", 11) < 9:
                continue  # a century renders as a misleading year
            return int(value["time"].lstrip("+")[:4])
    return None


def lifetime_conflict(person: "Person", start: Optional[str]) -> Optional[str]:
    """Why this person cannot have held office from `start`, if they cannot.

    Namesakes across centuries are the failure mode a name match cannot see:
    es.wikipedia has one Angel Polibio Chaves (1855-1930) and the roster names
    another as labour minister in 1998.
    """
    if not start:
        return None
    year = int(start[:4])
    if person.birth is not None and year - person.birth < 18:
        return f"born {person.birth}, term starts {year}"
    if person.death is not None and person.death < year:
        return f"died {person.death}, term starts {year}"
    return None


def political_marker(person: "Person") -> bool:
    """Does anything on this item suggest a person who holds public office?"""
    if person.p39 or person.p102:
        return True
    if POLITICAL_OCCUPATIONS.intersection(person.p106):
        return True
    return bool(person.description and POLITICAL_WORDS.search(person.description))


def title_variants(name: str) -> List[str]:
    """A roster name and the shorter titles its article may actually sit at.

    Rosters print all four Spanish name parts ("Carlos Marx Carrasco Vicuña")
    while the article is usually at three or two ("Carlos Marx Carrasco"), so
    the full name alone finds nothing. Truncations are namesake-prone, hence
    the label check in `identify`.
    """
    parts = name.split()
    return [" ".join(parts[:n]) for n in range(len(parts), 1, -1)]


def build_people(
    session, portfolio: Portfolio, rows: List[RosterRow]
) -> Tuple[Dict[str, Person], Dict[str, str]]:
    """The person universe: category members plus roster-identified people.

    Returns (people by QID, roster title → QID).
    """
    cats: Dict[str, List[str]] = {}
    titles: Dict[str, List[str]] = {}
    for lang, cat in (("es", portfolio.es_cat), ("en", portfolio.en_cat)):
        if not cat:
            continue
        for qid, title in category_members(session, cat, lang, depth=0):
            titles.setdefault(qid, []).append(title)
            cats.setdefault(qid, []).append(f"{lang}:{cat}")

    wanted = [row.link for row in rows if row.link]
    for row in rows:
        if not row.link:
            wanted.extend(title_variants(row.name))
    by_title = resolve_titles(session, "es", wanted)

    entities = fetch_entities(
        session,
        sorted(set(titles) | set(by_title.values())),
        props="labels|descriptions|aliases|claims|sitelinks",
    )
    people: Dict[str, Person] = {}
    for qid, entity in entities.items():
        if "Q5" not in claim_qids(entity, "P31"):
            continue  # PETScan's Q5 filter also passes Category: items
        names = list(titles.get(qid, []))
        for lang in ("es", "en", "mul"):
            term = entity.get("labels", {}).get(lang)
            if term:
                names.append(term["value"])
            for alias in entity.get("aliases", {}).get(lang, []):
                names.append(alias["value"])
        for site in ("eswiki", "enwiki"):
            link = entity.get("sitelinks", {}).get(site)
            if link:
                names.append(link["title"])
        people[qid] = Person(
            qid=qid,
            label=(entity.get("labels", {}).get("es", {}) or {}).get("value")
            or best_label(entity)
            or (names[0] if names else qid),
            description=best_description(entity),
            names=list(dict.fromkeys(names)),
            p39=claim_qids(entity, "P39"),
            p27=claim_qids(entity, "P27"),
            p106=claim_qids(entity, "P106"),
            p102=claim_qids(entity, "P102"),
            birth=year_of(entity, "P569"),
            death=year_of(entity, "P570"),
            cats=cats.get(qid, []),
        )
    return people, by_title


def holders(session, qid: str) -> set:
    rows = sparql(
        session, f"SELECT DISTINCT ?p WHERE {{ ?p p:P39 ?st . ?st ps:P39 wd:{qid} . }}"
    )
    return {row["p"] for row in rows}


def ministerial_rows(
    page_html: str, portfolio: Portfolio
) -> Tuple[List[RosterRow], List[str]]:
    """The office's own rows, plus the headings of the tables left out."""
    rows: List[RosterRow] = []
    skipped: List[str] = []
    for roster in parse_rosters(page_html):
        heading = (roster.heading or "").strip()
        if re.search(portfolio.headings, heading, re.I):
            rows.extend(roster.rows)
        else:
            skipped.append(f"{heading or '(no heading)'} [{len(roster.rows)} rows]")
    return rows, skipped


def identify(
    row: RosterRow, people: Dict[str, Person], by_title: Dict[str, str]
) -> Tuple[Optional[str], str]:
    """Roster row → QID, with how it was established (or why it wasn't)."""
    if row.link:
        qid = by_title.get(row.link)
        if qid in people:
            return qid, "wikilink"
        if qid:
            return None, f"linked to {qid}, not a human item"
        return None, f"link '{row.link}' has no Wikidata item"
    for index, title in enumerate(title_variants(row.name)):
        qid = by_title.get(title)
        person = people.get(qid) if qid else None
        if person is None:
            continue
        # An article title is not a wikilink from the roster: the roster never
        # asserted this identity, so it has to survive three checks — no
        # contradicting citizenship, a lifetime covering the term, and some
        # sign that this person holds public office at all.
        if person.p27 and "Q736" not in person.p27:
            continue
        if lifetime_conflict(person, row.start):
            continue
        if not political_marker(person):
            continue
        if index == 0:
            return qid, "article title"
        if not any(names_match(row.name, n) for n in person.names):
            continue
        return qid, f"article title '{title}'"
    hits = [
        candidate
        for candidate, person in people.items()
        if person.cats
        and any(names_match(row.name, name) for name in person.names)
        and not lifetime_conflict(person, row.start)
    ]
    if len(hits) == 1:
        return hits[0], "name match"
    if len(hits) > 1:
        return None, f"ambiguous: {', '.join(hits)}"
    return None, "no item found under this name"


def target_for(row: RosterRow, portfolio: Portfolio) -> str:
    section = (row.section or "").casefold()
    for pattern, qid in portfolio.section_targets:
        if re.search(pattern, section):
            return qid
    return portfolio.target


def review_section(row: RosterRow, portfolio: Portfolio) -> Optional[str]:
    section = (row.section or "").casefold()
    return row.section if any(w in section for w in portfolio.review_sections) else None


def overlaps(terms: List[Tuple[str, Optional[str], Optional[str]]]) -> List[str]:
    """Warn when two people's terms overlap — a roster is sequential, so an
    overlap means a misparsed cell rather than a genuine co-appointment."""
    warnings: List[str] = []
    ordered = sorted((t for t in terms if t[1]), key=lambda t: t[1] or "")
    for (qid_a, start_a, end_a), (qid_b, start_b, _) in zip(ordered, ordered[1:]):
        if end_a and start_b and end_a > start_b and qid_a != qid_b:
            warnings.append(f"{qid_a} ({start_a}–{end_a}) overlaps {qid_b} (from {start_b})")
    return warnings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--portfolio", nargs="*", default=None,
                        help="Portfolio keys to run (default: all)")
    args = parser.parse_args()

    chosen = [p for p in PORTFOLIOS if args.portfolio is None or p.key in args.portfolio]
    if not chosen:
        raise SystemExit(f"No portfolio matched {args.portfolio}")

    session = make_session()
    verdict_dir = OUT_DIR / "verdicts"
    verdict_dir.mkdir(parents=True, exist_ok=True)
    audit: List[str] = [
        "# Ecuador ministers — roster match audit",
        "",
        "Every ministerial roster row, how its person was identified, and what "
        "became of it. `add` rows are in the .qs; everything else is review.",
        "",
    ]
    totals: Counter = Counter()

    for portfolio in chosen:
        page = fetch_html(session, "es", portfolio.roster)
        if page is None:
            raise SystemExit(f"Roster page missing: {portfolio.roster}")
        source = permalink("es", page["revid"])
        rows, skipped = ministerial_rows(page["html"], portfolio)
        people, by_title = build_people(session, portfolio, rows)
        targets = [portfolio.target] + [qid for _, qid in portfolio.section_targets]
        held_by_target = {target: holders(session, target) for target in dict.fromkeys(targets)}

        # Keyed by (person, target): one roster can span two named ministries,
        # and the same person may then belong on both items.
        per_person: Dict[Tuple[str, str], List[RosterRow]] = {}
        row_status: List[Tuple[RosterRow, Optional[str], str]] = []
        for row in rows:
            qid, how = identify(row, people, by_title)
            row_status.append((row, qid, how))
            if qid:
                per_person.setdefault((qid, target_for(row, portfolio)), []).append(row)

        verdicts: List[dict] = []
        spans: List[Tuple[str, Optional[str], Optional[str]]] = []
        statuses: Dict[int, str] = {}

        for (qid, target), group in per_person.items():
            person = people[qid]
            held = held_by_target[target]
            in_category = bool(person.cats)
            conflict = next(
                (c for c in (lifetime_conflict(person, row.start) for row in group) if c),
                None,
            )
            ref = next((url for row in group for url in row.ref_urls), None)
            acting = [row for row in group if row.acting]
            flagged = [row for row in group if review_section(row, portfolio) and not row.acting]
            plain = [row for row in group if row not in acting and row not in flagged]
            for row in group:
                if conflict:
                    statuses[id(row)] = f"review: lifetime ({conflict})"
                elif qid in held:
                    statuses[id(row)] = "already holds P39"
                elif row in acting:
                    statuses[id(row)] = "review: acting"
                elif row in flagged:
                    statuses[id(row)] = "review: pre-ministerial section"
                elif portfolio.hold:
                    statuses[id(row)] = f"review: {portfolio.hold}"
                elif row.start and int(row.start[:4]) < MODERN_FROM:
                    statuses[id(row)] = "review: pre-1979"
                elif in_category:
                    statuses[id(row)] = "add"
                else:
                    statuses[id(row)] = "add (roster only)"
            if conflict:
                verdicts.append({
                    "qid": qid,
                    "label": person.label,
                    "position": target,
                    "verdict": "unclear",
                    "era": "lifetime_mismatch",
                    "terms": [{"start": row.start, "end": row.end} for row in group],
                    "evidence": (
                        f"roster row '{group[0].name}' ({group[0].period_raw}) resolved "
                        f"to this item, but {conflict}"
                    ),
                    "source_url": next((u for r in group for u in r.ref_urls), source),
                    "notes": "probable namesake — the roster's person may have no item",
                })
                continue
            if qid in held:
                continue
            if plain:
                terms = merge_terms(plain)
                spans.extend((qid, start, end) for start, end in terms)
                first = next((start for start, _ in terms if start), None)
                historical = bool(first) and int(first[:4]) < MODERN_FROM
                if portfolio.hold:
                    era = portfolio.hold
                elif historical:
                    era = "historical" if in_category else "historical_roster_only"
                else:
                    era = "modern" if in_category else "roster_only"
                verdicts.append({
                    "qid": qid,
                    "label": person.label,
                    "position": target,
                    "verdict": "add",
                    "era": era,
                    "terms": [{"start": start, "end": end} for start, end in terms],
                    "evidence": (
                        f"'{portfolio.roster}' lists them as minister "
                        f"{'; '.join(row.period_raw for row in plain)}"
                        + (f", appointed by {plain[0].appointer}" if plain[0].appointer else "")
                        + (f"; category: {', '.join(person.cats)}" if in_category else
                           "; NOT in any portfolio category — roster wikilink only")
                    ),
                    "source_url": ref or source,
                    "source_prop": "S854" if ref else "S4656",
                    "notes": f"existing P39s: {', '.join(person.p39) or 'none'}",
                })
            for row in acting:
                verdicts.append({
                    "qid": qid,
                    "label": person.label,
                    "position": target,
                    "verdict": "unclear",
                    "era": "acting",
                    "terms": [{"start": row.start, "end": row.end}],
                    "evidence": f"roster marks this spell encargado: {row.period_raw}",
                    "source_url": ref or source,
                    "notes": "acting — needs the P2868 convention call",
                })
            for row in flagged:
                verdicts.append({
                    "qid": qid,
                    "label": person.label,
                    "position": target,
                    "verdict": "unclear",
                    "era": "predecessor_body",
                    "terms": [{"start": row.start, "end": row.end}],
                    "evidence": f"roster section '{row.section}': {row.period_raw}",
                    "source_url": ref or source,
                    "notes": "filed under a pre-ministerial body — same office?",
                })

        audit.append(f"## {portfolio.label} → {', '.join(dict.fromkeys(targets))}")
        audit.append(
            f"{sum(1 for p in people.values() if p.cats)} category members · "
            f"{len(rows)} ministerial roster rows · "
            f"{sum(len(h) for h in held_by_target.values())} existing holders · "
            f"roster {source}"
        )
        for warning in overlaps(spans):
            audit.append(f"* ⚠ date overlap: {warning}")
        if skipped:
            audit.append(
                "* tables not counted as this office (sibling ministries and "
                f"predecessor agencies, each its own item): {'; '.join(skipped)}"
            )
        audit.append("")
        audit.append("| roster row | dates | identified as | how | status |")
        audit.append("|---|---|---|---|---|")
        for row, qid, how in row_status:
            if qid:
                person = people[qid]
                if len(held_by_target) > 1:
                    how = f"{how} → {target_for(row, portfolio)}"
                who = (
                    f"{qid} {person.label} — {person.description or 'no description'}"
                    f" [{', '.join(person.cats) or 'not in category'}]"
                )
                status = statuses.get(id(row), "?")
            else:
                who, status = "—", "no identity"
            totals[status] += 1
            audit.append(f"| {row.name} | {row.period_raw} | {who} | {how} | {status} |")

        matched_qids = {qid for qid, _ in per_person}
        for qid, person in sorted(people.items()):
            if qid in matched_qids or qid in held_by_target[portfolio.target] or not person.cats:
                continue
            totals["review: category only"] += 1
            audit.append(
                f"| — (absent from roster) | — | {qid} {person.label} — "
                f"{person.description or 'no description'} [{', '.join(person.cats)}] "
                f"| category | review: category only |"
            )
            verdicts.append({
                "qid": qid,
                "label": person.label,
                "position": portfolio.target,
                "verdict": "unclear",
                "era": "category_only",
                "terms": [],
                "evidence": f"in {', '.join(person.cats)} but absent from {portfolio.roster}",
                "source_url": source,
                "notes": (
                    f"existing P39s: {', '.join(person.p39) or 'none'} — the roster "
                    "starts in 1979, so pre-1979 holders land here; check the article"
                ),
            })
        audit.append("")

        path = verdict_dir / f"minister_{portfolio.key}.jsonl"
        path.write_text("".join(json.dumps(v, ensure_ascii=False) + "\n" for v in verdicts))
        adds = Counter(v["era"] for v in verdicts if v["verdict"] == "add")
        print(
            f"{portfolio.label:<24} {len(rows):>3} rows → {adds['modern']:>3} batch, "
            f"{adds['roster_only']:>3} roster-only, "
            f"{adds['historical'] + adds['historical_roster_only']:>3} pre-1979, "
            f"{sum(1 for v in verdicts if v['verdict'] == 'unclear'):>3} review"
        )

    (OUT_DIR / "ministers_audit.md").write_text("\n".join(audit) + "\n")
    print(f"\n{dict(totals)}")
    print(f"Wrote {OUT_DIR / 'ministers_audit.md'}")


if __name__ == "__main__":
    main()
