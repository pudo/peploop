"""Fail when an AMLR file is malformed, or when the unit rule admits the wrong item.

Every lane reads these files, so a bad class or a lost sheet row misleads
all three at once. The unit rule runs on fabricated items: no network, no
database. Run it as `python -m peploop.check_amlr` from the repository root.
"""

import re
import sys
from typing import Any

import yaml

from peploop import amlr, eras, memo, wikidata
from peploop.checks import ent, expect

QID = re.compile(r"^Q[1-9]\d*$")
#: The member states and the Union: one file each.
CODES = {"at", "be", "bg", "cy", "cz", "de", "dk", "ee", "es", "eu", "fi", "fr", "gr", "hr", "hu", "ie",
         "it", "lt", "lu", "lv", "mt", "nl", "pl", "pt", "ro", "se", "si", "sk"}
#: The curated sheet's data rows: its header is row 1, so they run 2..SHEET_ROWS + 1.
SHEET_ROWS = 2759


def expansion_ok(entry: Any) -> bool:
    if not isinstance(entry, dict):
        return False
    if set(entry) == {"position"} or set(entry) == {"body"}:
        return bool(QID.match(str(next(iter(entry.values())))))
    return set(entry) == {"level", "office"} and entry["level"] in amlr.LEVELS and bool(entry["office"])


def check_files() -> None:
    codes = set(amlr.codes())
    expect(codes == CODES, f"one file for each member state and the Union ({len(codes)})")
    raw = {cc: yaml.safe_load((amlr.DIR / f"{cc}.yml").read_text()) or {} for cc in codes}
    expect(all(set(d) <= {"threshold", "units", "functions"} for d in raw.values()), "every file has only known keys")
    expect(all(set(d.get("units") or {}) <= {*amlr.LEVELS, "exclude"} for d in raw.values()),
           "every units block names only known levels")
    expect(not raw["eu"].get("units"), "the Union has no units")
    specs = [amlr.get(cc) for cc in sorted(codes)]
    expect(all(QID.match(q) for s in specs for q in [*s.classes, *s.exclude]),
           "unit classes and exclusions are QIDs")
    fns = [f for s in specs for f in s.functions]
    expect(all(f.amlr in amlr.CATEGORIES and f.kind in amlr.KINDS for f in fns), "every row's category and kind are known")
    expect(all(isinstance(f.row, int) and isinstance(f.position, str) and isinstance(f.checked, bool) for f in fns),
           "every row has a number, a position text and a checked flag")
    expect(all(isinstance(f.expansion, list) and all(expansion_ok(e) for e in f.expansion) for f in fns),
           "every expansion is a position, a body or a level's office")
    rows = [f.row for f in fns]
    expect(len(rows) == len(set(rows)), "no sheet row is in two places")
    expect(sorted(rows) == list(range(2, SHEET_ROWS + 2)), f"the rows cover the sheet ({len(rows)})")


def pop(amount: int, when: str | None = None, rank: str = "normal") -> dict:
    claim: dict[str, Any] = {"rank": rank, "mainsnak": {"datavalue": {"value": {"amount": f"+{amount}"}}}}
    if when:
        claim["qualifiers"] = {"P585": [{"datavalue": {"value": {"time": f"+{when}-01-01T00:00:00Z"}}}]}
    return claim


def unit(types: list[str], *pops: dict, country: str = "Q1", **claims: Any) -> dict:
    e = ent({"en": "unit"}, P31=types, P17=[country])
    e["claims"]["P1082"] = list(pops)
    e["claims"].update(claims)
    return e


def check_units() -> None:
    dissolved = [{"rank": "normal", "mainsnak": {"datavalue": {"value": {"time": "+2015-01-01T00:00:00Z"}}}}]
    world = {
        "Q10": unit(["Q100", "Q515"], pop(60_000, "2020")),
        "Q11": unit(["Q101"], pop(70_000, "2021")),
        "Q12": unit(["Q100"], pop(60_000), P576=dissolved),
        "Q13": unit(["Q100", amlr.FORMER], pop(60_000)),
        "Q14": unit(["Q100"], pop(60_000), country="Q2"),
        "Q15": unit(["Q100"], pop(40_000)),
        "Q16": unit(["Q100"], pop(55_000, "2011"), pop(48_000, "2021")),
        "Q17": unit(["Q100"], pop(45_000, "2023"), pop(52_000, "2011", rank="preferred")),
        "Q18": unit(["Q102", "Q103"], pop(900_000)),
        "Q19": unit(["Q100"], pop(80_000)),
        "Q20": unit(["Q999"], pop(90_000)),
    }
    spec = amlr.Spec(cc="xx", classes={"Q100": "municipal", "Q101": "grouping", "Q102": "grouping",
                                       "Q103": "metro"}, exclude=frozenset({"Q19"}))
    saved = (amlr.get, amlr.candidates, wikidata.fetch_items, eras.current_qids, memo.cached)
    try:
        amlr.get = lambda _cc: spec  # type: ignore[assignment]
        amlr.candidates = lambda _cl, _co, _t: sorted(world)  # type: ignore[assignment]
        wikidata.fetch_items = lambda qids, props="": {q: world[q] for q in qids if q in world}
        eras.current_qids = lambda _cc, extra=(): ["Q1"]  # type: ignore[assignment]
        memo.cached = lambda _key, fn, max_age=0: fn()  # type: ignore[assignment]
        got = amlr.units("xx")
        expect(got.get("Q10") == ("municipal", 60_000), "a unit typed with a level's class, populous enough")
        expect(got.get("Q11") == ("grouping", 70_000), "a grouping class gives a grouping")
        expect("Q12" not in got and "Q13" not in got, "a dissolved or former unit is history")
        expect("Q14" not in got, "a unit of another country is not this one's")
        expect("Q15" not in got, "a unit below the threshold is out")
        expect("Q16" not in got, "the latest population decides, not the largest")
        expect(got.get("Q17") == ("municipal", 52_000), "a preferred population outranks a newer normal one")
        expect(got.get("Q18") == ("metro", 900_000), "a unit typed metro and grouping is metro")
        expect("Q19" not in got, "an excluded unit is out")
        expect("Q20" not in got, "a class the file does not name admits nothing, whatever it subclasses")
        spec = amlr.Spec(cc="xx", threshold=45_000, classes={"Q100": "municipal"})
        got = amlr.units("xx")
        expect("Q15" not in got and got.get("Q16") == ("municipal", 48_000), "a file's own threshold applies")
        spec = amlr.Spec(cc="xx")
        expect(amlr.units("xx") == {}, "a country without unit classes has no units")
    finally:
        amlr.get, amlr.candidates, wikidata.fetch_items, eras.current_qids, memo.cached = saved  # type: ignore[assignment]


def main() -> int:
    check_files()
    check_units()
    return 0


if __name__ == "__main__":
    sys.exit(main())
