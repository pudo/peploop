"""Seed people from a Wikipedia category and read their articles as text.

Articles come from the REST API as Parsoid HTML, which keeps the infobox and
the section structure in stable markup, and are reduced here to the plain
text the model reads.
"""

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, NamedTuple
from urllib.parse import quote, unquote

import yaml
from lxml import html as lxml_html

from peploop import db, http

PETSCAN_URL = "https://petscan.wmcloud.org/"
REST_HTML = "https://{lang}.wikipedia.org/api/rest_v1/page/html/{title}"
PAGE_URL = "https://{lang}.wikipedia.org/wiki/{title}"
SPARQL_URL = "https://query.wikidata.org/sparql"
# Every Wikipedia language edition with its code, for the `P143` of a reference.
EDITIONS_QUERY = "SELECT ?wiki ?code WHERE { ?wiki wdt:P31 wd:Q10876391; wdt:P424 ?code. }"

# Class fragments whose elements carry no biography: navigation, references,
# succession boxes, hatnotes. They differ per wiki (de has "navileiste" and
# "klappleiste" where en has "navbox"), so match on a fragment of the class.
DROP_CLASSES = (
    "navbox",
    "navileiste",
    "klappleiste",
    "navigation-not-searchable",
    "hatnote",
    "reflist",
    "mw-references",
    "references-small",
    "succession-box",
    "authority-control",
    "mw-editsection",
    "metadata",
    "noprint",
    "sistersite",
    "sisterproject",
    "ambox",
    "navigatie",
)
DROP_TAGS = ("style", "script", "link", "meta", "figure", "audio", "video")
BLOCK_TAGS = ("p", "li", "dd", "dt", "blockquote", "pre")
HEADINGS = ("h1", "h2", "h3", "h4", "h5", "h6")
# Whitespace that a cell's join put where no writer would: in front of closing
# punctuation, or just inside an opening bracket.
PUNCT_SPACE_RE = re.compile(r"\s+(?=[,.;:)])|(?<=\()\s+")


class SeedEntry(NamedTuple):
    """One line of a seed file: a category tree to ask PetScan for."""

    category: str
    lang: str
    depth: int


def load_seeds(path: Path) -> list[SeedEntry]:
    """Read a seed file as a list of category trees, in file order.

    The file is a YAML list of entries with `category`, `lang` and an
    optional `depth`. Many narrow categories at shallow depth are preferred
    to one wide category at depth 3, so `depth` defaults to 1.
    """
    entries = yaml.safe_load(path.read_text())
    if not isinstance(entries, list):
        raise TypeError(f"{path}: expected a list of seed entries")
    seeds: list[SeedEntry] = []
    for entry in entries:
        category = str(entry["category"]).strip()
        seeds.append(SeedEntry(category, str(entry["lang"]), int(entry.get("depth", 1))))
    return seeds


def seed_category(
    category: str, lang: str, depth: int = 1, project: str = "wikipedia"
) -> list[tuple[str, str]]:
    """Return (page title, QID) for the members of a category tree.

    PetScan's `wikidata_prop_item_use=Q5` filter passes `Category:` items
    through, so membership here is a candidate set: the caller enforces
    `P31 = Q5` against the item itself.
    """
    params = {
        "language": lang,
        "project": project,
        "categories": category.replace("_", " ").strip(),
        "depth": str(depth),
        "format": "json",
        "doit": "",
        "wikidata_item": "with",
        "wikidata_prop_item_use": "Q5",
        "sortorder": "ascending",
    }
    raw = http.get_text(PETSCAN_URL, params=params)
    # A PetScan failure arrives as HTTP 200, either as an HTML page or as
    # valid JSON holding an `error` key; both would otherwise be cached for a
    # week as if they were the category.
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        db.cache_drop(PETSCAN_URL, params)
        raise RuntimeError(f"PetScan returned non-JSON: {raw[:120]!r}") from exc
    if "error" in data or "*" not in data:
        db.cache_drop(PETSCAN_URL, params)
        raise RuntimeError(f"PetScan failed: {raw[:200]!r}")
    members: list[tuple[str, str]] = []
    for row in data["*"][0]["a"]["*"]:
        qid = row.get("metadata", {}).get("wikidata")
        # Namespace 0 only: PetScan's Q5 filter also passes `Category:` items.
        if qid and row.get("namespace") == 0:
            members.append((row["title"], qid))
    return members


def fetch_article(lang: str, title: str) -> dict[str, Any]:
    """Fetch one article as Parsoid HTML, with the revision it was rendered at.

    The revision is in the ETag (`W/"<rev>/<uuid>/view/html"`); the root
    element's `about` URI repeats it and is the fallback when a proxy has
    dropped the header.
    """
    path = quote(title.replace(" ", "_"), safe="")
    res = http.get(REST_HTML.format(lang=lang, title=path))
    return {
        "lang": lang,
        "title": title,
        "url": PAGE_URL.format(lang=lang, title=path),
        "rev_id": _revision(res.headers.get("etag"), res.text),
        "html": res.text,
        "redirect": _landed_elsewhere(title, res.text),
    }


def page_item(lang: str, title: str) -> str | None:
    """The Wikidata item a page is linked to, or None when it has none."""
    raw = http.get_text(
        f"https://{lang}.wikipedia.org/w/api.php",
        params={"action": "query", "prop": "pageprops", "ppprop": "wikibase_item",
                "titles": title, "redirects": "1", "format": "json"},
    )
    for page in json.loads(raw).get("query", {}).get("pages", {}).values():
        return page.get("pageprops", {}).get("wikibase_item")
    return None


def _landed_elsewhere(title: str, body: str) -> str | None:
    """The page the response is a version of, when it is not the one asked for.

    The REST endpoint follows a redirect whatever it is asked, so a sitelink
    that has become one comes back as some other page. Most such pages are the
    same person under a moved title; the one that matters was a politician's
    title redirected to his wife's biography, stored and read as his. The body
    names the page it belongs to (`dc:isVersionOf`); the caller asks whose item
    that page is.
    """
    root = lxml_html.fromstring(body)
    for link in root.iter("link"):
        if link.get("rel") == "dc:isVersionOf":
            landed = unquote((link.get("href") or "").rsplit("/wiki/", 1)[-1]).replace("_", " ")
            if landed.casefold() != title.replace("_", " ").casefold():
                return landed
    return None


def _revision(etag: str | None, body: str) -> int | None:
    match = re.search(r'"(\d+)/', etag or "")
    if match:
        return int(match.group(1))
    # The root element's `about` names the revision too, but through a
    # localized special page ("Speciální:Přesměrování" on cs), so only the
    # trailing path segment can be matched on.
    about = lxml_html.fromstring(body).get("about") or ""
    match = re.search(r"/revision/(\d+)", about)
    return int(match.group(1)) if match else None


def _drop(element: Any) -> bool:
    if element.tag in DROP_TAGS:
        return True
    classes = (element.get("class") or "").lower()
    if element.tag == "sup" and ("reference" in classes or "mw-ref" in classes):
        return True
    return any(fragment in classes for fragment in DROP_CLASSES)


def _clean(root: Any) -> None:
    """Remove navigation, references and styling from the parsed article.

    `drop_tree` rather than `remove`: the tail text after an element belongs
    to its parent's prose and a plain remove takes it along.
    """
    for element in list(root.iter()):
        if isinstance(element.tag, str) and _drop(element):
            parent = element.getparent()
            if parent is not None:
                element.drop_tree()


def _text(element: Any) -> str:
    return " ".join(element.text_content().split())


def _cell_text(element: Any) -> str:
    """Join an infobox cell's text nodes with spaces.

    Infobox cells stack their parts in nested spans and divs with no
    whitespace between them, so plain text extraction yields "In office28
    November 2021" and loses the date to the label. The join is what puts a
    space in front of the punctuation that ends a span of its own, which is
    how "Ph.D. , MBA" and "Kolín , Protektorát" come about.
    """
    text = " ".join(" ".join(element.itertext()).split())
    return PUNCT_SPACE_RE.sub("", text)


def _infobox(table: Any, out: list[str]) -> None:
    for row in table.iter("tr"):
        cells = [c for c in row if c.tag in ("th", "td")]
        parts = [_cell_text(c) for c in cells]
        parts = [p for p in parts if p]
        if len(parts) >= 2:
            out.append(f"{parts[0]}: {' '.join(parts[1:])}")
        elif len(parts) == 1 and len(cells) == 1:
            out.append(parts[0])


def _walk(element: Any, out: list[str]) -> None:
    for child in element:
        if not isinstance(child.tag, str):
            continue
        classes = (child.get("class") or "").lower()
        if child.tag == "table":
            if "infobox" in classes:
                out.append("")
                _infobox(child, out)
                out.append("")
            continue
        if child.tag in HEADINGS:
            out.extend(["", f"## {_text(child)}", ""])
            continue
        if child.tag in BLOCK_TAGS:
            text = _text(child)
            if text:
                out.append(text)
            continue
        _walk(child, out)


def html_to_text(html: str) -> str:
    """Reduce Parsoid article HTML to headings, paragraphs and infobox lines."""
    root = lxml_html.fromstring(html)
    _clean(root)
    body = root.find("body")
    out: list[str] = []
    _walk(body if body is not None else root, out)
    lines: list[str] = []
    for line in out:
        if line or (lines and lines[-1]):
            lines.append(line)
    return "\n".join(lines).strip()


def revision_url(url: str, rev: int | None) -> str:
    """Turn an article URL into the permanent URL of the revision that was read.

    `P4656` wants a link that still shows what was cited after the page has
    moved on; `/wiki/<title>` shows whatever is current. The title is already
    percent-encoded in the stored URL, so it transfers as it stands.
    """
    head, marker, title = url.partition("/wiki/")
    if not marker or rev is None:
        return url
    return f"{head}/w/index.php?title={title}&oldid={rev}"


@lru_cache(maxsize=1)
def edition_items() -> dict[str, str]:
    """Map a language code to the Wikidata item of its Wikipedia, via SPARQL.

    The set barely changes, so the seven-day HTTP cache is the right tolerance:
    this is a fact about Wikipedia, not the item state a write invalidates.
    """
    data = http.get_json(SPARQL_URL, params={"query": EDITIONS_QUERY, "format": "json"})
    return {
        row["code"]["value"]: row["wiki"]["value"].rsplit("/", 1)[-1]
        for row in data["results"]["bindings"]
    }


def edition_qid(lang: str) -> str | None:
    """Return the item of one language's Wikipedia, or None if it has none."""
    return edition_items().get(lang)
