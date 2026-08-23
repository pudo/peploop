"""Read the OpenSanctions PETScan category config as enrichment work items.

Reach for this whenever a pass is scoped to a `wd_categories.yml` entry rather
than to a country. Each spec pairs a Wikipedia category (the candidate
generator) with the office its members are asserted to hold — and, for the ~240
specs an earlier resolution pass settled, the actual Wikidata item behind that
office. A spec is therefore a cohort plus a target, which is everything a
per-person P39 verification needs.

The config is a workaround: it mass-includes people as PEPs *because* their
Wikidata items lack the P39 that would find them properly. So the unit of
progress is a spec whose `position:` block can be deleted, and
`Spec.retirable_when` names what that takes.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

import yaml

from wd.positions import country_names

#: The config lives in the opensanctions repo; this workbench only reads it.
YML = Path(
    "/Users/pudo/Code/opensanctions/datasets/_wikidata/categories/wd_categories.yml"
)

#: Granularity of a spec's `position:` name — what a member's P39 can point at.
OFFICE = "office"          # one seat: "Mayor of Bogotá"
MEMBERSHIP = "membership"  # one named body: "Deputy of the Kursk Oblast Duma"
BUCKET = "bucket"          # a class: "Governor of a Russian Region"


def granularity(name: str, country: Optional[str]) -> str:
    """Classify what a synthetic position name actually denotes.

    The distinction decides whether a spec has one P39 target or needs
    per-person narrowing, so it is the first thing a run branches on: `office`
    and `membership` collapse position association to "did this person hold
    *this* item, and when", while `bucket` names a class of offices and needs a
    gazetteer search per person.
    """
    low = name.casefold().strip()
    if re.search(r"\b(?:a|an)\s+[a-z]", low) or low in ("mayor", "mayor (spain)"):
        return BUCKET
    # Class assignments over many distinct offices, not one seat:
    if re.match(r"^local councillor\b", low) or re.search(
        r"\b(advisor|leadership)$", low
    ):
        return BUCKET
    # "Minister of <own country>" = any portfolio, not one office:
    for cname in country_names(country):
        if re.fullmatch(
            rf"(?:deputy )?(?:minister|member of the government) "
            rf"of (?:the )?{re.escape(cname)}",
            low,
        ):
            return BUCKET
    if re.match(r"^(?:member|deputy|senator|mp) (?:of|at|in)\b", low):
        return MEMBERSHIP
    return OFFICE


@dataclass
class Spec:
    """One `wd_categories.yml` entry, as a unit of enrichment work."""

    key: str                     # "<language>:<category>", the run's identity
    category: str
    language: str
    depth: int
    position_name: str
    position_country: Optional[str]
    position_topics: List[str] = field(default_factory=list)
    target: Optional[str] = None          # position.wikidata_id, if resolved
    granularity: str = OFFICE
    os_topic: Optional[str] = None
    os_country: Optional[str] = None
    negcats: Tuple[str, ...] = ()

    @property
    def blocked(self) -> Optional[str]:
        """Why this spec cannot be worked as-is, or None.

        `no-target` and `bucket` are both "no single item to verify against",
        kept apart because the second is a designed path and the first is a
        resolution gap.
        """
        if self.granularity == BUCKET:
            return BUCKET
        if not self.target:
            return "no-target"
        return None

    def retirable_when(self, members_total: int, gap: int) -> bool:
        """The spec's `position:` block can go once every member is accounted for.

        A zero gap over zero members is not progress — it is the langcheck bug
        (`scripts/category_langcheck.py`): the crawler handed PETScan a title
        from the wrong wiki, so the category matches no page and the spec
        silently contributes nobody.
        """
        return members_total > 0 and gap == 0 and bool(self.target)


def _categories(node):
    """Find the `categories` list wherever it sits in the yml."""
    if isinstance(node, dict):
        if "categories" in node:
            return node["categories"]
        for value in node.values():
            found = _categories(value)
            if found is not None:
                return found
    return None


def load_specs(path: Path = YML, position_only: bool = True) -> List[Spec]:
    """Read the config. `position_only` keeps the specs that assert an office.

    Read the yml itself rather than a cached snapshot of it: eleven Lithuanian
    specs were added upstream after `data/categories/positions.json` was written
    and were never resolved at all (`tasks/category_positions.md`).
    """
    raw = _categories(yaml.safe_load(path.read_text())) or []
    specs: List[Spec] = []
    for entry in raw:
        pos = entry.get("position")
        if position_only and not pos:
            continue
        pos = pos or {}
        country = pos.get("country") or entry.get("country")
        name = pos.get("name", "")
        specs.append(
            Spec(
                key=f"{entry.get('language', 'en')}:{entry['category']}",
                category=entry["category"],
                language=entry.get("language", "en"),
                depth=entry.get("depth", 0) or 0,
                position_name=name,
                position_country=country,
                position_topics=pos.get("topics", []),
                target=pos.get("wikidata_id"),
                granularity=granularity(name, country) if name else BUCKET,
                os_topic=entry.get("topic") or (entry.get("topics") or [None])[0],
                os_country=entry.get("country"),
                negcats=tuple(
                    c for c in (entry.get("negcats") or "").split("\n") if c.strip()
                ),
            )
        )
    return specs
