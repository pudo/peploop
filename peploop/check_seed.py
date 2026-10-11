"""Pin what seeding falls back to when PetScan is down, offline.

PetScan is a single volunteer-run service, and when it hangs every seed file
stalls on it: four country runs once sat for over half an hour on its first
entry. The fallback walks the category tree through the wiki's own API. What
this file guards is that the walk answers the question PetScan answered --
`depth` counted the same way, a category reached twice read once, a page
without an item left out -- and that one outage is paid for once per process,
not once per entry.

No network, no key, no database: `http.get_json` is replaced by a hand-built
category tree. Run it as `python -m peploop.check_seed` from the repository
root.
"""

import sys
from typing import Any

from peploop import http, wikipedia

# A tree with a shared grandchild and a page that has no item.
TREE: dict[str, list[dict[str, Any]]] = {
    "Category:Root": [
        {"ns": 0, "title": "Alice", "pageprops": {"wikibase_item": "Q1"}},
        {"ns": 0, "title": "No item"},
        {"ns": 14, "title": "Category:Child A"},
        {"ns": 14, "title": "Category:Child B"},
    ],
    "Category:Child_A": [
        {"ns": 0, "title": "Bob", "pageprops": {"wikibase_item": "Q2"}},
        {"ns": 14, "title": "Category:Shared"},
    ],
    "Category:Child_B": [
        {"ns": 0, "title": "Alice", "pageprops": {"wikibase_item": "Q1"}},
        {"ns": 14, "title": "Category:Shared"},
    ],
    "Category:Shared": [
        {"ns": 0, "title": "Carol", "pageprops": {"wikibase_item": "Q3"}},
    ],
}
READS: list[str] = []


def fake_get_json(url: str, params: dict[str, Any] | None = None, **_kw: Any) -> Any:
    title = (params or {})["gcmtitle"]
    READS.append(title)
    pages = TREE.get(title, [])
    return {"query": {"pages": {str(i): p for i, p in enumerate(pages)}}}


PETSCAN_CALLS: list[str] = []


def failing_petscan(category: str, *_a: Any) -> list[tuple[str, str]]:
    PETSCAN_CALLS.append(category)
    raise TimeoutError("read timed out")


def main() -> int:
    http.get_json = fake_get_json  # type: ignore[assignment]
    wikipedia._petscan = failing_petscan  # type: ignore[assignment]
    failures = 0

    def check(name: str, ok: bool) -> None:
        nonlocal failures
        print(f"  {'ok  ' if ok else 'FAIL'} {name}")
        failures += not ok

    check("depth 0 is the category's own pages, and a page with no item is left out",
          wikipedia.walk_category("Root", "xx", 0) == [("Alice", "Q1")])
    check("depth 1 adds one generation of subcategories",
          [q for _, q in wikipedia.walk_category("Root", "xx", 1)] == ["Q1", "Q2"])
    READS.clear()
    got = wikipedia.walk_category("Root", "xx", 2)
    check("depth 2 reaches the grandchild, and lists each person once",
          [q for _, q in got] == ["Q1", "Q2", "Q3"])
    check("a category reached through two parents is read once",
          READS.count("Category:Shared") == 1)

    got = wikipedia.seed_category("Root", "xx", 1)
    check("a PetScan failure falls back to the walk", [q for _, q in got] == ["Q1", "Q2"])
    wikipedia.seed_category("Root", "xx", 0)
    check("and PetScan is not asked again in the same process", PETSCAN_CALLS == ["Root"])

    # Wikimedia limits an IP across all its wikis, so a fetch reading several
    # languages paces them together, while the query service keeps its own.
    wiki = {http._pacer(f"https://{h}/w/api.php") for h in
            ("fr.wikipedia.org", "en.wikipedia.org", "www.wikidata.org")}
    check("every wiki and Wikidata's API draw from one pacer", len(wiki) == 1)
    check("the query service does not",
          http._pacer("https://query.wikidata.org/sparql") not in wiki)

    print(f"{failures} failures")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
