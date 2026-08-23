"""Everything known about one person, assembled once and paid for once.

The campaigns spent their requests per *office*: fetch a roster, identify its
rows, write P39. That never asks about the offices nobody configured. The
enrichment loop spends them per *person* instead — and to make one LLM call per
person affordable, the evidence has to arrive in one packet, already parsed,
with every fragment citable.

Two rules hold the cost down:

* **Shared evidence is fetched once, not per person.** A roster page names fifty
  people; fetching it fifty times is fifty times the cost and the same bytes.
  `RosterIndex` reads a spec's list articles once and hands each person the rows
  that name them — which is also where the good dates are, because a roster
  states a term and a biography usually does not.
* **Every fragment is quotable.** The model is required to cite a verbatim span
  for each proposal, and `Dossier.contains` checks it afterwards. That turns
  "the model asserted a date" into "the model pointed at a date in a document we
  fetched", which is the cheapest hallucination gate available.

Nothing here fetches anything new: it is an assembly layer over `wd/api.py`,
`wd/wikipedia.py`, `wd/roster.py`, `wd/officebox.py`, `wd/infobox.py` and
`wd/human.py`.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from lxml import html as lxml_html
from requests import Session

from wd.api import best_label, fetch_entities
from wd.human import Verdict as HumanVerdict
from wd.human import verify as verify_human
from wd.infobox import Evidence, parse_categories, parse_lead_html, parse_wikitext
from wd.infobox import worth_rendering
from wd.officebox import Tenure, parse_officebox
from wd.roster import Roster, RosterRow, drop_keeping_tail, names_match, parse_rosters
from wd.shape import type_closure
from wd.wikipedia import (
    fetch_html,
    fetch_lead_html,
    fetch_pages,
    permalink,
    sitelink_title,
    wikipedia_langs,
)

#: How much rendered article prose one person is worth. A head of state's
#: article runs past 100k characters and the tenure signal is front-loaded, so
#: the budget is a real limit rather than a safety net — but it is applied to
#: *sections*, and a truncated section is reported as truncated rather than
#: silently dropped.
BODY_BUDGET = 24000

#: Sections that never carry a tenure. Trimming them is what buys the budget.
#: Deliberately multilingual and deliberately incomplete: it covers the wikis
#: `wd/roster.py` already reads (en, es, cs, ru, uk, be, ar, fa) and nothing
#: else, so a section in an unlisted language costs budget rather than being
#: silently mis-skipped. Getting this wrong in the safe direction is cheap.
SKIP_SECTIONS = re.compile(
    r"^\s*("
    r"references|notes|citations|external links|further reading|bibliography|"
    r"see also|sources|footnotes|awards|honours|honors|publications|"
    r"selected works|filmography|discography|gallery"
    # cs
    r"|odkazy|reference|extern[ií] odkazy|literatura|souvisej[ií]c[ií] [čc]l[áa]nky"
    r"|ocen[ěe]n[ií]"
    # es
    r"|referencias|enlaces externos|bibliograf[ií]a|v[ée]ase tambi[ée]n"
    r"|notas|premios"
    # ru / uk / be
    r"|примечания|литература|ссылки|см\.? также|источники|нагороди|награды"
    r"|примітки|посилання|джерела|зноски|глядзіце таксама"
    # ar / fa
    r"|مراجع|وصلات خارجية|انظر أيضا|منابع|پیوند به بیرون|جستارهای وابسته"
    r")\b",
    re.I,
)


@dataclass
class Fragment:
    """One citable piece of evidence."""

    kind: str            # item | lead | officebox | categories | body | roster
    source: str          # short citation id, e.g. "en:Jack_Smith#lead"
    text: str
    url: Optional[str] = None
    truncated: bool = False

    def render(self) -> str:
        head = f"### [{self.source}] {self.kind}"
        if self.url:
            head += f"\n<{self.url}>"
        if self.truncated:
            head += "\n(truncated to fit the evidence budget)"
        return f"{head}\n\n{self.text}"


@dataclass
class Dossier:
    qid: str
    label: Optional[str] = None
    #: `wd/human.py`'s reading of the item — defects, gaps, every existing
    #: tenure with its occupancy verdict. What must *not* be re-proposed.
    item: Dict = field(default_factory=dict)
    fragments: List[Fragment] = field(default_factory=list)
    #: Pre-parsed structured signals, kept beside the prose they came from.
    officebox: List[Tenure] = field(default_factory=list)
    roster_rows: List[Tuple[str, RosterRow]] = field(default_factory=list)
    birth_evidence: Optional[Evidence] = None
    langs: Tuple[str, ...] = ()
    #: Positions whose recorded tenures were hidden from `item`. Backtest mode
    #: only: scoring the loop against statements it was shown measures nothing.
    withheld: Tuple[str, ...] = ()

    @property
    def empty(self) -> bool:
        """No article anywhere. There is nothing to judge and nothing to buy."""
        return not self.fragments

    def contains(self, quote: str) -> bool:
        """Does this span actually occur in the evidence?

        Whitespace-insensitive and nothing else: a model that paraphrases fails
        the check, which is the intent. Compare
        `scripts/classify_jurisdictions.py`'s stray-QID guard — a schema
        constrains a field's shape and never its value.
        """
        needle = " ".join((quote or "").split())
        if len(needle) < 8:      # too short to be evidence of anything
            return False
        # Check against the *rendered* dossier — the exact text the model was
        # shown — and not against `fragments`. Three sections are rendered from
        # structured fields rather than from a fragment: the item's own record,
        # the officebox tenures and the roster rows. Checking only fragments
        # made a faithful citation of those unverifiable, and it rejected four
        # correct proposals in Poland's run whose quote was the officebox line
        # this file prints ("Member of the Sejm — 2023-11-13"). A quote gate that
        # fails on evidence we presented is worse than no gate: it discards
        # truthful work and looks like the model hallucinating.
        return needle in " ".join(self.render().split())

    def render(self) -> str:
        head = [
            f"# {self.label or self.qid} ({self.qid})",
            "",
            "## What Wikidata already records",
            "",
            "Do not propose anything already here.",
            "",
            "```json",
            json.dumps(self.item, ensure_ascii=False, indent=1, sort_keys=True),
            "```",
            "",
        ]
        if self.officebox:
            head += [f"## [{self.qid}#officebox] tenures from the article's own "
                     "infobox", ""]
            for tenure in self.officebox:
                span = "–".join(filter(None, (tenure.start, tenure.end))) or "undated"
                flags = " ".join(
                    f for f, on in (("acting", tenure.acting),
                                    ("incumbent", tenure.incumbent)) if on
                )
                head.append(
                    f"* {tenure.office} — {span}"
                    + (f" [{flags}]" if flags else "")
                    + (f"  (raw: {tenure.period_raw})" if tenure.period_raw else "")
                )
            head.append("")
        if self.roster_rows:
            head += ["## Rows naming this person in officeholder lists "
                     "(cite the [source] on the row)", ""]
            for source, row in self.roster_rows:
                span = "–".join(filter(None, (row.start, row.end))) or "undated"
                head.append(
                    f"* [{source}] {row.section or ''} | {row.name} | {span}"
                    + (" | acting" if row.acting else "")
                    + (f" | raw: {row.period_raw}" if row.period_raw else "")
                )
            head.append("")
        head += ["## Sources", ""]
        return "\n".join(head + [f.render() for f in self.fragments])


# --------------------------------------------------------------------------- #
# Shared evidence: one fetch per page, not per person.
# --------------------------------------------------------------------------- #


@dataclass
class RosterIndex:
    """Officeholder-list rows, indexed by who they name.

    Built once per run from the spec's list articles. A row is reachable two
    ways, and both are needed: by the QID its wikilink resolves to (exact, and
    what `wd/campaign.py:identify` calls a strong identity) and by name
    (necessary, because most rosters link some rows and not others).
    """

    by_qid: Dict[str, List[Tuple[str, RosterRow]]] = field(default_factory=dict)
    rows: List[Tuple[str, RosterRow]] = field(default_factory=list)
    pages: List[str] = field(default_factory=list)

    def add(
        self, source: str, rosters: Sequence[Roster], titles: Dict[str, str]
    ) -> None:
        self.pages.append(source)
        for roster in rosters:
            for row in roster.rows:
                self.rows.append((source, row))
                qid = titles.get(row.link or "")
                if qid:
                    self.by_qid.setdefault(qid, []).append((source, row))

    def lookup(self, qid: str, names: Iterable[str]) -> List[Tuple[str, RosterRow]]:
        """Rows for this person: linked rows first, then unlinked name matches.

        Name matching is deliberately the weaker channel and stays labelled as
        such — a bare name match is a namesake risk, which is why
        `wd/policy.py` refuses to apply on one alone.
        """
        found = list(self.by_qid.get(qid, ()))
        seen = {id(row) for _, row in found}
        wanted = [n for n in names if n]
        for source, row in self.rows:
            if id(row) in seen or row.link:
                continue
            if any(names_match(row.name, name) for name in wanted):
                found.append((source, row))
        return found


def build_roster_index(
    session: Session,
    pages: Sequence[Tuple[str, str]],
    resolve: Optional[object] = None,
) -> RosterIndex:
    """Parse a run's officeholder lists once. `pages` is (lang, title) pairs.

    `resolve` is a callable turning article titles into QIDs — pass
    `wd/campaign.py:resolve_titles` bound to the session; without it rows are
    reachable by name only.
    """
    index = RosterIndex()
    for lang, title in pages:
        page = fetch_html(session, lang, title)
        if not page:
            continue
        rosters = parse_rosters(page["html"])
        links = {row.link for roster in rosters for row in roster.rows if row.link}
        titles: Dict[str, str] = {}
        if resolve and links:
            titles = resolve(session, lang, sorted(links))    # type: ignore[operator]
        index.add(f"{lang}:{title}", rosters, titles)
    return index


# --------------------------------------------------------------------------- #
# Per-person assembly
# --------------------------------------------------------------------------- #


def article_text(page_html: str, budget: int = BODY_BUDGET) -> Tuple[str, bool]:
    """Rendered article → prose, reference apparatus dropped, budget applied.

    Rendered HTML rather than wikitext for the same reason `wd/roster.py` uses
    it (WORKBENCH.md): templates have already run, so a date reads as a date.
    Sections are kept whole — a half-sentence is not quotable evidence.
    """
    doc = lxml_html.fromstring(page_html)
    # `drop_keeping_tail`, never `remove()`: lxml takes the element's tail with
    # it, and for a citation superscript the tail is the rest of the sentence.
    # Removing them naively turned "…added in July.[12] The indictment charged…"
    # into "…added in July.indictment on four charges." — text lost, silently,
    # in the middle of a quotable span. Same trap as `wd/roster.py` §7.
    for bad in doc.xpath(
        "//table | //sup[contains(@class,'reference')] | //style | //script"
        " | //*[contains(@class,'navbox')] | //*[contains(@class,'reflist')]"
        " | //*[contains(@class,'mw-editsection')]"
    ):
        if bad.getparent() is not None:
            drop_keeping_tail(bad)
    chunks, keep = [], True
    for element in doc.iter("h2", "h3", "h4", "p", "li", "dd"):
        text = " ".join((element.text_content() or "").split())
        if not text:
            continue
        if element.tag in ("h2", "h3", "h4"):
            keep = not SKIP_SECTIONS.match(text)
            if keep:
                chunks.append(f"\n## {text}")
            continue
        if keep:
            chunks.append(text)
    body, truncated = "\n".join(chunks).strip(), False
    if len(body) > budget:
        cut = body.rfind("\n", 0, budget)
        body, truncated = body[: cut if cut > 0 else budget], True
    return body, truncated


#: Fallback order once the caller's preferences are exhausted. Alphabetical
#: order is actively wrong here: it puts `arz` (Egyptian Arabic, largely
#: bot-generated stubs) ahead of `ar`, `de` and `fr` on every article, so the
#: second wiki read was reliably the least informative one available.
WIKI_PRIORITY = (
    "en", "de", "fr", "es", "ru", "it", "pt", "nl", "pl", "ja", "zh", "ar",
    "uk", "cs", "sv", "tr", "fa", "he", "ko", "id", "hi", "fi", "da", "no",
    "hu", "ro", "el", "bg", "ca", "sr", "sk", "hr", "lt", "lv", "et", "vi",
)


def pick_langs(
    entity: dict, prefer: Sequence[str] = ("en",), limit: int = 2
) -> List[str]:
    """Which wikis to read, preferred first. Fall back to whatever exists.

    Two by default: a second wiki is often the only one that dates a tenure,
    and past two the marginal article repeats the first.
    """
    have = set(wikipedia_langs(entity))
    ordered = [lang for lang in prefer if lang in have]
    for lang in WIKI_PRIORITY:
        if lang in have and lang not in ordered:
            ordered.append(lang)
    ordered += sorted(have - set(ordered))
    return ordered[:limit]


def build(
    session: Session,
    qid: str,
    *,
    entity: Optional[dict] = None,
    closure: Optional[Dict[str, Set[str]]] = None,
    topics: Optional[Dict[str, Set[str]]] = None,
    prefer: Sequence[str] = ("en",),
    langs_limit: int = 2,
    rosters: Optional[RosterIndex] = None,
    body: bool = True,
    withhold: Sequence[str] = (),
) -> Dossier:
    """Assemble one person's dossier.

    `topics` maps a position QID to the topics `wd/shape.py` resolved for it. It
    is the *office's*, not the person's — an after-office window belongs to the
    office, and judging a tenure without one reads every ex-minister as dropped
    (`research/person_items.md` §5).

    Deliberately no `accepted` filter: a dossier's job is to disclose everything
    Wikidata already records, so the model can be told not to re-propose it.
    Scoping tenures to one run's accepted set is what hid two existing P39
    statements behind `out_of_scope: 2` the first time this ran.

    `withhold` is the exception, and it exists for one purpose: a backtest scores
    the loop against tenures Wikidata already holds, and a dossier that shows
    them measures the model's ability to copy a list. Hiding those positions
    turns the recorded statements into a labelled test set the evidence has to
    rediscover on its own.
    """
    if entity is None:
        entity = fetch_entities(session, [qid], max_age=0).get(qid) or {}
    closure = closure or type_closure(session, [qid])
    verdict: HumanVerdict = verify_human(
        entity, closure.get(qid, set()), topics=topics
    )
    item = verdict.as_dict()
    # Resolve the label of every position the person already holds. Without it
    # the "already recorded" section is a list of bare QIDs, and the model
    # cannot tell whether a statement it is about to propose is the same office
    # under another item — the first run asked for exactly this, in a note.
    held = [t["position"] for t in item["tenures"] if t.get("position")]
    if held:
        labels = fetch_entities(session, sorted(set(held)), props="labels")
        for tenure in item["tenures"]:
            tenure["position_label"] = best_label(
                labels.get(tenure.get("position") or "", {})
            )
    if withhold:
        hidden = set(withhold)
        item["tenures"] = [
            t for t in item["tenures"] if t.get("position") not in hidden
        ]
    dossier = Dossier(
        qid=qid, label=best_label(entity), item=item, withheld=tuple(withhold)
    )

    langs = pick_langs(entity, prefer=prefer, limit=langs_limit)
    dossier.langs = tuple(langs)
    for lang in langs:
        title = sitelink_title(entity, lang)
        if not title:
            continue
        pages = fetch_pages(session, lang, [title])
        page = pages.get(title)
        if not page:
            continue
        source = f"{lang}:{page['title']}"
        url = permalink(lang, page["revid"])
        wikitext = page["wikitext"]

        dossier.officebox.extend(parse_officebox(wikitext, lang))

        if page.get("categories"):
            dossier.fragments.append(
                Fragment(
                    kind="categories", source=f"{source}#categories", url=url,
                    text="\n".join(f"* {c}" for c in page["categories"]),
                )
            )

        # The birth-date channel pair, already built and already measured: the
        # infobox microformat against the article's own births category.
        if lang == langs[0]:
            evidence = Evidence(qid=qid, title=page["title"], revid=page["revid"])
            parse_wikitext(evidence, wikitext)
            parse_categories(evidence, page["categories"])
            if worth_rendering(wikitext):
                lead = fetch_lead_html(session, lang, page["title"])
                if lead:
                    parse_lead_html(evidence, lead)
            dossier.birth_evidence = evidence

        if body:
            rendered = fetch_html(session, lang, page["title"])
            if rendered:
                text, truncated = article_text(rendered["html"])
                if text:
                    dossier.fragments.append(
                        Fragment(
                            kind="body", source=f"{source}#article",
                            url=permalink(lang, rendered["revid"]),
                            text=text, truncated=truncated,
                        )
                    )

    if rosters is not None:
        names = [dossier.label] + [
            sitelink_title(entity, lang) for lang in dossier.langs
        ]
        dossier.roster_rows = rosters.lookup(qid, names)
        for source, row in dossier.roster_rows:
            dossier.fragments.append(
                Fragment(
                    kind="roster", source=source,
                    text=" | ".join(str(c) for c in (row.cells or [row.name])),
                )
            )
    return dossier
