"""PETScan client: enumerate Wikipedia category members that have a Wikidata
item, the same query the OS `wd_categories` crawler runs (petscan.wmcloud.org).
"""

import json
from typing import Dict, List, Optional, Tuple

from requests import Session

from wd.http import get_text

PETSCAN_URL = "https://petscan.wmcloud.org/"


def category_members(
    session: Session,
    category: str,
    language: str,
    depth: int = 0,
    project: str = "wikipedia",
    max_age: Optional[int] = None,
) -> List[Tuple[str, str]]:
    """Return (QID, page title) for members of a category (and subcategories,
    to `depth`) that are linked to a Wikidata human (P31=Q5 item present).

    Keep depth low (0-1) for edit-candidate generation: subcategory drift is
    the main source of false members. The OS crawler uses depth 4 for recall.
    """
    params: Dict[str, str] = {
        "language": language,
        "project": project,
        "categories": category.replace("_", " ").strip(),
        "depth": str(depth),
        "format": "json",
        "doit": "",
        "wikidata_item": "with",
        "wikidata_prop_item_use": "Q5",
        "sortorder": "ascending",
    }
    kwargs = {} if max_age is None else {"max_age": max_age}
    raw = get_text(session, PETSCAN_URL, params=params, **kwargs)
    data = json.loads(raw)
    members: List[Tuple[str, str]] = []
    for row in data["*"][0]["a"]["*"]:
        qid = row.get("metadata", {}).get("wikidata")
        if qid:
            members.append((qid, row["title"]))
    return members
