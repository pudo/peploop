"""Fetch Wikipedia article source for LLM reading.

We fetch raw wikitext rather than a plaintext extract: infoboxes and
succession templates carry exactly the officeholder dates the extracts strip
out, and an LLM reads wikitext fine.
"""

import json
from typing import Any, Dict, Iterable, Optional

from requests import Session

from wd.http import get_text

WIKI_API = "https://{lang}.wikipedia.org/w/api.php"

# The action API takes up to 50 titles per query for anonymous clients.
TITLE_CHUNK = 50


def sitelink_title(entity: Dict[str, Any], lang: str) -> Optional[str]:
    """The entity's article title on `lang`.wikipedia, if it has one."""
    link = entity.get("sitelinks", {}).get(f"{lang}wiki")
    return link["title"] if link else None


def fetch_wikitext(
    session: Session, lang: str, title: str, max_age: Optional[int] = None
) -> Optional[str]:
    """Raw wikitext of an article, following redirects. None if missing."""
    params = {
        "action": "query",
        "prop": "revisions",
        "rvprop": "content",
        "rvslots": "main",
        "redirects": "1",
        "formatversion": "2",
        "format": "json",
        "titles": title,
    }
    kwargs = {} if max_age is None else {"max_age": max_age}
    raw = get_text(session, WIKI_API.format(lang=lang), params=params, **kwargs)
    data = json.loads(raw)
    for page in data.get("query", {}).get("pages", []):
        if "missing" in page:
            return None
        revisions = page.get("revisions", [])
        if revisions:
            return revisions[0]["slots"]["main"]["content"]
    return None


def _resolve(data: Dict[str, Any]) -> Dict[str, str]:
    """Map the titles we asked for onto the titles the API answered under."""
    query = data.get("query", {})
    alias: Dict[str, str] = {}
    for key in ("normalized", "redirects"):
        for entry in query.get(key, []):
            alias[entry["from"]] = entry["to"]
    return alias


def _chase(alias: Dict[str, str], title: str) -> str:
    """Follow a normalise/redirect chain, guarding against redirect loops."""
    seen = {title}
    while title in alias and alias[title] not in seen:
        title = alias[title]
        seen.add(title)
    return title


def fetch_pages(
    session: Session,
    lang: str,
    titles: Iterable[str],
    max_age: Optional[int] = None,
) -> Dict[str, Dict[str, Any]]:
    """Wikitext, revision id and categories for many titles, 50 per request.

    Batching matters when triaging thousands of articles: the per-page render
    endpoint costs one request each, so use this to decide which pages are
    worth rendering and only then fetch those individually. Results are keyed
    by the title as passed in, with redirects already followed.
    """
    out: Dict[str, Dict[str, Any]] = {}
    todo = list(dict.fromkeys(titles))
    kwargs = {} if max_age is None else {"max_age": max_age}
    for i in range(0, len(todo), TITLE_CHUNK):
        chunk = todo[i : i + TITLE_CHUNK]
        params = {
            "action": "query",
            "prop": "revisions|categories",
            "rvprop": "content|ids",
            "rvslots": "main",
            "cllimit": "max",
            "clshow": "!hidden",
            "redirects": "1",
            "formatversion": "2",
            "format": "json",
            "titles": "|".join(chunk),
        }
        raw = get_text(session, WIKI_API.format(lang=lang), params=params, **kwargs)
        data = json.loads(raw)
        pages: Dict[str, Dict[str, Any]] = {}
        for page in data.get("query", {}).get("pages", []):
            if "missing" in page or "invalid" in page:
                continue
            revisions = page.get("revisions", [])
            if not revisions:
                continue
            pages[page["title"]] = {
                "title": page["title"],
                "wikitext": revisions[0]["slots"]["main"]["content"],
                "revid": revisions[0]["revid"],
                "categories": [
                    cat["title"].split(":", 1)[-1] for cat in page.get("categories", [])
                ],
            }
        alias = _resolve(data)
        for title in chunk:
            page = pages.get(_chase(alias, title))
            if page is not None:
                out[title] = page
    return out


def fetch_lead_html(
    session: Session, lang: str, title: str, max_age: Optional[int] = None
) -> Optional[str]:
    """Rendered HTML of section 0 — the infobox and lead paragraph.

    Rendering is how you avoid parsing every `{{birth date}}` spelling by hand:
    the templates emit a normalised ISO date in their microformat markup, so
    argument order, `df=` flags and capitalisation stop mattering.
    """
    params = {
        "action": "parse",
        "page": title,
        "prop": "text",
        "section": "0",
        "redirects": "1",
        "formatversion": "2",
        "format": "json",
    }
    kwargs = {} if max_age is None else {"max_age": max_age}
    raw = get_text(session, WIKI_API.format(lang=lang), params=params, **kwargs)
    data = json.loads(raw)
    if "error" in data:
        return None
    return data.get("parse", {}).get("text")


def permalink(lang: str, revid: int) -> str:
    """Stable revision URL, for citing exactly what a value was read from."""
    return f"https://{lang}.wikipedia.org/w/index.php?oldid={revid}"
