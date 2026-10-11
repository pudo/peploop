#!/usr/bin/env python
"""Fetch the Wikipedia article (raw wikitext) for Wikidata items.

    python scripts/fetch_article.py Q47891929 --lang lt
    python scripts/fetch_article.py --from-report data/positions/Q55607326.json --lang lt

Articles land in data/articles/<qid>.<lang>.wiki; the path is printed per
item. With a single QID and --stdout, prints the wikitext instead.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wd.api import fetch_entities
from wd.http import REPO_ROOT, make_session
from wd.wikipedia import fetch_wikitext, sitelink_title

ARTICLE_DIR = REPO_ROOT / "data" / "articles"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("qids", nargs="*", help="Wikidata QIDs")
    parser.add_argument("--from-report", type=Path, default=None,
                        help="Read candidate QIDs from a markdown gap report")
    parser.add_argument("--lang", required=True, help="Wikipedia language code")
    parser.add_argument("--stdout", action="store_true",
                        help="Print wikitext to stdout (single QID only)")
    args = parser.parse_args()

    qids = list(args.qids)
    if args.from_report is not None:
        report = json.loads(args.from_report.read_text())
        qids.extend(c["qid"] for c in report["candidates"])
    if not qids:
        parser.error("No QIDs given")

    session = make_session()
    entities = fetch_entities(session, qids, props="sitelinks/urls")
    ARTICLE_DIR.mkdir(parents=True, exist_ok=True)
    for qid in qids:
        entity = entities.get(qid)
        title = sitelink_title(entity, args.lang) if entity else None
        if title is None:
            print(f"{qid}\tNO_ARTICLE", file=sys.stderr)
            continue
        text = fetch_wikitext(session, args.lang, title)
        if text is None:
            print(f"{qid}\tMISSING_PAGE\t{title}", file=sys.stderr)
            continue
        if args.stdout and len(qids) == 1:
            print(text)
            return
        path = ARTICLE_DIR / f"{qid}.{args.lang}.wiki"
        path.write_text(text)
        print(f"{qid}\t{title}\t{path}")


if __name__ == "__main__":
    main()
