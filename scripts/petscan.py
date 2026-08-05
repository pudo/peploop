#!/usr/bin/env python
"""List Wikipedia category members that have a Wikidata item.

    python scripts/petscan.py --lang lt "Lietuvos_prezidentai" --depth 1

Prints TSV (QID, title) to stdout.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wd.http import make_session
from wd.petscan import category_members


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("category", help="Category name (with or without underscores)")
    parser.add_argument("--lang", required=True, help="Wikipedia language code, e.g. lt")
    parser.add_argument("--depth", type=int, default=0, help="Subcategory depth (default 0)")
    parser.add_argument("--no-cache", action="store_true", help="Bypass the disk cache")
    args = parser.parse_args()

    session = make_session()
    kwargs = {"max_age": 0} if args.no_cache else {}
    members = category_members(
        session, args.category, args.lang, depth=args.depth, **kwargs
    )
    for qid, title in members:
        print(f"{qid}\t{title}")
    print(f"# {len(members)} members", file=sys.stderr)


if __name__ == "__main__":
    main()
