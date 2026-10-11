"""Read office tenures out of a person's own Wikipedia infobox.

A roster article is the workbench's usual evidence: one page listing an office's
holders in order, which dates every row at once. Some countries do not publish
one. Qatar is the case that forced this module — two of its thirty-two ministry
articles carry a dated list of ministers, so the roster channel reaches the
throne and almost nothing else, while 213 dated tenures sit in the infoboxes of
the people themselves on ar.wikipedia.

The infobox states the same fact from the other side: instead of an office
naming its holders, a holder names their offices. That makes it a *source of
rows* and nothing more — `officebox_rows` returns `RosterRow`s, so identity
resolution, `target_for` routing, the backtest, the policy table and the render
path all apply unchanged.

It is one channel, and one channel is never enough here. An infobox is written
by whoever wrote the article and is corrected by nobody in particular, so
`wd.policy` releases these rows only where the person also sits in the office's
own Wikipedia category — see `officebox.two_channel`. Rows carry the office
string in `section`, which is what `Office.section_targets` matches on.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from wd.roster import RosterRow, parse_date, parse_period
from wd.wikipedia import permalink

#: Infobox templates that describe someone *by the offices they held*. A person
#: box ("صندوق معلومات شخص", "Infobox person") is excluded on purpose: it has no
#: office/term grammar, and reading its `title` as an office turns a job
#: description into a position claim.
INFOBOX_NAMES = re.compile(
    r"^\s*(?:infobox\s+(?:officeholder|office\s*holder|politician|"
    r"congressman|senator|governor|minister|monarch|royalty)"
    r"|معلومات\s+صاحب\s+منصب|صندوق\s+معلومات\s+صاحب\s+منصب"
    r"|صندوق\s+معلومات\s+سياسي|معلومات\s+سياسي)",
    re.IGNORECASE,
)

#: Parameter names per language: the office, and the two bounds of its term.
#: Matched whole after stripping the numeric suffix that groups them, so
#: "المنصب1" pairs with "بداية الفترة1" and never with "بداية الفترة".
FIELDS: Dict[str, Dict[str, Tuple[str, ...]]] = {
    "en": {
        "office": ("office", "title", "order"),
        "start": ("term_start", "termstart", "term_begin"),
        "end": ("term_end", "termend"),
    },
    # `المنصب` / `بداية الفترة` / `نهاية الفترة`. The bare prefixes `منصب` and
    # `بداية` look like the same fields and are not: measured across 222 Qatari
    # ar.wikipedia articles they match 16 where the definite forms match 101.
    "ar": {
        "office": ("المنصب", "منصب"),
        "start": ("بداية الفترة", "بداية فترة", "بداية المنصب"),
        "end": ("نهاية الفترة", "نهاية فترة", "نهاية المنصب"),
    },
}

#: An infobox that takes its values *from* Wikidata cannot tell us anything
#: Wikidata does not already hold, and reading one back would manufacture
#: agreement between a claim and itself. `wd/infobox.py` reasons the same way
#: about birth dates.
FROM_WIKIDATA = re.compile(
    r"\{\{\s*#property\s*:|\{\{\s*wikidata\s*\||fetchwikidata|\{\{#invoke:\s*wikidata",
    re.IGNORECASE,
)

#: "(non-resident)", "(acting)" and the like, printed inside the office cell.
_PARENTHETICAL = re.compile(r"\s*\((?:[^()]*)\)\s*$")
_TAGS = re.compile(r"<[^>]+>")
_REFS = re.compile(r"<ref[^>]*>.*?</ref>|<ref[^>]*/>", re.IGNORECASE | re.DOTALL)
_LINK = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]*))?\]\]")
_SUFFIX = re.compile(r"(\d+)$")

ACTING_WORDS = re.compile(r"\bacting\b|\binterim\b|بالوكالة|بالنيابة|مكلف", re.IGNORECASE)


@dataclass(frozen=True)
class Tenure:
    """One office group out of an infobox: the office, and when it was held."""

    #: The office as printed, links resolved to their visible text.
    office: str
    #: The article the office links to, if it is linked. Usually the *ministry*
    #: rather than the position item, which is why routing is by pattern.
    link: Optional[str]
    start: Optional[str] = None
    end: Optional[str] = None
    incumbent: bool = False
    acting: bool = False
    #: The numeric suffix that grouped it — "" for the unsuffixed first group.
    index: str = ""
    #: The raw start/end cells, for the audit and for `wd.backtest`.
    period_raw: str = ""


def _strip(value: str) -> str:
    """A parameter value as printed: references and markup gone, links kept."""
    value = _REFS.sub("", value)
    value = _TAGS.sub("", value)
    return " ".join(value.split()).strip()


def _linked(value: str) -> Tuple[str, Optional[str]]:
    """Printed text and the first article the value links to."""
    target: Optional[str] = None
    match = _LINK.search(value)
    if match:
        target = match.group(1).split("#")[0].strip()
        if ":" in target:  # a File:/Category: link is not an office
            target = None

    def show(hit: re.Match) -> str:
        return (hit.group(2) or hit.group(1)).strip()

    return _strip(_LINK.sub(show, value)), target


def template_body(wikitext: str) -> Optional[str]:
    """The officeholder infobox's body, or None if the article has no such box.

    Scans braces rather than matching to the first `}}`: an infobox is full of
    nested templates ({{start date}}, {{cite web}}, {{lang}}), and stopping at
    the first closer would cut the box off at its first citation.
    """
    for opener in re.finditer(r"\{\{", wikitext):
        start = opener.start()
        if not INFOBOX_NAMES.match(wikitext[start + 2: start + 60]):
            continue
        depth = 0
        for pos in range(start, len(wikitext) - 1):
            pair = wikitext[pos: pos + 2]
            if pair == "{{":
                depth += 1
            elif pair == "}}":
                depth -= 1
                if depth == 0:
                    return wikitext[start + 2: pos]
        return wikitext[start + 2:]
    return None


def parameters(body: str) -> List[Tuple[str, str]]:
    """`name = value` pairs, split on the pipes that belong to this template.

    A pipe inside `[[a|b]]`, `{{a|b}}` or a table markup block is part of a
    value, not a separator; splitting on every pipe tears a piped wikilink in
    half and leaves the office named "Ministry of Commerce and Industry
    (Qatar)" — the article — instead of "Minister of Commerce and Industry".
    """
    out: List[Tuple[str, str]] = []
    depth = brackets = 0
    field = ""
    for index, char in enumerate(body):
        pair = body[index: index + 2]
        if pair == "{{":
            depth += 1
        elif pair == "}}":
            depth -= 1
        elif pair == "[[":
            brackets += 1
        elif pair == "]]":
            brackets -= 1
        if char == "|" and depth <= 0 and brackets <= 0:
            out.append(("", field))
            field = ""
            continue
        field += char
    out.append(("", field))

    pairs: List[Tuple[str, str]] = []
    for _, chunk in out:
        if "=" not in chunk:
            continue
        name, _, value = chunk.partition("=")
        name = " ".join(name.split())
        if name:
            pairs.append((name, value))
    return pairs


def parse_officebox(wikitext: str, lang: str) -> List[Tenure]:
    """Every dated office group an article's own infobox states.

    Returns them in the order the infobox lists them, which is the order the
    article's author considered current-first — not chronological, and not
    something to rely on.
    """
    vocab = FIELDS.get(lang)
    body = template_body(wikitext) if vocab else None
    if body is None or vocab is None:
        return []
    if FROM_WIKIDATA.search(body):
        return []

    groups: Dict[str, Dict[str, str]] = {}
    for name, value in parameters(body):
        suffix = _SUFFIX.search(name)
        index = suffix.group(1) if suffix else ""
        stem = name[: suffix.start()].strip() if suffix else name
        for role, keys in vocab.items():
            if stem in keys:
                # An empty value is an absent one. `| term_end = | birth_date =`
                # is real markup on Q107379868, and a reader that took the next
                # line's *name* as this field's value dated his ambassadorship
                # to "birth_date".
                if _strip(value):
                    groups.setdefault(index, {})[role] = value
                break

    tenures: List[Tenure] = []
    for index, group in sorted(groups.items(), key=lambda kv: (kv[0] != "", kv[0])):
        if "office" not in group:
            continue
        printed, link = _linked(group["office"])
        acting = bool(ACTING_WORDS.search(printed))
        printed = _PARENTHETICAL.sub("", printed).strip()
        raw_start = _strip(_LINK.sub(lambda m: (m.group(2) or m.group(1)), group.get("start", "")))
        raw_end = _strip(_LINK.sub(lambda m: (m.group(2) or m.group(1)), group.get("end", "")))
        start = parse_date(raw_start) if raw_start else None
        end = parse_date(raw_end) if raw_end else None
        # "Incumbent" / "حتى الآن" in an end cell is data, not a defect: it says
        # the spell is open, which is a missing end and not a missing date.
        _, _, incumbent = parse_period(f"{raw_start} – {raw_end}") if raw_end else (None, None, False)
        tenures.append(Tenure(
            office=printed, link=link, start=start, end=end,
            incumbent=incumbent and end is None, acting=acting, index=index,
            period_raw=" – ".join(part for part in (raw_start, raw_end) if part),
        ))
    return tenures


def officebox_rows(
    pages: Dict[str, dict], lang: str, titles: Sequence[str]
) -> List[RosterRow]:
    """Infobox tenures as roster rows, one per office group per person.

    `pages` is `wd.wikipedia.fetch_pages` output. The row's `link` is the
    article title, so `identify` resolves the person the same way it resolves a
    roster wikilink — the strongest rung of the identity ladder, because the
    article *is* the person. The office goes in `section`, which is what
    `Office.section_targets` matches on.
    """
    rows: List[RosterRow] = []
    ordinal = 0
    for title in titles:
        page = pages.get(title)
        if not page:
            continue
        # Each row cites the revision of the article it was read from, and each
        # row is a different article — unlike a roster lane, where one permalink
        # sources the whole office. Without it these statements render with no
        # reference at all, which is the one thing every other lane here is
        # careful not to do.
        revid = page.get("revid")
        source = permalink(lang, revid) if revid else ""
        for tenure in parse_officebox(page.get("wikitext") or "", lang):
            ordinal += 1
            rows.append(RosterRow(
                ordinal=ordinal,
                section=tenure.office,
                name=title,
                link=title,
                start=tenure.start,
                end=tenure.end,
                incumbent=tenure.incumbent,
                period_raw=tenure.period_raw,
                flags=["officebox"] + (["acting"] if tenure.acting else []),
                cells={"office": tenure.office,
                       "office_link": tenure.link or "",
                       "officebox_source": source},
            ))
    return rows


__all__ = ["Tenure", "officebox_rows", "parse_officebox", "template_body"]
