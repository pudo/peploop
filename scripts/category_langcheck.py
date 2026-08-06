#!/usr/bin/env python
"""Check that every wd_categories.yml category page actually exists.

    python scripts/category_langcheck.py

The crawler passes the spec's `language` straight through to PETScan, which
defaults to `en` when the key is absent — so a spec naming a category in the
local language without declaring the language queries en.wikipedia and
silently matches nobody. Same for plain typos and categories since renamed.
A dead spec is invisible in the crawl: no error, just zero members.

Asks each wiki whether the page exists (batched, 50 titles per call), and for
the misses reports whichever wiki does have it.

Output: data/categories/langcheck.md
"""

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import quote

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wd.http import REPO_ROOT, get_text, make_session

YML = Path(
    "/Users/pudo/Code/opensanctions/datasets/_wikidata/categories/wd_categories.yml"
)
OUT_DIR = REPO_ROOT / "data" / "categories"
# Wikis to try for a category that misses on its declared language.
PROBE_LANGS = (
    "en", "ru", "es", "cs", "pt", "pl", "it", "de", "fr", "hu", "sk", "lt",
    "lv", "et", "is", "el", "vi", "fi", "sv", "no", "nl", "uk", "be", "tr",
    "ar", "fa", "he", "zh", "ja", "ko", "hi", "id", "my",
)
BATCH = 50
# Percent-encoded Cyrillic/Greek titles are ~9 bytes per character, so a
# 50-title batch overflows the URI (HTTP 414) long before the API's limit.
URL_BUDGET = 3500


def batches(titles: List[str]) -> Iterable[List[str]]:
    chunk: List[str] = []
    size = 0
    for title in titles:
        cost = len(quote(title)) + 3
        if chunk and (len(chunk) >= BATCH or size + cost > URL_BUDGET):
            yield chunk
            chunk, size = [], 0
        chunk.append(title)
        size += cost
    if chunk:
        yield chunk


def exists(
    session, language: str, titles: Iterable[str]
) -> Dict[str, bool]:
    """Which of these page titles exist on {language}.wikipedia?"""
    todo = list(dict.fromkeys(titles))
    out: Dict[str, bool] = {}
    for chunk in batches(todo):
        raw = get_text(
            session,
            f"https://{language}.wikipedia.org/w/api.php",
            params={
                "action": "query", "format": "json", "formatversion": "2",
                "titles": "|".join(chunk),
            },
        )
        data = json.loads(raw).get("query", {})
        # The API normalizes "Category:" to the local namespace name, so map
        # results back to what we asked for.
        back = {n["to"]: n["from"] for n in data.get("normalized", [])}
        for page in data.get("pages", []):
            asked = back.get(page["title"], page["title"])
            out[asked] = "missing" not in page
        for title in chunk:
            out.setdefault(title, False)
    return out


def search_categories(session, language: str, name: str) -> List[str]:
    """Closest existing category titles — Wikipedia renames categories
    constantly ("White House Counsels" → "White House counsels"), so a dead
    spec usually needs a new title rather than a new language."""
    raw = get_text(
        session,
        f"https://{language}.wikipedia.org/w/api.php",
        params={
            "action": "query", "format": "json", "formatversion": "2",
            "list": "search", "srnamespace": "14", "srlimit": "3",
            "srsearch": name.replace("_", " ").strip(),
        },
    )
    hits = json.loads(raw).get("query", {}).get("search", [])
    return [h["title"].split(":", 1)[-1] for h in hits]


def specs_from_yml() -> List[dict]:
    data = yaml.safe_load(YML.read_text())

    def find(node, key):
        if isinstance(node, dict):
            if key in node:
                return node[key]
            for value in node.values():
                found = find(value, key)
                if found is not None:
                    return found
        return None

    return list(find(data, "categories"))


def main() -> None:
    specs = specs_from_yml()
    session = make_session()

    by_lang: Dict[str, List[dict]] = defaultdict(list)
    for spec in specs:
        by_lang[spec.get("language", "en")].append(spec)

    dead: List[Tuple[dict, str]] = []
    live = 0
    for language, group in sorted(by_lang.items()):
        titles = {
            "Category:" + s["category"].replace("_", " ").strip(): s for s in group
        }
        found = exists(session, language, titles)
        for title, spec in titles.items():
            if found.get(title):
                live += 1
            else:
                dead.append((spec, language))
        print(f"{language}: {sum(found.values())}/{len(titles)} exist",
              file=sys.stderr)

    # For each dead spec, find a wiki that does have the category.
    elsewhere: Dict[str, Optional[str]] = {}
    for language in PROBE_LANGS:
        pending = [
            s for s, _ in dead
            if elsewhere.get(s["category"]) is None
        ]
        if not pending:
            break
        titles = {
            "Category:" + s["category"].replace("_", " ").strip(): s["category"]
            for s in pending
        }
        found = exists(session, language, titles)
        for title, category in titles.items():
            if found.get(title):
                elsewhere[category] = language

    md = [
        "# wd_categories.yml — do the category pages exist?",
        "",
        f"{len(specs)} specs: **{live} live, {len(dead)} match nothing**.",
        "",
        "The crawler hands `language` to PETScan, which defaults to `en`. A",
        "spec whose category does not exist on the wiki being queried returns",
        "zero rows and logs no error, so it contributes nothing — including",
        "its `position:` block.",
        "",
        "| category | queried | exists on | likely fix |",
        "|---|---|---|---|",
    ]
    suggestions: Dict[str, List[str]] = {}
    for spec, language in sorted(dead, key=lambda d: (d[1], d[0]["category"])):
        other = elsewhere.get(spec["category"])
        if other and other != language:
            fix = f"`language: {other}`"
        else:
            near = search_categories(session, other or language, spec["category"])
            suggestions[spec["category"]] = near
            fix = ("renamed? nearest: "
                   + ", ".join(f"`{n}`" for n in near) if near
                   else "**no similar category found** — deleted?")
        has_pos = " *(has `position:`)*" if "position" in spec else ""
        md.append(
            f"| `{spec['category']}`{has_pos} | {language}wiki | "
            f"{other + 'wiki' if other else '(none)'} | {fix} |")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "langcheck.md").write_text("\n".join(md) + "\n")
    (OUT_DIR / "langcheck.json").write_text(json.dumps(
        [
            {
                "category": s["category"],
                "queried": lang,
                "exists_on": elsewhere.get(s["category"]),
                "has_position": "position" in s,
            }
            for s, lang in dead
        ],
        indent=1, ensure_ascii=False))
    print(f"{live} live, {len(dead)} dead → {OUT_DIR / 'langcheck.md'}")


if __name__ == "__main__":
    main()
