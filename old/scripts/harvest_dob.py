#!/usr/bin/env python
"""Harvest missing P569 (date of birth) from Wikipedia infoboxes, per country.

    python scripts/harvest_dob.py --country Q1033 --name nigeria
    python scripts/harvest_dob.py --country Q668 --name india --limit 500

Enumerates people with a position held (P39) and no P569 that do have an
article on the chosen Wikipedia, reads the birth date out of the infobox, and
cross-checks it against the article's `Category:NNNN births`. Writes to
data/birthdates/<name>/:

  plan.md       every candidate, grouped by verdict, for review
  day.qs        day-precision dates where both signals agree
  year.qs       year-precision dates where both signals agree
  evidence.json the raw per-article signals

Countries differ enormously in how much of this is reachable — 88% of India's
gap items have an enwiki article against 16% globally — so scope one country
at a time and read the plan before running anything.
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wd.api import sparql
from wd.http import REPO_ROOT, make_session
from wd.infobox import (
    Evidence,
    parse_categories,
    parse_lead_html,
    parse_wikitext,
    worth_rendering,
)
from wd.wikipedia import fetch_lead_html, fetch_pages, permalink

BASE = REPO_ROOT / "data" / "birthdates"

# Statement-node scans time out on WDQS, but NOT EXISTS on an already-bound
# ?person is a lookup. p:P569 rather than wdt:P569 so that a somevalue or
# deprecated-only birth date still counts as present.
GAP_QUERY = """
SELECT DISTINCT ?person ?title WHERE {
  ?person wdt:P31 wd:Q5 ; wdt:P39 ?position ; wdt:P27 wd:%(country)s .
  ?article schema:about ?person ;
           schema:isPartOf <https://%(lang)s.wikipedia.org/> ;
           schema:name ?title .
  FILTER NOT EXISTS { ?person p:P569 ?statement }
}
"""

# Imported-from-Wikipedia is what the community actually uses on these values
# (P143=Q328 is the single most common reference on P569); the permalink makes
# the specific revision auditable.
WIKI_ITEM = {"en": "Q328", "de": "Q48183", "fr": "Q8447", "es": "Q8449"}


def qs_time(value: str, precision: int) -> str:
    """QuickStatements time literal. Year precision zeroes month and day."""
    if precision >= 11:
        return f"+{value}T00:00:00Z/11"
    return f"+{value[:4]}-00-00T00:00:00Z/9"


def collect(session, country: str, lang: str, limit: int) -> list[Evidence]:
    rows = sparql(session, GAP_QUERY % {"country": country, "lang": lang})
    print(f"{len(rows)} people with P39, no P569, and a {lang}wiki article")
    if limit:
        rows = rows[:limit]

    by_title = {row["title"]: row["person"] for row in rows}
    pages = fetch_pages(session, lang, list(by_title))
    print(f"fetched {len(pages)} articles ({len(by_title) - len(pages)} missing)")

    evidence: list[Evidence] = []
    render = []
    for title, qid in by_title.items():
        page = pages.get(title)
        if page is None:
            continue
        item = Evidence(qid=qid, title=page["title"], revid=page["revid"])
        parse_wikitext(item, page["wikitext"])
        parse_categories(item, page["categories"])
        evidence.append(item)
        if worth_rendering(page["wikitext"]):
            render.append(item)

    # Two items whose titles redirect to one article are duplicate Wikidata
    # items. Writing the date to both would paper over a merge candidate, so
    # note the collision and let review deal with it.
    by_article: dict[str, list[Evidence]] = {}
    for item in evidence:
        by_article.setdefault(item.title, []).append(item)
    for group in by_article.values():
        if len(group) > 1:
            for item in group:
                item.shares_article_with = [o.qid for o in group if o is not item]

    # Rendering costs one request per article, so only the triaged candidates
    # get one; the rest cannot carry a microformat date anyway.
    print(f"rendering {len(render)} candidates of {len(evidence)}")
    for index, item in enumerate(render, 1):
        if index % 100 == 0:
            print(f"  {index}/{len(render)}")
        try:
            html = fetch_lead_html(session, lang, item.title)
        except Exception as exc:  # a single bad article must not sink the run
            print(f"  {item.qid} {item.title}: render failed ({exc})")
            continue
        if html:
            parse_lead_html(item, html)
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--country", required=True, help="Citizenship QID, e.g. Q1033")
    parser.add_argument("--name", required=True, help="Output directory name")
    parser.add_argument("--lang", default="en", help="Wikipedia language (default en)")
    parser.add_argument("--limit", type=int, default=0, help="Cap candidates (testing)")
    args = parser.parse_args()

    session = make_session()
    evidence = collect(session, args.country, args.lang, args.limit)

    out = BASE / args.name
    out.mkdir(parents=True, exist_ok=True)
    verdicts = Counter(item.verdict for item in evidence)

    day_qs: list[str] = []
    year_qs: list[str] = []
    source = WIKI_ITEM.get(args.lang)
    for item in evidence:
        if item.verdict != "batch":
            continue
        ref = ""
        if source:
            ref = f"\tS143\t{source}"
            if item.revid:
                ref += f'\tS4656\t"{permalink(args.lang, item.revid)}"'
        line = f"{item.qid}\tP569\t{qs_time(item.value, item.precision)}{ref}"
        (day_qs if item.precision == 11 else year_qs).append(line)

    md = [
        f"# Birth dates from {args.lang}wiki infoboxes — {args.name}",
        "",
        (
            f"country: {args.country} · candidates: {len(evidence)} · "
            f"verdicts: {dict(verdicts)}"
        ),
        "",
        f"`day.qs`: {len(day_qs)} statements · `year.qs`: {len(year_qs)} statements.",
        "",
        "Only `batch` rows are in the .qs files: the infobox date and the",
        "article's birth-year category agree. Everything below that needs a",
        "human — `conflict` most of all, since the two channels disagreeing",
        "usually means Wikipedia itself is wrong somewhere.",
        "",
    ]

    md.append(f"## batch ({verdicts.get('batch', 0)}) — in the .qs files")
    for item in sorted((i for i in evidence if i.verdict == "batch"), key=lambda i: i.value):
        precision = "day" if item.precision == 11 else "year"
        md.append(f"* {item.qid} [{item.title}]({permalink(args.lang, item.revid)}) — "
                  f"**{item.value}** ({precision})")

    for bucket, blurb in (
        ("conflict", "infobox and birth-year category disagree — check the article"),
        ("suspicious-precision", "Jan 1st, usually a placeholder; the year is likely fine"),
        ("duplicate-item", "several items share one article — likely merges"),
        ("ambiguous-source", "more than one candidate date in the article"),
        ("flagged-uncertain", "Wikipedia flags the birth year as unknown/uncertain"),
        ("no-cross-check", "no birth-year category to confirm the infobox"),
    ):
        rows = [i for i in evidence if i.verdict == bucket]
        md.append(f"\n## {bucket} ({len(rows)}) — {blurb}")
        for item in sorted(rows, key=lambda i: i.qid):
            extra = ""
            if item.shares_article_with:
                extra = f" · also {', '.join(item.shares_article_with)}"
            md.append(f"* {item.qid} [{item.title}]({permalink(args.lang, item.revid)}) — "
                      f"{item.reason}{extra}")

    nothing = [i for i in evidence if i.verdict == "nothing-found"]
    shapes = Counter(
        "infobox reads from Wikidata" if i.wikidata_driven
        else "no infobox" if not i.has_infobox
        else "infobox without a usable birth date"
        for i in nothing
    )
    md.append(f"\n## nothing-found ({len(nothing)}), by shape: {dict(shapes)}")

    (out / "plan.md").write_text("\n".join(md) + "\n")
    (out / "day.qs").write_text("\n".join(day_qs) + "\n")
    (out / "year.qs").write_text("\n".join(year_qs) + "\n")
    (out / "evidence.json").write_text(
        json.dumps(
            [
                vars(i)
                | {"verdict": i.verdict, "value": i.value, "precision": i.precision}
                for i in evidence
            ],
            indent=2,
        )
    )
    print(f"\nverdicts: {dict(verdicts)}")
    print(f"QS: {len(day_qs)} day-precision, {len(year_qs)} year-precision")
    print(f"Wrote {out}/plan.md, day.qs, year.qs, evidence.json")


if __name__ == "__main__":
    main()
