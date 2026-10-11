"""Match a place name inside a position label, without the substring trap.

Reach for this whenever a lane needs to know *which polity* a label names —
the jurisdiction backfill's label channel, the subnational pinning in
`render_citizenship_plan.py`. Every matcher this workbench built started as
`name in label` and every one of them was too loose: the alias "Loire" fires
inside "Indre-et-Loire", "the North" hits the North Riding, "Jersey" hits New
Jersey, "Samoa" hits American Samoa. Two rules answer all four:

* **Longest name wins, and matches must not overlap.** The index carries every
  territory `rigour` knows, historical and subnational included, so a longer
  name always exists to consume the shorter one — "American Samoa" is matched
  and "Samoa" never gets to fire inside it.
* **Only an unambiguous result counts.** A label naming two territories, or a
  name several territories share, yields nothing rather than a guess.

`match_admin` keeps a third, stricter rule for subdivisions, because their
names are far more collision-prone than country names: only the label's
after-preposition *tail*, compared for equality.

The ambiguity rule earns its keep twice over on international posts, because
`rigour` carries the IGOs as pseudo-territories: "Zambian Permanent
Representative to the United Nations" names two places and so names none. That
is the right answer — the office belongs to the UN's registry, not to Zambia's
jurisdiction — and it is the false positive a label matcher otherwise walks
straight into.
"""

import re
from typing import Any, Dict, List, NamedTuple, Optional, Sequence, Set, Tuple

from rigour.territories import get_territories

from wd.api import best_label, fetch_entities

#: Shorter names are dropped from every index: three-letter place names collide
#: with ordinary words and with each other far more often than they identify.
MIN_NAME = 4

#: Demonym. "Zambian Permanent Representative…" and "Maltese Labour Party…"
#: name their country adjectivally and no label or alias catches them.
DEMONYM = "P1549"


class Place(NamedTuple):
    """A territory the index can return, with what a caller needs to judge it."""

    qid: str
    code: Optional[str]
    name: Optional[str]
    is_country: bool
    is_historical: bool


class NameIndex(NamedTuple):
    """Compiled place-name matcher. Build once, match many."""

    pattern: Optional[re.Pattern[str]]
    by_name: Dict[str, str]
    places: Dict[str, Place]


def entity_names(entity: Dict[str, Any], langs: Sequence[str] = ()) -> Set[str]:
    """Casefolded labels and aliases of an item. All languages unless `langs`."""
    names: Set[str] = set()
    labels = entity.get("labels", {})
    aliases = entity.get("aliases", {})
    keys = langs or list({*labels, *aliases})
    for lang in keys:
        obj = labels.get(lang)
        if obj is not None:
            names.add(obj["value"].casefold())
        for alias in aliases.get(lang, []):
            names.add(alias["value"].casefold())
    return names


def current_p17(entity: Dict[str, Any]) -> Optional[str]:
    """The item's one current country, or None when it has several.

    Preferred rank first, then un-ended claims, then everything: a place whose
    P17 changed hands (London → Kingdom of England) must not answer with the
    historical value, and one still disputed must not answer at all.
    """
    claims = [
        c for c in entity.get("claims", {}).get("P17", [])
        if c.get("rank") != "deprecated"
        and "id" in c.get("mainsnak", {}).get("datavalue", {}).get("value", {})
    ]
    preferred = [c for c in claims if c.get("rank") == "preferred"]
    current = [c for c in claims if "P582" not in c.get("qualifiers", {})]
    for pool in (preferred, current, claims):
        values = {c["mainsnak"]["datavalue"]["value"]["id"] for c in pool}
        if len(values) == 1:
            return values.pop()
    return None


def _demonyms(entity: Dict[str, Any], langs: Sequence[str]) -> Set[str]:
    out: Set[str] = set()
    for claim in entity.get("claims", {}).get(DEMONYM, []):
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(value, dict) and value.get("language") in langs:
            out.add(value["text"].casefold())
    return out


def _compile(by_name: Dict[str, str], places: Dict[str, Place]) -> NameIndex:
    # Longest alternative first so the engine prefers "American Samoa" at the
    # position where "Samoa" would also match; `finditer` then consumes it and
    # the shorter name never gets a turn.
    ordered = sorted(by_name, key=len, reverse=True)
    pattern = None
    if ordered:
        alternation = "|".join(re.escape(n) for n in ordered)
        pattern = re.compile(rf"(?<!\w)({alternation})(?!\w)")
    return NameIndex(pattern=pattern, by_name=by_name, places=places)


def territory_index(session: Any, langs: Sequence[str] = ("en", "mul")) -> NameIndex:
    """Every territory `rigour` knows, indexed by name, alias and demonym.

    Historical and subnational territories are indexed deliberately, not by
    oversight: they are what makes the longest-match rule work, and a label
    that names one should return *it* so the caller can decline, rather than
    silently falling through to a country hiding inside the same string.
    """
    places: Dict[str, Place] = {}
    for territory in get_territories():
        if territory.qid and territory.qid not in places:
            places[territory.qid] = Place(
                qid=territory.qid,
                code=territory.code,
                name=territory.name,
                is_country=territory.is_country,
                is_historical=territory.is_historical,
            )
    entities = fetch_entities(session, list(places), props="labels|aliases|claims")
    seen: Dict[str, Set[str]] = {}
    for qid, entity in entities.items():
        if qid not in places:
            continue  # a redirect landed on an item rigour does not know
        for name in entity_names(entity, langs) | _demonyms(entity, langs):
            if len(name) >= MIN_NAME:
                seen.setdefault(name, set()).add(qid)
    by_name = {name: qids.copy().pop() for name, qids in seen.items() if len(qids) == 1}
    return _compile(by_name, places)


def match_place(index: NameIndex, label: Optional[str]) -> Optional[Place]:
    """The one territory this label names, or None if none or several."""
    if not label or index.pattern is None:
        return None
    found = {index.by_name[m.group(1)] for m in index.pattern.finditer(label.casefold())}
    if len(found) != 1:
        return None
    return index.places.get(found.pop())


TAIL_RE = re.compile(
    r".*(?:\bof\b|\bde\b|\bdu\b|\bdes\b|\bdel\b|\bin\b|\bd')\s*", re.I)
ARTICLE_RE = re.compile(r"^(?:the|la|le|les|l'|el|los)\s+", re.I)


def label_tail(label: str) -> Optional[str]:
    """The entity name after the label's last preposition ("member of the
    X Oblast Duma" won't parse; "Duma of the Astrakhan Region" → "astrakhan
    region"). Subdivision names collide with each other and with ordinary
    words too readily for `match_place`'s longest-match rule to carry them, so
    only this tail is compared — and only for exact equality."""
    m = TAIL_RE.match(label)
    if m is None:
        return None
    tail = label[m.end():].strip().strip(".,;:()")
    tail = ARTICLE_RE.sub("", tail)
    return tail.casefold() or None


def admin_index(session: Any, country_qid: str) -> List[Tuple[Set[str], str, str]]:
    """Names of a country's first-level subdivisions (its own P150 targets),
    for matching region names inside position labels. First-level only — the
    right granularity for a regional office, never for a municipal one."""
    country = fetch_entities(session, [country_qid], props="claims").get(country_qid)
    if country is None:
        return []
    targets = [
        c["mainsnak"]["datavalue"]["value"]["id"]
        for c in country.get("claims", {}).get("P150", [])
        if c.get("rank") != "deprecated"
        and "id" in c.get("mainsnak", {}).get("datavalue", {}).get("value", {})
    ]
    index = []
    for qid, entity in fetch_entities(session, targets, props="labels|aliases").items():
        names = {n for n in entity_names(entity) if len(n) >= MIN_NAME}
        if names:
            index.append((names, (best_label(entity) or "").casefold(), qid))
    return index


def match_admin(index: List[Tuple[Set[str], str, str]], label: str) -> Optional[str]:
    """The subdivision one of whose names IS the label's tail — unambiguous
    matches only. A bare-eponym alias of a suffixed subdivision ("Gombe" for
    "Gombe State", "Mandalay" for "Mandalay Region") is rejected: those
    labels name the city/traditional polity, not the subdivision."""
    tail = label_tail(label)
    if tail is None:
        return None
    found = {
        qid
        for names, primary, qid in index
        if tail in names and not primary.startswith(tail + " ")
    }
    return found.pop() if len(found) == 1 else None
