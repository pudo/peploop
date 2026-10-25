"""Seed the holders of the offices `mint_units` made into the person lane.

A unit's or a body's head office is minted from the unit's own head
statement or infobox, not from a seeded person's article, so no mention was
clustered into it and `feed` reopens nothing: the office exists and its
holder's `P39` never follows. The holder is queued here like a category
member instead -- upserted under the run's country, with a membership naming
the office -- and the ordinary stages read their own articles, so the `P39`
carries its reference and dates and passes the usual checks, and the same
run fills their other properties. Copying the unit's `P6` into a `P39` would
be an inference with no reference.

Only offices that exist are seeded: a row mint created or found. A holder
queued before the item exists has nothing to land on.
"""

import re
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote, urlparse

from peploop import db, wikidata, wikipedia
from peploop.mint_units import same_person
from peploop.text import fold

#: The candidate statuses whose office exists: made, made and loaded, or found existing.
EXISTING = ("created", "loaded", "found")


@dataclass
class Holder:
    """One office's holder, with the item that holds it where one is known."""

    candidate: int
    ref: str
    #: The office's item, where mint made or found one.
    office: str | None
    #: The wiki the unit's article is in, which the person's article is read in first.
    lang: str
    name: str
    qid: str | None
    #: How the item was known (`holder/statement`, `holder/link`) or why it was not.
    how: str


@dataclass
class Lookup:
    """The reads a holder's resolution makes, replaceable in the checks."""

    html: Callable[[str, str], str] = lambda lang, title: wikipedia.fetch_article(lang, title)["html"]
    page_item: Callable[[str, str], str | None] = wikipedia.page_item
    items: Callable[[list[str]], dict[str, dict[str, Any]]] = \
        lambda qids: wikidata.fetch_items(qids, props="claims|sitelinks")


def _words(text: str) -> list[str]:
    return re.findall(r"\w+", fold(text))


def linked_title(lines: Sequence[tuple[str, list[tuple[str, str]]]], name: str) -> tuple[str | None, str]:
    """The article the infobox line naming the holder links the name to, or None with why.

    The line must carry every word of the name, and exactly one page must be
    linked from text naming the same person: a line linking two people's
    pages, or none, is not resolved by guessing.
    """
    wanted = _words(name)
    targets = {target for line, links in lines if wanted and set(wanted) <= set(_words(line))
               for text, target in links if same_person(text, name)}
    if not targets:
        return None, "holder/unlinked"
    if len(targets) > 1:
        return None, "holder/several-links"
    return next(iter(targets)), "holder/link"


def resolve(name: str, lang: str, url: str, lookup: Lookup | None = None) -> tuple[str | None, str]:
    """The item of the holder an infobox names, through the link on their name, or None with why.

    Kept only when the item is a living human with an article in the unit's
    own wiki: an unlinked name is residue, never a search.
    """
    lookup = lookup or Lookup()
    parsed = urlparse(url)
    title = unquote(parsed.path.rsplit("/wiki/", 1)[-1]).replace("_", " ")
    if not (parsed.hostname or "").endswith(".wikipedia.org") or not title:
        return None, "holder/no-article"
    target, why = linked_title(wikipedia.infobox_links(lookup.html(lang, title)), name)
    if target is None:
        return None, why
    qid = lookup.page_item(lang, target)
    if not qid:
        return None, "holder/no-item"
    entity = lookup.items([qid]).get(qid) or {}
    if "Q5" not in wikidata.claim_qids(entity, "P31", include_deprecated=False):
        return None, "holder/not-human"
    if wikidata.claim_time(entity, "P570", include_deprecated=False):
        return None, "holder/dead"
    if f"{lang}wiki" not in (entity.get("sitelinks") or {}):
        return None, "holder/other-wiki"
    return qid, why


def _lang(unit: dict[str, Any]) -> str:
    """The unit's wiki: the level's, or the host of its article's URL."""
    if unit.get("lang"):
        return unit["lang"]
    host = urlparse(unit.get("url") or "").hostname or ""
    return host.split(".")[0] if host.endswith(".wikipedia.org") else "en"


def holders(cc: str, statuses: Sequence[str] = EXISTING, lookup: Lookup | None = None) -> list[Holder]:
    """The holder of every unit or body office of the run whose candidate is in `statuses`.

    The holder's item is the unit's own head statement where the draft took
    it from one, else the one the infobox links the name to.
    """
    rows = db.conn().execute(
        "SELECT id, ref, qid, draft->'unit' FROM office_candidate WHERE country = %s"
        " AND 'unit' = ANY(origin) AND status = ANY(%s) ORDER BY id",
        (cc, list(statuses)),
    ).fetchall()
    out = []
    for candidate, ref, office, unit in rows:
        unit = unit or {}
        lang, name = _lang(unit), unit.get("holder") or ""
        if unit.get("holder_qid"):
            qid, how = unit["holder_qid"], "holder/statement"
        elif not name:
            qid, how = None, "holder/unnamed"
        else:
            try:
                qid, how = resolve(name, lang, unit.get("url") or "", lookup)
            except Exception as exc:  # noqa: BLE001 -- one unreadable article is one holder's residue
                qid, how = None, f"holder/unreadable: {type(exc).__name__}"
        out.append(Holder(candidate, ref, office, lang, name, qid, how))
    return out


def seed(cc: str, found: Sequence[Holder]) -> Counter[str]:
    """Queue each resolved holder under the run's country, with a membership naming the office.

    Someone already in the lane keeps their status, as with any seed: a
    refusal the new office would now place is re-asked by `reconcile`.
    """
    counts: Counter[str] = Counter()
    for holder in found:
        counts[holder.how] += 1
        if holder.qid is None:
            continue
        counts["new"] += db.upsert_person(holder.qid, cc)
        db.upsert_membership(holder.qid, f"holder:{holder.office or holder.ref}", holder.lang)
    return counts
