"""Kinship statements a dynastic genealogy article proves, and nobody wrote down.

Reach for this where a wiki keeps one article that *is* a family's descent —
`en:Descendants of Ibn Saud` — rather than N biographies each restating a
fragment of it. Such an article carries three things no single item does: the
generation a person belongs to, the parent whose section they are listed under,
and, in an Arabic naming culture, the patronymic chain that names their father
outright.

`wd.campaign.family_records` already asserts `P53` from a hereditary *office*,
which works where the office and the surname are two independent channels. A
royal house of several thousand people needs something else: most of its members
hold no office at all — 330 of the 411 people carrying `P53 = Q31711` have no
`P39` — and the article is the only source that places them.

The bar is the same as everywhere else in this workbench: **two independent
channels per statement, and no statement from one.**

* a **mother** (`P25`) is proposed only where the article lists the child under
  that wife's section *and* the wife's item is confirmed from outside the
  section heading — by the section's own hatnote link, or by the child's
  siblings already recording her.
* a **father** (`P22`) is proposed only where the name's patronymic resolves to
  exactly one candidate in the closed set the article's own heading defines
  ("Patrilineal grandsons" ⇒ the father is a son of the ancestor) *and* that
  candidate can have fathered the person.
* **membership** (`P53`) is proposed only where the article lists the person as
  a descendant *and* their name or their recorded parentage says the same.

What fails a gate stays visible with its reason. In a house where infant sons
were routinely renamed after — Turki I and Turki II, Badr I and Badr, Fahd I and
Fahd — ambiguity is the normal case, not an edge case, and a wrong father is
worse than a gap.
"""

import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from lxml import html as lxml_html

from wd.record import Decision, Record, Signal, Snak, Statement, Subject, Value
from wd.roster import fold

#: Where a list item stops naming a person and starts describing them. The
#: numbered lists under a wife use "; ", the bulleted descendant lists use
#: `{{spaced ndash}}` — a non-breaking space, an en dash and more space. Cutting
#: here is what keeps the *first link in the item* from being the wrong person:
#: "Sa'ad (I); [[Robert Lacey]] in his book…" links a historian, not a prince.
DESCRIPTION_CUT = re.compile(r";|[\s ]+[–—-][\s ]+")

#: Tags whose text is not part of the name: reference superscripts, the
#: TemplateStyles blobs MediaWiki inlines, and edit links. A nested list is in
#: here because a bullet's children render *inside* its own `<li>`: without
#: this, every descendant's name would be read as part of their parent's.
DROP_TAGS = {"sup", "style", "script", "link", "meta", "ul", "ol"}

#: A parenthetical that annotates rather than names. `en:Hashemites` glosses
#: every entry with its relation to the reigning king — "(The King's
#: half-niece)" — which is not part of the name and, read as one, leaves
#: `name_chain` a chain of English words. Cut only where an article is declared
#: to use them (`parse_genealogy(glosses=True)`), and never over a regnal
#: marker: "Sa'ad (I)" and "Bazza (II)" are how two same-named relatives are
#: told apart, which is the opposite of noise.
GLOSS = re.compile(r"\s*\(([^)]*)\)\s*$")

#: A regnal marker after a given name — "Turki I", "Bazza (II)", "Fahd (I)".
#: Load-bearing rather than noise: it is what tells two same-named sons apart,
#: and the house has at least six such pairs.
REGNAL = re.compile(r"^(?:\(([ivx]+)\)|([ivx]+))$", re.I)

#: The patronymic connectors, folded. "bin"/"ibn" for a son, "bint" for a
#: daughter; "al"/"as" introduce the house name and end the chain.
CONNECTORS = {"bin", "ibn", "ben", "bn", "bint", "binte"}
#: What follows the chain rather than continuing it: "… Al Saud", "… Al Sudairi".
HOUSE_LEAD = {"al", "as", "el", "ash", "aal"}
#: Words that begin a lifespan rather than a name part.
LIFESPAN_WORDS = {"born", "died", "b", "d", "c", "ca", "circa", "of"}


@dataclass
class Listed:
    """One person exactly as the genealogy article lists them.

    `section` is the heading directly above — a wife's name in the first
    chapter, "Patrilineal grandsons" later — and it is the whole reason this
    article is worth parsing: it is an assertion about descent that the person's
    own item does not carry.
    """

    name: str
    link: Optional[str]
    chapter: str
    section: str
    #: The lifespan cell or parenthetical, unparsed — a second channel on the
    #: lifetime gate where the item carries no dates.
    lifespan: str = ""
    #: Article titles linked in the section's hatnote ({{main|…}}), which is how
    #: a wife's own item is named where it is named at all.
    section_links: Tuple[str, ...] = ()
    #: Nesting depth in the list that carries them, 1 for a top-level bullet.
    #: `en:Hashemites` asserts descent by indentation where
    #: `en:Descendants of Ibn Saud` asserts it by heading, so for that article
    #: the enclosing bullet is what a section heading is here — see `parent`.
    depth: int = 0
    #: The person whose bullet encloses this one, where the list is nested. This
    #: is an assertion of parentage exactly as a wife's section heading is: the
    #: indentation is what the article states, and it is *not* the same thing as
    #: the parenthetical gloss beside the name, which on `en:Hashemites` is
    #: written relative to the reigning king ("The King's half-brother") and
    #: describes a different relation entirely.
    parent: Optional[str] = None
    parent_link: Optional[str] = None
    #: Where one bullet names a couple — "[[Hamzah]] and [[Princess Basmah]]" —
    #: the other half of it. Both are emitted as their own `Listed`, so the
    #: children nested beneath take one parent from each.
    partner: Optional[str] = None
    partner_link: Optional[str] = None
    #: True for the half of a couple who married into the family rather than
    #: descending from it — the second name in the bullet, which these articles
    #: write in that order ("half-brother and half-sister-in-law"). They are
    #: *listed* under the bullet above without being a child of it, so every
    #: lane about descent has to drop them: left in, Hamzah's wife reads as
    #: Queen Noor's daughter, and a wife's married name ("Princess Ghazi of
    #: Jordan") reads as evidence that she descends from the house she married.
    married_in: bool = False


def _tokens(element, top: bool = True) -> Iterable[Tuple[str, str]]:
    """(kind, text) in document order, where kind is "text" or "link:<title>".

    Written as an explicit walk rather than `itertext()` because the *position*
    of a link relative to the description separator is the whole question.
    """
    if element.tag in DROP_TAGS:
        if not top and element.tail:
            yield "text", element.tail
        return
    if element.tag == "a":
        title = _article_title(element)
        text = element.text_content() or ""
        yield (f"link:{title}" if title else "text"), text
        if not top and element.tail:
            yield "text", element.tail
        return
    if element.text:
        yield "text", element.text
    for child in element:
        yield from _tokens(child, top=False)
    if not top and element.tail:
        yield "text", element.tail


def _article_title(anchor) -> Optional[str]:
    """The article an anchor points at, or None if it points anywhere else.

    Rejects red links (`?action=edit`), namespaced targets and section-only
    links, so a reference marker or a category never becomes a person.
    """
    href = anchor.get("href") or ""
    if not href.startswith("/wiki/"):
        return None
    title = href[len("/wiki/"):].split("#")[0]
    if not title or ":" in title:
        return None
    if anchor.get("class") and "new" in (anchor.get("class") or ""):
        return None
    return title.replace("_", " ")


def _lead(element) -> Tuple[Optional[str], str]:
    """The linked article and printed name in an item's *name* part."""
    links, name = _leads(element)
    return (links[0][0] if links else None), name


def _leads(element) -> Tuple[List[Tuple[str, str]], str]:
    """The couple an item names, if it names one, plus its printed name part.

    A bullet naming two people joins them with nothing but "and":
    "[[Hamzah]] and [[Princess Basmah]]". Requiring *exactly* that is what keeps
    the test structural and tight — "two links in the item" is far too loose,
    and matched "[[Muhammad bin Fahd]] (1950–2025) Former governor of the
    [[Eastern Province]]", which would have entered a province as a person and
    married it to a prince. The gloss that follows a real couple says
    "half-brother and half-sister-in-law", carrying the same word one level out,
    so the word alone proves nothing either; only its position does.
    """
    links: List[Tuple[str, str]] = []
    shown: List[str] = []
    between: List[str] = []
    joined = True
    for kind, text in _tokens(element):
        if kind.startswith("link:"):
            if links and "".join(between).strip().casefold() not in ("and", "&"):
                joined = False
            links.append((kind[len("link:"):], " ".join(text.split())))
            between = []
        else:
            between.append(text)
        cut = DESCRIPTION_CUT.search(text)
        shown.append(text[: cut.start()] if cut else text)
        if cut:
            break
    name = " ".join("".join(shown).split())
    return (links[:2] if len(links) > 1 and joined else links[:1]), name


def _cut_gloss(name: str) -> str:
    """Drop an annotating parenthetical, keeping a regnal marker.

    The gloss is often cut off mid-way by the description separator before this
    sees it — "Princess Muna (King Hussein's second wife" — so an unclosed
    bracket has to be cut as well as a closed one, or the name keeps half a
    sentence and `name_chain` reads it as ancestry.
    """
    match = GLOSS.search(name)
    if match and not REGNAL.match(match.group(1).strip()):
        name = name[: match.start()].strip()
    if name.count("(") > name.count(")"):
        name = name[: name.rindex("(")].strip()
    return name


def _heading_of(node) -> Optional[Tuple[str, str]]:
    """(level tag, text) if this block is a section heading."""
    found = node.xpath(".//h1|.//h2|.//h3|.//h4|.//h5|.//h6")
    if node.tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
        found = [node]
    if not found:
        return None
    heading = found[0]
    text = " ".join(
        "".join(
            part for part in heading.itertext()
        ).split()
    )
    # MediaWiki renders an "[edit]" affordance inside the heading.
    text = re.sub(r"\[\s*edit\s*\]\s*$", "", text).strip()
    return heading.tag, text


def _walk_list(
    node, *, chapter: str, section: str, hatnote: Tuple[str, ...],
    glosses: bool, depth: int = 1,
    parent: Optional[str] = None, parent_link: Optional[str] = None,
) -> List[Listed]:
    """A list and every list nested inside it, carrying the nesting down.

    `en:Hashemites` states descent by indentation: a wife at one level, her
    children at the next, hers at the next again. Reading only the outermost
    items — which is all a flat `./li` gets, because a nested list renders
    *inside* its parent's `<li>` — would return the four wives and lose the
    seventy people the article exists to place.
    """
    out: List[Listed] = []
    for item in node.xpath("./li"):
        links, name = _leads(item)
        if glosses:
            name = _cut_gloss(name)
        name = name.strip(" ,;·-–—")
        # One bullet, two links: a couple. Each is emitted under their own name
        # so the chain a patronymic gives is theirs, and each points at the
        # other so the children below can take one parent from each.
        pairs = links[:2] if len(links) > 1 else [(links[0] if links else (None, name))]
        entries: List[Listed] = []
        for index, (link, shown) in enumerate(pairs):
            other = pairs[1 - index] if len(pairs) > 1 else (None, None)
            married_in = index > 0
            entries.append(Listed(
                name=(shown or name) if len(pairs) > 1 else name,
                link=link, chapter=chapter, section=section,
                section_links=hatnote, depth=depth,
                # The in-law is listed here but descends from somewhere else,
                # so the bullet above is not their parent.
                parent=None if married_in else parent,
                parent_link=None if married_in else parent_link,
                partner=other[1], partner_link=other[0],
                married_in=married_in,
            ))
        out.extend(entry for entry in entries if entry.name)
        # The children hang off whoever this bullet named first — the blood
        # descendant, whom the article lists before the in-law they married.
        head = entries[0] if entries else None
        for nested in item.xpath("./ul|./ol"):
            out.extend(_walk_list(
                nested, chapter=chapter, section=section, hatnote=hatnote,
                glosses=glosses, depth=depth + 1,
                parent=head.name if head else parent,
                parent_link=head.link if head else parent_link,
            ))
    return out


def parse_genealogy(page_html: str, glosses: bool = False) -> List[Listed]:
    """Every person a genealogy article lists, with the heading that lists them.

    Handles both shapes one article uses at once: `en:Descendants of Ibn Saud`
    tabulates nine of Ibn Saud's wives' children in `Name | Lifespan | Notes`
    wikitables and lists the other twelve as numbered items, purely by which
    editor wrote the section. A parser that read only one shape would silently
    lose half the first generation.

    Set `glosses` for an article that annotates each entry with a parenthetical
    describing it rather than naming it (`en:Hashemites`); see `GLOSS`.
    """
    doc = lxml_html.fromstring(page_html)
    roots = doc.xpath("//div[contains(@class,'mw-parser-output')]")
    root = roots[0] if roots else doc

    out: List[Listed] = []
    chapter = section = ""
    hatnote: Tuple[str, ...] = ()
    for node in root:
        heading = _heading_of(node)
        if heading is not None:
            level, text = heading
            if level in ("h1", "h2"):
                chapter, section = text, ""
            else:
                section = text
            hatnote = ()
            continue
        classes = node.get("class") or ""
        # {{main|X}} renders as a hatnote div; its links name the section's own
        # subject, which for a wife's section is her item.
        if node.tag == "div" and ("hatnote" in classes or "dablink" in classes):
            hatnote = tuple(
                title for title in
                (_article_title(a) for a in node.xpath(".//a"))
                if title
            )
            continue
        if node.tag in ("ol", "ul"):
            out.extend(_walk_list(
                node, chapter=chapter, section=section, hatnote=hatnote,
                glosses=glosses,
            ))
            continue
        if node.tag != "table" or "wikitable" not in classes:
            continue
        # A `Name | Lifespan | Notes` table: the name is the first cell and the
        # lifespan the second, so read cells rather than the whole row.
        for item in node.xpath(".//tr")[1:]:
            cells = item.xpath("./td|./th")
            if not cells:
                continue
            link, name = _lead(cells[0])
            lifespan = (cells[1].text_content() or "").strip() if len(cells) > 1 else ""
            name = name.strip(" ,;·-–—")
            if not name:
                continue
            out.append(Listed(
                name=name, link=link, chapter=chapter, section=section,
                lifespan=lifespan, section_links=hatnote, depth=1,
            ))
    return out


def name_chain(name: str) -> List[str]:
    """A patronymic name as its lineage: given name, father's, grandfather's…

    "Mohammed bin Salman bin Abdulaziz Al Saud" → ["mohammed", "salman",
    "abdulaziz"]. The house name is dropped, because it names the dynasty and
    not a person, and a regnal number stays glued to the name part it
    distinguishes ("turki i") — that marker is the only thing separating two
    sons of Ibn Saud who share a given name.
    """
    words = fold(name).replace("-", " ").split()
    parts: List[List[str]] = [[]]
    for word in words:
        clean = word.strip(".,()")
        if not clean:
            continue
        if clean in CONNECTORS:
            parts.append([])
            continue
        if clean in HOUSE_LEAD:
            break  # "… Al Saud" ends the chain
        if REGNAL.match(word) and parts[-1]:
            match = REGNAL.match(word)
            parts[-1].append((match.group(1) or match.group(2)).lower())
            continue
        # A lifespan is not part of the name. The descendant lists print it
        # inside the name part — "Abdul Aziz bin Fahd (born 1973)" — because the
        # description separator comes after it, and without this the father's
        # name reads as "fahd born 1973" and matches nobody.
        if clean in LIFESPAN_WORDS or any(char.isdigit() for char in clean):
            break
        parts[-1].append(clean)
    return [" ".join(part) for part in parts if part]


def spouse_matches(section: str, name: str) -> bool:
    """Does a genealogy section heading name the same woman as this item?

    Deliberately not `wd.roster.names_match`, which requires two shared tokens:
    eight of Ibn Saud's wives head their section under a single given name
    ("Shahida", "Mudhi", "Bushra", "Futayma") and would match nothing at all.
    A chain is compared to the depth both sides state, so "Hussa Al Sudairi"
    matches "Hussa bint Ahmed Al Sudairi", and a regnal marker has to agree —
    which is what keeps Bazza (I) and Bazza (II), two different wives, apart.
    """
    left, right = name_chain(section), name_chain(name)
    if not left or not right:
        return False
    depth = min(len(left), len(right))
    return left[:depth] == right[:depth]


@dataclass
class Kin:
    """A resolved person, with what the kinship gates need to read."""

    qid: str
    label: str
    names: List[str] = field(default_factory=list)
    p22: List[str] = field(default_factory=list)
    p25: List[str] = field(default_factory=list)
    p53: List[str] = field(default_factory=list)
    #: Recorded spouses, so a `P26` already on the item is never restated.
    p26: List[str] = field(default_factory=list)
    #: Sex or gender, which is what decides whether a parent bullet is the
    #: father or the mother. Read from the item, never from the printed title:
    #: "Prince"/"Princess" is a good guess and this lane does not guess.
    gender: Optional[str] = None
    birth: Optional[int] = None
    death: Optional[int] = None

    def chains(self) -> List[List[str]]:
        """Every spelling of this person's name, as a lineage."""
        return [name_chain(name) for name in [self.label, *self.names] if name]


#: Youngest a father can be at a child's birth. Deliberately low: the question
#: is whether a candidate is *impossible*, not whether they are likely.
FATHER_MIN_AGE = 16


def _can_father(parent: Kin, child_birth: Optional[int]) -> bool:
    """Could this person have fathered a child born that year?

    The gate that does the real work here. Six pairs of Ibn Saud's sons share a
    given name because an infant died and a later son was named after him, so a
    patronymic alone is ambiguous for all of them — and the infant is excluded
    by having died decades before the grandchild was born.
    """
    if child_birth is None:
        return True
    if parent.birth is not None and child_birth - parent.birth < FATHER_MIN_AGE:
        return False
    return not (parent.death is not None and parent.death < child_birth)


def _matches_father(child: List[str], parent: Kin) -> bool:
    """Does the child's patronymic chain name this parent?

    Two things have to line up, not one. The parent's given name must equal the
    child's *second* chain element — an equality, never a prefix, because
    "Abdullah" and "Abdulaziz" share five letters and half the dynasty. And
    where the child's name states the grandfather too, the parent's own chain
    must agree about him: "Mohammed bin Salman bin Abdulaziz" pins the father to
    a Salman who is himself a son of Abdulaziz, which is a far stronger claim
    than a given-name match.
    """
    if len(child) < 2:
        return False
    named = [c for c in parent.chains() if c and c[0] == child[1]]
    if not named:
        return False
    if len(child) < 3:
        return True
    # The child states the grandfather, so the parent's own patronymic has to
    # agree about him — and a *shorter* spelling of the parent's name is not
    # evidence either way and must not be allowed to pass instead.
    #
    # Letting it pass is how "Sattam bin Khalid bin Nasser Al Saud" was filed
    # under Khalid bin **Faisal**: the alias "Khalid Al Faisal" chains to
    # ["khalid"] alone, the length test short-circuited, and a man was given the
    # wrong father out of the right generation.
    stated = [c for c in named if len(c) >= 2]
    return bool(stated) and any(c[1] == child[2] for c in stated)


def child_chain(printed: str, person: Kin) -> Tuple[List[str], str]:
    """The fullest patronymic available for this person, and why not if none is.

    The article prints a short form — "Abdul Aziz bin Fahd" — where the item's
    own label often carries the whole lineage: "Abdulaziz bin Fahd bin Turki II
    bin Abdulaziz Al Saud". Reading only the printed form throws the grandfather
    away, and the grandfather is what makes this safe: on the short form that
    name resolves to **King Fahd**, and on the full one to a Fahd bin Turki II
    who is a different man one generation further down. That statement was in
    the batch until the chains were unioned.

    Where two spellings disagree about the father outright, neither is used.
    """
    chains = [c for c in [name_chain(printed)] + person.chains() if len(c) >= 2]
    if not chains:
        return [], "no spelling of the name carries a patronymic"
    fathers = {c[1] for c in chains}
    if len(fathers) > 1:
        return [], (
            "spellings of this name disagree about the father: "
            + ", ".join(sorted(fathers))
        )
    return max(chains, key=len), ""


def father_candidates(
    chain: Sequence[str], pool: Sequence[Kin], child_birth: Optional[int]
) -> Tuple[List[Kin], str]:
    """Everyone in the pool the child's name could be naming, and why."""
    if len(chain) < 2:
        return [], "the name carries no patronymic"
    named = [parent for parent in pool if _matches_father(list(chain), parent)]
    if not named:
        return [], f"no {chain[1]!r} in the generation this section names"
    possible = [parent for parent in named if _can_father(parent, child_birth)]
    if not possible:
        return [], (
            f"the only {chain[1]!r} in that generation cannot have fathered "
            f"someone born {child_birth}"
        )
    return possible, ""


def reference(source: str) -> List[Snak]:
    """The article permalink as an import source, never as S854."""
    return [Snak("S4656", Value.url(source))] if source else []


def _record(
    *, campaign: str, lane: str, person: Kin, prop: str, value: str,
    rule: str, concern: str, rationale: str, detail: str, source: str,
    action: str = "apply", flags: Sequence[str] = (),
) -> Record:
    return Record(
        campaign=campaign,
        office=lane,
        subject=Subject(kind="item", qid=person.qid, label=person.label),
        statements=[Statement(prop, Value.item(value), references=reference(source))],
        decision=Decision(action=action, rule=rule, concern=concern,
                          rationale=rationale),
        identity={"method": "genealogy wikilink"},
        flags=list(flags) or [concern],
        signals=[Signal("genealogy", concern, detail, source or None)],
    )


def spouse_records(
    *, campaign: str, lane: str, couples: Sequence[Tuple[Listed, int]],
    people: Dict[str, Kin], source: str, dispositions: Dict[str, str],
) -> List[Record]:
    """`P26` where one bullet names a couple *and* the article gives them issue.

    The pairing itself is one channel, and one channel is not enough — a bullet
    reading "X and Y" is the article's word alone. The second is the children
    nested underneath it: the article is asserting not just that these two are a
    couple but that this is the marriage its next generation descends from.
    A childless pair is reported rather than emitted.

    `couples` is (the entry, how many children the article nests under the pair),
    which the caller counts because only it knows how the list was grouped.
    """
    records: List[Record] = []
    for entry, issue in couples:
        person = people.get(entry.link or "")
        partner = people.get(entry.partner_link or "")
        if person is None or partner is None:
            continue
        if partner.qid in person.p26:
            continue
        if not issue:
            records.append(_record(
                campaign=campaign, lane=lane, person=person,
                prop="P26", value=partner.qid,
                rule="spouse.no_issue", concern="p26",
                rationale="the article pairs them in one bullet and nothing "
                          "else does; a pairing on its own is a single channel",
                detail=f"listed as a couple with {partner.label}, no children "
                       f"nested under them",
                source=source,
                action=dispositions.get("spouse.no_issue", "skip"),
            ))
            continue
        records.append(_record(
            campaign=campaign, lane=lane, person=person,
            prop="P26", value=partner.qid,
            rule="spouse.paired_with_issue", concern="p26",
            rationale="the article names them as a couple and lists the "
                      "children descending from the pair",
            detail=f"listed as a couple with {partner.label}; {issue} "
                   f"child(ren) nested under them",
            source=source,
        ))
    return records


def mother_records(
    *, campaign: str, lane: str, sections: Dict[str, List[Listed]],
    people: Dict[str, Kin], mothers: Dict[str, str], ancestor: str,
    source: str, dispositions: Dict[str, str],
) -> List[Record]:
    """`P25` for children the article files under a named wife.

    Two channels, and the second is the hard part: the section *heading* is a
    name, not an item, and only 2 of the 21 wife sections carry a hatnote naming
    hers. `mothers` is the resolution this campaign managed — by hatnote, or by
    the section's own siblings already recording her, which is a statement made
    by editors who were not this run.

    Gated on the child already recording `P22 = ancestor`: the mother is added
    only where the community already agrees about the father, so the statement
    joins a parentage rather than asserting one on its own.
    """
    records: List[Record] = []
    for section, listed in sections.items():
        mother = mothers.get(section)
        for entry in listed:
            person = people.get(entry.link or "")
            if person is None:
                continue
            if mother is None:
                records.append(_record(
                    campaign=campaign, lane=lane, person=person,
                    prop="P25", value=ancestor,  # unused: the record is a skip
                    rule="mother.unresolved", concern="p25",
                    rationale="no item could be confirmed for the wife this "
                              "section names, so there is nothing to point at",
                    detail=f"listed under {section!r}, whose item is unresolved",
                    source=source,
                    action=dispositions.get("mother.unresolved", "skip"),
                ))
                continue
            if person.p25:
                continue  # a mother is already recorded; a second would be wrong
            if ancestor not in person.p22:
                records.append(_record(
                    campaign=campaign, lane=lane, person=person,
                    prop="P25", value=mother,
                    rule="mother.father_not_recorded", concern="p25",
                    rationale="the item does not record the father this article "
                              "gives them, so the second channel is missing",
                    detail=f"listed under {section!r} → {mother}, but P22 is "
                           f"{', '.join(person.p22) or 'unset'}",
                    source=source,
                    action=dispositions.get("mother.father_not_recorded", "skip"),
                ))
                continue
            records.append(_record(
                campaign=campaign, lane=lane, person=person,
                prop="P25", value=mother,
                rule="mother.section_and_father", concern="p25",
                rationale="the genealogy lists them among this wife's children "
                          "and the item already records the father she shares",
                detail=f"listed under {section!r}, resolved to {mother}; "
                       f"P22 already {ancestor}",
                source=source,
            ))
    return records


def contradictory_links(listed: Sequence[Listed]) -> Set[str]:
    """Article titles the genealogy files in two different generations at once.

    One link cannot be both a grandson and a great-grandson of the same man, so
    a title appearing under both is a wiki error and neither entry can be
    trusted to be about the item it points at. `en:Descendants of Ibn Saud` has
    exactly one: `Abdulaziz bin Fahd bin Turki II bin Abdulaziz Al Saud` is
    listed as a grandson "born 1973" and as a great-grandson "born 1990" — two
    different people, one of whose links is wrong.

    Cheap to detect and worth detecting: the section heading is what closes the
    candidate set for a patronymic, so a person under the wrong heading gets
    resolved against the wrong generation entirely.
    """
    chapters: Dict[str, Set[str]] = {}
    for entry in listed:
        if entry.link:
            chapters.setdefault(entry.link, set()).add(entry.chapter)
    return {link for link, seen in chapters.items() if len(seen) > 1}


def father_records(
    *, campaign: str, lane: str, listed: Sequence[Listed],
    people: Dict[str, Kin], pool: Sequence[Kin], generation: str,
    source: str, dispositions: Dict[str, str], contradictory: Set[str] = frozenset(),
) -> List[Record]:
    """`P22` where a patronymic resolves inside the generation a heading names.

    The heading is what closes the candidate set and makes this mechanical
    rather than a guess: everyone under "Patrilineal grandsons" has a father who
    is a son of the ancestor, so "Khalid bin Faisal" is resolved against 45
    people and not against Wikidata.
    """
    records: List[Record] = []
    for entry in listed:
        person = people.get(entry.link or "")
        if person is None or person.p22:
            continue
        if entry.link in contradictory:
            records.append(_record(
                campaign=campaign, lane=lane, person=person,
                prop="P22", value=pool[0].qid,
                rule="father.generation_contradicted", concern="p22",
                rationale="the article lists this same link in two generations, "
                          "so the heading cannot say which one closes the "
                          "candidate set",
                detail=f"'{entry.name}' under {entry.section!r}, and the same "
                       "link appears in another chapter",
                source=source,
                action=dispositions.get("father.generation_contradicted", "skip"),
            ))
            continue
        chain, unusable = child_chain(entry.name, person)
        possible, why = (
            ([], unusable) if unusable
            else father_candidates(chain, pool, person.birth)
        )
        if len(possible) == 1:
            father = possible[0]
            records.append(_record(
                campaign=campaign, lane=lane, person=person,
                prop="P22", value=father.qid,
                rule="father.patronymic_in_generation", concern="p22",
                rationale=f"the article lists them as a {generation} and their "
                          "patronymic names exactly one person of that "
                          "generation who could have fathered them",
                detail=f"'{entry.name}' under {entry.section!r} → "
                       f"{father.qid} {father.label}",
                source=source,
            ))
            continue
        records.append(_record(
            campaign=campaign, lane=lane, person=person,
            prop="P22", value=possible[0].qid if possible else pool[0].qid,
            rule="father.ambiguous" if possible else "father.unresolved",
            concern="p22",
            rationale=(
                "the patronymic names more than one person of this generation "
                "and no lifetime rules them out"
                if possible else
                f"the patronymic cannot be resolved: {why}"
            ),
            detail=f"'{entry.name}' under {entry.section!r} → "
                   + (", ".join(f"{p.qid} {p.label}" for p in possible) or why),
            source=source,
            action=dispositions.get(
                "father.ambiguous" if possible else "father.unresolved", "skip"
            ),
        ))
    return records


def house_records(
    *, campaign: str, lane: str, listed: Sequence[Listed],
    people: Dict[str, Kin], house: str, markers: Sequence[str],
    kin_qids: Set[str], source: str, dispositions: Dict[str, str],
) -> List[Record]:
    """`P53` for descendants the article names and whose own record agrees.

    The article alone is one channel. The second is the person's own item: their
    name carries the house's own name, or they already record a parent who is in
    it. Neither is emitted alone — a name without the descent is a namesake, and
    a place in someone's family tree without either is an article's claim about
    a person who may not be the one this item describes.

    `P53` is multi-valued and a branch house is a real second value, so the
    question is whether *this* house is recorded, never whether any is.
    """
    # A list, not a set: the marker reported is the first that matches, and set
    # iteration order varies between processes, so the same run wrote a
    # different rationale each time and no baseline could be reproduced.
    wanted = list(dict.fromkeys(fold(marker) for marker in markers))
    records: List[Record] = []
    for entry in listed:
        person = people.get(entry.link or "")
        if person is None or house in person.p53:
            continue
        spellings = [person.label, *person.names, entry.name]
        matched = next(
            (marker for marker in wanted
             if any(marker in fold(spelling) for spelling in spellings)),
            None,
        )
        related = sorted(
            set(person.p22 + person.p25) & kin_qids
        )
        if matched is None and not related:
            records.append(_record(
                campaign=campaign, lane=lane, person=person,
                prop="P53", value=house,
                rule="house.one_channel", concern="p53",
                rationale="the article lists them, but nothing on the item — "
                          "neither the name nor a recorded parent — says the "
                          "same, and one channel is not enough",
                detail=f"listed under {entry.section!r} as '{entry.name}'",
                source=source,
                action=dispositions.get("house.one_channel", "skip"),
            ))
            continue
        second = (f"their name carries {matched!r}" if matched
                  else f"their recorded parent {related[0]} is of this house")
        records.append(_record(
            campaign=campaign, lane=lane, person=person,
            prop="P53", value=house,
            rule="house.listed_and_named", concern="p53",
            rationale="the genealogy lists them as a descendant and "
                      + second,
            detail=f"listed under {entry.section!r} as '{entry.name}'; {second}",
            source=source,
        ))
    return records


__all__ = [
    "Kin", "Listed", "child_chain", "contradictory_links", "father_candidates",
    "father_records", "house_records", "mother_records", "name_chain",
    "parse_genealogy", "spouse_matches",
]
