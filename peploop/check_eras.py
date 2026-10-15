"""Pin when a state existed and whose life it reached, offline.

    .venv/bin/python -m peploop.check_eras
"""

from typing import Any

from peploop import eras


def expect(cond: bool, what: str) -> None:
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        raise SystemExit(1)


def claim(prop: str, value: Any, rank: str = "normal") -> dict[str, Any]:
    datavalue = {"time": value, "precision": 9} if isinstance(value, str) and value[0] in "+-" else {"id": value}
    return {"rank": rank, "mainsnak": {"property": prop, "datavalue": {"value": datavalue}}}


def item(*claims: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, list[dict[str, Any]]] = {}
    for c in claims:
        out.setdefault(c["mainsnak"]["property"], []).append(c)
    return {"claims": out}


def main() -> None:
    republic = item(claim("P571", "+1993-01-01T00:00:00Z", "preferred"), claim("P571", "+1198-00-00T00:00:00Z"))
    expect(eras.entity_span(republic) == [1993, None], "the preferred inception outranks an older normal one")
    russia = item(claim("P571", "+1263-00-00T00:00:00Z", "preferred"), claim("P1365", "Q2"))
    union = item(claim("P571", "+1922-00-00T00:00:00Z"), claim("P576", "+1991-00-00T00:00:00Z"),
                 claim("P1366", "Q1"))
    ents = {"Q1": russia, "Q2": union}
    expect(eras.state_start("Q1", ["Q2"], ents) == 1991, "a home state starts where the predecessor it replaced ended")
    expect(eras.state_start("Q1", [], ents) == 1263, "without its chain, the state's own inception stands")
    empire = item(claim("P571", "+1922-00-00T00:00:00Z"), claim("P576", "+1991-00-00T00:00:00Z"),
                  claim("P1366", "Q9"))
    expect(eras.state_start("Q1", ["Q3"], {**ents, "Q3": empire}) == 1263,
           "a predecessor that names another successor moves nothing")
    expect(not eras.lived_under(1893, 1961, [1993, None]), "a life over before the state began is outside it")
    expect(not eras.lived_under(1995, None, [1918, 1992]), "a life begun after the state ended is outside it")
    expect(eras.lived_under(1930, 1995, [1993, None]), "a life that reaches the state's first years is inside it")
    expect(eras.lived_under(None, None, [1993, None]), "a person nothing dates is never vetoed")
    expect(eras.lived_under(1893, 1961, None), "a state nothing dates vetoes nothing")


if __name__ == "__main__":
    main()
