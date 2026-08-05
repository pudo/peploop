#!/usr/bin/env python
"""Size the missing-P569 harvest per country, to pick which one to run.

    python scripts/dob_country_sizing.py

Prints a markdown table: how many people per citizenship hold a position but
have no birth date, and how many of those have an English Wikipedia article
(the only ones an infobox harvest can reach). The second number is what
matters and it does not track the first — bulk-imported national registries
inflate the gap without adding articles.

Writes data/birthdates/sizing.md.
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wd.api import sparql
from wd.http import REPO_ROOT, get_text, make_session

WD_API = "https://www.wikidata.org/w/api.php"
BASE = REPO_ROOT / "data" / "birthdates"

COUNTRIES = {
    "India": "Q668",
    "United States": "Q30",
    "Nigeria": "Q1033",
    "Indonesia": "Q252",
    "Pakistan": "Q843",
    "United Kingdom": "Q145",
    "Malaysia": "Q833",
    "Philippines": "Q928",
    "Bangladesh": "Q902",
    "Brazil": "Q155",
    "France": "Q142",
    "Russia": "Q159",
    "Germany": "Q183",
    "Japan": "Q17",
    "Iran": "Q794",
    "Turkey": "Q43",
    "Poland": "Q36",
    "Ukraine": "Q212",
}

ADDRESSABLE = """
SELECT (COUNT(DISTINCT ?person) AS ?c) WHERE {
  ?person wdt:P31 wd:Q5 ; wdt:P39 ?position ; wdt:P27 wd:%(country)s .
  ?article schema:about ?person ; schema:isPartOf <https://en.wikipedia.org/> .
  FILTER NOT EXISTS { ?person p:P569 ?statement }
}
"""


def patient(session, query: str, tries: int = 6, wait: float = 30.0) -> list[dict]:
    """Run a query that WDQS may 502 on before it succeeds.

    The big countries sit right at the timeout — the US enumeration takes
    ~4 minutes and fails outright about half the time — so a single attempt
    silently drops exactly the rows that matter most.
    """
    for attempt in range(tries):
        try:
            return sparql(session, query, max_age=0)
        except Exception as exc:
            if attempt == tries - 1:
                raise
            print(f"  retrying after: {str(exc)[:60]}", file=sys.stderr)
            time.sleep(wait)
    return []


def gap_count(session, qid: str) -> int:
    """Total gap items for a country, via CirrusSearch (instant, unlike a
    COUNT over the same join on WDQS)."""
    raw = get_text(
        session,
        WD_API,
        params={
            "action": "query",
            "list": "search",
            "srsearch": (
                f"haswbstatement:P31=Q5 haswbstatement:P39 "
                f"-haswbstatement:P569 haswbstatement:P27={qid}"
            ),
            "srnamespace": "0",
            "srlimit": "1",
            "srinfo": "totalhits",
            "format": "json",
        },
    )
    return json.loads(raw)["query"]["searchinfo"]["totalhits"]


def main() -> None:
    session = make_session()
    rows = []
    for name, qid in COUNTRIES.items():
        gap = gap_count(session, qid)
        try:
            addressable = int(patient(session, ADDRESSABLE % {"country": qid})[0]["c"])
        except Exception as exc:
            print(f"{name}: addressable count failed ({exc})", file=sys.stderr)
            addressable = None
        rows.append((name, qid, gap, addressable))
        print(f"{name}: gap={gap} addressable={addressable}", file=sys.stderr)

    rows.sort(key=lambda r: -(r[3] or 0))
    md = [
        "# Missing P569 by country",
        "",
        "`gap` = P31=Q5 + P39 + no P569. `enwiki` = of those, how many have an",
        "English Wikipedia article. At the measured ~10% extraction rate, the",
        "last column is the rough harvest to expect.",
        "",
        "| country | QID | gap | enwiki | % | est. harvest |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for name, qid, gap, addressable in rows:
        if addressable is None:
            md.append(f"| {name} | {qid} | {gap:,} | ? | ? | ? |")
            continue
        pct = 100 * addressable / gap if gap else 0
        md.append(
            f"| {name} | {qid} | {gap:,} | {addressable:,} | {pct:.0f}% | "
            f"~{round(addressable * 0.10):,} |"
        )
    BASE.mkdir(parents=True, exist_ok=True)
    (BASE / "sizing.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
