"""Find the person a seat names when the body's article does not link them.

Most board members a body's article names are plain text or red links, yet
many of them have an item and a Wikipedia page of their own. A name alone
proves nothing (homonyms are common, and many human items are bare author
records), so a name match only proposes candidates: a candidate is accepted
when their own Wikipedia page places them at the body, or in its field, as
the narrow check (`match.py`) judges. This module is the deterministic half:
how names are compared, where candidates come from, and what is gathered
about each one.
"""

import re
import unicodedata
from typing import Any

import normality
from rigour.text import levenshtein

from peploop import http
from peploop.corp import rules, wd

WD_API = "https://www.wikidata.org/w/api.php"
#: Hits read per search; a common name past this many is a crowd of homonyms anyway.
SEARCH_LIMIT = 20
#: Candidates a seat may have before it is left alone as a crowd of namesakes.
MAX_CANDIDATES = 8
#: Characters of a person's page shown to the check: the lead and the career, rarely more.
PAGE_CHARS = 8000
#: Name particles that are part of a surname in some languages and dropped in others.
PARTICLES = frozenset({"von", "van", "der", "de", "den", "del", "della", "di", "da", "du", "la", "le", "zu", "y", "e"})


def fold(name: str) -> list[str]:
    """A person's name as comparable tokens: titles and degrees dropped, Latin script, no accents, no case."""
    text = rules.norm(name)
    text = unicodedata.normalize("NFKC", normality.ascii_text(text) or "").lower()
    return [t for t in re.split(r"[\s\-'.]+", text) if t]


def token_fits(a: str, b: str) -> bool:
    """Two name tokens that write the same name: equal, an initial of the other, or one letter apart in a long one."""
    if a == b:
        return True
    if len(a) == 1 or len(b) == 1:
        return a[0] == b[0]
    shorter = min(len(a), len(b))
    if shorter >= 5 and a[0] == b[0]:
        # Transliteration and stray inflection: "Mitsotakis" / "Metsotakes".
        return levenshtein(a, b) <= (2 if shorter >= 8 else 1)
    return False


def name_fits(seat: str, label: str) -> bool:
    """Whether a label can name the person a seat names.

    Order does not count (family name first in some languages); a middle
    name, a second surname or a particle one side leaves out does, as long
    as at least a given name and a family name agree. A lone surname never
    fits: it names a family, not a person.
    """
    a = [t for t in fold(seat) if t not in PARTICLES]
    b = [t for t in fold(label) if t not in PARTICLES]
    if len(a) < 2 or len(b) < 2:
        return False
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    pool = list(long_)
    full = 0
    for t in short:
        hit = next((p for p in pool if token_fits(t, p)), None)
        if hit is None:
            return False
        pool.remove(hit)
        full += len(t) > 1 and len(hit) > 1
    # Two whole tokens must agree: initials alone ("J. K. Smith") are too weak.
    return full >= 2


def names_of(entity: dict[str, Any]) -> list[str]:
    """Every label, alias and page title of an item: the names it may go by."""
    names = [v["value"] for v in entity.get("labels", {}).values()]
    names += [a["value"] for al in entity.get("aliases", {}).values() for a in al]
    names += [s["title"] for k, s in entity.get("sitelinks", {}).items() if k.endswith("wiki")]
    return list(dict.fromkeys(names))


def search_terms(name: str) -> str:
    """The name as a search query: no titles, degrees or disambiguators."""
    return " ".join(t for t in rules.norm(name).split() if not t.isdigit())


def search_items(name: str) -> list[str]:
    """Human items whose label or alias matches the name, in any language (the search folds accents)."""
    data = http.get_json(WD_API, params={"action": "query", "list": "search", "format": "json",
                                         "srsearch": f"{search_terms(name)} haswbstatement:P31=Q5",
                                         "srlimit": SEARCH_LIMIT, "srprop": ""})
    return [h["title"] for h in data.get("query", {}).get("search", [])]


def search_pages(name: str, lang: str) -> list[str]:
    """Items of the pages in this Wikipedia whose title is the name (redirects and order variants included)."""
    data = http.get_json(f"https://{lang}.wikipedia.org/w/api.php", params={
        "action": "query", "format": "json", "generator": "search", "gsrsearch": search_terms(name),
        "gsrlimit": 10, "gsrnamespace": 0, "gsrwhat": "text", "prop": "pageprops", "ppprop": "wikibase_item",
        "redirects": 1})
    pages = data.get("query", {}).get("pages", {}).values()
    return [p["pageprops"]["wikibase_item"] for p in pages
            if p.get("pageprops", {}).get("wikibase_item") and name_fits(name, p.get("title", ""))]


def candidates(name: str, langs: list[str], body: str) -> list[dict[str, Any]]:
    """The human items a seat's name may mean, each with a page in one of these languages.

    Found by Wikidata's search over labels and aliases and by each
    Wikipedia's own search over page titles, kept when a name of theirs fits
    the seat's and they have a page the check can read. The body itself and
    anything not typed human fall away.
    """
    found = dict.fromkeys(search_items(name))
    for lang in langs:
        found.update(dict.fromkeys(search_pages(name, lang)))
    found.pop(body, None)
    if not found:
        return []
    entities = wd.fetch_items(list(found), props="labels|aliases|descriptions|claims|sitelinks")
    out = []
    for qid in found:
        e = entities.get(qid)
        if not e or "Q5" not in wd.values(e, "P31"):
            continue
        if not any(name_fits(name, n) for n in names_of(e)):
            continue
        pages = [lang for lang in langs if f"{lang}wiki" in e.get("sitelinks", {})]
        out.append({"qid": e.get("id", qid), "entity": e, "pages": pages})
    return out


def page_text(lang: str, title: str) -> str:
    """A page's plain text (sections included), kept a week in the HTTP cache."""
    data = http.get_json(f"https://{lang}.wikipedia.org/w/api.php", params={
        "action": "query", "format": "json", "prop": "extracts", "explaintext": 1, "redirects": 1,
        "titles": title})
    for page in data.get("query", {}).get("pages", {}).values():
        return page.get("extract") or ""
    return ""


def page_links(lang: str, title: str) -> set[str]:
    """The items a page links to (article namespace)."""
    out: set[str] = set()
    params: dict[str, Any] = {"action": "query", "format": "json", "generator": "links", "titles": title,
                              "gplnamespace": 0, "gpllimit": "max", "prop": "pageprops",
                              "ppprop": "wikibase_item", "redirects": 1}
    for _ in range(5):
        data = http.get_json(f"https://{lang}.wikipedia.org/w/api.php", params=params)
        out |= {p["pageprops"]["wikibase_item"] for p in data.get("query", {}).get("pages", {}).values()
                if p.get("pageprops", {}).get("wikibase_item")}
        if "continue" not in data:
            break
        params = {**params, **data["continue"]}
    return out
